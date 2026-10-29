"""C25 real owner-authorized interfaces with explicit durable synthetic bytes.

No executor, remote worker, physical termination or cloud service is exercised.
"""
import base64
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select, text

from api import auth, experiment_workspace_routes as routes
from api.rate_limit import policy_for_request
from api.v1_runtime_routes import V1RuntimeConfiguration, _research_experiments
from db.app_models import AppBase, AppUser, ResearchExperimentReservation
from orchestration.experiment_workspace import ExperimentWorkspaceError, ExperimentWorkspaceService
from orchestration.research_experiments import ResearchExperimentError
from schema.experiment_workspace import (
    CancellationAcknowledgement, ExecutionArtifactResponse, ExecutionCapability,
    ExecutionSnapshot, MAX_ARTIFACT_CHUNK, TablePreview,
)
from schema.research_experiments import ExperimentDispatchSnapshot
from tests.experiment_workspace_support import DurableSyntheticExecutionPort
from tests.research_experiment_support import make_experiment_fixture


@pytest.fixture(scope='module')
def retained(tmp_path_factory):
    directory = tmp_path_factory.mktemp('c25-durable-synthetic')
    engine = create_engine('sqlite+pysqlite:///' + str(directory / 'app.sqlite'))
    @event.listens_for(engine, 'connect')
    def keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    AppBase.metadata.create_all(engine)
    fixture = make_experiment_fixture(engine, directory)
    port = DurableSyntheticExecutionPort(experiments=fixture.service, path=directory / 'projections.sqlite')
    yield fixture, port
    engine.dispose()


@pytest.fixture
def actual(retained, monkeypatch):
    for name in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS'):
        monkeypatch.setenv(name, 'true')
    monkeypatch.setenv('DEPLOYMENT_ENV', 'development')
    fixture, port = retained
    fixture.state.update(enabled=True, dispatch_enabled=True)
    for denied in fixture.retained.policy.values():
        denied.clear()
    fixture.investigations.artifact_resolver = port.resolve_artifact
    workspace = ExperimentWorkspaceService(experiments=fixture.service, port=port, enabled=lambda: True)
    return fixture, port, workspace


def prepared(actual, *, state='running', raw=None, approve=True):
    fixture, port, workspace = actual
    experiment = fixture.create()
    if approve:
        experiment = fixture.service.invoke('approve', fixture.decision(experiment), fixture.user)['experiment']
    request = fixture.decision(experiment)
    request.pop('idempotency_key')
    access = workspace._access(request, fixture.user)
    files = [('summary.json', 'application/json', raw)] if raw is not None else None
    projection = port.seed(access, state=state, files=files)
    return experiment, request, access, projection


def invoke(actual, name, payload):
    return actual[2].invoke(name, payload, actual[0].user)


def test_unconfigured_unavailable_never_discovers_a_fixture(actual):
    fixture, _, _ = actual
    experiment = fixture.create()
    request = fixture.decision(experiment)
    request.pop('idempotency_key')
    absent = ExperimentWorkspaceService(experiments=fixture.service, enabled=lambda: True)
    assert absent.invoke('capability', {}, fixture.user)['capability']['transport'] == 'unavailable'
    status = absent.invoke('status', request, fixture.user)
    assert status['execution'] is None and status['capability']['start_enabled'] is False
    with pytest.raises(ExperimentWorkspaceError):
        absent.invoke('events', {**request, 'execution_id': str(uuid.uuid4())}, fixture.user)


