"""Actual restricted-controller reserve over real synthetic C22 approvals.

Requires an explicitly supplied owned disposable PostgreSQL. No server, runtime,
cloud resource, fake dispatch or scientific approval is created by this module.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from api.v1_experiment_start import create_experiment_start_router
from db.app_models import AppBase
from db.experiment_execution_models import EXECUTION_MODELS
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.execution_store import (
    ExecutionStoreConfig, bootstrap_retained_controller_reads,
)
from orchestration.experiment_sandbox.retained_bridge import C23RetainedBridge, RetainedMaterialPolicy
from orchestration.experiment_sandbox.retained_work import RetainedWorkQueue
from orchestration.research_experiments import ResearchExperimentError
from schema.research_experiments import EnvironmentDescriptor
from tests import experiment_execution_postgres_support as pg
from tests.research_experiment_support import make_experiment_fixture
from tests.retained_reserve_support import bridge as configured
from tests.test_experiment_sandbox_execution_store import configuration

pytestmark = pytest.mark.skipif(os.environ.get('RUN_C23_POSTGRES_INTEGRATION') != '1',
    reason='explicit new owned PostgreSQL required; tests start no service')
disposable_database, isolated, role_database = pg.disposable_database, pg.isolated, pg.role_database


@pytest.fixture
def retained(role_database, tmp_path, monkeypatch):
    for name in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS'):
        monkeypatch.setenv(name, 'true')
    database = role_database
    serving = database['roles'].serving_role
    execution_tables = {model.__tablename__ for model in EXECUTION_MODELS}
    # Explicit fixture-only application writer rights on C22 tables; no new
    # C23 serving privileges. The bridge never receives this writer factory.
    with database['engine'].begin() as connection:
        for table in AppBase.metadata.tables.values():
            if table.name not in execution_tables:
                connection.exec_driver_sql(f'GRANT SELECT,INSERT,UPDATE ON TABLE {database["schema"]}.{table.name} TO {serving}')
    fixture = make_experiment_fixture(database['role_engines'][serving], tmp_path)
    fixture.service.executor = None
    fixture.state['dispatch_enabled'] = False
    fixture.environment = EnvironmentDescriptor(kind='linux-gvisor', test_only=False,
        python_version='3.12.15', image_digest='sha256:' + 'a' * 64, lockfile_sha256='b' * 64,
        packages={name: '1.0.0' for name in ('numpy','pandas','pyarrow','scipy','statsmodels','matplotlib')},
        description='Explicit synthetic retained DB fixture; no runtime acceptance')
    fixture.service.environments[fixture.environment.identity_sha256] = fixture.environment.model_dump(mode='json')
    old = configuration()
    config = ExecutionStoreConfig(site_id=fixture.service.site_id, database_name=database['url'].database,
        schema=database['schema'], controller_session_factory=database['controller_factory'],
        recorder_session_factory=database['recorder_factory'], roles=database['roles'],
        verifier_registry=old.verifier_registry, store_scope='isolated-unmounted-operator', enabled=lambda: True)
    with database['engine'].begin() as connection:
        bootstrap_retained_controller_reads(connection, config=config)
    bridge = configured(fixture, factory=database['controller_factory'], config=config)
    def approved(*, actor=None):
        actor = fixture.user if actor is None else actor
        created = fixture.service.invoke('create', fixture.request(user=actor), actor)['experiment']
        current = fixture.service.invoke('approve', fixture.decision(created), actor)['experiment']
        assert current['approval']['status'] == 'current' and not current['dispatch']['eligible']
        return fixture.decision(current)
    return SimpleNamespace(database=database, fixture=fixture, bridge=bridge, approved=approved)


def counts(case):
    with case.database['engine'].connect() as connection:
        return tuple(connection.scalar(text('SELECT count(*) FROM ' + table)) for table in (
            'research_experiment_reservation', 'research_experiment_execution', 'research_experiment_outbox'))


def test_actual_restricted_controller_reserves_exact_real_approval_and_replays(retained):
    case = retained
    request = case.approved()
    result = case.bridge.reserve(request, current_owner=case.fixture.user)
    assert case.bridge._service.session_factory is case.database['controller_factory']
    assert case.bridge._service.session_factory is not case.fixture.factory
    with case.database['controller_factory']() as session:
        assert tuple(session.execute(text('SELECT current_user,session_user')).one()) == (
            case.database['roles'].controller_role,) * 2
        row = session.execute(text('SELECT envelope_json,envelope_sha256 FROM research_experiment_execution')).one()
        assert json.loads(row[0])['approval_id'] == result.document['approval_id']
        assert row[1] == result.document['envelope_sha256']
    replay = case.bridge.reserve(request, current_owner=case.fixture.user)
    assert replay.document == result.document and counts(case) == (1, 1, 0)
    assert result.document['capacity_reserved_at_commit'] is True
    assert result.execution_authorized is False and case.fixture.service.executor is None


def test_private_start_records_one_job_and_fresh_controller_reopens_exact_inputs(retained, monkeypatch):
    case = retained
    request = case.approved()
    app = FastAPI()
    state = {'owner': None}

    @app.middleware('http')
    async def authenticated_owner(request, call_next):
        request.state.current_user = state['owner']
        return await call_next(request)

    app.include_router(create_experiment_start_router(bridge=case.bridge))
    with TestClient(app) as client:
        path = '/internal/experiments/start'
        assert client.post(path, json=request).status_code == 401
        state['owner'] = case.fixture.admin
        assert client.post(path, json=request).status_code == 404
        state['owner'] = case.fixture.user
        assert client.post(path, json={**request, 'owner_user_id': str(case.fixture.admin.id)}).status_code == 422
        assert counts(case) == (0, 0, 0)

        reserve = case.bridge.reserve

        def lose_acknowledgement(*args, **kwargs):
            reserve(*args, **kwargs)
            raise SandboxError('simulated_response_lost_after_commit')

        with monkeypatch.context() as patch:
            patch.setattr(case.bridge, 'reserve', lose_acknowledgement)
            assert client.post(path, json=request).status_code == 503
        assert counts(case) == (1, 1, 0)

        restarted = configured(case.fixture, factory=case.database['controller_factory'], config=case.bridge.store.config)
        work = RetainedWorkQueue(bridge=restarted)
        status, = work.list_unreleased()
        assert status.state == 'reserved' and status.exact_material is True
        pending = work.reopen(status.execution_id)
        assert pending.owner == case.fixture.user
        first = client.post(path, json=request)
        assert first.status_code == 200 and first.headers['cache-control'] == 'no-store'
        result = first.json()
        assert set(result) == {'version', 'execution_id', 'reservation_id',
            'capacity_reserved_at_commit', 'execution_authorized'}
        assert result['capacity_reserved_at_commit'] is True and result['execution_authorized'] is False
        assert result['execution_id'] == status.execution_id == pending.identity.document['execution_id']
        assert client.post(path, json=request).json() == result

    with pytest.raises(ResearchExperimentError) as denied:
        restarted.reopen_pending(result['execution_id'], current_owner=case.fixture.admin)
    assert denied.value.status_code == 404
    identity, envelope = pending.identity, pending.envelope
    assert identity.document['reservation_id'] == result['reservation_id']
    assert identity.document['job_id'] == envelope.job_id
    assert identity.document['envelope_sha256'] == envelope.envelope_sha256
    assert envelope.metadata['hashes'] == request['expected_hashes'] and envelope.files
    assert counts(case) == (1, 1, 0)

    catalogue = case.fixture.retained
    child = catalogue.registrations[request['snapshot_id']].child_snapshot_ids[0]
    catalogue.store.revoke(child)
    with pytest.raises(ResearchExperimentError) as withdrawn:
        work.reopen(result['execution_id'])
    assert (withdrawn.value.code, withdrawn.value.status_code) == ('experiments_unavailable', 503)
    assert counts(case) == (1, 1, 0)


def test_paused_and_mismatched_workers_cannot_reopen_held_work(retained):
    case = retained
    result = case.bridge.reserve(case.approved(), current_owner=case.fixture.user)
    execution_id = result.document['execution_id']
    policy = json.loads(case.bridge._material_json)

    def queue(**changes):
        return RetainedWorkQueue(bridge=C23RetainedBridge(inspection=case.bridge.inspection,
            store=case.bridge.store, material_policy=RetainedMaterialPolicy.model_validate({**policy, **changes}),
            enabled=lambda: case.fixture.state['enabled']))

    same_worker_new_runtime = queue(runtime_sha256='d' * 64)
    held, = same_worker_new_runtime.list_unreleased()
    assert held.execution_id == execution_id and held.exact_material is False
    with pytest.raises(ResearchExperimentError) as conflict:
        same_worker_new_runtime.reopen(execution_id)
    assert conflict.value.status_code == 409
    another_worker = queue(worker_id='e' * 64)
    assert another_worker.list_unreleased() == ()
    with pytest.raises(ResearchExperimentError) as missing:
        another_worker.reopen(execution_id)
    assert missing.value.status_code == 404
    case.fixture.state['enabled'] = False
    paused = queue()
    held, = paused.list_unreleased()
    assert held.execution_id == execution_id and held.exact_material is True
    with pytest.raises(SandboxError, match='sandbox_retained_bridge_disabled'):
        paused.reopen(execution_id)
    assert counts(case) == (1, 1, 0)


def test_native_current_c22_read_grants_and_only_three_id_writes(retained):
    case = retained
    request = case.approved()
    factory = case.database['controller_factory']
    for statement in ("UPDATE app_user SET status=status", 'UPDATE research_experiment SET version=version',
        'UPDATE research_investigation SET status=status', 'UPDATE research_experiment_execution_state SET fence=fence',
        'INSERT INTO research_experiment_outbox(reservation_id,state,attempts) VALUES(gen_random_uuid(),\'pending\',0)'):
        with pytest.raises(DBAPIError), factory.begin() as session:
            session.execute(text(statement))
    for table in ('app_user', 'research_investigation', 'research_experiment'):
        with factory.begin() as session:
            # Explicitly prove this is real UPDATE(id) privilege, not lock-only.
            session.execute(text(f'UPDATE {table} SET id=id'))
    result = case.bridge.reserve(request, current_owner=case.fixture.user)
    assert result.document['capacity_reserved_at_commit'] and counts(case) == (1, 1, 0)


def test_native_rollback_after_named_reserve_retains_no_partial_capacity(retained, monkeypatch):
    case = retained
    request = case.approved()
    original = case.bridge.store.reserve_after_fence_in_transaction
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('test rollback after actual native reserve')
    monkeypatch.setattr(case.bridge.store, 'reserve_after_fence_in_transaction', fail)
    with pytest.raises(RuntimeError, match='rollback'):
        case.bridge.reserve(request, current_owner=case.fixture.user)
    assert counts(case) == (0, 0, 0)


def test_native_admin_factory_cannot_substitute_for_controller(retained):
    case = retained
    request = case.approved()
    from sqlalchemy.orm import sessionmaker
    admin_factory = sessionmaker(bind=case.database['engine'], expire_on_commit=False)
    config = replace(case.bridge.store.config, controller_session_factory=admin_factory)
    wrong = configured(case.fixture, factory=admin_factory, config=config)
    with pytest.raises(SandboxError, match='role_boundary'):
        wrong.reserve(request, current_owner=case.fixture.user)
    assert counts(case) == (0, 0, 0)


def test_native_late_factory_callback_cannot_pass_final_fence(retained):
    case = retained
    request = case.approved()
    seen = []
    original_check = case.bridge.store._check_session
    def checked(session, role):
        original_check(session, role)
        seen.append(session)
    case.bridge.store._check_session = checked
    original_factory = case.bridge._service.session_factory
    def enabled():
        if seen:
            case.bridge._service.session_factory = lambda: None
        return True
    config = replace(case.bridge.store.config, enabled=enabled)
    case.bridge.store.config = case.bridge._store_config = config
    try:
        with pytest.raises(ValueError, match='exact configured|exact restricted'):
            case.bridge.reserve(request, current_owner=case.fixture.user)
    finally:
        case.bridge._service.session_factory = original_factory
    assert counts(case) == (0, 0, 0)


def test_native_same_owner_capacity_and_changed_replay_are_rejected(retained):
    case = retained
    first = case.approved()
    case.bridge.reserve(first, current_owner=case.fixture.user)
    second = case.approved()
    with pytest.raises(DBAPIError):
        case.bridge.reserve(second, current_owner=case.fixture.user)
    with pytest.raises(DBAPIError):
        case.bridge.reserve({**second, 'idempotency_key': first['idempotency_key']}, current_owner=case.fixture.user)
    assert counts(case) == (1, 1, 0)


def test_native_bridge_global_capacity_is_two_and_never_creates_fake_delivery(retained):
    case = retained
    for actor in (case.fixture.user, case.fixture.other):
        case.bridge.reserve(case.approved(actor=actor), current_owner=actor)
    request = case.approved(actor=case.fixture.admin)
    with pytest.raises(DBAPIError):
        case.bridge.reserve(request, current_owner=case.fixture.admin)
    assert counts(case) == (2, 2, 0)


def test_native_concurrent_exact_replay_has_one_retained_reservation(retained):
    case = retained
    request = case.approved()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(case.bridge.reserve, request, current_owner=case.fixture.user) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert results[0].document == results[1].document and counts(case) == (1, 1, 0)


@pytest.mark.parametrize('field', ['user_id', 'expected_hashes'])
def test_native_callers_cannot_inject_owner_or_approval_claims(retained, field):
    case = retained
    request = case.approved()
    if field == 'user_id':
        request[field] = str(uuid.uuid4())
    else:
        request[field] = {name: '0' * 64 for name in request[field]}
    with pytest.raises(ResearchExperimentError):
        case.bridge.reserve(request, current_owner=case.fixture.user)
    assert counts(case) == (0, 0, 0)
