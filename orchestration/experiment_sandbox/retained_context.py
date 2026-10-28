"""Actual held-job scope for retained controllers, without runtime authority.

Only the internal context manager claims the exact adapter's durable journal.
These host-safe lifetime/binding checks do not perform Linux preflight, mint a
start/publication permit, prove termination, authenticate an issuer or release
capacity. The retained runner must perform actual base preflight beforehand.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import threading
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict

from orchestration.experiment_sandbox.contracts import (
    SandboxError, VerifiedEnvelope, verify_execution_envelope,
)
from orchestration.experiment_sandbox.journal import DurableExecutionJournal, DurableLease
from orchestration.experiment_sandbox.linux_runtime import LinuxExecutionAdapter
from orchestration.experiment_sandbox.profile import RuntimePreparation
from orchestration.experiment_sandbox.profile_execution import PreparedExecutionProfile, VERSION as PROFILE_VERSION
from orchestration.experiment_sandbox.retained_bridge import RetainedExecutionIdentity
from schema.context_catalogue import canonical_json
from schema.experiment_execution import Hash, Job, Site
from schema.investigations import UUIDString
from schema.research_experiments import content_sha256

_SHA = re.compile(r'^[a-f0-9]{64}$')
_MUTEX = threading.RLock()
_CONTEXTS = {}
_HELD_JOBS = {}


def _after_fork():
    # Do not touch a lease, descriptor or inherited parent mutex here. The
    # journal's existing fork handler safely closes only child FD copies.
    global _MUTEX
    _MUTEX = threading.RLock()
    _CONTEXTS.clear()
    _HELD_JOBS.clear()


os.register_at_fork(after_in_child=_after_fork)


def _error(reason='sandbox_retained_context_binding'):
    raise SandboxError(reason)


class _IdentityDocument(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    version: Literal['c23-retained-reserve-identity-v1']
    execution_id: UUIDString
    reservation_id: UUIDString
    site_id: Site
    owner_user_id: UUIDString
    experiment_id: UUIDString
    proposal_revision_id: UUIDString
    approval_id: UUIDString
    envelope_sha256: Hash
    execution_request_sha256: Hash
    job_id: Job
    capacity_reserved_at_commit: bool
    capacity_snapshot_only: Literal[True]
    execution_authorized: Literal[False]
    publication_authorized: Literal[False]
    reservation_release_authorized: Literal[False]
    scientific_approval: Literal['not_independently_verified']


@dataclass(frozen=True, slots=True)
class _Bindings:
    worker_root: str
    runtime_directory: str
    cgroup_root: str
    journal_root: str
    host_id: str
    host_boot_id: str
    runtime_json: str
    helper_sha256: str
    envelope_json: str
    envelope_sha256: str
    job_id: str
    files: tuple
    profile_json: str
    profile_sha256: str
    execution_json: str
    execution_id: str
    reservation_id: str
    owner_user_id: str
    site_id: str


def _path(value):
    if not isinstance(value, Path) or not value.is_absolute():
        _error()
    return str(value)


def _canonical_document(raw, maximum):
    if type(raw) is not str or not 2 <= len(raw.encode('utf-8')) <= maximum:
        _error()
    value = json.loads(raw)
    if type(value) is not dict or canonical_json(value) != raw:
        _error()
    return value


def _files(envelope):
    if type(envelope._files) is not MappingProxyType:
        _error()
    items = tuple(sorted(envelope.files.items()))
    if any(type(name) is not str or type(raw) is not bytes for name, raw in items):
        _error()
    return items


def _capture(adapter, envelope, profile, execution):
    if (type(adapter) is not LinuxExecutionAdapter or type(adapter.journal) is not DurableExecutionJournal
            or type(envelope) is not VerifiedEnvelope or type(profile) is not PreparedExecutionProfile
            or type(execution) is not RetainedExecutionIdentity):
        _error()
    try:
        metadata = _canonical_document(envelope._metadata_json, 1024 * 1024)
        identity = _IdentityDocument.model_validate(_canonical_document(execution._json, 65536)).model_dump(mode='json')
        document = _canonical_document(profile._json, 1024 * 1024)
        runtime = RuntimePreparation.model_validate(_canonical_document(adapter._runtime_json, 65536)).model_dump(mode='json')
        files = _files(envelope)
        # This repeats pure byte/hash checks only, using the already retained
        # envelope's descriptor as data. It is no fresh environment admission.
        checked = verify_execution_envelope({'metadata': metadata, 'files': dict(files)},
            expected_envelope_sha256=envelope.envelope_sha256,
            environments={metadata['proposal']['environment_id']: metadata['environment']})
        if (checked.job_id != envelope.job_id or checked._metadata_json != envelope._metadata_json
                or canonical_json(identity) != execution._json
                or profile.profile_sha256 != content_sha256(document)
                or not callable(adapter.clock)
                or type(adapter._helper_sha256) is not str or not _SHA.fullmatch(adapter._helper_sha256)
                or document['version'] != PROFILE_VERSION
                or document['job_id'] != envelope.job_id or document['envelope_sha256'] != envelope.envelope_sha256
                or document['runtime_preparation'] != runtime
                or document['environment_sha256'] != metadata['hashes']['environment_sha256']
                or document['proposal_hashes'] != metadata['hashes']
                or document['approved_resources'] != metadata['proposal']['resources']
                or document['config']['linux']['cgroupsPath'] != '/ocean-c23/' + envelope.job_id + '/sandbox'
                or document['image_preparation']['image_digest'] != metadata['environment']['image_digest']
                or identity['job_id'] != envelope.job_id or identity['envelope_sha256'] != envelope.envelope_sha256
                or any(identity[name] != metadata[name] for name in (
                    'reservation_id','owner_user_id','site_id','experiment_id','proposal_revision_id','approval_id'))):
            _error()
        journal = adapter.journal
        return _Bindings(_path(adapter.worker_root), _path(adapter.runtime_directory), _path(adapter.cgroup_root),
            _path(journal.root), journal.host_id, journal.host_boot_id, adapter._runtime_json,
            adapter._helper_sha256, envelope._metadata_json, envelope.envelope_sha256, envelope.job_id,
            files, profile._json, profile.profile_sha256, execution._json,
            identity['execution_id'], identity['reservation_id'], identity['owner_user_id'], identity['site_id'])
    except SandboxError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        _error()


@dataclass(frozen=True, slots=True)
class _Registration:
    context: object
    pid: int
    adapter: LinuxExecutionAdapter
    journal: DurableExecutionJournal
    lease: DurableLease
    envelope: VerifiedEnvelope
    profile: PreparedExecutionProfile
    execution: RetainedExecutionIdentity
    clock: object
    bindings: _Bindings
    journal_id: str


def _registered(context):
    # PID and exact-type checks precede any mutex, including after a fork where
    # another vanished parent thread could have held a lock.
    if type(context) is not HeldRuntimeContext:
        _error('sandbox_retained_context_closed')
    try:
        if type(context._pid) is not int or context._pid != os.getpid():
            _error('sandbox_retained_context_closed')
    except AttributeError:
        _error('sandbox_retained_context_closed')
    with _MUTEX:
        record = _CONTEXTS.get(id(context))
        if record is None or record.context is not context or record.pid != os.getpid():
            _error('sandbox_retained_context_closed')
    try:
        if (context._adapter is not record.adapter or context._journal is not record.journal
                or context._lease is not record.lease or context._envelope is not record.envelope
                or context._profile is not record.profile or context._execution_identity is not record.execution):
            _error()
    except AttributeError:
        _error()
    return record


def _unchanged(record):
    a, j, b = record.adapter, record.journal, record.bindings
    e, p, execution = record.envelope, record.profile, record.execution
    try:
        if (type(a) is not LinuxExecutionAdapter or type(j) is not DurableExecutionJournal
                or type(e) is not VerifiedEnvelope or type(p) is not PreparedExecutionProfile
                or type(execution) is not RetainedExecutionIdentity or a.journal is not j
                or a.clock is not record.clock or _path(a.worker_root) != b.worker_root
                or _path(a.runtime_directory) != b.runtime_directory or _path(a.cgroup_root) != b.cgroup_root
                or _path(j.root) != b.journal_root or j.host_id != b.host_id or j.host_boot_id != b.host_boot_id
                or a._runtime_json != b.runtime_json or a._helper_sha256 != b.helper_sha256
                or e._metadata_json != b.envelope_json or e.envelope_sha256 != b.envelope_sha256
                or e.job_id != b.job_id or _files(e) != b.files
                or p._json != b.profile_json or p.profile_sha256 != b.profile_sha256
                or execution._json != b.execution_json):
            _error()
    except SandboxError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        _error()


@dataclass(frozen=True, init=False, slots=True)
class HeldRuntimeContext:
    """Internal actual-job scope, never Linux/start/publication/proof authority.

    Readonly getters require a live registered scope; they are not a substitute
    for require_current immediately around each trusted operation. No context
    or copied fields may be serialized/reconstructed into a fresh start permit.
    """
    _pid: int
    _adapter: LinuxExecutionAdapter
    _journal: DurableExecutionJournal
    _lease: DurableLease
    _envelope: VerifiedEnvelope
    _profile: PreparedExecutionProfile
    _execution_identity: RetainedExecutionIdentity

    def __init__(self, *args, **kwargs):
        raise TypeError('Use the internal _hold_runtime_context scope')

    def require_current(self, expected_head_sha256=None):
        record = _registered(self)
        if expected_head_sha256 is not None and (type(expected_head_sha256) is not str
                or not _SHA.fullmatch(expected_head_sha256)):
            _error('sandbox_retained_context_head')
        _unchanged(record)
        # Keep both guarded journal reads on one actual journal mutex. Never
        # hold the module registry mutex while entering journal/SQLite locks.
        with record.journal._mutex:
            snapshot = DurableExecutionJournal.require_current(record.journal, record.lease)
            identity = DurableExecutionJournal.identity_reference(record.journal, record.lease)
            b = record.bindings
            event = snapshot.events[-1]
            if (identity.journal_id != record.journal_id or identity.job_id != b.job_id
                    or identity.envelope_sha256 != b.envelope_sha256 or identity.host_id != b.host_id
                    or identity.configured_host_boot_id != b.host_boot_id
                    or identity.epoch != snapshot.epoch or identity.sequence != event.sequence
                    or identity.head_sha256 != event.sha256
                    or (expected_head_sha256 is not None and event.sha256 != expected_head_sha256)):
                _error('sandbox_retained_context_head')
            _unchanged(record)
            if _registered(self) is not record:
                _error('sandbox_retained_context_closed')
            return snapshot

    @property
    def adapter(self):
        return _registered(self).adapter

    @property
    def journal(self):
        return _registered(self).journal

    @property
    def lease(self):
        return _registered(self).lease

    @property
    def envelope(self):
        return _registered(self).envelope

    @property
    def profile(self):
        return _registered(self).profile

    @property
    def execution_identity(self):
        return _registered(self).execution

    def _binding(self, name):
        return getattr(_registered(self).bindings, name)

    job_id = property(lambda self: self._binding('job_id'))
    envelope_sha256 = property(lambda self: self._binding('envelope_sha256'))
    profile_sha256 = property(lambda self: self._binding('profile_sha256'))
    execution_id = property(lambda self: self._binding('execution_id'))
    reservation_id = property(lambda self: self._binding('reservation_id'))
    owner_user_id = property(lambda self: self._binding('owner_user_id'))
    site_id = property(lambda self: self._binding('site_id'))
    host_id = property(lambda self: self._binding('host_id'))
    host_boot_id = property(lambda self: self._binding('host_boot_id'))
    worker_root = property(lambda self: Path(self._binding('worker_root')))
    runtime_directory = property(lambda self: Path(self._binding('runtime_directory')))
    cgroup_root = property(lambda self: Path(self._binding('cgroup_root')))
    runtime_json = property(lambda self: self._binding('runtime_json'))
    helper_sha256 = property(lambda self: self._binding('helper_sha256'))
    journal_id = property(lambda self: _registered(self).journal_id)


@contextmanager
def _hold_runtime_context(adapter, envelope, profile, execution_identity):
    """Claim the actual journal here; never accept an external lease/context.

    The context is invalidated before the actual claim exits, including failed
    checks and exceptions. A terminal reacquisition gets a new live context;
    the old object never regains access and no new start is authorized.
    """
    bindings = _capture(adapter, envelope, profile, execution_identity)
    journal, clock = adapter.journal, adapter.clock
    pid, token = os.getpid(), object()
    job_key = (id(journal), bindings.job_id)
    with _MUTEX:
        if job_key in _HELD_JOBS:
            _error('sandbox_retained_context_busy')
        _HELD_JOBS[job_key] = token
    context = None
    try:
        with DurableExecutionJournal.claim(journal, bindings.job_id, bindings.envelope_sha256) as lease:
            identity = DurableExecutionJournal.identity_reference(journal, lease)
            context = object.__new__(HeldRuntimeContext)
            for name, value in {'_pid':pid,'_adapter':adapter,'_journal':journal,'_lease':lease,
                                '_envelope':envelope,'_profile':profile,'_execution_identity':execution_identity}.items():
                object.__setattr__(context,name,value)
            record = _Registration(context,pid,adapter,journal,lease,envelope,profile,execution_identity,
                                   clock,bindings,identity.journal_id)
            with _MUTEX:
                _CONTEXTS[id(context)] = record
            try:
                context.require_current()
                yield context
            finally:
                # A child does not inherit the parent's registry or revoke its
                # context/lease. Its journal PID guard also forbids LOCK_UN.
                if os.getpid() == pid:
                    with _MUTEX:
                        if _CONTEXTS.get(id(context)) is record:
                            del _CONTEXTS[id(context)]
    finally:
        if os.getpid() == pid:
            with _MUTEX:
                if _HELD_JOBS.get(job_key) is token:
                    del _HELD_JOBS[job_key]
