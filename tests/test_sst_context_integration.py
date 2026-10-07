from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest
import xarray as xr

from ingestion.artifact_store import ArtifactStore
from ingestion.immutable_bundle import canonical_bytes, digest, read_bundle
from ingestion.sst_context_integration import (
    MAX_BATCH_RAW_BYTES,
    STAGED_STATUS,
    build_context_integration_plan,
    stage_context_batch,
)
from ingestion.sst_inventory import build_inventory
from ingestion.sst_nasa_context import build_nasa_context_plan, context_child
from ingestion.sst_nasa_subset import validate_nasa_pilot


def raw(child, *, interim=False):
    request = child["requests"][0]
    f = request["footprint"]
    lat = np.arange(round(f["south"] * 100), round(f["north"] * 100) + 1, 5) / 100
    lon = np.arange(round(f["west"] * 100), round(f["east"] * 100) + 1, 5) / 100
    ds = xr.Dataset(
        {
            v: (("time", "lat", "lon"), np.ones((1, len(lat), len(lon))))
            for v in ("analysed_sst", "analysis_error", "mask", "sea_ice_fraction")
        },
        coords={
            "time": [np.datetime64(request["expected_time_utc"].removesuffix("Z"))],
            "lat": lat,
            "lon": lon,
        },
        attrs={
            "title": "Daily MUR SST, Interim near-real-time (nrt) product"
            if interim
            else "Daily MUR SST, Final product",
            "product_version": "04.1nrt" if interim else "04.1",
        },
    )
    ds.analysed_sst.attrs["units"] = "kelvin"
    ds.analysis_error.attrs["units"] = "kelvin"
    data = ds.to_netcdf()
    sha = hashlib.sha256(data).hexdigest()
    entry = {
        **request,
        "raw_sha256": sha,
        "bytes": len(data),
        "filename": request["day"] + "-" + sha + ".nc",
        "granule_id": digest({"source_url": request["source_url"], "raw_sha256": sha}),
    }
    manifest = {
        "status": "complete_unapproved_acquisition",
        "plan": child,
        "files": [entry],
    }
    contents = {entry["filename"]: data}
    diagnostics = validate_nasa_pilot(manifest, contents, child, archive_interim=True)
    contents.update(
        {
            "acquisition.json": canonical_bytes(manifest),
            "diagnostics.json": canonical_bytes(diagnostics),
            "journal.json": canonical_bytes({"fixture": True}),
        }
    )
    return manifest, diagnostics, contents


def fixture(tmp_path, *, masquerade_interim=False):
    inventory = build_inventory(
        [
            {
                "sample_id": digest("sample"),
                "collection_date_utc": "2020-07-15",
                "temporal_precision": "date",
                "lat": 38.625,
                "lon": 141.4375,
                "sample_kind": "unknown",
                "raw_metadata_json": {},
            }
        ],
        {"basis": "fixture"},
    )
    plan = build_nasa_context_plan(inventory)
    destination = (tmp_path / "archive" / plan["plan_sha256"]).as_uri()
    rows = []
    for descriptor in plan["requests"]:
        selected = descriptor["days"][0] in {"2020-01-02", "2020-01-03"}
        row = {
            "history_plan_sha256": plan["plan_sha256"],
            "request_sha256": descriptor["request_sha256"],
            "role": "context",
            "days": 1,
            "raw_bytes": 1000,
            "processing_generation": "final" if selected else "interim",
            "artifact_id": digest(descriptor),
            "receipt_sha256": digest("not-staged"),
        }
        if selected:
            child = context_child(descriptor, plan["provider"])
            manifest, diagnostics, contents = raw(child, interim=masquerade_interim)
            identity = digest({"manifest": manifest, "diagnostics": diagnostics})
            store = ArtifactStore(
                destination + "/requests/" + descriptor["request_sha256"]
            )
            receipt = store.publish(
                "raw",
                identity,
                contents,
                metadata={
                    "history_plan_sha256": plan["plan_sha256"],
                    "role": "context",
                    "request_sha256": descriptor["request_sha256"],
                    "scientific_approval": False,
                },
            )
            row.update(
                artifact_id=identity,
                receipt_sha256=digest(receipt),
                raw_bytes=manifest["files"][0]["bytes"],
            )
            store.replace_pointer("operations/checkpoint.json", row, 0)
        rows.append(row)
    report = {
        "algorithm": plan["algorithm"],
        "history_plan_sha256": plan["plan_sha256"],
        "status": "complete_unapproved_context_acquisition",
        "scientific_approval": False,
        "database_access": False,
        "coarse_context_is_native_sample_evidence": False,
        "completed_at": "2026-10-07T10:49:47+00:00",
        "raw_bytes": sum(r["raw_bytes"] for r in rows),
        "counts": {"context_days": plan["request_count"], "native_location_days": 0},
        "expected": plan["expected"],
        "request_results": rows,
        "acquisition_scope": "context_only",
        "full_hybrid_acquisition_complete": False,
        "native_patch_acquisition_pending": True,
        "processing_generation_counts": {"final": 2, "interim": len(rows) - 2},
    }
    report["report_id"] = digest(report)
    ArtifactStore(destination + "/acquisition-runs").publish(
        "operations",
        report["report_id"],
        {
            "reconciliation.json": canonical_bytes(
                {k: v for k, v in report.items() if k != "report_id"}
            )
        },
    )
    return plan, report, destination


