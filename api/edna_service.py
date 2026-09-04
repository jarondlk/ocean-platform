"""Read-only API queries for the active canonical eDNA corpus."""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

from sqlalchemy import text

from db.connection import get_engine
from schema.time_range import sql_time_conditions


EDNA_ASSIGNMENT_METHODS = frozenset(
    {"qcauto_target", "qcauto_95pct_3nn_target"}
)
EDNA_SAMPLE_KINDS = frozenset(
    {
        "environmental",
        "negative_control",
        "positive_control",
        "mock_community",
        "unknown",
    }
)
SAFE_SHA256 = re.compile(r"^[a-f0-9]{64}$")
TAXON_COLUMNS = (
    "assigned_taxon_name",
    "superkingdom",
    "kingdom",
    "phylum",
    '"class"',
    '"order"',
    "family",
    "genus",
    "species",
    "subspecies",
)


def validate_edna_id(value: str, label: str) -> str:
    if not SAFE_SHA256.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def _row(row: Any) -> dict[str, Any]:
    result = dict(row._mapping)
    for key in (
        "raw_metadata_json",
        "taxonomy_json",
        "source_row_numbers_json",
        "classification_review_json",
    ):
        value = result.get(key)
        if isinstance(value, str):
            try:
                result[key.removesuffix("_json")] = json.loads(value)
            except json.JSONDecodeError:
                result[key.removesuffix("_json")] = value
            del result[key]
    return result


def _scalar(connection: Any, statement: str, params: Mapping[str, Any] | None = None) -> int:
    return int(connection.execute(text(statement), dict(params or {})).scalar() or 0)


def _sample_conditions(filters: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    conditions = ["s.active IS TRUE"]
    params: dict[str, Any] = {}
    direct = {
        "provider": "s.provider",
        "provider_project_id": "s.provider_project_id",
        "provider_run_id": "s.provider_run_id",
        "sample_kind": "s.sample_kind",
        "sample_id": "s.sample_id",
    }
    for name, column in direct.items():
        value = filters.get(name)
        if value is not None:
            conditions.append(f"{column} = :{name}")
            params[name] = value
    if filters.get("is_control") is not None:
        conditions.append("s.is_control IS NOT DISTINCT FROM :is_control")
        params["is_control"] = filters["is_control"]
    if filters.get("assay_id") is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM edna_assay a WHERE a.sample_id = s.sample_id "
            "AND a.active IS TRUE AND a.assay_id = :assay_id)"
        )
        params["assay_id"] = filters["assay_id"]
    for name, column, operator in (
        ("lat_min", "s.lat", ">="),
        ("lat_max", "s.lat", "<="),
        ("lon_min", "s.lon", ">="),
        ("lon_max", "s.lon", "<="),
    ):
        value = filters.get(name)
        if value is not None:
            conditions.append(f"{column} {operator} :{name}")
            params[name] = value
    times, values = sql_time_conditions("s.collection_date_utc", filters.get("time_from"), filters.get("time_to"))
    conditions.extend(times)
    params.update(values)
    method = filters.get("assignment_method")
    taxon = filters.get("taxon")
    if method is not None or taxon is not None:
        detection_conditions = [
            "a.sample_id = s.sample_id",
            "a.active IS TRUE",
            "d.assay_id = a.assay_id",
            "d.active IS TRUE",
        ]
        if method is not None:
            detection_conditions.append("d.assignment_method = :assignment_method")
            params["assignment_method"] = method
        if taxon is not None:
            comparisons = " OR ".join(
                f"lower(d.{column}) = lower(:taxon)" for column in TAXON_COLUMNS
            )
            detection_conditions.append(f"({comparisons})")
            params["taxon"] = taxon
        conditions.append(
            "EXISTS (SELECT 1 FROM edna_assay AS a "
            "JOIN edna_detection AS d ON d.assay_id = a.assay_id WHERE "
            + " AND ".join(detection_conditions)
            + ")"
        )
    return conditions, params


