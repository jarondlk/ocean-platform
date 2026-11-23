"""Immutable transport for validated C23 output bytes, scoped to one execution."""

from dataclasses import dataclass
import json
import re

from ingestion.provenance_snapshot import SnapshotConflict, SnapshotError, SnapshotNotFound
from orchestration.experiment_sandbox.contracts import ExecutionMetadata, SandboxError
from orchestration.experiment_sandbox.execution_store import ExecutionReservationBinding
from orchestration.experiment_sandbox.files import (
    MAX_LOG_BYTES, VERSION, ValidatedOutputs, _canonical, _hash, validate_expected_outputs,
)
from schema.research_experiments import MAX_OUTPUT_BYTES


MAX_MANIFEST_BYTES = 64 * 1024
_HASH = re.compile(r'[a-f0-9]{64}')
_MEDIA = {'json-table-v1': 'application/json', 'csv-table-v1': 'text/csv', 'png-rgb8-v1': 'image/png'}


@dataclass(frozen=True)
class RetainedOutputFile:
    id: str
    name: str
    kind: str
    media_type: str
    sha256: str
    size_bytes: int


def _prefix(binding, manifest_sha256):
    if (type(binding) is not ExecutionReservationBinding
            or type(manifest_sha256) is not str or not _HASH.fullmatch(manifest_sha256)):
        raise SandboxError('sandbox_output_store_integrity')
    identity = binding.model_dump(include={'site_id', 'owner_user_id', 'execution_id',
                                            'reservation_id', 'envelope_sha256'})
    return f'c23/outputs-v1/{_hash(_canonical(identity))}/{manifest_sha256}'


def _manifest_files(raw, *, prefix, manifest_sha256, expected_outputs, max_bytes):
    try:
        expected = validate_expected_outputs(expected_outputs)
        if (type(max_bytes) is not int or not 1 <= max_bytes <= MAX_OUTPUT_BYTES
                or type(raw) is not bytes or not 0 < len(raw) <= min(max_bytes, MAX_MANIFEST_BYTES)
                or _hash(raw) != manifest_sha256):
            raise ValueError
        manifest = json.loads(raw)
        if (type(manifest) is not dict or _canonical(manifest) != raw
                or set(manifest) != {'version', 'authority', 'scientific_approval', 'files', 'logs'}
                or manifest['version'] != VERSION or manifest['authority'] != 'experimental'
                or manifest['scientific_approval'] != 'not_independently_verified'
                or type(manifest['files']) is not list or len(manifest['files']) != len(expected)
                or type(manifest['logs']) is not list or len(manifest['logs']) > 2):
            raise ValueError
        files, total = [], len(raw)
        for (name, profile), item in zip(expected.items(), manifest['files'], strict=True):
            if (type(item) is not dict
                    or set(item) != {'name', 'size_bytes', 'sha256', 'kind', 'format', 'validation'}
                    or item['name'] != name or item['kind'] != profile['kind'] or item['format'] != profile['format']
                    or type(item['validation']) is not dict or type(item['sha256']) is not str
                    or not _HASH.fullmatch(item['sha256']) or type(item['size_bytes']) is not int
                    or not 1 <= item['size_bytes'] <= max_bytes):
                raise ValueError
            files.append(RetainedOutputFile(f'output-{_hash(f"{prefix}/{name}".encode())}',
                name, item['kind'], _MEDIA[item['format']], item['sha256'], item['size_bytes']))
            total += item['size_bytes']
        log_names = set()
        for item in manifest['logs']:
            if (type(item) is not dict or set(item) != {'name', 'sha256', 'size_bytes', 'capture_completeness'}
                    or item['name'] not in ('stdout', 'stderr') or item['name'] in log_names
                    or type(item['sha256']) is not str or not _HASH.fullmatch(item['sha256'])
                    or type(item['size_bytes']) is not int or not 0 <= item['size_bytes'] <= MAX_LOG_BYTES
                    or item['capture_completeness'] != 'not_asserted'):
                raise ValueError
            log_names.add(item['name'])
            total += item['size_bytes']
        if total > max_bytes:
            raise ValueError
        return tuple(files)
    except (TypeError, ValueError, RecursionError):
        raise SandboxError('sandbox_output_store_integrity') from None


