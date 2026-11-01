"""Independent authenticated API bootstrap, actual reads and closed execution."""
from dataclasses import replace
import time
import uuid

from fastapi.testclient import TestClient
import jwt
from pydantic import SecretStr, ValidationError
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from api import v1_host
from api.auth import ROLE_PERMISSIONS
from api.v1_host import HostConfigurationError, V1HostSettings, V1ReadServices, create_host_app
from db.app_models import AppBase, AppUser

SECRET = 'independent-v1-host-test-secret-' * 2
READ_FLAGS = ('SHELL', 'CATALOGUE', 'CATALOGUE_BROWSER', 'INVESTIGATIONS', 'RESEARCH_RUNS',
    'EVIDENCE', 'EXPERIMENTS', 'EXPERIMENT_WORKSPACE')


def settings(**changes):
    return V1HostSettings.model_validate({
        'version': 'ocean-v1-api-host-v1', 'project_id': 'ocean-v1-beta-test',
        'site_id': 'v1:ocean-v1-beta-test', 'revision': '1' * 40,
        'public_origin': 'https://beta.oceaninfobio.com', 'database_name': 'ocean_v1_beta',
        'backend_hosts': ('127.0.0.1:8000',), 'allowed_providers': ('oidc', 'google'),
        'internal_issuer': 'ocean-v1-frontend', 'internal_audience': 'ocean-v1-api', **changes})


def token(actor=None, **changes):
    now = int(time.time())
    claims = {'iss': 'ocean-v1-frontend', 'aud': 'ocean-v1-api', 'iat': now, 'exp': now + 60,
        'sub': str(actor.id) if actor else 'subject-1', 'email': actor.email if actor else 'owner@beta.invalid',
        'provider': actor.auth_provider if actor else 'oidc', 'email_verified': True, **changes}
    return jwt.encode(claims, SECRET, algorithm='HS256')


def headers(actor=None, **claims):
    return {'Authorization': 'Bearer ' + token(actor, **claims)}


def mark_test_schema(engine, revision='20261027_0021'):
    # SQLite here is an explicitly identified application/unit fixture, not an
    # assertion that Alembic migrated it; C27 retains real PG migration evidence.
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version (version_num TEXT NOT NULL)'))
        connection.execute(text('INSERT INTO alembic_version VALUES (:revision)'), {'revision': revision})


