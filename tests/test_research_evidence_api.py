"""Actual C20/C21 HTTP wire, current authorization and bounded public actions."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import threading
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api import auth
from api import research_evidence_routes as routes
from api.rate_limit import policy_for_request
from tests import test_research_answers as answer_fixtures

retained = answer_fixtures.retained
actual = answer_fixtures.actual


@pytest.fixture
def http(actual, monkeypatch):
    fixture, evidence, answers = answer_fixtures.service(actual)
    monkeypatch.setenv('DEPLOYMENT_ENV', 'test')
    monkeypatch.setenv('ENABLE_V1_EVIDENCE', 'true')
    monkeypatch.setenv('ENABLE_V1_SYNTHESIS', 'true')
    state = {'user': fixture.user}
    monkeypatch.setattr(auth, 'authenticate_request', lambda request: state['user'])
    app = FastAPI()
    app.middleware('http')(auth.authorization_middleware)
    @app.middleware('http')
    async def capture_loop(request, call_next):
        app.state.loop_thread = threading.get_ident()
        return await call_next(request)
    app.include_router(routes.router)
    app.state.investigation_service = fixture.retained.service
    app.state.research_evidence_service = evidence
    app.state.research_answer_service = answers
    return app, state, fixture, evidence, answers


def test_all_nine_actual_actions_and_source_bound_wire_capture(http, monkeypatch):
    app, _, fixture, evidence, answers = http
    run, data = answer_fixtures.request(fixture)
    capture, threads = [], []
    original = routes.research_evidence_response

    def observed(*args):
        threads.append(threading.get_ident())
        return original(*args)

    monkeypatch.setattr(routes, 'research_evidence_response', observed)
    caller = threading.get_ident()
    with TestClient(app) as client:
        def post(group, name, request):
            path = '/research/' + group + '/' + name
            response = client.post(path, json=request)
            assert response.status_code == 200, response.text
            assert response.headers['cache-control'] == 'no-store'
            assert response.headers['x-content-type-options'] == 'nosniff'
            assert auth.route_permission('POST', path) == ('data:export' if name == 'export' else 'chat:use')
            capture.append({'path': path, 'request': request, 'response': response.json()})
            return response.json()

        job = post('answers', 'submit', data)['job']
        answers.execute_delivery(**answer_fixtures.delivery(fixture, job))
        status = post('answers', 'status', answer_fixtures.address(job))
        assert status['job']['status'] == 'completed'
        post('answers', 'events', {**answer_fixtures.address(job), 'after_cursor': 0, 'limit': 2})
        post('answers', 'list', fixture.address(run))
        post('answers', 'cancel', {**answer_fixtures.address(job), 'idempotency_key': str(uuid.uuid4())})
        receipt = post('evidence', 'list', {**fixture.address(run), 'input_version': 1})['items'][0]
        address = {'receipt_id': receipt['id'], 'expected_sha256': receipt['sha256']}
        post('evidence', 'open', address)
        post('evidence', 'page', {**address, 'section': 'inputs', 'offset': 0, 'limit': 2})
        exported = post('evidence', 'export', {**address, 'format': 'csv', 'section': 'inputs', 'offset': 0, 'limit': 2})
        assert hashlib.sha256(exported['content_text'].encode()).hexdigest() == exported['content_sha256']
    assert len(capture) == 9 and threads and all(thread not in {caller, app.state.loop_thread} for thread in threads)
    output = os.environ.get('C21_WIRE_CAPTURE')
    if output:
        root = Path(__file__).resolve().parents[1]
        sources = [*root.glob('schema/research_evidence.py'), *root.glob('orchestration/research_*.py'),
                   root / 'orchestration/catalogue_service.py', root / 'api/research_evidence_routes.py']
        value = {'kind': 'actual-local-synthetic-http-capture', 'independent_scientific_review': False,
                 'sources': {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in sorted(sources)}, 'actions': capture}
        with Path(output).open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)


@pytest.mark.parametrize('raw', [b'{"limit":1,"limit":2}', b'{"limit":NaN}', b'null', b'[]',
                               b'{"cursor":"\\udfff"}', b'{}' + b' ' * 65536])
def test_invalid_or_excessive_body_never_enters_service(http, monkeypatch, raw):
    app, _, _, _, answers = http
    monkeypatch.setattr(answers, 'invoke', lambda *_: pytest.fail('Invalid body dispatched'))
    with TestClient(app) as client:
        response = client.post('/research/answers/list', content=raw)
    assert response.status_code == 422 and response.json()['error']['code'] == 'invalid_request'


@pytest.mark.parametrize('permissions', [frozenset(), frozenset({'chat:use'}), frozenset({'data:read'}),
                                      frozenset({'data:export'})])
def test_current_dual_permission_precedes_body_and_export(http, permissions):
    app, state, fixture, _, _ = http
    state['user'] = replace(fixture.user, permissions=permissions)
    with TestClient(app) as client:
        for path in ('/research/answers/submit', '/research/evidence/export'):
            response = client.post(path, content=b'private malformed body')
            assert response.status_code == 403 and 'private' not in response.text


def test_fresh_export_permission_and_synthesis_disabled_history(http, monkeypatch):
    app, state, fixture, evidence, answers = http
    run, data = answer_fixtures.request(fixture)
    job = answers.invoke('submit', data, fixture.user)['job']
    answers.execute_delivery(**answer_fixtures.delivery(fixture, job))
    receipt = evidence.ensure_retained(run['id'], 1, fixture.user).receipts[0]
    address = {'receipt_id': receipt.id, 'expected_sha256': receipt.sha256}
    monkeypatch.setenv('ENABLE_V1_SYNTHESIS', 'false')
    with TestClient(app) as client:
        assert client.post('/research/answers/status', json=answer_fixtures.address(job)).status_code == 200
        assert client.post('/research/evidence/open', json=address).status_code == 200
        # Exact acknowledgement recovery remains a read of the existing input;
        # new request keys cannot dispatch while the synthesis gate is paused.
        assert client.post('/research/answers/submit', json=data).status_code == 200
        assert client.post('/research/answers/submit', json={**data, 'idempotency_key': str(uuid.uuid4())}).status_code == 503
        state['user'] = replace(fixture.user, permissions=fixture.user.permissions - {'data:export'})
        assert client.post('/research/evidence/export', json=address).status_code == 403
        # C20 binds the complete original actor epoch: membership changes also
        # fail history closed until a fresh authorized context is selected.
        assert client.post('/research/answers/status', json=answer_fixtures.address(job)).status_code == 403


@pytest.mark.parametrize('path,scope,limit', [
    ('answers/submit', 'answer_dispatch', 10), ('answers/cancel', 'answer_cancel', 30),
    ('evidence/export', 'evidence_export', 30), ('answers/status', 'answer_evidence_history', 240),
    ('answers/events', 'answer_evidence_history', 240), ('answers/list', 'answer_evidence_history', 240),
    ('evidence/list', 'answer_evidence_history', 240), ('evidence/open', 'answer_evidence_history', 240),
    ('evidence/page', 'answer_evidence_history', 240),
])
def test_fixed_route_and_rate_policy(path, scope, limit):
    policy = policy_for_request('POST', '/research/' + path)
    assert policy.scope == scope and policy.limit == limit
    assert auth.route_permission('POST', '/research/' + path + '/') is None
    assert auth.route_permission('GET', '/research/' + path) is None
