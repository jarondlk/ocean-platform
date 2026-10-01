"""The live QA queue must use validated controls and count actual attempts."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.schemas import ChatRequest
from evaluation.qa.run_v061_acceptance import GenerationBudgetExceeded, MeteredModels
from orchestration.edna_aggregation import freshness_question, plan_aggregation


def test_english_matrix_has_explicit_scopes_and_expected_routes():
    matrix = json.loads(Path("evaluation/qa/anemone_v061_questions.json").read_text())
    assert sum(case["repeat"] for case in matrix["cases"] if case["provider_generation"]) == 31
    assert matrix["provider_generation_limit"] == 33
    for case in matrix["cases"]:
        request = ChatRequest(**case["request"]).model_dump(exclude_none=True)
        assert request["evidence_scope"]
        if case["id"] == "freshness":
            assert freshness_question(request)
        elif case["provider_generation"]:
            assert plan_aggregation(request) is None, case["id"]
        else:
            plan = plan_aggregation(request)
            assert plan is not None, case["id"]
            if case["expected_kind"] == "answer":
                assert plan.clarification is None, case["id"]


def test_provider_budget_counts_failed_invocations_and_stops_before_next_call():
    actual_calls = []
    def generate(**kwargs):
        actual_calls.append(kwargs)
        if len(actual_calls) == 1:
            raise TimeoutError("fixture timeout")
        return SimpleNamespace(usage_metadata=None)
    meter = MeteredModels(SimpleNamespace(generate_content=generate), limit=2)
    with pytest.raises(TimeoutError):
        meter.generate_content(model="fixture")
    meter.generate_content(model="fixture")
    with pytest.raises(GenerationBudgetExceeded):
        meter.generate_content(model="fixture")
    assert len(actual_calls) == 2
    assert [call["status"] for call in meter.generations] == ["failed", "returned"]


def test_large_qa_evidence_is_chunked_and_round_trips_without_truncation(capsys):
    from evaluation.qa.run_v061_acceptance import decode_cases, emit_case
    payload = {'id': 'large', 'repeat': 1, 'issues': [], 'provider_calls': [],
        'latency_ms': 1, 'response': {'answer': 'measured', 'sources': [{'text': '海水🌊' * 30_000}]}}
    emit_case(payload)
    lines = capsys.readouterr().out.splitlines()
    assert all(len(line.encode()) < 50_000 for line in lines)
    assert decode_cases(lines) == [payload]
    chunks = [line for line in lines if line.startswith('V061_QA_CHUNK=')]
    with pytest.raises(ValueError, match='Incomplete'):
        decode_cases(chunks[:-1])
    corrupted = json.loads(chunks[0].split('=', 1)[1])
    corrupted['payload'] += 'corruption'
    with pytest.raises(ValueError, match='hash'):
        decode_cases(['V061_QA_CHUNK=' + json.dumps(corrupted), *chunks[1:]])


def test_actual_chat_generation_factory_uses_the_meter_and_enforces_budget(monkeypatch):
    import uuid
    import api.main as api
    import config
    from api.auth import CurrentUser, ROLE_PERMISSIONS
    from evaluation.qa.run_v061_acceptance import install_generation_meter
    from model_runtime import VertexRuntime
    monkeypatch.setattr(config, 'MODEL_PROVIDER', 'vertex')
    monkeypatch.setenv('PERSIST_LOCAL_CHAT', 'false')
    monkeypatch.setattr(api, 'get_model_runtime', api.get_model_runtime)
    doc = {'doc_id': 'ctd-qa-fixture', 'source_type': 'ctd', 'text': 'Temperature is 12 C.'}
    monkeypatch.setattr(api, 'retrieve_with_expansion', lambda *a, **k: {'primary': [doc], 'linked': [], 'diagnostics': {}})
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text='Temperature is 12 C [S1].', usage_metadata=None, candidates=[])
    runtime = VertexRuntime(project='fixture', location='global', embedding_dim=768,
        client=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    meter = install_generation_meter(runtime, 1)
    user = CurrentUser(id=uuid.UUID(int=0), email='qa@test.invalid', display_name=None,
        role='researcher', account_type='research', status='active', auth_provider='disabled',
        permissions=ROLE_PERMISSIONS['researcher'])
    from tests.test_chat_source_scope import scope
    result = api.chat(ChatRequest(query='Explain the measured temperature', evidence_scope=scope('ctd'),
        inject_analysis=False, inject_reliability=False), user=user)
    assert result.model_invoked and result.outcome == 'answered'
    assert len(calls) == len(meter.generations) == 1
    with pytest.raises(GenerationBudgetExceeded):
        api.get_model_runtime().chat(model='fixture', prompt='fixture')
    assert len(calls) == 1
