from __future__ import annotations

import os
import hashlib
import json
import uuid
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

import config
import api.edna_service as edna_service
import retrieval.hybrid_retriever as hybrid_retriever
from db.models import CorpusBase
from retrieval.edna_document_builder import build_edna_documents
from retrieval.edna_materializer import (
    _document_frame,
    _merge_documents,
    _read_active_frames,
)
from scripts.load_db import _upsert_anemone_bundle


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires the disposable PostgreSQL integration service",
)


def _hash(character: str) -> str:
    return character * 64


def _frames(unique: str) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    snapshot_id = _hash("a")
    source_file_id = _hash("b")
    sample_id = _hash("c")
    assay_id = _hash("d")
    detection_id = _hash("e")
    standard_id = _hash("f")
    common = {
        "source_snapshot_id": snapshot_id,
        "source_file_id": source_file_id,
        "active": True,
        "first_seen_snapshot_id": snapshot_id,
        "last_seen_snapshot_id": snapshot_id,
        "scientific_content_sha256": _hash("1"),
        "source_row_hash": _hash("2"),
    }
    frames = {
        "external_source_snapshot": pd.DataFrame(
            [
                {
                    "snapshot_id": snapshot_id,
                    "provider": "anemone",
                    "source_family": "edna_metabarcoding",
                    "scope_url": (
                        "https://db.anemone.bio/dist/MiFish/ANEMONE/"
                        f"project-{unique}/run-{unique}/sample-{unique}"
                    ),
                    "scope_level": "sample",
                    "source_collection_sha256": _hash("3"),
                    "contract_version": 1,
                    "contract_sha256": _hash("4"),
                    "selection_policy": "interpreted_tsv_only",
                    "generated_at": "2026-09-01T00:00:00+00:00",
                    "file_count": 1,
                    "selected_file_count": 1,
                    "total_bytes": 10,
                    "status": "complete",
                    "manifest_sha256": _hash("5"),
                    "manifest_summary_json": "{}",
                }
            ]
        ),
        "external_source_file": pd.DataFrame(
            [
                {
                    "source_file_id": source_file_id,
                    "snapshot_id": snapshot_id,
                    "relative_path": "sample/community_qc_target.tsv.xz",
                    "source_url": "https://db.anemone.bio/dist/example",
                    "sample_name": f"sample-{unique}",
                    "role": "community_qc",
                    "selection_status": "selected",
                    "size_bytes": 10,
                    "etag": "fixture",
                    "last_modified": "2026-09-01T00:00:00Z",
                    "sha256": _hash("6"),
                    "validation_status": "valid",
                    "row_count": 1,
                }
            ]
        ),
        "edna_sample": pd.DataFrame(
            [
                {
                    "sample_id": sample_id,
                    "provider": "anemone",
                    "provider_sample_id": f"sample-{unique}",
                    "provider_project_id": f"project-{unique}",
                    "provider_run_id": f"run-{unique}",
                    "project_name": "Integration fixture",
                    "original_sample_label": f"sample-{unique}",
                    "sample_kind": "environmental",
                    "is_control": False,
                    "classification_basis": "metadata:sample_type",
                    "collection_date_utc": "2026-09-01",
                    "temporal_precision": "date",
                    "lat": 38.4,
                    "lon": 141.5,
                    "raw_metadata_json": "{}",
                    "anchor_event_id": None,
                    "source_row_numbers_json": "[2]",
                    **common,
                }
            ]
        ),
        "edna_assay": pd.DataFrame(
            [
                {
                    "assay_id": assay_id,
                    "sample_id": sample_id,
                    "target_gene": "12S",
                    "primer_set": "MiFish",
                    "sequencing_method": "Illumina",
                    "library_layout": "paired",
                    "instrument_model": "MiSeq",
                    "raw_metadata_json": "{}",
                    "source_row_numbers_json": "[2]",
                    **common,
                }
            ]
        ),
        "edna_detection": pd.DataFrame(
            [
                {
                    "detection_id": detection_id,
                    "assay_id": assay_id,
                    "assignment_method": "qcauto_target",
                    "sequence": "ACGT",
                    "sequence_sha256": _hash("7"),
                    "read_count": 10,
                    "copies_per_ml": None,
                    "taxonomy_json": "{}",
                    "source_row_number": 2,
                    **common,
                }
            ]
        ),
        "edna_internal_standard": pd.DataFrame(
            [
                {
                    "internal_standard_id": standard_id,
                    "assay_id": assay_id,
                    "standard_name": "standard-1",
                    "sequence": "ACGT",
                    "sequence_sha256": _hash("8"),
                    "read_count": 5,
                    "source_row_number": 2,
                    **common,
                }
            ]
        ),
        "edna_anchor_event": pd.DataFrame(columns=["event_id"]),
    }
    return frames, {
        "snapshot_id": snapshot_id,
        "sample_id": sample_id,
        "detection_id": detection_id,
    }


