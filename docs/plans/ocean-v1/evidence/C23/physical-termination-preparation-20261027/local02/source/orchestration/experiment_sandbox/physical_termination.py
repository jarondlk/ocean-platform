"""Explicit held-lease Linux observations and retained termination issuance.

This module is not registered with the synthetic adapter or serving application.
It accepts no caller-created claims as physical evidence. Host-safe tests of
these checks are software evidence; actual Linux acceptance remains separate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import threading
import time
from types import MappingProxyType
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text

from orchestration.experiment_sandbox.contracts import SandboxError, VerifiedEnvelope
from orchestration.experiment_sandbox.execution_store import C23ExecutionStore
from orchestration.experiment_sandbox.journal import DurableExecutionJournal, DurableLease
from orchestration.experiment_sandbox import linux_runtime as native
from orchestration.experiment_sandbox.profile_execution import PreparedExecutionProfile
from orchestration.experiment_sandbox.proofs import (
    TerminationVerifierRegistry, canonical_packet_bytes, retain_termination_packet,
    sign_termination_claims, verify_termination_packet,
)
from schema.experiment_execution import (
    ClosedExecutionBinding, TerminationClaims, TerminationIssuerScope,
    TERMINATION_PACKET_VERSION,
)

OBSERVATION_VERSION = 'c23-native-termination-observation-v1'
START_INTENT_VERSION = 'c23-retained-start-intent-v1'
WORKER_POLICY_VERSION = 'c23-worker-source-policy-v1'
PROFILE_POLICY_VERSION = 'c23-profile-source-policy-v1'
SOURCE_POLICY_VERSION = 'c23-physical-termination-source-policy-v1'
MAX_NATIVE_BYTES = 16 * 1024
MAX_SOURCE_BYTES = 32 * 1024**2
MAX_SOURCE_FILE_BYTES = 2 * 1024**2
MAX_SOURCE_FILES = 512
WORKER_FILES = frozenset({
    'orchestration/experiment_sandbox/' + name + '.py' for name in (
        'physical_termination', 'linux_runtime', 'journal', 'profile',
        'profile_execution', 'proofs', 'execution_store', 'operator_inspection',
        'retained_runner', 'retained_bridge', 'retained_context')
} | {'schema/experiment_execution.py', 'sandbox/experiment/trusted_init.py'})
PROFILE_FILES = frozenset({'orchestration/experiment_sandbox/profile.py',
    'orchestration/experiment_sandbox/profile_execution.py', 'sandbox/experiment/trusted_init.py'})
_HASH = re.compile(r'^[a-f0-9]{64}$')
_TOKEN = object()
_LIVE_LOCK = threading.RLock()
_LIVE_HANDLES = {}


def _after_fork():
    global _LIVE_LOCK
    _LIVE_LOCK = threading.RLock()
    _LIVE_HANDLES.clear()


os.register_at_fork(after_in_child=_after_fork)


def _error(reason='sandbox_physical_termination_identity'):
    raise SandboxError(reason)


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      sort_keys=True, separators=(',', ':')).encode('ascii')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _now():
    value = time.monotonic_ns()
    if type(value) is not int or not 0 <= value < 2**63:
        _error('sandbox_physical_clock')
    return value


def _file_id(info):
    return info.st_dev, info.st_ino


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _lease(adapter, envelope, profile, lease):
    if (type(adapter) is not native.LinuxExecutionAdapter
            or type(envelope) is not VerifiedEnvelope
            or type(profile) is not PreparedExecutionProfile
            or type(adapter.journal) is not DurableExecutionJournal
            or type(lease) is not DurableLease):
        _error()
    if any(name in adapter.__dict__ for name in ('_preflight', '_paths', '_spawn', '_wait', '_command', '_cleanup')):
        _error('sandbox_physical_adapter_changed')
    snapshot = adapter.journal.require_current(lease)
    if (snapshot.job_id != envelope.job_id or snapshot.envelope_sha256 != envelope.envelope_sha256
            or profile.document['job_id'] != envelope.job_id
            or profile.document['envelope_sha256'] != envelope.envelope_sha256):
        _error()
    return snapshot


def _host_guard(adapter, envelope, profile, lease):
    _lease(adapter, envelope, profile, lease)
    native._require_linux_host(adapter.journal, adapter.cgroup_root)
    machine = native._read('/etc/machine-id', 128).decode('ascii').strip()
    if (not re.fullmatch(r'[a-f0-9]{32}', machine)
            or _sha(('c23-linux-machine-id:' + machine).encode()) != adapter.journal.host_id):
        _error('sandbox_physical_worker_identity')
    reference = adapter.journal.identity_reference(lease)
    if (reference.host_id != adapter.journal.host_id
            or reference.configured_host_boot_id != reference.event_host_boot_id
            or any(event.host_boot_id != reference.configured_host_boot_id
                   for event in lease.require_current().events)):
        _error('sandbox_physical_boot_continuity')
    _lease(adapter, envelope, profile, lease)
    return reference


def _materials(adapter, envelope, profile, lease):
    _lease(adapter, envelope, profile, lease)
    result = adapter._preflight(envelope, profile)
    _lease(adapter, envelope, profile, lease)
    return result


class OriginalCgroupHandle:
    """Private live native handle; retain it through cleanup, finish and issuance."""
    __slots__ = ('_adapter', '_envelope', '_profile', '_lease', '_fd', '_identity',
                 '_path', '_pid', '_token', '_create', '_closed', '_observation', '_operation_lock')

    def __init__(self, *args, **kwargs):
        raise TypeError('Use open_original_cgroup under the actual held lease')

    def close(self):
        if type(self) is not OriginalCgroupHandle or self._pid != os.getpid():
            _error()
        with self._operation_lock:
            with _LIVE_LOCK:
                if self._closed:
                    return
                if _LIVE_HANDLES.get(id(self)) is not self:
                    _error()
                _LIVE_HANDLES.pop(id(self))
                self._closed = True
            try:
                if _file_id(os.fstat(self._fd)) == self._identity:
                    os.close(self._fd)
            except OSError:
                pass

    def __enter__(self):
        _handle(self, self._adapter, self._envelope, self._profile, self._lease)
        return self

    def __exit__(self, *_):
        self.close()


def _handle(handle, adapter, envelope, profile, lease):
    try:
        if (type(handle) is not OriginalCgroupHandle or handle._token is not _TOKEN
                or handle._pid != os.getpid() or handle._closed
                or handle._adapter is not adapter or handle._lease is not lease
                or handle._envelope is not envelope or handle._profile is not profile):
            _error()
        with _LIVE_LOCK:
            if _LIVE_HANDLES.get(id(handle)) is not handle:
                _error()
        _lease(adapter, envelope, profile, lease)
        named, opened = handle._path.lstat(), os.fstat(handle._fd)
        parent = handle._path.parent.lstat()
        if (handle._path != handle._path.resolve(strict=True)
                or handle._path.parent != handle._path.parent.resolve(strict=True)
                or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
                or parent.st_mode & 0o022
                or not stat.S_ISDIR(opened.st_mode) or not stat.S_ISDIR(named.st_mode)
                or named.st_uid != os.geteuid() or opened.st_uid != os.geteuid()
                or named.st_mode & 0o022 or opened.st_mode & 0o022
                or _file_id(opened) != handle._identity or _file_id(named) != handle._identity
                or native._read_at(handle._fd, 'cgroup.type', 128).strip() != b'domain'):
            _error('sandbox_physical_cgroup_identity')
        _lease(adapter, envelope, profile, lease)
    except SandboxError:
        raise
    except (OSError, ValueError, TypeError, AttributeError):
        _error('sandbox_physical_cgroup_identity')


def open_original_cgroup(adapter, envelope, profile, lease, identity):
    """Open only an original cgroup already pinned in the validated create intent."""
    descriptor = None
    try:
        _host_guard(adapter, envelope, profile, lease)
        _materials(adapter, envelope, profile, lease)
        if (type(identity) is not tuple or len(identity) != 2
                or any(type(item) is not int or not 0 <= item < 2**63 for item in identity)
                or identity[1] == 0):
            _error()
        snapshot = _lease(adapter, envelope, profile, lease)
        creates = [event for event in snapshot.events if event.kind == 'create_intent']
        if len(creates) != 1 or creates[0].payload != {
                'profile_sha256': profile.profile_sha256, 'cgroup_identity': list(identity)}:
            _error('sandbox_physical_create_intent')
        outer, _, _ = adapter._paths(envelope.job_id)
        descriptor = os.open(outer, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        value = object.__new__(OriginalCgroupHandle)
        for name, item in {'_adapter': adapter, '_envelope': envelope, '_profile': profile,
                '_lease': lease, '_fd': descriptor, '_identity': identity, '_path': outer,
                '_pid': os.getpid(), '_token': _TOKEN, '_create': creates[0],
                '_closed': False, '_observation': None, '_operation_lock': threading.Lock()}.items():
            setattr(value, name, item)
        with _LIVE_LOCK:
            if len(_LIVE_HANDLES) >= 128:
                _error('sandbox_physical_handle_limit')
            if any(item._lease is lease for item in _LIVE_HANDLES.values()):
                _error('sandbox_physical_handle_already_open')
            _LIVE_HANDLES[id(value)] = value
        try:
            _handle(value, adapter, envelope, profile, lease)
        except BaseException:
            with _LIVE_LOCK:
                _LIVE_HANDLES.pop(id(value), None)
            raise
        descriptor = None
        return value
    except SandboxError:
        raise
    except (OSError, ValueError, TypeError, AttributeError, UnicodeError):
        _error()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _kill(handle):
    _handle(handle, handle._adapter, handle._envelope, handle._profile, handle._lease)
    descriptor = os.open('cgroup.kill', os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=handle._fd)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode) or os.write(descriptor, b'1\n') != 2:
            _error('sandbox_physical_cgroup_identity')
    finally:
        os.close(descriptor)
    _handle(handle, handle._adapter, handle._envelope, handle._profile, handle._lease)


def _empty(handle, deadline):
    while True:
        _handle(handle, handle._adapter, handle._envelope, handle._profile, handle._lease)
        raw = native._read_at(handle._fd, 'cgroup.events', 4096)
        fields = {}
        try:
            for line in raw.decode('ascii').splitlines():
                key, value = line.split()
                if key in fields or key not in {'populated', 'frozen'} or value not in {'0', '1'}:
                    raise ValueError
                fields[key] = value
        except (ValueError, UnicodeError):
            _error('sandbox_physical_cgroup_events')
        _handle(handle, handle._adapter, handle._envelope, handle._profile, handle._lease)
        if fields.get('populated') == '0':
            return raw, _now()
        if fields.get('populated') != '1' or time.monotonic() >= deadline:
            _error('sandbox_physical_termination_uncertain')
        time.sleep(0.01)


def _run_delete(adapter, envelope, profile, lease, handle, sidecapture):
    """Only native boundary mocked by command tests; no caller command accepted."""
    _handle(handle, adapter, envelope, profile, lease)
    _, host, _ = adapter._paths(envelope.job_id)
    argv = [str(adapter.runtime_directory / 'runsc'), *profile.runtime_args,
            'delete', '--force', envelope.job_id]
    capture = adapter._spawn(argv, host, deadline=time.monotonic() + 2)
    try:
        if type(capture) is not native._Capture or type(capture.process) is not subprocess.Popen:
            _error('sandbox_physical_delete_identity')
        code = adapter._wait(capture, deadline=time.monotonic() + 2, lease=lease, side=sidecapture)
        if (type(code) is not int or code != 0 or capture.process.poll() != 0
                or capture.eof is not True or type(capture.process.pid) is not int):
            _error('sandbox_physical_delete_uncertain')
        acknowledged = _now()
        _handle(handle, adapter, envelope, profile, lease)
        stdout, stderr = bytes(capture.stdout), bytes(capture.stderr)
        command = {'argv': argv, 'runtime_sha256': _sha(adapter._runtime_json.encode()),
                   'runsc_sha256': json.loads(adapter._runtime_json)['files']['runsc']}
        receipt = {'command': command, 'command_sha256': _sha(_canonical(command)),
            'exit_code': code, 'pid': capture.process.pid, 'pipes_eof': True,
            'stdout_size_bytes': len(stdout), 'stdout_sha256': _sha(stdout),
            'stderr_size_bytes': len(stderr), 'stderr_sha256': _sha(stderr),
            'acknowledged_monotonic_ns': acknowledged}
        return receipt
    finally:
        capture.close()


def _validate_delete(receipt, adapter, envelope, profile):
    expected = {'argv': [str(adapter.runtime_directory / 'runsc'), *profile.runtime_args,
                         'delete', '--force', envelope.job_id],
        'runtime_sha256': _sha(adapter._runtime_json.encode()),
        'runsc_sha256': json.loads(adapter._runtime_json)['files']['runsc']}
    if (type(receipt) is not dict or receipt.get('command') != expected
            or receipt.get('command_sha256') != _sha(_canonical(expected))
            or type(receipt.get('exit_code')) is not int or receipt['exit_code'] != 0
            or type(receipt.get('pid')) is not int or not 1 < receipt['pid'] < 2**31
            or receipt.get('pipes_eof') is not True
            or type(receipt.get('acknowledged_monotonic_ns')) is not int
            or not 0 <= receipt['acknowledged_monotonic_ns'] < 2**63):
        _error('sandbox_physical_delete_uncertain')
    for stream, limit in (('stdout', native.MAX_COMMAND_BYTES), ('stderr', native.MAX_RUNTIME_STDERR)):
        size, digest = receipt.get(stream + '_size_bytes'), receipt.get(stream + '_sha256')
        if (type(size) is not int or not 0 <= size <= limit
                or type(digest) is not str or not _HASH.fullmatch(digest)):
            _error('sandbox_physical_delete_uncertain')


def _private_directory(path, *, create=False):
    if create:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
    info = path.lstat()
    if (not path.is_absolute() or path != path.resolve(strict=True)
            or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        _error('sandbox_physical_evidence_path')
    return path


def _retained_bytes(directory, name, raw, lease, *, maximum=MAX_NATIVE_BYTES):
    """Private single-link regular file, create-only and byte-exact on retry."""
    lease.require_current()
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum:
        _error('sandbox_physical_evidence_limit')
    directory = _private_directory(Path(directory))
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if _file_id(os.fstat(parent)) != _file_id(directory.lstat()):
            _error('sandbox_physical_evidence_path')
        try:
            descriptor = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                | os.O_NONBLOCK | os.O_CLOEXEC, 0o600, dir_fd=parent)
            created = True
        except FileExistsError:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > maximum):
                _error('sandbox_physical_evidence_path')
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                                 dir_fd=parent)
            created = False
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or opened.st_uid != os.geteuid() or stat.S_IMODE(opened.st_mode) != 0o600):
                _error('sandbox_physical_evidence_path')
            if not created and _file_id(opened) != _file_id(info):
                _error('sandbox_physical_evidence_path')
            if created:
                pending = memoryview(raw)
                while pending:
                    count = os.write(descriptor, pending)
                    if count <= 0:
                        _error('sandbox_physical_evidence_path')
                    pending = pending[count:]
                os.fsync(descriptor)
            if os.pread(descriptor, maximum + 1, 0) != raw:
                _error('sandbox_physical_evidence_conflict')
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if _stamp(named) != _stamp(os.fstat(descriptor)) or named.st_nlink != 1:
                _error('sandbox_physical_evidence_path')
            if _file_id(directory.lstat()) != _file_id(os.fstat(parent)):
                _error('sandbox_physical_evidence_path')
            os.fsync(parent)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)
    lease.require_current()
    return directory / name


@dataclass(frozen=True, init=False, slots=True)
class HostTerminationObservation:
    """Private live native provenance; audit JSON is never accepted in its place."""
    _handle: OriginalCgroupHandle = field(repr=False)
    _native_bytes: bytes = field(repr=False)
    _native_path: Path = field(repr=False)
    _cleanup_event: object = field(repr=False)
    _termination_event: object = field(repr=False)
    _token: object = field(repr=False)
    native_observation_sha256: str
    cleanup_intent_sequence: int
    cleanup_intent_sha256: str
    termination_sequence: int
    termination_sha256: str

    def __init__(self, *args, **kwargs):
        raise TypeError('Use cleanup_under_lease with an original live cgroup handle')

    @property
    def audit_record(self):
        return {'native_observation': json.loads(self._native_bytes),
            'native_observation_sha256': self.native_observation_sha256,
            'termination_sequence': self.termination_sequence,
            'termination_sha256': self.termination_sha256,
            'reservation_release_authorized': False}


def cleanup_under_lease(adapter, envelope, profile, lease, handle, sidecapture=None):
    """Kill/observe the original cgroup and directly acknowledge pinned deletion."""
    _handle(handle, adapter, envelope, profile, lease)
    with handle._operation_lock:
        return _cleanup_under_lease(adapter, envelope, profile, lease, handle, sidecapture)


def _cleanup_under_lease(adapter, envelope, profile, lease, handle, sidecapture):
    try:
        reference = _host_guard(adapter, envelope, profile, lease)
        _materials(adapter, envelope, profile, lease)
        _handle(handle, adapter, envelope, profile, lease)
        if handle._observation is not None or lease.require_current().terminal:
            _error('sandbox_physical_cleanup_replay')
        if sidecapture is not None:
            if type(sidecapture) is not native._Capture:
                _error('sandbox_physical_delete_identity')
            sidecapture.cancel_launch()
        started = _now()
        cleanup = lease.append('cleanup_intent', {'version': OBSERVATION_VERSION,
            'profile_sha256': profile.profile_sha256, 'cgroup_path': '/ocean-c23/' + envelope.job_id,
            'cgroup_device': handle._identity[0], 'cgroup_inode': handle._identity[1],
            'create_intent_sha256': handle._create.sha256, 'cleanup_started_monotonic_ns': started})
        _kill(handle)
        _empty(handle, time.monotonic() + 2)
        try:
            deletion = _run_delete(adapter, envelope, profile, lease, handle, sidecapture)
            _validate_delete(deletion, adapter, envelope, profile)
        finally:
            _kill(handle)
            raw_events, empty_at = _empty(handle, time.monotonic() + 2)
        if sidecapture is not None:
            deadline = time.monotonic() + 1
            while not sidecapture.eof:
                lease.require_current()
                sidecapture.drain()
                if time.monotonic() >= deadline:
                    _error('sandbox_physical_pipe_uncertain')
                time.sleep(0.01)
        # These values originate in direct native operations above. They are
        # retained for audit, never accepted as a caller-provided observation.
        document = {'version': OBSERVATION_VERSION, 'job_id': envelope.job_id,
            'envelope_sha256': envelope.envelope_sha256, 'worker_id': reference.host_id,
            'host_boot_id': reference.configured_host_boot_id, 'journal_id': reference.journal_id,
            'journal_epoch': lease.epoch, 'profile_sha256': profile.profile_sha256,
            'runtime_sha256': _sha(adapter._runtime_json.encode()),
            'adapter_source_sha256': adapter._helper_sha256,
            'create_intent_sequence': handle._create.sequence,
            'create_intent_sha256': handle._create.sha256,
            'cleanup_intent_sequence': cleanup.sequence, 'cleanup_intent_sha256': cleanup.sha256,
            'cgroup_path': '/ocean-c23/' + envelope.job_id, 'cgroup_device': handle._identity[0],
            'cgroup_inode': handle._identity[1], 'populated': 0,
            'cgroup_events_sha256': _sha(raw_events), 'delete': deletion,
            'cleanup_started_monotonic_ns': started, 'populated_zero_monotonic_ns': empty_at}
        if not started <= deletion['acknowledged_monotonic_ns'] <= empty_at:
            _error('sandbox_physical_clock')
        raw = _canonical(document)
        directory = _private_directory(adapter.worker_root / envelope.job_id / 'physical-termination', create=True)
        path = _retained_bytes(directory, f'native-e{lease.epoch}-c{cleanup.sequence}.json', raw, lease)
        digest = _sha(raw)
        terminated = lease.append('termination_verified', {'version': OBSERVATION_VERSION,
            'native_observation_sha256': digest, 'cleanup_intent_sequence': cleanup.sequence,
            'cleanup_intent_sha256': cleanup.sha256, 'profile_sha256': profile.profile_sha256,
            'cgroup_identity': list(handle._identity)})
        value = object.__new__(HostTerminationObservation)
        for name, item in {'_handle': handle, '_native_bytes': raw, '_native_path': path,
                '_cleanup_event': cleanup, '_termination_event': terminated, '_token': _TOKEN,
                'native_observation_sha256': digest, 'cleanup_intent_sequence': cleanup.sequence,
                'cleanup_intent_sha256': cleanup.sha256, 'termination_sequence': terminated.sequence,
                'termination_sha256': terminated.sha256}.items():
            object.__setattr__(value, name, item)
        handle._observation = value
        _handle(handle, adapter, envelope, profile, lease)
        return value
    except SandboxError:
        raise
    except (OSError, ValueError, TypeError, AttributeError, KeyError, UnicodeError, subprocess.SubprocessError):
        _error('sandbox_physical_termination_uncertain')


def _manifest(value, *, required, version):
    if type(value) is not dict or not required <= set(value) or not 1 <= len(value) <= MAX_SOURCE_FILES:
        raise ValueError('Complete bounded trusted worker source manifest required')
    detached = {}
    for name, digest in value.items():
        path = PurePosixPath(name) if type(name) is str else None
        if (path is None or path.is_absolute() or str(path) != name
                or any(part in {'.', '..'} for part in path.parts)
                or not re.fullmatch(r'[A-Za-z0-9_./-]{1,192}', name)
                or type(digest) is not str or not _HASH.fullmatch(digest)):
            raise ValueError('Exact relative source files and SHA256 pins required')
        detached[name] = digest
    return MappingProxyType(detached), _sha(_canonical({'version': version, 'files': detached}))


@dataclass(frozen=True, init=False)
class PhysicalIssuerConfig:
    """Trusted operator configuration; never supplied by analysis or a request."""
    store: C23ExecutionStore = field(repr=False)
    registry: TerminationVerifierRegistry = field(repr=False)
    scope: TerminationIssuerScope
    issuer_id: str
    key_id: str
    source_root: Path
    evidence_root: Path
    enabled: bool
    _private_key: object = field(repr=False)
    _worker_files: object = field(repr=False)
    _profile_files: object = field(repr=False)
    _source_policy_bytes: bytes = field(repr=False)

    def __init__(self, *, store, registry, scope, issuer_id, key_id, private_key,
                 source_root, evidence_root, worker_source_files, profile_source_files,
                 source_policy_bytes, enabled=False):
        if (type(store) is not C23ExecutionStore or type(registry) is not TerminationVerifierRegistry
                or type(scope) is not TerminationIssuerScope or type(enabled) is not bool
                or not isinstance(private_key, Ed25519PrivateKey)):
            raise ValueError('Explicit exact store, independent registry, scope and operator key required')
        if store.config.verifier_registry.policy_sha256 != registry.policy_sha256:
            raise ValueError('Physical issuer and recorder must pin the same verifier policy')
        scope = TerminationIssuerScope.model_validate(scope.model_dump(mode='python'))
        worker, worker_hash = _manifest(worker_source_files, required=WORKER_FILES, version=WORKER_POLICY_VERSION)
        profile, profile_hash = _manifest(profile_source_files, required=PROFILE_FILES, version=PROFILE_POLICY_VERSION)
        if (set(profile) != PROFILE_FILES or any(worker.get(name) != digest for name, digest in profile.items())
                or worker_hash != scope.worker_source_sha256 or profile_hash != scope.profile_policy_sha256):
            raise ValueError('Worker/profile source policy identity mismatch')
        policy = {'version': SOURCE_POLICY_VERSION, 'trust_scope': registry.trust_scope,
            **{name: getattr(scope, name) for name in TerminationIssuerScope.model_fields
               if name not in {'site_id', 'source_policy_sha256'}}}
        if (type(source_policy_bytes) is not bytes or len(source_policy_bytes) > 4096
                or source_policy_bytes != _canonical(policy) or _sha(source_policy_bytes) != scope.source_policy_sha256
                or scope.site_id != store.config.site_id):
            raise ValueError('Exact canonical trusted source policy binding required')
        entry = registry._issuers.get((issuer_id, key_id))
        if (entry is None or entry.public_key != private_key.public_key().public_bytes_raw()
                or entry.scope != scope):
            raise ValueError('Signing key must match independently pinned issuer policy')
        source_root, evidence_root = Path(source_root), Path(evidence_root)
        if (not source_root.is_absolute() or not evidence_root.is_absolute()
                or source_root == evidence_root or source_root in evidence_root.parents
                or evidence_root in source_root.parents):
            raise ValueError('Independent explicit absolute source and issuer evidence roots required')
        for name, item in {'store': store, 'registry': registry, 'scope': scope,
                'issuer_id': issuer_id, 'key_id': key_id, 'source_root': source_root,
                'evidence_root': evidence_root, 'enabled': enabled, '_private_key': private_key,
                '_worker_files': worker, '_profile_files': profile,
                '_source_policy_bytes': bytes(source_policy_bytes)}.items():
            object.__setattr__(self, name, item)


def _source_files(config, adapter, envelope, profile, lease):
    _private_directory(config.source_root)
    total = 0
    for name, digest in config._worker_files.items():
        _lease(adapter, envelope, profile, lease)
        path = config.source_root / name
        if path != path.resolve(strict=True):
            _error('sandbox_physical_source_policy')
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_mode & 0o222 or before.st_nlink != 1
                or not 1 <= before.st_size <= MAX_SOURCE_FILE_BYTES):
            _error('sandbox_physical_source_policy')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            raw = os.read(descriptor, MAX_SOURCE_FILE_BYTES + 1)
            if (len(raw) != before.st_size or _sha(raw) != digest
                    or _stamp(before) != _stamp(os.fstat(descriptor)) or _stamp(before) != _stamp(path.lstat())):
                _error('sandbox_physical_source_policy')
        finally:
            os.close(descriptor)
        total += len(raw)
        if total > MAX_SOURCE_BYTES:
            _error('sandbox_physical_source_policy')
        _lease(adapter, envelope, profile, lease)
    if (config.source_root / 'orchestration/experiment_sandbox/physical_termination.py' != Path(__file__).resolve()
            or config.source_root / 'orchestration/experiment_sandbox/linux_runtime.py' != Path(native.__file__).resolve()
            or config._worker_files['orchestration/experiment_sandbox/linux_runtime.py'] != adapter._helper_sha256):
        _error('sandbox_physical_source_policy')


def _closed_rows(store, execution_id):
    """Only DB boundary mocked by host-safe tests; credentials stay in the store."""
    schema = store.config.schema
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
        _error('sandbox_physical_closed_binding')
    with store._recorder_transaction() as session:
        binding = ClosedExecutionBinding.model_validate(session.scalar(text(
            f'SELECT {schema}.ocean_c23_closed_binding(CAST(:id AS uuid))'), {'id': execution_id}))
        row = session.execute(text(f'''SELECT s.state,s.fence,s.start_event_id,s.current_event_id,
            c.terminal_sequence,c.terminal_head_sha256,c.result_sha256 AS terminal_result_sha256,
            t.id AS start_id,t.fence AS start_fence,t.host_boot_id AS start_boot_id,
            t.journal_id AS start_journal_id,t.journal_epoch AS start_journal_epoch,
            t.profile_sha256 AS start_profile_sha256,t.preceding_journal_sha256
            FROM {schema}.research_experiment_execution_state s
            JOIN {schema}.research_experiment_execution_event c ON c.id=s.current_event_id
            JOIN {schema}.research_experiment_execution_event t ON t.id=s.start_event_id
            WHERE s.execution_id=CAST(:id AS uuid) AND c.kind='closed' AND t.kind='start_consumed'
            AND c.execution_id=s.execution_id AND t.execution_id=s.execution_id'''),
            {'id': execution_id}).mappings().one()
        return binding, dict(row)


def _observation(observation, adapter, envelope, profile, lease):
    try:
        if (type(observation) is not HostTerminationObservation or observation._token is not _TOKEN
                or observation._handle._observation is not observation):
            _error('sandbox_physical_observation')
        _handle(observation._handle, adapter, envelope, profile, lease)
        if _sha(observation._native_bytes) != observation.native_observation_sha256:
            _error('sandbox_physical_observation')
        _retained_bytes(observation._native_path.parent, observation._native_path.name,
                        observation._native_bytes, lease)
        return json.loads(observation._native_bytes)
    except SandboxError:
        raise
    except (AttributeError, TypeError, ValueError, OSError):
        _error('sandbox_physical_observation')


def _journal_claims(adapter, envelope, profile, lease, observation, binding, row):
    snapshot = _lease(adapter, envelope, profile, lease)
    terminal = adapter.journal.terminal_reference(lease)
    if (terminal.journal_id != binding.journal_id or terminal.host_id != binding.worker_id
            or terminal.configured_host_boot_id != binding.host_boot_id
            or terminal.event_host_boot_id != binding.host_boot_id or terminal.epoch != binding.journal_epoch
            or terminal.terminal_sequence != row['terminal_sequence']
            or terminal.terminal_head_sha256 != row['terminal_head_sha256']
            or terminal.terminal_result_sha256 != row['terminal_result_sha256']):
        _error('sandbox_physical_terminal_binding')
    starts = [event for event in snapshot.events if event.kind == 'start_intent']
    creates = [event for event in snapshot.events if event.kind == 'create_intent']
    if len(starts) != 1 or len(creates) != 1 or creates[0] != observation._handle._create:
        _error('sandbox_physical_start_binding')
    start, create = starts[0], creates[0]
    expected = {'version': START_INTENT_VERSION, 'execution_id': binding.execution_id,
        'reservation_id': binding.reservation_id, 'start_id': str(row['start_id']),
        'start_event_id': str(row['start_event_id']), 'start_fence': row['start_fence'],
        'journal_id': str(row['start_journal_id']), 'journal_epoch': row['start_journal_epoch'],
        'worker_id': binding.worker_id, 'host_boot_id': str(row['start_boot_id']),
        'job_id': binding.job_id, 'envelope_sha256': binding.envelope_sha256,
        'profile_sha256': row['start_profile_sha256'],
        'preceding_journal_sha256': row['preceding_journal_sha256']}
    cleanup, termination = observation._cleanup_event, observation._termination_event
    if (row['state'] != 'closed' or row['fence'] != binding.closed_fence
            or str(row['start_event_id']) != str(row['start_id'])
            or str(row['start_journal_id']) != binding.journal_id
            or str(row['start_boot_id']) != binding.host_boot_id
            or row['start_profile_sha256'] != profile.profile_sha256
            or start.payload != expected or start.previous_sha256 != row['preceding_journal_sha256']
            or start.epoch != row['start_journal_epoch'] or start.epoch > lease.epoch
            or not create.sequence < start.sequence < cleanup.sequence < termination.sequence < terminal.terminal_sequence
            or cleanup.epoch != lease.epoch or termination.epoch != lease.epoch
            or snapshot.events[cleanup.sequence - 1] != cleanup
            or snapshot.events[termination.sequence - 1] != termination
            or termination.payload.get('native_observation_sha256') != observation.native_observation_sha256):
        _error('sandbox_physical_start_binding')
    return terminal, {'create_intent_sequence': create.sequence, 'create_intent_sha256': create.sha256,
        'cleanup_intent_sequence': cleanup.sequence, 'cleanup_intent_sha256': cleanup.sha256,
        'termination_sequence': termination.sequence, 'termination_sha256': termination.sha256,
        'terminal_sequence': terminal.terminal_sequence, 'terminal_head_sha256': terminal.terminal_head_sha256,
        'terminal_result_sha256': terminal.terminal_result_sha256}


class LinuxTerminationIssuer:
    """Explicit physical issuer; no existing generic issuer gate is enabled."""
    def __init__(self, *, config):
        if type(config) is not PhysicalIssuerConfig:
            raise ValueError('Explicit physical issuer configuration required')
        self.config = config

    def issue_under_lease(self, execution_id, adapter, envelope, profile, lease, observation):
        if (self.config.enabled is not True or self.config.registry.enabled is not True
                or self.config.store.config.verifier_registry.enabled is not True):
            _error('sandbox_physical_issuer_unavailable')
        _observation(observation, adapter, envelope, profile, lease)
        with observation._handle._operation_lock:
            return self._issue_under_lease(execution_id, adapter, envelope, profile, lease, observation)

    def _issue_under_lease(self, execution_id, adapter, envelope, profile, lease, observation):
        config = self.config
        if config.enabled is not True or config.registry.enabled is not True:
            _error('sandbox_physical_issuer_unavailable')
        try:
            if type(execution_id) is not str or str(uuid.UUID(execution_id)) != execution_id:
                _error('sandbox_physical_closed_binding')
            reference = _host_guard(adapter, envelope, profile, lease)
            _, _, runtime_hash = _materials(adapter, envelope, profile, lease)
            data = _observation(observation, adapter, envelope, profile, lease)
            _lease(adapter, envelope, profile, lease)
            binding, row = _closed_rows(config.store, execution_id)
            _lease(adapter, envelope, profile, lease)
            scoped = TerminationIssuerScope.model_validate({
                name: getattr(binding, name) for name in TerminationIssuerScope.model_fields})
            metadata = envelope.metadata
            if (scoped != config.scope or binding.execution_id != execution_id
                    or binding.job_id != envelope.job_id or binding.envelope_sha256 != envelope.envelope_sha256
                    or binding.worker_id != reference.host_id or binding.host_boot_id != reference.configured_host_boot_id
                    or binding.journal_id != reference.journal_id or binding.journal_epoch != lease.epoch
                    or binding.profile_sha256 != profile.profile_sha256 or binding.runtime_sha256 != runtime_hash
                    or binding.adapter_source_sha256 != adapter._helper_sha256
                    or binding.image_digest != envelope.environment['image_digest']
                    or binding.trusted_init_sha256 != profile.document['trusted_init']['sha256']
                    or any(getattr(binding, name) != metadata[name] for name in (
                        'site_id', 'reservation_id', 'owner_user_id', 'experiment_id', 'proposal_revision_id', 'approval_id'))
                    or binding.environment_sha256 != metadata['hashes']['environment_sha256']):
                _error('sandbox_physical_closed_binding')
            _source_files(config, adapter, envelope, profile, lease)
            terminal, journal = _journal_claims(adapter, envelope, profile, lease, observation, binding, row)
            _empty(observation._handle, time.monotonic() + 2)
            delete = data['delete']
            _validate_delete(delete, adapter, envelope, profile)
            if (data['journal_epoch'] != lease.epoch or data['host_boot_id'] != binding.host_boot_id
                    or data['journal_id'] != binding.journal_id or data['runtime_sha256'] != binding.runtime_sha256
                    or data['profile_sha256'] != binding.profile_sha256 or delete['exit_code'] != 0
                    or delete['pipes_eof'] is not True):
                _error('sandbox_physical_observation')
            kernel = {'cgroup_path': data['cgroup_path'], 'cgroup_device': data['cgroup_device'],
                'cgroup_inode': data['cgroup_inode'], 'populated': 0, 'delete_exit_code': 0,
                'delete_job_id': binding.job_id, 'delete_runtime_sha256': binding.runtime_sha256,
                'delete_host_boot_id': binding.host_boot_id, 'delete_command_sha256': delete['command_sha256'],
                'delete_acknowledgement_sha256': _sha(_canonical(delete)),
                'raw_observation_sha256': observation.native_observation_sha256,
                'cleanup_started_monotonic_ns': data['cleanup_started_monotonic_ns'],
                'delete_acknowledged_monotonic_ns': delete['acknowledged_monotonic_ns'],
                'populated_zero_monotonic_ns': data['populated_zero_monotonic_ns'],
                'terminal_recorded_monotonic_ns': terminal.terminal_recorded_monotonic_ns,
                'issued_monotonic_ns': _now()}
            claims = TerminationClaims.model_validate({'binding': binding, 'journal': journal, 'kernel': kernel})
            _private_directory(config.evidence_root)
            job = adapter.worker_root / envelope.job_id
            if any(config.evidence_root == job / part or job / part in config.evidence_root.parents
                   for part in ('rootfs', 'inputs')):
                _error('sandbox_physical_evidence_path')
            name = f'issuance-{execution_id}-{binding.closed_fence}.json'
            path = config.evidence_root / name
            if path.exists() or path.is_symlink():
                # Read only the checked stable receipt helper, then reuse its
                # already frozen timestamp. Any other changed field conflicts.
                before = path.lstat()
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o600
                        or not 1 <= before.st_size <= MAX_NATIVE_BYTES):
                    _error('sandbox_physical_evidence_path')
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
                try:
                    existing = os.read(descriptor, MAX_NATIVE_BYTES + 1)
                    if _stamp(before) != _stamp(os.fstat(descriptor)) or _stamp(before) != _stamp(path.lstat()):
                        _error('sandbox_physical_evidence_path')
                finally:
                    os.close(descriptor)
                intent = json.loads(existing)
                issued = intent['claims']['kernel']['issued_monotonic_ns']
                if type(issued) is not int or issued > kernel['issued_monotonic_ns']:
                    _error('sandbox_physical_evidence_conflict')
                kernel['issued_monotonic_ns'] = issued
                claims = TerminationClaims.model_validate({'binding': binding, 'journal': journal, 'kernel': kernel})
            unsigned = _canonical({'version': TERMINATION_PACKET_VERSION, 'algorithm': 'Ed25519',
                'trust_scope': config.registry.trust_scope, 'issuer_id': config.issuer_id,
                'key_id': config.key_id, 'claims': claims.model_dump(mode='json')})
            _retained_bytes(config.evidence_root, name, unsigned, lease)
            _host_guard(adapter, envelope, profile, lease)
            _handle(observation._handle, adapter, envelope, profile, lease)
            _empty(observation._handle, time.monotonic() + 2)
            _lease(adapter, envelope, profile, lease)
            signed = sign_termination_claims(claims, issuer_id=config.issuer_id, key_id=config.key_id,
                trust_scope=config.registry.trust_scope, private_key=config._private_key)
            _lease(adapter, envelope, profile, lease)
            verified = verify_termination_packet(canonical_packet_bytes(signed), expected=binding, registry=config.registry)
            retain_termination_packet(config.evidence_root, verified)
            _lease(adapter, envelope, profile, lease)
            return signed
        except SandboxError:
            raise
        except (OSError, ValueError, TypeError, AttributeError, KeyError, UnicodeError, RecursionError):
            _error('sandbox_physical_issuer_unavailable')
