from copy import deepcopy

import config
from evaluation.edna_pilot import evaluate_records
from ingestion.edna_analysis_bundle import publish_analysis
from preprocessing.edna_analysis import build_analysis
from tests.test_edna_analysis import fixture


def test_pilot_requires_resolved_citations_human_review_and_live_evidence(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path)
    recipe, source = fixture()
    result = build_analysis(recipe, source)
    publish_analysis(result)
    identity = result["analysis_id"]
    citation = "analysis_edna_" + identity + "_diversity"
    cases = {"cases": [{"id": "diversity", "question": "Describe diversity."}]}
    record = {
        "case_id": "diversity",
        "kind": "live",
        "latency_ms": 500,
        "request": {"query": "Describe diversity.", "analysis_id": identity},
        "response": {
            "query": "Describe diversity.",
            "answer": "Richness is two [" + citation + "].",
            "sources": [],
            "model": "test-model",
            "n_sources": 0,
            "analysis_context": [
                {
                    "doc_id": citation,
                    "context_type": "analysis",
                    "analysis_id": identity,
                    "table": "diversity",
                    "result_ids": [result["tables"]["diversity"][0]["result_id"]],
                }
            ],
            "options": {"context": {"analysis_id": identity}},
        },
        "review": {
            "verdict": "accepted",
            "reviewer": "synthetic-reviewer",
            "reviewed_at": "2026-09-03",
            "notes": "Test fixture only.",
            "source_values_checked": True,
            "unsupported_scientific_claims": False,
        },
    }

    def resolve(_):
        return {"found": True, "trace": {"fixture": True}}

    assert evaluate_records(cases, [record], resolve_citation=resolve)["accepted"]
    for changed in (
        {**record, "review": {}},
        {**record, "kind": "synthetic"},
        {**record, "latency_ms": 999999},
        {**record, "response": {**record["response"], "answer": "No citation"}},
    ):
        assert not evaluate_records(cases, [changed], resolve_citation=resolve)[
            "accepted"
        ]
    assert not evaluate_records(
        cases, [record], resolve_citation=lambda _: {"found": False}
    )["accepted"]
    assert evaluate_records(cases, [], resolve_citation=resolve)["missing_cases"] == [
        "diversity"
    ]
    bad = deepcopy(record)
    bad["response"]["analysis_context"][0]["result_ids"] = ["0" * 64]
    assert (
        "context_result_mismatch"
        in evaluate_records(cases, [bad], resolve_citation=resolve)["results"][0][
            "errors"
        ]
    )