@pytest.fixture
def independent(tmp_path, monkeypatch):
    monkeypatch.setenv('DEPLOYMENT_ENV', 'test')
    for name in v1_host.EXECUTION_FLAGS:
        monkeypatch.setenv(name, 'false')
    for name in READ_FLAGS:
        monkeypatch.setenv('ENABLE_V1_' + name, 'true')
    engine = create_engine('sqlite+pysqlite:///' + str(tmp_path / 'independent-v1.sqlite'))
    AppBase.metadata.create_all(engine)
    mark_test_schema(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    identity = uuid.uuid4()
    with factory.begin() as session:
        session.add(AppUser(id=identity, auth_subject='subject-1', auth_provider='oidc',
            email='owner@beta.invalid', display_name='Beta owner', role='researcher',
            account_type='internal', status='active'))
    yield engine, factory
    engine.dispose()


def app(factory, services=None):
    return create_host_app(settings=settings(), session_factory=factory,
        internal_secret=SecretStr(SECRET), services=services, _allow_test_sqlite=True)


def test_empty_host_auth_and_unavailable_catalogue_do_not_use_legacy_database(independent, monkeypatch):
    from db import connection
    engine, factory = independent
    def legacy_forbidden(*args, **kwargs):
        raise AssertionError('No ambient legacy connection may be used')
    monkeypatch.setattr(connection, 'get_engine', legacy_forbidden)
    monkeypatch.setattr(connection, 'get_session', legacy_forbidden)
    monkeypatch.setenv('AUTH_MODE', 'disabled')  # Must not bypass the new boundary.
    before = inspect(engine).get_table_names()
    with TestClient(app(factory), base_url='http://127.0.0.1:8000') as client:
        assert client.get('/health/live').json() == {'status': 'live', 'execution_enabled': False}
        assert client.get('/me').status_code == 401
        me = client.get('/me', headers=headers())
        assert me.status_code == 200
        assert me.json()['permissions'] == sorted(ROLE_PERMISSIONS['researcher'])
        runtime = client.get('/v1/runtime', headers=headers())
        assert runtime.status_code == 200, runtime.text
        assert runtime.json()['capabilities']['catalogue']['status'] == 'unavailable'
        assert runtime.json()['capabilities']['research']['status'] == 'unavailable'
        assert runtime.json()['research_runs']['submit_enabled'] is False
        assert me.headers['cache-control'] == 'no-store'
    assert inspect(engine).get_table_names() == before


@pytest.mark.parametrize('claims', [
    {'iss': 'ocean-platform-frontend'}, {'aud': 'ocean-platform-api'},
    {'aud': ['ocean-v1-api', 'ocean-platform-api']},
    {'provider': 'mock-credentials'}, {'email_verified': False}, {'email': None},
    {'sub': ''}, {'iat': True}, {'exp': 1}, {'exp': int(time.time()) + 500},
])
def test_identity_claims_fail_closed(independent, claims):
    _, factory = independent
    with TestClient(app(factory), base_url='http://127.0.0.1:8000') as client:
        assert client.get('/me', headers=headers(**claims)).status_code == 401


def test_current_role_suspension_and_email_are_resolved_on_every_request(independent):
    _, factory = independent
    with TestClient(app(factory), base_url='http://127.0.0.1:8000') as client:
        auth = headers()
        assert client.get('/me', headers=auth).json()['role'] == 'researcher'
        with factory.begin() as session:
            user = session.scalar(select(AppUser))
            user.role = 'viewer'
        assert client.get('/me', headers=auth).json()['role'] == 'viewer'
        assert client.post('/catalogue/overview', json={}, headers=auth).status_code == 403
        with factory.begin() as session:
            session.scalar(select(AppUser)).status = 'suspended'
        assert client.get('/me', headers=auth).status_code == 403
        with factory.begin() as session:
            user = session.scalar(select(AppUser))
            user.status = 'active'
            user.email = 'changed@beta.invalid'
        assert client.get('/me', headers=auth).status_code == 403


def test_unenrolled_identity_does_not_create_or_import_account(independent):
    _, factory = independent
    with TestClient(app(factory), base_url='http://127.0.0.1:8000') as client:
        assert client.get('/me', headers=headers(sub='other-subject')).status_code == 403
    with factory() as session:
        assert len(session.scalars(select(AppUser)).all()) == 1


@pytest.mark.parametrize('path', ['/research/runs/submit', '/research/runs/continue',
    '/research/answers/submit', '/research/experiments/approve', '/research/experiments/dispatch',
    '/research/investigations/create', '/admin/users', '/chat'])
def test_all_new_work_and_legacy_routes_are_closed(independent, path):
    _, factory = independent
    with TestClient(app(factory), base_url='http://127.0.0.1:8000') as client:
        result = client.post(path, json={}, headers=headers())
        assert result.status_code == 403
        assert result.json()['error']['code'] == 'readonly_stage'


def test_host_queries_duplicate_tokens_and_request_size_are_bounded(independent):
    _, factory = independent
    with TestClient(app(factory), base_url='http://127.0.0.1:8000') as client:
        assert client.get('/me', headers={**headers(), 'Host': 'oceaninfobio.com'}).status_code == 421
        assert client.get('/me?target=legacy', headers=headers()).status_code == 422
        assert client.get('/me', headers=[('Authorization', 'Bearer '+token()), ('Authorization', 'Bearer '+token())]).status_code == 401
        assert client.post('/catalogue/overview', content=b'x' * (v1_host.MAX_REQUEST_BYTES+1), headers=headers()).status_code == 413


def test_dispatch_flag_change_after_startup_closes_request(independent, monkeypatch):
    _, factory = independent
    with TestClient(app(factory), base_url='http://127.0.0.1:8000') as client:
        assert client.get('/me', headers=headers()).status_code == 200
        monkeypatch.setenv('ENABLE_V1_SYNTHESIS', 'true')
        result = client.get('/me', headers=headers())
        assert result.status_code == 503 and result.json()['error']['code'] == 'host_configuration_unavailable'
    with pytest.raises(HostConfigurationError):
        app(factory)


def test_sqlite_test_injection_is_rejected_in_production(independent, monkeypatch):
    _, factory = independent
    monkeypatch.setenv('DEPLOYMENT_ENV', 'production')
    with pytest.raises(HostConfigurationError, match='explicit test environment'):
        app(factory)


def test_schema_readiness_never_creates_or_upgrades_a_database(tmp_path, monkeypatch):
    monkeypatch.setenv('DEPLOYMENT_ENV', 'test')
    for name in v1_host.EXECUTION_FLAGS:
        monkeypatch.setenv(name, 'false')
    engine = create_engine('sqlite+pysqlite:///' + str(tmp_path / 'blank.sqlite'))
    factory = sessionmaker(bind=engine)
    with pytest.raises(HostConfigurationError, match='schema is unavailable'):
        app(factory)
    assert inspect(engine).get_table_names() == []
    mark_test_schema(engine, '20261005_0016')
    with pytest.raises(HostConfigurationError, match='migration head'):
        app(factory)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '20261005_0016'
    with pytest.raises(HostConfigurationError, match='PostgreSQL'):
        create_host_app(settings=settings(), session_factory=factory, internal_secret=SecretStr(SECRET))
    engine.dispose()


@pytest.mark.parametrize('changes', [
    {'site_id': 'v1:legacy'}, {'project_id': 'data-infra-infobio'}, {'database_name': 'ocean_platform'},
    {'public_origin': 'https://oceaninfobio.com'}, {'backend_hosts': ('*',)},
    {'allowed_providers': ('mock-credentials',)}, {'internal_issuer': 'ocean-platform-frontend'},
])
def test_configuration_rejects_legacy_implicit_or_mock_targets(changes):
    with pytest.raises(ValidationError):
        settings(**changes)


def test_production_factory_requires_only_explicit_prefixed_inputs(tmp_path, monkeypatch):
    monkeypatch.delenv('OCEAN_V1_HOST_CONFIG', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://legacy:credentialSentinel@localhost/ocean_platform')
    with pytest.raises(HostConfigurationError) as error:
        v1_host.create_from_environment()
    assert 'credentialSentinel' not in str(error.value)
    cfg = tmp_path / 'host.json'
    cfg.write_text(settings().model_dump_json())
    monkeypatch.setenv('OCEAN_V1_HOST_CONFIG', str(cfg))
    monkeypatch.setenv('OCEAN_V1_DATABASE_URL', 'postgresql://legacy:credentialSentinel@localhost/ocean_platform')
    monkeypatch.setenv('OCEAN_V1_INTERNAL_AUTH_SECRET', SECRET)
    calls = []
    monkeypatch.setattr(v1_host, 'create_engine', lambda *a, **kw: calls.append(a))
    with pytest.raises(HostConfigurationError) as error:
        v1_host.create_from_environment()
    assert not calls and 'credentialSentinel' not in str(error.value)
    cfg.write_text('{"version":"one","version":"two"}')
    with pytest.raises(HostConfigurationError):
        v1_host.create_from_environment()


def test_actual_frozen_services_catalogue_context_and_owner_denial(independent, tmp_path, monkeypatch):
    from orchestration.research_controller import ResearchController
    from orchestration.research_dispatch import FakeResearchQueue
    from tests.investigation_support import make_investigation_fixture
    engine, _ = independent
    fixture = make_investigation_fixture(engine, tmp_path / 'frozen-services')
    # Enroll the explicit synthetic fixture subjects under this host's allowed
    # test OIDC issuer; production must not allow the fixture's mock provider.
    with fixture.factory.begin() as session:
        for name in ('user', 'other', 'admin'):
            actor = getattr(fixture, name)
            session.get(AppUser, actor.id).auth_provider = 'oidc'
            setattr(fixture, name, replace(actor, auth_provider='oidc'))
    # Actual canonical four-family fixture and existing accepted services; only
    # this test imports fixture builders, never the production module/entry.
    services = v1_host.compose_read_services(session_factory=fixture.factory, site_id=settings().site_id,
        snapshot_store=fixture.store, registrations=fixture.registrations,
        policy_resolver=fixture.service.catalogue.resolver.policy_resolver,
        snapshots=[{'snapshot_id': sid, 'label': {'en': 'Synthetic sealed source', 'ja': '合成'}} for sid in fixture.snapshots],
        discovery_policy=lambda user, descriptor: True,
        policy_revision='beta-host-test-policy', cursor_key=b'c'*32)
    investigation = services.investigation_service
    saved = investigation.invoke('create', {'name': 'Saved independent beta context',
        'snapshot_id': fixture.snapshots[0], 'scope': fixture.scope,
        'idempotency_key': str(uuid.uuid4())}, fixture.user)
    conversation = investigation.invoke('conversations/create', {
        'investigation_id': saved['investigation']['id'], 'name': 'Saved beta conversation',
        'idempotency_key': str(uuid.uuid4())}, fixture.user)['conversation']
    # Seed a real completed durable run before installing the read-only host.
    # The explicit fake transport is removed; no provider/model is involved.
    runs = services.research_run_service
    queue = FakeResearchQueue()
    runs.queue = queue
    runs.controller_factory = lambda identity_provider: ResearchController(investigations=investigation,
        catalogue=services.catalogue_service, identity_provider=identity_provider)
    runs.dispatch_enabled = lambda: True
    monkeypatch.setenv('ENABLE_V1_RESEARCH_CONTROLLER', 'true')
    submitted = runs.invoke('submit', {'investigation_id': saved['investigation']['id'],
        'conversation_id': conversation['id'], 'revision_id': saved['context']['id'],
        'expected_snapshot_id': fixture.snapshots[0], 'expected_payload_sha256': saved['context']['payload_sha256'],
        'question': 'Count all datasets', 'idempotency_key': str(uuid.uuid4())}, fixture.user)['run']
    assert runs.dispatch_outbox() == 1
    finished = queue.deliver_next(runs)['run']
    assert finished['id'] == submitted['id'] and finished['status'] == 'completed'
    retained = services.research_evidence_service.ensure_retained(finished['id'], 1, fixture.user)
    assert retained.receipts
    runs.queue = runs.controller_factory = None
    runs.dispatch_enabled = lambda: False
    monkeypatch.setenv('ENABLE_V1_RESEARCH_CONTROLLER', 'false')
    with TestClient(app(fixture.factory, services), base_url='http://127.0.0.1:8000') as client:
        auth = headers(fixture.user)
        runtime = client.get('/v1/runtime', headers=auth)
        assert runtime.status_code == 200, runtime.text
        assert runtime.json()['capabilities']['catalogue']['status'] == 'ready'
        page = client.post('/catalogue/snapshots', json={'scope': fixture.scope}, headers=auth)
        assert page.status_code == 200 and page.json()['total'] == 2, page.text
        address = {'run_id': finished['id'], 'investigation_id': saved['investigation']['id'],
            'conversation_id': conversation['id']}
        history = client.post('/research/runs/status', json=address, headers=auth)
        assert history.status_code == 200 and history.json()['run']['status'] == 'completed', history.text
        evidence = client.post('/research/evidence/list', json={**address, 'input_version': 1}, headers=auth)
        assert evidence.status_code == 200, evidence.text
        assert {item['id'] for item in evidence.json()['items']} == {item.id for item in retained.receipts}
        first = evidence.json()['items'][0]
        opened = client.post('/research/evidence/open', json={'receipt_id': first['id'],
            'expected_sha256': first['sha256']}, headers=auth)
        assert opened.status_code == 200 and opened.json()['receipt']['sha256'] == first['sha256'], opened.text
        request = {'investigation_id': saved['investigation']['id']}
        response = client.post('/research/investigations/get', json=request, headers=auth)
        assert response.status_code == 200, response.text
        denied = client.post('/research/investigations/get', json=request, headers=headers(fixture.other))
        assert denied.status_code == 404
        with fixture.factory.begin() as session:
            session.get(AppUser, fixture.user.id).status = 'suspended'
        assert client.post('/research/investigations/get', json=request, headers=auth).status_code == 403
    other = sessionmaker(bind=engine)
    with pytest.raises(HostConfigurationError, match='independent database'):
        create_host_app(settings=settings(), session_factory=other, internal_secret=SecretStr(SECRET),
            services=services, _allow_test_sqlite=True)


def test_service_bundle_rejects_any_executing_wiring(independent, tmp_path, monkeypatch):
    from tests.system_acceptance_support import make_system_acceptance_fixture
    engine, _ = independent
    for name in v1_host.EXECUTION_FLAGS:
        monkeypatch.setenv(name, 'true')
    fixture = make_system_acceptance_fixture(engine, tmp_path / 'executing-fixture')
    for name in v1_host.EXECUTION_FLAGS:
        monkeypatch.setenv(name, 'false')
    # Direct validation isolates the dangerous bundle wiring without pretending
    # this fixture's separately named site is the production beta configuration.
    bundle = V1ReadServices(fixture.retained.service.catalogue, fixture.browser,
        fixture.retained.service, fixture.runs.service, fixture.evidence, fixture.answers,
        fixture.experiments.service, fixture.workspace)
    with pytest.raises(HostConfigurationError, match='research execution wiring'):
        bundle.validate(session_factory=fixture.retained.factory, site_id=fixture.retained.service.site_id, allow_test=True)
    with pytest.raises(HostConfigurationError, match='typed v1'):
        replace(bundle, research_run_service=object()).validate(
            session_factory=fixture.retained.factory, site_id=fixture.retained.service.site_id, allow_test=True)
