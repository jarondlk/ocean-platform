"""Stage one explicitly selected existing raw cohort; no cloud or publication.

Default is a verified local plan. --prepare copies only the pinned source cohort
into a new private directory outside both the checkout and selected source tree.
This is raw quarantine packaging, not a C09 snapshot or scientific approval.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[4]
HISTORICAL_ROOT = Path('/Users/jaronchai/Desktop/source_chat_agt')
MANIFEST_RELATIVE = Path('data/provenance/raw_source_manifest_latest.json')
PROJECT = 'ocean-v1-beta-20261101'
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SOURCE_FILES = 2000
MAX_PAYLOAD_BYTES = 128 * 1024 * 1024
MAX_TRANSFER_BYTES = 4 * 1024 * 1024
CHUNK = 1024 * 1024
AMENDMENT_RELATIVE = Path('deploy/gcp/beta/data/scope-amendment.json')
AMENDMENT_SHA256 = '73e49c36a7fa53d7cdb831970c57345a52250f8fffa582d62f6c8a7ebf2db1b3'
AMENDMENT_BYTES = 6991


class QuarantineError(ValueError):
    """Fixed diagnostics and approved relative source paths only."""


@dataclass(frozen=True)
class ExpectedCohort:
    manifest_sha256: str
    manifest_bytes: int
    files: int
    payload_bytes: int
    historical_root: Path


EXPECTED = ExpectedCohort(
    '9ac5170ff1030a9ffb153754865d5fd9bcd0acce81542456dae543e831b86a65',
    875939, 1860, 89159370, HISTORICAL_ROOT,
)


@dataclass(frozen=True)
class Source:
    relative: str
    source_dataset: str
    size: int
    sha256: str

    @property
    def member(self):
        return 'payload/' + self.relative


def require(condition, message):
    if not condition:
        raise QuarantineError(message)


def signature(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
        value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def clean_absolute(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts,
        'Explicit absolute paths without traversal are required')
    return path


def safe_ancestors(path):
    """Reject symlinks, including ancestors, before using a trusted local root."""
    for item in reversed((path, *path.parents)):
        info = item.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            'Regular nonsymlink source and output directories are required')


@contextmanager
def source_file(root, relative):
    """Open every relative directory and the file with O_NOFOLLOW.

    The descriptor, parent directory entry and path are checked before/after use.
    Owner-controlled ancestor replacement is outside the trusted local-root model.
    """
    parts = PurePosixPath(relative).parts
    require(parts and not PurePosixPath(relative).is_absolute()
        and all(p not in {'', '.', '..'} and not p.startswith('.') for p in parts),
        'Invalid relative raw-source path')
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    stream = None
    try:
        for part in parts[:-1]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent)
            os.close(parent)
            parent = following
        # A replaced FIFO must fail the regular-file check without blocking open.
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        stream = os.fdopen(fd, 'rb')
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode), 'Raw-source member must be a regular file')
        require(signature(before) == signature(os.stat(parts[-1], dir_fd=parent,
            follow_symlinks=False)), 'Raw-source path changed before reading')
        yield stream, signature(before)
        require(signature(before) == signature(os.fstat(stream.fileno()))
            == signature(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False))
            == signature((root / relative).lstat()), 'Raw-source changed while reading')
    except OSError:
        raise QuarantineError('Raw-source missing, replaced or not safely readable: ' + relative) from None
    finally:
        if stream is not None:
            stream.close()
        os.close(parent)


def unique(items):
    value = {}
    for key, item in items:
        require(key not in value, 'Duplicate source-manifest JSON key')
        value[key] = item
    return value


def finite_constant(_value):
    raise QuarantineError('Nonfinite source-manifest JSON value')


def raw_relative(relative):
    path = PurePosixPath(relative)
    return (isinstance(relative, str) and str(path) == relative and not path.is_absolute()
        and all(not p.startswith('.') and p not in {'.', '..'} for p in path.parts)
        and (relative.startswith('data/raw/ctd/') or relative.startswith('data/raw/meta/')
            or relative.startswith('onagawa_sst_subset/')))


def committed_amendment():
    path = ROOT / AMENDMENT_RELATIVE
    with source_file(ROOT, AMENDMENT_RELATIVE.as_posix()) as (stream, pinned):
        require(pinned[4] == AMENDMENT_BYTES, 'Pinned path-amendment length mismatch')
        data = stream.read(MAX_TRANSFER_BYTES + 1)
    require(hashlib.sha256(data).hexdigest() == AMENDMENT_SHA256,
        'Pinned path-amendment identity mismatch')
    result = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--verify', 'HEAD^{commit}'],
        capture_output=True, check=False, timeout=10)
    require(result.returncode == 0, 'Committed path-amendment source is required')
    revision = result.stdout.decode().strip()
    require(re.fullmatch(r'[a-f0-9]{40}', revision), 'Committed amendment revision is invalid')
    result = subprocess.run(['git', '-C', str(ROOT), 'show',
        revision + ':' + AMENDMENT_RELATIVE.as_posix()], capture_output=True, check=False, timeout=10)
    require(result.returncode == 0 and result.stdout == data and path.read_bytes() == data,
        'Exact path-amendment bytes must be committed before preparation')
    return data, revision


def reconcile_aliases(entries, expected, amendment):
    groups = {}
    for index, item in enumerate(entries):
        groups.setdefault(item.relative, []).append((index, item))
    duplicates = {path:values for path, values in groups.items() if len(values) > 1}
    if amendment is None:
        require(not duplicates, 'Duplicate raw-source path requires the explicit pinned alias amendment')
        return entries
    try:
        document = json.loads(amendment.decode('utf-8'), object_pairs_hook=unique,
            parse_constant=finite_constant)
        require(document.get('version') == 'ocean-beta-raw-path-alias-amendment-v1'
            and document.get('source_manifest_sha256') == expected.manifest_sha256
            and document.get('scientific_approval') is False
            and document.get('publication_or_c09_seal') is False
            and type(document.get('aliases')) is list,
            'Explicit raw-path amendment identity or scope mismatch')
        sources = [values[0][1] for values in groups.values()]
        alias_names, corrected = set(), {}
        for row in document['aliases']:
            alias, reference = row['alias_path'], row['original_referenced_path']
            require(raw_relative(alias) and alias not in groups and alias not in alias_names
                and reference in duplicates, 'Path amendment contains an unknown or duplicate alias')
            values = groups[reference]
            first = values[0][1]
            require(row['original_manifest_entry_indices'] == [i for i, _ in values]
                and all(item == first for _, item in values)
                and row['bytes'] == first.size and row['sha256'] == first.sha256
                and row['source_dataset'] == first.source_dataset,
                'Path amendment does not match the exact repeated original byte pins')
            alias_names.add(alias)
            corrected[reference] = corrected.get(reference, 0) + 1
            sources.append(Source(alias, first.source_dataset, first.size, first.sha256))
        require(corrected == {path:len(values) - 1 for path, values in duplicates.items()}
            and document.get('original_entry_count') == len(entries)
            and document.get('original_unique_paths') == len(groups)
            and document.get('alias_paths') == len(alias_names)
            and document.get('result_unique_paths') == len(sources) == expected.files
            and document.get('result_payload_bytes') == sum(item.size for item in sources) == expected.payload_bytes,
            'Path amendment does not reconcile the complete original cohort')
        return sources
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError) as error:
        if isinstance(error, QuarantineError):
            raise
        raise QuarantineError('Invalid explicit path-amendment manifest') from None


def raw_inventory(root):
    paths = set()
    def inventory_error(_error):
        raise QuarantineError('Complete raw inventory could not be read')
    for base in ['data/raw', 'onagawa_sst_subset']:
        safe_ancestors(root / base)
        for directory, dirs, files in os.walk(root / base, followlinks=False, onerror=inventory_error):
            require(not any((Path(directory) / name).is_symlink() for name in [*dirs, *files]),
                'Raw inventory contains a symlink')
            for name in files:
                if name == '.DS_Store':
                    continue
                relative = (Path(directory) / name).relative_to(root).as_posix()
                require(raw_relative(relative), 'Raw inventory contains an unapproved member path')
                paths.add(relative)
                require(len(paths) <= MAX_SOURCE_FILES, 'Raw inventory exceeds finite file bound')
    return paths


def read_manifest(path, *, checkout_root, source_root, expected, amendment=None):
    require(path in {checkout_root / MANIFEST_RELATIVE, source_root / MANIFEST_RELATIVE},
        'Only the explicit pinned raw-source manifest may be read')
    manifest_root = checkout_root if path == checkout_root / MANIFEST_RELATIVE else source_root
    with source_file(manifest_root, MANIFEST_RELATIVE.as_posix()) as (stream, pinned):
        require(pinned[4] == expected.manifest_bytes <= MAX_MANIFEST_BYTES,
            'Pinned source-manifest length mismatch')
        data = stream.read(MAX_MANIFEST_BYTES + 1)
    require(len(data) == expected.manifest_bytes
        and hashlib.sha256(data).hexdigest() == expected.manifest_sha256,
        'Pinned source-manifest identity mismatch')
    try:
        document = json.loads(data.decode('utf-8'), object_pairs_hook=unique,
            parse_constant=finite_constant)
        require(type(document) is dict and type(document.get('schema_version')) is int
            and document['schema_version'] == 1 and type(document.get('source_count')) is int
            and document['source_count'] == expected.files
            and type(document.get('sources')) is list
            and len(document['sources']) == expected.files <= MAX_SOURCE_FILES,
            'Pinned source-manifest cohort count mismatch')
        sources = []
        for row in document['sources']:
            require(type(row) is dict, 'Invalid raw-source manifest entry')
            raw = row.get('source_file')
            require(isinstance(raw, str) and len(raw) <= 1024 and '\x00' not in raw,
                'Invalid original raw-source path')
            path = clean_absolute(raw)
            require(str(path) == raw, 'Raw-source paths must be canonical')
            relative = path.relative_to(expected.historical_root).as_posix()
            require(raw_relative(relative),
                'Manifest member is outside the approved existing raw cohort')
            group, size, digest = row.get('source_dataset'), row.get('file_size_bytes'), row.get('sha256')
            require(isinstance(group, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', group)
                and type(size) is int and 0 < size <= MAX_PAYLOAD_BYTES
                and isinstance(digest, str) and re.fullmatch(r'[a-f0-9]{64}', digest),
                'Invalid raw-source group, size or checksum')
            sources.append(Source(relative, group, size, digest))
        require(sum(item.size for item in sources) == expected.payload_bytes <= MAX_PAYLOAD_BYTES,
            'Pinned raw-source total length mismatch')
        sources = reconcile_aliases(sources, expected, amendment)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
        if isinstance(error, QuarantineError):
            raise
        raise QuarantineError('Invalid pinned raw-source manifest') from None
    return data, tuple(sorted(sources, key=lambda item: item.member)), pinned


def scan_sources(root, sources):
    pinned = {}
    for item in sources:
        with source_file(root, item.relative) as (stream, before):
            require(before[4] == item.size, 'Raw-source length mismatch: ' + item.relative)
            digest = hashlib.sha256()
            remaining = item.size + 1
            while remaining:
                block = stream.read(min(CHUNK, remaining))
                if not block:
                    break
                digest.update(block)
                remaining -= len(block)
            require(remaining == 1, 'Raw-source length changed: ' + item.relative)
            require(digest.hexdigest() == item.sha256, 'Raw-source checksum mismatch: ' + item.relative)
            pinned[item.relative] = before
    return pinned


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def transfer_manifest(root, sources, expected, amendment=None):
    entries = [{'path':item.relative, 'archive_member':item.member,
        'source_dataset':item.source_dataset, 'bytes':item.size, 'sha256':item.sha256}
        for item in sources]
    result = {
        'version':'ocean-beta-existing-raw-quarantine-v1', 'project_id':PROJECT,
        'purpose':'raw quarantine only; normalization and current eligibility remain pending',
        'authorization_reference':'Current chat: user selected all eligible existing project datasets for the initial beta import',
        'scope':'Complete available raw cohort in the exact pinned historical manifest; no source acquisition',
        'source_manifest':{'sha256':expected.manifest_sha256, 'bytes':expected.manifest_bytes,
            'file':'source-manifest.json', 'schema_version':1},
        'source_path_mapping':{'original_manifest_root':str(expected.historical_root),
            'selected_source_root':str(root), 'method':'explicit whole-tree prefix mapping; no per-file fallback'},
        'file_count':len(sources), 'payload_bytes':sum(item.size for item in sources),
        'cohort_sha256':hashlib.sha256(canonical(entries)).hexdigest(),
        'files':entries, 'scientific_approval':False, 'normalized':False,
        'c09_snapshot_sealed':False, 'catalogue_registered':False, 'published_or_promoted':False,
        'unresolved_sources':['Later cloud ANEMONE/eDNA cohort: not inventoried or included',
            'Later cloud historical-SST cohort: not inventoried or included'],
        'excluded':['Database backups, accounts, conversations and history',
            'Credentials and keys', 'Generated analysis/reliability/serving/evaluation outputs',
            'Operational pipeline manifests/logs and filesystem metadata'],
    }
    if amendment is not None:
        document = json.loads(amendment)
        result['path_alias_amendment'] = {'file':'scope-amendment.json', 'bytes':len(amendment),
            'sha256':hashlib.sha256(amendment).hexdigest(), 'alias_paths':document['alias_paths'],
            'original_manifest_entries':document['original_entry_count'],
            'original_unique_paths':document['original_unique_paths'],
            'method':'deduplicate original paths and add only exact reviewed byte-identical aliases'}
    return result


class HashingReader:
    def __init__(self, stream):
        self.stream, self.digest, self.count = stream, hashlib.sha256(), 0

    def read(self, size):
        block = self.stream.read(size)
        self.digest.update(block)
        self.count += len(block)
        return block


def info(name, size):
    value = tarfile.TarInfo(name)
    value.size, value.mode = size, 0o444
    value.uid = value.gid = value.mtime = 0
    value.uname = value.gname = ''
    return value


def verify_archive(path, sources, metadata):
    expected = {item.member:(item.size, item.sha256) for item in sources}
    expected.update({name:(len(data), hashlib.sha256(data).hexdigest())
        for name, data in metadata.items()})
    seen = []
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and not path.is_symlink(), 'Regular archive required')
    with tarfile.open(path, 'r:') as archive:
        for member in archive:
            require(member.name in expected and member.name not in seen and member.isfile()
                and member.uid == member.gid == member.mtime == 0 and member.mode == 0o444
                and member.uname == member.gname == '' and not member.linkname
                and not member.pax_headers, 'Archive member inventory or normalized metadata mismatch')
            seen.append(member.name)
            size, digest = expected[member.name]
            require(member.size == size, 'Archive member size mismatch')
            stream = archive.extractfile(member)
            require(stream is not None, 'Archive member bytes unavailable')
            actual, count = hashlib.sha256(), 0
            with stream:
                for block in iter(lambda: stream.read(CHUNK), b''):
                    actual.update(block)
                    count += len(block)
            require(count == size and actual.hexdigest() == digest, 'Archive member checksum mismatch')
    require(seen == sorted(expected), 'Archive complete sorted member inventory mismatch')
    require(signature(before) == signature(path.lstat()), 'Archive changed during verification')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    require(signature(before) == signature(path.lstat()), 'Archive changed during final hashing')
    return {'members':len(seen), 'payload_files':len(sources), 'bytes':before.st_size, 'sha256':digest}


def private_bytes(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def prepare(*, source_manifest, source_root, output, applying=False,
            expected=EXPECTED, checkout_root=ROOT, _test_amendment=None):
    """Expected/root injection is for isolated tests; CLI pins the actual cohort."""
    checkout_root, source_root = clean_absolute(checkout_root), clean_absolute(source_root)
    source_manifest, output = clean_absolute(source_manifest), clean_absolute(output)
    require(source_root in {checkout_root, expected.historical_root},
        'Select exactly the current checkout or reviewed historical source tree')
    safe_ancestors(checkout_root)
    safe_ancestors(source_root)
    require(not output.is_relative_to(checkout_root) and not output.is_relative_to(source_root)
        and not output.is_relative_to(expected.historical_root),
        'Output must be outside the checkout and both reviewed source trees')
    require(not output.exists() and not output.is_symlink(), 'Output directory must not already exist')
    safe_ancestors(output.parent)
    require(_test_amendment is None or expected is not EXPECTED,
        'The actual cohort accepts only its committed pinned path amendment')
    amendment, amendment_revision = (committed_amendment() if expected is EXPECTED
        else (_test_amendment, None))
    data, sources, manifest_stat = read_manifest(source_manifest, checkout_root=checkout_root,
        source_root=source_root, expected=expected, amendment=amendment)
    require(raw_inventory(source_root) == {item.relative for item in sources},
        'Actual raw-file inventory differs from the exact reconciled cohort')
    pinned = scan_sources(source_root, sources)
    transfer = canonical(transfer_manifest(source_root, sources, expected, amendment))
    require(len(transfer) <= MAX_TRANSFER_BYTES, 'Transfer manifest exceeds finite metadata bound')
    result = {'version':'ocean-beta-existing-raw-preparation-v1', 'project_id':PROJECT,
        'state':'verified_plan_only', 'files':len(sources), 'payload_bytes':expected.payload_bytes,
        'source_manifest_sha256':expected.manifest_sha256,
        'transfer_manifest_sha256':hashlib.sha256(transfer).hexdigest(),
        'scientific_approval':False, 'c09_snapshot_sealed':False,
        'published_or_promoted':False, 'cloud_calls':False, 'output_created':False}
    if amendment is not None:
        result['path_amendment_sha256'] = hashlib.sha256(amendment).hexdigest()
        result['path_amendment_revision'] = amendment_revision
    if not applying:
        return result
    output.mkdir(mode=0o700)
    metadata = {'source-manifest.json':data, 'transfer-manifest.json':transfer}
    if amendment is not None:
        metadata['scope-amendment.json'] = amendment
    source_by_member = {item.member:item for item in sources}
    partial = output / 'raw-quarantine.tar.partial'
    fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        with tarfile.open(fileobj=handle, mode='w:', format=tarfile.USTAR_FORMAT) as archive:
            for name in sorted((*source_by_member, *metadata)):
                if name in metadata:
                    value = metadata[name]
                    archive.addfile(info(name, len(value)), io.BytesIO(value))
                    continue
                item = source_by_member[name]
                with source_file(source_root, item.relative) as (stream, before):
                    require(before == pinned[item.relative], 'Raw-source changed after preflight: ' + item.relative)
                    reader = HashingReader(stream)
                    archive.addfile(info(name, item.size), reader)
                    require(reader.count == item.size and reader.digest.hexdigest() == item.sha256,
                        'Raw-source changed during archive copy: ' + item.relative)
        handle.flush()
        os.fsync(handle.fileno())
    for item in sources:
        with source_file(source_root, item.relative) as (_stream, current):
            require(current == pinned[item.relative], 'Raw-source changed before completion: ' + item.relative)
    manifest_root = checkout_root if source_manifest == checkout_root / MANIFEST_RELATIVE else source_root
    with source_file(manifest_root, MANIFEST_RELATIVE.as_posix()) as (stream, current):
        require(current == manifest_stat and hashlib.sha256(stream.read(MAX_MANIFEST_BYTES + 1)).hexdigest()
            == expected.manifest_sha256, 'Source manifest changed during preparation')
    verification = verify_archive(partial, sources, metadata)
    for name, value in metadata.items():
        private_bytes(output / name, value)
    # Failed attempts retain only the .partial name; never report an accepted archive.
    final = output / 'raw-quarantine.tar'
    require(not final.exists() and not final.is_symlink(), 'Accepted archive path unexpectedly exists')
    partial.rename(final)
    result.update({'state':'raw_quarantine_prepared_and_verified', 'output_created':True,
        'archive':str(final), 'archive_verification':verification})
    private_bytes(output / 'preparation-receipt.json', canonical(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--source-manifest', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    try:
        result = prepare(source_manifest=args.source_manifest, source_root=args.source_root,
            output=args.output, applying=args.prepare)
    except (QuarantineError, OSError, tarfile.TarError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, QuarantineError) else 'Local preparation failed; inspect partial output before retry'
        print(json.dumps({'state':'refused', 'error':message, 'cloud_calls':False,
            'scientific_approval':False, 'published_or_promoted':False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
