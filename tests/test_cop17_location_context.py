"""Count examples and approximate names cannot broaden scientific scope."""

from copy import deepcopy
import math

import pytest
from fastapi.testclient import TestClient

import api.main as api
import config
from ingestion import location_context as evidence
from ingestion.edna_aggregate import AggregateUnavailable
from orchestration.location_context import plan_context, render
from tests.test_chat_source_scope import scope
from tests.test_cop17_geography_chat import geography_bundle

ORIGINAL = "Find one ANEMONE eDNA sample from Otsuchi Bay in 2020 and list five fish taxa detected in it. Distinguish species-level and genus-level identifications, and cite the source."


def context_bundle(base=None, *, limit=10, areas=False):
    item = deepcopy(base or geography_bundle())
    item["payload"].update(metric=evidence.METRIC, algorithm_version=evidence.ALGORITHM)
    item["payload"]["group_by"] = []
    item["payload"]["summary"]["publication"] = item["payload"]["publication"]
    item["payload"]["summary"]["source_occurrences"] = item["payload"]["summary"][
        "geography"
    ]["locations"]["source_occurrences"]
    n = item["payload"]["summary"]["geography"]["locations"][
        "distinct_coordinate_pairs"
    ]
    rows = [
        {
            "lat": float(i) / 100,
            "lon": 0.0,
            "sample_id": format(i + 1, "064x"),
            "source_snapshot_id": "4" * 64,
            "source_file_id": "5" * 64,
            "source_row_hash": "6" * 64,
            "original_sample_label": "Source | [label] <script>",
            "collection_date_utc": "2020-08-17",
            "coordinate_precision": "provider_grid_unconfirmed",
            "temporal_precision": "day",
            "map_context": {
                "lat": float(i) / 100,
                "lon": 0.0,
                "feature_id": None,
                "reason": "unassigned",
            },
        }
        for i in range(n)
    ]
    item["payload"]["summary"]["location_context"] = {
        "options": {"example_limit": limit, "area_groups": areas},
        "positions": rows,
        "groups": evidence.grouping(rows),
        "registry_sha256": "2" * 64,
        "registry_version": "synthetic-map-v1",
        "features": {},
        "map_sources": [
            {"name": "Synthetic map source", "url": "https://www.geonames.org/"}
        ],
        "map_method": "synthetic unassigned points",
        "selection": evidence.SELECTION,
        "disclaimer": evidence.DISCLAIMER,
        "base_geography_aggregate_id": "3" * 64,
    }
    return item


@pytest.mark.parametrize(
    "query",
    [
        "How many sampling locations are recorded in ANEMONE DB? Please show me 10 example locations.",
        "How many sampling locations are recorded in ANEMONE DB? Show me ten locations.",
        "Show me example sampling locations in ANEMONE DB.",
        "Please list 10 example locations.",
        "ANEMONE DBの採水地点はいくつありますか？10か所の例を示してください。",
        "ANEMONE DBの採水地点はいくつありますか？例を10か所示してください。",
    ],
)
def test_examples_are_presentation_limit_not_count_scope(query):
    result = plan_context(
        {
            "query": query,
            "evidence_scope": scope("edna_metabarcoding", "remote_sensing"),
        }
    )
    assert result.clarification is None
    assert result.metric == "location_context" and result.context_options == {
        "example_limit": 10,
        "area_groups": False,
    }
    assert result.filters == {"provider": "anemone", "exclude_explicit_controls": True}


@pytest.mark.parametrize(
    "query",
    [
        ORIGINAL,
        "How many sampling locations are recorded in ANEMONE DB?",
        "How many sampling locations are recorded in ANEMONE db?",
        "ANEMONE DBの採水地点はいくつありますか？",
        "Are all the sampling data from around the same area?",
        "Show the top 10 fish by detection frequency",
        "Compare fish and sea surface temperature",
    ],
)
def test_previous_routes_are_not_intercepted(query):
    assert plan_context({"query": query}) is None


@pytest.mark.parametrize(
    "query",
    [
        "How many named areas are available in ANEMONE DB?",
        "How many generalized named sampling areas are available?",
        "Which bays have sampling data?",
        "名前のある採水エリアはいくつありますか？",
    ],
)
def test_named_queries_get_separate_approximate_context(query):
    result = plan_context({"query": query})
    assert result.clarification is None and result.context_options == {
        "example_limit": 0,
        "area_groups": True,
    }


@pytest.mark.parametrize(
    "suffix",
    [
        "in 2020",
        "in Otsuchi Bay",
        "containing tuna",
        "with SST observations",
        "in the selected project",
        "for confirmed environmental samples",
        "with more than 10 samples",
    ],
)
def test_example_clause_never_erases_unresolved_scope(suffix):
    query = (
        f"How many sampling locations {suffix}? Please show me 10 example locations."
    )
    result = plan_context({"query": query})
    assert result.clarification


@pytest.mark.parametrize("n", [0, 21, 100])
def test_example_limits_fail_closed(n):
    result = plan_context(
        {"query": f"How many locations? Show me {n} example locations."}
    )
    assert result.clarification and "1 and 20" in result.clarification


