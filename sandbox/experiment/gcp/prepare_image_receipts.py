"""Create-only identity receipts for the dedicated C23 worker's offline image.

This records materialization, not containment acceptance or dispatch authority.
No image or analysis code is executed. The runtime install, complete OCI blobs,
reviewed context, build verifier observation and materialized bytes must agree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from orchestration.experiment_sandbox.profile import (
    ImagePreparation, RuntimePreparation, rootfs_inventory_sha256,
)
from sandbox.experiment.gcp.run_operator_acceptance import (
    APP_GID, APP_UID, FIXED_ROOT, _create, _read, require_worker,
)
from sandbox.experiment.verify_image import validate_materials


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _blob(root, descriptor, maximum, *, retain=True):
    digest = descriptor['digest']
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise ValueError('oci_digest')
    path = root / 'blobs' / 'sha256' / digest[7:]
    if retain:
        raw = _read(path, maximum)
        if len(raw) != descriptor['size'] or _sha(raw) != digest[7:]:
            raise ValueError('oci_blob_integrity')
        return raw
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or not 0 <= before.st_size == descriptor['size'] <= maximum):
        raise ValueError('oci_blob_integrity')
    descriptor_fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        def stamp(info):
            return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                    info.st_nlink, info.st_uid, info.st_gid, info.st_mtime_ns, info.st_ctime_ns)
        checksum, size = hashlib.sha256(), 0
        while True:
            raw = os.read(descriptor_fd, 1024**2)
            if not raw:
                break
            size += len(raw)
            if size > before.st_size:
                raise ValueError('oci_blob_integrity')
            checksum.update(raw)
        if (size != before.st_size or checksum.hexdigest() != digest[7:]
                or stamp(os.fstat(descriptor_fd)) != stamp(before)
                or stamp(path.lstat()) != stamp(before)):
            raise ValueError('oci_blob_integrity')
    finally:
        os.close(descriptor_fd)
    return None


def record(label, wrapper_sha256):
    require_worker()
    if not re.fullmatch(r'quota-v[3-9][0-9]*', label):
        raise ValueError('fixed_amendment_label_required')
    if not re.fullmatch(r'[a-f0-9]{64}', wrapper_sha256):
        raise ValueError('reviewed_wrapper_sha256_required')
    # Every amendment has separate context, OCI tree, rootfs and observations.
    context = FIXED_ROOT / ('build-context-' + label)
    oci = FIXED_ROOT / ('scientific-oci-' + label)
    rootfs = FIXED_ROOT / ('scientific-bundle-' + label) / 'rootfs'
    evidence = FIXED_ROOT / 'evidence'
    materials_raw = _read(context / 'build-materials.json', 1024**2)
    lock = _read(context / 'requirements.lock', 4 * 1024**2)
    materials = json.loads(materials_raw)
    validate_materials(materials, lock, base_reference=materials['base_reference'])
    wrapper = _read(context / 'trusted_init.py', 1024**2)
    installed_wrapper = _read(rootfs / 'opt/c23/trusted_init.py', 1024**2)
    if _sha(wrapper) != wrapper_sha256 or installed_wrapper != wrapper:
        raise ValueError('installed_wrapper_identity')
    installed = json.loads(_read(evidence / 'installed-runtime.json', 1024**2))
    runtime = RuntimePreparation.model_validate({
        'version': 'c23-runtime-preparation-v1', 'evidence_class': 'configuration-only',
        'release': installed['release'], 'architecture': installed['architecture'],
        'files': installed['files'], 'input_host_uid': APP_UID, 'input_host_gid': APP_GID,
    }).model_dump(mode='json')
    if runtime['release'] != 'release-20261019.0' or runtime['architecture'] != 'amd64':
        raise ValueError('pinned_dedicated_worker_runtime_required')
    runtime_root = Path('/opt/ocean-c23-runtime') / runtime['release']
    for name, digest in runtime['files'].items():
        if _sha(_read(runtime_root / name, 256 * 1024**2)) != digest:
            raise ValueError('installed_runtime_identity')
    index = json.loads(_read(oci / 'index.json', 1024**2))
    if index['schemaVersion'] != 2 or len(index['manifests']) != 1:
        raise ValueError('one_platform_oci_manifest_required')
    descriptor = index['manifests'][0]
    manifest_raw = _blob(oci, descriptor, 4 * 1024**2)
    manifest = json.loads(manifest_raw)
    if manifest['schemaVersion'] != 2 or not 1 <= len(manifest['layers']) <= 256:
        raise ValueError('oci_manifest_shape')
    config = json.loads(_blob(oci, manifest['config'], 4 * 1024**2))
    if config['architecture'] != 'amd64' or config['os'] != 'linux':
        raise ValueError('linux_amd64_image_required')
    for layer in manifest['layers']:
        _blob(oci, layer, 2 * 1024**3, retain=False)
    # The trusted offline build runs the installed-inventory verifier itself.
    # A declaration in the input manifest alone cannot satisfy this check.
    observations = []
    for line in _read(evidence / ('image-build-' + label + '.stdout.txt'), 16 * 1024**2).splitlines():
        try:
            value = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if isinstance(value, dict) and value.get('dependency_graph') == 'verified':
            observations.append(value)
    expected = {'python_version': materials['python_version'],
                'packages': materials['packages'], 'dependency_graph': 'verified'}
    if observations != [expected]:
        raise ValueError('actual_build_inventory_observation_required')
    image = ImagePreparation.model_validate({
        'version': 'c23-image-preparation-v1', 'evidence_class': 'configuration-only',
        'image_digest': descriptor['digest'],
        'base_image_digest': materials['base_reference'].rsplit('@', 1)[1],
        'architecture': 'amd64', 'python_version': materials['python_version'],
        'lockfile_sha256': _sha(lock), 'packages': materials['packages'],
        'oci_manifest_sha256': _sha(manifest_raw),
        'oci_config_sha256': manifest['config']['digest'][7:],
        'layer_sha256': [item['digest'][7:] for item in manifest['layers']],
        'rootfs_inventory_sha256': rootfs_inventory_sha256(rootfs),
    }).model_dump(mode='json')
    document = {'version': 'c23-worker-materialization-v1', 'label': label,
                'trusted_init_sha256': wrapper_sha256,
                'image': image, 'runtime': runtime,
                'containment_verified': False, 'dispatch_eligible': False,
                'scientific_approval': 'not_independently_verified'}
    for name, value in ((f'image-preparation-{label}.json', image),
                        (f'runtime-preparation-{label}.json', runtime),
                        (f'materialization-{label}.json', document)):
        _create(evidence / name, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--trusted-init-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(record(args.label, args.trusted_init_sha256), sort_keys=True))


if __name__ == '__main__':
    main()
