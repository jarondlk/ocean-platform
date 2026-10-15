"""C06 acceptance across actual adapters, API receipts and planner validation."""
from __future__ import annotations

import json
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
import pytest

import api.auth as api_auth
import api.main as api_main
import config
import model_runtime
import orchestration.settings_planner as planner
from api.schemas import ChatRequest
from db.app_models import ChatInteraction
from tests.test_auto_settings import catalogue, proposal
from tests.test_chat_feedback import _add_user, _database, _install_database, _stub_chat_dependencies
from tests.test_chat_source_scope import scope


class Payload:
    def __init__(self, value):
        self.value = value

    def raise_for_status(self):
        pass

    def json(self):
        return self.value


def install_runtime(monkeypatch, provider, reason, *, content='Synthetic salinity: 34 PSU [S1].', usage=True,
                    failed=False):
    calls = []

    def invoke(**kwargs):
        calls.append(kwargs)
        if failed:
            raise RuntimeError('private-prompt-or-credential-must-not-escape')
        if provider == 'ollama':
            payload = {'message': {'content': content}, 'done': True}
            if reason is not None:
                payload['done_reason'] = reason
            if usage:
                payload.update(prompt_eval_count=11, eval_count=7)
            return Payload(payload)
        return SimpleNamespace(text=content,
                               candidates=[SimpleNamespace(finish_reason=reason)],
                               usage_metadata=SimpleNamespace(prompt_token_count=11,
                                                              candidates_token_count=7,
                                                              total_token_count=18) if usage else None)

    if provider == 'ollama':
        monkeypatch.setattr(model_runtime.requests, 'post', lambda *args, **kwargs: invoke(**kwargs))
        runtime = model_runtime.OllamaRuntime('http://synthetic.invalid')
    else:
        client = SimpleNamespace(models=SimpleNamespace(generate_content=invoke))
        runtime = model_runtime.VertexRuntime(project='fixture', location='global', embedding_dim=2,
                                             client=client)
    monkeypatch.setattr(api_main, 'get_model_runtime', lambda: runtime)
    monkeypatch.setattr(planner, 'get_model_runtime', lambda: runtime)
    return calls


@pytest.fixture
def persisted_api(monkeypatch):
    factory = _database()
    user = _add_user(factory, 'c06-synthetic@example.invalid')
    _install_database(monkeypatch, factory)
    _stub_chat_dependencies(monkeypatch)
    monkeypatch.setattr(api_auth, 'authenticate_request', lambda _: user)
    monkeypatch.setattr(config, 'AUTO_SETTINGS_ENABLED', True)
    monkeypatch.setattr(planner, 'planner_catalog', catalogue)
    with TestClient(api_main.app) as client:
        yield client, factory
    factory.kw['bind'].dispose()


def chat(client, **changes):
    payload = {'query': 'Describe CTD salinity', 'settings_mode': 'manual',
               'evidence_scope': scope('ctd'), 'run_answer_audit': False,
               'inject_analysis': False, 'inject_reliability': False}
    payload.update(changes)
    return client.post('/chat', json=payload)


@pytest.mark.parametrize('provider,reason,status', [
    ('ollama', 'length', 'output_limited'), ('vertex', 'MAX_TOKENS', 'output_limited'),
    ('ollama', None, 'unknown'), ('vertex', None, 'unknown'),
    ('ollama', 'synthetic-unknown', 'unknown'), ('vertex', 'synthetic-unknown', 'unknown'),
    ('vertex', 'SAFETY', 'refused'),
])
def test_incomplete_actual_adapter_never_creates_completed_answer(monkeypatch, persisted_api,
                                                                  provider, reason, status):
    calls = install_runtime(monkeypatch, provider, reason)
    client, factory = persisted_api
    response = chat(client)
    assert response.status_code == 502, response.text
    detail = response.json()['detail']
    assert detail['code'] == ('llm_output_limit' if status == 'output_limited' else 'llm_request_failed')
    assert len(calls) == 1
    assert 'Synthetic salinity' not in response.text
    with factory() as session:
        row = session.get(ChatInteraction, uuid.UUID(detail['interaction_id']))
        assert row.status == 'failed' and row.answer is None and row.outcome is None
        assert row.answer_audit_snapshot is None
        metadata = row.request_options['generation_result']
        assert metadata['provider'] == provider and metadata['status'] == status
        assert metadata['elapsed_seconds'] >= 0
        assert 'content' not in metadata and 'Synthetic salinity' not in json.dumps(metadata)


@pytest.mark.parametrize('provider,reason', [('ollama', 'stop'), ('vertex', 'STOP')])
@pytest.mark.parametrize('usage', [True, False])
def test_completed_metadata_and_optional_usage_persist_with_answer(monkeypatch, persisted_api,
                                                                  provider, reason, usage):
    calls = install_runtime(monkeypatch, provider, reason, usage=usage)
    client, factory = persisted_api
    response = chat(client)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['outcome'] == 'answered' and len(calls) == 1
    metadata = data['options']['generation_result']
    assert metadata['provider'] == provider and metadata['status'] == 'completed'
    assert metadata['finish_reason'] == reason and metadata['elapsed_seconds'] >= 0
    assert 'content' not in metadata
    if usage:
        assert metadata['usage']['input_tokens'] == 11 and metadata['usage']['output_tokens'] == 7
    else:
        assert metadata['usage'] is None
    with factory() as session:
        row = session.get(ChatInteraction, uuid.UUID(data['interaction_id']))
        assert row.status == 'completed' and row.answer == data['answer']
        assert row.request_options['generation_result'] == metadata


