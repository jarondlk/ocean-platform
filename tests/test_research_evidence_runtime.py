"""C21 explicit bootstrap capability, independent history and dispatch gates."""
from fastapi.testclient import TestClient
import pytest

from orchestration.research_answers import FakeAnswerQueue, ResearchAnswerService
from orchestration.research_evidence import ResearchEvidenceService
from tests import test_research_run_runtime as run_runtime

application = run_runtime.application
research_application = run_runtime.research_application
runs_application = run_runtime.runs_application


@pytest.fixture
def evidence_application(runs_application, monkeypatch):
    app, state = runs_application
    monkeypatch.setenv('ENABLE_V1_EVIDENCE', 'true')
    monkeypatch.setenv('ENABLE_V1_SYNTHESIS', 'true')
    investigations = app.state.investigation_service
    evidence = ResearchEvidenceService(session_factory=investigations.session_factory,
        site_id=investigations.site_id, investigations=investigations, runs=app.state.research_run_service)
    answers = ResearchAnswerService(evidence=evidence, queue=FakeAnswerQueue())
    app.state.research_evidence_service, app.state.research_answer_service = evidence, answers
    return app, state


@pytest.mark.parametrize('gate', ['ready', 'evidence_disabled', 'evidence_invalid', 'synthesis_disabled',
    'synthesis_invalid', 'queue_missing', 'evidence_missing', 'answers_missing', 'answers_wrong',
    'evidence_store_mismatch', 'answer_store_mismatch', 'no_data', 'no_chat', 'controller_disabled'])
def test_real_matching_services_and_fresh_gates_without_database_discovery(evidence_application, monkeypatch, gate):
    app, state = evidence_application
    evidence, answers = app.state.research_evidence_service, app.state.research_answer_service
    for prefix in ('evidence', 'synthesis'):
        if gate in {prefix + '_disabled', prefix + '_invalid'}:
            monkeypatch.setenv('ENABLE_V1_' + prefix.upper(), 'false' if gate.endswith('disabled') else 'invalid')
    if gate == 'queue_missing':
        answers.queue = None
    elif gate == 'evidence_missing':
        app.state.research_evidence_service = None
    elif gate == 'answers_missing':
        app.state.research_answer_service = None
    elif gate == 'answers_wrong':
        app.state.research_answer_service = object()
    elif gate == 'evidence_store_mismatch':
        evidence.session_factory = object()
    elif gate == 'answer_store_mismatch':
        answers.session_factory = object()
    elif gate in {'no_data', 'no_chat'}:
        removed = 'data:read' if gate == 'no_data' else 'chat:use'
        state['user'] = run_runtime.user(permissions=state['user'].permissions - {removed})
    elif gate == 'controller_disabled':
        monkeypatch.setenv('ENABLE_V1_RESEARCH_CONTROLLER', 'false')
    with TestClient(app) as client:
        response = client.get('/v1/runtime')
    assert response.status_code == 200, response.text
    capability = response.json()['research_evidence']
    readable = gate in {'ready', 'synthesis_disabled', 'synthesis_invalid', 'queue_missing', 'controller_disabled'}
    dispatch = gate in {'ready', 'controller_disabled'}
    assert capability['transport'] == ('http-v1' if readable else 'unavailable')
    assert capability['submit_enabled'] is dispatch
    assert capability['synthesis'] == ('http-v1' if dispatch else 'unavailable')
    assert response.json()['research_runs']['synthesis'] == 'unavailable'


def test_capability_toggles_permission_revision_and_legacy_wire_stays_optional(evidence_application, monkeypatch):
    app, _ = evidence_application
    with TestClient(app) as client:
        first = client.get('/v1/runtime').json()
        monkeypatch.setenv('ENABLE_V1_SYNTHESIS', 'false')
        disabled = client.get('/v1/runtime').json()
        assert disabled['research_evidence']['transport'] == 'http-v1'
        assert disabled['permission_revision'] != first['permission_revision']
        app.state.research_evidence_service = app.state.research_answer_service = None
        absent = client.get('/v1/runtime').json()
    assert 'research_evidence' not in absent and absent['permission_revision'] != disabled['permission_revision']
