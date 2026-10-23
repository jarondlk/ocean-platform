"""COP17 reuses only verified immutable receipts for the exact current scope."""

import json

import pytest
from sqlalchemy import create_engine, text

import config
from ingestion import edna_aggregate as aggregates
from ingestion.immutable_bundle import canonical_bytes, digest
from orchestration.edna_aggregation import evidence_document, render_answer
from tests.integration import test_edna_aggregate_postgres as catalogue_tests

# Existing fixtures create/drop a unique schema on a disposable PostgreSQL server.
database = catalogue_tests.database
published = catalogue_tests.published
pytestmark = catalogue_tests.pytestmark


@pytest.fixture
def demo(published, monkeypatch):
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", True)
    return published[0]


def location(filters=None, *, engine=None):
    return aggregates.build_aggregate(
        filters or {"provider": "anemone"}, engine=engine, metric="recorded_locations"
    )


def instrument(monkeypatch, name):
    original = getattr(aggregates, name)
    calls = []

    def wrapped(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(aggregates, name, wrapped)
    return calls


def forbidden(*args, **kwargs):
    raise AssertionError("A verified warm location receipt must bypass full aggregation")


def retain(engine, payload):
    identity = digest(payload)
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO edna_aggregate_evidence(aggregate_id,algorithm_version,payload_json)
                VALUES (:id,:algorithm,:payload)
            """),
            {"id": identity, "algorithm": aggregates.LOCATION_ALGORITHM,
             "payload": canonical_bytes(payload).decode()},
        )
    return identity


def test_cold_miss_then_warm_reuses_identical_citation_without_recount(demo, monkeypatch):
    inputs = instrument(monkeypatch, "_inputs")
    summaries = instrument(monkeypatch, "edna_summary")
    counts = instrument(monkeypatch, "edna_location_summary")
    cold = location()
    assert len(inputs) == len(summaries) == len(counts) == 1
    assert cold["payload"]["summary"]["locations"]["distinct_coordinate_pairs"] == 1
    assert cold["payload"]["filters"] == {"provider":"anemone","exclude_explicit_controls":True}
    for name in ("_inputs", "edna_summary", "edna_location_summary"):
        monkeypatch.setattr(aggregates, name, forbidden)
    warm = location()
    assert warm == cold
    assert aggregates.load_aggregate(warm["aggregate_id"]) == cold
    assert evidence_document(warm) == evidence_document(cold)
    citation = "[aggregate_edna_" + cold["aggregate_id"] + "]"
    assert citation in render_answer(warm, "How many locations?")
    assert citation in render_answer(warm, "ANEMONEの採水地点はいくつありますか？")
    trace = aggregates.aggregate_trace(warm["aggregate_id"])
    assert trace["found"]
    assert trace["trace"]["document"]["metadata"] == cold["payload"]
    with demo.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM edna_aggregate_evidence")).scalar() == 1


@pytest.mark.parametrize("scope", [
    {"provider_project_id":"not-published"},
    {"provider_run_id":"not-published"},
    {"sample_id":"a"*64},
    {"is_control":True},
    {"is_control":False},
    {"sample_kind":"unknown"},
    {"assignment_method":"qcauto_target"},
])
def test_exact_scope_and_explicit_classification_have_separate_receipts(demo, monkeypatch, scope):
    global_receipt = location()
    inputs = instrument(monkeypatch, "_inputs")
    scoped = location({"provider":"anemone", **scope})
    assert len(inputs) == 1
    assert scoped["aggregate_id"] != global_receipt["aggregate_id"]
    for key, value in scope.items():
        assert scoped["payload"]["filters"][key] == value
    if "is_control" in scope or "sample_kind" in scope:
        assert "exclude_explicit_controls" not in scoped["payload"]["filters"]
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    assert location({**scope, "provider":"anemone"}) == scoped
    assert location() == global_receipt
    with demo.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM edna_aggregate_evidence")).scalar() == 2


def test_demo_disabled_still_revalidates_existing_v2_receipts(demo, monkeypatch):
    cold = location()
    monkeypatch.setattr(config, "COP17_DEMO_ENABLED", False)
    monkeypatch.setattr(aggregates, "_reuse_location_aggregate", forbidden)
    inputs = instrument(monkeypatch, "_inputs")
    assert location() == cold
    assert len(inputs) == 1


def test_v1_catalogue_counts_never_use_demo_location_reuse(demo, monkeypatch):
    cold = aggregates.build_aggregate({"provider":"anemone"})
    assert cold["payload"]["algorithm_version"] == aggregates.ALGORITHM
    monkeypatch.setattr(aggregates, "_reuse_location_aggregate", forbidden)
    inputs = instrument(monkeypatch, "_inputs")
    assert aggregates.build_aggregate({"provider":"anemone"}) == cold
    assert len(inputs) == 1
    assert aggregates.load_aggregate(cold["aggregate_id"]) == cold


@pytest.mark.parametrize("channel", ["edna", "edna-canonical", "anemone-canonical"])
def test_missing_publication_head_cannot_serve_a_warm_receipt(demo, monkeypatch, channel):
    cold = location()
    with demo.begin() as connection:
        connection.execute(text("DELETE FROM corpus_publication WHERE channel=:channel"), {"channel":channel})
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable):
        location()
    assert aggregates.load_aggregate(cold["aggregate_id"]) == cold


def test_mismatched_canonical_heads_cannot_serve_a_warm_receipt(demo, monkeypatch):
    cold = location()
    with demo.begin() as connection:
        connection.execute(text("UPDATE corpus_publication SET generation_id=:generation WHERE channel='edna-canonical'"), {"generation":"c"*64})
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable):
        location()
    assert aggregates.load_aggregate(cold["aggregate_id"]) == cold


@pytest.mark.parametrize("patch", [
    {"status":"pending"}, {"generation_id":"d"*64}, {"manifest_sha256":"e"*64},
])
def test_invalid_pointer_before_reuse_fails_closed(demo, monkeypatch, patch):
    location()
    pointer = aggregates.publication_pointer()
    monkeypatch.setattr(aggregates, "publication_pointer", lambda: {**pointer, **patch})
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable):
        location()


def test_coherent_new_publication_is_a_cold_miss_and_old_citation_survives(demo, monkeypatch):
    cold = location()
    with demo.begin() as connection:
        connection.execute(text("""
            UPDATE corpus_publication SET generation_id=:generation,manifest_sha256=:manifest
            WHERE channel IN ('anemone-canonical','edna-canonical')
        """), {"generation":"f"*64,"manifest":"e"*64})
    inputs = instrument(monkeypatch, "_inputs")
    latest = location()
    assert len(inputs) == 1
    assert latest["aggregate_id"] != cold["aggregate_id"]
    assert latest["payload"]["publication"]["anemone-canonical"]["generation_id"] == "f"*64
    assert aggregates.load_aggregate(cold["aggregate_id"]) == cold
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    assert location() == latest


def test_pointer_change_after_candidate_validation_is_rechecked(demo, monkeypatch):
    cold = location()
    original_load = aggregates.load_aggregate

    def load_then_change_pointer(identity, *, engine=None):
        result = original_load(identity, engine=engine)
        pointer = aggregates.publication_pointer()
        (config.SERVING_DIR / "edna_current.json").write_text(json.dumps({**pointer,"status":"pending"}))
        return result

    monkeypatch.setattr(aggregates, "load_aggregate", load_then_change_pointer)
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable):
        location()
    assert original_load(cold["aggregate_id"]) == cold


def test_head_change_after_candidate_validation_is_rechecked_outside_snapshot(demo, monkeypatch):
    cold = location()
    original_load = aggregates.load_aggregate

    def load_then_change_heads(identity, *, engine=None):
        result = original_load(identity, engine=engine)
        with demo.begin() as writer:
            writer.execute(text("""
                UPDATE corpus_publication SET generation_id=:generation
                WHERE channel IN ('anemone-canonical','edna-canonical')
            """), {"generation":"9"*64})
        return result

    monkeypatch.setattr(aggregates, "load_aggregate", load_then_change_heads)
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable, match="Publication changed"):
        location()
    assert original_load(cold["aggregate_id"]) == cold


def test_warm_receipt_payload_tampering_is_hash_verified(demo, monkeypatch):
    cold = location()
    bad = json.loads(json.dumps(cold["payload"]))
    bad["summary"]["locations"]["distinct_coordinate_pairs"] = 999
    with demo.begin() as connection:
        connection.execute(text("UPDATE edna_aggregate_evidence SET payload_json=:payload WHERE aggregate_id=:id"),
                           {"payload":json.dumps(bad),"id":cold["aggregate_id"]})
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable, match="integrity"):
        location()


@pytest.mark.parametrize("contract", ["group_by", "summary_publication", "algorithm"])
def test_hash_valid_but_incompatible_location_contract_is_not_reused(demo, monkeypatch, contract):
    cold = location()
    bad = json.loads(json.dumps(cold["payload"]))
    if contract == "group_by":
        bad["group_by"] = ["provider_project_id"]
    elif contract == "summary_publication":
        bad["summary"]["publication"]["anemone-canonical"]["generation_id"] = "7"*64
    else:
        bad["algorithm_version"] = aggregates.ALGORITHM
    with demo.begin() as connection:
        connection.execute(text("DELETE FROM edna_aggregate_evidence"))
    retain(demo,bad)
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable, match="scope mismatch"):
        location()


def test_multiple_hash_valid_receipts_for_same_publication_and_scope_fail_closed(demo, monkeypatch):
    cold = location()
    other = json.loads(json.dumps(cold["payload"]))
    other["summary"]["locations"]["distinct_coordinate_pairs"] += 1
    other_id = retain(demo,other)
    assert other_id != cold["aggregate_id"]
    assert aggregates.load_aggregate(other_id)["payload"] == other
    monkeypatch.setattr(aggregates, "_inputs", forbidden)
    with pytest.raises(aggregates.AggregateUnavailable, match="Conflicting"):
        location()


def test_warm_reuse_works_with_a_single_connection_pool(demo, monkeypatch):
    cold = location()
    with demo.connect() as connection:
        schema = connection.exec_driver_sql("SELECT current_schema()").scalar()
    single = create_engine(demo.url, connect_args={"options":f"-csearch_path={schema},public"},
                           pool_size=1,max_overflow=0,pool_timeout=1)
    try:
        monkeypatch.setattr(aggregates, "_inputs", forbidden)
        assert location(engine=single) == cold
    finally:
        single.dispose()