@pytest.mark.parametrize('provider', ['ollama', 'vertex'])
def test_transport_failure_is_private_and_recorded_without_retries(monkeypatch, persisted_api, caplog, provider):
    calls = install_runtime(monkeypatch, provider, None, failed=True)
    client, factory = persisted_api
    response = chat(client)
    assert response.status_code == 502 and len(calls) == 1
    assert 'private-prompt-or-credential' not in response.text + caplog.text
    with factory() as session:
        row = session.get(ChatInteraction, uuid.UUID(response.json()['detail']['interaction_id']))
        assert row.status == 'failed' and row.answer is None
        assert row.request_options['generation_result']['status'] == 'failed'
        assert 'private-prompt-or-credential' not in json.dumps(row.request_options)


def test_completed_generation_can_fail_citation_acceptance_without_losing_usage(monkeypatch, persisted_api):
    install_runtime(monkeypatch, 'ollama', 'stop', content='Unrecognized claim [S999].')
    client, factory = persisted_api
    response = chat(client)
    assert response.status_code == 502
    detail = response.json()['detail']
    assert detail['code'] == 'llm_invalid_citation'
    with factory() as session:
        row = session.get(ChatInteraction, uuid.UUID(detail['interaction_id']))
        assert row.status == 'failed' and row.answer is None
        assert row.request_options['generation_result']['status'] == 'completed'
        assert row.request_options['generation_result']['usage']['output_tokens'] == 7


@pytest.mark.parametrize('provider,reason,status', [
    ('ollama', 'length', 'output_limited'), ('vertex', 'MAX_TOKENS', 'output_limited'),
    ('ollama', None, 'unknown'), ('vertex', None, 'unknown'),
    ('ollama', 'synthetic-unknown', 'unknown'), ('vertex', 'SAFETY', 'refused'),
])
def test_parseable_but_incomplete_plan_cannot_run_retrieval(monkeypatch, persisted_api,
                                                          provider, reason, status):
    calls = install_runtime(monkeypatch, provider, reason, content=json.dumps(proposal()))
    monkeypatch.setattr(api_main, 'retrieve_with_expansion', lambda *a, **kw: pytest.fail('incomplete plan executed'))
    client, factory = persisted_api
    response = chat(client, settings_mode='auto')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['outcome'] == 'abstained' and not data['model_invoked']
    assert data['options']['planning']['status'] == 'unavailable'
    assert len(calls) == 1
    metadata = data['options']['planning']['generation_result']
    assert metadata['status'] == status and metadata['provider'] == provider
    with factory() as session:
        row = session.get(ChatInteraction, uuid.UUID(data['interaction_id']))
        # Existing deterministic abstention completes its lifecycle; no model
        # answer generation or completed answer receipt is fabricated.
        assert row.status == 'completed' and row.outcome == 'abstained'
        assert row.request_options['planning']['generation_result'] == metadata
        assert 'generation_result' not in row.request_options


@pytest.mark.parametrize('provider,reason', [('ollama', 'stop'), ('vertex', 'STOP')])
def test_completed_planner_exposes_generation_metadata(monkeypatch, provider, reason):
    install_runtime(monkeypatch, provider, reason, content=json.dumps(proposal()))
    monkeypatch.setattr(config, 'AUTO_SETTINGS_ENABLED', True)
    monkeypatch.setattr(planner, 'planner_catalog', catalogue)
    effective, metadata = planner.plan_settings(ChatRequest(query='CTD salinity', settings_mode='auto',
                                                           evidence_scope=scope()))
    assert effective.evidence_scope.sources.ctd.enabled
    assert metadata['generation_result']['status'] == 'completed'
    assert metadata['generation_result']['usage']['output_tokens'] == 7


def test_deterministic_planning_does_not_fabricate_generation_metadata(monkeypatch):
    from orchestration.settings_plan import SettingsProposal

    monkeypatch.setattr(config, 'AUTO_SETTINGS_ENABLED', True)
    monkeypatch.setattr(config, 'AUTO_EXACT_WORKFLOWS_ENABLED', True)
    monkeypatch.setattr(planner, 'planner_catalog', catalogue)
    monkeypatch.setattr(planner, 'exact_catalogue_plan',
                        lambda *args: (SettingsProposal.model_validate(proposal()), {'analysis_id': 'synthetic'}))
    monkeypatch.setattr(planner, 'get_model_runtime', lambda: pytest.fail('deterministic plan invoked model'))
    _, metadata = planner.plan_settings(ChatRequest(query='CTD salinity', settings_mode='auto',
                                                   evidence_scope=scope()))
    assert metadata['deterministic_match'] and not metadata['planner_invoked']
    assert 'generation_result' not in metadata


def test_completed_provider_text_still_requires_valid_planner_json(monkeypatch):
    install_runtime(monkeypatch, 'ollama', 'stop', content='not valid JSON')
    monkeypatch.setattr(config, 'AUTO_SETTINGS_ENABLED', True)
    monkeypatch.setattr(planner, 'planner_catalog', catalogue)
    with pytest.raises(planner.PlanningError) as failure:
        planner.plan_settings(ChatRequest(query='CTD salinity', settings_mode='auto', evidence_scope=scope()))
    assert failure.value.status == 'invalid'
    assert failure.value.generation_result['status'] == 'completed'
    assert failure.value.generation_result['usage']['output_tokens'] == 7
