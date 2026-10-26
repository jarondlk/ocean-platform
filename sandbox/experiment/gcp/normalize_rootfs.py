"""Split trusted OCI hardlinks in a separate tree without relaxing C23 guards.

Only ``normalize`` mutates materialization paths, after the dedicated-worker
guard. The scanner/verifier are read-only and may inspect temporary test trees.
No image, generated analysis, cloud command or package installer is executed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import posixpath
import selectors
import stat
import subprocess
import time

VERSION = 'c23-trusted-hardlink-normalization-v1'
LABEL = 'quota-v3'
FIXED_ROOT = Path('/var/lib/ocean-c23')
MAX_ENTRIES = 100000
MAX_BYTES = 8 * 1024**3
MAX_LOG = 1024**2
RECEIPT_KEYS = frozenset(('version', 'label', 'target', 'recorded_at', 'command', 'helper_sha256',
    'cp_exit_status', 'cp_version_sha256', 'source_rootfs', 'destination_rootfs',
    'source_semantic_sha256', 'destination_semantic_sha256', 'source_snapshot_before_sha256',
    'source_snapshot_after_sha256', 'source_hardlink_topology_sha256', 'source_counts',
    'destination_counts', 'destination_rootfs_inventory_sha256', 'source_unchanged',
    'semantic_equivalence', 'all_regular_nlink_one', 'source_inode_confinement_verified',
    'C23_complete', 'dispatch_eligible'))


class NormalizationError(ValueError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _directory(path):
    path = Path(path)
    info = path.lstat()
    if (not path.is_absolute() or path != path.resolve(strict=True)
            or not stat.S_ISDIR(info.st_mode)):
        raise NormalizationError('canonical_directory_required')
    return path


def _stamp(info):
    # atime can change during a legitimate read; it is not a source-byte change.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def scan_tree(path, *, require_single_links=False):
    """Bounded, no-follow semantic inventory and exact source inode snapshot."""
    path = _directory(path)
    semantics, snapshots, groups = [], [], {}
    total, count = 0, 0
    root_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    root = os.fstat(root_fd)

    def visit(fd, prefix, depth):
        nonlocal total, count
        if depth > 64:
            raise NormalizationError('tree_depth_limit')
        before_dir = os.fstat(fd)
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                count += 1
                if count > MAX_ENTRIES:
                    raise NormalizationError('tree_entry_limit')
                name = entry.name
                if (name in {'.', '..'} or '\n' in name or '\r' in name
                        or not 1 <= len(name.encode('utf-8')) <= 255):
                    raise NormalizationError('tree_name')
                names.append(name)
        for name in sorted(names):
            relative = prefix + name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if info.st_dev != root.st_dev:
                raise NormalizationError('tree_cross_device')
            row = {'path': relative, 'mode': stat.S_IMODE(info.st_mode),
                   'uid': info.st_uid, 'gid': info.st_gid}
            if stat.S_ISDIR(info.st_mode):
                row['kind'] = 'directory'
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                try:
                    if _stamp(os.fstat(child)) != _stamp(info):
                        raise NormalizationError('source_changed')
                    visit(child, relative + '/', depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                if (info.st_nlink < 1 or require_single_links and info.st_nlink != 1
                        or not 0 <= info.st_size <= MAX_BYTES - total):
                    raise NormalizationError('regular_file_bounds_or_links')
                opened = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
                try:
                    if _stamp(os.fstat(opened)) != _stamp(info):
                        raise NormalizationError('source_changed')
                    checksum, observed = hashlib.sha256(), 0
                    while True:
                        raw = os.read(opened, min(1024**2, info.st_size + 1 - observed))
                        if not raw:
                            break
                        observed += len(raw)
                        if observed > info.st_size:
                            raise NormalizationError('source_changed')
                        checksum.update(raw)
                    if observed != info.st_size or _stamp(os.fstat(opened)) != _stamp(info):
                        raise NormalizationError('source_changed')
                finally:
                    os.close(opened)
                total += info.st_size
                row.update(kind='file', size_bytes=info.st_size, sha256=checksum.hexdigest())
                group = groups.setdefault((info.st_dev, info.st_ino), {'nlink': info.st_nlink, 'paths': []})
                if group['nlink'] != info.st_nlink:
                    raise NormalizationError('source_changed')
                group['paths'].append(relative)
            elif stat.S_ISLNK(info.st_mode):
                target = os.readlink(name, dir_fd=fd)
                if (not target or target.startswith('//') or '\n' in target or '\r' in target
                        or len(target.encode('utf-8')) > 4096):
                    raise NormalizationError('symlink_target')
                logical = posixpath.normpath(target if target.startswith('/') else posixpath.join(prefix, target))
                if logical == '..' or logical.startswith('../'):
                    raise NormalizationError('symlink_escape')
                row.update(kind='symlink', target=target)
            else:
                raise NormalizationError('special_file')
            if _stamp(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _stamp(info):
                raise NormalizationError('source_changed')
            semantics.append(row)
            snapshots.append({'path': relative, 'stamp': _stamp(info)})
        if _stamp(os.fstat(fd)) != _stamp(before_dir):
            raise NormalizationError('source_changed')

    try:
        semantics.append({'path': '.', 'kind': 'directory', 'mode': stat.S_IMODE(root.st_mode),
                          'uid': root.st_uid, 'gid': root.st_gid})
        snapshots.append({'path': '.', 'stamp': _stamp(root)})
        visit(root_fd, '', 0)
        if _stamp(path.lstat()) != _stamp(root) or _stamp(os.fstat(root_fd)) != _stamp(root):
            raise NormalizationError('source_changed')
    finally:
        os.close(root_fd)
    topology = []
    for (_device, _inode), group in groups.items():
        # No source regular inode may have an undiscovered alias outside this tree.
        if len(group['paths']) != group['nlink']:
            raise NormalizationError('source_hardlink_outside_tree')
        if group['nlink'] > 1:
            topology.append(group)
    topology.sort(key=lambda item: item['paths'])
    return {'semantic_sha256': _sha(_canonical(sorted(semantics, key=lambda item: item['path']))),
            'snapshot_sha256': _sha(_canonical(sorted(snapshots, key=lambda item: item['path']))),
            'hardlink_topology_sha256': _sha(_canonical(topology)),
            'counts': {'entries': count, 'regular_files': len([row for row in semantics if row['kind'] == 'file']),
                       'regular_bytes': total, 'hardlink_groups': len(topology),
                       'hardlinked_paths': sum(len(group['paths']) for group in topology)}}


def _strict_inventory(path):
    from orchestration.experiment_sandbox.profile import rootfs_inventory_sha256
    return rootfs_inventory_sha256(path)


def verify_normalization_receipt(document, *, source, destination):
    """Recompute provenance; this function grants no execution authority."""
    source, destination = _directory(source), _directory(destination)
    target = {'project': 'ocean-v1-c23-20261024', 'instance': 'c23-containment-01', 'linux_root_guard': True}
    if (type(document) is not dict or set(document) != RECEIPT_KEYS or document.get('version') != VERSION
            or document.get('label') != LABEL or document.get('source_rootfs') != str(source)
            or document.get('destination_rootfs') != str(destination)
            or document.get('command') != ['/usr/bin/cp', '-a', '--no-preserve=links', '--reflink=auto',
                                          '--', str(source), str(destination)]
            or type(document.get('cp_exit_status')) is not int or document['cp_exit_status'] != 0
            or document.get('helper_sha256') != _sha(Path(__file__).read_bytes())
            or _canonical(document.get('target')) != _canonical(target)
            or any(document.get(key) is not True for key in ('source_unchanged', 'semantic_equivalence',
                'all_regular_nlink_one', 'source_inode_confinement_verified'))
            or any(document.get(key) is not False for key in ('C23_complete', 'dispatch_eligible'))):
        raise NormalizationError('normalization_receipt_shape')
    before = scan_tree(source)
    copied = scan_tree(destination, require_single_links=True)
    after = scan_tree(source)
    if (before != after or before['semantic_sha256'] != copied['semantic_sha256']
            or document.get('source_semantic_sha256') != before['semantic_sha256']
            or document.get('destination_semantic_sha256') != copied['semantic_sha256']
            or document.get('source_snapshot_before_sha256') != before['snapshot_sha256']
            or document.get('source_snapshot_after_sha256') != after['snapshot_sha256']
            or document.get('source_hardlink_topology_sha256') != before['hardlink_topology_sha256']
            or document.get('source_counts') != before['counts'] or document.get('destination_counts') != copied['counts']
            or document.get('destination_rootfs_inventory_sha256') != _strict_inventory(destination)):
        raise NormalizationError('normalization_provenance_mismatch')
    raw = _canonical(document)
    if len(raw) > 4 * 1024**2:
        raise NormalizationError('normalization_receipt_limit')
    return json.loads(raw)


def _capture(command, *, timeout):
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, close_fds=True, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    selector = selectors.DefaultSelector()
    retained = {'stdout': bytearray(), 'stderr': bytearray()}
    deadline = time.monotonic() + timeout
    try:
        for stream, name in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            if time.monotonic() >= deadline:
                raise NormalizationError('copy_timeout')
            for key, _ in selector.select(min(0.05, max(0, deadline - time.monotonic()))):
                raw = os.read(key.fd, 65536)
                if not raw:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                else:
                    retained[key.data].extend(raw)
                    if len(retained[key.data]) > MAX_LOG:
                        raise NormalizationError('copy_log_limit')
        return process.wait(timeout=max(0.01, deadline - time.monotonic())), {
            name: bytes(raw) for name, raw in retained.items()}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for key in list(selector.get_map().values()):
            key.fileobj.close()
        selector.close()


def normalize(label):
    from sandbox.experiment.gcp.run_operator_acceptance import _create, _private_directory, require_worker
    target = require_worker()  # Before path reads, mkdir or any cp process.
    if label != LABEL:
        raise NormalizationError('fixed_label_required')
    _private_directory(FIXED_ROOT)
    source = _directory(FIXED_ROOT / ('scientific-bundle-' + label) / 'rootfs')
    parent = FIXED_ROOT / ('scientific-normalized-' + label)
    destination = parent / 'rootfs'
    receipt = FIXED_ROOT / 'evidence' / ('rootfs-normalization-' + label + '.json')
    if parent.exists() or parent.is_symlink() or receipt.exists() or receipt.is_symlink():
        raise NormalizationError('normalization_target_exists')
    before = scan_tree(source)
    status, version = _capture(['/usr/bin/cp', '--version'], timeout=5)
    if status != 0 or not version['stdout'].startswith(b'cp (GNU coreutils)'):
        raise NormalizationError('gnu_cp_required')
    _private_directory(parent, create=True)
    command = ['/usr/bin/cp', '-a', '--no-preserve=links', '--reflink=auto', '--', str(source), str(destination)]
    _create(parent / 'copy-intent.json', _canonical({'version': VERSION, 'target': target,
        'command': command, 'source_before': before, 'helper_sha256': _sha(Path(__file__).read_bytes())}))
    status, logs = _capture(command, timeout=300)
    for name, raw in logs.items():
        _create(parent / ('copy-' + name + '.bin'), raw)
    if status != 0:
        raise NormalizationError('gnu_cp_failed')
    copied = scan_tree(destination, require_single_links=True)
    after = scan_tree(source)
    if before != after or before['semantic_sha256'] != copied['semantic_sha256']:
        raise NormalizationError('copy_changed_source_or_semantics')
    document = {'version': VERSION, 'label': label, 'target': target,
        'recorded_at': datetime.now(timezone.utc).isoformat(), 'command': command,
        'helper_sha256': _sha(Path(__file__).read_bytes()), 'cp_exit_status': status,
        'cp_version_sha256': _sha(version['stdout']),
        'source_rootfs': str(source), 'destination_rootfs': str(destination),
        'source_semantic_sha256': before['semantic_sha256'],
        'destination_semantic_sha256': copied['semantic_sha256'],
        'source_snapshot_before_sha256': before['snapshot_sha256'],
        'source_snapshot_after_sha256': after['snapshot_sha256'],
        'source_hardlink_topology_sha256': before['hardlink_topology_sha256'],
        'source_counts': before['counts'], 'destination_counts': copied['counts'],
        'destination_rootfs_inventory_sha256': _strict_inventory(destination),
        'source_unchanged': True, 'semantic_equivalence': True,
        'all_regular_nlink_one': True, 'source_inode_confinement_verified': True,
        'C23_complete': False, 'dispatch_eligible': False}
    verify_normalization_receipt(document, source=source, destination=destination)
    _create(receipt, _canonical(document))
    return {'receipt': str(receipt), 'sha256': _sha(_canonical(document)),
            'destination_rootfs': str(destination), 'dispatch_eligible': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True, choices=[LABEL])
    args = parser.parse_args()
    print(json.dumps(normalize(args.label), sort_keys=True))


if __name__ == '__main__':
    main()
