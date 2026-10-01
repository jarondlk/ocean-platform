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
