"""Immutable location receipts coexist with existing v1 catalogue history."""

import json

import pytest
from sqlalchemy import text
from ingestion import edna_aggregate as aggregates
from orchestration.edna_aggregation import render_answer
from tests.integration import test_edna_aggregate_postgres as catalogue_tests

# Register the existing isolated-schema fixtures without importing unused names.
database = catalogue_tests.database
published = catalogue_tests.published
pytestmark = catalogue_tests.pytestmark


def test_location_v2_roundtrip_preserves_v1_counts_and_historical_citations(published):
    engine, _, _ = published
    old = aggregates.build_aggregate({"provider": "anemone"})
    new = aggregates.build_aggregate(
        {"provider": "anemone"}, metric="recorded_locations"
    )
    assert old["payload"]["algorithm_version"] == aggregates.ALGORITHM
    assert new["payload"]["algorithm_version"] == aggregates.LOCATION_ALGORITHM
    assert old["aggregate_id"] != new["aggregate_id"]
    assert new["payload"]["filters"]["exclude_explicit_controls"] is True
    locations = new["payload"]["summary"]["locations"]
    assert (
        locations["source_occurrences"]
        == new["payload"]["inputs"]["tables"]["edna_sample"]["rows"]
    )
    assert (
        locations["valid_coordinate_occurrences"]
        + locations["missing_coordinate_occurrences"]
        + locations["invalid_coordinate_occurrences"]
        == locations["source_occurrences"]
    )
    assert locations["distinct_coordinate_pairs"] == 1
    assert (
        aggregates.build_aggregate({"provider": "anemone"}, metric="recorded_locations")
        == new
    )
    for item in [old, new]:
        assert aggregates.load_aggregate(item["aggregate_id"]) == item
        assert aggregates.aggregate_trace(item["aggregate_id"])["found"]
    assert aggregates.build_aggregate({"provider": "anemone"}) == old
    assert "1 distinct reported coordinate positions" in render_answer(
        new, "How many locations?"
    )


def test_location_scoped_empty_count_and_publication_consistency(
    published, monkeypatch
):
    empty = aggregates.build_aggregate(
        {"provider": "anemone", "provider_project_id": "not-published"},
        metric="recorded_locations",
    )
    assert empty["payload"]["summary"]["locations"]["distinct_coordinate_pairs"] == 0
    assert empty["payload"]["summary"]["locations"]["source_occurrences"] == 0
    pointer = aggregates.publication_pointer()
    monkeypatch.setattr(
        aggregates, "publication_pointer", lambda: {**pointer, "status": "pending"}
    )
    with pytest.raises(aggregates.AggregateUnavailable):
        aggregates.build_aggregate({"provider": "anemone"}, metric="recorded_locations")
    assert aggregates.load_aggregate(empty["aggregate_id"]) == empty


def test_location_receipt_tampering_and_invalid_metric_fail_closed(published):
    engine, _, _ = published
    item = aggregates.build_aggregate(
        {"provider": "anemone"}, metric="recorded_locations"
    )
    bad = json.loads(json.dumps(item["payload"]))
    bad["summary"]["locations"]["distinct_coordinate_pairs"] = 999
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE edna_aggregate_evidence SET payload_json=:payload WHERE aggregate_id=:id"
            ),
            {"payload": json.dumps(bad), "id": item["aggregate_id"]},
        )
    with pytest.raises(aggregates.AggregateUnavailable, match="integrity"):
        aggregates.load_aggregate(item["aggregate_id"])
    for kwargs in [
        {"metric": "physical_sites"},
        {"metric": "recorded_locations", "group_by": ["provider_project_id"]},
    ]:
        with pytest.raises(aggregates.AggregateUnavailable):
            aggregates.build_aggregate({"provider": "anemone"}, **kwargs)
