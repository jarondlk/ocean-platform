"""Verified, local diagnostics for coarse SST context; never scientific publication."""

import calendar
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import xarray as xr

from ingestion.immutable_bundle import canonical_bytes, digest, read_bundle
from ingestion.sst_context_integration import (
    ALGORITHM as STAGING_ALGORITHM,
    MAX_PACKAGE_BYTES,
    STAGED_STATUS,
    build_context_integration_plan,
)
from ingestion.sst_nasa_context import context_child
from ingestion.sst_nasa_subset import validate_nasa_pilot

ALGORITHM = "historical-regional-context-diagnostics-v1"
STATUS = "unapproved_context_diagnostics"


def load_context_review(plan, report, staging):
    """Recheck a sealed package against its source plan and terminal reconciliation.

    Only retained local bytes are read. This does not refresh remote object
    generations or establish researcher approval/current publication bindings.
    """
    integration = build_context_integration_plan(plan, report)
    batches = [
        b for b in integration["batches"] if b["batch_id"] == staging["batch_id"]
    ]
    if len(batches) != 1:
        raise ValueError("Unknown context review batch")
    batch = batches[0]
    package = Path(staging["package_path"])
    if (
        not package.is_absolute()
        or package.name != batch["batch_id"]
        or any(p.is_symlink() for p in (package, *package.parents))
        or staging
        != {
            "status": STAGED_STATUS,
            "batch_id": batch["batch_id"],
            "integration_plan_id": integration["integration_plan_id"],
            "package_path": str(package),
            "manifest_sha256": staging["manifest_sha256"],
            "final_days": len(batch["days"]),
            "raw_bytes": batch["raw_bytes"],
            "scientific_approval": False,
            "scientific_publication": False,
            "database_access": False,
            "cloud_writes": False,
        }
    ):
        raise ValueError("Context review staging receipt/path mismatch")
    manifest, contents = read_bundle(
        package.parent,
        batch["batch_id"],
        expected_digest=staging["manifest_sha256"],
        max_bytes=MAX_PACKAGE_BYTES,
    )
    if {k: v for k, v in manifest.items() if k not in {"id", "files"}} != {
        "schema_version": 1,
        "algorithm": STAGING_ALGORITHM,
        "status": STAGED_STATUS,
    }:
        raise ValueError("Context review manifest contract mismatch")
    inventory = json.loads(contents["review-inventory.json"])
    if (
        {k: v for k, v in inventory.items() if k != "files"}
        != {
            "status": STAGED_STATUS,
            "integration_plan_id": integration["integration_plan_id"],
            "batch": batch,
            "source_archive_uri": inventory["source_archive_uri"],
            "unsupported_final_dates": integration["unsupported_final_dates"],
            "scientific_approval": False,
            "scientific_publication": False,
            "scientific_matching_performed": False,
            "coarse_context_is_native_sample_evidence": False,
            "required_reviews": integration["required_reviews"],
        }
        or not inventory["source_archive_uri"].endswith("/" + plan["plan_sha256"])
        or len(inventory["files"]) != len(batch["days"])
    ):
        raise ValueError("Context review inventory binding mismatch")
    descriptors = {r["request_sha256"]: r for r in plan["requests"]}
    rows = {r["request_sha256"]: r for r in report["request_results"]}
    required = {"review-inventory.json"}
    verified = []
    for entry, identity in zip(inventory["files"], batch["request_sha256s"]):
        name = "provenance-" + identity + ".json"
        provenance = json.loads(contents[name])
        acquisition = provenance["acquisition"]
        if set(provenance) != {
            "acquisition",
            "diagnostics",
            "receipt",
            "request_result",
        }:
            raise ValueError("Context review provenance contract mismatch")
        child = context_child(descriptors[identity], plan["provider"])
        diagnostics = validate_nasa_pilot(acquisition, contents, child)
        original = acquisition["files"][0]
        receipt = provenance["receipt"]
        if (
            entry
            != {
                **original,
                "processing_generation": "final",
                "evidence_role": "regional_context",
                "spatial_operation": "grid_point_subsampling",
                "provenance_filename": name,
            }
            or entry["spatial_stride"] != 5
            or provenance["request_result"] != rows[identity]
            or provenance["diagnostics"] != diagnostics
            or digest(receipt) != rows[identity]["receipt_sha256"]
            or receipt["id"] != rows[identity]["artifact_id"]
            or receipt["id"]
            != digest({"manifest": acquisition, "diagnostics": diagnostics})
            or receipt["schema_version"] != 1
            or receipt["namespace"] != "raw"
            or receipt["metadata"]
            != {
                "history_plan_sha256": plan["plan_sha256"],
                "role": "context",
                "request_sha256": identity,
                "scientific_approval": False,
            }
            or original["bytes"] != rows[identity]["raw_bytes"]
        ):
            raise ValueError("Context review retained provenance mismatch")
        for filename, data in {
            original["filename"]: contents[original["filename"]],
            "acquisition.json": canonical_bytes(acquisition),
            "diagnostics.json": canonical_bytes(diagnostics),
        }.items():
            binding = receipt["files"][filename]
            if (
                binding["sha256"] != hashlib.sha256(data).hexdigest()
                or binding["size"] != len(data)
                or type(binding["generation"]) is not int
                or binding["generation"] <= 0
            ):
                raise ValueError("Context review raw/metadata receipt mismatch")
        required.update((name, original["filename"]))
        verified.append((entry, contents[original["filename"]], rows[identity]))
    if set(manifest["files"]) != required:
        raise ValueError("Context review package file contract mismatch")
    return integration, inventory, verified


