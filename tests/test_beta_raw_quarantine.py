"""Local raw-cohort packaging; synthetic bytes only, no cloud or scientific data."""
from dataclasses import replace
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile

import pytest

PATH = Path(__file__).resolve().parents[1] / 'deploy/gcp/beta/data/prepare_quarantine.py'
SPEC = importlib.util.spec_from_file_location('beta_raw_quarantine', PATH)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def cohort(tmp_path, rows=None):
    parent = tmp_path.resolve()
    root, original = parent / 'checkout', parent / 'original'
    root.mkdir()
    data = {'data/raw/ctd/casts.tsv': b'synthetic-ctd\n',
        'data/raw/meta/abundance.tsv': b'synthetic-meta\n',
        'onagawa_sst_subset/202601/01/sst.nc': b'synthetic-netcdf\n'}
    for relative, value in data.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    sources = rows if rows is not None else [
        {'source_file':str(original / relative), 'source_dataset':group,
            'file_size_bytes':len(data[relative]), 'sha256':hashlib.sha256(data[relative]).hexdigest()}
        for relative, group in zip(data, ['ctd', 'kraken_genus_sample_tsv', 'sst_netcdf'], strict=True)]
    raw = json.dumps({'schema_version':1, 'source_count':len(sources), 'sources':sources}).encode()
    manifest = root / module.MANIFEST_RELATIVE
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_bytes(raw)
    expected = module.ExpectedCohort(hashlib.sha256(raw).hexdigest(), len(raw), len(sources),
        sum(row['file_size_bytes'] for row in sources), original)
    return root, original, manifest, expected, data


def invoke(root, manifest, expected, output, **kwargs):
    return module.prepare(source_manifest=manifest, source_root=root, checkout_root=root,
        expected=expected, output=output, **kwargs)


def test_default_plan_checks_mapped_sources_without_creating_output(tmp_path):
    root, original, manifest, expected, _data = cohort(tmp_path)
    assert not original.exists()
    output = tmp_path.resolve() / 'plan'
    result = invoke(root, manifest, expected, output)
    assert result['state'] == 'verified_plan_only'
    assert result['files'] == 3 and result['cloud_calls'] is False
    assert not output.exists()


