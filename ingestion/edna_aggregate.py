"""Exact SQL aggregates with immutable, bounded evidence retained in app history."""

import hashlib
import json

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import config
from api.edna_service import (
    edna_summary,
    _sample_conditions,
    _detection_conditions,
    _aggregate_assay_conditions,
)
from db.connection import get_engine
from ingestion.immutable_bundle import canonical_bytes, digest, validate_id
from ingestion.provenance_snapshot import SnapshotError

ALGORITHM = "edna-catalogue-aggregate-v1"
MAX_ROWS = 1_000_000
MAX_PAYLOAD_BYTES = 1024 * 1024


class AggregateUnavailable(ValueError):
    pass


def publication_pointer():
    if config.EDNA_ARTIFACT_URI:
        from ingestion.artifact_store import ArtifactStore

        pointer, _ = ArtifactStore(config.EDNA_ARTIFACT_URI).pointer(
            "retrieval/current.json"
        )
        return pointer
    path = config.SERVING_DIR / "edna_current.json"
    return json.loads(path.read_bytes()) if path.exists() else None


def _assert_publication(pointer, publication):
    edna = publication.get("edna")
    canonical = publication.get("anemone-canonical")
    if not pointer or pointer.get("status") != "ready" or not edna or not canonical:
        raise AggregateUnavailable(
            "Exact aggregation requires a complete canonical and retrieval publication"
        )
    if publication.get("edna-canonical") != canonical:
        raise AggregateUnavailable(
            "Retrieval publication does not match the current canonical generation"
        )
    for record in (edna, canonical):
        validate_id(record["generation_id"])
        validate_id(record["manifest_sha256"])
    if (
        pointer.get("generation_id") != edna["generation_id"]
        or pointer.get("manifest_sha256") != edna["manifest_sha256"]
    ):
        raise AggregateUnavailable(
            "Canonical and retrieval publication are not ready together"
        )


def _inputs(connection, filters):
    sample, sample_params = _sample_conditions(filters)
    assay, assay_params = _aggregate_assay_conditions(filters)
    detection, detection_params = _detection_conditions(filters)
    tables = (
        ("edna_sample", "sample_id", "s", "edna_sample s", sample, sample_params),
        (
            "edna_assay",
            "assay_id",
            "a",
            "edna_assay a JOIN edna_sample s ON s.sample_id=a.sample_id",
            assay,
            assay_params,
        ),
        (
            "edna_detection",
            "detection_id",
            "d",
            "edna_detection d JOIN edna_assay a ON a.assay_id=d.assay_id JOIN edna_sample s ON s.sample_id=a.sample_id",
            detection,
            detection_params,
        ),
        (
            "edna_internal_standard",
            "internal_standard_id",
            "i",
            "edna_internal_standard i JOIN edna_assay a ON a.assay_id=i.assay_id JOIN edna_sample s ON s.sample_id=a.sample_id",
            [*assay, "i.active IS TRUE"],
            assay_params,
        ),
    )
    fingerprints, snapshots, used = {}, set(), 0
    for table, key, alias, joins, conditions, params in tables:
        statement = (
            f"SELECT {alias}.{key} AS id,{alias}.source_row_hash,{alias}.source_snapshot_id,{alias}.source_file_id "
            f"FROM {joins} WHERE "
            + " AND ".join(conditions)
            + f" ORDER BY {alias}.{key} LIMIT :aggregate_limit"
        )
        rows = connection.execution_options(stream_results=True).execute(
            text(statement), {**params, "aggregate_limit": MAX_ROWS - used + 1}
        )
        hasher, count = hashlib.sha256(), 0
        for row in rows:
            used += 1
            if used > MAX_ROWS:
                rows.close()
                raise AggregateUnavailable(
                    "Aggregate cohort exceeds row budget; narrow the filters"
                )
            for value in row:
                validate_id(value)
            hasher.update(canonical_bytes(list(row)) + b"\n")
            snapshots.add(row.source_snapshot_id)
            count += 1
        rows.close()
        fingerprints[table] = {
            "rows": count,
            "ordered_identity_and_source_hash_sha256": hasher.hexdigest(),
        }
    connection.execution_options(stream_results=False)
    if len(snapshots) > 2048:
        raise AggregateUnavailable("Aggregate source snapshot budget exceeded")
    sources = (
        connection.execute(
            text(
                "SELECT snapshot_id,source_collection_sha256,manifest_sha256,contract_sha256,scope_url,generated_at FROM external_source_snapshot WHERE snapshot_id = ANY(:ids) ORDER BY snapshot_id"
            ),
            {"ids": sorted(snapshots)},
        )
        .mappings()
        .all()
    )
    if len(sources) != len(snapshots):
        raise AggregateUnavailable("Aggregate source snapshots are incomplete")
    for row in sources:
        for key in (
            "snapshot_id",
            "source_collection_sha256",
            "manifest_sha256",
            "contract_sha256",
        ):
            validate_id(row[key])
    reviews = (
        connection.execute(
            text(
                "SELECT s.sample_id,s.classification_review_json FROM edna_sample s WHERE "
                + " AND ".join([*sample, "s.classification_review_json IS NOT NULL"])
                + " ORDER BY s.sample_id LIMIT 2049"
            ),
            sample_params,
        )
        .mappings()
        .all()
    )
    if len(reviews) > 2048:
        raise AggregateUnavailable("Aggregate classification review budget exceeded")
    return {
        "classification_reviews": [dict(row) for row in reviews],
        "tables": fingerprints,
        "source_snapshots": [{k: str(v) for k, v in row.items()} for row in sources],
        "hash_definition": "SHA256 of ordered canonical JSON lines [id, source_row_hash, source_snapshot_id, source_file_id] per table",
        "reproduction": "Apply the recorded filter/query contract to retained normalized bundles and recorded classification reviews for these source versions. No live database state is substituted for a historical result.",
    }


