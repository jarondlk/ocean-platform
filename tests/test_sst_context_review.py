from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from ingestion.immutable_bundle import canonical_bytes, digest
from ingestion.sst_context_integration import stage_context_batch
from ingestion.sst_nasa_subset import validate_nasa_pilot
from preprocessing.sst_context_review import (
    build_context_diagnostics,
    load_context_review,
)
from tests import test_sst_context_integration as source
from scripts import preview_historical_sst_context as cli


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    original_raw = source.raw

    def numeric_raw(child, **kwargs):
        manifest, _, contents = original_raw(child, **kwargs)
        entry = manifest["files"][0]
        path = tmp_path / (entry["day"] + ".nc")
        path.write_bytes(contents[entry["filename"]])
        with xr.open_dataset(path) as handle:
            ds = handle.load()
        ds["mask"].values[:] = 0
        ds["mask"].values[0, 0, :3] = 1
        ds.analysed_sst.values[0, 0, :3] = [283.15, 293.15, np.nan]
        ds.analysis_error.values[0, 0, :3] = [1, -1, np.nan]
        ds.sea_ice_fraction.values[0, 0, :3] = [0, 1.2, -0.1]
        data = ds.to_netcdf()
        sha = hashlib.sha256(data).hexdigest()
        entry.update(
            raw_sha256=sha,
            bytes=len(data),
            filename=entry["day"] + "-" + sha + ".nc",
            granule_id=digest({"source_url": entry["source_url"], "raw_sha256": sha}),
        )
        contents = {entry["filename"]: data}
        diagnostics = validate_nasa_pilot(manifest, contents, child)
        contents.update(
            {
                "acquisition.json": canonical_bytes(manifest),
                "diagnostics.json": canonical_bytes(diagnostics),
                "journal.json": canonical_bytes({"fixture": True}),
            }
        )
        return manifest, diagnostics, contents

    monkeypatch.setattr(source, "raw", numeric_raw)
    args = source.stage_args(tmp_path)
    return args[0], args[1], stage_context_batch(*args)


def test_verified_units_missing_values_and_context_semantics(inputs):
    result = build_context_diagnostics(*inputs)
    assert result == build_context_diagnostics(*inputs)
    assert result["diagnostics_id"] == digest(
        {k: v for k, v in result.items() if k != "diagnostics_id"}
    )
    day = result["daily"][0]
    assert day["ocean_grid_points"] == 3
    assert day["finite_ocean_temperature_points"] == 2
    assert day["missing_ocean_temperature_points"] == 1
    assert day["temperature_c"]["mean"] == pytest.approx(15)
    assert day["temperature_c"]["min"] == pytest.approx(10)
    assert day["temperature_c"]["max"] == pytest.approx(20)
    # Temperature differences must not receive the Kelvin-to-Celsius offset.
    assert day["analysis_error_k"]["mean"] == 0
    assert day["negative_ocean_analysis_error_points"] == 1
    assert day["missing_ocean_analysis_error_points"] == 1
    assert day["out_of_range_ocean_ice_points"] == 2
    assert day["finite_temperature_fraction_of_ocean"] == pytest.approx(2 / 3)
    assert result["grid_step_degrees"] == 0.05
    for flag in (
        "scientific_publication",
        "scientific_approval",
        "area_weighting_applied",
        "quality_acceptance_rules_applied",
        "scientific_matching_performed",
        "coarse_context_is_native_sample_evidence",
        "rectangle_is_reviewed_sampling_area",
    ):
        assert result[flag] is False
    assert len(result["month_dates_without_final_evidence_in_this_batch"]) == 29
    assert {
        g["reason"] for g in result["month_dates_without_final_evidence_in_this_batch"]
    } == {"interim_generation"}


def test_rectangle_and_no_ocean_preserve_nulls(inputs):
    plan = inputs[0]
    f = plan["context_footprint"]
    bounds = {
        "south": f["south"],
        "north": f["south"] + 0.01,
        "west": f["west"],
        "east": f["west"] + 0.01,
    }
    result = build_context_diagnostics(*inputs, bounds=bounds)
    assert result["daily"][0]["grid_points"] == 1
    assert result["daily"][0]["temperature_c"]["mean"] == pytest.approx(10)
    bounds.update(west=f["west"] + 0.1, east=f["west"] + 0.11)
    # Third point has missing SST; no invented zero or imputation.
    day = build_context_diagnostics(*inputs, bounds=bounds)["daily"][0]
    assert day["temperature_c"]["mean"] is None
    bounds.update(south=f["south"] + 0.05, north=f["south"] + 0.06)
    day = build_context_diagnostics(*inputs, bounds=bounds)["daily"][0]
    assert day["ocean_grid_points"] == 0
    assert day["finite_temperature_fraction_of_ocean"] is None
    assert day["temperature_c"]["mean"] is None
    # A rectangle between retained grid points also remains explicitly empty.
    bounds.update(south=f["south"] + 0.02, north=f["south"] + 0.03)
    day = build_context_diagnostics(*inputs, bounds=bounds)["daily"][0]
    assert day["grid_points"] == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"south": float("nan"), "north": 40, "west": 140, "east": 141},
        {"south": 17, "north": 40, "west": 140, "east": 141},
        {"south": 40, "north": 38, "west": 140, "east": 141},
        {"south": True, "north": 40, "west": 140, "east": 141},
        {"south": 38, "north": 40, "west": 140, "east": 141, "area_id": "approved"},
    ],
)
def test_rectangle_cannot_expand_archive_or_imply_approval(inputs, bad):
    with pytest.raises(ValueError, match="rectangle"):
        build_context_diagnostics(*inputs, bounds=bad)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scientific_approval", True),
        ("raw_bytes", 1),
        ("final_days", 1),
        ("integration_plan_id", "f" * 64),
        ("manifest_sha256", "f" * 64),
    ],
)
def test_stale_or_approved_receipt_rejected(inputs, field, value):
    plan, report, receipt = inputs
    receipt = {**receipt, field: value}
    with pytest.raises(ValueError):
        load_context_review(plan, report, receipt)


