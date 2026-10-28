"""Real C22/PG admission with inert runtime and explicitly synthetic signatures.

No generated Python, Linux runtime, cgroup or physical issuer executes here.
These tests cannot clear the separate actual retained GCP execution gate.
"""
from contextlib import contextmanager
import hashlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import text

from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.journal import _safe_sqlite_version
from orchestration.experiment_sandbox.proofs import canonical_packet_bytes, sign_termination_claims
from orchestration.research_experiments import ResearchExperimentError
from schema.experiment_execution import TerminationClaims
from schema.research_experiments import content_sha256
from tests import experiment_execution_postgres_support as pg
from tests.integration import test_retained_reserve_postgres as reserve_tests
from tests.retained_admission_support import configured_native

pytestmark = pytest.mark.skipif(os.environ.get('RUN_C23_POSTGRES_INTEGRATION') != '1',
    reason='Explicit owned C23 PostgreSQL required; starts no service')
disposable_database, isolated, role_database = pg.disposable_database, pg.isolated, pg.role_database
retained = reserve_tests.retained


@pytest.fixture
def case(tmp_path, monkeypatch, request):
    if not _safe_sqlite_version(sqlite3.sqlite_version_info):
        pytest.skip('Actual retained-admission journal tests require SQLite with the WAL-reset fix')
    value = configured_native(request.getfixturevalue('retained'), tmp_path, monkeypatch)
    try:
        yield value
    finally:
        value.journal.close()


def start(case, context):
    case.hooks.admit_preparation(context)
    context.lease.append('create_intent', {'synthetic_software_only': True})
    context.lease.append('enforcement_verified', {'synthetic_software_only': True})
    permit = case.hooks.admit_start(context)
    payload = permit.consume(context)
    context.lease.append('start_intent', payload)
    with pytest.raises(SandboxError):
        permit.consume(context)
    return payload


def finish(case, context):
    cleanup = context.lease.append('cleanup_intent', {'synthetic_software_only': True})
    termination = context.lease.append('termination_observed', {'synthetic_software_only': True})
    outputs = context.adapter._retain_outputs(case.job, context.envelope, {
        'files': {'summary.json': b'{"columns":["value"],"rows":[[42]]}'},
        'logs': {'stdout': b'literal software fixture; no analysis ran', 'stderr': b''}})
    record = context.adapter._record(context.envelope, context.profile,
        content_sha256(json.loads(context.runtime_json)), state='completed',
        reason='synthetic_software_only', outputs=outputs)
    record.update(simulation=True, execution_started=False, start_attempted=False)
    context.lease.finish(record)
    return context.journal.terminal_reference(context.lease), outputs, cleanup, termination


def synthetic_packet(case, context, binding, terminal, cleanup, termination):
    create = next(event for event in context.require_current().events if event.kind == 'create_intent')
    digest = hashlib.sha256(b'explicit synthetic software witness, not native facts').hexdigest()
    claims = TerminationClaims.model_validate({'binding': binding,
        'journal': {'create_intent_sequence': create.sequence, 'create_intent_sha256': create.sha256,
            'cleanup_intent_sequence': cleanup.sequence, 'cleanup_intent_sha256': cleanup.sha256,
            'termination_sequence': termination.sequence, 'termination_sha256': termination.sha256,
            'terminal_sequence': terminal.terminal_sequence,
            'terminal_head_sha256': terminal.terminal_head_sha256,
            'terminal_result_sha256': terminal.terminal_result_sha256},
        'kernel': {'cgroup_path': '/ocean-c23/' + context.job_id, 'cgroup_device': 0,
            'cgroup_inode': 1, 'populated': 0, 'delete_exit_code': 0,
            'delete_job_id': context.job_id, 'delete_runtime_sha256': binding.runtime_sha256,
            'delete_host_boot_id': context.host_boot_id, 'delete_command_sha256': digest,
            'delete_acknowledgement_sha256': digest, 'raw_observation_sha256': digest,
            'cleanup_started_monotonic_ns': cleanup.monotonic_ns,
            'delete_acknowledged_monotonic_ns': termination.monotonic_ns,
            'populated_zero_monotonic_ns': termination.monotonic_ns,
            'terminal_recorded_monotonic_ns': terminal.terminal_recorded_monotonic_ns,
            'issued_monotonic_ns': terminal.terminal_recorded_monotonic_ns}})
    return canonical_packet_bytes(sign_termination_claims(claims, issuer_id='synthetic-admission',
        key_id='ephemeral-admission', trust_scope='synthetic-software-test', private_key=case.key))


@pytest.mark.parametrize('revoked', [False, True])
def test_actual_admission_publication_or_revocation_then_independent_close_and_release(case, revoked):
    with case.hold() as context:
        payload = start(case, context)
        assert payload['start_fence'] == 2 and payload['start_id'] == payload['start_event_id']
        terminal, outputs, cleanup, termination = finish(case, context)
        if revoked:
            case.native.fixture.state['enabled'] = False
            with case.native.fixture.factory.begin() as session:
                session.execute(text("UPDATE app_user SET status='suspended' WHERE id=:id"),
                    {'id': case.native.fixture.user.id})
            with pytest.raises((ResearchExperimentError, SandboxError)):
                case.hooks.admit_publication(context, terminal, hashlib.sha256(outputs.manifest_bytes).hexdigest())
        else:
            publication = case.hooks.admit_publication(context, terminal, hashlib.sha256(outputs.manifest_bytes).hexdigest())
            assert publication.document['publication_retained'] is True
        closed = case.hooks.close_execution(context, terminal)
        assert case.hooks.close_execution(context, terminal) == closed
        packet = synthetic_packet(case, context, closed, terminal, cleanup, termination)
        proof = case.hooks.record_termination(context, packet)
        release = case.hooks.release_terminated(context, proof, closed.closed_fence)
        assert case.hooks.record_termination(context, packet) == proof
        assert case.hooks.release_terminated(context, proof, closed.closed_fence) == release
        with case.native.database['engine'].connect() as connection:
            assert connection.scalar(text('SELECT state FROM research_experiment_reservation')) == 'released'
            assert connection.scalar(text('SELECT count(*) FROM research_experiment_release')) == 1


def test_commit_ack_loss_never_mints_or_retries_a_start(case, monkeypatch):
    with case.hold() as context:
        case.hooks.admit_preparation(context)
        original = case.store.controller_transaction

        @contextmanager
        def lost_ack(*, cleanup=False):
            with original(cleanup=cleanup) as session:
                yield session
            if not cleanup:
                with case.native.database['engine'].connect() as connection:
                    state = connection.scalar(text('SELECT state FROM research_experiment_execution_state'))
                if state == 'start_consumed':
                    raise OSError('Synthetic committed transaction acknowledgement loss')

        monkeypatch.setattr(case.store, 'controller_transaction', lost_ack)
        with pytest.raises(OSError, match='acknowledgement'):
            case.hooks.admit_start(context)
        with pytest.raises(SandboxError):
            case.hooks.admit_start(context)
        assert not any(event.kind == 'start_intent' for event in context.require_current().events)
        with case.native.database['engine'].connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM research_experiment_execution_event')) == 1


def test_missing_internal_owner_execution_fails_before_admission(case):
    database = case.native.database
    with database['engine'].begin() as connection:
        owner = database['roles'].function_owner_role
        connection.exec_driver_sql(f'REVOKE EXECUTE ON FUNCTION {database["schema"]}.ocean_c23_closed_binding(uuid) FROM {owner}')
    with case.hold() as context, pytest.raises(SandboxError, match='role_boundary'):
        case.hooks.admit_preparation(context)
