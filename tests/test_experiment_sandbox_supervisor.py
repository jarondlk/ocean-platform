"""C23 simulations over an actual C22 envelope; no generated code executes."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event

from db.app_models import AppBase
from orchestration.experiment_sandbox.contracts import SandboxError, verify_execution_envelope
from orchestration.experiment_sandbox.files import ValidatedOutputs, validate_outputs
from orchestration.experiment_sandbox.supervisor import (
    ExperimentSupervisor, JournalToken, MemoryExecutionJournal, RuntimeObservation,
    SupervisorResult, SyntheticRuntime, TerminationProof, synthetic_identity,
)
from schema.context_catalogue import canonical_json
from schema.research_experiments import content_sha256
from tests.research_experiment_support import make_experiment_fixture


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp('c23-supervisor')
    sentinel = root / 'generated-code-must-not-run'
    engine = create_engine('sqlite+pysqlite:///' + str(root / 'app.sqlite'))

    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

    with patch.dict(os.environ, {'ENABLE_V1_CATALOGUE': 'true', 'ENABLE_V1_INVESTIGATIONS': 'true'}):
        AppBase.metadata.create_all(engine)
        actual = make_experiment_fixture(engine, root)
        request = actual.request()
        request['proposal']['python_code'] = f'from pathlib import Path\nPath({str(sentinel)!r}).write_text("executed")\n'
        experiment = actual.service.invoke('create', request, actual.user)['experiment']
        experiment = actual.service.invoke('approve', actual.decision(experiment), actual.user)['experiment']
        experiment = actual.service.invoke('dispatch', actual.decision(experiment), actual.user)['experiment']
        raw = actual.service.load_execution_envelope(experiment['dispatch']['reservation_id'], user=actual.user)
        verified = verify_execution_envelope(raw, expected_envelope_sha256=content_sha256(raw['metadata']),
            environments=actual.service.environments)
        yield verified, sentinel
    engine.dispose()


@pytest.fixture
def envelope(prepared):
    return prepared[0]


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def collected(files=None, logs=None):
    files = files if files is not None else {'summary.json': b'{"columns":["synthetic"],"rows":[[1]]}'}
    with TemporaryDirectory(prefix='c23-validated-') as directory:
        for name, value in files.items():
            Path(directory, name).write_bytes(value)
        expected = [{'name': name, 'kind': 'table', 'description': 'Synthetic fixture'} for name in sorted(files)]
        return validate_outputs(Path(directory).resolve(), expected_outputs=expected, max_output_bytes=50 * 1024 * 1024, logs=logs)


def damaged_collection(valid, files, logs, manifest, total):
    value = object.__new__(ValidatedOutputs)  # Deliberate post-validation tampering probe.
    for key, item in {'_files': MappingProxyType(files), '_logs': MappingProxyType(logs),
                      '_manifest_json': canonical_json(manifest).encode(), 'total_bytes': total}.items():
        object.__setattr__(value, key, item)
    return value


def run(envelope, *, runtime=None, journal=None, clock=None, admission=None, cancelled=None, collect=None, **kwargs):
    runtime = runtime or SyntheticRuntime()
    journal = journal or MemoryExecutionJournal()
    supervisor = ExperimentSupervisor(runtime=runtime, journal=journal, clock=clock or Clock(), **kwargs)
    result = supervisor.run(envelope, admission=admission or (lambda value: value.envelope_sha256),
        cancelled=cancelled or (lambda: False), collect=collect or (lambda *_: collected()))
    return result, runtime, journal


def test_actual_c22_envelope_simulates_with_exact_identity_and_inert_python(prepared):
    envelope, sentinel = prepared
    result, runtime, journal = run(envelope)
    document = result.document
    assert result.state == 'simulated'
    assert document['simulation'] is True and document['execution_performed'] is False
    assert document['reservation_released'] is False and document['scientific_approval'] == 'not_independently_verified'
    assert document['hashes'] == envelope.metadata['hashes']
    assert document['environment'] == envelope.environment and document['seeds'] == envelope.proposal['seeds']
    assert document['resources'] == envelope.resources and document['envelope_sha256'] == envelope.envelope_sha256
    assert document['termination']['whole_process_tree_gone'] is True
    assert document['termination']['simulation'] is True and document['runtime']['containment_verified'] is False
    assert [action for action, _ in runtime.calls] == ['preflight', 'create', 'verify_created', 'start', 'observe', 'terminate']
    assert not sentinel.exists()
    kinds = [item.kind for item in journal.events(envelope.job_id)]
    assert kinds.index('create_intent') < kinds.index('start_intent') < kinds.index('terminated') < kinds.index('validated_outputs')
    assert document['output_manifest']['files'][0]['name'] == 'summary.json'
    document['resources']['cpus'] = 999
    assert result.document['resources']['cpus'] == envelope.resources['cpus']


def test_terminal_redelivery_is_immutable_and_checks_current_admission(envelope):
    first, runtime, journal = run(envelope)
    calls = list(runtime.calls)
    repeated, _, _ = run(envelope, runtime=runtime, journal=journal)
    assert repeated.sha256 == first.sha256 and runtime.calls == calls
    denied, _, _ = run(envelope, runtime=runtime, journal=journal, admission=lambda _: None)
    assert denied.state == 'unavailable' and denied.document['output_manifest'] is None
    assert journal.completed(envelope.job_id, envelope.envelope_sha256).sha256 == first.sha256


@pytest.mark.parametrize('decision', [True, False, None, '0' * 64])
def test_admission_boolean_or_wrong_hash_never_reaches_runtime(envelope, decision):
    result, runtime, _ = run(envelope, admission=lambda _: decision)
    assert result.state == 'unavailable' and result.document['reason'] == 'sandbox_admission_denied'
    assert runtime.calls == [] and result.document['output_manifest'] is None


def test_lost_create_ack_reconciles_same_job_without_duplicate_create(envelope):
    runtime, journal = SyntheticRuntime(lose_ack=['create']), MemoryExecutionJournal()
    first, _, _ = run(envelope, runtime=runtime, journal=journal)
    assert first.state == 'uncertain' and first.document['reservation_released'] is False
    assert journal.completed(envelope.job_id, envelope.envelope_sha256) is None
    second, _, _ = run(envelope, runtime=runtime, journal=journal)
    assert second.state == 'simulated'
    assert [name for name, _ in runtime.calls].count('create') == 1
    assert [name for name, _ in runtime.calls].count('start') == 1
    assert second.document['journal_epoch'] > first.document['journal_epoch']


def test_lost_start_ack_is_uncertain_and_never_restarts(envelope):
    runtime, journal = SyntheticRuntime(lose_ack=['start']), MemoryExecutionJournal()
    first, _, _ = run(envelope, runtime=runtime, journal=journal)
    assert first.state == 'uncertain' and first.document['reason'] == 'sandbox_start_unknown'
    assert first.document['termination']['whole_process_tree_gone'] is True
    second, _, _ = run(envelope, runtime=runtime, journal=journal)
    assert second.state == 'failed'
    assert [name for name, _ in runtime.calls].count('start') == 1
    assert second.document['reservation_released'] is False


def test_lost_effect_with_missing_runtime_state_never_creates_again(envelope):
    runtime, journal = SyntheticRuntime(lose_ack=['create']), MemoryExecutionJournal()
    run(envelope, runtime=runtime, journal=journal)
    runtime._jobs.clear()  # Losing metadata is not whole-job termination proof.
    result, _, _ = run(envelope, runtime=runtime, journal=journal)
    assert result.state == 'uncertain' and result.document['termination'] is None
    assert [name for name, _ in runtime.calls].count('create') == 1
    assert not any(name == 'start' for name, _ in runtime.calls)


def test_initial_exit_is_not_whole_process_tree_cleanup(envelope):
    runtime, did_collect = SyntheticRuntime(termination_succeeds=False), []
    result, _, _ = run(envelope, runtime=runtime, collect=lambda *_: did_collect.append(True))
    assert result.state == 'uncertain' and result.document['termination'] is None
    assert did_collect == [] and result.document['reservation_released'] is False
    with pytest.raises(SandboxError, match='termination_unverified'):
        runtime.output_bytes(envelope.job_id)


def test_cancellation_cleans_whole_tree_before_any_output(envelope):
    runtime, did_collect = SyntheticRuntime(observations=[('running', 1.0, None)]), []
    result, _, _ = run(envelope, runtime=runtime,
        cancelled=lambda: any(action == 'start' for action, _ in runtime.calls),
        collect=lambda *_: did_collect.append(True))
    assert result.state == 'cancelled' and result.document['termination']['whole_process_tree_gone'] is True
    assert did_collect == [] and result.document['reservation_released'] is False


def test_revocation_after_create_cannot_block_cleanup_or_allow_start(envelope):
    runtime = SyntheticRuntime()
    def admission(value):
        return None if any(action == 'create' for action, _ in runtime.calls) else value.envelope_sha256
    result, _, _ = run(envelope, runtime=runtime, admission=admission)
    assert result.state == 'unavailable' and result.document['termination']['whole_process_tree_gone'] is True
    assert 'start' not in [action for action, _ in runtime.calls]


def test_revocation_during_collection_discards_private_manifest(envelope):
    allowed = [True]
    def collect(*_):
        allowed[0] = False
        return collected()
    result, runtime, _ = run(envelope, collect=collect,
        admission=lambda value: value.envelope_sha256 if allowed[0] else None)
    assert result.state == 'unavailable' and result.document['output_manifest'] is None
    assert result.document['termination']['whole_process_tree_gone'] is True
    assert any(name == 'terminate' for name, _ in runtime.calls)


@pytest.mark.parametrize('after_start', [float('nan'), float('inf'), -1.0, 99.0, 10**10000],
                         ids=['nan', 'infinity', 'negative', 'rollback', 'huge_integer'])
def test_invalid_or_backwards_clock_after_start_still_cleans_up(envelope, after_start):
    clock = Clock()
    class ClockRuntime(SyntheticRuntime):
        def start(self, job_id):
            value = super().start(job_id)
            clock.now = after_start
            return value
    result, _, _ = run(envelope, runtime=ClockRuntime(), clock=clock)
    assert result.state == 'failed' and result.document['reason'] == 'sandbox_clock_invalid'
    assert result.document['termination']['whole_process_tree_gone'] is True


@pytest.mark.parametrize('initial', [float('nan'), float('inf'), -1.0, True, 10**10000],
                         ids=['nan', 'infinity', 'negative', 'boolean', 'huge_integer'])
def test_invalid_initial_clock_refuses_before_any_effect(envelope, initial):
    runtime = SyntheticRuntime()
    with pytest.raises(SandboxError, match='clock_invalid'):
        run(envelope, runtime=runtime, clock=lambda: initial)
    assert runtime.calls == []


def test_timeout_uses_elapsed_observation_and_cleans_descendants(envelope):
    runtime = SyntheticRuntime(observations=[('running', envelope.resources['wall_seconds'], None)])
    result, _, _ = run(envelope, runtime=runtime)
    assert result.state == 'timed_out' and result.document['termination']['whole_process_tree_gone'] is True
    assert result.document['output_manifest'] is None


def test_decreasing_runtime_elapsed_is_not_accepted(envelope):
    runtime = SyntheticRuntime(observations=[('running', 2.0, None), ('stopped', 1.0, 0)])
    result, _, _ = run(envelope, runtime=runtime)
    assert result.state == 'failed' and result.document['reason'] == 'sandbox_runtime_observation'
    assert result.document['termination']['whole_process_tree_gone'] is True


def test_wrong_resource_profile_never_starts(envelope):
    class WrongProfile(SyntheticRuntime):
        def verify_created(self, job_id):
            return replace(super().verify_created(job_id), resources_sha256='f' * 64)
    result, runtime, _ = run(envelope, runtime=WrongProfile())
    assert result.state == 'failed' and result.document['reason'] == 'sandbox_enforcement_unverified'
    assert not any(action == 'start' for action, _ in runtime.calls)
    assert result.document['termination']['whole_process_tree_gone'] is True


def test_wrong_observation_hash_requires_cleanup(envelope):
    class WrongObservation(SyntheticRuntime):
        def observe(self, job_id, identity):
            return replace(super().observe(job_id, identity), identity=replace(identity, envelope_sha256='e' * 64))
    result, _, _ = run(envelope, runtime=WrongObservation())
    assert result.state == 'failed' and result.document['termination']['whole_process_tree_gone'] is True


def test_wrong_termination_identity_keeps_uncertain(envelope):
    class WrongProof(SyntheticRuntime):
        def terminate_and_prove(self, job_id, identity):
            return TerminationProof(replace(identity, profile_sha256='d' * 64), True, True)
    result, _, _ = run(envelope, runtime=WrongProof())
    assert result.state == 'uncertain' and result.document['termination'] is None
    assert result.document['output_manifest'] is None


def test_stale_epoch_cannot_publish_a_result(envelope):
    journal = MemoryExecutionJournal()
    def collect(*_):
        journal.claim(envelope.job_id, envelope.envelope_sha256)
        return collected()
    result, _, _ = run(envelope, journal=journal, collect=collect)
    assert result.state == 'uncertain' and result.document['reason'] == 'sandbox_fence_lost'
    assert journal.completed(envelope.job_id, envelope.envelope_sha256) is None
    assert result.document['output_manifest'] is None


def test_journal_hash_chain_and_stale_claim_fence(envelope):
    journal = MemoryExecutionJournal()
    old = journal.claim(envelope.job_id, envelope.envelope_sha256)
    first = journal.append(old, 'prepared', 1.0, {'exact': 17})
    current = journal.claim(envelope.job_id, envelope.envelope_sha256)
    with pytest.raises(SandboxError, match='fence_lost'):
        journal.append(old, 'stale', 2.0, {})
    second = journal.append(current, 'observed', 2.0, {})
    assert second.previous_sha256 == first.sha256 and first.payload['exact'] == 17
    changed = first.payload
    changed['exact'] = 0
    assert first.payload['exact'] == 17 and journal.events(envelope.job_id) == (first, second)
    with pytest.raises(SandboxError, match='journal_identity'):
        journal.claim(envelope.job_id, 'f' * 64)
    with pytest.raises(SandboxError, match='journal_integrity'):
        journal.append(current, 'rollback', 1.0, {})


@pytest.mark.parametrize('damage', ['hash', 'size', 'extra', 'count', 'authority', 'logs'])
def test_tampered_validated_output_receipt_cannot_be_published(envelope, damage):
    valid = collected()
    manifest = deepcopy(valid.manifest)
    files, logs, total = dict(valid.files), dict(valid.logs), valid.total_bytes
    if damage == 'hash':
        manifest['files'][0]['sha256'] = '0' * 64
    elif damage == 'size':
        manifest['files'][0]['size_bytes'] += 1
    elif damage == 'extra':
        files['extra.html'] = b'<html>unsafe</html>'
    elif damage == 'count':
        total += 1
    elif damage == 'authority':
        manifest['authority'] = 'published'
    else:
        logs['credentials'] = b'not an allowed stream'
    corrupt = damaged_collection(valid, files, logs, manifest, total)
    result, _, _ = run(envelope, collect=lambda *_: corrupt)
    assert result.state == 'failed' and result.document['reason'] == 'sandbox_output_integrity'
    assert result.document['output_manifest'] is None


def test_ducktyped_fake_validation_receipt_is_refused(envelope):
    class Forged:
        files = {'summary.json': b'not validated'}
        logs = {}
        manifest = {}
        total_bytes = 1
    result, _, _ = run(envelope, collect=lambda *_: Forged())
    assert result.state == 'failed' and result.document['reason'] == 'sandbox_output_integrity'


def test_collector_exception_is_safe_and_never_reports_success(envelope):
    def collect(*_):
        raise RuntimeError('secret host path must not escape')
    result, _, _ = run(envelope, collect=collect)
    assert result.state == 'failed' and result.document['reason'] == 'sandbox_adapter_unavailable'
    assert 'secret' not in canonical_json(result.document)


def test_no_unbounded_observation_loop(envelope):
    result, runtime, _ = run(envelope, runtime=SyntheticRuntime(observations=[]), max_observations=2)
    assert result.state == 'failed' and result.document['reason'] == 'sandbox_observation_limit'
    assert [name for name, _ in runtime.calls].count('observe') == 2
    assert result.document['termination']['whole_process_tree_gone'] is True


def test_nonzero_exit_has_no_oom_inference_or_outputs(envelope):
    result, _, _ = run(envelope, runtime=SyntheticRuntime(observations=[('stopped', 1.0, 137)]))
    assert result.state == 'failed' and result.document['reason'] == 'sandbox_nonzero_exit'
    assert result.document['exit_code'] == 137 and result.document['output_manifest'] is None
    assert 'oom' not in canonical_json(result.document)


def test_real_runtime_shape_and_environment_upgrade_are_refused(envelope):
    class OrdinaryHostRuntime:
        simulation = False
    with pytest.raises(SandboxError, match='real_runtime_unavailable'):
        ExperimentSupervisor(runtime=OrdinaryHostRuntime(), journal=MemoryExecutionJournal())
    changed = object.__new__(type(envelope))
    metadata = envelope.metadata
    metadata['environment']['kind'] = 'linux-gvisor'
    for name, value in {'_metadata_json': json.dumps(metadata), '_files': envelope.files,
                        'envelope_sha256': content_sha256(metadata), 'job_id': envelope.job_id}.items():
        object.__setattr__(changed, name, value)
    runtime = SyntheticRuntime()
    with pytest.raises(SandboxError, match='real_runtime_unavailable'):
        run(changed, runtime=runtime)
    assert runtime.calls == []


@pytest.mark.parametrize('elapsed', [float('nan'), -1.0, True, 10**10000],
                         ids=['nan', 'negative', 'boolean', 'huge_integer'])
def test_observation_dtos_reject_invalid_runtime_values(envelope, elapsed):
    with pytest.raises(SandboxError, match='runtime_observation'):
        RuntimeObservation(synthetic_identity(envelope), 'running', elapsed)


def test_dtos_reject_unhashable_states_and_unknown_real_claims(envelope):
    with pytest.raises(SandboxError, match='runtime_observation'):
        RuntimeObservation(synthetic_identity(envelope), [])
    with pytest.raises(SandboxError, match='result_identity'):
        SupervisorResult({'state': []})
    result, _, _ = run(envelope)
    for field in ('execution_performed', 'reservation_released'):
        document = result.document
        document[field] = True
        with pytest.raises(SandboxError, match='result_identity'):
            SupervisorResult(document)


@pytest.mark.parametrize(('field', 'bad'), [
    ('job_id', None), ('job_id', []), ('job_id', b'c23-' + b'a' * 48),
    ('job_id', 'c23-' + 'A' * 48), ('job_id', 'c23-' + 'a' * 47),
    ('envelope_sha256', None), ('envelope_sha256', []), ('envelope_sha256', True),
    ('envelope_sha256', 'A' * 64), ('envelope_sha256', 'a' * 63),
    ('epoch', True), ('epoch', False), ('epoch', 0), ('epoch', -1),
    ('epoch', 1.0), ('epoch', '1'), ('epoch', None), ('epoch', []),
    ('epoch', 2**63),
], ids=['job-none', 'job-list', 'job-bytes', 'job-uppercase', 'job-length',
        'hash-none', 'hash-list', 'hash-bool', 'hash-uppercase', 'hash-length',
        'epoch-true', 'epoch-false', 'epoch-zero', 'epoch-negative', 'epoch-float',
        'epoch-string', 'epoch-none', 'epoch-list', 'epoch-overflow'])
def test_journal_token_rejects_malformed_identifiers_and_epochs(envelope, field, bad):
    values = {'job_id': envelope.job_id, 'envelope_sha256': envelope.envelope_sha256, 'epoch': 1}
    values[field] = bad
    with pytest.raises(SandboxError, match='sandbox_journal_identity'):
        JournalToken(**values)


def test_journal_token_boundary_and_claim_saturation(envelope):
    journal = MemoryExecutionJournal()
    token = journal.claim(envelope.job_id, envelope.envelope_sha256)
    assert token == JournalToken(envelope.job_id, envelope.envelope_sha256, 1)
    assert JournalToken(envelope.job_id, envelope.envelope_sha256, 2**63 - 1).epoch == 2**63 - 1
    journal._jobs[envelope.job_id]['epoch'] = 2**63 - 1  # Explicit bounded-state saturation fixture.
    with pytest.raises(SandboxError, match='sandbox_journal_limit'):
        journal.claim(envelope.job_id, envelope.envelope_sha256)
    assert journal._jobs[envelope.job_id]['epoch'] == 2**63 - 1


def test_journal_rejects_ducktyped_lease(envelope):
    journal = MemoryExecutionJournal()
    token = journal.claim(envelope.job_id, envelope.envelope_sha256)
    class DuckToken:
        job_id = token.job_id
        envelope_sha256 = token.envelope_sha256
        epoch = True
    with pytest.raises(SandboxError, match='sandbox_journal_identity'):
        journal.require_current(DuckToken())


@pytest.mark.parametrize('failed_kind', ['terminate_intent', 'terminated'])
def test_journal_cleanup_write_failure_still_terminates_without_publication(envelope, failed_kind):
    class BrokenJournal(MemoryExecutionJournal):
        def append(self, token, kind, at, payload):
            if kind == failed_kind:
                raise OSError('unavailable private journal path')
            return super().append(token, kind, at, payload)
    journal, did_collect = BrokenJournal(), []
    result, runtime, _ = run(envelope, journal=journal, collect=lambda *_: did_collect.append(True))
    assert result.state == 'uncertain' and result.document['reason'] == 'sandbox_journal_unavailable'
    assert result.document['termination']['whole_process_tree_gone'] is True
    assert result.document['journal_recording_complete'] is False
    assert result.document['reservation_released'] is False and result.document['output_manifest'] is None
    assert any(action == 'terminate' for action, _ in runtime.calls)
    assert did_collect == [] and journal.completed(envelope.job_id, envelope.envelope_sha256) is None


def test_journal_limit_after_start_cannot_prevent_best_effort_cleanup(envelope):
    class LimitedJournal(MemoryExecutionJournal):
        def append(self, token, kind, at, payload):
            if any(event.kind == 'start_intent' for event in self.events(token.job_id)):
                raise SandboxError('sandbox_journal_limit')
            return super().append(token, kind, at, payload)
    journal = LimitedJournal()
    result, runtime, _ = run(envelope, journal=journal, collect=lambda *_: (_ for _ in ()).throw(AssertionError()))
    assert result.state == 'uncertain' and result.document['reason'] == 'sandbox_journal_unavailable'
    assert result.document['termination']['whole_process_tree_gone'] is True
    assert result.document['output_manifest'] is None and result.document['reservation_released'] is False
    assert [action for action, _ in runtime.calls].count('terminate') == 1
    assert journal.completed(envelope.job_id, envelope.envelope_sha256) is None


def test_journal_result_write_failure_discards_validated_manifest(envelope):
    class BrokenResultJournal(MemoryExecutionJournal):
        def append(self, token, kind, at, payload):
            if kind == 'result':
                raise OSError('result path unavailable')
            return super().append(token, kind, at, payload)
    journal = BrokenResultJournal()
    result, _, _ = run(envelope, journal=journal)
    assert result.state == 'uncertain' and result.document['journal_recording_complete'] is False
    assert result.document['output_manifest'] is None and result.document['reservation_released'] is False
    assert journal.completed(envelope.job_id, envelope.envelope_sha256) is None


def test_failed_journal_cleanup_record_does_not_override_lost_fence(envelope):
    class LostFenceJournal(MemoryExecutionJournal):
        def append(self, token, kind, at, payload):
            if kind == 'terminate_intent':
                self.claim(token.job_id, token.envelope_sha256)
                raise OSError('append failed during forced failover')
            return super().append(token, kind, at, payload)
    journal = LostFenceJournal()
    result, runtime, _ = run(envelope, journal=journal)
    assert result.state == 'uncertain' and result.document['termination'] is None
    assert result.document['output_manifest'] is None and result.document['reservation_released'] is False
    assert not any(action == 'terminate' for action, _ in runtime.calls)
    assert journal.completed(envelope.job_id, envelope.envelope_sha256) is None


def test_cancel_cleanup_continues_after_journal_write_failure(envelope):
    class BrokenJournal(MemoryExecutionJournal):
        def append(self, token, kind, at, payload):
            if kind in {'terminate_intent', 'terminated', 'result'}:
                raise OSError('journal unavailable')
            return super().append(token, kind, at, payload)
    runtime, journal = SyntheticRuntime(), BrokenJournal()
    result, _, _ = run(envelope, runtime=runtime, journal=journal,
        cancelled=lambda: any(action == 'start' for action, _ in runtime.calls))
    assert result.state == 'uncertain' and result.document['reason'] == 'sandbox_journal_unavailable'
    assert result.document['termination']['whole_process_tree_gone'] is True
    assert result.document['output_manifest'] is None and result.document['reservation_released'] is False
    assert journal.completed(envelope.job_id, envelope.envelope_sha256) is None

