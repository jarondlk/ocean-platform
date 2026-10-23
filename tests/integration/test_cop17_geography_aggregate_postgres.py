"""Canonical geography-v3 evidence remains separate from v1/v2 history."""

import json

import pytest
from sqlalchemy import create_engine, text

import config
from ingestion import edna_aggregate as aggregates
from ingestion.immutable_bundle import canonical_bytes, digest
from tests.integration import test_edna_aggregate_postgres as catalogue_tests

# Existing fixtures create/drop a unique schema on the disposable server.
database = catalogue_tests.database
published = catalogue_tests.published
pytestmark = catalogue_tests.pytestmark


@pytest.fixture
def demo(published, monkeypatch):
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", True)
    return published[0]


def geography(filters=None, *, engine=None):
    return aggregates.build_aggregate(
        filters or {"provider": "anemone"}, engine=engine, metric="catalogue_geography"
    )


def forbidden(*args, **kwargs):
    raise AssertionError("Verified warm geography evidence must bypass full aggregation")


def retain(engine, payload):
    identity = digest(payload)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO edna_aggregate_evidence(aggregate_id,algorithm_version,payload_json) "
                 "VALUES (:id,:algorithm,:payload)"),
            {"id": identity, "algorithm": aggregates.GEOGRAPHY_ALGORITHM,
             "payload": canonical_bytes(payload).decode()},
        )
    return identity


def test_v1_v2_v3_roundtrip_has_distinct_immutable_contracts(demo):
    old = aggregates.build_aggregate({"provider": "anemone"})
    positions = aggregates.build_aggregate({"provider": "anemone"}, metric="recorded_locations")
    current = geography()
    assert len({item["aggregate_id"] for item in (old, positions, current)}) == 3
    assert old["payload"]["algorithm_version"] == aggregates.ALGORITHM
    assert positions["payload"]["algorithm_version"] == aggregates.LOCATION_ALGORITHM
    assert current["payload"]["algorithm_version"] == aggregates.GEOGRAPHY_ALGORITHM
    assert "geography" not in old["payload"]["summary"]
    assert "geography" not in positions["payload"]["summary"]
    assert "locations" not in current["payload"]["summary"]
    facts = current["payload"]["summary"]["geography"]
    assert facts["locations"]["distinct_coordinate_pairs"] == 1
    assert facts["named_area_count"] is None
    assert facts["named_area_status"] == "not_established_by_canonical_catalogue"
    assert current["payload"]["query_contract"]["geography"]["application_area_registries_consulted"] is False
    for item in (old, positions, current):
        assert aggregates.load_aggregate(item["aggregate_id"]) == item
        assert aggregates.aggregate_trace(item["aggregate_id"])["trace"]["document"]["metadata"] == item["payload"]
    assert aggregates.build_aggregate({"provider": "anemone"}) == old
    assert aggregates.build_aggregate({"provider": "anemone"}, metric="recorded_locations") == positions
    assert geography() == current


def test_warm_geography_reuses_verified_v3_without_recount(demo, monkeypatch):
    # Both versions may exist at the same scope without conflicting cache matches.
    positions = aggregates.build_aggregate({"provider": "anemone"}, metric="recorded_locations")
    cold = geography()
    calls = []
    original_load = aggregates.load_aggregate
    def checked_load(identity, **kwargs):
        calls.append(identity)
        return original_load(identity, **kwargs)
    monkeypatch.setattr(aggregates, "load_aggregate", checked_load)
    for name in ("_inputs", "edna_summary", "edna_geography_summary"):
        monkeypatch.setattr(aggregates, name, forbidden)
    warm = geography()
    assert warm == cold and calls == [cold["aggregate_id"]]
    assert aggregates.build_aggregate({"provider": "anemone"}, metric="recorded_locations") == positions
    assert aggregates.aggregate_trace(warm["aggregate_id"])["found"]


@pytest.mark.parametrize("filters", [
    {"provider_project_id": "not-published"},
    {"sample_id": "a" * 64},
    {"is_control": True},
    {"taxon": "absent"},
    {"lat_min": 89.0},
])
def test_filtered_empty_scope_reconciles_and_does_not_reuse_global(demo, monkeypatch, filters):
    global_receipt = geography()
    scoped = geography({"provider": "anemone", **filters})
    assert scoped["aggregate_id"] != global_receipt["aggregate_id"]
    value = scoped["payload"]["summary"]["geography"]
    assert value["locations"]["source_occurrences"] == 0
    assert value["locations"]["distinct_coordinate_pairs"] == 0
    assert value["coordinate_extent"] == dict.fromkeys(("lat_min", "lat_max", "lon_min", "lon_max"))
    assert value["latitude_extreme_positions"] == []
    assert value["latitude_extreme_separation_km"] is None
    assert value["named_area_count"] is None
    for key, value in filters.items():
        assert scoped["payload"]["filters"][key] == value
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    assert geography({"provider": "anemone", **filters}) == scoped


