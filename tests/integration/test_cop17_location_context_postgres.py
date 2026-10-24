"""Real PostgreSQL context receipts share exact scope and preserve old history."""

from copy import deepcopy
import json

import pytest
from sqlalchemy import text

import config
from ingestion import edna_aggregate as a
from ingestion import location_context as c
from ingestion.immutable_bundle import canonical_bytes, digest
from tests.integration import test_edna_aggregate_postgres as baseline

database = baseline.database
published = baseline.published
pytestmark = baseline.pytestmark


@pytest.fixture
def demo(published, monkeypatch):
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", True)
    return published[0]


def build(engine, limit=10, areas=False, **filters):
    return a.build_aggregate(
        {"provider": "anemone", **filters},
        engine=engine,
        metric="location_context",
        context_options={"example_limit": limit, "area_groups": areas},
    )


def forbidden(*args, **kwargs):
    raise AssertionError("warm evidence recomputed rows")


def test_v4_count_examples_and_legacy_history_are_distinct(demo):
    old = [
        a.build_aggregate({"provider": "anemone"}, engine=demo, metric=m)
        for m in (None, "recorded_locations", "catalogue_geography")
    ]
    new = build(demo)
    context = new["payload"]["summary"]["location_context"]
    assert (
        len(context["positions"])
        == new["payload"]["summary"]["geography"]["locations"][
            "distinct_coordinate_pairs"
        ]
        == 1
    )
    assert context["positions"][0]["original_sample_label"]
    assert len({x["aggregate_id"] for x in old + [new]}) == 4
    for item in old + [new]:
        assert a.load_aggregate(item["aggregate_id"], engine=demo) == item
    assert build(demo) == new
    assert build(demo, limit=5)["aggregate_id"] != new["aggregate_id"]
    assert build(demo, limit=0, areas=True)["aggregate_id"] != new["aggregate_id"]
    for metric, item in zip((None, "recorded_locations", "catalogue_geography"), old):
        assert (
            a.build_aggregate({"provider": "anemone"}, engine=demo, metric=metric)
            == item
        )


def test_warm_reuse_and_registry_version_are_separate_cache_keys(demo, monkeypatch):
    first = build(demo)
    monkeypatch.setattr(c, "read_positions", forbidden)
    monkeypatch.setattr(a, "_inputs", forbidden)
    assert build(demo) == first
    mapping, map_hash = c.registry()
    changed = deepcopy(mapping)
    changed["version"] = "synthetic-new-registry"
    monkeypatch.setattr(c, "registry", lambda: (changed, "9" * 64))
    with pytest.raises(AssertionError, match="recomputed"):
        build(demo)
    assert a.load_aggregate(first["aggregate_id"], engine=demo) == first


@pytest.mark.parametrize(
    "filters",
    [
        {"provider_project_id": "absent"},
        {"taxon": "absent"},
        {"lat_min": 89},
        {"is_control": True},
        {"sample_id": "a" * 64},
    ],
)
def test_empty_scopes_do_not_inherit_global_examples_or_names(demo, filters):
    global_result = build(demo)
    result = build(demo, **filters)
    context = result["payload"]["summary"]["location_context"]
    assert context["positions"] == [] and context["groups"] == {
        "generalized_area_groups": [],
        "mapped_positions": 0,
        "unassigned_positions": 0,
    }
    assert result["aggregate_id"] != global_result["aggregate_id"]
    assert build(demo, **filters) == result


def test_filtered_representative_cannot_escape_method_taxon_date_scope(demo):
    matched = build(
        demo,
        taxon="Fixture fish",
        assignment_method="qcauto_target",
        time_from="2020-01-01",
    )
    row = matched["payload"]["summary"]["location_context"]["positions"][0]
    empty = build(demo, taxon="absent", sample_id=row["sample_id"])
    assert empty["payload"]["summary"]["location_context"]["positions"] == []


def test_corrupted_retained_context_never_becomes_a_new_answer(demo):
    original = build(demo)
    bad = deepcopy(original["payload"])
    bad["summary"]["location_context"]["groups"]["mapped_positions"] = 999
    with demo.begin() as conn:
        conn.execute(
            text(
                "UPDATE edna_aggregate_evidence SET payload_json=:p WHERE aggregate_id=:id"
            ),
            {"p": json.dumps(bad), "id": original["aggregate_id"]},
        )
    with pytest.raises(a.AggregateUnavailable, match="integrity"):
        build(demo)


def test_semantically_invalid_but_hash_valid_context_is_rejected(demo):
    original = build(demo)
    bad = deepcopy(original["payload"])
    bad["summary"]["location_context"]["positions"][0]["map_context"]["lat"] = 50
    identity = digest(bad)
    with demo.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO edna_aggregate_evidence(aggregate_id,algorithm_version,payload_json) VALUES (:id,:a,:p)"
            ),
            {"id": identity, "a": c.ALGORITHM, "p": canonical_bytes(bad).decode()},
        )
    with pytest.raises(a.AggregateUnavailable, match="contract"):
        a.load_aggregate(identity, engine=demo)


def test_stale_publication_and_changed_heads_reject_context(demo, monkeypatch):
    first = build(demo)
    pointer = a.publication_pointer()
    monkeypatch.setattr(
        a, "publication_pointer", lambda: {**pointer, "status": "pending"}
    )
    with pytest.raises(a.AggregateUnavailable):
        build(demo)
    assert a.load_aggregate(first["aggregate_id"], engine=demo) == first
