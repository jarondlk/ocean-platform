"""Catalogue promotion and correction tests in a disposable PostgreSQL schema."""

import os
import uuid
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

import config
import api.edna_service as service
from db.models import CorpusBase
from ingestion.anemone_catalogue import prepare_catalogue, read_normalized_unit
from scripts import import_anemone_catalogue as importer
from tests.test_anemone_catalogue import make_archive, rewrite
from scripts.load_db import _stage_edna_dataframe

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires disposable PostgreSQL",
)


@pytest.fixture
def database(tmp_path, monkeypatch):
    schema = "catalogue_test_" + uuid.uuid4().hex
    admin = create_engine(config.DATABASE_URL)
    with admin.begin() as c:
        c.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(
        config.DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"}
    )
    CorpusBase.metadata.create_all(engine, checkfirst=False)
    monkeypatch.setattr(config, "SERVING_DIR", tmp_path / "serving")
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(service, "get_engine", lambda: engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


def state(engine):
    with engine.connect() as c:
        return {
            t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar()
            for t in (
                "edna_sample",
                "edna_detection",
                "retrieval_document",
                "corpus_publication",
            )
        }


def test_copy_staging_preserves_values_types_and_transaction_lifetime(database):
    with database.begin() as c:
        c.exec_driver_sql(
            'CREATE TABLE copy_target (id bigint, "odd name" text, amount numeric(25,4), enabled boolean, observed_at timestamptz)'
        )
    values = [
        None,
        "",
        r"\N",
        "line\tbreak\nreturn\r",
        '日本語 "quoted" \\ path',
        "null",
    ]
    frame = pd.DataFrame(
        {
            "id": pd.Series(
                [9007199254740993 + i for i in range(len(values))], dtype="Int64"
            ),
            "odd name": values,
            "amount": [Decimal("12345678901234567890.1234")] * len(values),
            "enabled": pd.Series(
                [True, False, pd.NA, True, False, pd.NA], dtype="boolean"
            ),
            "observed_at": [pd.Timestamp("2026-09-28T12:30:01.123456+09:00")]
            * len(values),
        }
    )
    with database.begin() as c:
        _stage_edna_dataframe(
            c, frame, table_name="copy_target", temporary_table="copy_stage"
        )
        rows = (
            c.exec_driver_sql("SELECT * FROM copy_stage ORDER BY id").mappings().all()
        )
        assert [r["odd name"] for r in rows] == values
        assert [r["id"] for r in rows] == frame["id"].tolist()
        assert all(r["amount"] == Decimal("12345678901234567890.1234") for r in rows)
        assert [r["enabled"] for r in rows] == [True, False, None, True, False, None]
        assert all(r["observed_at"] == frame["observed_at"][0] for r in rows)
        assert (
            c.exec_driver_sql(
                "SELECT relpersistence FROM pg_class WHERE oid='copy_stage'::regclass"
            ).scalar()
            == "t"
        )
        with database.connect() as other:
            assert (
                other.exec_driver_sql("SELECT to_regclass('copy_stage')").scalar()
                is None
            )
    with database.connect() as c:
        assert (
            c.exec_driver_sql("SELECT to_regclass('pg_temp.copy_stage')").scalar()
            is None
        )
        assert c.exec_driver_sql("SELECT count(*) FROM copy_target").scalar() == 0


def test_copy_staging_multiple_batches_and_failure_roll_back(database):
    from psycopg2.errors import InvalidTextRepresentation

    with database.begin() as c:
        c.exec_driver_sql("CREATE TABLE copy_target (id bigint, value text)")
        c.exec_driver_sql("INSERT INTO copy_target VALUES (1,'original')")
    with database.begin() as c:
        _stage_edna_dataframe(
            c,
            pd.DataFrame({"id": range(10003), "value": ["same"] * 10003}),
            table_name="copy_target",
            temporary_table="copy_stage",
        )
        assert c.exec_driver_sql("SELECT count(*) FROM copy_stage").scalar() == 10003
    # COPY uses the same DBAPI transaction as the preceding SQLAlchemy update.
    # Invalid input must undo both, without leaving a published staging table.
    with pytest.raises(InvalidTextRepresentation, match="invalid input syntax"):
        with database.begin() as c:
            c.exec_driver_sql("UPDATE copy_target SET value='changed'")
            _stage_edna_dataframe(
                c,
                pd.DataFrame({"id": [*range(5001), "invalid"], "value": ["bad"] * 5002}),
                table_name="copy_target",
                temporary_table="copy_failed",
            )
    with database.connect() as c:
        assert c.exec_driver_sql("SELECT value FROM copy_target").scalar() == "original"
        assert (
            c.exec_driver_sql("SELECT to_regclass('pg_temp.copy_failed')").scalar()
            is None
        )


def test_bulk_merge_mixed_changes_and_non_primary_conflict(database):
    import hashlib
    from sqlalchemy.exc import IntegrityError
    from scripts.load_db import _merge_edna_dataframe, _upsert_anemone_bundle
    from tests.integration.test_anemone_postgres import _frames

    frames, _ = _frames("bulk-merge")
    records = []
    for sequence in ("ACGT", "ACGA", "ACGC", "ACGG", "ACCC"):
        row = frames["edna_detection"].iloc[0].to_dict()
        row.update(
            detection_id=hashlib.sha256(("detection-" + sequence).encode()).hexdigest(),
            sequence=sequence,
            sequence_sha256=hashlib.sha256(sequence.encode()).hexdigest(),
        )
        records.append(row)
    frames["edna_detection"] = pd.DataFrame(records[:4])
    with database.begin() as c:
        _upsert_anemone_bundle(
            c, frames=frames, manifest={"source_scope_level": "sample"}
        )
        c.execute(
            text("UPDATE edna_detection SET active=FALSE WHERE detection_id=:id"),
            {"id": records[3]["detection_id"]},
        )
    incoming = pd.DataFrame(records)
    incoming.loc[1, ["read_count", "scientific_content_sha256", "source_row_hash"]] = [
        11,
        "b" * 64,
        "c" * 64,
    ]
    incoming.loc[2, "source_row_hash"] = "d" * 64
    with database.begin() as c:
        result = _merge_edna_dataframe(
            c, table_name="edna_detection", incoming=incoming, key_column="detection_id"
        )
        assert result == {
            "incoming": 5,
            "matched": 4,
            "updated": 3,
            "inserted": 1,
            "scientific_corrections": 1,
            "provenance_refreshes": 2,
            "unchanged": 1,
        }
        repeat = _merge_edna_dataframe(
            c, table_name="edna_detection", incoming=incoming, key_column="detection_id"
        )
        assert repeat["unchanged"] == 5 and repeat["updated"] == repeat["inserted"] == 0
        assert (
            c.exec_driver_sql(
                "SELECT count(*) FROM edna_detection WHERE active"
            ).scalar()
            == 5
        )
        assert (
            c.exec_driver_sql(
                "SELECT DISTINCT first_seen_snapshot_id FROM edna_detection"
            ).scalar()
            == records[0]["first_seen_snapshot_id"]
        )
    # Only primary-key conflicts may be skipped. A different ID for the same
    # assay/method/sequence must still fail the scientific identity constraint.
    duplicate = incoming.iloc[:1].copy()
    duplicate["detection_id"] = "9" * 64
    with pytest.raises(IntegrityError, match="uq_edna_detection_identity"):
        with database.begin() as c:
            _merge_edna_dataframe(
                c,
                table_name="edna_detection",
                incoming=duplicate,
                key_column="detection_id",
            )
    with database.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM edna_detection").scalar() == 5


def test_atomic_import_rerun_stale_generation_and_failed_derivation(
    database, tmp_path, monkeypatch
):
    work = tmp_path / "work"
    candidate = prepare_catalogue(make_archive(tmp_path / "archive"), work)
    before = state(database)
    result = importer.import_candidate(database, work, publish_retrieval=True)
    assert not result["committed"] and state(database) == before
    first = importer.import_candidate(
        database, work, execute=True, publish_retrieval=True
    )
    assert first["retrieval"]["documents"] == 2
    summary = service.edna_summary({})
    assert summary["source_occurrences"] == 1 and summary["assays"] == 1
    assert len(summary["methods"]) == 2
    assert summary["publication"]["anemone-canonical"]["generation_id"] == candidate["candidate_id"]
    pointer = (config.SERVING_DIR / "edna_current.json").read_bytes()
    second = importer.import_candidate(
        database,
        work,
        execute=True,
        expected_previous=candidate["candidate_id"],
        publish_retrieval=True,
    )
    assert second["retrieval"]["merge"]["unchanged"] == 2
    assert second["retrieval"]["merge"]["embedding_invalidated"] == 0
    assert (config.SERVING_DIR / "edna_current.json").read_bytes() == pointer
    before = state(database)
    with pytest.raises(ValueError, match="generation changed"):
        importer.import_candidate(database, work, execute=True)
    assert state(database) == before

    def changed(p):
        rewrite(
            p,
            "community_qc_target.tsv.xz",
            lambda lines: [lines[0], lines[1].replace("\t10\t", "\t11\t")],
        )

    # A derivative error after all canonical units have merged must roll back.
    prepare_catalogue(make_archive(tmp_path / "correction", changed), work)
    monkeypatch.setattr(
        importer,
        "_merge_documents",
        lambda *a: (_ for _ in ()).throw(RuntimeError("injected derivative failure")),
    )
    with pytest.raises(RuntimeError, match="injected"):
        importer.import_candidate(
            database,
            work,
            execute=True,
            expected_previous=candidate["candidate_id"],
            publish_retrieval=True,
        )
    assert state(database) == before
    assert (config.SERVING_DIR / "edna_current.json").read_bytes() == pointer
    with database.connect() as c:
        assert (
            c.execute(
                text(
                    "SELECT generation_id FROM corpus_publication WHERE channel='anemone-canonical'"
                )
            ).scalar()
            == candidate["candidate_id"]
        )


def test_late_unit_corruption_rolls_back_and_empty_tables_remain_queryable(
    database, tmp_path
):
    def mutate(p):
        for name in ("community_qc_target.tsv.xz", "community_qc3nn_target.tsv.xz"):
            rewrite(p, name, lambda lines: lines[:1])
        for key, data in list(p.items()):
            p[key.replace("/MiFish/ANEMONE/", "/Other/OtherTeam/")] = data

    work = tmp_path / "work"
    candidate = prepare_catalogue(make_archive(tmp_path / "archive", mutate), work)
    unit = candidate["units"][-1]
    path = (
        work
        / "normalized/snapshots"
        / unit["normalization_id"]
        / "normalization_manifest.json"
    )
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        importer.import_candidate(database, work, execute=True)
    assert state(database)["edna_sample"] == 0
    path.write_bytes(original)
    importer.import_candidate(database, work, execute=True, publish_retrieval=True)
    assert (
        service.edna_samples(
            {"assignment_method": "qcauto_target"}, limit=10, offset=0
        )["total"]
        == 2
    )
    assert (
        service.edna_samples(
            {"provider_locus": "Other", "target_status": "target"}, limit=10, offset=0
        )["total"]
        == 1
    )
    assert (
        service.edna_samples(
            {"assignment_method": "qcauto_nontarget"}, limit=10, offset=0
        )["total"]
        == 0
    )
    assert service.edna_samples({"taxon": "missing"}, limit=10, offset=0)["total"] == 0
    assert state(database)["retrieval_document"] == 4
    summary = service.edna_summary({"assignment_method": "qcauto_target"})
    assert summary["source_occurrences"] == 2 and summary["methods"] == []
    assert summary["community_availability"] == [{"assignment_method": "qcauto_target", "available_tables": 2, "empty_tables": 2}]


def test_matching_review_preserves_anchor_and_changed_evidence_does_not(
    database, tmp_path
):
    def unknown(p):
        rewrite(
            p,
            "sample.tsv.xz",
            lambda lines: [line for line in lines if "\tsample_type\t" not in line],
        )

    work = tmp_path / "work"
    candidate = prepare_catalogue(make_archive(tmp_path / "archive", unknown), work)
    importer.import_candidate(database, work, execute=True)
    frames, _ = read_normalized_unit(
        work / "normalized", candidate["units"][0]["normalization_id"]
    )
    sample = frames["edna_sample"].iloc[0]
    # Stand in for an already approved and applied database review. Validation
    # of review signatures is covered by the classification integration suite.
    with database.begin() as c:
        c.execute(
            text(
                "INSERT INTO anchor_event(event_id,sample_id,source_types,active) VALUES (:id,:sample,'edna_metabarcoding',TRUE)"
            ),
            {"id": "a" * 64, "sample": sample.sample_id},
        )
        c.execute(
            text(
                "UPDATE edna_sample SET classification_review_json='{}', sample_kind='environmental', is_control=FALSE, anchor_event_id=:anchor WHERE sample_id=:sample"
            ),
            {"anchor": "a" * 64, "sample": sample.sample_id},
        )
    result = importer.import_candidate(
        database, work, execute=True, expected_previous=candidate["candidate_id"]
    )
    assert result["changes"]["preserved_reviews"] == 1
    with database.connect() as c:
        assert c.execute(
            text("SELECT active FROM anchor_event WHERE event_id=:id"), {"id": "a" * 64}
        ).scalar()
        frames["external_source_file"].loc[
            frames["external_source_file"].source_file_id == sample.source_file_id,
            "sha256",
        ] = "0" * 64
        assert importer.preserve_matching_reviews(c, frames) == 0
