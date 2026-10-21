"""Real C22 approval bytes through C23 preparation; no Python execution."""
import hashlib
import uuid

from sqlalchemy import select

from db.app_models import ResearchExperimentReservation
from orchestration.experiment_sandbox.contracts import verify_execution_envelope
from orchestration.experiment_sandbox.files import stage_inputs, validate_outputs, verify_staged_inputs
from orchestration.experiment_sandbox.supervisor import (
    ExperimentSupervisor, MemoryExecutionJournal, SyntheticRuntime,
)
from tests.test_experiment_sandbox_contracts import approved_envelope as _retained_fixture

# Register the actual C22 service fixture in this module's pytest scope.
approved_envelope = _retained_fixture


def prepared(approved_envelope):
    raw, expected, environments, sentinel, service_fixture = approved_envelope
    envelope = verify_execution_envelope(raw, expected_envelope_sha256=expected, environments=environments)
    admissions = []
    def admit(candidate):
        retained = service_fixture.service.load_execution_envelope(
            candidate.metadata['reservation_id'], user=service_fixture.user)
        checked = verify_execution_envelope(retained, expected_envelope_sha256=expected, environments=environments)
        admissions.append(checked.envelope_sha256)
        return checked.envelope_sha256
    return envelope, sentinel, service_fixture, admissions, admit


def reservation_state(fixture, envelope):
    with fixture.factory() as session:
        return session.scalar(select(ResearchExperimentReservation.state).where(
            ResearchExperimentReservation.id == uuid.UUID(envelope.metadata['reservation_id'])))


def collector(directory, *, revoke=None):
    def collect(envelope, runtime, proof):
        assert proof.whole_process_tree_gone and proof.runtime_state_removed and proof.simulation
        files, logs = runtime.output_bytes(envelope.job_id)
        directory.mkdir(mode=0o700)
        for name, raw in files.items():
            (directory / name).write_bytes(raw)
        result = validate_outputs(directory, expected_outputs=envelope.proposal['expected_outputs'],
                                  max_output_bytes=envelope.resources['max_output_bytes'], logs=logs)
        if revoke is not None:
            revoke()
        return result
    return collect


def test_retained_service_to_stage_supervisor_and_validated_simulation(approved_envelope, tmp_path):
    envelope, sentinel, fixture, admissions, admit = prepared(approved_envelope)
    parent = tmp_path.resolve() / 'jobs'
    parent.mkdir(mode=0o700)
    staged = stage_inputs(parent, envelope)
    assert verify_staged_inputs(staged, envelope)
    assert staged.code_path.read_bytes() == envelope.code
    for name, raw in envelope.files.items():
        assert (staged.input_dir / name).read_bytes() == raw
    before = reservation_state(fixture, envelope)
    exact = b'{"columns":["value"],"rows":[[9223372036854775807],[null],["synthetic"]]}'
    runtime = SyntheticRuntime(outputs={'summary.json': exact}, logs={'stdout': b'explicit synthetic fixture\n'})
    journal = MemoryExecutionJournal()
    supervisor = ExperimentSupervisor(runtime=runtime, journal=journal)
    result = supervisor.run(envelope, admission=admit, collect=collector(tmp_path.resolve() / 'extracted'))
    document = result.document
    assert result.state == 'simulated' and document['simulation'] is True
    assert document['execution_performed'] is False and document['reservation_released'] is False
    assert document['scientific_approval'] == 'not_independently_verified'
    assert document['output_manifest']['files'][0]['sha256'] == hashlib.sha256(exact).hexdigest()
    assert document['hashes'] == envelope.metadata['hashes'] and document['seeds'] == envelope.proposal['seeds']
    assert reservation_state(fixture, envelope) == before and not sentinel.exists()
    assert len(admissions) >= 5
    calls_before_replay = list(runtime.calls)
    replay = supervisor.run(envelope, admission=admit, collect=lambda *args: (_ for _ in ()).throw(AssertionError()))
    assert replay.sha256 == result.sha256 and runtime.calls == calls_before_replay
    fixture.state['dispatch_enabled'] = False
    try:
        denied = supervisor.run(envelope, admission=admit, collect=lambda *args: None)
        assert denied.state == 'unavailable' and denied.document['output_manifest'] is None
        assert journal.completed(envelope.job_id, envelope.envelope_sha256).sha256 == result.sha256
        assert runtime.calls == calls_before_replay
    finally:
        fixture.state['dispatch_enabled'] = True


def test_disabled_current_admission_never_creates_or_collects(approved_envelope):
    envelope, sentinel, fixture, _, admit = prepared(approved_envelope)
    runtime = SyntheticRuntime()
    fixture.state['dispatch_enabled'] = False
    try:
        result = ExperimentSupervisor(runtime=runtime, journal=MemoryExecutionJournal()).run(
            envelope, admission=admit, collect=lambda *args: (_ for _ in ()).throw(AssertionError()))
        assert result.state == 'unavailable' and runtime.calls == [] and not sentinel.exists()
        assert result.document['reservation_released'] is False
    finally:
        fixture.state['dispatch_enabled'] = True


def test_collector_cannot_publish_after_current_admission_revoked(approved_envelope, tmp_path):
    envelope, sentinel, fixture, _, admit = prepared(approved_envelope)
    runtime = SyntheticRuntime(outputs={'summary.json': b'{"columns":["synthetic"],"rows":[]}'})
    collect = collector(tmp_path.resolve() / 'revoked-extracted',
                        revoke=lambda: fixture.state.update(dispatch_enabled=False))
    try:
        result = ExperimentSupervisor(runtime=runtime, journal=MemoryExecutionJournal()).run(
            envelope, admission=admit, collect=collect)
        assert result.state in {'failed', 'unavailable'}
        assert result.document['output_manifest'] is None
        assert result.document['termination']['whole_process_tree_gone'] is True
        assert result.document['reservation_released'] is False and not sentinel.exists()
    finally:
        fixture.state['dispatch_enabled'] = True