def _detection_conditions(filters: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    conditions = ["s.active IS TRUE", "a.active IS TRUE", "d.active IS TRUE"]
    times, params = sql_time_conditions("s.collection_date_utc", filters.get("time_from"), filters.get("time_to"))
    conditions.extend(times)
    direct = {
        "sample_id": "s.sample_id",
        "assay_id": "a.assay_id",
        "provider": "s.provider",
        "provider_project_id": "s.provider_project_id",
        "provider_run_id": "s.provider_run_id",
        "assignment_method": "d.assignment_method",
        "sample_kind": "s.sample_kind",
    }
    for name, column in direct.items():
        value = filters.get(name)
        if value is not None:
            conditions.append(f"{column} = :{name}")
            params[name] = value
    if filters.get("is_control") is not None:
        conditions.append("s.is_control IS NOT DISTINCT FROM :is_control")
        params["is_control"] = filters["is_control"]
    taxon = filters.get("taxon")
    if taxon is not None:
        comparisons = " OR ".join(
            f"lower(d.{column}) = lower(:taxon)" for column in TAXON_COLUMNS
        )
        conditions.append(f"({comparisons})")
        params["taxon"] = taxon
    for name, column, operator in (
        ("lat_min", "s.lat", ">="),
        ("lat_max", "s.lat", "<="),
        ("lon_min", "s.lon", ">="),
        ("lon_max", "s.lon", "<="),
    ):
        value = filters.get(name)
        if value is not None:
            conditions.append(f"{column} {operator} :{name}")
            params[name] = value
    return conditions, params


def edna_catalog() -> dict[str, Any]:
    with get_engine().connect() as connection:
        counts = connection.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM edna_sample WHERE active IS TRUE) AS samples,
                  (SELECT count(*) FROM edna_assay WHERE active IS TRUE) AS assays,
                  (SELECT count(*) FROM edna_detection WHERE active IS TRUE) AS detections,
                  (SELECT count(*) FROM edna_sample WHERE active IS TRUE AND is_control IS TRUE) AS controls,
                  (SELECT count(*) FROM edna_sample WHERE active IS TRUE AND is_control IS NULL) AS unknown_control_status,
                  (SELECT min(collection_date_utc) FROM edna_sample WHERE active IS TRUE) AS time_min,
                  (SELECT max(collection_date_utc) FROM edna_sample WHERE active IS TRUE) AS time_max,
                  (SELECT min(lat) FROM edna_sample WHERE active IS TRUE) AS lat_min,
                  (SELECT max(lat) FROM edna_sample WHERE active IS TRUE) AS lat_max,
                  (SELECT min(lon) FROM edna_sample WHERE active IS TRUE) AS lon_min,
                  (SELECT max(lon) FROM edna_sample WHERE active IS TRUE) AS lon_max
                """
            )
        ).one()

        def values(column: str, table: str) -> list[str]:
            rows = connection.execute(
                text(
                    f"SELECT DISTINCT {column} AS value FROM {table} "
                    f"WHERE active IS TRUE AND {column} IS NOT NULL "
                    f"ORDER BY {column}"
                )
            )
            return [str(row.value) for row in rows]

        return {
            "samples": int(counts.samples or 0),
            "assays": int(counts.assays or 0),
            "detections": int(counts.detections or 0),
            "controls": int(counts.controls or 0),
            "unknown_control_status": int(counts.unknown_control_status or 0),
            "providers": values("provider", "edna_sample"),
            "projects": values("provider_project_id", "edna_sample"),
            "runs": values("provider_run_id", "edna_sample"),
            "assignment_methods": values("assignment_method", "edna_detection"),
            "sample_kinds": values("sample_kind", "edna_sample"),
            "time_extent": {"min": counts.time_min, "max": counts.time_max},
            "coordinate_extent": {
                "lat_min": counts.lat_min,
                "lat_max": counts.lat_max,
                "lon_min": counts.lon_min,
                "lon_max": counts.lon_max,
            },
        }


def edna_samples(
    filters: Mapping[str, Any],
    *,
    limit: int,
    offset: int,
    sort: str = "collection_date_utc",
    direction: str = "desc",
) -> dict[str, Any]:
    sort_columns = {
        "collection_date_utc": "s.collection_date_utc",
        "provider_sample_id": "s.provider_sample_id",
        "provider_project_id": "s.provider_project_id",
        "provider_run_id": "s.provider_run_id",
        "sample_kind": "s.sample_kind",
    }
    sort_column = sort_columns.get(sort)
    if sort_column is None or direction not in {"asc", "desc"}:
        raise ValueError("Unsupported eDNA sample sort")
    conditions, params = _sample_conditions(filters)
    where = " AND ".join(conditions)
    params.update({"limit": limit, "offset": offset})
    with get_engine().connect() as connection:
        total = _scalar(
            connection,
            f"SELECT count(*) FROM edna_sample AS s WHERE {where}",
            params,
        )
        rows = connection.execute(
            text(
                f"""
                SELECT s.sample_id, s.provider, s.provider_sample_id,
                       s.provider_project_id, s.provider_run_id, s.project_name,
                       s.original_sample_label, s.sample_kind, s.is_control,
                       s.classification_basis, s.collection_date_utc,
                       s.temporal_precision, s.lat, s.lon, s.anchor_event_id,
                       s.source_snapshot_id, s.source_file_id,
                       (SELECT count(*) FROM edna_assay a
                        WHERE a.sample_id = s.sample_id AND a.active IS TRUE) AS assay_count,
                       (SELECT count(*) FROM edna_detection d
                        JOIN edna_assay a ON a.assay_id = d.assay_id
                        WHERE a.sample_id = s.sample_id AND a.active IS TRUE
                          AND d.active IS TRUE) AS detection_count
                       ,(SELECT count(*) FROM edna_detection d
                        JOIN edna_assay a ON a.assay_id = d.assay_id
                        WHERE a.sample_id = s.sample_id AND a.active IS TRUE
                          AND d.active IS TRUE AND d.assignment_method = 'qcauto_target') AS qcauto_detection_count
                       ,(SELECT count(*) FROM edna_detection d
                        JOIN edna_assay a ON a.assay_id = d.assay_id
                        WHERE a.sample_id = s.sample_id AND a.active IS TRUE
                          AND d.active IS TRUE AND d.assignment_method = 'qcauto_95pct_3nn_target') AS three_nn_detection_count
                FROM edna_sample AS s
                WHERE {where}
                ORDER BY {sort_column} {direction.upper()} NULLS LAST, s.sample_id ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "rows": [_row(row) for row in rows]}


