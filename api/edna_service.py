"""Read-only API queries for the active canonical eDNA corpus."""
from __future__ import annotations

import json
from contextlib import contextmanager, nullcontext
import re
from typing import Any, Mapping

from sqlalchemy import text

from db.connection import get_engine
from preprocessing.anemone_classification import (
    ReviewError,
    parse_review_lineage,
    validate_sample_review_lineage,
)
from preprocessing.edna_eligibility import evaluate_analysis_eligibility
from preprocessing.edna_recipe import METHODS
from schema.time_range import sql_time_conditions


EDNA_ASSIGNMENT_METHODS = frozenset(
    {"qcauto_target", "qcauto_95pct_3nn_target", "qcauto_nontarget", "qcauto_95pct_3nn_nontarget"}
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


@contextmanager
def _read_snapshot():
    """Keep page totals, rows and eligibility on the same database generation."""
    with get_engine().connect() as connection:
        if getattr(getattr(connection, "dialect", None), "name", None) == "postgresql" and not connection.in_transaction():
            connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        yield connection


def validate_edna_id(value: str, label: str) -> str:
    if not SAFE_SHA256.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def _row(row: Any) -> dict[str, Any]:
    result = dict(row._mapping)
    for key in (
        "raw_metadata_json",
        "raw_metadata_rows_json",
        "provider_note_json",
        "community_availability_json",
        "taxonomy_json",
        "source_row_numbers_json",
    ):
        value = result.get(key)
        if isinstance(value, str):
            try:
                result[key.removesuffix("_json")] = json.loads(value)
            except json.JSONDecodeError:
                result[key.removesuffix("_json")] = value
            del result[key]
    if "classification_review_json" in result:
        raw_lineage = result.pop("classification_review_json")
        try:
            required = {
                "sample_kind",
                "is_control",
                "classification_basis",
                "source_snapshot_id",
                "provider_sample_id",
            }
            if required.issubset(result):
                lineage = validate_sample_review_lineage(
                    raw_lineage,
                    sample_kind=result["sample_kind"],
                    is_control=result["is_control"],
                    classification_basis=result["classification_basis"],
                    source_snapshot_id=result["source_snapshot_id"],
                    provider_sample_id=result["provider_sample_id"],
                )
            else:
                lineage = parse_review_lineage(raw_lineage) if raw_lineage is not None else None
        except ReviewError as exc:
            raise ValueError("Canonical classification lineage is invalid") from exc
        if lineage is not None:
            result["classification_review"] = lineage
    return result


def _scalar(connection: Any, statement: str, params: Mapping[str, Any] | None = None) -> int:
    return int(connection.execute(text(statement), dict(params or {})).scalar() or 0)


def environmental_analysis_eligibility(
    sample: Mapping[str, Any], assay_count: int
) -> dict[str, Any]:
    """Compatibility summary for callers that only know whether an assay exists."""
    assays = (
        [{"assay_id": "known", "target_gene": "known", "primer_set": "known", "sequencing_method": "known"}]
        if assay_count
        else []
    )
    result = evaluate_analysis_eligibility(
        sample,
        assays,
        {"known": METHODS} if assay_count else {},
        METHODS,
    )
    return {
        "analysis_eligibility": result["analysis_eligibility"],
        "exclusion_reasons": result["exclusion_reasons"],
    }


def _sample_eligibility(
    connection: Any,
    samples: list[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    sample_ids = sorted({str(sample["sample_id"]) for sample in samples})
    if not sample_ids:
        return {}
    rows = connection.execute(
        text(
            """
            SELECT a.sample_id, a.assay_id, a.target_gene, a.primer_set,
                   a.sequencing_method, a.library_layout, a.community_availability_json,
                   d.assignment_method
            FROM edna_assay AS a
            LEFT JOIN (
                SELECT DISTINCT assay_id, assignment_method
                FROM edna_detection
                WHERE active IS TRUE
            ) AS d ON d.assay_id = a.assay_id
            WHERE a.active IS TRUE AND a.sample_id = ANY(:sample_ids)
            ORDER BY a.sample_id, a.assay_id, d.assignment_method
            """
        ),
        {"sample_ids": sample_ids},
    ).fetchall()
    assays_by_sample: dict[str, dict[str, dict[str, Any]]] = {}
    methods_by_assay: dict[str, set[str]] = {}
    for row in rows:
        item = dict(row._mapping)
        method = item.pop("assignment_method")
        sample_id = str(item["sample_id"])
        assay_id = str(item["assay_id"])
        assays_by_sample.setdefault(sample_id, {})[assay_id] = item
        availability = item.get("community_availability_json")
        if availability:
            methods_by_assay.setdefault(assay_id, set()).update(json.loads(availability))
        if method is not None:
            methods_by_assay.setdefault(assay_id, set()).add(str(method))
    return {
        str(sample["sample_id"]): evaluate_analysis_eligibility(
            sample,
            list(assays_by_sample.get(str(sample["sample_id"]), {}).values()),
            methods_by_assay,
            METHODS,
        )
        for sample in samples
    }


def _detection_eligibility(row: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate the one assay/method represented by a detection API row."""
    result = evaluate_analysis_eligibility(
        row,
        [
            {
                "assay_id": row["assay_id"],
                "target_gene": row.get("target_gene"),
                "primer_set": row.get("primer_set"),
                "sequencing_method": row.get("sequencing_method"),
                "active": True,
            }
        ],
        {str(row["assay_id"]): {str(row["assignment_method"])}},
        [str(row["assignment_method"])],
    )
    method = result["method_eligibility"][0]
    if row["assignment_method"] not in METHODS:
        method["analysis_eligibility"] = "excluded"
        method["exclusion_reasons"].append("method_not_supported")
    return method


def _sample_conditions(filters: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    conditions = ["s.active IS TRUE"]
    params: dict[str, Any] = {}
    direct = {
        "provider": "s.provider",
        "provider_locus": "s.provider_locus",
        "provider_team": "s.provider_team",
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
    target_status = filters.get("target_status")
    if method is not None or taxon is not None or target_status is not None:
        detection_conditions = [
            "a.sample_id = s.sample_id",
            "a.active IS TRUE",
            "d.assay_id = a.assay_id",
            "d.active IS TRUE",
        ]
        if filters.get("assay_id") is not None:
            detection_conditions.append("a.assay_id = :assay_id")
        if target_status is not None:
            detection_conditions.append("d.target_status = :target_status")
            params["target_status"] = target_status
        if method is not None:
            detection_conditions.append("d.assignment_method = :assignment_method")
            params["assignment_method"] = method
        if taxon is not None:
            comparisons = " OR ".join(
                f"lower(d.{column}) = lower(:taxon)" for column in TAXON_COLUMNS
            )
            detection_conditions.append(f"({comparisons})")
            params["taxon"] = taxon
        detection_match = (
            "EXISTS (SELECT 1 FROM edna_assay AS a "
            "JOIN edna_detection AS d ON d.assay_id = a.assay_id WHERE "
            + " AND ".join(detection_conditions) + ")"
        )
        if taxon is None:
            # An available table may contain zero detections. The assay's
            # versioned source evidence, not a fabricated detection, proves it.
            available = []
            if filters.get("assay_id") is not None:
                available.append("a.assay_id = :assay_id")
            if method is not None:
                available.append("m.method = :assignment_method")
            if target_status is not None:
                available.append("CASE WHEN m.method LIKE '%_nontarget' THEN 'nontarget' ELSE 'target' END = :target_status")
            availability_match = (
                "EXISTS (SELECT 1 FROM edna_assay a CROSS JOIN LATERAL "
                "jsonb_object_keys(COALESCE(a.community_availability_json, '{}')::jsonb) AS m(method) "
                "WHERE a.sample_id=s.sample_id AND a.active IS TRUE AND "
                + " AND ".join(available) + ")"
            )
            detection_match = "(" + detection_match + " OR " + availability_match + ")"
        conditions.append(detection_match)
    return conditions, params


def _detection_conditions(filters: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    conditions = ["s.active IS TRUE", "a.active IS TRUE", "d.active IS TRUE"]
    times, params = sql_time_conditions("s.collection_date_utc", filters.get("time_from"), filters.get("time_to"))
    conditions.extend(times)
    direct = {
        "sample_id": "s.sample_id",
        "assay_id": "a.assay_id",
        "provider": "s.provider",
        "provider_locus": "s.provider_locus",
        "provider_team": "s.provider_team",
        "provider_project_id": "s.provider_project_id",
        "provider_run_id": "s.provider_run_id",
        "assignment_method": "d.assignment_method",
        "target_status": "d.target_status",
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




def _aggregate_assay_conditions(filters):
    base = {key:value for key,value in filters.items() if key not in {"assignment_method", "target_status", "taxon"}}
    conditions, params = _sample_conditions(base)
    conditions.append("a.active IS TRUE")
    if filters.get("assay_id") is not None:
        conditions.append("a.assay_id = :assay_id")
    if any(filters.get(key) is not None for key in ("assignment_method", "target_status", "taxon")):
        detection, detection_params = _detection_conditions(filters)
        params.update(detection_params)
        match = "EXISTS (SELECT 1 FROM edna_detection d WHERE d.assay_id=a.assay_id AND " + " AND ".join(detection) + ")"
        if filters.get("taxon") is None:
            available = []
            if filters.get("assignment_method") is not None:
                available.append("m.key = :assignment_method")
            if filters.get("target_status") is not None:
                available.append("CASE WHEN m.key LIKE '%_nontarget' THEN 'nontarget' ELSE 'target' END = :target_status")
            match = "(" + match + " OR EXISTS (SELECT 1 FROM jsonb_object_keys(COALESCE(a.community_availability_json,'{}')::jsonb) AS m(key) WHERE " + " AND ".join(available) + "))"
        conditions.append(match)
    return conditions, params

def edna_summary(filters: Mapping[str, Any], *, connection=None, group_by=()) -> dict[str, Any]:
    """Exact whole-cohort SQL totals, with alternative methods kept separate."""
    if len(group_by) > 2 or len(set(group_by)) != len(group_by) or any(key not in {"provider_locus", "provider_team", "provider_project_id", "provider_run_id"} for key in group_by):
        raise ValueError("Unsupported aggregate grouping")
    sample_conditions, sample_params = _sample_conditions(filters)
    conditions, params = _detection_conditions(filters)
    with (nullcontext(connection) if connection is not None else _read_snapshot()) as connection:
        generations = {row.channel: {"generation_id": row.generation_id, "manifest_sha256": row.manifest_sha256}
                       for row in connection.execute(text("SELECT channel,generation_id,manifest_sha256 FROM corpus_publication WHERE channel IN ('anemone-canonical','edna','edna-canonical')"))}
        sample_counts = connection.execute(text(
            "SELECT count(*) AS source_occurrences, "
            "count(DISTINCT s.provider_locus) AS loci, "
            "count(DISTINCT (s.provider_locus,s.provider_team)) AS teams, "
            "count(DISTINCT (s.provider_locus,s.provider_team,s.provider_project_id)) AS projects, "
            "count(DISTINCT (s.provider_locus,s.provider_team,s.provider_project_id,s.provider_run_id)) AS runs, "
            "count(*) FILTER (WHERE s.is_control IS TRUE) AS controls, "
            "count(*) FILTER (WHERE s.is_control IS NULL) AS unknown_control_status, "
            "count(*) FILTER (WHERE s.sample_kind = 'environmental' AND s.is_control IS FALSE) AS environmental_classified "
            "FROM edna_sample s WHERE " + " AND ".join(sample_conditions)
        ), sample_params).mappings().one()
        methods = connection.execute(text(
            "SELECT d.assignment_method,d.target_status,count(*) AS assignment_rows, "
            "count(DISTINCT a.assay_id) AS assays_with_detections, "
            "COALESCE(sum(d.read_count),0) AS read_count_sum, "
            "count(*) FILTER (WHERE d.copies_per_ml IS NOT NULL) AS concentration_records, "
            "count(*) FILTER (WHERE d.concentration_status = 'missing') AS concentration_missing, "
            "count(*) FILTER (WHERE d.concentration_status = 'column_absent') AS concentration_column_absent "
            "FROM edna_sample s JOIN edna_assay a ON a.sample_id=s.sample_id "
            "JOIN edna_detection d ON d.assay_id=a.assay_id WHERE "
            + " AND ".join(conditions) + " GROUP BY d.assignment_method,d.target_status ORDER BY d.assignment_method"
        ), params).mappings().all()
        assay_conditions, assay_params = _aggregate_assay_conditions(filters)
        assay_count = _scalar(connection, "SELECT count(*) FROM edna_assay a JOIN edna_sample s ON s.sample_id=a.sample_id WHERE " + " AND ".join(assay_conditions), assay_params)
        availability_conditions = list(assay_conditions)
        if filters.get("assignment_method") is not None:
            availability_conditions.append("m.key = :assignment_method")
        if filters.get("target_status") is not None:
            availability_conditions.append("CASE WHEN m.key LIKE '%_nontarget' THEN 'nontarget' ELSE 'target' END = :target_status")
        availability = connection.execute(text(
            "SELECT m.key AS assignment_method,count(*) AS available_tables, "
            "count(*) FILTER (WHERE m.value->>'row_count' = '0') AS empty_tables "
            "FROM edna_assay a JOIN edna_sample s ON s.sample_id=a.sample_id "
            "CROSS JOIN LATERAL jsonb_each(COALESCE(a.community_availability_json,'{}')::jsonb) m WHERE "
            + " AND ".join(availability_conditions) + " GROUP BY m.key ORDER BY m.key"
        ), assay_params).mappings().all()
        standards = connection.execute(text(
            "SELECT count(*) AS rows,COALESCE(sum(i.read_count),0) AS reads FROM edna_internal_standard i "
            "JOIN edna_assay a ON a.assay_id=i.assay_id JOIN edna_sample s ON s.sample_id=a.sample_id "
            "WHERE i.active IS TRUE AND " + " AND ".join(assay_conditions)
        ), assay_params).mappings().one()
        kinds = connection.execute(text("SELECT s.sample_kind,count(*) AS n FROM edna_sample s WHERE "
            + " AND ".join(sample_conditions) + " GROUP BY s.sample_kind ORDER BY s.sample_kind"), sample_params).mappings().all()
        groups = []
        if group_by:
            columns = ','.join('s.' + key for key in group_by)
            groups = connection.execute(text("SELECT " + columns + ",count(*) AS source_occurrences FROM edna_sample s WHERE "
                + " AND ".join(sample_conditions) + " GROUP BY " + columns + " ORDER BY " + columns + " LIMIT 2001"), sample_params).mappings().all()
            if len(groups) > 2000:
                raise ValueError("Aggregate grouping exceeds 2000 groups; narrow the filters")
        return {"publication": generations,
                "namespaces": {key:int(sample_counts[key]) for key in ("loci", "teams", "projects", "runs")},
                "sample_kinds": {row['sample_kind']: int(row['n']) for row in kinds},
                "internal_standards": {key:int(value) for key,value in standards.items()},
                "group_by": list(group_by), "groups": [dict(row) for row in groups], "filters": dict(filters),
                "community_availability": [dict(row) for row in availability],
                "scope": "all active canonical rows matching the explicit filters; no retrieval top-k limit",
                "sample_count_definition": "provider source occurrences; physical sample linkage unresolved",
                "physical_sample_count": None, "assays": assay_count,
                **{k: int(v) for k, v in sample_counts.items() if k not in {"loci", "teams", "projects", "runs"}},
                "methods": [{k: int(v) if k not in {"assignment_method", "target_status"} else v for k, v in row.items()} for row in methods],
                "interpretation": "Assignment methods share sequence evidence; do not sum their reads as independent observations. Missing detections do not establish biological absence."}

def edna_catalog() -> dict[str, Any]:
    with _read_snapshot() as connection:
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
            "loci": values("provider_locus", "edna_sample"),
            "teams": values("provider_team", "edna_sample"),
            "physical_sample_count": None,
            "sample_count_definition": "provider source occurrences; physical sample linkage unresolved",
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
    with _read_snapshot() as connection:
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
                       s.provider_locus, s.provider_team, s.source_occurrence_id, s.physical_sample_id, s.coordinate_precision,
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
        result_rows = [_row(row) for row in rows]
        eligibility = _sample_eligibility(connection, result_rows)
    for item in result_rows:
        item.update(eligibility[str(item["sample_id"])])
    return {"total": total, "limit": limit, "offset": offset, "rows": result_rows}


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
    with _read_snapshot() as connection:
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
        sample_payload = _row(sample)
        sample_payload.update(
            _sample_eligibility(connection, [sample_payload])[sample_id]
        )
        return {
            "sample": sample_payload,
            "assays": [_row(row) for row in assays],
            "method_summaries": [_row(row) for row in summaries],
            "provenance": _provenance(connection, provenance_records),
        }


def edna_assay_detail(assay_id: str) -> dict[str, Any] | None:
    validate_edna_id(assay_id, "assay_id")
    with _read_snapshot() as connection:
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
        sample_payload = _row(sample)
        eligibility = _sample_eligibility(connection, [sample_payload])[str(sample.sample_id)]
        sample_payload.update(eligibility)
        assay_payload = _row(assay)
        assay_payload["method_eligibility"] = [
            row
            for row in eligibility["method_eligibility"]
            if row["assay_id"] == str(assay.assay_id)
        ]
        return {
            "assay": assay_payload,
            "sample": sample_payload,
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
    with _read_snapshot() as connection:
        total = _scalar(connection, f"SELECT count(*) {base}", params)
        rows = connection.execute(
            text(
                f"""
                SELECT d.detection_id, d.assay_id, s.sample_id, s.provider,
                       s.provider_sample_id, s.provider_project_id,
                       s.provider_run_id, s.sample_kind, s.is_control,
                       s.collection_date_utc, s.lat, s.lon,
                       a.target_gene, a.primer_set, a.sequencing_method,
                       s.provider_locus, s.provider_team, s.coordinate_precision,
                       d.assignment_algorithm, d.target_status, d.concentration_status,
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
    result_rows = [_row(row) for row in rows]
    for item in result_rows:
        eligibility = _detection_eligibility(item)
        item["analysis_eligibility"] = eligibility["analysis_eligibility"]
        item["exclusion_reasons"] = eligibility["exclusion_reasons"]
    return {"total": total, "limit": limit, "offset": offset, "rows": result_rows}


def edna_detection_detail(detection_id: str) -> dict[str, Any] | None:
    validate_edna_id(detection_id, "detection_id")
    with _read_snapshot() as connection:
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
        sample_payload = _row(sample)
        eligibility = _sample_eligibility(connection, [sample_payload])[str(sample.sample_id)]
        sample_payload.update(eligibility)
        assay_payload = _row(assay)
        assay_payload["method_eligibility"] = [
            row
            for row in eligibility["method_eligibility"]
            if row["assay_id"] == str(assay.assay_id)
        ]
        detection_payload = _row(detection)
        selected_method = next(
            row
            for row in assay_payload["method_eligibility"]
            if row["assignment_method"] == str(detection.assignment_method)
        )
        detection_payload["analysis_eligibility"] = selected_method["analysis_eligibility"]
        detection_payload["exclusion_reasons"] = selected_method["exclusion_reasons"]
        return {
            "detection": detection_payload,
            "assay": assay_payload,
            "sample": sample_payload,
            "provenance": _provenance(
                connection,
                [
                    ("sample", sample.sample_id, sample),
                    ("assay", assay.assay_id, assay),
                    ("detection", detection_id, detection),
                ],
            ),
        }