def reseal(package, receipt):
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"] = {
        name: hashlib.sha256((package / name).read_bytes()).hexdigest()
        for name in manifest["files"]
    }
    manifest_path.write_bytes(canonical_bytes(manifest))
    return {**receipt, "manifest_sha256": digest(manifest)}


@pytest.mark.parametrize("mutation", ["gaps", "provenance", "generation", "extra"])
def test_resealed_package_cannot_change_source_contract(inputs, mutation):
    plan, report, receipt = inputs
    package = Path(receipt["package_path"])
    inventory_path = package / "review-inventory.json"
    inventory = json.loads(inventory_path.read_bytes())
    if mutation == "gaps":
        inventory["unsupported_final_dates"] = []
    elif mutation == "generation":
        inventory["files"][0]["processing_generation"] = "interim"
    elif mutation == "provenance":
        path = package / inventory["files"][0]["provenance_filename"]
        provenance = json.loads(path.read_bytes())
        provenance["request_result"]["artifact_id"] = "f" * 64
        path.write_bytes(canonical_bytes(provenance))
    else:
        (package / "extra.json").write_bytes(b"{}")
        path = package / "manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest["files"]["extra.json"] = hashlib.sha256(b"{}").hexdigest()
        path.write_bytes(canonical_bytes(manifest))
    inventory_path.write_bytes(canonical_bytes(inventory))
    with pytest.raises(ValueError):
        load_context_review(plan, report, reseal(package, receipt))


def test_tampered_raw_and_symlink_paths_rejected(inputs, tmp_path):
    plan, report, receipt = inputs
    alias = tmp_path / "alias"
    alias.symlink_to(Path(receipt["package_path"]).parent, target_is_directory=True)
    with pytest.raises(ValueError, match="path"):
        load_context_review(
            plan, report, {**receipt, "package_path": str(alias / receipt["batch_id"])}
        )
    package = Path(receipt["package_path"])
    path = next(package.glob("*.nc"))
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        load_context_review(plan, report, receipt)


def test_source_report_mismatch_rejected(inputs):
    plan, report, receipt = inputs
    changed = deepcopy(report)
    changed["completed_at"] = "2026-10-08T00:00:00+00:00"
    changed["report_id"] = digest(
        {k: v for k, v in changed.items() if k != "report_id"}
    )
    with pytest.raises(ValueError):
        load_context_review(plan, changed, receipt)


def test_split_month_does_not_mislabel_other_final_dates_as_archive_gaps(
    tmp_path, monkeypatch
):
    from ingestion import sst_context_integration

    monkeypatch.setattr(sst_context_integration, "MAX_BATCH_DAYS", 1)
    args = source.stage_args(tmp_path)
    receipt = stage_context_batch(*args)
    result = build_context_diagnostics(args[0], args[1], receipt)
    gaps = {
        g["day"]: g["reason"]
        for g in result["month_dates_without_final_evidence_in_this_batch"]
    }
    assert gaps["2020-01-03"] == "final_date_in_another_batch"
    assert "2020-01-03" not in {
        g["day"] for g in result["archive_unsupported_final_dates"]
    }


@pytest.mark.parametrize(
    "destination", ["input", "package", "package_dotdot", "symlink"]
)
def test_cli_cannot_overwrite_inputs_or_sealed_review(
    inputs, tmp_path, monkeypatch, destination
):
    plan, report, receipt = inputs
    paths = []
    for name, data in zip(("plan", "report", "receipt"), inputs):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical_bytes(data))
        paths.append(path)
    package = Path(receipt["package_path"])
    if destination == "input":
        output = paths[0]
    elif destination == "package":
        output = package / "preview.json"
    elif destination == "package_dotdot":
        output = package.parent / "other" / ".." / package.name / "preview.json"
    else:
        alias = tmp_path / "alias"
        alias.symlink_to(package, target_is_directory=True)
        output = alias / "preview.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "preview",
            "--context-plan",
            str(paths[0]),
            "--reconciliation",
            str(paths[1]),
            "--staging-receipt",
            str(paths[2]),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert not (package / "preview.json").exists()
    assert load_context_review(plan, report, receipt)
