"""Host-safe reserve bridge composition; SQLite is not a native role boundary."""
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
import json
import uuid

import pytest
from sqlalchemy import text

from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.execution_store import C23ExecutionStore
from orchestration.experiment_sandbox.retained_bridge import (
    C23RetainedBridge, RetainedExecutionIdentity, RetainedMaterialPolicy,
)
from orchestration.research_experiments import ResearchExperimentError
from tests.retained_reserve_support import bridge as configured, material
from tests.test_experiment_sandbox_operator_inspection import operator_store, case

__all__ = ['operator_store', 'case']


@pytest.fixture
def reserved(case, monkeypatch):
    value = configured(case.fixture)
    calls, sessions = [], []
    # Software composition only. Native tests exercise actual PG role checks.
    monkeypatch.setattr(value.store, '_check_session', lambda *_: None)
    original_transaction = value.store.controller_transaction
    @contextmanager
    def transaction(**kwargs):
        with original_transaction(**kwargs) as session:
            sessions.append(session)
            original_scalar = session.scalar
            def scalar(statement, parameters=None, **options):
                if 'ocean_c23_reserve' in str(statement):
                    payload = json.loads(parameters['p'])
                    calls.append(payload)
                    return payload['execution_id']
                if 'research_experiment_release' in str(statement):
                    return False  # PostgreSQL EXISTS is bool; SQLite returns int.
                return original_scalar(statement, parameters, **options)
            monkeypatch.setattr(session, 'scalar', scalar)
            yield session
    monkeypatch.setattr(value.store, 'controller_transaction', transaction)
    return value, calls, sessions


def request(case, **changes):
    return {**case.request, 'idempotency_key': str(uuid.uuid4()), **changes}


def test_reserve_returns_detached_private_non_execution_identity(case, reserved):
    value, calls, _ = reserved
    req = request(case)
    result = value.reserve(req, current_owner=case.fixture.user)
    assert len(calls) == 1 and calls[0]['approval_id'] == result.document['approval_id']
    assert result.document['capacity_reserved_at_commit'] is True
    assert result.document['capacity_snapshot_only'] is True
    assert result.execution_authorized is result.reservation_release_authorized is False
    assert result.scientific_approval == 'not_independently_verified'
    assert result.document['publication_authorized'] is False
    assert value.reserve(req, current_owner=case.fixture.user).document == result.document
    assert len(calls) == 2 and calls[0] == calls[1]
    envelope = json.loads(calls[0]['envelope_json'])
    assert envelope['environment']['kind'] == 'linux-gvisor'
    assert envelope['reservation_id'] == result.document['reservation_id']
    assert envelope['approval_id'] == calls[0]['approval_id']
    assert envelope['scientific_approval'] == 'not_independently_verified'
    result.document['job_id'] = 'changed'
    assert result.document['job_id'] != 'changed'
    with pytest.raises(TypeError):
        RetainedExecutionIdentity()
    with pytest.raises(FrozenInstanceError):
        result._json = '{}'
    assert not case.sentinel.exists() and case.fixture.executor.deliveries == []


def test_disabled_bridge_never_reaches_inspection_or_store(case, monkeypatch):
    value = configured(case.fixture, enabled=lambda: False)
    monkeypatch.setattr(value.inspection, 'inspect_approved', lambda *_a, **_k: pytest.fail('disabled read'))
    with pytest.raises(SandboxError, match='disabled'):
        value.reserve(request(case), current_owner=case.fixture.user)


def test_factory_or_site_mismatch_refuses_without_admin_substitution(case):
    value = configured(case.fixture)
    value.store.config = replace(value.store.config, controller_session_factory=lambda: None)
    with pytest.raises(ValueError, match='exact restricted'):
        value.reserve(request(case), current_owner=case.fixture.user)
    with pytest.raises(ValueError):
        C23RetainedBridge(inspection=value.inspection, store=value.store,
            material_policy=material(case.fixture), enabled=lambda: True)


@pytest.mark.parametrize('field', ['environment_sha256', 'image_digest'])
def test_material_policy_cannot_promote_an_unmatched_registry(case, field):
    data = material(case.fixture).model_dump()
    data[field] = ('sha256:' if field == 'image_digest' else '') + 'f' * 64
    original = configured(case.fixture)
    value = C23RetainedBridge(inspection=original.inspection, store=original.store,
        material_policy=RetainedMaterialPolicy.model_validate(data), enabled=lambda: True)
    with pytest.raises(SandboxError, match='material_identity'):
        value.reserve(request(case), current_owner=case.fixture.user)


@pytest.mark.parametrize('mutation', ['owner', 'context', 'proposal', 'factory', 'flag', 'source', 'approval'])
def test_last_store_enable_callback_cannot_cross_closing_authority_fence(case, reserved, mutation):
    value, calls, sessions = reserved
    original_factory = value._service.session_factory
    touched = []
    def enabled():
        # Entry enablement precedes a session; _controller's last callback runs
        # with the final session already holding the normal C22 authority locks.
        if sessions and not touched:
            touched.append(True)
            if mutation == 'owner':
                sessions[-1].execute(text("UPDATE app_user SET status='suspended' WHERE id=:id"),
                    {'id': case.fixture.user.id.hex})
            elif mutation == 'context':
                sessions[-1].execute(text("UPDATE research_investigation SET status='archived' WHERE id=:id"),
                    {'id': uuid.UUID(case.request['investigation_id']).hex})
            elif mutation == 'proposal':
                sessions[-1].execute(text('UPDATE research_experiment SET version=version+1 WHERE id=:id'),
                    {'id': uuid.UUID(case.request['experiment_id']).hex})
            elif mutation == 'factory':
                value._service.session_factory = lambda: None
            elif mutation == 'source':
                for denied in case.fixture.retained.policy.values():
                    denied.add(case.fixture.retained.dataset_ids['ctd'])
            elif mutation == 'approval':
                sessions[-1].execute(text("UPDATE research_experiment_approval SET request_sha256=:sha WHERE revision_id=:id"),
                    {'sha': '0' * 64, 'id': uuid.UUID(case.request['expected_proposal_revision_id']).hex})
            else:
                return False
        return True
    value.store.config = replace(value.store.config, enabled=enabled)
    value._store_config = value.store.config
    try:
        with pytest.raises((SandboxError, ResearchExperimentError, ValueError)):
            value.reserve(request(case), current_owner=case.fixture.user)
    finally:
        value._service.session_factory = original_factory
        for denied in case.fixture.retained.policy.values():
            denied.clear()
    assert touched and calls == []


def test_native_reserve_method_prepares_params_and_runs_no_enable_after_fence(monkeypatch):
    from tests.test_experiment_sandbox_execution_store import binding, configuration
    sequence = []
    value = C23ExecutionStore(config=configuration(enabled=lambda: sequence.append('enabled') or True))
    payload = binding()
    class Session:
        info = {value._controller_token: value}
        def in_transaction(self):
            return True
        def scalar(self, statement, parameters):
            sequence.append('sql')
            assert json.loads(parameters['p']) == payload.model_dump()
            return payload.execution_id
    monkeypatch.setattr(value, '_check_session', lambda *_: sequence.append('role'))
    result = value.reserve_after_fence_in_transaction(Session(), payload,
        final_fence=lambda: sequence.append('closing'))
    assert result == payload.execution_id and sequence == ['enabled', 'role', 'closing', 'sql']