def test_single_position_is_actual_repeated_endpoint_and_zero_separation(demo):
    item = geography()
    value = item["payload"]["summary"]["geography"]
    assert len(value["latitude_extreme_positions"]) == 2
    assert value["latitude_extreme_positions"][0] == value["latitude_extreme_positions"][1]
    assert value["latitude_extreme_separation_km"] == 0.0
    assert value["coordinate_extent"]["lat_min"] == value["coordinate_extent"]["lat_max"]
    assert "not maximum pairwise distance" in item["payload"]["query_contract"]["geography"]["latitude_extreme_separation"]
    assert "not continuous sampled coverage" in item["payload"]["query_contract"]["geography"]["coordinate_extent"]


def test_demo_disabled_geography_recomputes_with_same_receipt(demo, monkeypatch):
    cold = geography()
    original = aggregates._inputs
    calls = []
    def inputs(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", False)
    monkeypatch.setattr(aggregates, "_reuse_geography_aggregate", forbidden)
    monkeypatch.setattr(aggregates, "_inputs", inputs)
    assert geography() == cold and calls == [True]


def test_geography_tampering_is_hash_verified_before_warm_answer(demo, monkeypatch):
    cold = geography()
    bad = json.loads(json.dumps(cold["payload"]))
    bad["summary"]["geography"]["locations"]["distinct_coordinate_pairs"] = 999
    with demo.begin() as connection:
        connection.execute(text("UPDATE edna_aggregate_evidence SET payload_json=:payload WHERE aggregate_id=:id"),
                           {"payload": json.dumps(bad), "id": cold["aggregate_id"]})
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable, match="integrity"):
        geography()


@pytest.mark.parametrize("contract", ["missing_geography", "missing_extent", "named_count", "named_status", "wrong_metric", "source_count"])
def test_hash_valid_but_invalid_geography_contract_fails_load(demo, contract):
    cold = geography()
    bad = json.loads(json.dumps(cold["payload"]))
    facts = bad["summary"]["geography"]
    if contract == "missing_geography":
        del bad["summary"]["geography"]
    elif contract == "missing_extent":
        del facts["coordinate_extent"]["lat_min"]
    elif contract == "named_count":
        facts["named_area_count"] = 0
    elif contract == "named_status":
        facts["named_area_status"] = "no_geographic_areas"
    elif contract == "wrong_metric":
        bad["metric"] = "recorded_locations"
    else:
        facts["locations"]["source_occurrences"] += 1
    identity = retain(demo, bad)
    with pytest.raises(aggregates.AggregateUnavailable, match="Geography aggregate contract"):
        aggregates.load_aggregate(identity)


@pytest.mark.parametrize("contract", ["group_by", "summary_publication"])
def test_warm_geography_rejects_hash_valid_incompatible_scope(demo, monkeypatch, contract):
    cold = geography()
    bad = json.loads(json.dumps(cold["payload"]))
    if contract == "group_by":
        bad["group_by"] = ["provider_project_id"]
    else:
        bad["summary"]["publication"]["anemone-canonical"]["generation_id"] = "7" * 64
    with demo.begin() as connection:
        connection.execute(text("DELETE FROM edna_aggregate_evidence"))
    retain(demo, bad)
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable, match="scope mismatch"):
        geography()


def test_geography_rechecks_heads_and_pointer_after_verification(demo, monkeypatch):
    geography()
    original_load = aggregates.load_aggregate
    def load_then_change_head(identity, **kwargs):
        value = original_load(identity, **kwargs)
        with demo.begin() as writer:
            writer.execute(text("UPDATE corpus_publication SET generation_id=:generation WHERE channel IN ('anemone-canonical','edna-canonical')"), {"generation": "9" * 64})
        return value
    monkeypatch.setattr(aggregates, "load_aggregate", load_then_change_head)
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable, match="Publication changed"):
        geography()


def test_geography_warm_reuse_needs_only_one_pool_connection(demo, monkeypatch):
    cold = geography()
    with demo.connect() as connection:
        schema = connection.exec_driver_sql("SELECT current_schema()").scalar()
    single = create_engine(demo.url, connect_args={"options": f"-csearch_path={schema},public"},
                           pool_size=1, max_overflow=0, pool_timeout=1)
    try:
        monkeypatch.setattr(aggregates, "_inputs", forbidden)
        assert geography(engine=single) == cold
    finally:
        single.dispose()