def test_anemone_migration_and_transactional_merge_are_idempotent(monkeypatch):
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    CorpusBase.metadata.create_all(engine)
    expected_tables = {
        "external_source_snapshot",
        "external_source_file",
        "edna_sample",
        "edna_assay",
        "edna_detection",
        "edna_internal_standard",
    }
    assert expected_tables.issubset(inspect(engine).get_table_names())

    frames, identifiers = _frames(uuid.uuid4().hex)
    manifest = {"source_scope_level": "sample"}
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            first, first_inactive = _upsert_anemone_bundle(
                connection,
                frames=frames,
                manifest=manifest,
            )
            second, second_inactive = _upsert_anemone_bundle(
                connection,
                frames=frames,
                manifest=manifest,
            )

            assert first["edna_detection"]["inserted"] == 1
            assert first_inactive["edna_detection"] == 0
            assert second["edna_detection"]["unchanged"] == 1
            assert second["edna_detection"]["updated"] == 0
            assert second_inactive["edna_detection"] == 0

            samples, assays, detections = _read_active_frames(connection)
            documents = build_edna_documents(samples, assays, detections)
            assert len(documents) == 1
            first_docs = _merge_documents(
                connection,
                _document_frame(documents),
            )
            second_docs = _merge_documents(
                connection,
                _document_frame(documents),
            )
            assert first_docs["inserted"] == 1
            assert second_docs["unchanged"] == 1
            assert connection.execute(
                text(
                    "SELECT source_type, assignment_method, active "
                    "FROM retrieval_document WHERE doc_id = :doc_id"
                ),
                {"doc_id": documents[0].doc_id},
            ).one() == ("edna_metabarcoding", "qcauto_target", True)
            monkeypatch.setattr(
                edna_service, "get_engine",
                lambda: SimpleNamespace(connect=lambda: nullcontext(connection)),
            )
            assert edna_service.edna_catalog()["samples"] == 1
            sample_detail = edna_service.edna_sample_detail(identifiers["sample_id"])
            assert sample_detail["method_summaries"][0]["read_count_sum"] == 10
            assert edna_service.edna_assay_detail(_hash("d"))["internal_standards"][0]["read_count"] == 5
            detail = edna_service.edna_detection_detail(identifiers["detection_id"])
            assert detail["provenance"]["records"][-1]["source_row_locator"] == 2
            assert edna_service.edna_samples({"is_control": True}, limit=10, offset=0)["total"] == 0
            assert edna_service.edna_samples({"assay_id": _hash("d")}, limit=10, offset=0)["total"] == 1
            listing = edna_service.edna_detections(
                {"assignment_method": "qcauto_target", "lat_min": 38, "lat_max": 39},
                limit=10, offset=0,
            )
            assert listing["total"] == 1
            assert "sequence" not in listing["rows"][0]
            assert listing["rows"][0]["source_sha256"] == _hash("6")
            assert edna_service.edna_detections({"taxon": "missing"}, limit=10, offset=0)["total"] == 0

            monkeypatch.setattr(hybrid_retriever, "get_session", lambda: nullcontext(connection))
            monkeypatch.setattr(hybrid_retriever, "embed_text", lambda _query: [0.1] * config.EMBEDDING_DIM)
            results = hybrid_retriever.hybrid_search("MiFish", provider="anemone", is_control=False)
            assert [row.doc_id for row in results] == [documents[0].doc_id]
            assert hybrid_retriever.hybrid_search("MiFish", taxon="missing") == []

            connection.execute(
                text("UPDATE retrieval_document SET embedding = CAST(:value AS vector), embedding_provider = 'test', embedding_model = 'test-model' WHERE doc_id = :id"),
                {"value": str([0.1] * config.EMBEDDING_DIM), "id": documents[0].doc_id},
            )

            refreshed = {name: frame.copy() for name, frame in frames.items()}
            refreshed_snapshot_id = _hash("9")
            refreshed_source_file_id = _hash("0")
            refreshed["external_source_snapshot"].loc[
                0, "snapshot_id"
            ] = refreshed_snapshot_id
            refreshed["external_source_snapshot"].loc[
                0, "source_collection_sha256"
            ] = _hash("8")
            refreshed["external_source_snapshot"].loc[
                0, "manifest_sha256"
            ] = _hash("7")
            refreshed["external_source_file"].loc[
                0, "source_file_id"
            ] = refreshed_source_file_id
            refreshed["external_source_file"].loc[
                0, "snapshot_id"
            ] = refreshed_snapshot_id
            for table_name in (
                "edna_sample",
                "edna_assay",
                "edna_detection",
                "edna_internal_standard",
            ):
                refreshed[table_name].loc[
                    :, "source_snapshot_id"
                ] = refreshed_snapshot_id
                refreshed[table_name].loc[
                    :, "source_file_id"
                ] = refreshed_source_file_id
                refreshed[table_name].loc[
                    :, "last_seen_snapshot_id"
                ] = refreshed_snapshot_id
                refreshed[table_name].loc[:, "source_row_hash"] = _hash("6")
            refresh_result, _ = _upsert_anemone_bundle(
                connection,
                frames=refreshed,
                manifest=manifest,
            )
            assert (
                refresh_result["edna_detection"]["provenance_refreshes"] == 1
            )
            assert (
                refresh_result["edna_detection"]["scientific_corrections"]
                == 0
            )
            lifecycle = connection.execute(
                text(
                    "SELECT first_seen_snapshot_id, last_seen_snapshot_id "
                    "FROM edna_detection WHERE detection_id = :detection_id"
                ),
                {"detection_id": identifiers["detection_id"]},
            ).mappings().one()
            assert lifecycle["first_seen_snapshot_id"] == identifiers["snapshot_id"]
            assert lifecycle["last_seen_snapshot_id"] == refreshed_snapshot_id
            refreshed_docs = build_edna_documents(*_read_active_frames(connection))
            refreshed_merge = _merge_documents(connection, _document_frame(refreshed_docs))
            assert refreshed_merge["updated"] == 1
            assert refreshed_merge["embedding_invalidated"] == 0
            assert connection.execute(text("SELECT embedding IS NOT NULL FROM retrieval_document WHERE doc_id = :id"), {"id": documents[0].doc_id}).scalar_one() is True

            corrected = {
                name: frame.copy() for name, frame in refreshed.items()
            }
            corrected["edna_detection"].loc[0, "read_count"] = 11
            corrected["edna_detection"].loc[
                0, "scientific_content_sha256"
            ] = _hash("5")
            corrected["edna_detection"].loc[0, "source_row_hash"] = _hash("4")
            correction_result, _ = _upsert_anemone_bundle(
                connection,
                frames=corrected,
                manifest=manifest,
            )
            assert (
                correction_result["edna_detection"]["scientific_corrections"]
                == 1
            )
            corrected_docs = build_edna_documents(*_read_active_frames(connection))
            corrected_merge = _merge_documents(connection, _document_frame(corrected_docs))
            assert corrected_merge["embedding_invalidated"] == 1
            assert connection.execute(text("SELECT embedding IS NULL FROM retrieval_document WHERE doc_id = :id"), {"id": documents[0].doc_id}).scalar_one() is True

            missing = {name: frame.copy() for name, frame in corrected.items()}
            missing["edna_detection"] = corrected["edna_detection"].iloc[0:0]
            _, inactive = _upsert_anemone_bundle(
                connection,
                frames=missing,
                manifest=manifest,
            )
            assert inactive["edna_detection"] == 1
            active = connection.execute(
                text(
                    "SELECT active FROM edna_detection "
                    "WHERE detection_id = :detection_id"
                ),
                {"detection_id": identifiers["detection_id"]},
            ).scalar_one()
            assert active is False
            samples, assays, detections = _read_active_frames(connection)
            empty_documents = build_edna_documents(samples, assays, detections)
            assert empty_documents == []
            inactive_docs = _merge_documents(
                connection,
                _document_frame(empty_documents),
            )
            assert inactive_docs["inactivated"] == 1
            assert connection.execute(
                text(
                    "SELECT count(*) FROM external_source_snapshot "
                    "WHERE snapshot_id = :snapshot_id"
                ),
                {"snapshot_id": identifiers["snapshot_id"]},
            ).scalar_one() == 1
        finally:
            transaction.rollback()