def _provenance(connection: Any, records: list[tuple[str, str, Any]]) -> dict[str, Any]:
    items = []
    seen: set[tuple[str, str]] = set()
    for entity_type, entity_id, record in records:
        source_file_id = record.source_file_id
        key = (entity_type, entity_id)
        if key in seen:
            continue
        seen.add(key)
        source = connection.execute(
            text(
                """
                SELECT f.source_file_id, f.snapshot_id, f.relative_path,
                       f.source_url, f.role, f.sha256, f.etag, f.last_modified,
                       f.validation_status, s.source_collection_sha256,
                       s.contract_version, s.contract_sha256
                FROM external_source_file AS f
                JOIN external_source_snapshot AS s ON s.snapshot_id = f.snapshot_id
                WHERE f.source_file_id = :source_file_id
                """
            ),
            {"source_file_id": source_file_id},
        ).first()
        items.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "source_row_locator": (
                    record.source_row_number
                    if hasattr(record, "source_row_number")
                    else json.loads(record.source_row_numbers_json)
                ),
                **(_row(source) if source else {"source_file_id": source_file_id}),
            }
        )
    return {"records": items}


def edna_sample_detail(sample_id: str) -> dict[str, Any] | None:
    validate_edna_id(sample_id, "sample_id")
    with get_engine().connect() as connection:
        sample = connection.execute(
            text("SELECT * FROM edna_sample WHERE sample_id = :id AND active IS TRUE"),
            {"id": sample_id},
        ).first()
        if sample is None:
            return None
        assays = connection.execute(
            text("SELECT * FROM edna_assay WHERE sample_id = :id AND active IS TRUE ORDER BY assay_id"),
            {"id": sample_id},
        ).fetchall()
        summaries = connection.execute(
            text(
                """
                SELECT d.assignment_method, count(*) AS detection_count,
                       sum(d.read_count) AS read_count_sum,
                       count(d.copies_per_ml) AS copies_per_ml_record_count
                FROM edna_detection d JOIN edna_assay a ON a.assay_id = d.assay_id
                WHERE a.sample_id = :id AND a.active IS TRUE AND d.active IS TRUE
                GROUP BY d.assignment_method ORDER BY d.assignment_method
                """
            ),
            {"id": sample_id},
        ).fetchall()
        provenance_records = [("sample", sample_id, sample)] + [
            ("assay", assay.assay_id, assay) for assay in assays
        ]
        return {
            "sample": _row(sample),
            "assays": [_row(row) for row in assays],
            "method_summaries": [_row(row) for row in summaries],
            "provenance": _provenance(connection, provenance_records),
        }


