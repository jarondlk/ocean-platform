"""Exact counts and durable citations against isolated PostgreSQL schemas."""

import json

import pytest
from sqlalchemy import text

from db.app_models import EdnaAggregateEvidence
from ingestion import edna_aggregate as aggregates
from ingestion.anemone_catalogue import prepare_catalogue
from ingestion.immutable_bundle import digest
from scripts import import_anemone_catalogue as importer
from tests.integration.test_anemone_catalogue_postgres import database, pytestmark  # noqa: F401
from tests.test_anemone_catalogue import make_archive, rewrite


@pytest.fixture
def published(database, tmp_path, monkeypatch):  # noqa: F811
    EdnaAggregateEvidence.__table__.create(database, checkfirst=False)
    monkeypatch.setattr(aggregates, "get_engine", lambda: database)
    work = tmp_path / "work"
    candidate = prepare_catalogue(make_archive(tmp_path / "archive"), work)
    importer.import_candidate(database, work, execute=True, publish_retrieval=True)
    return database, work, candidate


def test_exact_counts_filters_groups_empty_cohort_and_repeatability(published):
    engine, _, _ = published
    bundle = aggregates.build_aggregate(
        {"provider": "anemone"}, ["provider_locus", "provider_project_id"]
    )
    summary = bundle["payload"]["summary"]
    assert summary["source_occurrences"] == summary["assays"] == 1
    assert [r["read_count_sum"] for r in summary["methods"]] == [17, 17]
    assert summary["internal_standards"] == {"rows": 1, "reads": 4}
    assert summary["groups"] == [
        {
            "provider_locus": "MiFish",
            "provider_project_id": "ProjectA",
            "source_occurrences": 1,
        }
    ]
    assert bundle["aggregate_id"] == digest(bundle["payload"])
    assert (
        aggregates.build_aggregate(
            {"provider": "anemone"}, ["provider_locus", "provider_project_id"]
        )
        == bundle
    )
    assert aggregates.load_aggregate(bundle["aggregate_id"]) == bundle
    for filters in (
        {"taxon": "absent"},
        {"provider_locus": "Other"},
        {"target_status": "nontarget"},
        {"time_from": "2025-01-01"},
    ):
        empty = aggregates.build_aggregate({"provider": "anemone", **filters})
        assert empty["payload"]["summary"]["source_occurrences"] == 0
        assert empty["payload"]["summary"]["assays"] == 0
        assert empty["payload"]["summary"]["methods"] == []
        assert empty["payload"]["inputs"]["tables"]["edna_detection"]["rows"] == 0
    matched = aggregates.build_aggregate(
        {
            "provider": "anemone",
            "taxon": "FIXTURE FISH",
            "assignment_method": "qcauto_target",
        }
    )
    assert len(matched["payload"]["summary"]["methods"]) == 1
    assert matched["payload"]["summary"]["source_occurrences"] == 1
    with engine.connect() as c:
        assert (
            c.execute(text("SELECT count(*) FROM edna_aggregate_evidence")).scalar()
            == 6
        )


def test_historical_evidence_survives_correction_and_unpublished_changes_fail_closed(
    published, tmp_path
):
    engine, work, candidate = published
    original = aggregates.build_aggregate({"provider": "anemone"})

    def change(payloads):
        rewrite(
            payloads,
            "community_qc_target.tsv.xz",
            lambda lines: [lines[0], lines[1].replace("\t17\t", "\t23\t")],
        )

    corrected = prepare_catalogue(make_archive(tmp_path / "correction", change), work)
    importer.import_candidate(
        engine, work, execute=True, expected_previous=candidate["candidate_id"]
    )
    with pytest.raises(aggregates.AggregateUnavailable, match="does not match"):
        aggregates.build_aggregate({"provider": "anemone"})
    assert aggregates.load_aggregate(original["aggregate_id"]) == original
    importer.import_candidate(
        engine,
        work,
        execute=True,
        expected_previous=corrected["candidate_id"],
        publish_retrieval=True,
    )
    latest = aggregates.build_aggregate({"provider": "anemone"})
    assert latest["aggregate_id"] != original["aggregate_id"]
    assert {
        r["assignment_method"]: r["read_count_sum"]
        for r in latest["payload"]["summary"]["methods"]
    }["qcauto_target"] == 23
    assert aggregates.load_aggregate(original["aggregate_id"]) == original
    assert (
        aggregates.aggregate_trace(original["aggregate_id"])["trace"]["document"][
            "metadata"
        ]
        == original["payload"]
    )
    # Corpus tables and latest pointers are not required to resolve old evidence.
    with engine.begin() as c:
        c.execute(text("DELETE FROM corpus_publication"))
    assert aggregates.load_aggregate(original["aggregate_id"]) == original


def test_available_empty_tables_are_not_missing(published, tmp_path):
    engine, work, candidate = published

    def empty(payloads):
        for name in ("community_qc_target.tsv.xz", "community_qc3nn_target.tsv.xz"):
            rewrite(payloads, name, lambda lines: lines[:1])

    prepare_catalogue(make_archive(tmp_path / "empty", empty), work)
    importer.import_candidate(
        engine,
        work,
        execute=True,
        expected_previous=candidate["candidate_id"],
        publish_retrieval=True,
    )
    result = aggregates.build_aggregate({"assignment_method": "qcauto_target"})[
        "payload"
    ]["summary"]
    assert result["source_occurrences"] == result["assays"] == 1
    assert result["methods"] == []
    assert result["community_availability"] == [
        {"assignment_method": "qcauto_target", "available_tables": 1, "empty_tables": 1}
    ]