def _read_bytes(store, key, max_bytes):
    try:
        return store.read(key, max_bytes=max_bytes).data
    except SnapshotNotFound:
        raise
    except (OSError, SnapshotError):
        raise SandboxError('sandbox_output_store_unavailable') from None
    except (TypeError, ValueError):
        raise SandboxError('sandbox_output_store_integrity') from None


class RetainedOutputReader:
    """Bounded reads through an explicitly supplied private transport."""

    def __init__(self, store):
        if not callable(getattr(store, 'read', None)):
            raise ValueError('An explicit bounded output transport is required')
        self._store = store

    def describe(self, binding, manifest_sha256, *, expected_outputs, max_bytes):
        prefix = _prefix(binding, manifest_sha256)
        try:
            raw = _read_bytes(self._store, prefix + '/manifest.json', min(max_bytes, MAX_MANIFEST_BYTES))
        except SnapshotNotFound:
            return ()
        return _manifest_files(raw, prefix=prefix, manifest_sha256=manifest_sha256,
                               expected_outputs=expected_outputs, max_bytes=max_bytes)

    def read_file(self, binding, manifest_sha256, file):
        if (type(file) is not RetainedOutputFile or type(file.sha256) is not str or not _HASH.fullmatch(file.sha256)
                or type(file.size_bytes) is not int or not 1 <= file.size_bytes <= MAX_OUTPUT_BYTES):
            raise SandboxError('sandbox_output_store_integrity')
        prefix = _prefix(binding, manifest_sha256)
        try:
            data = _read_bytes(self._store, f'{prefix}/files/{file.sha256}', file.size_bytes)
        except SnapshotNotFound:
            raise SandboxError('sandbox_output_store_unavailable') from None
        if (type(data) is not bytes or len(data) != file.size_bytes or _hash(data) != file.sha256):
            raise SandboxError('sandbox_output_store_integrity')
        return data


class RetainedOutputWriter:
    """Stage create-only files and publish the exact manifest last."""

    def __init__(self, store):
        if not callable(getattr(store, 'read', None)) or not callable(getattr(store, 'create', None)):
            raise ValueError('An explicit bounded, create-only output transport is required')
        self._store = store

    def _put(self, key, raw):
        try:
            self._store.create(key, raw)
        except SnapshotConflict:
            pass
        except (OSError, SnapshotError):
            raise SandboxError('sandbox_output_store_unavailable') from None
        try:
            observed = _read_bytes(self._store, key, len(raw))
        except SnapshotNotFound:
            raise SandboxError('sandbox_output_store_unavailable') from None
        if observed != raw:
            raise SandboxError('sandbox_output_store_integrity')

    def publish(self, binding, outputs, manifest_sha256):
        prefix = _prefix(binding, manifest_sha256)
        if type(outputs) is not ValidatedOutputs:
            raise SandboxError('sandbox_output_store_integrity')
        metadata = ExecutionMetadata.model_validate_json(binding.envelope_json)
        files = _manifest_files(outputs.manifest_bytes, prefix=prefix, manifest_sha256=manifest_sha256,
                                expected_outputs=[item.model_dump(mode='json') for item in metadata.proposal.expected_outputs],
                                max_bytes=metadata.proposal.resources.max_output_bytes)
        for item in files:
            raw = outputs.files.get(item.name)
            if type(raw) is not bytes or len(raw) != item.size_bytes or _hash(raw) != item.sha256:
                raise SandboxError('sandbox_output_store_integrity')
            self._put(f'{prefix}/files/{item.sha256}', raw)
        self._put(prefix + '/manifest.json', outputs.manifest_bytes)