def edna_assay_detail(assay_id: str) -> dict[str, Any] | None:
    validate_edna_id(assay_id, "assay_id")
    with get_engine().connect() as connection:
        assay = connection.execute(
            text("SELECT * FROM edna_assay WHERE assay_id = :id AND active IS TRUE"),
            {"id": assay_id},
        ).first()
        if assay is None:
            return None
        sample = connection.execute(
            text("SELECT * FROM edna_sample WHERE sample_id = :id AND active IS TRUE"),
            {"id": assay.sample_id},
        ).first()
        if sample is None:
            return None
        summaries = connection.execute(
            text(
                """
                SELECT assignment_method, count(*) AS detection_count,
                       sum(read_count) AS read_count_sum,
                       count(copies_per_ml) AS copies_per_ml_record_count
                FROM edna_detection WHERE assay_id = :id AND active IS TRUE
                GROUP BY assignment_method ORDER BY assignment_method
                """
            ),
            {"id": assay_id},
        ).fetchall()
        standards = connection.execute(
            text(
                "SELECT * FROM edna_internal_standard "
                "WHERE assay_id = :id AND active IS TRUE ORDER BY internal_standard_id"
            ),
            {"id": assay_id},
        ).fetchall()
        provenance_records = [
            ("sample", sample.sample_id, sample),
            ("assay", assay_id, assay),
            *[("internal_standard", row.internal_standard_id, row) for row in standards],
        ]
        return {
            "assay": _row(assay),
            "sample": _row(sample),
            "method_summaries": [_row(row) for row in summaries],
            "internal_standards": [_row(row) for row in standards],
            "provenance": _provenance(connection, provenance_records),
        }


def edna_detections(
    filters: Mapping[str, Any],
    *,
    limit: int,
    offset: int,
    sort: str = "read_count",
    direction: str = "desc",
    include_sequence: bool = False,
) -> dict[str, Any]:
    sort_columns = {
        "read_count": "d.read_count",
        "copies_per_ml": "d.copies_per_ml",
        "assigned_taxon_name": "d.assigned_taxon_name",
        "collection_date_utc": "s.collection_date_utc",
        "detection_id": "d.detection_id",
    }
    sort_column = sort_columns.get(sort)
    if sort_column is None or direction not in {"asc", "desc"}:
        raise ValueError("Unsupported eDNA detection sort")
    conditions, params = _detection_conditions(filters)
    where = " AND ".join(conditions)
    params.update({"limit": limit, "offset": offset})
    sequence_column = "d.sequence," if include_sequence else ""
    base = (
        "FROM edna_detection AS d "
        "JOIN edna_assay AS a ON a.assay_id = d.assay_id "
        "JOIN edna_sample AS s ON s.sample_id = a.sample_id "
        "JOIN external_source_file AS f ON f.source_file_id = d.source_file_id "
        f"WHERE {where}"
    )
    with get_engine().connect() as connection:
        total = _scalar(connection, f"SELECT count(*) {base}", params)
        rows = connection.execute(
            text(
                f"""
                SELECT d.detection_id, d.assay_id, s.sample_id, s.provider,
                       s.provider_sample_id, s.provider_project_id,
                       s.provider_run_id, s.sample_kind, s.is_control,
                       s.collection_date_utc, s.lat, s.lon,
                       a.target_gene, a.primer_set, a.sequencing_method,
                       d.assignment_method, {sequence_column} d.sequence_sha256,
                       d.read_count, d.copies_per_ml, d.superkingdom, d.kingdom,
                       d.phylum, d."class" AS class, d."order" AS "order",
                       d.family, d.genus, d.species, d.subspecies,
                       d.assigned_taxon_name, d.assigned_taxon_rank,
                       d.source_snapshot_id, d.source_file_id,
                       d.source_row_number, f.source_url, f.sha256 AS source_sha256
                {base}
                ORDER BY {sort_column} {direction.upper()} NULLS LAST, d.detection_id ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "rows": [_row(row) for row in rows]}


def edna_detection_detail(detection_id: str) -> dict[str, Any] | None:
    validate_edna_id(detection_id, "detection_id")
    with get_engine().connect() as connection:
        detection = connection.execute(
            text("SELECT * FROM edna_detection WHERE detection_id = :id AND active IS TRUE"),
            {"id": detection_id},
        ).first()
        if detection is None:
            return None
        assay = connection.execute(
            text("SELECT * FROM edna_assay WHERE assay_id = :id AND active IS TRUE"),
            {"id": detection.assay_id},
        ).first()
        if assay is None:
            return None
        sample = connection.execute(
            text("SELECT * FROM edna_sample WHERE sample_id = :id AND active IS TRUE"),
            {"id": assay.sample_id},
        ).first()
        if sample is None:
            return None
        return {
            "detection": _row(detection),
            "assay": _row(assay),
            "sample": _row(sample),
            "provenance": _provenance(
                connection,
                [
                    ("sample", sample.sample_id, sample),
                    ("assay", assay.assay_id, assay),
                    ("detection", detection_id, detection),
                ],
            ),
        }
