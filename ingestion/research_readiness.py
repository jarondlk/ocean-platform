"""Read-only, hash-verified readiness census. Occurrences are not physical samples."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from ingestion.anemone_catalogue import file_sha256, safe_archive_path
from ingestion.immutable_bundle import digest, validate_id
from preprocessing.anemone import resolve_normalized_bundle
from preprocessing.edna_eligibility import PROTOCOL_FIELDS
from preprocessing.edna_recipe import METHODS

MAX_UNITS = 128
MAX_OCCURRENCES = 10_000
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024


def _json(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Unsafe or oversized candidate manifest")
    return json.loads(path.read_bytes())


def read_candidate_metadata(root: Path) -> tuple[dict, dict]:
    """Verify all artifacts, retaining only bounded sample/assay metadata in memory."""
    if root.is_symlink():
        raise ValueError("Candidate root must not be a symlink")
    root = root.resolve()
    pointer = _json(root / "candidate.json")
    identity = validate_id(pointer["candidate_id"])
    path = safe_archive_path(root, f"candidates/{identity}/candidate.json")
    if file_sha256(path) != pointer["manifest_sha256"]:
        raise ValueError("Candidate manifest checksum mismatch")
    candidate = _json(path)
    if (
        candidate.get("candidate_id") != identity
        or candidate.get("status") != "complete"
    ):
        raise ValueError("Candidate is not a complete reconciled publication")
    units = candidate["units"]
    if not 1 <= len(units) <= MAX_UNITS:
        raise ValueError("Candidate unit limit exceeded")
    source = {"edna_sample": [], "edna_assay": []}
    seen_units, seen_rows, row_counts, total_bytes = (
        set(),
        defaultdict(set),
        Counter(),
        0,
    )
    for unit in units:
        normalization = validate_id(unit["normalization_id"])
        if normalization in seen_units:
            raise ValueError("Duplicate normalized unit")
        seen_units.add(normalization)
        manifest_path = safe_archive_path(
            root, f"normalized/snapshots/{normalization}/normalization_manifest.json"
        )
        preliminary = _json(manifest_path)
        if file_sha256(manifest_path) != unit["manifest_sha256"]:
            raise ValueError("Candidate unit manifest checksum mismatch")
        # Apply byte/row budgets before the legacy resolver reads any Parquet.
        for name, entry in preliminary["artifacts"].items():
            artifact = safe_archive_path(manifest_path.parent, entry["path"])
            total_bytes += artifact.stat().st_size
            if total_bytes > MAX_ARTIFACT_BYTES:
                raise ValueError("Candidate artifact byte limit exceeded")
            count = entry.get("row_count")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("Invalid normalized artifact row count")
            if name in source and row_counts[name] + count > MAX_OCCURRENCES:
                raise ValueError("Canonical metadata row limit exceeded")
        directory, manifest = resolve_normalized_bundle(
            normalization, normalized_root=root / "normalized"
        )
        if (
            file_sha256(directory / "normalization_manifest.json")
            != unit["manifest_sha256"]
        ):
            raise ValueError("Candidate unit manifest checksum mismatch")
        if manifest["source_snapshot_id"] != unit["source_snapshot_id"]:
            raise ValueError("Candidate source generation mismatch")
        for name, entry in manifest["artifacts"].items():
            artifact = safe_archive_path(directory, entry["path"])
            if file_sha256(artifact) != entry["sha256"]:
                raise ValueError("Normalized artifact checksum mismatch")
            row_counts[name] += entry["row_count"]
            if name not in source:
                continue
            frame = pd.read_parquet(artifact)
            if len(frame) != entry["row_count"]:
                raise ValueError("Normalized metadata row count mismatch")
            # Pandas handles timestamps/nulls without introducing NaN into the report.
            records = json.loads(frame.to_json(orient="records", date_format="iso"))
            key = "sample_id" if name == "edna_sample" else "assay_id"
            for row in records:
                if row[key] in seen_rows[name]:
                    raise ValueError("Duplicate canonical metadata identity")
                seen_rows[name].add(row[key])
            source[name].extend(records)
            if len(source[name]) > MAX_OCCURRENCES:
                raise ValueError("Canonical metadata row limit exceeded")
    if dict(row_counts) != candidate["row_counts"]:
        raise ValueError("Candidate row counts do not reconcile")
    return source, {
        "candidate_id": identity,
        "candidate_manifest_sha256": pointer["manifest_sha256"],
        "archive_manifest_sha256": candidate["archive_manifest_sha256"],
        "normalized_units": sorted(seen_units),
        "row_counts": dict(row_counts),
        "verified_artifact_bytes": total_bytes,
        "production_imported": candidate.get("production_imported", False),
    }


def method_status(assay: dict, method: str) -> str:
    raw = assay.get("community_availability_json") or {}
    availability = json.loads(raw) if isinstance(raw, str) else raw
    entry = availability.get(method)
    if not isinstance(entry, dict):
        return "unavailable"
    status = entry.get("status")
    count = entry.get("row_count")
    if status == "available" and (
        isinstance(count, bool) or not isinstance(count, int) or count < 0
    ):
        return "invalid_availability"
    if status == "available" and isinstance(count, int):
        return (
            "available_nonempty"
            if entry["row_count"] > 0
            else "valid_empty_requires_qc_review"
        )
    return str(status or "unavailable")


def build_readiness(source: dict, provenance: dict) -> dict:
    """An evidence census, never an approval inferred from names or coordinates."""
    samples = [s for s in source["edna_sample"] if s.get("active", True) is True]
    assays = [a for a in source["edna_assay"] if a.get("active", True) is True]
    if len(samples) > MAX_OCCURRENCES or len(assays) > MAX_OCCURRENCES:
        raise ValueError("Readiness row limit exceeded")
    by_sample = defaultdict(list)
    for assay in assays:
        by_sample[assay["sample_id"]].append(assay)
    counts = Counter()
    kinds, identities, precisions, methods = Counter(), Counter(), Counter(), Counter()
    coverage = defaultdict(lambda: Counter())
    reported_names = Counter()
    dates = []
    for sample in samples:
        kinds[sample.get("sample_kind") or "unknown"] += 1
        identities[sample.get("identity_status") or "unresolved"] += 1
        precisions[sample.get("temporal_precision") or "unknown"] += 1
        reported_names[sample.get("original_sample_label")] += 1
        environmental = (
            sample.get("sample_kind") == "environmental"
            and sample.get("is_control") is False
        )
        counts["environmental_occurrences"] += environmental
        counts["occurrences_with_physical_id"] += bool(sample.get("physical_sample_id"))
        available = by_sample.get(sample["sample_id"], [])
        counts["occurrences_without_active_assay"] += not available
        counts["occurrences_with_complete_protocol"] += any(
            all(a.get(k) is not None and str(a[k]).strip() for k in PROTOCOL_FIELDS)
            for a in available
        )
        metadata = sample.get("raw_metadata_json") or {}
        metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
        cell = str(metadata.get("worldmesh") or "unreported")
        value = sample.get("collection_date_utc")
        month = "undated"
        if value:
            try:
                when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    raise ValueError("Source timestamp has no timezone")
                local = when.astimezone(ZoneInfo("Asia/Tokyo"))
                month = local.strftime("%Y-%m")
                dates.append(when.isoformat())
            except (TypeError, ValueError):
                counts["invalid_dates"] += 1
        group = coverage[(month, cell)]
        group["source_occurrences"] += 1
        group["environmental_occurrences"] += environmental
        group["physical_id_present"] += bool(sample.get("physical_sample_id"))
    for assay in assays:
        for method in METHODS:
            methods[f"{method}:{method_status(assay, method)}"] += 1
    blockers = [
        "reviewed_physical_membership_and_representative_assays_required",
        "reviewed_region_and_area_membership_required",
        "eligible_cohort_must_be_measured_after_reviews",
    ]
    if not counts["environmental_occurrences"]:
        blockers.append("no_classified_environmental_occurrences")
    cases = []
    for number in range(1, 7):
        reasons = list(blockers)
        if number in {2, 4, 6}:
            reasons.append("verified_historical_sst_panel_required")
        if number in {5, 6}:
            reasons.append("supported_endpoint_area_season_protocol_panel_required")
        cases.append(
            {"question": f"Q{number}", "status": "data_blocked", "reasons": reasons}
        )
    report = {
        "schema_version": 1,
        "analysis_kind": "research_readiness",
        "source": provenance,
        "calendar": "Asia/Tokyo",
        "analysis_unit": "source_occurrence_diagnostic_only",
        "counts": {
            "source_occurrences": len(samples),
            "active_assays": len(assays),
            **dict(counts),
        },
        "sample_kinds": dict(sorted(kinds.items())),
        "identity_statuses": dict(sorted(identities.items())),
        "date_precisions": dict(sorted(precisions.items())),
        "source_time_extent": {
            "from": min(dates) if dates else None,
            "to": max(dates) if dates else None,
        },
        "method_statuses": dict(sorted(methods.items())),
        "repeated_reported_labels": sum(
            n > 1 for name, n in reported_names.items() if name
        ),
        "coverage": [
            {"month": month, "reported_worldmesh": cell, **dict(values)}
            for (month, cell), values in sorted(coverage.items())
        ],
        "case_dispositions": cases,
        "limitations": [
            "Reported cells are unreviewed provider metadata, not approved area membership.",
            "Physical ID presence alone does not establish reviewed identity or eligible sample counts.",
            "This report does not approve classification, identity, geography or historical SST.",
        ],
    }
    report["report_id"] = digest(report)
    return report