def stage_args(tmp_path, **kwargs):
    plan, report, destination = fixture(tmp_path, **kwargs)
    integration = build_context_integration_plan(plan, report)
    return (
        plan,
        report,
        integration,
        destination,
        integration["batches"][0]["batch_id"],
        tmp_path / "review",
    )


def test_final_only_plan_preserves_context_and_scientific_gates(tmp_path):
    plan, report, _ = fixture(tmp_path)
    integration = build_context_integration_plan(plan, report)
    assert integration["selected_final_days"] == 2
    assert integration["batches"][0]["days"] == ["2020-01-02", "2020-01-03"]
    assert len(integration["unsupported_final_dates"]) == 364
    assert integration["evidence_role"] == "regional_context"
    assert integration["spatial_operation"] == "grid_point_subsampling"
    assert integration["scientific_matching_performed"] is False
    assert integration["scientific_publication"] is False


@pytest.mark.parametrize(
    "mutation", ["partial", "duplicate", "bytes", "generation", "native", "report_hash"]
)
def test_malformed_terminal_evidence_cannot_enter_integration(tmp_path, mutation):
    plan, report, _ = fixture(tmp_path)
    if mutation == "partial":
        report["status"] = "bounded_partial_context_acquisition"
    elif mutation == "duplicate":
        report["request_results"][1] = deepcopy(report["request_results"][0])
    elif mutation == "bytes":
        report["raw_bytes"] += 1
    elif mutation == "generation":
        report["request_results"][1]["processing_generation"] = "unknown"
    elif mutation == "native":
        report["request_results"][1]["role"] = "native_patch"
    else:
        report["report_id"] = "f" * 64
    if mutation != "report_hash":
        report["report_id"] = digest(
            {k: v for k, v in report.items() if k != "report_id"}
        )
    with pytest.raises(ValueError):
        build_context_integration_plan(plan, report)


def test_large_month_is_partitioned_without_relaxing_byte_caps(tmp_path):
    plan, report, _ = fixture(tmp_path)
    for row in report["request_results"]:
        row.update(raw_bytes=8 * 1024**2, processing_generation="final")
    report["raw_bytes"] = len(report["request_results"]) * 8 * 1024**2
    report["processing_generation_counts"] = {
        "final": plan["request_count"],
        "interim": 0,
    }
    report["report_id"] = digest({k: v for k, v in report.items() if k != "report_id"})
    integration = build_context_integration_plan(plan, report)
    assert all(
        b["raw_bytes"] <= MAX_BATCH_RAW_BYTES and len(b["days"]) <= 2
        for b in integration["batches"]
    )
    assert sum(len(b["days"]) for b in integration["batches"]) == plan["request_count"]


def test_exact_retained_files_stage_and_repeat_with_verified_provenance(tmp_path):
    args = stage_args(tmp_path)
    result = stage_context_batch(*args)
    assert result["final_days"] == 2 and result["status"] == STAGED_STATUS
    assert result["database_access"] is False and result["cloud_writes"] is False
    manifest, files = read_bundle(
        args[-1], result["batch_id"], expected_digest=result["manifest_sha256"]
    )
    inventory = json.loads(files["review-inventory.json"])
    assert not inventory["status"].startswith("complete")
    assert inventory["coarse_context_is_native_sample_evidence"] is False
    assert all(
        f["evidence_role"] == "regional_context" and f["spatial_stride"] == 5
        for f in inventory["files"]
    )
    assert len([name for name in files if name.endswith(".nc")]) == 2
    assert stage_context_batch(*args) == result
    assert manifest["status"] == STAGED_STATUS


def test_actual_interim_header_cannot_be_staged_as_final(tmp_path):
    args = stage_args(tmp_path, masquerade_interim=True)
    with pytest.raises(ValueError, match="final MUR"):
        stage_context_batch(*args)
    assert not (args[-1] / args[-2]).exists()


def test_durable_report_mismatch_fails_before_local_staging(tmp_path):
    args = stage_args(tmp_path)
    plan, report, integration, uri, batch, root = args
    changed = deepcopy(report)
    changed["completed_at"] = "2026-10-08T00:00:00+00:00"
    changed["report_id"] = digest(
        {k: v for k, v in changed.items() if k != "report_id"}
    )
    ArtifactStore(uri + "/acquisition-runs").publish(
        "operations",
        changed["report_id"],
        {"reconciliation.json": canonical_bytes({"different": True})},
    )
    with pytest.raises(ValueError, match="Durable"):
        stage_context_batch(
            plan,
            changed,
            build_context_integration_plan(plan, changed),
            uri,
            build_context_integration_plan(plan, changed)["batches"][0]["batch_id"],
            root,
        )
    assert not root.exists()


def test_staging_rejects_modified_preflight_and_symlink_root(tmp_path):
    args = list(stage_args(tmp_path))
    args[2]["scientific_approval"] = True
    with pytest.raises(ValueError, match="preflight"):
        stage_context_batch(*args)
    args[2] = build_context_integration_plan(args[0], args[1])
    target = tmp_path / "target"
    target.mkdir()
    args[-1].symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="non-symlink"):
        stage_context_batch(*args)
