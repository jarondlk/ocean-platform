#!/usr/bin/env python3
"""
scripts/load_db.py – Load normalized data into PostgreSQL + pgvector.

1. Creates all tables (init_db)
2. Loads anchor events, CTD, metagenome, SST, and retrieval documents
3. Populates tsvector column for FTS
4. Optionally embeds documents via Ollama

Usage:
    python scripts/load_db.py --upsert        # transactional incremental load
    python scripts/load_db.py --upsert --embed
    python scripts/load_db.py --reset        # drop and recreate corpus tables
    python scripts/load_db.py --upsert --dry-run --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import Boolean as SQLBoolean
from sqlalchemy import DateTime as SQLDateTime
from sqlalchemy import Float as SQLFloat
from sqlalchemy import Integer as SQLInteger
from sqlalchemy import Numeric as SQLNumeric
from sqlalchemy import String
from sqlalchemy import text

import config
from db.connection import drop_corpus_tables, get_engine, get_session, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("load_db")


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def add_source_row_hash(df: pd.DataFrame) -> pd.DataFrame:
    """Attach a stable SHA-256 hash for every normalized database row."""
    output = df.copy()
    columns = sorted(
        column for column in output.columns if column != "source_row_hash"
    )
    output["source_row_hash"] = [
        hashlib.sha256(
            json.dumps(
                {column: _json_value(row[column]) for column in columns},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        for _, row in output.iterrows()
    ]
    return output


def _database_column_definitions(
    table_name: str,
) -> dict[str, dict[str, Any]]:
    return {
        column["name"]: column
        for column in sa_inspect(get_engine()).get_columns(table_name)
    }


def _prepare_dataframe(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    definitions = _database_column_definitions(table_name)
    db_columns = set(definitions)
    df = df.copy()
    for column in df.columns:
        definition = definitions.get(column)
        if definition and isinstance(definition["type"], String):
            df[column] = df[column].map(
                lambda value: (
                    None
                    if value is None or bool(pd.isna(value))
                    else str(value)
                )
            )
        elif definition and isinstance(
            definition["type"],
            (SQLFloat, SQLNumeric),
        ):
            df[column] = pd.to_numeric(df[column], errors="coerce").astype(
                float
            )
        elif definition and isinstance(definition["type"], SQLInteger):
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            ).astype("Int64")
        elif definition and isinstance(definition["type"], SQLBoolean):
            df[column] = df[column].astype("boolean")
        elif definition and isinstance(definition["type"], SQLDateTime):
            df[column] = pd.to_datetime(df[column], errors="coerce")
    if "source_row_hash" in db_columns and "source_row_hash" not in df.columns:
        df = add_source_row_hash(df)
    keep_columns = [column for column in df.columns if column in db_columns]
    if not keep_columns:
        raise ValueError(f"{table_name}: no incoming columns match the database")
    return df[keep_columns]


def load_parquet_to_table(
    parquet_path: Path,
    table_name: str,
    column_map: dict | None = None,
    if_exists: str = "append",
) -> int:
    """Load a parquet file into a DB table using pandas + SQLAlchemy."""
    if not parquet_path.exists():
        logger.warning("  Skipping %s – file not found: %s", table_name, parquet_path)
        return 0

    df = pd.read_parquet(parquet_path)
    if column_map:
        df = df.rename(columns=column_map)

    engine = get_engine()

    df = _prepare_dataframe(df, table_name)

    df.to_sql(table_name, engine, if_exists=if_exists, index=False, method="multi")
    logger.info("  Loaded %d rows → %s", len(df), table_name)
    return len(df)


def load_retrieval_documents() -> int:
    """Load retrieval documents from parquet."""
    path = config.SERVING_DIR / "retrieval_documents.parquet"
    if not path.exists():
        logger.warning("  retrieval_documents.parquet not found")
        return 0

    df = pd.read_parquet(path)
    engine = get_engine()
    df = _prepare_dataframe(df, "retrieval_document")
    df.to_sql("retrieval_document", engine, if_exists="append", index=False, method="multi")
    logger.info("  Loaded %d retrieval documents", len(df))
    return len(df)


def update_fts_vectors() -> None:
    """Populate the text_tsv column for full-text search."""
    with get_session() as session:
        session.execute(text("""
            UPDATE retrieval_document
            SET text_tsv = to_tsvector('english', coalesce(title, '') || ' ' || coalesce(text, ''))
            WHERE text_tsv IS NULL
        """))
    logger.info("  Updated FTS vectors")


def load_cross_source_links() -> int:
    """Load cross-source links from parquet."""
    path = config.CANONICAL_DIR / "cross_source_links.parquet"
    return load_parquet_to_table(path, "cross_source_link")


def load_anchor_events() -> int:
    """Load anchor events from parquet."""
    path = config.CANONICAL_DIR / "anchor_events.parquet"
    return load_parquet_to_table(path, "anchor_event")


def metagenome_samples_dataframe() -> pd.DataFrame:
    """Build metagenome database rows from the multisource context."""
    path = config.SERVING_DIR / "sample_multisource_context.parquet"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_parquet(path)

    # Map columns to DB model
    records = []
    for _, row in df.iterrows():
        sid = row.get("sample_id")
        if pd.isna(sid):
            continue
        has_kr = row.get("has_kraken", False)
        has_me = row.get("has_metaeuk", False)
        if not has_kr and not has_me:
            continue

        records.append({
            "sample_id": sid,
            "bay": row.get("bay"),
            "station_code": row.get("station_code"),
            "sample_year_month": row.get("sample_year_month"),
            "n_runs": int(row["n_runs"]) if pd.notna(row.get("n_runs")) else None,
            "first_run_date": row.get("first_run_date"),
            "last_run_date": row.get("last_run_date"),
            "sum_reads_gt1kb": row.get("sum_reads_gt1kb"),
            "sum_bases_gt1kb": row.get("sum_bases_gt1kb"),
            "has_kraken": bool(has_kr),
            "has_metaeuk": bool(has_me),
            "has_ctd": bool(row.get("has_ctd", False)),
            "top_kraken_genera_json": row.get("top_genus_10_json_x"),
            "top_metaeuk_genera_json": row.get("top_genus_10_json_y"),
            "top_upper_groups_json": row.get("top_upper_group_10_json"),
        })

    return pd.DataFrame(records)


def load_metagenome_samples() -> int:
    """Load metagenome sample records from the multisource context."""
    df = metagenome_samples_dataframe()
    if not df.empty:
        engine = get_engine()
        df = _prepare_dataframe(df, "metagenome_sample")
        df.to_sql(
            "metagenome_sample", engine, if_exists="append", index=False, method="multi"
        )
    logger.info("  Loaded %d metagenome samples", len(df))
    return len(df)


def _incoming_table_frames() -> list[tuple[str, pd.DataFrame, list[str]]]:
    specs = [
        (
            "anchor_event",
            config.CANONICAL_DIR / "anchor_events.parquet",
            ["event_id"],
        ),
        (
            "ctd_profile",
            config.NORMALIZED_DIR / "ctd_profile_standardized.parquet",
            ["sample_id", "ctd_date", "depth_m"],
        ),
        (
            "ctd_summary",
            config.NORMALIZED_DIR / "ctd_summary.parquet",
            ["sample_id"],
        ),
        (
            "sst_point_observation",
            config.NORMALIZED_DIR / "sst_point_timeseries.parquet",
            ["file", "time_utc"],
        ),
        (
            "sst_daily_summary",
            config.NORMALIZED_DIR / "sst_daily_summary.parquet",
            ["date_jst"],
        ),
        (
            "retrieval_document",
            config.SERVING_DIR / "retrieval_documents.parquet",
            ["doc_id"],
        ),
        (
            "cross_source_link",
            config.CANONICAL_DIR / "cross_source_links.parquet",
            ["source_event_id", "target_event_id", "link_type"],
        ),
    ]
    frames: list[tuple[str, pd.DataFrame, list[str]]] = []
    for table_name, path, keys in specs:
        if not path.exists():
            logger.warning("  Skipping %s – file not found: %s", table_name, path)
            continue
        frames.append((table_name, pd.read_parquet(path), keys))
    metagenome = metagenome_samples_dataframe()
    if not metagenome.empty:
        frames.insert(
            3,
            ("metagenome_sample", metagenome, ["sample_id"]),
        )
    return frames


def _quoted_join(
    preparer: Any,
    *,
    target_alias: str,
    source_alias: str,
    key_columns: list[str],
) -> str:
    return " AND ".join(
        f"{target_alias}.{preparer.quote(column)} "
        f"IS NOT DISTINCT FROM {source_alias}.{preparer.quote(column)}"
        for column in key_columns
    )


def _upsert_count_summary(
    *,
    matched: int,
    replaced: int,
    inserted_after_delete: int,
) -> dict[str, int]:
    """Separate new inserts from changed rows replaced by the merge."""
    new_rows = inserted_after_delete - replaced
    if new_rows < 0 or replaced > matched:
        raise RuntimeError(
            "Database returned inconsistent row counts during corpus upsert"
        )
    return {
        "updated": replaced,
        "inserted": new_rows,
        "unchanged": matched - replaced,
    }


def _upsert_dataframe(
    connection: Any,
    *,
    table_name: str,
    incoming: pd.DataFrame,
    key_columns: list[str],
) -> dict[str, int]:
    incoming = _prepare_dataframe(incoming, table_name)
    missing_keys = [
        column for column in key_columns if column not in incoming.columns
    ]
    if missing_keys:
        raise ValueError(
            f"{table_name}: missing upsert keys: {', '.join(missing_keys)}"
        )
    if incoming[key_columns].isna().any(axis=None):
        raise ValueError(f"{table_name}: upsert keys contain null values")
    duplicate_count = int(incoming.duplicated(key_columns, keep=False).sum())
    if duplicate_count:
        raise ValueError(
            f"{table_name}: {duplicate_count} rows have duplicate upsert keys"
        )

    preparer = connection.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    temporary_table = f"_ocean_upsert_{table_name}_{uuid.uuid4().hex[:10]}"
    quoted_temporary = preparer.quote(temporary_table)
    columns = list(incoming.columns)
    quoted_columns = ", ".join(preparer.quote(column) for column in columns)
    source_columns = ", ".join(
        f"source.{preparer.quote(column)}" for column in columns
    )
    join_condition = _quoted_join(
        preparer,
        target_alias="target",
        source_alias="source",
        key_columns=key_columns,
    )
    compare_columns = [
        column
        for column in columns
        if column not in key_columns and column != "source_row_hash"
    ]
    changed_condition = " OR ".join(
        f"target.{preparer.quote(column)} "
        f"IS DISTINCT FROM source.{preparer.quote(column)}"
        for column in compare_columns
    ) or "FALSE"

    incoming.to_sql(
        temporary_table,
        connection,
        if_exists="fail",
        index=False,
        method="multi",
    )
    matched = int(
        connection.exec_driver_sql(
            f"SELECT count(*) FROM {quoted_table} AS target "
            f"JOIN {quoted_temporary} AS source ON {join_condition}"
        ).scalar_one()
    )
    replaced = int(
        connection.exec_driver_sql(
            f"DELETE FROM {quoted_table} AS target "
            f"USING {quoted_temporary} AS source "
            f"WHERE {join_condition} AND ({changed_condition})"
        ).rowcount
        or 0
    )
    inserted_after_delete = int(
        connection.exec_driver_sql(
            f"INSERT INTO {quoted_table} ({quoted_columns}) "
            f"SELECT {source_columns} FROM {quoted_temporary} AS source "
            f"WHERE NOT EXISTS ("
            f"SELECT 1 FROM {quoted_table} AS target WHERE {join_condition}"
            f")"
        ).rowcount
        or 0
    )
    counts = _upsert_count_summary(
        matched=matched,
        replaced=replaced,
        inserted_after_delete=inserted_after_delete,
    )
    hashes_refreshed = 0
    if "source_row_hash" in columns:
        quoted_hash = preparer.quote("source_row_hash")
        hashes_refreshed = connection.exec_driver_sql(
            f"UPDATE {quoted_table} AS target "
            f"SET {quoted_hash} = source.{quoted_hash} "
            f"FROM {quoted_temporary} AS source "
            f"WHERE {join_condition} "
            f"AND target.{quoted_hash} "
            f"IS DISTINCT FROM source.{quoted_hash}"
        ).rowcount
    connection.exec_driver_sql(f"DROP TABLE IF EXISTS {quoted_temporary}")

    return {
        "incoming": len(incoming),
        "matched": matched,
        **counts,
        "hashes_refreshed": int(hashes_refreshed or 0),
    }


def _immutable_insert_dataframe(
    connection: Any,
    *,
    table_name: str,
    incoming: pd.DataFrame,
    key_columns: list[str],
) -> dict[str, int]:
    """Insert append-only rows and reject identity/content conflicts."""
    incoming = _prepare_dataframe(incoming, table_name)
    if incoming.empty:
        return {
            "incoming": 0,
            "matched": 0,
            "updated": 0,
            "inserted": 0,
            "unchanged": 0,
        }
    if incoming[key_columns].isna().any(axis=None):
        raise ValueError(f"{table_name}: immutable keys contain null values")
    if incoming.duplicated(key_columns, keep=False).any():
        raise ValueError(f"{table_name}: immutable keys are duplicated")
    preparer = connection.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    temporary_table = f"_ocean_immutable_{table_name}_{uuid.uuid4().hex[:10]}"
    quoted_temporary = preparer.quote(temporary_table)
    incoming.to_sql(
        temporary_table,
        connection,
        if_exists="fail",
        index=False,
        method="multi",
    )
    join = _quoted_join(
        preparer,
        target_alias="target",
        source_alias="source",
        key_columns=key_columns,
    )
    compare_columns = [
        column for column in incoming.columns if column not in key_columns
    ]
    conflict = " OR ".join(
        f"target.{preparer.quote(column)} "
        f"IS DISTINCT FROM source.{preparer.quote(column)}"
        for column in compare_columns
    ) or "FALSE"
    conflict_count = int(
        connection.exec_driver_sql(
            f"SELECT count(*) FROM {quoted_table} AS target "
            f"JOIN {quoted_temporary} AS source ON {join} "
            f"WHERE {conflict}"
        ).scalar_one()
    )
    if conflict_count:
        raise RuntimeError(
            f"{table_name}: immutable identity conflicts with existing content"
        )
    columns = list(incoming.columns)
    quoted_columns = ", ".join(preparer.quote(column) for column in columns)
    source_columns = ", ".join(
        f"source.{preparer.quote(column)}" for column in columns
    )
    inserted = int(
        connection.exec_driver_sql(
            f"INSERT INTO {quoted_table} ({quoted_columns}) "
            f"SELECT {source_columns} FROM {quoted_temporary} AS source "
            f"WHERE NOT EXISTS ("
            f"SELECT 1 FROM {quoted_table} AS target WHERE {join}"
            f")"
        ).rowcount
        or 0
    )
    connection.exec_driver_sql(f"DROP TABLE IF EXISTS {quoted_temporary}")
    return {
        "incoming": len(incoming),
        "matched": len(incoming) - inserted,
        "updated": 0,
        "inserted": inserted,
        "unchanged": len(incoming) - inserted,
    }


def _merge_edna_dataframe(
    connection: Any,
    *,
    table_name: str,
    incoming: pd.DataFrame,
    key_column: str,
) -> dict[str, int]:
    """Merge current eDNA rows without deleting referenced parent records."""
    incoming = _prepare_dataframe(incoming, table_name)
    if incoming.empty:
        return {
            "incoming": 0,
            "matched": 0,
            "updated": 0,
            "inserted": 0,
            "scientific_corrections": 0,
            "provenance_refreshes": 0,
            "unchanged": 0,
        }
    required = {
        key_column,
        "scientific_content_sha256",
        "source_row_hash",
        "active",
        "first_seen_snapshot_id",
        "last_seen_snapshot_id",
    }
    missing = sorted(required - set(incoming.columns))
    if missing:
        raise ValueError(
            f"{table_name}: missing eDNA merge columns: {', '.join(missing)}"
        )
    if incoming[[key_column]].isna().any(axis=None):
        raise ValueError(f"{table_name}: eDNA key contains null values")
    if incoming.duplicated([key_column], keep=False).any():
        raise ValueError(f"{table_name}: eDNA key is duplicated")
    preparer = connection.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    quoted_key = preparer.quote(key_column)
    temporary_table = f"_ocean_edna_{table_name}_{uuid.uuid4().hex[:10]}"
    quoted_temporary = preparer.quote(temporary_table)
    incoming.to_sql(
        temporary_table,
        connection,
        if_exists="fail",
        index=False,
        method="multi",
    )
    join = (
        f"target.{quoted_key} IS NOT DISTINCT FROM source.{quoted_key}"
    )
    matched = int(
        connection.exec_driver_sql(
            f"SELECT count(*) FROM {quoted_table} AS target "
            f"JOIN {quoted_temporary} AS source ON {join}"
        ).scalar_one()
    )
    scientific = int(
        connection.exec_driver_sql(
            f"SELECT count(*) FROM {quoted_table} AS target "
            f"JOIN {quoted_temporary} AS source ON {join} "
            "WHERE target.scientific_content_sha256 "
            "IS DISTINCT FROM source.scientific_content_sha256"
        ).scalar_one()
    )
    provenance = int(
        connection.exec_driver_sql(
            f"SELECT count(*) FROM {quoted_table} AS target "
            f"JOIN {quoted_temporary} AS source ON {join} "
            "WHERE target.scientific_content_sha256 "
            "IS NOT DISTINCT FROM source.scientific_content_sha256 "
            "AND (target.source_row_hash IS DISTINCT FROM source.source_row_hash "
            "OR target.active IS DISTINCT FROM TRUE)"
        ).scalar_one()
    )
    update_columns = [
        column
        for column in incoming.columns
        if column not in {key_column, "first_seen_snapshot_id"}
    ]
    assignments = ", ".join(
        f"{preparer.quote(column)} = source.{preparer.quote(column)}"
        for column in update_columns
    )
    connection.exec_driver_sql(
        f"UPDATE {quoted_table} AS target SET {assignments} "
        f"FROM {quoted_temporary} AS source WHERE {join} "
        "AND (target.source_row_hash IS DISTINCT FROM source.source_row_hash "
        "OR target.active IS DISTINCT FROM TRUE)"
    )
    columns = list(incoming.columns)
    quoted_columns = ", ".join(preparer.quote(column) for column in columns)
    source_columns = ", ".join(
        f"source.{preparer.quote(column)}" for column in columns
    )
    inserted = int(
        connection.exec_driver_sql(
            f"INSERT INTO {quoted_table} ({quoted_columns}) "
            f"SELECT {source_columns} FROM {quoted_temporary} AS source "
            f"WHERE NOT EXISTS ("
            f"SELECT 1 FROM {quoted_table} AS target WHERE {join}"
            f")"
        ).rowcount
        or 0
    )
    connection.exec_driver_sql(f"DROP TABLE IF EXISTS {quoted_temporary}")
    return {
        "incoming": len(incoming),
        "matched": matched,
        "updated": scientific + provenance,
        "inserted": inserted,
        "scientific_corrections": scientific,
        "provenance_refreshes": provenance,
        "unchanged": matched - scientific - provenance,
    }


def _load_anemone_bundle_frames(
    normalization_id: str | None,
    *,
    allow_noncurrent: bool,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]] | None:
    from preprocessing.anemone import resolve_normalized_bundle

    pointer_path = config.ANEMONE_NORMALIZED_DIR / "current.json"
    pointer_id: str | None = None
    if pointer_path.exists():
        try:
            pointer_id = str(
                json.loads(pointer_path.read_text(encoding="utf-8")).get(
                    "normalization_id"
                )
                or ""
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("ANEMONE current normalization pointer is invalid") from exc
    if normalization_id is None and not pointer_id:
        return None
    if (
        normalization_id
        and pointer_id
        and normalization_id != pointer_id
        and not allow_noncurrent
    ):
        raise ValueError(
            "Explicit ANEMONE normalization differs from current.json; "
            "use --allow-anemone-noncurrent to override"
        )
    root, manifest = resolve_normalized_bundle(
        normalization_id,
        normalized_root=config.ANEMONE_NORMALIZED_DIR,
    )
    expected = (
        "external_source_snapshot",
        "external_source_file",
        "edna_sample",
        "edna_assay",
        "edna_detection",
        "edna_internal_standard",
        "edna_anchor_event",
    )
    frames: dict[str, pd.DataFrame] = {}
    for name in expected:
        artifact = manifest.get("artifacts", {}).get(name)
        if not artifact:
            raise ValueError(f"ANEMONE bundle is missing artifact {name}")
        artifact_path = root / str(artifact["path"])
        if not artifact_path.is_file():
            raise ValueError(f"ANEMONE bundle artifact is missing: {name}")
        expected_sha = str(artifact.get("sha256") or "")
        actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if not expected_sha or actual_sha != expected_sha:
            raise ValueError(f"ANEMONE bundle artifact hash changed for {name}")
        frames[name] = pd.read_parquet(artifact_path)
        if len(frames[name]) != int(artifact["row_count"]):
            raise ValueError(f"ANEMONE bundle row count changed for {name}")
    return frames, manifest


def _scope_parameters(
    samples: pd.DataFrame,
    manifest: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if samples.empty:
        raise ValueError("ANEMONE bundle contains no samples")
    first = samples.iloc[0]
    parameters = {"provider": str(first["provider"])}
    if manifest.get("source_scope_level") == "sample":
        if len(samples) != 1:
            raise ValueError("ANEMONE sample scope contains multiple samples")
        parameters["provider_sample_id"] = str(first["provider_sample_id"])
        return (
            "{alias}.provider = :provider AND "
            "{alias}.provider_sample_id = :provider_sample_id",
            parameters,
        )
    projects = set(samples["provider_project_id"].astype(str))
    runs = set(samples["provider_run_id"].astype(str))
    if len(projects) != 1 or len(runs) != 1:
        raise ValueError("ANEMONE run bundle spans multiple provider runs")
    parameters["provider_project_id"] = projects.pop()
    parameters["provider_run_id"] = runs.pop()
    return (
        "{alias}.provider = :provider AND "
        "{alias}.provider_project_id = :provider_project_id AND "
        "{alias}.provider_run_id = :provider_run_id",
        parameters,
    )


def _inactivate_missing_anemone_rows(
    connection: Any,
    *,
    frames: dict[str, pd.DataFrame],
    manifest: dict[str, Any],
) -> dict[str, int]:
    scope_template, parameters = _scope_parameters(
        frames["edna_sample"],
        manifest,
    )
    preparer = connection.dialect.identifier_preparer
    specs = (
        (
            "edna_detection",
            "detection_id",
            "edna_assay AS assay JOIN edna_sample AS sample "
            "ON assay.sample_id = sample.sample_id",
            "target.assay_id = assay.assay_id",
            "sample",
        ),
        (
            "edna_internal_standard",
            "internal_standard_id",
            "edna_assay AS assay JOIN edna_sample AS sample "
            "ON assay.sample_id = sample.sample_id",
            "target.assay_id = assay.assay_id",
            "sample",
        ),
        (
            "edna_assay",
            "assay_id",
            "edna_sample AS sample",
            "target.sample_id = sample.sample_id",
            "sample",
        ),
        ("edna_sample", "sample_id", None, None, "target"),
        (
            "anchor_event",
            "event_id",
            "edna_sample AS sample",
            "target.sample_id = sample.sample_id "
            "AND target.source_types = 'edna_metabarcoding'",
            "sample",
        ),
    )
    counts: dict[str, int] = {}
    for table_name, key_column, from_clause, join_clause, scope_alias in specs:
        frame_name = "edna_anchor_event" if table_name == "anchor_event" else table_name
        incoming = frames[frame_name]
        keys = (
            incoming[key_column].dropna().astype(str).tolist()
            if key_column in incoming.columns
            else []
        )
        temporary = f"_ocean_edna_keys_{table_name}_{uuid.uuid4().hex[:10]}"
        pd.DataFrame({key_column: pd.Series(keys, dtype="string")}).to_sql(
            temporary,
            connection,
            if_exists="fail",
            index=False,
        )
        quoted_temp = preparer.quote(temporary)
        quoted_key = preparer.quote(key_column)
        sql = (
            f"UPDATE {preparer.quote(table_name)} AS target "
            "SET active = FALSE "
        )
        if from_clause:
            sql += f"FROM {from_clause} "
        conditions = []
        if join_clause:
            conditions.append(join_clause)
        conditions.append(scope_template.format(alias=scope_alias))
        conditions.append("target.active IS TRUE")
        conditions.append(
            f"NOT EXISTS (SELECT 1 FROM {quoted_temp} AS incoming "
            f"WHERE incoming.{quoted_key} = target.{quoted_key})"
        )
        sql += "WHERE " + " AND ".join(conditions)
        counts[table_name] = int(
            connection.execute(text(sql), parameters).rowcount or 0
        )
        connection.exec_driver_sql(f"DROP TABLE IF EXISTS {quoted_temp}")
    return counts


def _upsert_anemone_bundle(
    connection: Any,
    *,
    frames: dict[str, pd.DataFrame],
    manifest: dict[str, Any],
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    results: dict[str, dict[str, int]] = {}
    results["external_source_snapshot"] = _immutable_insert_dataframe(
        connection,
        table_name="external_source_snapshot",
        incoming=frames["external_source_snapshot"],
        key_columns=["snapshot_id"],
    )
    results["external_source_file"] = _immutable_insert_dataframe(
        connection,
        table_name="external_source_file",
        incoming=frames["external_source_file"],
        key_columns=["source_file_id"],
    )
    results["anchor_event"] = _upsert_dataframe(
        connection,
        table_name="anchor_event",
        incoming=frames["edna_anchor_event"],
        key_columns=["event_id"],
    ) if not frames["edna_anchor_event"].empty else {
        "incoming": 0,
        "matched": 0,
        "updated": 0,
        "inserted": 0,
        "unchanged": 0,
        "hashes_refreshed": 0,
    }
    for table_name, key_column in (
        ("edna_sample", "sample_id"),
        ("edna_assay", "assay_id"),
        ("edna_detection", "detection_id"),
        ("edna_internal_standard", "internal_standard_id"),
    ):
        results[table_name] = _merge_edna_dataframe(
            connection,
            table_name=table_name,
            incoming=frames[table_name],
            key_column=key_column,
        )
    inactive = _inactivate_missing_anemone_rows(
        connection,
        frames=frames,
        manifest=manifest,
    )
    return results, inactive


def upsert_corpus(
    *,
    anemone_normalization_id: str | None = None,
    allow_anemone_noncurrent: bool = False,
) -> dict[str, Any]:
    """Transactionally merge incoming corpus rows while retaining stale rows."""
    anemone_bundle = _load_anemone_bundle_frames(
        anemone_normalization_id,
        allow_noncurrent=allow_anemone_noncurrent,
    )
    init_db()
    engine = get_engine()
    table_results: dict[str, dict[str, int]] = {}
    with engine.begin() as connection:
        connection.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtext('ocean_platform_corpus_upsert'))"
            )
        )
        for table_name, frame, key_columns in _incoming_table_frames():
            result = _upsert_dataframe(
                connection,
                table_name=table_name,
                incoming=frame,
                key_columns=key_columns,
            )
            table_results[table_name] = result
            logger.info(
                "  Upserted %s: incoming=%d inserted=%d updated=%d unchanged=%d",
                table_name,
                result["incoming"],
                result["inserted"],
                result["updated"],
                result["unchanged"],
            )
        anemone_inactive: dict[str, int] = {}
        anemone_manifest: dict[str, Any] | None = None
        if anemone_bundle is not None:
            anemone_frames, anemone_manifest = anemone_bundle
            anemone_results, anemone_inactive = _upsert_anemone_bundle(
                connection,
                frames=anemone_frames,
                manifest=anemone_manifest,
            )
            for table_name, result in anemone_results.items():
                if table_name in table_results:
                    prior = table_results[table_name]
                    table_results[table_name] = {
                        key: int(prior.get(key, 0)) + int(result.get(key, 0))
                        for key in set(prior) | set(result)
                    }
                else:
                    table_results[table_name] = result
                logger.info(
                    "  Upserted ANEMONE %s: incoming=%d inserted=%d "
                    "updated=%d unchanged=%d",
                    table_name,
                    result["incoming"],
                    result["inserted"],
                    result["updated"],
                    result["unchanged"],
                )
        connection.execute(
            text(
                """
                UPDATE retrieval_document
                SET text_tsv = to_tsvector(
                    'english',
                    coalesce(title, '') || ' ' || coalesce(text, '')
                )
                WHERE text_tsv IS NULL
                """
            )
        )
    return {
        "mode": "upsert",
        "stale_rows_deleted": False,
        "tables": table_results,
        "incoming_rows": sum(
            result["incoming"] for result in table_results.values()
        ),
        "inserted_rows": sum(
            result["inserted"] for result in table_results.values()
        ),
        "updated_rows": sum(
            result["updated"] for result in table_results.values()
        ),
        "unchanged_rows": sum(
            result["unchanged"] for result in table_results.values()
        ),
        "anemone": {
            "included": anemone_bundle is not None,
            "normalization_id": (
                anemone_manifest.get("normalization_id")
                if anemone_manifest
                else None
            ),
            "scientific_corrections": sum(
                int(result.get("scientific_corrections") or 0)
                for result in table_results.values()
            ),
            "provenance_refreshes": sum(
                int(result.get("provenance_refreshes") or 0)
                for result in table_results.values()
            ),
            "inactivated": anemone_inactive,
            "noncurrent_override": allow_anemone_noncurrent,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Load data into PostgreSQL")
    parser.add_argument("--embed", action="store_true", help="Compute embeddings via Ollama")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate corpus tables (users, invites, and feedback are preserved)",
    )
    parser.add_argument(
        "--upsert",
        action="store_true",
        help="Transactionally insert or update incoming rows; stale rows are retained.",
    )
    parser.add_argument("--dry-run", action="store_true", help="With --upsert, produce a read-only lineage-aware upsert plan.")
    parser.add_argument("--limit-keys", type=int, default=25, help="Maximum example keys to show per dry-run upsert table.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON for dry-run upsert planning.")
    parser.add_argument(
        "--anemone-normalization-id",
        help=(
            "Load this immutable ANEMONE normalized bundle "
            "(defaults to current.json)."
        ),
    )
    parser.add_argument(
        "--allow-anemone-noncurrent",
        action="store_true",
        help=(
            "Allow an explicit ANEMONE bundle that differs from current.json."
        ),
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Loading data into PostgreSQL")
    logger.info("=" * 60)

    if args.reset and args.upsert:
        raise SystemExit(
            "Choose exactly one database mutation mode: --reset or --upsert."
        )
    if not args.reset and not args.upsert:
        raise SystemExit("Choose a safe database mutation mode: --upsert or --reset.")
    if args.reset and (
        args.anemone_normalization_id or args.allow_anemone_noncurrent
    ):
        raise SystemExit("ANEMONE bundle options require --upsert.")
    if args.allow_anemone_noncurrent and not args.anemone_normalization_id:
        raise SystemExit(
            "--allow-anemone-noncurrent requires --anemone-normalization-id."
        )

    if args.upsert and args.dry_run:
        from ingestion.lineage import build_upsert_dry_run_plan

        plan_kwargs: dict[str, Any] = {"limit_keys": args.limit_keys}
        if args.anemone_normalization_id:
            plan_kwargs["anemone_normalization_id"] = (
                args.anemone_normalization_id
            )
        if args.allow_anemone_noncurrent:
            plan_kwargs["allow_anemone_noncurrent"] = True
        plan = build_upsert_dry_run_plan(**plan_kwargs)
        if args.json:
            print(json.dumps(plan, indent=2, default=str))
        else:
            summary = plan["summary"]
            print("Upsert dry-run plan")
            print(f"database_available={summary['database_available']}")
            print(f"incoming_rows={summary['incoming_rows']}")
            print(f"planned_inserts={summary['planned_inserts']}")
            print(f"candidate_updates={summary['candidate_updates']}")
            print(f"stale_existing={summary['stale_existing']}")
            print(f"embedding_refresh_candidates={summary['embedding_refresh_candidates']}")
            for table_plan in plan["table_plans"]:
                print(
                    "{table}: incoming={incoming_count} existing={existing_count} "
                    "insert={planned_inserts} update={candidate_updates} stale={stale_existing}".format(**table_plan)
                )
        return

    if args.upsert:
        upsert_kwargs: dict[str, Any] = {}
        if args.anemone_normalization_id:
            upsert_kwargs["anemone_normalization_id"] = (
                args.anemone_normalization_id
            )
        if args.allow_anemone_noncurrent:
            upsert_kwargs["allow_anemone_noncurrent"] = True
        summary = upsert_corpus(**upsert_kwargs)
        if args.embed:
            logger.info("Computing missing or changed embeddings...")
            from db.vector_store import update_document_embeddings

            summary["embedded_documents"] = update_document_embeddings()
        if args.json:
            print(json.dumps(summary, indent=2, default=str))
        logger.info("=" * 60)
        logger.info("Transactional database upsert complete!")
        return

    if args.reset:
        logger.warning("Dropping corpus tables...")
        drop_corpus_tables()

    init_db()

    # Load data
    load_anchor_events()

    load_parquet_to_table(
        config.NORMALIZED_DIR / "ctd_profile_standardized.parquet",
        "ctd_profile",
    )
    load_parquet_to_table(
        config.NORMALIZED_DIR / "ctd_summary.parquet",
        "ctd_summary",
    )

    load_metagenome_samples()

    load_parquet_to_table(
        config.NORMALIZED_DIR / "sst_point_timeseries.parquet",
        "sst_point_observation",
    )
    load_parquet_to_table(
        config.NORMALIZED_DIR / "sst_daily_summary.parquet",
        "sst_daily_summary",
    )

    load_retrieval_documents()
    update_fts_vectors()

    load_cross_source_links()

    if args.embed:
        logger.info("Computing embeddings...")
        from db.vector_store import update_document_embeddings
        n = update_document_embeddings()
        logger.info("Embedded %d documents", n)

    logger.info("=" * 60)
    logger.info("Database load complete!")


if __name__ == "__main__":
    main()
