"""Bounded, final-only review staging from a completed private NASA archive.

No provider downloads, DB access, scientific decisions or corpus publication.
Coarse grid-point context is never relabelled as native sample-area evidence.
"""

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import tempfile

from ingestion.artifact_store import ArtifactStore
from ingestion.immutable_bundle import (
    canonical_bytes,
    digest,
    read_bundle,
    seal_bundle,
    validate_id,
)
from ingestion.sst_acquisition import MAX_FILE_BYTES
from ingestion.sst_nasa_context import context_child, validate_nasa_context_plan
from ingestion.sst_nasa_subset import validate_nasa_pilot

ALGORITHM = "nasa-context-review-staging-v1"
MAX_BATCH_DAYS = 31
MAX_BATCH_RAW_BYTES = 16 * 1024**2
MAX_PACKAGE_BYTES = 24 * 1024**2
REPORT_BYTES = 4 * 1024**2
STAGED_STATUS = "staged_unapproved_context_review_inputs"


def _report_body(report):
    return {k: v for k, v in report.items() if k != "report_id"}


def _validated_rows(plan, report):
    validate_nasa_context_plan(plan)
    if (
        report.get("report_id") != digest(_report_body(report))
        or report.get("history_plan_sha256") != plan["plan_sha256"]
        or report.get("algorithm") != plan["algorithm"]
        or report.get("status") != "complete_unapproved_context_acquisition"
        or report.get("acquisition_scope") != "context_only"
        or report.get("scientific_approval") is not False
        or report.get("database_access") is not False
        or report.get("full_hybrid_acquisition_complete") is not False
        or report.get("native_patch_acquisition_pending") is not True
        or report.get("coarse_context_is_native_sample_evidence") is not False
        or report.get("expected") != plan["expected"]
        or report.get("counts")
        != {"context_days": plan["request_count"], "native_location_days": 0}
    ):
        raise ValueError("Completed context reconciliation binding mismatch")
    when = datetime.fromisoformat(report["completed_at"])
    if when.tzinfo is None:
        raise ValueError("Context completion must be timezone qualified")
    rows = report.get("request_results")
    if not isinstance(rows, list) or len(rows) != plan["request_count"]:
        raise ValueError("Context completion request count mismatch")
    descriptors = {r["request_sha256"]: r for r in plan["requests"]}
    seen, total, generations, paired = set(), 0, Counter(), []
    for row in rows:
        identity = validate_id(row["request_sha256"])
        for key in ("artifact_id", "receipt_sha256"):
            validate_id(row[key])
        size = row["raw_bytes"]
        if (
            identity not in descriptors
            or identity in seen
            or row["history_plan_sha256"] != plan["plan_sha256"]
            or row["role"] != "context"
            or type(row["days"]) is not int
            or row["days"] != 1
            or type(size) is not int
            or not 1 <= size <= MAX_FILE_BYTES
            or row.get("processing_generation") not in {"final", "interim"}
        ):
            raise ValueError("Context request identity/generation/byte mismatch")
        seen.add(identity)
        total += size
        generations[row["processing_generation"]] += 1
        paired.append((descriptors[identity]["days"][0], row))
    if (
        seen != set(descriptors)
        or type(report["raw_bytes"]) is not int
        or total != report["raw_bytes"]
        or total > plan["maximum_raw_bytes"]
        or {g: generations[g] for g in ("final", "interim")}
        != report["processing_generation_counts"]
    ):
        raise ValueError("Context terminal counts or cumulative bytes mismatch")
    return sorted(paired)


def build_context_integration_plan(plan, report):
    """Offline reconciliation/batch planning is not retained-byte verification."""
    paired = _validated_rows(plan, report)
    batches, selected, month, used, part = [], [], None, 0, 0
    gaps = [
        {"day": day, "reason": "known_acquisition_exclusion"}
        for day in plan["excluded_days"]
    ]

    def finish():
        batch = {
            "source_plan_sha256": plan["plan_sha256"],
            "source_report_id": report["report_id"],
            "month": month,
            "part": part,
            "days": [day for day, _ in selected],
            "request_sha256s": [row["request_sha256"] for _, row in selected],
            "raw_bytes": used,
        }
        batches.append({**batch, "batch_id": digest(batch)})

    year_counts = {}
    for day, row in paired:
        counts = year_counts.setdefault(day[:4], {"final": 0, "interim": 0})
        counts[row["processing_generation"]] += 1
        if row["processing_generation"] == "interim":
            gaps.append({"day": day, "reason": "interim_generation"})
            continue
        new_month = day[:7]
        if selected and (
            new_month != month
            or len(selected) == MAX_BATCH_DAYS
            or used + row["raw_bytes"] > MAX_BATCH_RAW_BYTES
        ):
            finish()
            selected, used = [], 0
            part = part + 1 if new_month == month else 0
        month = new_month
        selected.append((day, row))
        used += row["raw_bytes"]
    if selected:
        finish()
    result = {
        "schema_version": 1,
        "algorithm": ALGORITHM,
        "kind": "historical_context_integration_preflight",
        "source_plan_sha256": plan["plan_sha256"],
        "source_report_id": report["report_id"],
        "source_inventory_id": plan["source_inventory"]["inventory_id"],
        "evidence_role": "regional_context",
        "spatial_operation": "grid_point_subsampling",
        "spatial_stride": 5,
        "context_footprint": plan["context_footprint"],
        "year_processing_generation_counts": year_counts,
        "selected_final_days": report["processing_generation_counts"]["final"],
        "unsupported_final_dates": sorted(gaps, key=lambda gap: gap["day"]),
        "batches": batches,
        "maximum_batch_days": MAX_BATCH_DAYS,
        "maximum_batch_raw_bytes": MAX_BATCH_RAW_BYTES,
        "scientific_approval": False,
        "scientific_publication": False,
        "scientific_matching_performed": False,
        "native_patch_acquisition_pending": True,
        "required_reviews": [
            "environmental_eligibility_and_physical_sample_identity",
            "sampling_areas_and_comparable_cohort",
            "product_generation_and_context_spatial_semantics",
            "quality_uncertainty_weighting_and_time_rules",
            "current_applied_registry_bindings",
        ],
        "retained_raw_verification": "required_per_selected_batch_at_staging",
    }
    return {**result, "integration_plan_id": digest(result)}


