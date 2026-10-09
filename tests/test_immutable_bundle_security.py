"""Untrusted bundle names must never open files outside the verified store."""
import hashlib
import json
import os

import pytest

from ingestion.immutable_bundle import read_bundle

IDENTITY = 'a' * 64


def bundle(root, files, *, content=b'verified result'):
    directory = root / IDENTITY
    directory.mkdir(parents=True)
    (directory / 'result.json').write_bytes(content)
    manifest = {'id': IDENTITY, 'files': files}
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    return directory


@pytest.mark.parametrize('name', ['../private.json', '/private.json', '..\\private.json', '', 'manifest.json', './result.json'])
def test_unsafe_manifest_names_rejected_before_external_read(tmp_path, name):
    private = tmp_path / 'private.json'
    private.write_bytes(b'private')
    root = tmp_path / 'store'
    bundle(root, {name: hashlib.sha256(b'private').hexdigest()})
    with pytest.raises(ValueError, match='Invalid bundle path'):
        read_bundle(root, IDENTITY)
    assert private.read_bytes() == b'private'


@pytest.mark.parametrize('component', ['root', 'bundle', 'manifest', 'result'])
def test_bundle_symlinks_rejected(tmp_path, component):
    root = tmp_path / 'store'
    data = b'verified result'
    directory = bundle(root, {'result.json': hashlib.sha256(data).hexdigest()})
    if component in ('root', 'bundle'):
        original = root if component == 'root' else directory
        outside = tmp_path / 'outside'
        original.rename(outside)
        original.symlink_to(outside, target_is_directory=True)
    else:
        path = directory / ('manifest.json' if component == 'manifest' else 'result.json')
        outside = tmp_path / 'private.json'
        path.rename(outside)
        path.symlink_to(outside)
    with pytest.raises(ValueError):
        read_bundle(root, IDENTITY)


def test_verified_bytes_and_resource_limit(tmp_path):
    data = b'x' * 4096
    root = tmp_path / 'store'
    bundle(root, {'result.json': hashlib.sha256(data).hexdigest()}, content=data)
    _, contents = read_bundle(root, IDENTITY)
    assert contents['result.json'] == data
    with pytest.raises(ValueError, match='Bundle byte resource limit exceeded'):
        read_bundle(root, IDENTITY, max_bytes=1024)
    with pytest.raises(ValueError, match='Bundle manifest limit exceeded'):
        read_bundle(root, IDENTITY, max_bytes=8)


@pytest.mark.parametrize('kind', ['directory', 'fifo'])
def test_nonregular_bundle_result_cannot_be_opened(tmp_path, kind):
    root = tmp_path / 'store'
    directory = bundle(root, {'result.json': hashlib.sha256(b'').hexdigest()})
    path = directory / 'result.json'
    path.unlink()
    if kind == 'directory':
        path.mkdir()
    else:
        os.mkfifo(path)
    with pytest.raises(ValueError, match='Bundle integrity check failed'):
        read_bundle(root, IDENTITY)
