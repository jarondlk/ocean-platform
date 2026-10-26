"""Temporary-tree normalization checks; no real image or GNU cp is executed."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import shutil

import pytest

from sandbox.experiment.gcp import normalize_rootfs as normalizer
from sandbox.experiment.gcp import run_operator_acceptance as operator
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.profile import rootfs_inventory_sha256


TARGET = {'project': operator.PROJECT, 'instance': operator.INSTANCE, 'linux_root_guard': True}


@pytest.fixture
def tree(tmp_path):
    source = tmp_path / 'source'
    source.mkdir(mode=0o755)
    (source / 'usr/bin').mkdir(parents=True)
    (source / 'usr/bin/gunzip').write_bytes(b'fixed synthetic bytes\x00\xff\n')
    (source / 'usr/bin/gunzip').chmod(0o555)
    os.link(source / 'usr/bin/gunzip', source / 'usr/bin/uncompress')
    (source / 'empty').write_bytes(b'')
    (source / 'bin').symlink_to('usr/bin', target_is_directory=True)
    (source / 'guest-absolute').symlink_to('/usr/bin/gunzip')
    return source


def document(source, destination):
    before = normalizer.scan_tree(source)
    copied = normalizer.scan_tree(destination, require_single_links=True)
    return {'version': normalizer.VERSION, 'label': normalizer.LABEL, 'target': TARGET,
        'recorded_at': '2026-10-25T09:00:00+00:00',
        'command': ['/usr/bin/cp', '-a', '--no-preserve=links', '--reflink=auto', '--',
                    str(source), str(destination)],
        'helper_sha256': hashlib.sha256(Path(normalizer.__file__).read_bytes()).hexdigest(),
        'cp_exit_status': 0, 'cp_version_sha256': 'a' * 64,
        'source_rootfs': str(source), 'destination_rootfs': str(destination),
        'source_semantic_sha256': before['semantic_sha256'],
        'destination_semantic_sha256': copied['semantic_sha256'],
        'source_snapshot_before_sha256': before['snapshot_sha256'],
        'source_snapshot_after_sha256': before['snapshot_sha256'],
        'source_hardlink_topology_sha256': before['hardlink_topology_sha256'],
        'source_counts': before['counts'], 'destination_counts': copied['counts'],
        'destination_rootfs_inventory_sha256': rootfs_inventory_sha256(destination),
        'source_unchanged': True, 'semantic_equivalence': True, 'all_regular_nlink_one': True,
        'source_inode_confinement_verified': True, 'C23_complete': False, 'dispatch_eligible': False}


def copied(tree, tmp_path):
    destination = tmp_path / 'normalized'
    shutil.copytree(tree, destination, symlinks=True, copy_function=shutil.copy2)
    return destination


def test_real_hardlinks_split_preserving_bytes_modes_owners_and_guest_symlinks(tree, tmp_path):
    source_before = normalizer.scan_tree(tree)
    destination = copied(tree, tmp_path)
    proof = document(tree, destination)
    verified = normalizer.verify_normalization_receipt(proof, source=tree, destination=destination)
    assert proof == verified and len(normalizer._canonical(verified)) < 4 * 1024**2
    assert source_before == normalizer.scan_tree(tree)
    assert source_before['counts']['hardlink_groups'] == 1
    assert verified['destination_counts']['hardlink_groups'] == 0
    for name in ('gunzip', 'uncompress'):
        left, right = tree / 'usr/bin' / name, destination / 'usr/bin' / name
        assert left.read_bytes() == right.read_bytes()
        assert (left.stat().st_mode, left.stat().st_uid, left.stat().st_gid) == (
            right.stat().st_mode, right.stat().st_uid, right.stat().st_gid)
        assert left.stat().st_nlink == 2 and right.stat().st_nlink == 1
    assert os.readlink(destination / 'guest-absolute') == '/usr/bin/gunzip'
    assert os.readlink(destination / 'bin') == 'usr/bin'
    assert (destination / 'usr/bin/gunzip').stat().st_ino != (destination / 'usr/bin/uncompress').stat().st_ino
    with pytest.raises(SandboxError):
        rootfs_inventory_sha256(tree)  # Accepted guard still rejects source nlink2.


@pytest.mark.parametrize('change', ['content', 'mode', 'symlink', 'hardlink'])
def test_changed_destination_cannot_reuse_valid_provenance(tree, tmp_path, change):
    destination = copied(tree, tmp_path)
    proof = document(tree, destination)
    target = destination / 'usr/bin/gunzip'
    if change == 'content':
        target.chmod(0o755)
        target.write_bytes(b'changed')
    elif change == 'mode':
        target.chmod(0o444)
    elif change == 'symlink':
        (destination / 'bin').unlink()
        (destination / 'bin').symlink_to('/different')
    else:
        (destination / 'usr/bin/uncompress').unlink()
        os.link(target, destination / 'usr/bin/uncompress')
    with pytest.raises(normalizer.NormalizationError):
        normalizer.verify_normalization_receipt(proof, source=tree, destination=destination)


def test_source_change_after_copy_invalidates_historical_snapshot(tree, tmp_path):
    destination = copied(tree, tmp_path)
    proof = document(tree, destination)
    (tree / 'empty').write_bytes(b'changed source')
    with pytest.raises(normalizer.NormalizationError):
        normalizer.verify_normalization_receipt(proof, source=tree, destination=destination)


def test_source_alias_outside_materialized_tree_is_rejected(tree, tmp_path):
    os.link(tree / 'empty', tmp_path / 'external-alias')
    with pytest.raises(normalizer.NormalizationError, match='outside_tree'):
        normalizer.scan_tree(tree)


@pytest.mark.parametrize('unsafe', ['fifo', 'escaping_symlink'])
def test_scan_never_opens_unsafe_nodes_or_traverses_symlinks(tree, unsafe):
    if unsafe == 'fifo':
        os.mkfifo(tree / 'unsafe')
    else:
        (tree / 'unsafe').symlink_to('../outside')
    with pytest.raises(normalizer.NormalizationError):
        normalizer.scan_tree(tree)


@pytest.mark.parametrize('key,value', [('helper_sha256', 'f' * 64), ('target', {}),
    ('cp_exit_status', True), ('source_unchanged', False), ('dispatch_eligible', True),
    ('source_semantic_sha256', 'f' * 64), ('destination_rootfs_inventory_sha256', 'f' * 64),
    ('source_hardlink_topology_sha256', 'f' * 64), ('scientific_approval', 'invented')])
def test_receipt_cannot_omit_or_forge_pins_and_authority(tree, tmp_path, key, value):
    destination = copied(tree, tmp_path)
    proof = document(tree, destination)
    proof[key] = value
    with pytest.raises(normalizer.NormalizationError):
        normalizer.verify_normalization_receipt(proof, source=tree, destination=destination)


def test_mutating_returned_receipt_cannot_change_input_provenance(tree, tmp_path):
    destination = copied(tree, tmp_path)
    proof = document(tree, destination)
    before = deepcopy(proof)
    value = normalizer.verify_normalization_receipt(proof, source=tree, destination=destination)
    value['source_counts']['entries'] = 999
    assert proof == before


def test_real_macos_guard_precedes_any_process_or_filesystem_effect(monkeypatch):
    monkeypatch.setattr(operator.sys, 'platform', 'darwin')
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Effect before dedicated Linux worker guard')
    monkeypatch.setattr(normalizer, '_directory', forbidden)
    monkeypatch.setattr(normalizer, '_capture', forbidden)
    with pytest.raises(operator.OperatorError, match='dedicated_linux_root_worker_required'):
        normalizer.normalize(normalizer.LABEL)


@pytest.mark.parametrize('existing', [False, True])
def test_guarded_pipeline_uses_fixed_gnu_arguments_and_never_replaces_target(tree, tmp_path, monkeypatch, existing):
    root = tmp_path / 'worker'
    root.mkdir(mode=0o700)
    (root / 'evidence').mkdir(mode=0o700)
    original = root / 'scientific-bundle-quota-v3'
    original.mkdir()
    source = original / 'rootfs'
    shutil.copytree(tree, source, symlinks=True)
    # Restore the fixture's trusted source hardlink topology after copying it.
    (source / 'usr/bin/uncompress').unlink()
    os.link(source / 'usr/bin/gunzip', source / 'usr/bin/uncompress')
    parent = root / 'scientific-normalized-quota-v3'
    if existing:
        parent.mkdir(mode=0o700)
        (parent / 'preserve').write_bytes(b'original')
    calls = []
    def capture(argv, *, timeout):
        calls.append(argv)
        if argv == ['/usr/bin/cp', '--version']:
            return 0, {'stdout': b'cp (GNU coreutils) 9.4\n', 'stderr': b''}
        assert argv == ['/usr/bin/cp', '-a', '--no-preserve=links', '--reflink=auto', '--',
                        str(source), str(parent / 'rootfs')]
        shutil.copytree(source, parent / 'rootfs', symlinks=True, copy_function=shutil.copy2)
        return 0, {'stdout': b'', 'stderr': b''}
    monkeypatch.setattr(normalizer, 'FIXED_ROOT', root)
    monkeypatch.setattr(operator, 'require_worker', lambda: TARGET)
    monkeypatch.setattr(normalizer, '_capture', capture)
    if existing:
        with pytest.raises(normalizer.NormalizationError, match='target_exists'):
            normalizer.normalize('quota-v3')
        assert calls == [] and (parent / 'preserve').read_bytes() == b'original'
    else:
        result = normalizer.normalize('quota-v3')
        assert result['dispatch_eligible'] is False
        assert Path(result['receipt']).stat().st_mode & 0o777 == 0o400
        assert normalizer.scan_tree(source)['counts']['hardlink_groups'] == 1
        assert len(calls) == 2
