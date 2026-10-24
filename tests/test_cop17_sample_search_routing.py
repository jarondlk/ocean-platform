"""Ordinary sample searches remain reachable beside exact COP17 geography.

Evidence and model output below are synthetic routing fixtures. They do not
establish the professor's historical Otsuchi sample, its date or its taxa.
"""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

import api.main as api
import config
from ingestion import edna_aggregate
from orchestration.catalogue_geography import plan_catalogue_geography
from orchestration.edna_aggregation import plan_aggregation, plan_location_count
from tests.test_chat_source_scope import scope


PROFESSOR_QUESTION = (
    "Find one ANEMONE eDNA sample from Otsuchi Bay in 2020 and list five "
    "fish taxa detected in it. Distinguish species-level and genus-level "
    "identifications, and cite the source."
)
ORDINARY_QUESTIONS = [
    PROFESSOR_QUESTION,
    "Find an ANEMONE eDNA sample from Otsuchi Bay in 2020 and list five fish taxa detected in it.",
    "List five fish taxa detected in one sample from Otsuchi Bay.",
    "Find one ANEMONE sample at a sampling location in 2020 and list fish taxa.",
    "Show fish taxa for one ANEMONE sample at this location.",
    "Where was the ANEMONE sample from Otsuchi Bay collected?",
    "Where is the sampling location for this ANEMONE sample?",
    "Where was one ANEMONE sample collected?",
    "Are ANEMONE samples from Otsuchi Bay suitable for comparing fish detections?",
    "List all fish taxa from one ANEMONE sample in the same area.",
    "Find an ANEMONE sample from a named sampling area and cite its source.",
    "2020年の大槌湾のANEMONE環境DNAサンプルを1件探し、検出された魚類5分類群を示してください。",
    "大槌湾で採水したANEMONEサンプルの種名と属名を示してください。",
    "このANEMONEサンプルの採水地点はどこですか？",
    "同じ地域で採取したANEMONEサンプル1件の魚類分類群をすべて示してください。",
    "大槌湾のANEMONEサンプルは魚類検出の比較に適していますか？",
]


@pytest.mark.parametrize("query", ORDINARY_QUESTIONS)
@pytest.mark.parametrize(
    "families", [("edna_metabarcoding",), ("edna_metabarcoding", "remote_sensing")]
)
def test_sample_search_does_not_enter_any_catalogue_aggregation(query, families):
    request = {"query": query, "evidence_scope": scope(*families)}
    assert plan_catalogue_geography(request) is None
    assert plan_location_count(request) is None
    assert plan_aggregation(request) is None


@pytest.mark.parametrize(
    "query",
    [
        "How many named sampling areas are available in Japan?",
        "How many bays have sampling data in 2020?",
        "Which bays in the north have sampling data?",
        "How many bays contain tuna?",
        "Are all the sampling locations in Sendai Bay?",
    ],
)
def test_real_geography_questions_keep_unresolved_scope_guards(query):
    plan = plan_catalogue_geography(
        {"query": query, "evidence_scope": scope("edna_metabarcoding")}
    )
    assert plan is not None
    assert plan.metric == "catalogue_geography"
    assert plan.clarification


def test_counting_samples_in_a_bay_is_not_counting_bays():
    request = {
        "query": "How many ANEMONE samples in Otsuchi Bay?",
        "evidence_scope": scope("edna_metabarcoding"),
    }
    assert plan_catalogue_geography(request) is None
    assert plan_location_count(request) is None
    plan = plan_aggregation(request)
    assert plan is not None and plan.clarification


@pytest.mark.parametrize("with_filters", [False, True])
@pytest.mark.parametrize(
    "families", [("edna_metabarcoding",), ("edna_metabarcoding", "remote_sensing")]
)
def test_exact_professor_question_reaches_retrieval_and_cited_model_answer(
    monkeypatch, with_filters, families
):
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", True)
    chosen = scope(*families)
    if with_filters:
        chosen["sources"]["edna_metabarcoding"]["filters"] = {
            "provider": "anemone",
            "provider_project_id": "synthetic-routing-project",
            "assignment_method": "qcauto_95pct_3nn_target",
            "time_from": "2020-01-01",
            "time_to": "2020-12-31",
            "is_control": False,
        }
    original_scope = deepcopy(chosen)
    document = {
        "doc_id": "edna_synthetic_sample_search",
        "source_type": "edna_metabarcoding",
        "sample_id": "synthetic-routing-sample",
        "assay_id": "synthetic-routing-assay",
        "title": "Synthetic routing fixture, not a historical Otsuchi record",
        "provider": "anemone",
        "provider_project_id": "synthetic-routing-project",
        "assignment_method": "qcauto_95pct_3nn_target",
        "time": "2020-04-12T00:00:00Z",
        "sample_kind": "unknown",
        "is_control": False,
        "text": (
            "Synthetic routing fixture sample synthetic-routing-sample, assay "
            "synthetic-routing-assay, assignment method qcauto_95pct_3nn_target. "
            "Five fixture fish assignment labels: Fixtureichthys alpha "
            "(species-level), Fixtureichthys beta (species-level), "
            "Fixtureichthys gamma (species-level), Examplogobius "
            "(genus-level), Testoblennius (genus-level). "
            "These labels are synthetic and do not describe a real sample."
        ),
        "metadata": {"source_family": "edna_metabarcoding"},
    }
    calls = {"retrieval": [], "model": [], "history": []}

    def forbidden_aggregate(*args, **kwargs):
        pytest.fail("an ordinary sample search must not build an exact aggregate")

    def retrieve(query, **options):
        calls["retrieval"].append((query, deepcopy(options)))
        return {"primary": [document], "linked": [], "diagnostics": {}}

    class Runtime:
        def chat(self, **options):
            calls["model"].append(options)
            return (
                "Synthetic fixture sample synthetic-routing-sample has the "
                "following five illustration labels: Fixtureichthys alpha, "
                "Fixtureichthys beta and Fixtureichthys gamma are species-level; "
                "Examplogobius and Testoblennius are genus-level. [S1]"
            )

    monkeypatch.setattr(edna_aggregate, "build_aggregate", forbidden_aggregate)
    monkeypatch.setattr(api, "retrieve_with_expansion", retrieve)
    monkeypatch.setattr(api, "get_model_runtime", lambda: Runtime())
    monkeypatch.setattr(
        api, "record_chat_context", lambda **values: calls["history"].append(values)
    )
    response = TestClient(api.app).post(
        "/chat",
        json={
            "query": PROFESSOR_QUESTION,
            "evidence_scope": chosen,
            "inject_analysis": False,
            "inject_reliability": False,
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "answered"
    assert result["model_invoked"] is True
    assert result["abstention_reason"] is None
    assert result["query"] == PROFESSOR_QUESTION
    assert len(calls["retrieval"]) == 1 and len(calls["model"]) == 1
    query, options = calls["retrieval"][0]
    assert query == PROFESSOR_QUESTION
    assert options["evidence_scope"] == original_scope
    assert chosen == original_scope
    assert not result["retrieval_diagnostics"].get("aggregate")
    assert "aggregate_scope" not in result["options"]["context"]
    assert [item["doc_id"] for item in result["sources"]] == [document["doc_id"]]
    assert "species-level" in result["answer"] and "genus-level" in result["answer"]
    assert "[edna_synthetic_sample_search]" in result["answer"]
    assert result["answer_audit"]["invalid_citation_count"] == 0
    assert PROFESSOR_QUESTION in calls["model"][0]["prompt"]
    assert "Fixtureichthys alpha" in calls["model"][0]["prompt"]
    assert len(calls["history"]) == 1
