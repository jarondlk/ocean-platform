"""Materialize active canonical eDNA rows into retrieval documents."""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

import config
from ingestion.immutable_bundle import digest, seal_bundle, read_bundle
from retrieval.edna_publication import publication_root, set_pending, set_ready
from db.connection import get_engine
from db.models import RetrievalDocument as RetrievalDocumentRow
from retrieval.document_builder import documents_to_dataframe
from retrieval.edna_document_builder import (
    EDNA_SOURCE_TYPE,
    build_edna_documents,
    document_source_row_hash,
)


logger = logging.getLogger(__name__)

EDNA_RETRIEVAL_PARQUET = "anemone_retrieval_documents.parquet"
EDNA_RETRIEVAL_JSONL = "anemone_retrieval_documents.jsonl"


def _read_active_frames(connection: Any) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    samples = pd.read_sql_query(
        text("SELECT * FROM edna_sample WHERE active IS TRUE ORDER BY sample_id LIMIT 2001"),
        connection,
    )
    assays = pd.read_sql_query(
        text("SELECT * FROM edna_assay WHERE active IS TRUE ORDER BY assay_id LIMIT 2001"),
        connection,
    )
    detections = pd.read_sql_query(
        text(
            "SELECT * FROM edna_detection "
            "WHERE active IS TRUE ORDER BY assay_id, assignment_method, detection_id LIMIT 250001"
        ),
        connection,
    )
    if len(samples) > 2000 or len(assays) > 2000 or len(detections) > 250000:
        raise ValueError('eDNA materialization exceeds pilot row limits')
    return samples, assays, detections


def _document_frame(documents: list[Any]) -> pd.DataFrame:
    frame = documents_to_dataframe(documents)
    if frame.empty:
        return frame
    frame["source_row_hash"] = [
        document_source_row_hash(document) for document in documents
    ]
    return frame


def _merge_documents(connection: Any, frame: pd.DataFrame) -> dict[str, int]:
    """Upsert eDNA documents while retaining embeddings for metadata-only changes."""
    preparer = connection.dialect.identifier_preparer
    target = preparer.quote("retrieval_document")
    incoming_ids = frame.get("doc_id", pd.Series(dtype="string")).astype(str).tolist()

    if frame.empty:
        inactivated = int(
            connection.execute(
                text(
                    "UPDATE retrieval_document SET active = FALSE "
                    "WHERE source_type = :source_type AND active IS TRUE"
                ),
                {"source_type": EDNA_SOURCE_TYPE},
            ).rowcount
            or 0
        )
        return {
            "incoming": 0,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "embedding_invalidated": 0,
            "inactivated": inactivated,
        }

    temporary = "_ocean_edna_retrieval_incoming"
    connection.exec_driver_sql(f"DROP TABLE IF EXISTS {temporary}")
    frame.to_sql(
        temporary,
        connection,
        if_exists="fail",
        index=False,
        method="multi",
        dtype={
            column: RetrievalDocumentRow.__table__.c[column].type
            for column in frame.columns
        },
    )
    quoted_temp = preparer.quote(temporary)
    matched = int(
        connection.exec_driver_sql(
            f"SELECT count(*) FROM {target} AS target "
            f"JOIN {quoted_temp} AS source ON target.doc_id = source.doc_id"
        ).scalar_one()
    )
    changed = int(
        connection.exec_driver_sql(
            f"SELECT count(*) FROM {target} AS target "
            f"JOIN {quoted_temp} AS source ON target.doc_id = source.doc_id "
            "WHERE target.source_row_hash IS DISTINCT FROM source.source_row_hash "
            "OR target.active IS DISTINCT FROM TRUE"
        ).scalar_one()
    )
    content_changed = int(
        connection.exec_driver_sql(
            f"SELECT count(*) FROM {target} AS target "
            f"JOIN {quoted_temp} AS source ON target.doc_id = source.doc_id "
            "WHERE target.title IS DISTINCT FROM source.title "
            "OR target.text IS DISTINCT FROM source.text"
        ).scalar_one()
    )
    columns = list(frame.columns)
    non_key_columns = [column for column in columns if column != "doc_id"]
    assignments = ", ".join(
        f"{preparer.quote(column)} = source.{preparer.quote(column)}"
        for column in non_key_columns
    )
    connection.exec_driver_sql(
        f"UPDATE {target} AS target SET {assignments}, "
        "embedding = CASE WHEN (target.title IS DISTINCT FROM source.title "
        "OR target.text IS DISTINCT FROM source.text) THEN NULL ELSE target.embedding END, "
        "embedding_provider = CASE WHEN (target.title IS DISTINCT FROM source.title "
        "OR target.text IS DISTINCT FROM source.text) THEN NULL ELSE target.embedding_provider END, "
        "embedding_model = CASE WHEN (target.title IS DISTINCT FROM source.title "
        "OR target.text IS DISTINCT FROM source.text) THEN NULL ELSE target.embedding_model END, "
        "embedding_dim = CASE WHEN (target.title IS DISTINCT FROM source.title "
        "OR target.text IS DISTINCT FROM source.text) THEN NULL ELSE target.embedding_dim END, "
        "embedded_at = CASE WHEN (target.title IS DISTINCT FROM source.title "
        "OR target.text IS DISTINCT FROM source.text) THEN NULL ELSE target.embedded_at END, "
        "text_tsv = to_tsvector('english', coalesce(source.title, '') || ' ' || coalesce(source.text, '')) "
        f"FROM {quoted_temp} AS source WHERE target.doc_id = source.doc_id "
        "AND (target.source_row_hash IS DISTINCT FROM source.source_row_hash "
        "OR target.active IS DISTINCT FROM TRUE)"
    )
    quoted_columns = ", ".join(preparer.quote(column) for column in columns)
    source_columns = ", ".join(
        f"source.{preparer.quote(column)}" for column in columns
    )
    inserted = int(
        connection.exec_driver_sql(
            f"INSERT INTO {target} ({quoted_columns}, text_tsv) "
            f"SELECT {source_columns}, "
            "to_tsvector('english', coalesce(source.title, '') || ' ' || coalesce(source.text, '')) "
            f"FROM {quoted_temp} AS source WHERE NOT EXISTS ("
            f"SELECT 1 FROM {target} AS target WHERE target.doc_id = source.doc_id)"
        ).rowcount
        or 0
    )
    inactivated = int(
        connection.exec_driver_sql(
            f"UPDATE {target} AS target SET active = FALSE "
            f"WHERE target.source_type = '{EDNA_SOURCE_TYPE}' "
            "AND target.active IS TRUE AND NOT EXISTS ("
            f"SELECT 1 FROM {quoted_temp} AS source "
            "WHERE source.doc_id = target.doc_id)"
        ).rowcount
        or 0
    )
    connection.exec_driver_sql(f"DROP TABLE IF EXISTS {quoted_temp}")
    return {
        "incoming": len(incoming_ids),
        "inserted": inserted,
        "updated": changed,
        "unchanged": matched - changed,
        "embedding_invalidated": content_changed,
        "inactivated": inactivated,
    }