def test_bound_durable_status_events_cancel_retry_and_no_termination(actual):
    fixture, port, workspace = actual
    experiment, request, access, initial = prepared(actual)
    reserved = fixture.service.invoke('dispatch', fixture.decision(experiment), fixture.user)['experiment']['dispatch']
    assert invoke(actual, 'status', request)['execution']['id'] == initial['id']
    cancel = {**request, 'execution_id': initial['id'], 'idempotency_key': str(uuid.uuid4())}
    acknowledgement = invoke(actual, 'cancel', cancel)
    assert acknowledgement['cancellation'] == {'idempotency_key': cancel['idempotency_key'],
        'status': 'requested', 'termination_confirmed': False}
    assert acknowledgement['execution']['state'] == 'cancelling'
    assert acknowledgement['execution']['termination_verified'] is False
    assert not fixture.executor.deliveries
    reopened_port = DurableSyntheticExecutionPort(experiments=fixture.service, path=port.path)
    reopened = ExperimentWorkspaceService(experiments=fixture.service, port=reopened_port, enabled=lambda: True)
    assert reopened.invoke('cancel', cancel, fixture.user) == acknowledgement
    page = workspace.invoke('events', {**request, 'execution_id': initial['id'], 'limit': 1}, fixture.user)
    assert page['next_cursor'] == 1 and page['has_more']
    tail = workspace.invoke('events', {**request, 'execution_id': initial['id'], 'after_cursor': 1}, fixture.user)
    assert tail['items'][0]['kind'] == 'cancel_requested' and not tail['has_more']
    with fixture.factory() as session:
        reservation = session.scalar(select(ResearchExperimentReservation).where(
            ResearchExperimentReservation.experiment_id == uuid.UUID(access.experiment_id)))
        assert str(reservation.id) == reserved['reservation_id'] and reservation.state == 'reserved'
    # Explicit SQLite-only fixture cleanup after the unchanged-capacity
    # assertion. No C25 operation or physical-release claim performs this SQL.
    with fixture.factory.begin() as session:
        session.execute(text("UPDATE research_experiment_reservation SET state='released' WHERE id=:id"),
            {'id': uuid.UUID(reserved['reservation_id']).hex})