def stage_context_batch(
    plan,
    report,
    integration,
    archive_uri,
    batch_id,
    output_root,
    *,
    store_factory=ArtifactStore,
):
    """Read one verified raw batch into an immutable, local review package."""
    if integration != build_context_integration_plan(plan, report):
        raise ValueError("Context integration preflight binding mismatch")
    validate_id(batch_id)
    matches = [b for b in integration["batches"] if b["batch_id"] == batch_id]
    if len(matches) != 1:
        raise ValueError("Unknown context integration batch")
    if not archive_uri.endswith("/" + plan["plan_sha256"]):
        raise ValueError("Context archive URI binding mismatch")
    batch = matches[0]
    output_root = Path(output_root)
    if not output_root.is_absolute() or any(
        p.is_symlink() for p in (output_root, *output_root.parents)
    ):
        raise ValueError("Context staging requires an absolute non-symlink directory")
    archive_report = _report_body(report)
    _, durable = store_factory(archive_uri + "/acquisition-runs").read(
        "operations", report["report_id"], max_bytes=REPORT_BYTES
    )
    if json.loads(durable["reconciliation.json"]) != archive_report:
        raise ValueError("Durable context reconciliation differs from preflight")
    rows = {r["request_sha256"]: r for r in report["request_results"]}
    descriptors = {r["request_sha256"]: r for r in plan["requests"]}
    output_root.mkdir(parents=True, exist_ok=True)
    entries, used = [], 0
    with tempfile.TemporaryDirectory(
        prefix=".context-review-", dir=output_root
    ) as stage:
        stage = Path(stage)
        for identity in batch["request_sha256s"]:
            row = rows[identity]
            store = store_factory(archive_uri + "/requests/" + identity)
            receipt, contents = store.read(
                "raw", row["artifact_id"], max_bytes=MAX_BATCH_RAW_BYTES
            )
            manifest = json.loads(contents["acquisition.json"])
            child = context_child(descriptors[identity], plan["provider"])
            diagnostics = validate_nasa_pilot(manifest, contents, child)
            checkpoint, _ = store.pointer("operations/checkpoint.json")
            if (
                digest(receipt) != row["receipt_sha256"]
                or receipt["id"]
                != digest({"manifest": manifest, "diagnostics": diagnostics})
                or receipt["metadata"]
                != {
                    "history_plan_sha256": plan["plan_sha256"],
                    "role": "context",
                    "request_sha256": identity,
                    "scientific_approval": False,
                }
                or checkpoint != row
                or diagnostics["processing_generation"] != "final"
                or json.loads(contents["diagnostics.json"]) != diagnostics
            ):
                raise ValueError(
                    "Context retained receipt/checkpoint/generation mismatch"
                )
            entry = manifest["files"][0]
            if entry["bytes"] != row["raw_bytes"]:
                raise ValueError("Context retained raw byte count mismatch")
            used += entry["bytes"]
            if used > MAX_BATCH_RAW_BYTES:
                raise ValueError("Context review batch raw byte cap exceeded")
            (stage / entry["filename"]).write_bytes(contents[entry["filename"]])
            provenance_name = "provenance-" + identity + ".json"
            (stage / provenance_name).write_bytes(
                canonical_bytes(
                    {
                        "request_result": row,
                        "receipt": receipt,
                        "acquisition": manifest,
                        "diagnostics": diagnostics,
                    }
                )
            )
            entries.append(
                {
                    **entry,
                    "processing_generation": "final",
                    "evidence_role": "regional_context",
                    "spatial_operation": "grid_point_subsampling",
                    "provenance_filename": provenance_name,
                }
            )
        if used != batch["raw_bytes"]:
            raise ValueError("Context batch total differs from preflight")
        inventory = {
            "status": STAGED_STATUS,
            "integration_plan_id": integration["integration_plan_id"],
            "batch": batch,
            "source_archive_uri": archive_uri,
            "files": entries,
            "unsupported_final_dates": integration["unsupported_final_dates"],
            "scientific_approval": False,
            "scientific_publication": False,
            "scientific_matching_performed": False,
            "coarse_context_is_native_sample_evidence": False,
            "required_reviews": integration["required_reviews"],
        }
        (stage / "review-inventory.json").write_bytes(canonical_bytes(inventory))
        if sum(p.stat().st_size for p in stage.iterdir()) > MAX_PACKAGE_BYTES:
            raise ValueError("Context review package byte cap exceeded")
        manifest = seal_bundle(
            stage,
            output_root,
            batch_id,
            {"schema_version": 1, "algorithm": ALGORITHM, "status": STAGED_STATUS},
        )
    observed, _ = read_bundle(
        output_root,
        batch_id,
        expected_digest=digest(manifest),
        max_bytes=MAX_PACKAGE_BYTES,
    )
    return {
        "status": STAGED_STATUS,
        "batch_id": batch_id,
        "integration_plan_id": integration["integration_plan_id"],
        "package_path": str(output_root / batch_id),
        "manifest_sha256": digest(observed),
        "final_days": len(entries),
        "raw_bytes": used,
        "scientific_approval": False,
        "scientific_publication": False,
        "database_access": False,
        "cloud_writes": False,
    }
