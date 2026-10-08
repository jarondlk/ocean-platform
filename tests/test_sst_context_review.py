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
    ContextQualityProposal,
    _quality_preview,
    build_context_diagnostics,
    load_context_review,
)
from tests import test_sst_context_integration as source
from scripts import preview_historical_sst_context as cli
from preprocessing.historical_sst_matching import preview_context_observations


def quality_proposal(**changes):
    return dict(
        max_analysis_error_k=1.0,
        max_sea_ice_fraction=0.15,
        min_valid_ocean_fraction=0.8,
        min_valid_ocean_points=5,
        weighting="cosine_latitude_grid_point_approximation",
        **changes,
    )


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


def test_context_adapter_keeps_sparse_mean_and_unpublished_provenance(inputs):
    result = build_context_diagnostics(*inputs, proposed_quality=quality_proposal())
    rows = preview_context_observations(result, "diagnostic-rectangle")
    assert rows[0]["sst_celsius"] == pytest.approx(10.0)
    assert rows[0]["status"] == "insufficient_support"
    assert rows[0]["source_diagnostics_id"] == result["diagnostics_id"]
    assert rows[0]["area_is_reviewed"] is False
    assert rows[0]["scientific_publication"] is False
    assert rows[0]["native_sample_area_evidence"] is False
    assert rows[0]["observation_id"] == digest(
        {k: v for k, v in rows[0].items() if k != "observation_id"}
    )


@pytest.mark.parametrize(
    "kind", ["tamper", "interim", "approval", "proposal", "duplicate"]
)
def test_context_adapter_rejects_changed_or_contradictory_evidence(inputs, kind):
    result = build_context_diagnostics(*inputs, proposed_quality=quality_proposal())
    if kind == "tamper":
        result["daily"][0]["proposed_quality_preview"]["sst_celsius"] = 19.0
    else:
        if kind == "interim":
            result["daily"][0]["processing_generation"] = "interim"
        elif kind == "approval":
            result["scientific_approval"] = True
        elif kind == "proposal":
            result["proposed_quality"]["max_analysis_error_k"] = 0.5
        elif kind == "duplicate":
            result["daily"].append(deepcopy(result["daily"][0]))
        result["diagnostics_id"] = digest(
            {k: v for k, v in result.items() if k != "diagnostics_id"}
        )
    with pytest.raises(ValueError):
        preview_context_observations(result, "diagnostic-rectangle")


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


def test_proposed_quality_keeps_sparse_value_without_approval(inputs):
    original = build_context_diagnostics(*inputs)
    proposal = quality_proposal()
    result = build_context_diagnostics(*inputs, proposed_quality=proposal)
    day = result["daily"][0]
    preview = day.pop("proposed_quality_preview")
    assert day == original["daily"][0]
    assert preview["valid_ocean_points"] == 1
    assert preview["valid_fraction_of_open_ocean"] == pytest.approx(1 / 3)
    assert preview["sst_celsius"] == pytest.approx(10)
    assert preview["meets_proposed_support"] is False
    assert len(preview["warnings"]) == 2
    assert result["quality_acceptance_rules_applied"] is False
    assert result["scientific_publication"] is False
    assert (
        result["archive_unsupported_final_dates"]
        == original["archive_unsupported_final_dates"]
    )
    assert result["diagnostics_id"] != original["diagnostics_id"]
    assert result["proposed_quality"]["proposal_id"] == digest(
        ContextQualityProposal.model_validate(proposal).model_dump(mode="json")
    )


def test_cosine_weighting_is_grid_point_approximation():
    proposal = quality_proposal()
    proposal["min_valid_ocean_points"] = 1
    arrays = (
        np.array([[10.0], [20.0]]),
        np.ones((2, 1)),
        np.zeros((2, 1)),
        np.ones((2, 1), dtype=bool),
        np.array([0.0, 60.0]),
    )
    weighted = _quality_preview(
        *arrays, ContextQualityProposal.model_validate(proposal)
    )
    assert weighted["sst_celsius"] == pytest.approx(40 / 3)
    assert weighted["meets_proposed_support"] is True
    proposal["weighting"] = "equal_grid_points"
    equal = _quality_preview(*arrays, ContextQualityProposal.model_validate(proposal))
    assert equal["sst_celsius"] == 15
    assert equal["native_sample_area_evidence"] is False
    # No usable values, including all-land support, must never turn into zero SST.
    arrays = (*arrays[:3], np.zeros((2, 1), dtype=bool), arrays[-1])
    absent = _quality_preview(*arrays, ContextQualityProposal.model_validate(proposal))
    assert absent["sst_celsius"] is None
    assert absent["valid_fraction_of_open_ocean"] is None
    assert "no_open_ocean_grid_support" in absent["warnings"]


def test_missing_ice_uses_mask_only_when_explicit_and_preserves_warning():
    proposal = quality_proposal()
    proposal["min_valid_ocean_points"] = 1
    arrays = (
        np.array([[10.0, 20.0, 30.0, 40.0]]),
        np.ones((1, 4)),
        np.array([[np.nan, np.inf, 0.5, np.nan]]),
        np.array([[True, True, True, False]]),
        np.array([38.0]),
    )
    strict = _quality_preview(*arrays, ContextQualityProposal.model_validate(proposal))
    assert strict["sst_celsius"] is None
    proposal["missing_ice_policy"] = "use_open_sea_mask_with_warning"
    preview = _quality_preview(*arrays, ContextQualityProposal.model_validate(proposal))
    assert preview["sst_celsius"] == 10
    assert preview["valid_ocean_points"] == 1
    assert preview["retained_points_with_missing_ice_fraction"] == 1
    assert "missing_ice_fraction_open_sea_mask_used" in preview["warnings"]
    # Known high ice, infinity and non-open-sea points are still excluded.
    assert preview["valid_fraction_of_open_ocean"] == pytest.approx(1 / 3)
    proposal["min_valid_ocean_fraction"] = 0.3
    preview = _quality_preview(*arrays, ContextQualityProposal.model_validate(proposal))
    assert preview["meets_proposed_support"] is True
    assert preview["warnings"] == ["missing_ice_fraction_open_sea_mask_used"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("scientific_approval", True),
        ("status", "approved"),
        ("max_analysis_error_k", -1),
        ("max_analysis_error_k", float("nan")),
        ("min_valid_ocean_fraction", 0),
        ("min_valid_ocean_fraction", 1.1),
        ("min_valid_ocean_points", True),
        ("max_sea_ice_fraction", -1),
        ("weighting", "native_area_weighted"),
        ("missing_ice_policy", "assume_zero"),
    ],
)
def test_quality_proposal_cannot_assert_approval_or_invalid_rules(field, value):
    from pydantic import ValidationError

    proposal = quality_proposal()
    proposal[field] = value
    with pytest.raises(ValidationError):
        ContextQualityProposal.model_validate(proposal)