def _write_artifacts(documents: list[Any], frame: pd.DataFrame, *, publish=True) -> dict:
    if not config.EDNA_ARTIFACT_URI:
        config.SERVING_DIR.mkdir(parents=True, exist_ok=True)
    root = publication_root()
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    generation = digest([document_source_row_hash(d) for d in documents])
    parquet_temp = staging / EDNA_RETRIEVAL_PARQUET
    jsonl_temp = staging / EDNA_RETRIEVAL_JSONL

    artifact_frame = frame.copy()
    if artifact_frame.empty:
        artifact_frame = pd.DataFrame(
            columns=[
                "doc_id",
                "source_type",
                "sample_id",
                "event_id",
                "time",
                "lat",
                "lon",
                "bay",
                "station",
                "title",
                "text",
                "active",
                "provider",
                "provider_project_id",
                "provider_run_id",
                "assay_id",
                "assignment_method",
                "sample_kind",
                "is_control",
                "source_snapshot_id",
                "metadata_json",
                "source_row_hash",
            ]
        )
    artifact_frame.to_parquet(parquet_temp, index=False)
    with jsonl_temp.open("w", encoding="utf-8") as handle:
        for document in documents:
            row = artifact_frame.loc[
                artifact_frame["doc_id"] == document.doc_id
            ].iloc[0].to_dict()
            row["id"] = row["doc_id"]
            row["date"] = row.get("time") or ""
            row["metadata"] = document.metadata
            row.pop("metadata_json", None)
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    manifest = seal_bundle(staging, root, generation, {"document_count": len(documents)})
    if config.EDNA_ARTIFACT_URI:
        from ingestion.artifact_store import ArtifactStore
        _, files = read_bundle(root, generation, expected_digest=digest(manifest))
        ArtifactStore(config.EDNA_ARTIFACT_URI).publish('retrieval', generation, files,
            metadata={'manifest_sha256': digest(manifest)})
    if publish:
        set_ready(manifest)
    return {"parquet": str(root / generation / EDNA_RETRIEVAL_PARQUET),
            "jsonl": str(root / generation / EDNA_RETRIEVAL_JSONL), "manifest": manifest}


def materialize_edna_retrieval(
    *,
    execute: bool,
    write_artifacts: bool = True,
) -> dict[str, Any]:
    """Plan or execute a database-wide active eDNA retrieval refresh."""
    engine = get_engine()
    documents: list[Any]
    frame: pd.DataFrame
    merge: dict[str, int] | None = None
    artifacts: dict[str, str] = {}
    with engine.connect() as connection:
        # Session lock spans commit AND pointer publication; acquire it before
        # starting the repeatable-read snapshot so waiting cannot yield stale input.
        if execute:
            connection.exec_driver_sql("SELECT pg_advisory_lock(hashtext('ocean_platform_corpus_upsert'))")
            connection.commit()
        try:
            if execute:
                set_pending()
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                samples, assays, detections = _read_active_frames(connection)
                documents = build_edna_documents(samples, assays, detections)
                frame = _document_frame(documents)
                if execute:
                    if write_artifacts:
                        artifacts = _write_artifacts(documents, frame, publish=False)
                    merge = _merge_documents(connection, frame)
                    manifest = artifacts.get("manifest")
                    if manifest:
                        connection.execute(text("INSERT INTO corpus_publication (channel, generation_id, manifest_sha256) VALUES ('edna', :generation, :sha) ON CONFLICT (channel) DO UPDATE SET generation_id=EXCLUDED.generation_id, manifest_sha256=EXCLUDED.manifest_sha256"), {"generation": manifest["id"], "sha": digest(manifest)})
            if artifacts:
                set_ready(artifacts["manifest"])
        finally:
            if execute:
                connection.rollback()
                connection.exec_driver_sql("SELECT pg_advisory_unlock(hashtext('ocean_platform_corpus_upsert'))")
                connection.commit()
    return {
        "execute": execute,
        "source_type": EDNA_SOURCE_TYPE,
        "active_samples": len(samples),
        "active_assays": len(assays),
        "active_detections": len(detections),
        "documents": len(documents),
        "merge": merge,
        "artifacts": artifacts,
    }