def test_conflicting_limits_and_source_selection_remain_explicit():
    assert plan_context(
        {
            "query": "How many locations? Show me 5 example locations and show me 10 locations."
        }
    ).clarification
    assert plan_context(
        {
            "query": "Show me 10 example locations",
            "evidence_scope": scope("remote_sensing"),
        }
    ).clarification
    chosen = scope("edna_metabarcoding")
    chosen["sources"]["edna_metabarcoding"]["analysis_id"] = "a" * 64
    assert plan_context(
        {"query": "Show me 10 example locations", "evidence_scope": chosen}
    ).clarification
    chosen["sources"]["edna_metabarcoding"]["analysis_id"] = None
    chosen["sources"]["edna_metabarcoding"]["filters"] = {
        "provider_project_id": "ProjectA",
        "time_from": "2020-01-01",
        "is_control": True,
    }
    plan = plan_context(
        {
            "query": "How many locations in ProjectA? Show me 5 example locations.",
            "evidence_scope": chosen,
        }
    )
    assert not plan.clarification and plan.filters == {
        "provider": "anemone",
        "provider_project_id": "ProjectA",
        "time_from": "2020-01-01",
        "is_control": True,
    }


@pytest.mark.parametrize("count", [0, 2, 216])
def test_render_shows_at_most_requested_unique_rows_and_source_labels(count):
    item = geography_bundle()
    item["payload"]["summary"]["geography"]["locations"][
        "distinct_coordinate_pairs"
    ] = count
    item = context_bundle(item)
    answer = render(item, "Show me 10 locations")
    assert f"{min(count, 10)} example locations" in answer
    assert answer.count("| Unassigned |") == min(count, 10)
    assert (
        "not sampling-area names supplied by ANEMONE" in answer
        and "grid coordinates" in answer
    )
    assert "[aggregate_edna_" in answer
    if count:
        assert r"Source ｜ \[label\] \<script\>" in answer
        assert "2020-08-17" in answer


def test_named_render_preserves_all_previous_geographic_facts():
    answer = render(context_bundle(areas=True), "How many named areas?")
    assert (
        "216" in answer
        and "3,184.8" in answer
        and "17.458333" in answer
        and "148.687500" in answer
    )
    assert (
        "not established" in answer
        and "does not mean there are zero geographic areas" in answer
    )
    assert "not a complete or ANEMONE-verified named-area total" in answer
    assert "216 positions remain unassigned" in answer


def test_context_contract_rejects_hash_valid_semantic_corruption():
    good = context_bundle()
    evidence.validate(good["payload"])
    for mutate in [
        lambda p: p["summary"]["location_context"]["positions"][0].update(lat=50),
        lambda p: p["summary"]["location_context"]["groups"].update(mapped_positions=1),
        lambda p: p["summary"]["geography"].update(named_area_count=0),
        lambda p: p["summary"]["location_context"]["options"].update(example_limit=999),
    ]:
        bad = deepcopy(good["payload"])
        mutate(bad)
        with pytest.raises(AggregateUnavailable):
            evidence.validate(bad)


def test_bundled_registry_has_partial_coverage_explicit_ambiguity_and_alias_dedup():
    mapping, map_hash = evidence.registry()
    assert len(map_hash) == 64 and len(mapping["positions"]) == 216
    assert sum(r["feature_id"] is not None for r in mapping["positions"]) == 96
    assert len(mapping["features"]) == 87
    otsuchi = next(
        r for r in mapping["positions"] if (r["lat"], r["lon"]) == (39.375, 141.9375)
    )
    assert otsuchi["feature_id"] is None and "ambiguous" in otsuchi["reason"]
    hakata = mapping["features"]["1863365"]
    assert {r["feature_id"] for r in hakata["references"]} == {"1863365", "1863954"}
    assert "CC BY" in mapping["sources"][0]["name"]
    # Independently check each accepted proximity against the frozen source point.
    for row in mapping["positions"]:
        if row["feature_id"] is None:
            continue
        f = mapping["features"][row["feature_id"]]
        ref = next(
            r for r in f["references"] if r["feature_id"] == row["reference_feature_id"]
        )
        a, b = math.radians(row["lat"]), math.radians(ref["lat"])
        h = (
            math.sin((b - a) / 2) ** 2
            + math.cos(a)
            * math.cos(b)
            * math.sin(math.radians(ref["lon"] - row["lon"]) / 2) ** 2
        )
        distance = 6371.0088 * 2 * math.asin(math.sqrt(h))
        assert abs(distance - row["distance_to_reference_km"]) < 0.002
        assert distance <= (20 if f["type"] in {"ISL", "ISLS"} else 10)


def test_api_returns_exact_count_examples_without_retrieval_or_model(monkeypatch):
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", True)
    monkeypatch.setattr(
        api,
        "retrieve_with_expansion",
        lambda *a, **k: pytest.fail("Cannot count top-k"),
    )
    monkeypatch.setattr(
        api, "get_model_runtime", lambda: pytest.fail("No model for exact examples")
    )
    from ingestion import edna_aggregate

    calls = []

    def build(filters, groups, *, metric, context_options):
        calls.append((filters, metric, context_options))
        return context_bundle()

    monkeypatch.setattr(edna_aggregate, "build_aggregate", build)
    response = TestClient(api.app).post(
        "/chat",
        json={
            "query": "How many sampling locations are recorded in ANEMONE DB? Please show me 10 example locations.",
            "evidence_scope": scope("edna_metabarcoding", "remote_sensing"),
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "answered" and result["model_invoked"] is False
    assert result["answer_audit"]["invalid_citation_count"] == 0
    assert calls[0][1:] == (
        "location_context",
        {"example_limit": 10, "area_groups": False},
    )