def test_reviewed_classification_import_replay_and_explicit_reversion(tmp_path, monkeypatch):
    from preprocessing.anemone import build_anemone_bundle
    from preprocessing.anemone_classification import review_template
    from tests.test_anemone_classification import approve_fixture, _remove_classification
    from tests.test_anemone_normalization import _acquire_snapshot

    raw_root = tmp_path / "raw"
    sid, contract = _acquire_snapshot(raw_root, mutate=_remove_classification)
    options = dict(raw_root=raw_root, contract=contract)
    original = build_anemone_bundle(sid, **options)
    review = approve_fixture(review_template(sid, **options))
    reviewed = build_anemone_bundle(sid, **options, classification_review=review)
    sample_id = reviewed.frames["edna_sample"].iloc[0]["sample_id"]
    original_metadata = original.frames["edna_sample"].iloc[0]["raw_metadata_json"]
    manifest = {"source_scope_level": "sample"}
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            _upsert_anemone_bundle(connection, frames=original.frames, manifest=manifest)
            documents = build_edna_documents(*_read_active_frames(connection))
            _merge_documents(connection, _document_frame(documents))
            changed, _ = _upsert_anemone_bundle(connection, frames=reviewed.frames, manifest=manifest)
            assert changed["edna_sample"]["scientific_corrections"] == 1
            assert changed["edna_detection"]["unchanged"] == 2
            replayed, _ = _upsert_anemone_bundle(connection, frames=reviewed.frames, manifest=manifest)
            assert replayed["edna_sample"]["unchanged"] == 1
            row = connection.execute(text("SELECT * FROM edna_sample WHERE sample_id=:id"), {"id": sample_id}).mappings().one()
            record = json.loads(row["classification_review_json"])
            assert row["raw_metadata_json"] == original_metadata
            assert row["sample_kind"] == "environmental" and row["is_control"] is False
            assert row["first_seen_snapshot_id"] == row["last_seen_snapshot_id"] == sid
            assert record["decision"] == review["decisions"][0]

            class SameTransactionEngine:
                def connect(self):
                    return nullcontext(connection)

            monkeypatch.setattr(edna_service, "get_engine", lambda: SameTransactionEngine())
            detail = edna_service.edna_sample_detail(sample_id)
            assert detail["sample"]["classification_review"] == record
            updated_docs = build_edna_documents(*_read_active_frames(connection))
            merge = _merge_documents(connection, _document_frame(updated_docs))
            assert merge["updated"] == 2
            assert all(d.metadata["classification_review"] == record for d in updated_docs if d.sample_id == sample_id)

            reverted, inactive = _upsert_anemone_bundle(connection, frames=original.frames, manifest=manifest)
            assert reverted["edna_sample"]["scientific_corrections"] == 1
            assert inactive["anchor_event"] == 1
            row = connection.execute(text("SELECT sample_kind, is_control, classification_review_json FROM edna_sample WHERE sample_id=:id"), {"id": sample_id}).one()
            assert tuple(row) == ("unknown", None, None)
        finally:
            transaction.rollback()
    engine.dispose()