def test_uncertain_cancel_commit_retries_same_durable_intent(actual, monkeypatch):
    _, port, _ = actual
    _, request, _, initial = prepared(actual)
    cancel = {**request, 'execution_id': initial['id'], 'idempotency_key': str(uuid.uuid4())}
    original = port.cancel
    def uncertain(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError('synthetic lost response after durable request commit')
    monkeypatch.setattr(port, 'cancel', uncertain)
    with pytest.raises(ResearchExperimentError):
        invoke(actual, 'cancel', cancel)
    monkeypatch.setattr(port, 'cancel', original)
    replay = invoke(actual, 'cancel', cancel)
    assert replay['execution']['state_revision'] == replay['execution']['latest_event_cursor'] == 2
    assert replay['cancellation']['termination_confirmed'] is False
    _, another, _, other_execution = prepared(actual)
    with pytest.raises(ExperimentWorkspaceError) as failed:
        invoke(actual, 'cancel', {**another, 'execution_id': other_execution['id'], 'idempotency_key': cancel['idempotency_key']})
    assert failed.value.status_code == 409


def test_exact_revision_context_hash_and_owner_checks(actual):
    fixture, _, workspace = actual
    _, request, _, initial = prepared(actual)
    for actor in (fixture.other, fixture.admin):
        with pytest.raises(ResearchExperimentError) as failure:
            workspace.invoke('status', request, actor)
        assert failure.value.status_code == 404
    for key, value in [('expected_version', request['expected_version'] + 1), ('context_payload_sha256', '0' * 64)]:
        with pytest.raises(ResearchExperimentError) as failure:
            invoke(actual, 'status', {**request, key: value})
        assert failure.value.status_code == 409
    changed = deepcopy(request)
    changed['expected_hashes']['code_sha256'] = '0' * 64
    with pytest.raises(ResearchExperimentError):
        invoke(actual, 'cancel', {**changed, 'execution_id': initial['id'], 'idempotency_key': str(uuid.uuid4())})


@pytest.mark.parametrize('state', ['running', 'completed'])
def test_historical_execution_reopens_after_proposal_revision_without_identity_drift(actual, monkeypatch, state):
    """A head concurrency version changes; the approved execution identity does not."""
    fixture, port, workspace = actual
    raw = b'{"columns":["int64"],"rows":[[9223372036854775807]]}' if state == 'completed' else None
    approved, old_request, old_access, original_execution = prepared(actual, state=state, raw=raw)
    revision = {**approved['binding'], 'experiment_id': approved['id'],
        'expected_version': approved['version'], 'expected_proposal_revision_id': approved['proposal_revision_id'],
        'proposal': {**approved['proposal'], 'method': 'New revision B needs a separate approval'},
        'idempotency_key': str(uuid.uuid4())}
    changed = fixture.service.invoke('revise', revision, fixture.user)['experiment']
    historical = fixture.service.invoke('get', {'experiment_id': approved['id'],
        'proposal_revision_id': approved['proposal_revision_id']}, fixture.user)['experiment']
    assert historical['version'] == changed['version'] == approved['version'] + 1
    assert historical['proposal_revision_id'] == approved['proposal_revision_id']
    assert historical['proposal'] == approved['proposal'] and historical['hashes'] == approved['hashes']
    request = fixture.decision(historical)
    request.pop('idempotency_key')
    current_access = workspace._access(request, fixture.user)
    assert current_access.proposal_version != old_access.proposal_version
    assert current_access.sha256 == old_access.sha256
    assert current_access.approval_id == old_access.approval_id
    assert current_access.approval_request_sha256 == old_access.approval_request_sha256
    status = invoke(actual, 'status', request)
    assert status['proposal_version'] == historical['version']
    assert status['execution'] == original_execution
    events = invoke(actual, 'events', {**request, 'execution_id': original_execution['id']})
    assert events['items'][0]['cursor'] == 1 and events['latest_event_cursor'] == 1
    if state == 'completed':
        item = original_execution['artifacts'][0]
        artifact_request = {**request, 'execution_id': original_execution['id'],
            'artifact_id': item['id'], 'expected_sha256': item['sha256']}
        artifact = invoke(actual, 'artifact', artifact_request)
        assert base64.b64decode(artifact['content_base64']) == raw
        assert artifact['preview']['rows'] == [['9223372036854775807']]
        assert artifact['artifact'] == item
        attached = fixture.investigations.invoke('context/change', {
            'investigation_id': request['investigation_id'], 'expected_revision_id': request['context_revision_id'],
            'idempotency_key': str(uuid.uuid4()), 'change': {'op': 'attach',
                'reference': item['attachment_reference']}}, fixture.user)
        assert attached['context']['attachments'] == [item['attachment_reference']]
        assert attached['context']['resolution'][0]['status'] == 'available'
        assert invoke(actual, 'artifact', artifact_request) == artifact
    cancelled = invoke(actual, 'cancel', {**request, 'execution_id': original_execution['id'],
        'idempotency_key': str(uuid.uuid4())})
    assert cancelled['cancellation']['termination_confirmed'] is False
    if state == 'completed':
        assert cancelled['cancellation']['status'] == 'already_terminal'
        assert cancelled['execution'] == original_execution
    else:
        assert cancelled['cancellation']['status'] == 'requested'
        assert cancelled['execution']['state'] == 'cancelling'
        assert cancelled['execution']['termination_verified'] is False
    with pytest.raises(ResearchExperimentError) as stale:
        invoke(actual, 'status', old_request)
    assert stale.value.status_code == 409
    with pytest.raises(ResearchExperimentError) as hidden:
        workspace.invoke('status', request, fixture.other)
    assert hidden.value.status_code == 404

    # An outward read cannot close authority using the earlier head version.
    original_status = port.status
    def racing_status(*args, **kwargs):
        value = original_status(*args, **kwargs)
        next_revision = {**changed['binding'], 'experiment_id': changed['id'],
            'expected_version': changed['version'], 'expected_proposal_revision_id': changed['proposal_revision_id'],
            'proposal': {**changed['proposal'], 'method': 'Concurrent revision C'},
            'idempotency_key': str(uuid.uuid4())}
        # Context attachment changed the active context in the completed case;
        # the historical binding remains readable, but revising requires the
        # currently active context binding.
        if state == 'completed':
            context = attached['context']
            next_revision.update(context_revision_id=context['id'], context_payload_sha256=context['payload_sha256'])
        fixture.service.invoke('revise', next_revision, fixture.user)
        return value
    monkeypatch.setattr(port, 'status', racing_status)
    with pytest.raises(ResearchExperimentError) as raced:
        invoke(actual, 'status', request)
    assert raced.value.status_code == 409


@pytest.mark.parametrize('operation', ['status', 'artifact'])
def test_revoked_during_outward_read_cannot_receive_projection(actual, monkeypatch, operation):
    fixture, port, _ = actual
    _, request, _, projection = prepared(actual, state='completed', raw=b'{"columns":["x"],"rows":[[1]]}')
    original = getattr(port, operation)
    def revoked(*args, **kwargs):
        value = original(*args, **kwargs)
        with fixture.factory.begin() as session:
            session.get(AppUser, fixture.user.id).status = 'suspended'
        return value
    monkeypatch.setattr(port, operation, revoked)
    payload = request if operation == 'status' else {**request, 'execution_id': projection['id'],
        'artifact_id': projection['artifacts'][0]['id'], 'expected_sha256': projection['artifacts'][0]['sha256']}
    try:
        with pytest.raises(ResearchExperimentError) as failure:
            invoke(actual, operation, payload)
        assert failure.value.status_code == 403
    finally:
        with fixture.factory.begin() as session:
            session.get(AppUser, fixture.user.id).status = 'active'


def test_cancel_closing_authority_failure_rolls_back_intent(actual, monkeypatch):
    _, port, workspace = actual
    _, request, access, initial = prepared(actual)
    original = workspace._authorized
    calls = []
    def denied(*args, **kwargs):
        calls.append(True)
        if len(calls) >= 3:
            raise ExperimentWorkspaceError('access_denied', 403)
        return original(*args, **kwargs)
    monkeypatch.setattr(workspace, '_authorized', denied)
    with pytest.raises(ResearchExperimentError):
        invoke(actual, 'cancel', {**request, 'execution_id': initial['id'], 'idempotency_key': str(uuid.uuid4())})
    assert len(calls) == 3
    assert port.status(access)['execution']['state'] == 'running'
    assert port.status(access)['execution']['latest_event_cursor'] == 1


def test_artifact_exact_bytes_display_int64_chunks_and_attachment(actual):
    fixture, _, _ = actual
    raw = b'{"columns":["int64","missing"],"rows":[[9223372036854775807,null]]}'
    _, request, _, initial = prepared(actual, state='completed', raw=raw)
    item = initial['artifacts'][0]
    payload = {**request, 'execution_id': initial['id'], 'artifact_id': item['id'], 'expected_sha256': item['sha256'], 'limit': 11}
    response = invoke(actual, 'artifact', payload)
    assert response['artifact']['attachment_reference'] is not None
    assert response['preview']['rows'] == [['9223372036854775807', None]]
    parts = [base64.b64decode(response['content_base64'])]
    while not response['eof']:
        response = invoke(actual, 'artifact', {**payload, 'offset': response['next_offset']})
        assert response['preview'] is None
        parts.append(base64.b64decode(response['content_base64']))
    assert b''.join(parts) == raw and hashlib.sha256(b''.join(parts)).hexdigest() == item['sha256']
    attached = fixture.investigations.invoke('context/change', {
        'investigation_id': request['investigation_id'], 'expected_revision_id': request['context_revision_id'],
        'idempotency_key': str(uuid.uuid4()), 'change': {'op': 'attach',
            'reference': response['artifact']['attachment_reference']}}, fixture.user)
    assert attached['context']['attachments'] == [response['artifact']['attachment_reference']]
    assert attached['context']['resolution'][0]['status'] == 'available'
    fixture.investigations.artifact_resolver = None
    assert invoke(actual, 'status', request)['execution']['artifacts'][0]['attachment_reference'] is None
    assert invoke(actual, 'artifact', payload)['artifact']['attachment_reference'] is None


@pytest.mark.parametrize('raw', [b'<html>unsafe</html>', b'{"columns":["x"],"rows":[[1,2]]}', b'{"columns":["x"],"rows":[[NaN]]}'])
def test_unvalidated_artifact_bytes_are_not_exposed(actual, raw):
    _, request, _, initial = prepared(actual, state='completed', raw=raw)
    item = initial['artifacts'][0]
    with pytest.raises(ResearchExperimentError) as failure:
        invoke(actual, 'artifact', {**request, 'execution_id': initial['id'], 'artifact_id': item['id'], 'expected_sha256': item['sha256']})
    assert failure.value.code == 'integrity_error'


def test_hash_drift_undeclared_output_and_no_approval_closed(actual, monkeypatch):
    _, port, _ = actual
    _, request, _, initial = prepared(actual, state='completed', raw=b'{"columns":["x"],"rows":[]}')
    item = initial['artifacts'][0]
    monkeypatch.setattr(port, 'artifact', lambda *_: b'changed')
    with pytest.raises(ResearchExperimentError):
        invoke(actual, 'artifact', {**request, 'execution_id': initial['id'], 'artifact_id': item['id'], 'expected_sha256': item['sha256']})
    original = port.status
    def wrong(*args):
        value = original(*args)
        value['execution']['artifacts'][0]['name'] = 'undeclared.json'
        return value
    monkeypatch.setattr(port, 'status', wrong)
    with pytest.raises(ResearchExperimentError):
        invoke(actual, 'status', request)
    monkeypatch.setattr(port, 'status', original)
    _, unapproved, _, _ = prepared(actual, approve=False)
    with pytest.raises(ResearchExperimentError):
        invoke(actual, 'status', unapproved)


def test_synthetic_rejected_in_production_and_port_binding_current(actual, monkeypatch):
    fixture, port, workspace = actual
    monkeypatch.setenv('DEPLOYMENT_ENV', 'production')
    assert workspace.capability(fixture.user)['capability']['source'] == 'unavailable'
    monkeypatch.setenv('DEPLOYMENT_ENV', 'development')
    monkeypatch.setattr(port, 'session_factory', object())
    with pytest.raises(ExperimentWorkspaceError):
        workspace.capability(fixture.user)


def test_runtime_capability_flags_and_explicit_synthetic_source(actual):
    fixture, _, workspace = actual
    configuration = V1RuntimeConfiguration(site_id=fixture.service.site_id, revision='c25-test')
    capability = _research_experiments(configuration, fixture.user, 'ready', fixture.investigations, fixture.service, workspace)
    assert capability['proposal_transport'] == capability['execution_transport'] == 'http-v1'
    assert capability['execution_source'] == 'synthetic-fixture' and capability['start_enabled'] is False
    assert capability['approval_enabled'] and capability['cancel_enabled'] and capability['artifacts_enabled']
    fixture.state['dispatch_enabled'] = False
    no_approval = _research_experiments(configuration, fixture.user, 'ready', fixture.investigations, fixture.service, workspace)
    assert no_approval['proposal_transport'] == 'http-v1' and no_approval['approval_enabled'] is False
    assert no_approval['start_enabled'] is False
    fixture.state['dispatch_enabled'] = True
    fixture.state['enabled'] = False
    paused = _research_experiments(configuration, fixture.user, 'ready', fixture.investigations, fixture.service, None)
    assert paused['proposal_transport'] == 'http-v1' and not paused['approval_enabled']
    assert paused['execution_transport'] == 'unavailable'


def test_released_reservation_valid_c22_read_and_execution_view(actual):
    """Synthetic raw SQL sets a released read case; this proves no real release."""
    fixture, _, _ = actual
    experiment, request, _, initial = prepared(actual)
    dispatched = fixture.service.invoke('dispatch', fixture.decision(experiment), fixture.user)['experiment']
    assert dispatched['dispatch']['reservation_id']
    with fixture.factory.begin() as session:
        session.execute(text("UPDATE research_experiment_reservation SET state='released' WHERE experiment_id=:id"),
            {'id': uuid.UUID(experiment['id']).hex})
    retained = fixture.service.invoke('get', fixture.address(experiment), fixture.user)['experiment']
    assert retained['dispatch']['status'] == 'unavailable' and retained['dispatch']['reservation_id'] is None
    # The pre-fix projection combined unavailable with a retained reservation
    # ID, which the unchanged v1 contract correctly rejects.
    with pytest.raises(ValueError):
        ExperimentDispatchSnapshot.model_validate({**retained['dispatch'],
            'reservation_id': dispatched['dispatch']['reservation_id']})
    assert retained['execution_performed'] is False and retained['approval']['status'] == 'current'
    assert invoke(actual, 'status', request)['execution']['id'] == initial['id']


def test_schema_rejects_forged_claims_null_rows_chunk_corruption(actual):
    assert TablePreview.model_validate({'columns': ['x'], 'rows': [[None]], 'total_rows': 1, 'truncated': False})
    with pytest.raises(ValueError):
        TablePreview.model_validate({'columns': ['x'], 'rows': [None], 'total_rows': 1, 'truncated': False})
    with pytest.raises(ValueError):
        ExecutionCapability.model_validate({'transport': 'unavailable', 'source': 'unavailable',
            'start_enabled': 0, 'cancel_enabled': False, 'artifacts_enabled': False, 'reason': {'en': 'off', 'ja': '不可'}})
    with pytest.raises(ValueError):
        CancellationAcknowledgement.model_validate({'idempotency_key': str(uuid.uuid4()), 'status': 'requested', 'termination_confirmed': 0})
    _, request, _, initial = prepared(actual, state='completed', raw=b'{"columns":["x"],"rows":[]}')
    for changes in ({'execution_performed': True}, {'termination_verified': True, 'termination_proof_sha256': 'f' * 64}):
        with pytest.raises(ValueError):
            ExecutionSnapshot.model_validate({**initial, **changes})
    item = initial['artifacts'][0]
    valid = invoke(actual, 'artifact', {**request, 'execution_id': initial['id'], 'artifact_id': item['id'], 'expected_sha256': item['sha256']})
    for changes in ({'offset': 1}, {'next_offset': 1}, {'eof': False}, {'content_base64': base64.b64encode(b'changed').decode()}):
        with pytest.raises(ValueError):
            ExecutionArtifactResponse.model_validate({**valid, **changes})


@pytest.fixture
def http(actual, monkeypatch):
    fixture, _, workspace = actual
    monkeypatch.setenv('AUTH_MODE', 'required')
    state = {'user': fixture.user}
    monkeypatch.setattr(auth, 'authenticate_request', lambda request: state['user'])
    app = FastAPI()
    app.middleware('http')(auth.authorization_middleware)
    app.include_router(routes.router)
    app.state.research_experiment_service = fixture.service
    app.state.experiment_workspace_service = workspace
    return app, state, actual


def post(client, action, payload, status=200):
    response = client.post('/research/experiment-executions/' + action, json=payload)
    assert response.status_code == status, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    return response.json()


def test_all_five_authenticated_http_actions_with_wire_capture(http):
    app, _, actual = http
    running_experiment, running, _, running_view = prepared(actual)
    completed_experiment, complete, _, complete_view = prepared(actual, state='completed', raw=b'{"columns":["x"],"rows":[[9223372036854775807]]}')
    captures = []
    with TestClient(app) as client:
        def call(action, request):
            response = post(client, action, request)
            captures.append({'action': action, 'request': request, 'response': response})
            return response
        call('capability', {})
        call('status', running)
        call('events', {**running, 'execution_id': running_view['id'], 'limit': 1})
        call('cancel', {**running, 'execution_id': running_view['id'], 'idempotency_key': str(uuid.uuid4())})
        item = complete_view['artifacts'][0]
        call('artifact', {**complete, 'execution_id': complete_view['id'], 'artifact_id': item['id'], 'expected_sha256': item['sha256']})
    output = os.environ.get('C25_EXECUTION_WIRE_CAPTURE')
    if output:
        with Path(output).open('x') as stream:
            json.dump({'kind': 'actual-local-durable-synthetic-http', 'python_executed': False,
                'scientific_approval': 'not_independently_verified',
                'experiments': {'running': running_experiment, 'completed': completed_experiment},
                'actions': captures}, stream, ensure_ascii=False, indent=2)


@pytest.mark.parametrize('raw', [b'{"limit":1,"limit":2}', b'{"limit":NaN}', b'null', b'[]', b'{}' + b' ' * 65536])
def test_strict_body_bounds_before_service(http, monkeypatch, raw):
    app, _, actual = http
    monkeypatch.setattr(actual[2], 'invoke', lambda *_: pytest.fail('Invalid input reached service'))
    with TestClient(app) as client:
        response = client.post('/research/experiment-executions/capability', content=raw)
    assert response.status_code == 422


def test_http_owner_roles_unknown_query_limits_and_safe_failures(http, monkeypatch):
    app, state, actual = http
    fixture, _, workspace = actual
    _, request, _, _ = prepared(actual)
    with TestClient(app) as client:
        state['user'] = fixture.other
        post(client, 'status', request, 404)
        state['user'] = replace(fixture.user, permissions=fixture.user.permissions - {'data:export'})
        post(client, 'artifact', {}, 403)
        state['user'] = fixture.user
        assert client.post('/research/experiment-executions/start', json={}).status_code == 403
        assert client.get('/research/experiment-executions/status').status_code == 403
        assert client.post('/research/experiment-executions/status?execute=true', json=request).status_code == 422
        post(client, 'status', {**request, 'limit': MAX_ARTIFACT_CHUNK + 1}, 422)
        app.state.experiment_workspace_service = None
        post(client, 'status', request, 503)
        app.state.experiment_workspace_service = workspace
        def failed(*_):
            raise OSError('PRIVATE-CREDENTIALS-HOST-PATH')
        monkeypatch.setattr(workspace, 'invoke', failed)
        assert 'PRIVATE' not in str(post(client, 'status', request, 503))


def test_auth_and_rate_scopes_are_fixed():
    prefix = '/research/experiment-executions/'
    assert auth.route_permission('POST', prefix + 'status') == 'chat:use'
    assert auth.route_permission('POST', prefix + 'artifact') == 'data:export'
    assert auth.route_permission('POST', prefix + 'cancel') == 'data:export'
    assert auth.route_permission('POST', prefix + 'start') is None
    assert policy_for_request('POST', prefix + 'cancel').scope == 'experiment_cancel'
    assert policy_for_request('POST', prefix + 'artifact').scope == 'experiment_artifact'