def build_aggregate(filters, group_by=(), *, engine=None):
    engine = engine if engine is not None else get_engine()
    try:
        allowed = {
            "provider",
            "provider_locus",
            "provider_team",
            "provider_project_id",
            "provider_run_id",
            "sample_id",
            "assay_id",
            "assignment_method",
            "target_status",
            "taxon",
            "sample_kind",
            "is_control",
            "time_from",
            "time_to",
            "lat_min",
            "lat_max",
            "lon_min",
            "lon_max",
        }
        if set(filters) - allowed:
            raise AggregateUnavailable("Unsupported aggregate filter")
        pointer = publication_pointer()
        with engine.connect() as connection:
            connection.exec_driver_sql(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            connection.exec_driver_sql("SET LOCAL statement_timeout = '20s'")
            summary = edna_summary(filters, connection=connection, group_by=group_by)
            _assert_publication(pointer, summary["publication"])
            inputs = _inputs(connection, filters)
            if (
                inputs["tables"]["edna_sample"]["rows"] != summary["source_occurrences"]
                or inputs["tables"]["edna_assay"]["rows"] != summary["assays"]
                or inputs["tables"]["edna_detection"]["rows"]
                != sum(r["assignment_rows"] for r in summary["methods"])
                or inputs["tables"]["edna_internal_standard"]["rows"]
                != summary["internal_standards"]["rows"]
            ):
                raise AggregateUnavailable("Aggregate row accounting mismatch")
        if pointer != publication_pointer():
            raise AggregateUnavailable("Publication changed during aggregation; retry")
        payload = {
            "algorithm_version": ALGORITHM,
            "filters": filters,
            "group_by": list(group_by),
            "publication": summary["publication"],
            "summary": summary,
            "inputs": inputs,
            "query_contract": {
                "scope": "active canonical rows, exact explicit filters, UTC interval overlap for date-only source records",
                "taxon": "case-insensitive exact match in any indexed taxonomic rank",
                "assays": "only matching assays; valid empty tables count as available when no taxon is requested",
                "standards": "separate technical rows in matching assays; never added to biological assignment totals",
                "groups": "source-occurrence counts, never physical-sample counts",
            },
        }
        data = canonical_bytes(payload)
        if len(data) > MAX_PAYLOAD_BYTES:
            raise AggregateUnavailable("Aggregate evidence exceeds byte budget")
        identity = digest(payload)
        # App-history table survives corpus rebuilds. No model may cite an
        # aggregate until the immutable evidence has been committed.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO edna_aggregate_evidence(aggregate_id,algorithm_version,payload_json) VALUES (:id,:algorithm,:payload) ON CONFLICT (aggregate_id) DO NOTHING"
                ),
                {"id": identity, "algorithm": ALGORITHM, "payload": data.decode()},
            )
            stored = connection.execute(
                text(
                    "SELECT payload_json FROM edna_aggregate_evidence WHERE aggregate_id=:id"
                ),
                {"id": identity},
            ).scalar_one()
            if canonical_bytes(json.loads(stored)) != data:
                raise AggregateUnavailable("Immutable aggregate evidence conflict")
        return {"aggregate_id": identity, "payload": payload}
    except AggregateUnavailable:
        raise
    except (SQLAlchemyError, ValueError, KeyError, OSError, SnapshotError) as exc:
        raise AggregateUnavailable(
            "Exact aggregate evidence could not be verified or retained"
        ) from exc


def load_aggregate(identity, *, engine=None):
    validate_id(identity)
    engine = engine if engine is not None else get_engine()
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT payload_json FROM edna_aggregate_evidence WHERE aggregate_id=:id"
            ),
            {"id": identity},
        ).scalar_one_or_none()
    if row is None:
        return None
    if len(row.encode()) > MAX_PAYLOAD_BYTES:
        raise AggregateUnavailable("Aggregate evidence exceeds byte budget")
    payload = json.loads(row)
    if digest(payload) != identity or payload.get("algorithm_version") != ALGORITHM:
        raise AggregateUnavailable("Aggregate evidence integrity check failed")
    return {"aggregate_id": identity, "payload": payload}


def aggregate_trace(identity):
    bundle = load_aggregate(identity)
    doc_id = "aggregate_edna_" + identity
    if bundle is None:
        return {"doc_id": doc_id, "found": False, "trace": {}}
    payload = bundle["payload"]
    return {
        "doc_id": doc_id,
        "found": True,
        "trace": {
            "document": {
                "doc_id": doc_id,
                "source_type": "analysis",
                "title": "Exact ANEMONE catalogue summary",
                "text": json.dumps(payload["summary"], sort_keys=True),
                "metadata": payload,
                "lineage_level": "immutable_aggregate",
            },
            "embedding": {"embedding_status": "not_applicable"},
            "artifacts": [
                {
                    "id": doc_id,
                    "sha256": identity,
                    "path": f"/data/edna/aggregates/{identity}",
                }
            ],
            "source_files": [
                {
                    "id": s["snapshot_id"],
                    "sha256": s["manifest_sha256"],
                    "path": s["scope_url"],
                }
                for s in payload["inputs"]["source_snapshots"]
            ],
            "trace_path": [
                {"level": "citation", "key": doc_id},
                {"level": "query_contract", "key": payload["algorithm_version"]},
                {
                    "level": "canonical_generation",
                    "key": payload["publication"]["anemone-canonical"]["generation_id"],
                },
                {"level": "input_fingerprint", "key": digest(payload["inputs"])},
            ],
        },
    }