def test_anemone_migration_downgrade_preserves_prior_schema_and_reupgrades():
    project_root = Path(__file__).resolve().parents[2]
    alembic_config = Config(str(project_root / "alembic.ini"))
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)

    command.downgrade(alembic_config, "20260825_0004")
    downgraded = inspect(engine)
    downgraded_tables = set(downgraded.get_table_names())
    assert "app_user" in downgraded_tables
    assert "external_source_snapshot" not in downgraded_tables
    assert "edna_detection" not in downgraded_tables
    assert "active" not in {
        column["name"] for column in downgraded.get_columns("anchor_event")
    }

    command.upgrade(alembic_config, "head")
    upgraded = inspect(engine)
    assert "edna_detection" in set(upgraded.get_table_names())
    assert "active" in {
        column["name"] for column in upgraded.get_columns("anchor_event")
    }
    retrieval_columns = {
        column["name"] for column in upgraded.get_columns("retrieval_document")
    }
    assert {
        "active",
        "provider",
        "assay_id",
        "assignment_method",
        "metadata_json",
    }.issubset(retrieval_columns)
    assert "classification_review_json" in {
        column["name"] for column in upgraded.get_columns("edna_sample")
    }


def test_edna_materialization_retains_scopes_and_filters_nonfeatured_taxa(monkeypatch):
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    first, _ = _frames("first")
    second, _ = _frames("second")
    replacements = {_hash(letter): _hash(str(index)) for index, letter in enumerate("abcdef")}
    second = {name: frame.replace(replacements) for name, frame in second.items()}
    second["edna_sample"]["is_control"] = None
    second["edna_sample"]["sample_kind"] = "unknown"
    second["edna_sample"]["lat"] = None
    second["edna_sample"]["lon"] = None
    base_detection = first["edna_detection"].iloc[0].to_dict()
    rows = []
    for index in range(12):
        rows.append({
            **base_detection,
            "detection_id": f"{index + 100:064x}",
            "read_count": index + 1,
            "sequence": "ACGT" + "A" * index,
            "sequence_sha256": hashlib.sha256(("ACGT" + "A" * index).encode()).hexdigest(),
            "genus": "RareTaxon" if index == 0 else "CommonTaxon",
        })
    rows.append({**base_detection, "detection_id": "9" * 64, "assignment_method": "qcauto_95pct_3nn_target", "genus": "AlternativeTaxon"})
    first["edna_detection"] = pd.DataFrame(rows)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            for frames in (first, second):
                _upsert_anemone_bundle(connection, frames=frames, manifest={"source_scope_level": "sample"})
            documents = build_edna_documents(*_read_active_frames(connection))
            assert len(documents) == 3
            assert {doc.provider_project_id for doc in documents} == {"project-first", "project-second"}
            rare = next(doc for doc in documents if doc.assignment_method == "qcauto_target" and doc.provider_project_id == "project-first")
            assert f"{100:064x}" not in rare.metadata["featured_detection_ids"]
            _merge_documents(connection, _document_frame(documents))
            monkeypatch.setattr(hybrid_retriever, "get_session", lambda: nullcontext(connection))
            monkeypatch.setattr(hybrid_retriever, "embed_text", lambda _query: [0.1] * config.EMBEDDING_DIM)
            results = hybrid_retriever.hybrid_search("MiFish", taxon="raretaxon", provider_project_id="project-first")
            assert [row.doc_id for row in results] == [rare.doc_id]
            assert hybrid_retriever.hybrid_search("MiFish", taxon="RareTaxon", assignment_method="qcauto_95pct_3nn_target") == []
            for index in range(20):
                connection.execute(text("INSERT INTO retrieval_document (doc_id, source_type, sample_id, assignment_method, title, text, text_tsv, active) VALUES (:id, 'edna_metabarcoding', :sample, 'qcauto_target', 'MiFish', :body, to_tsvector('english', :body), TRUE)"),
                    {'id': f'pr5-excluded-{index}', 'sample':'0'*64, 'body':'MiFish '*100})
            scoped = hybrid_retriever.hybrid_search('MiFish', k=1,
                sample_ids=[rare.sample_id], assignment_methods=['qcauto_target'])
            assert [r.doc_id for r in scoped] == [rare.doc_id]
            assert hybrid_retriever.hybrid_search('MiFish', sample_ids=[]) == []
            assert hybrid_retriever.hybrid_search('MiFish', assignment_methods=[]) == []
            from ingestion.artifact_store import ArtifactStore
            from tempfile import TemporaryDirectory
            with TemporaryDirectory(prefix='edna-publication-test-') as directory:
                with monkeypatch.context() as scoped_patch:
                    scoped_patch.setattr(config, 'EDNA_ARTIFACT_URI', Path(directory).as_uri())
                    store = ArtifactStore(config.EDNA_ARTIFACT_URI)
                    pending_generation = store.replace_pointer('retrieval/current.json', {'status':'pending'}, 0)
                    assert hybrid_retriever.hybrid_search('MiFish', sample_ids=[rare.sample_id]) == []
                    ready = {'status':'ready', 'generation_id':'a'*64, 'manifest_sha256':'b'*64}
                    store.replace_pointer('retrieval/current.json', ready, pending_generation)
                    assert hybrid_retriever.hybrid_search('MiFish', sample_ids=[rare.sample_id]) == []
                    connection.execute(text("INSERT INTO corpus_publication (channel, generation_id, manifest_sha256) VALUES ('edna', :generation, :sha) ON CONFLICT (channel) DO UPDATE SET generation_id=EXCLUDED.generation_id, manifest_sha256=EXCLUDED.manifest_sha256"), {'generation':'a'*64, 'sha':'b'*64})
                    assert hybrid_retriever.hybrid_search('MiFish', sample_ids=[rare.sample_id])
            connection.execute(text("UPDATE retrieval_document SET active = FALSE WHERE doc_id = :id"), {"id": rare.doc_id})
            assert hybrid_retriever.hybrid_search("MiFish", taxon="RareTaxon") == []
        finally:
            transaction.rollback()
