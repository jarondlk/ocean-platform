"""C23 supervisor ports and an explicitly non-executing local simulation.

No production adapter is provided. The in-memory journal is neither durable nor
a cross-host lease. Its epochs exercise fences, while fixed job identities
exercise reconciliation. Neither simulated termination nor a result releases a
C22 reservation. Real execution, persistence and containment remain gated.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import threading
import time
from types import MappingProxyType
from typing import Protocol

from orchestration.experiment_sandbox.contracts import SandboxError, VerifiedEnvelope
from orchestration.experiment_sandbox.files import ValidatedOutputs
from schema.context_catalogue import canonical_json
from schema.research_experiments import content_sha256

VERSION = 'c23-synthetic-supervisor-v1'
RUNTIME_VERSION = 'c23-nonexecuting-fake-v1'
PROFILE_VERSION = 'c23-synthetic-profile-v1'
_SHA = re.compile(r'^[a-f0-9]{64}$')
_JOB = re.compile(r'^c23-[a-f0-9]{48}$')
_FINAL = frozenset({'simulated', 'failed', 'cancelled', 'timed_out', 'unavailable'})


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class RuntimeAttestation:
    job_id: str
    envelope_sha256: str
    resources_sha256: str
    profile_sha256: str
    runtime_sha256: str
    kind: str = RUNTIME_VERSION
    simulation: bool = True
    containment_verified: bool = False

    def __post_init__(self):
        if (not isinstance(self.job_id, str) or not _JOB.fullmatch(self.job_id)
                or any(not isinstance(value, str) or not _SHA.fullmatch(value)
                       for value in (self.envelope_sha256, self.resources_sha256,
                                     self.profile_sha256, self.runtime_sha256))
                or self.kind != RUNTIME_VERSION or self.simulation is not True
                or self.containment_verified is not False):
            raise SandboxError('sandbox_runtime_identity')


@dataclass(frozen=True)
class RuntimeObservation:
    identity: RuntimeAttestation
    state: str
    elapsed_seconds: float = 0.0
    exit_code: int | None = None

    def __post_init__(self):
        if (type(self.identity) is not RuntimeAttestation
                or type(self.state) is not str or self.state not in {'absent', 'created', 'running', 'stopped', 'unknown'}
                or not _number(self.elapsed_seconds)
                or (self.exit_code is not None and (type(self.exit_code) is not int or not -255 <= self.exit_code <= 255))
                or (self.state != 'stopped' and self.exit_code is not None)):
            raise SandboxError('sandbox_runtime_observation')


@dataclass(frozen=True)
class TerminationProof:
    """Simulated proof shape only; it cannot authorize actual capacity release."""
    identity: RuntimeAttestation
    whole_process_tree_gone: bool
    runtime_state_removed: bool
    simulation: bool = True

    def __post_init__(self):
        if (type(self.identity) is not RuntimeAttestation or self.simulation is not True
                or type(self.whole_process_tree_gone) is not bool or type(self.runtime_state_removed) is not bool):
            raise SandboxError('sandbox_termination_identity')


class SandboxRuntime(Protocol):
    """Future trusted port. A conforming shape alone does not admit a runtime."""
    def preflight(self, envelope: VerifiedEnvelope) -> RuntimeAttestation: ...
    def create(self, envelope: VerifiedEnvelope, identity: RuntimeAttestation) -> RuntimeObservation: ...
    def verify_created(self, job_id: str) -> RuntimeAttestation: ...
    def start(self, job_id: str) -> RuntimeObservation: ...
    def observe(self, job_id: str, identity: RuntimeAttestation) -> RuntimeObservation: ...
    def terminate_and_prove(self, job_id: str, identity: RuntimeAttestation) -> TerminationProof: ...


@dataclass(frozen=True)
class JournalToken:
    job_id: str
    envelope_sha256: str
    epoch: int

    def __post_init__(self):
        if (type(self.job_id) is not str or not _JOB.fullmatch(self.job_id)
                or type(self.envelope_sha256) is not str or not _SHA.fullmatch(self.envelope_sha256)
                or type(self.epoch) is not int or not 1 <= self.epoch <= 2**63 - 1):
            raise SandboxError('sandbox_journal_identity')


@dataclass(frozen=True)
class JournalEvent:
    sequence: int
    token: JournalToken
    kind: str
    monotonic_at: float
    payload_json: str
    previous_sha256: str
    sha256: str

    @property
    def payload(self):
        return json.loads(self.payload_json)


@dataclass(frozen=True, init=False)
class SupervisorResult:
    """Detached immutable control-plane result, never a scientific finding."""
    _json: str

    def __init__(self, document):
        if (not isinstance(document, Mapping) or type(document.get('state')) is not str
                or document.get('state') not in _FINAL | {'uncertain'}
                or document.get('simulation') is not True
                or document.get('execution_performed') is not False
                or document.get('reservation_released') is not False
                or document.get('scientific_approval') != 'not_independently_verified'):
            raise SandboxError('sandbox_result_identity')
        object.__setattr__(self, '_json', canonical_json(document))

    @property
    def document(self):
        return json.loads(self._json)

    @property
    def state(self):
        return self.document['state']

    @property
    def sha256(self):
        return _hash_bytes(self._json.encode('utf-8'))


class ExecutionJournal(Protocol):
    def claim(self, job_id: str, envelope_sha256: str) -> JournalToken: ...
    def require_current(self, token: JournalToken) -> None: ...
    def append(self, token: JournalToken, kind: str, at: float, payload: Mapping) -> JournalEvent: ...
    def events(self, job_id: str) -> tuple[JournalEvent, ...]: ...
    def completed(self, job_id: str, envelope_sha256: str) -> SupervisorResult | None: ...
    def finish(self, token: JournalToken, result: SupervisorResult) -> None: ...


class MemoryExecutionJournal:
    """Synthetic single-process journal with append-only hash-linked events.

    Claiming an existing job explicitly models a forced controller failover and
    invalidates its previous epoch. It is not a time-based lease and must not be
    used as a production store or as evidence that an old process terminated.
    """
    simulation = True
    durable = False

    def __init__(self):
        self._jobs, self._lock = {}, threading.RLock()

    def claim(self, job_id, envelope_sha256):
        if (type(job_id) is not str or not _JOB.fullmatch(job_id)
                or type(envelope_sha256) is not str or not _SHA.fullmatch(envelope_sha256)):
            raise SandboxError('sandbox_journal_identity')
        with self._lock:
            job = self._jobs.setdefault(job_id, {'hash': envelope_sha256, 'epoch': 0, 'events': [], 'result': None})
            if job['hash'] != envelope_sha256:
                raise SandboxError('sandbox_journal_identity')
            if job['epoch'] >= 2**63 - 1:
                raise SandboxError('sandbox_journal_limit')
            job['epoch'] += 1
            return JournalToken(job_id, envelope_sha256, job['epoch'])

    def require_current(self, token):
        with self._lock:
            if type(token) is not JournalToken:
                raise SandboxError('sandbox_journal_identity')
            job = self._jobs.get(token.job_id)
            if job is None or job['hash'] != token.envelope_sha256 or job['epoch'] != token.epoch:
                raise SandboxError('sandbox_fence_lost')

    def append(self, token, kind, at, payload):
        with self._lock:
            self.require_current(token)
            job = self._jobs[token.job_id]
            events = job['events']
            if (job['result'] is not None or not _number(at) or (events and at < events[-1].monotonic_at)
                    or len(events) >= 4096 or not isinstance(kind, str) or not re.fullmatch(r'[a-z_]{1,40}', kind)):
                raise SandboxError('sandbox_journal_integrity')
            encoded = canonical_json(dict(payload))
            if len(encoded.encode()) > 64 * 1024:
                raise SandboxError('sandbox_journal_limit')
            previous = events[-1].sha256 if events else '0' * 64
            fields = {'sequence': len(events) + 1, 'token': asdict(token), 'kind': kind,
                      'monotonic_at': at, 'payload_json': encoded, 'previous_sha256': previous}
            event = JournalEvent(len(events) + 1, token, kind, at, encoded, previous, content_sha256(fields))
            events.append(event)
            return event

    def events(self, job_id):
        with self._lock:
            return tuple(self._jobs.get(job_id, {}).get('events', ()))

    def completed(self, job_id, envelope_sha256):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job['hash'] != envelope_sha256:
                raise SandboxError('sandbox_journal_identity')
            return job['result'] if job else None

    def finish(self, token, result):
        with self._lock:
            self.require_current(token)
            document = result.document
            if (document['job_id'] != token.job_id or document['envelope_sha256'] != token.envelope_sha256
                    or document['state'] not in _FINAL):
                raise SandboxError('sandbox_result_identity')
            job = self._jobs[token.job_id]
            if job['result'] is not None and job['result'].sha256 != result.sha256:
                raise SandboxError('sandbox_result_immutable')
            job['result'] = result


def synthetic_identity(envelope):
    return RuntimeAttestation(job_id=envelope.job_id, envelope_sha256=envelope.envelope_sha256,
        resources_sha256=content_sha256(envelope.resources),
        profile_sha256=content_sha256({'version': PROFILE_VERSION, 'resources': envelope.resources,
                                      'environment_sha256': content_sha256(envelope.environment)}),
        runtime_sha256=_hash_bytes(RUNTIME_VERSION.encode()))


class SyntheticRuntime:
    """Deterministic fixture state machine; never interprets approved Python.

    Fixed outputs/logs are supplied by the test harness. ``lose_ack`` models an
    effect followed by transport failure. A stopped initial process alone is
    deliberately not a whole-process-tree termination proof.
    """
    simulation = True
    kind = RUNTIME_VERSION

    def __init__(self, *, observations=None, outputs=None, logs=None, lose_ack=(), termination_succeeds=True):
        self.observations = tuple(observations if observations is not None else [('stopped', 0.0, 0)])
        self._outputs = MappingProxyType(dict(outputs or {}))
        self._logs = MappingProxyType(dict(logs or {}))
        if (any(type(name) is not str or type(raw) is not bytes for name, raw in self._outputs.items())
                or any(name not in {'stdout', 'stderr'} or type(raw) is not bytes for name, raw in self._logs.items())
                or type(termination_succeeds) is not bool):
            raise SandboxError('sandbox_fake_fixture')
        self._lose_ack = set(lose_ack)
        if not self._lose_ack <= {'create', 'start', 'terminate'}:
            raise SandboxError('sandbox_fake_fixture')
        self.termination_succeeds = termination_succeeds
        self._jobs, self._lock, self.calls = {}, threading.RLock(), []

    def _call(self, action, job_id):
        self.calls.append((action, job_id))

    def _ack(self, action):
        if action in self._lose_ack:
            self._lose_ack.remove(action)
            raise SandboxError('sandbox_fake_ack_lost')

    def preflight(self, envelope):
        self._call('preflight', envelope.job_id)
        if envelope.environment['kind'] != 'c22-fake' or envelope.environment['test_only'] is not True:
            raise SandboxError('sandbox_real_runtime_unavailable')
        return synthetic_identity(envelope)

    def create(self, envelope, identity):
        with self._lock:
            self._call('create', envelope.job_id)
            if identity != synthetic_identity(envelope):
                raise SandboxError('sandbox_runtime_identity')
            existing = self._jobs.get(envelope.job_id)
            if existing is not None and existing['identity'] != identity:
                raise SandboxError('sandbox_runtime_identity')
            job = self._jobs.setdefault(envelope.job_id, {'identity': identity, 'state': 'created', 'elapsed': 0.0,
                'exit': None, 'started': False, 'next': 0, 'gone': False, 'removed': False})
            self._ack('create')
            return self._observation(job)

    def verify_created(self, job_id):
        with self._lock:
            self._call('verify_created', job_id)
            job = self._jobs[job_id]
            if job['state'] != 'created' or job['removed']:
                raise SandboxError('sandbox_runtime_observation')
            return job['identity']

    def start(self, job_id):
        with self._lock:
            self._call('start', job_id)
            job = self._jobs[job_id]
            if not job['started']:
                if job['state'] != 'created' or job['removed']:
                    raise SandboxError('sandbox_runtime_observation')
                job['started'], job['state'] = True, 'running'
            self._ack('start')
            return self._observation(job)

    @staticmethod
    def _observation(job):
        return RuntimeObservation(job['identity'], job['state'], job['elapsed'], job['exit'])

    def observe(self, job_id, identity):
        with self._lock:
            self._call('observe', job_id)
            job = self._jobs.get(job_id)
            if job is None:
                return RuntimeObservation(identity, 'absent')
            if job['state'] == 'running' and job['next'] < len(self.observations):
                state, elapsed, code = self.observations[job['next']]
                job['state'], job['elapsed'], job['exit'] = state, elapsed, code
                job['next'] += 1
            return self._observation(job)

    def terminate_and_prove(self, job_id, identity):
        with self._lock:
            self._call('terminate', job_id)
            job = self._jobs.get(job_id)
            if job is None or job['identity'] != identity:
                return TerminationProof(identity, False, False)
            if self.termination_succeeds:
                job['state'], job['gone'], job['removed'] = 'stopped', True, True
                job['exit'] = job['exit'] if job['exit'] is not None else -9
            self._ack('terminate')
            return TerminationProof(job['identity'], job['gone'], job['removed'])

    def output_bytes(self, job_id):
        with self._lock:
            job = self._jobs[job_id]
            if not job['gone'] or not job['removed']:
                raise SandboxError('sandbox_termination_unverified')
            return self._outputs, self._logs


class ExperimentSupervisor:
    """Exercise the trusted lifecycle using synthetic ports only.

    The admission callback must perform a fresh C22 authorization/integrity read
    and return its verified exact envelope hash. A Boolean is insufficient.
    Cleanup is independent of admission. The collector must validate actual
    output bytes; its receipt is checked again before retained publication.
    """
    def __init__(self, *, runtime, journal, clock=time.monotonic, max_observations=1000):
        if (not isinstance(runtime, SyntheticRuntime) or runtime.kind != RUNTIME_VERSION
                or runtime.simulation is not True or not isinstance(journal, MemoryExecutionJournal)
                or journal.simulation is not True or journal.durable is not False
                or type(max_observations) is not int or not 1 <= max_observations <= 10000):
            raise SandboxError('sandbox_real_runtime_unavailable')
        self.runtime, self.journal, self.clock = runtime, journal, clock
        self.max_observations = max_observations

    def run(self, envelope, *, admission, cancelled=lambda: False, collect):
        if (type(envelope) is not VerifiedEnvelope or envelope.environment['kind'] != 'c22-fake'
                or envelope.environment['test_only'] is not True
                or content_sha256(envelope.metadata) != envelope.envelope_sha256
                or envelope.job_id != 'c23-' + content_sha256({'site': envelope.metadata['site_id'],
                    'reservation': envelope.metadata['reservation_id'], 'envelope': envelope.envelope_sha256})[:48]):
            raise SandboxError('sandbox_real_runtime_unavailable')
        expected = synthetic_identity(envelope)
        previous = self.journal.events(envelope.job_id)
        last_at = previous[-1].monotonic_at if previous else None
        try:
            now = self.clock()
        except Exception:
            raise SandboxError('sandbox_clock_invalid') from None
        if not _number(now) or (last_at is not None and now < last_at):
            raise SandboxError('sandbox_clock_invalid')
        last_at = now
        first_start = next((event.monotonic_at for event in previous if event.kind == 'start_intent'), None)
        started_at = first_start
        last_elapsed = 0.0
        token = None
        proof, output_manifest, exit_code = None, None, None
        journal_failed = False
        had_effect = any(event.kind in {'create_intent', 'start_intent'} for event in previous)
        stage = 'admission'

        def current():
            if token is not None:
                self.journal.require_current(token)

        def tick():
            nonlocal last_at
            value = self.clock()
            if not _number(value) or value < last_at:
                raise SandboxError('sandbox_clock_invalid')
            last_at = value
            current()
            return value

        def event(kind, payload=None):
            return self.journal.append(token, kind, tick(), payload or {})

        def admit():
            current()
            if admission(envelope) != envelope.envelope_sha256:
                raise SandboxError('sandbox_admission_denied')
            current()
            tick()

        def observation(value):
            nonlocal last_elapsed, exit_code
            current()
            if type(value) is not RuntimeObservation or value.identity != expected or value.elapsed_seconds < last_elapsed:
                raise SandboxError('sandbox_runtime_observation')
            last_elapsed, exit_code = value.elapsed_seconds, value.exit_code
            event('observation', asdict(value))
            return value

        def terminate():
            nonlocal proof, journal_failed
            current()
            # Clock failure must not prevent cleanup. Use the last actually
            # observed timestamp, without inventing a later clock observation.
            try:
                self.journal.append(token, 'terminate_intent', last_at, {'clock_at_is_last_observed': True})
            except Exception:
                journal_failed = True
                current()  # Failed persistence must not bypass the current fence.
            current()
            candidate = self.runtime.terminate_and_prove(envelope.job_id, expected)
            current()
            if (type(candidate) is not TerminationProof or candidate.identity != expected
                    or not candidate.whole_process_tree_gone or not candidate.runtime_state_removed):
                raise SandboxError('sandbox_termination_unverified')
            proof = candidate
            try:
                self.journal.append(token, 'terminated', last_at, asdict(proof))
            except Exception:
                journal_failed = True
                current()
            return proof

        def result(state, reason):
            nonlocal journal_failed, output_manifest
            if journal_failed:
                state = 'uncertain'
                reason = 'sandbox_fence_lost' if reason == 'sandbox_fence_lost' else 'sandbox_journal_unavailable'
                output_manifest = None
            document = {'version': VERSION, 'job_id': envelope.job_id, 'envelope_sha256': envelope.envelope_sha256,
                'reservation_id': envelope.metadata['reservation_id'], 'proposal_revision_id': envelope.metadata['proposal_revision_id'],
                'state': state, 'reason': reason, 'simulation': True, 'execution_performed': False,
                'reservation_released': False, 'authority': 'experimental',
                'scientific_approval': 'not_independently_verified', 'hashes': envelope.metadata['hashes'],
                'environment': envelope.environment, 'resources': envelope.resources, 'seeds': envelope.proposal['seeds'],
                'runtime': asdict(expected), 'termination': asdict(proof) if proof else None,
                'exit_code': exit_code, 'simulated_elapsed_seconds': last_elapsed,
                'control_elapsed_seconds': max(0.0, last_at - started_at) if started_at is not None else 0.0,
                'output_manifest': output_manifest, 'journal_epoch': token.epoch if token else None,
                'journal_recording_complete': not journal_failed,
                'limitations': ['No Python was executed; outputs are supplied synthetic fixtures',
                    'In-memory journal is not durable or a production lease',
                    'Simulated termination cannot release C22 reservations or prove Linux containment']}
            value = SupervisorResult(document)
            if token is not None:
                current()
                if journal_failed:
                    return value  # Never retain/publish a result after failed journaling.
                try:
                    self.journal.append(token, 'result', last_at, {'state': state, 'reason': reason, 'sha256': value.sha256})
                except Exception:
                    journal_failed = True
                    current()
                    return result('uncertain', 'sandbox_journal_unavailable')
                if state in _FINAL:
                    self.journal.finish(token, value)
            return value

        try:
            retained = self.journal.completed(envelope.job_id, envelope.envelope_sha256)
            if retained is not None:
                admit()  # Retained results still need current access.
                return retained
            token = self.journal.claim(envelope.job_id, envelope.envelope_sha256)
            event('claim', {'durable': False})
            admit()
            stage = 'preflight'
            identity = self.runtime.preflight(envelope)
            current()
            if type(identity) is not RuntimeAttestation or identity != expected:
                raise SandboxError('sandbox_runtime_identity')
            event('preflight', asdict(identity))
            if cancelled() is not False:
                if had_effect:
                    terminate()
                return result('cancelled', 'sandbox_cancelled')
            if had_effect:
                state = observation(self.runtime.observe(envelope.job_id, expected))
                if state.state in {'unknown', 'absent'}:
                    return result('uncertain', 'sandbox_effect_unknown')
            else:
                admit()
                event('create_intent', {'job_id': envelope.job_id})
                had_effect, stage = True, 'create'
                state = observation(self.runtime.create(envelope, identity))
            if state.state == 'created':
                if first_start is not None:
                    terminate()
                    return result('uncertain', 'sandbox_start_unknown')
                stage = 'verify_created'
                measured = self.runtime.verify_created(envelope.job_id)
                current()
                if type(measured) is not RuntimeAttestation or measured != expected:
                    raise SandboxError('sandbox_enforcement_unverified')
                event('enforcement_verified', {'simulation': True, 'real_containment_verified': False})
                admit()
                if cancelled() is not False:
                    terminate()
                    return result('cancelled', 'sandbox_cancelled')
                started_at = tick()
                event('start_intent', {'job_id': envelope.job_id})
                stage = 'start'
                started_observation = self.runtime.start(envelope.job_id)
                stage = 'observe'  # The acknowledgement arrived; later clock failure is distinct.
                state = observation(started_observation)
            stage = 'observe'
            for _ in range(self.max_observations):
                if cancelled() is not False:
                    terminate()
                    return result('cancelled', 'sandbox_cancelled')
                elapsed = max(last_elapsed, tick() - started_at) if started_at is not None else last_elapsed
                if elapsed >= envelope.resources['wall_seconds']:
                    terminate()
                    return result('timed_out', 'sandbox_wall_limit')
                if state.state == 'stopped':
                    break
                if state.state != 'running':
                    terminate()
                    return result('uncertain', 'sandbox_effect_unknown')
                state = observation(self.runtime.observe(envelope.job_id, expected))
            else:
                terminate()
                return result('failed', 'sandbox_observation_limit')
            terminate()  # Initial process exit never proves descendant cleanup.
            if journal_failed:
                return result('uncertain', 'sandbox_journal_unavailable')
            if exit_code != 0:
                return result('failed', 'sandbox_nonzero_exit' if exit_code is not None else 'sandbox_exit_unknown')
            stage = 'collect'
            admit()
            collected = collect(envelope, self.runtime, proof)
            current()
            output_manifest = _collected_manifest(envelope, collected)
            admit()  # A collector callback cannot retain revoked private outputs.
            event('validated_outputs', {'sha256': content_sha256(output_manifest)})
            return result('simulated', 'sandbox_simulated_only')
        except Exception as error:
            reason = error.reason if isinstance(error, SandboxError) else 'sandbox_adapter_unavailable'
            if reason not in {'sandbox_admission_denied', 'sandbox_clock_invalid', 'sandbox_fence_lost',
                              'sandbox_runtime_identity', 'sandbox_runtime_observation', 'sandbox_enforcement_unverified',
                              'sandbox_output_integrity', 'sandbox_output_limit'}:
                reason = 'sandbox_adapter_unavailable'
            output_manifest = None
            if token is None:
                # A retained terminal result is never rewritten on denied read.
                return result('unavailable', reason)
            try:
                current()
            except SandboxError:
                token = None
                return result('uncertain', 'sandbox_fence_lost')
            if had_effect and stage != 'create':
                try:
                    terminate()
                except Exception:
                    proof = None
                    return result('uncertain', 'sandbox_termination_unverified')
            if stage == 'create':
                # No retry or claim of absence after a lost create acknowledgement.
                return result('uncertain', 'sandbox_effect_unknown')
            if stage == 'start':
                return result('uncertain', 'sandbox_start_unknown')
            return result('unavailable' if reason == 'sandbox_admission_denied' or not had_effect else 'failed', reason)


def _collected_manifest(envelope, collected):
    """Defensively bind the trusted byte validator's exact retained receipt."""
    try:
        if type(collected) is not ValidatedOutputs:
            raise ValueError
        files, logs, manifest = dict(collected.files), dict(collected.logs), collected.manifest
        if (manifest['version'] != 'c23-validated-outputs-v1' or manifest['authority'] != 'experimental'
                or manifest['scientific_approval'] != 'not_independently_verified'
                or set(files) != {item['name'] for item in envelope.proposal['expected_outputs']}
                or not set(logs) <= {'stdout', 'stderr'}
                or any(type(raw) is not bytes for raw in (*files.values(), *logs.values()))):
            raise ValueError
        for key, values in (('files', files), ('logs', logs)):
            descriptors = manifest[key]
            if (len(descriptors) != len(values) or [item['name'] for item in descriptors] != sorted(values)
                    or any(item['sha256'] != _hash_bytes(values[item['name']])
                           or type(item['size_bytes']) is not int or item['size_bytes'] != len(values[item['name']])
                           for item in descriptors)):
                raise ValueError
        total = sum(map(len, files.values())) + sum(map(len, logs.values())) + len(canonical_json(manifest).encode())
        if type(collected.total_bytes) is not int or collected.total_bytes != total:
            raise ValueError
        if total > envelope.resources['max_output_bytes']:
            raise SandboxError('sandbox_output_limit')
        return json.loads(canonical_json(manifest))
    except SandboxError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise SandboxError('sandbox_output_integrity') from None