def _stats(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not values.size:
        return {k: None for k in ("min", "p05", "median", "p95", "max", "mean")}
    q = np.quantile(values, [0, 0.05, 0.5, 0.95, 1])
    return dict(
        zip(
            ("min", "p05", "median", "p95", "max", "mean"),
            [*map(float, q), float(values.mean())],
        )
    )


def _bounds(bounds, footprint):
    bounds = footprint if bounds is None else bounds
    if (
        set(bounds) != {"south", "north", "west", "east"}
        or any(
            type(v) not in (int, float) or not np.isfinite(v) for v in bounds.values()
        )
        or not footprint["south"]
        <= bounds["south"]
        < bounds["north"]
        <= footprint["north"]
        or not footprint["west"] <= bounds["west"] < bounds["east"] <= footprint["east"]
    ):
        raise ValueError(
            "Diagnostic rectangle must be finite and inside acquired context"
        )
    return dict(bounds)


def build_context_diagnostics(plan, report, staging, *, bounds=None):
    """Describe final grid points with no uncertainty/ice/coverage acceptance rule.

    Equal weights describe retained grid points, not an area-weighted mean or a
    sample-time SST estimate. Even a user-specified rectangle is unreviewed.
    """
    integration, inventory, verified = load_context_review(plan, report, staging)
    rectangle = _bounds(bounds, integration["context_footprint"])
    daily = []
    for entry, raw, request_result in verified:
        with tempfile.TemporaryDirectory(prefix="sst-context-diagnostics-") as tmp:
            path = Path(tmp) / "subset.nc"
            path.write_bytes(raw)
            path.chmod(0o600)
            with xr.open_dataset(path) as ds:
                lat, lon = ds.lat.values, ds.lon.values
                y = np.flatnonzero(
                    (lat >= rectangle["south"] - 2e-5)
                    & (lat <= rectangle["north"] + 2e-5)
                )
                x = np.flatnonzero(
                    (lon >= rectangle["west"] - 2e-5)
                    & (lon <= rectangle["east"] + 2e-5)
                )
                region = ds.isel(time=0, lat=y, lon=x)
                mask = np.asarray(region["mask"].values)
                temperature = (
                    np.asarray(region.analysed_sst.values, dtype=float) - 273.15
                )
                uncertainty = np.asarray(region.analysis_error.values, dtype=float)
                ice = np.asarray(region.sea_ice_fraction.values, dtype=float)
                ocean = mask == 1
                finite = ocean & np.isfinite(temperature)
                mask_values, counts = np.unique(
                    mask[np.isfinite(mask)], return_counts=True
                )
                daily.append(
                    {
                        "day": entry["day"],
                        "time_utc": entry["expected_time_utc"],
                        "granule_id": entry["granule_id"],
                        "raw_sha256": entry["raw_sha256"],
                        "source_url": entry["source_url"],
                        "request_sha256": request_result["request_sha256"],
                        "receipt_sha256": request_result["receipt_sha256"],
                        "processing_generation": "final",
                        "product_version": "04.1",
                        "grid_points": int(mask.size),
                        "ocean_grid_points": int(ocean.sum()),
                        "finite_ocean_temperature_points": int(finite.sum()),
                        "missing_ocean_temperature_points": int(
                            (ocean & ~finite).sum()
                        ),
                        "finite_temperature_fraction_of_ocean": float(
                            finite.sum() / ocean.sum()
                        )
                        if ocean.any()
                        else None,
                        "mask_counts": {
                            format(float(v), ".17g"): int(n)
                            for v, n in zip(mask_values, counts)
                        },
                        "missing_mask_points": int((~np.isfinite(mask)).sum()),
                        "temperature_c": _stats(temperature[finite]),
                        "analysis_error_k": _stats(uncertainty[ocean]),
                        "missing_ocean_analysis_error_points": int(
                            (ocean & ~np.isfinite(uncertainty)).sum()
                        ),
                        "negative_ocean_analysis_error_points": int(
                            (ocean & np.isfinite(uncertainty) & (uncertainty < 0)).sum()
                        ),
                        "sea_ice_fraction": _stats(ice[ocean]),
                        "missing_ocean_ice_points": int(
                            (ocean & ~np.isfinite(ice)).sum()
                        ),
                        "out_of_range_ocean_ice_points": int(
                            (ocean & np.isfinite(ice) & ((ice < 0) | (ice > 1))).sum()
                        ),
                    }
                )
    year, month = map(int, inventory["batch"]["month"].split("-"))
    present = {r["day"] for r in daily}
    gaps = {r["day"]: r["reason"] for r in integration["unsupported_final_dates"]}
    result = {
        "schema_version": 1,
        "algorithm": ALGORITHM,
        "status": STATUS,
        "source_plan_sha256": plan["plan_sha256"],
        "source_report_id": report["report_id"],
        "integration_plan_id": integration["integration_plan_id"],
        "batch_id": staging["batch_id"],
        "source_manifest_sha256": staging["manifest_sha256"],
        "source_archive_uri": inventory["source_archive_uri"],
        "evidence_role": "regional_context",
        "spatial_operation": "grid_point_subsampling",
        "grid_step_degrees": 0.05,
        "diagnostic_rectangle": rectangle,
        "rectangle_is_reviewed_sampling_area": False,
        "temperature_summary_basis": "equal_weight_finite_grid_points_with_mask_1",
        "uncertainty_and_ice_summary_basis": "finite_grid_points_with_mask_1",
        "quality_acceptance_rules_applied": False,
        "area_weighting_applied": False,
        "daily": daily,
        "month_dates_without_final_evidence_in_this_batch": [
            {"day": day, "reason": gaps.get(day, "final_date_in_another_batch")}
            for n in range(1, calendar.monthrange(year, month)[1] + 1)
            if (day := f"{year:04d}-{month:02d}-{n:02d}") not in present
        ],
        "archive_unsupported_final_dates": integration["unsupported_final_dates"],
        "required_reviews": integration["required_reviews"],
        "scientific_approval": False,
        "scientific_publication": False,
        "scientific_matching_performed": False,
        "coarse_context_is_native_sample_evidence": False,
        "database_access": False,
        "cloud_writes": False,
    }
    return {**result, "diagnostics_id": digest(result)}
