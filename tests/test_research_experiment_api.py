"""C22 real synthetic service over authenticated worker-owned HTTP actions."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import threading
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event

from api import auth, research_experiment_routes as routes
from db.app_models import AppBase
from tests.research_experiment_support import make_experiment_fixture


@pytest.fixture
def http(tmp_path, monkeypatch):
    for name in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS', 'ENABLE_V1_EXPERIMENTS', 'ENABLE_V1_EXPERIMENT_DISPATCH'):
        monkeypatch.setenv(name, 'true')
    monkeypatch.setenv('AUTH_MODE', 'required')
    monkeypatch.setenv('DEPLOYMENT_ENV', 'development')
    engine = create_engine('sqlite+pysqlite:///' + str(tmp_path / 'v1.sqlite'))
    @event.listens_for(engine, 'connect')
    def keys(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')
    AppBase.metadata.create_all(engine)
    fixture = make_experiment_fixture(engine, tmp_path)
    state = {'user': fixture.user}
    monkeypatch.setattr(auth, 'authenticate_request', lambda request: state['user'])
    app = FastAPI()
    app.middleware('http')(auth.authorization_middleware)
    @app.middleware('http')
    async def capture_loop(request, call_next):
        app.state.loop_thread = threading.get_ident()
        return await call_next(request)
    app.include_router(routes.router)
    app.state.research_experiment_service = fixture.service
    app.state.investigation_service = fixture.investigations
    yield app, state, fixture
    engine.dispose()


def post(client, action, payload, status=200):
    response = client.post('/research/experiments/' + action, json=payload)
    assert response.status_code == status, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    return response.json()


def test_all_nine_actual_actions_reopen_exact_bytes_and_never_execute(http, monkeypatch, tmp_path):
    app, _, fixture = http
    thread_ids, capture = [], []
    original = routes.research_experiment_response
    def observed(*args):
        thread_ids.append(threading.get_ident())
        return original(*args)
    monkeypatch.setattr(routes, 'research_experiment_response', observed)
    request = fixture.request()
    sentinel = tmp_path / 'C22-PYTHON-MUST-NOT-EXECUTE'
    request['proposal']['python_code'] = 'from pathlib import Path\nPath(' + repr(str(sentinel)) + ').write_text("unexpected")\n'
    caller = threading.get_ident()
    with TestClient(app) as client:
        def invoke(action, value):
            result = post(client, action, value)
            capture.append({'action': action, 'request': value, 'response': result})
            return result
        created = invoke('create', request)
        first = created['experiment']
        assert created['operation']['state'] == 'ready'
        assert first['hashes']['code_sha256'] == hashlib.sha256(request['proposal']['python_code'].encode()).hexdigest()
        changed = {**request, 'experiment_id': first['id'], 'expected_version': first['version'],
            'expected_proposal_revision_id': first['proposal_revision_id'], 'idempotency_key': str(uuid.uuid4()),
            'proposal': {**request['proposal'], 'method': 'Revised exact synthetic review method'}}
        revised = invoke('revise', changed)
        current = revised['experiment']
        assert current['proposal_revision_id'] != first['proposal_revision_id'] and current['version'] == 2
        old = invoke('get', {**fixture.address(current), 'proposal_revision_id': first['proposal_revision_id']})['experiment']
        assert old['proposal'] == first['proposal']
        assert invoke('status', fixture.address(current))['experiment']['proposal'] == current['proposal']
        listed = invoke('list', {'investigation_id': request['investigation_id'], 'limit': 1})
        assert [item['id'] for item in listed['items']] == [current['id']]
        assert invoke('retry', {'operation_id': revised['operation']['id']})['experiment']['proposal_revision_id'] == current['proposal_revision_id']
        approved = invoke('approve', fixture.decision(current))['experiment']
        assert approved['approval']['status'] == 'current' and approved['dispatch']['eligible']
        decision = fixture.decision(approved)
        dispatched = invoke('dispatch', decision)['experiment']
        assert dispatched['dispatch']['reservation_id'] and not dispatched['execution_performed']
        fixture.state['dispatch_enabled'] = False
        assert post(client, 'dispatch', decision)['experiment']['dispatch']['reservation_id'] == dispatched['dispatch']['reservation_id']
        fixture.state['dispatch_enabled'] = True
        assert fixture.service.dispatch_outbox() == {'sent': 1, 'execution_performed': False}
        assert len(fixture.executor.deliveries) == 1
        events = invoke('events', {**fixture.address(current), 'limit': 2})
        assert [item['cursor'] for item in events['items']] == [1, 2] and events['has_more']
        end = post(client, 'events', {**fixture.address(current), 'after_cursor': events['next_cursor'], 'limit': 100})
        assert not end['has_more'] and end['next_cursor'] == end['latest_event_cursor']
        fixture.state['enabled'] = False
        assert post(client, 'get', fixture.address(current))['experiment']['dispatch']['status'] == 'accepted'
    assert not sentinel.exists()
    assert set(item['action'] for item in capture) == set(routes.EXPERIMENT_REQUEST_MODELS)
    assert thread_ids and all(value not in {caller, app.state.loop_thread} for value in thread_ids)
    output = os.environ.get('C22_WIRE_CAPTURE')
    if output:
        with Path(output).open('x') as stream:
            json.dump({'kind': 'actual-local-synthetic-http', 'python_executed': False,
                'scientific_approval': 'not_independently_verified', 'actions': capture}, stream, ensure_ascii=False, indent=2)


@pytest.mark.parametrize('raw', [b'{"limit":1,"limit":2}', b'{"limit":NaN}', b'null', b'[]',
    b'{"operation_id":"\\udfff"}', b'{}' + b' ' * 65536])
def test_invalid_or_excessive_body_never_calls_service(http, monkeypatch, raw):
    app, _, fixture = http
    monkeypatch.setattr(fixture.service, 'invoke', lambda *_: pytest.fail('Invalid body dispatched'))
    with TestClient(app) as client:
        response = client.post('/research/experiments/retry', content=raw)
    assert response.status_code == 422 and response.json()['error']['code'] == 'invalid_request'


def test_query_and_stream_byte_bound_are_enforced_before_service(http, monkeypatch):
    app, _, fixture = http
    monkeypatch.setattr(fixture.service, 'invoke', lambda *_: pytest.fail('Invalid body dispatched'))
    with TestClient(app) as client:
        assert client.post('/research/experiments/retry?execute=true', json={}).status_code == 422
        response = client.post('/research/experiments/retry', content=iter([b'{', b' ' * 32768, b' ' * 32768, b'}']))
        assert response.status_code == 422


@pytest.mark.parametrize('actor', ['other', 'admin'])
def test_cross_owner_status_and_approval_are_absent_even_for_admin(http, actor):
    app, state, fixture = http
    experiment = fixture.create()
    state['user'] = getattr(fixture, actor)
    with TestClient(app) as client:
        post(client, 'get', fixture.address(experiment), 404)
        post(client, 'approve', fixture.decision(experiment), 404)


def test_inactive_and_missing_permissions_reject_before_service(http, monkeypatch):
    from dataclasses import replace
    app, state, fixture = http
    monkeypatch.setattr(fixture.service, 'invoke', lambda *_: pytest.fail('Denied request dispatched'))
    with TestClient(app) as client:
        for changes in ({'status': 'suspended'}, {'permissions': fixture.user.permissions - {'data:read'}},
                        {'permissions': fixture.user.permissions - {'chat:use'}}, {'role': 'viewer'}):
            state['user'] = replace(fixture.user, **changes)
            post(client, 'get', {'experiment_id': str(uuid.uuid4())}, 403)


def test_unknown_missing_and_mismatched_service_never_discovers_a_fallback(http, monkeypatch):
    app, _, fixture = http
    with TestClient(app) as client:
        for path in ('/execute', '/publish', '/dispatch/other'):
            assert client.post('/research/experiments' + path, json={}).status_code == 403
        app.state.research_experiment_service = None
        assert post(client, 'get', {'experiment_id': str(uuid.uuid4())}, 503)['error']['code'] == 'experiments_unavailable'
        app.state.research_experiment_service = fixture.service
        monkeypatch.setattr(fixture.service, 'session_factory', object())
        post(client, 'get', {'experiment_id': str(uuid.uuid4())}, 503)


def test_bad_response_identity_is_closed_but_unknown_exceptions_are_sanitized(http, monkeypatch):
    app, _, fixture = http
    experiment = fixture.create()
    valid = fixture.service.invoke('get', fixture.address(experiment), fixture.user)
    with TestClient(app) as client:
        wrong = deepcopy(valid)
        wrong['experiment']['id'] = str(uuid.uuid4())
        monkeypatch.setattr(fixture.service, 'invoke', lambda *_: wrong)
        response = post(client, 'get', fixture.address(experiment), 503)
        assert 'private' not in str(response)
        def failed(*_):
            raise RuntimeError('private source credentials must not leak')
        monkeypatch.setattr(fixture.service, 'invoke', failed)
        response = post(client, 'get', fixture.address(experiment), 503)
        assert 'credentials' not in str(response)


def test_completed_create_response_must_match_the_reviewed_request(http, monkeypatch):
    app, _, fixture = http
    data = fixture.request()
    saved = fixture.service.invoke('create', data, fixture.user)
    different = deepcopy(data)
    different['proposal']['method'] = 'A different reviewable method'
    monkeypatch.setattr(fixture.service, 'invoke', lambda *_: saved)
    with TestClient(app) as client:
        post(client, 'create', different, 503)


def test_failed_revise_on_new_context_preserves_old_head_and_retry_identity(http):
    app, _, fixture = http
    request = fixture.request()
    experiment = fixture.service.invoke('create', request, fixture.user)['experiment']
    scope = deepcopy(fixture.retained.scope)
    scope['sources']['metagenome']['enabled'] = False
    changed = fixture.investigations.invoke('context/change', {
        'investigation_id': request['investigation_id'], 'expected_revision_id': request['context_revision_id'],
        'idempotency_key': str(uuid.uuid4()), 'change': {'op': 'scope', 'scope': scope}}, fixture.user)['context']
    revised = {**request, 'context_revision_id': changed['id'], 'snapshot_id': changed['snapshot_id'],
        'context_payload_sha256': changed['payload_sha256'], 'experiment_id': experiment['id'],
        'expected_version': experiment['version'], 'expected_proposal_revision_id': experiment['proposal_revision_id'],
        'idempotency_key': str(uuid.uuid4()), 'proposal': {**request['proposal'], 'resources': {'max_input_bytes': 1}}}
    with TestClient(app) as client:
        failed = post(client, 'revise', revised)
        assert failed['operation']['state'] == 'unavailable'
        assert failed['experiment']['binding'] == experiment['binding']
        retried = post(client, 'retry', {'operation_id': failed['operation']['id']})
        assert retried['operation']['id'] == failed['operation']['id']
        assert retried['experiment']['proposal_revision_id'] == experiment['proposal_revision_id']