def test_prepare_complete_private_deterministic_archive_and_authority_labels(tmp_path):
    root, original, manifest, expected, data = cohort(tmp_path)
    first = invoke(root, manifest, expected, tmp_path.resolve() / 'first', applying=True)
    second = invoke(root, manifest, expected, tmp_path.resolve() / 'second', applying=True)
    assert first['archive_verification'] == second['archive_verification']
    archive_path = Path(first['archive'])
    assert stat.S_IMODE(archive_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(archive_path.parent.stat().st_mode) == 0o700
    with tarfile.open(archive_path, 'r:') as archive:
        names = archive.getnames()
        assert names == sorted(['payload/' + relative for relative in data]
            + ['source-manifest.json', 'transfer-manifest.json'])
        for relative, value in data.items():
            assert archive.extractfile('payload/' + relative).read() == value
        assert archive.extractfile('source-manifest.json').read() == manifest.read_bytes()
        transfer = json.load(archive.extractfile('transfer-manifest.json'))
        assert transfer['source_path_mapping'] == {
            'original_manifest_root':str(original), 'selected_source_root':str(root),
            'method':'explicit whole-tree prefix mapping; no per-file fallback'}
        assert transfer['file_count'] == 3 and transfer['payload_bytes'] == expected.payload_bytes
        for key in ['scientific_approval', 'normalized', 'c09_snapshot_sealed',
            'catalogue_registered', 'published_or_promoted']:
            assert transfer[key] is False
        assert len(transfer['unresolved_sources']) == 2
        for member in archive:
            assert member.uid == member.gid == member.mtime == 0
            assert member.mode == 0o444 and not member.pax_headers
    assert not (archive_path.parent / 'raw-quarantine.tar.partial').exists()
    assert json.loads((archive_path.parent / 'preparation-receipt.json').read_text()) == first


def test_missing_selected_source_has_no_original_tree_fallback(tmp_path):
    root, original, manifest, expected, data = cohort(tmp_path)
    relative = next(iter(data))
    (original / relative).parent.mkdir(parents=True)
    (original / relative).write_bytes(data[relative])
    (root / relative).unlink()
    output = tmp_path.resolve() / 'missing'
    with pytest.raises(module.QuarantineError, match='inventory|missing, replaced'):
        invoke(root, manifest, expected, output, applying=True)
    assert not output.exists()


@pytest.mark.parametrize('kind', ['file', 'directory', 'manifest'])
def test_symlink_source_or_ancestor_or_manifest_refused(tmp_path, kind):
    root, _original, manifest, expected, data = cohort(tmp_path)
    outside = tmp_path.resolve() / 'outside'
    if kind == 'file':
        relative = next(iter(data))
        outside.write_bytes(data[relative])
        (root / relative).unlink()
        (root / relative).symlink_to(outside)
    elif kind == 'directory':
        (root / 'data/raw/meta').rename(outside)
        (root / 'data/raw/meta').symlink_to(outside, target_is_directory=True)
    else:
        manifest.rename(outside)
        manifest.symlink_to(outside)
    with pytest.raises((module.QuarantineError, OSError)):
        invoke(root, manifest, expected, tmp_path.resolve() / 'refused', applying=True)


def test_preflight_checksum_mismatch_refuses_before_output(tmp_path):
    root, _original, manifest, expected, data = cohort(tmp_path)
    relative = next(iter(data))
    value = data[relative]
    (root / relative).write_bytes(bytes([value[0] ^ 1]) + value[1:])
    output = tmp_path.resolve() / 'bad-checksum'
    with pytest.raises(module.QuarantineError, match='checksum mismatch'):
        invoke(root, manifest, expected, output, applying=True)
    assert not output.exists()


def test_replaced_fifo_is_opened_nonblocking_and_refused(tmp_path):
    root, _original, manifest, expected, data = cohort(tmp_path)
    path = root / next(iter(data))
    path.unlink()
    os.mkfifo(path)
    output = tmp_path.resolve() / 'fifo'
    with pytest.raises(module.QuarantineError, match='regular file'):
        invoke(root, manifest, expected, output, applying=True)
    assert not output.exists()


def test_source_mutation_during_copy_never_accepts_archive(tmp_path, monkeypatch):
    root, _original, manifest, expected, data = cohort(tmp_path)
    relative = sorted(data)[0]
    original_read, changed = module.HashingReader.read, False
    def changing_read(reader, size):
        nonlocal changed
        if not changed:
            changed = True
            (root / relative).write_bytes(b'changed source')
        return original_read(reader, size)
    monkeypatch.setattr(module.HashingReader, 'read', changing_read)
    output = tmp_path.resolve() / 'mutated'
    with pytest.raises(module.QuarantineError, match='changed'):
        invoke(root, manifest, expected, output, applying=True)
    assert (output / 'raw-quarantine.tar.partial').exists()
    assert not (output / 'raw-quarantine.tar').exists()
    assert not (output / 'preparation-receipt.json').exists()


@pytest.mark.parametrize('replacement', [
    '/etc/passwd', '/old/source/data/raw/ctd/../secret',
    '/old/source/data/backups/private.dump', '/old/source/onagawa_sst_subset/.private/key',
])
def test_manifest_paths_outside_explicit_raw_cohort_refused(tmp_path, replacement):
    row = {'source_file':replacement, 'source_dataset':'ctd', 'file_size_bytes':1, 'sha256':'a' * 64}
    root, _original, manifest, expected, _data = cohort(tmp_path, [row])
    expected = replace(expected, historical_root=Path('/old/source'))
    with pytest.raises(module.QuarantineError):
        invoke(root, manifest, expected, tmp_path.resolve() / 'invalid-path')


def test_manifest_identity_and_declared_bounds_are_strict(tmp_path):
    root, _original, manifest, expected, _data = cohort(tmp_path)
    output = tmp_path.resolve() / 'limits'
    for wrong in [replace(expected, manifest_sha256='0' * 64),
        replace(expected, manifest_bytes=module.MAX_MANIFEST_BYTES + 1),
        replace(expected, files=module.MAX_SOURCE_FILES + 1),
        replace(expected, payload_bytes=module.MAX_PAYLOAD_BYTES + 1)]:
        with pytest.raises(module.QuarantineError):
            invoke(root, manifest, wrong, output)
    assert not output.exists()


def test_duplicate_manifest_member_refused(tmp_path):
    original = tmp_path.resolve() / 'original'
    row = {'source_file':str(original / 'data/raw/ctd/one.tsv'), 'source_dataset':'ctd',
        'file_size_bytes':1, 'sha256':'a' * 64}
    root, _original, manifest, expected, _data = cohort(tmp_path, [row, row])
    with pytest.raises(module.QuarantineError, match='Duplicate raw-source path'):
        invoke(root, manifest, expected, tmp_path.resolve() / 'duplicate')


def alias_cohort(tmp_path):
    root, original, manifest, expected, data = cohort(tmp_path)
    document = json.loads(manifest.read_text())
    document['sources'].append(dict(document['sources'][0]))
    document['source_count'] = 4
    raw = json.dumps(document).encode()
    manifest.write_bytes(raw)
    expected = replace(expected, manifest_sha256=hashlib.sha256(raw).hexdigest(),
        manifest_bytes=len(raw), files=4, payload_bytes=expected.payload_bytes + len(next(iter(data.values()))))
    relative, value = next(iter(data.items()))
    alias = 'data/raw/ctd/reviewed-alias.tsv'
    (root / alias).write_bytes(value)
    amendment = {'version':'ocean-beta-raw-path-alias-amendment-v1',
        'source_manifest_sha256':expected.manifest_sha256,
        'scientific_approval':False, 'publication_or_c09_seal':False,
        'original_entry_count':4, 'original_unique_paths':3, 'alias_paths':1,
        'result_unique_paths':4, 'result_payload_bytes':expected.payload_bytes,
        'aliases':[{'alias_path':alias, 'original_referenced_path':relative,
            'original_manifest_entry_indices':[0, 3], 'source_dataset':'ctd',
            'bytes':len(value), 'sha256':hashlib.sha256(value).hexdigest()}]}
    return root, original, manifest, expected, data, amendment


def test_explicit_matching_alias_amendment_preserves_original_and_archives_unique_paths(tmp_path):
    root, _original, manifest, expected, _data, amendment = alias_cohort(tmp_path)
    original_bytes = manifest.read_bytes()
    amendment_bytes = module.canonical(amendment)
    result = invoke(root, manifest, expected, tmp_path.resolve() / 'aliases', applying=True,
        _test_amendment=amendment_bytes)
    assert result['files'] == 4 and result['archive_verification']['members'] == 7
    assert result['path_amendment_sha256'] == hashlib.sha256(amendment_bytes).hexdigest()
    assert manifest.read_bytes() == original_bytes
    with tarfile.open(result['archive'], 'r:') as archive:
        assert len(set(archive.getnames())) == 7
        assert archive.extractfile('source-manifest.json').read() == original_bytes
        assert archive.extractfile('scope-amendment.json').read() == amendment_bytes
        transfer = json.load(archive.extractfile('transfer-manifest.json'))
        assert transfer['path_alias_amendment']['original_unique_paths'] == 3
        assert transfer['path_alias_amendment']['alias_paths'] == 1


@pytest.mark.parametrize('kind', ['no-amendment', 'wrong-bytes', 'extra-alias', 'wrong-indices', 'unlisted-file'])
def test_alias_reconciliation_refuses_missing_wrong_or_extra_authority(tmp_path, kind):
    root, _original, manifest, expected, _data, amendment = alias_cohort(tmp_path)
    if kind == 'wrong-bytes':
        amendment['aliases'][0]['sha256'] = '0' * 64
    elif kind == 'extra-alias':
        amendment['aliases'].append(dict(amendment['aliases'][0], alias_path='data/raw/ctd/extra.tsv'))
    elif kind == 'wrong-indices':
        amendment['aliases'][0]['original_manifest_entry_indices'] = [0, 2]
    elif kind == 'unlisted-file':
        (root / 'data/raw/ctd/unlisted.tsv').write_bytes(b'unapproved')
    kwargs = {} if kind == 'no-amendment' else {'_test_amendment':module.canonical(amendment)}
    output = tmp_path.resolve() / 'bad-alias'
    with pytest.raises(module.QuarantineError):
        invoke(root, manifest, expected, output, applying=True, **kwargs)
    assert not output.exists()


def test_output_in_checkout_or_existing_or_symlink_ancestor_refused(tmp_path):
    root, _original, manifest, expected, _data = cohort(tmp_path)
    existing = tmp_path.resolve() / 'existing'
    existing.mkdir()
    link = tmp_path.resolve() / 'link'
    link.symlink_to(existing, target_is_directory=True)
    for output in [root / 'output', existing, link / 'child']:
        with pytest.raises(module.QuarantineError):
            invoke(root, manifest, expected, output, applying=True)


def test_archive_verifier_rejects_unexpected_appended_member(tmp_path):
    root, _original, manifest, expected, _data = cohort(tmp_path)
    result = invoke(root, manifest, expected, tmp_path.resolve() / 'archive', applying=True)
    path = Path(result['archive'])
    with tarfile.open(path, 'a:') as archive:
        archive.addfile(module.info('unapproved-file', 1), io.BytesIO(b'x'))
    raw, sources, _pinned = module.read_manifest(manifest, checkout_root=root,
        source_root=root, expected=expected)
    metadata = {'source-manifest.json':raw,
        'transfer-manifest.json':module.canonical(module.transfer_manifest(root, sources, expected))}
    with pytest.raises(module.QuarantineError, match='inventory'):
        module.verify_archive(path, sources, metadata)