def test_assay_filter_does_not_match_sibling_detections(published):
    engine, _, _ = published
    with engine.begin() as c:
        columns = [
            r.column_name
            for r in c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='edna_assay' ORDER BY ordinal_position"
                )
            )
        ]
        select = [
            "'" + "c" * 64 + "'"
            if col == "assay_id"
            else "'{}'"
            if col == "community_availability_json"
            else col
            for col in columns
        ]
        c.execute(
            text(
                "INSERT INTO edna_assay("
                + ",".join(columns)
                + ") SELECT "
                + ",".join(select)
                + " FROM edna_assay LIMIT 1"
            )
        )
    for filters in (
        {"taxon": "Fixture fish"},
        {"assignment_method": "qcauto_target"},
        {"target_status": "target"},
    ):
        summary = aggregates.build_aggregate({"assay_id": "c" * 64, **filters})[
            "payload"
        ]["summary"]
        assert summary["source_occurrences"] == summary["assays"] == 0
        assert summary["methods"] == [] and summary["internal_standards"]["rows"] == 0


@pytest.mark.parametrize(
    "failure", ["pending", "mismatch", "race", "rows", "bytes", "badfilter"]
)
def test_unavailable_publication_or_budget_never_retains_evidence(
    published, monkeypatch, failure
):
    engine, _, _ = published
    pointer = aggregates.publication_pointer()
    if failure == "pending":
        monkeypatch.setattr(
            aggregates, "publication_pointer", lambda: {**pointer, "status": "pending"}
        )
    elif failure == "mismatch":
        monkeypatch.setattr(
            aggregates,
            "publication_pointer",
            lambda: {**pointer, "generation_id": "a" * 64},
        )
    elif failure == "race":
        values = iter([pointer, {**pointer, "status": "pending"}])
        monkeypatch.setattr(aggregates, "publication_pointer", lambda: next(values))
    elif failure == "rows":
        monkeypatch.setattr(aggregates, "MAX_ROWS", 2)
    elif failure == "bytes":
        monkeypatch.setattr(aggregates, "MAX_PAYLOAD_BYTES", 10)
    with pytest.raises(aggregates.AggregateUnavailable):
        aggregates.build_aggregate(
            {"ignored_filter": "Japan"}
            if failure == "badfilter"
            else {"provider": "anemone"}
        )
    with engine.connect() as c:
        assert (
            c.execute(text("SELECT count(*) FROM edna_aggregate_evidence")).scalar()
            == 0
        )


def test_corrupt_historical_evidence_fails_integrity_check(published):
    engine, _, _ = published
    original = aggregates.build_aggregate({"provider": "anemone"})
    corrupted = json.loads(json.dumps(original["payload"]))
    corrupted["summary"]["source_occurrences"] = 999
    with engine.begin() as c:
        c.execute(
            text("UPDATE edna_aggregate_evidence SET payload_json=:data"),
            {"data": json.dumps(corrupted)},
        )
    with pytest.raises(aggregates.AggregateUnavailable, match="integrity"):
        aggregates.load_aggregate(original["aggregate_id"])


def test_repeatable_read_during_concurrent_publication(published, monkeypatch):
    engine, _, _ = published
    original_inputs = aggregates._inputs
    pointer = aggregates.publication_pointer()
    pointers = iter([pointer, {**pointer, "status": "pending"}])
    monkeypatch.setattr(aggregates, "publication_pointer", lambda: next(pointers))

    def concurrent_change(connection, filters):
        before = original_inputs(connection, filters)
        with engine.begin() as writer:
            writer.execute(
                text("UPDATE edna_detection SET read_count=999,source_row_hash=:hash"),
                {"hash": "9" * 64},
            )
        assert original_inputs(connection, filters) == before, (
            "MVCC must pin summary and input evidence together"
        )
        return before

    monkeypatch.setattr(aggregates, "_inputs", concurrent_change)
    with pytest.raises(aggregates.AggregateUnavailable, match="Publication changed"):
        aggregates.build_aggregate({"provider": "anemone"})
    with engine.connect() as c:
        assert (
            c.execute(text("SELECT count(*) FROM edna_aggregate_evidence")).scalar()
            == 0
        )


def test_corpus_rebuild_keeps_aggregate_history_and_downgrade_refuses_to_erase_it(
    published, monkeypatch
):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from db.models import CorpusBase
    import importlib

    engine, _, _ = published
    original = aggregates.build_aggregate({"provider": "anemone"})
    migration = importlib.import_module(
        "migrations.versions.20260925_0013_edna_aggregate_evidence"
    )
    with engine.begin() as connection:
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(connection))
        )
        with pytest.raises(RuntimeError, match="application-history backup"):
            migration.downgrade()
    CorpusBase.metadata.drop_all(engine, checkfirst=False)
    assert aggregates.load_aggregate(original["aggregate_id"]) == original
