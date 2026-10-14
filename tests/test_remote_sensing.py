from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from preprocessing.research_recipe import ReviewedArea
from preprocessing.remote_sensing import (
    compute_daily_summary,
    extract_point_timeseries,
    parse_sst_time_from_filename,
)


def _write_sst(path, value, *, units="degree_Celsius", title="Synthetic regional SST"):
    dataset = xr.Dataset(
        {
            "SST": (
                ("time", "depth", "latitude", "longitude"),
                np.array([[[[value, value + 1], [value + 2, value + 3]]]]),
            )
        },
        coords={
            "time": [0],
            "depth": [0],
            "latitude": [38.0, 39.0],
            "longitude": [141.0, 142.0],
        },
    )
    dataset.attrs["title"] = title
    dataset["SST"].attrs.update(units=units, standard_name="sea_surface_temperature")
    dataset.to_netcdf(path, engine="netcdf4")


def test_sst_extractors_read_point_and_daily_region(tmp_path):
    _write_sst(tmp_path / "onagawa_sst_20240101_0000.nc", 10.0)
    _write_sst(tmp_path / "onagawa_sst_20240101_1200.nc", 12.0)

    point = extract_point_timeseries(tmp_path, 38.1, 141.1)
    daily = compute_daily_summary(tmp_path)

    assert len(point) == 2
    assert list(point["sst"]) == [10.0, 12.0]
    assert len(daily) == 1
    assert daily.iloc[0]["n_files"] == 2
    assert daily.iloc[0]["mean_sst"] == 12.5


def test_sst_filename_parser_rejects_missing_timestamp(tmp_path):
    assert parse_sst_time_from_filename(
        tmp_path / "onagawa_sst_20240101_1200.nc"
    ).year == 2024

    try:
        parse_sst_time_from_filename(tmp_path / "invalid.nc")
    except ValueError as exc:
        assert "Could not parse timestamp" in str(exc)
    else:
        raise AssertionError("Invalid SST filename was accepted")


def _reviewed_region(**changes):
    values = {
        "area_id": "synthetic-regional-context", "region_id": "synthetic-region",
        "label": "Synthetic regional context", "geometry_type": "reviewed_regional_context_rectangle",
        "west": 141.0, "east": 142.0, "south": 38.0, "north": 39.0,
        "coordinate_uncertainty_km": None,
        "decision": {
            "reviewer": "Synthetic reviewer", "rationale": "Synthetic geometry fixture only",
            "references": ["fixture://reviewed-regional-context"], "evidence_sha256": "a" * 64,
        },
    }
    values.update(changes)
    return ReviewedArea.model_validate(values)


def test_daily_summary_retains_exact_unreviewed_requested_bounds_and_sources(tmp_path):
    first = tmp_path / "onagawa_sst_20240101_0000.nc"
    second = tmp_path / "onagawa_sst_20240101_1200.nc"
    _write_sst(first, 10.0)
    _write_sst(second, 12.0)

    daily = compute_daily_summary(tmp_path, lat_min=38.0, lat_max=38.5, lon_min=141.0, lon_max=141.5)

    row = daily.iloc[0]
    support = json.loads(row["spatial_support"])
    assert support["kind"] == "unreviewed_regional_context_rectangle"
    assert support["reviewed"] is False and support["reference"] is None
    assert [support[key] for key in ("west", "east", "south", "north")] == [141.0, 141.5, 38.0, 38.5]
    assert row["mean_sst"] == 11.0 and row["n_files"] == 2
    assert "not a point" in row["aggregation_semantics"]
    inputs = json.loads(row["input_provenance"])
    assert inputs == {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in (first, second)}
    sources = json.loads(row["source_metadata"])
    assert len(sources) == 2
    assert sources[0]["product"]["title"] == "Synthetic regional SST"
    assert sources[0]["sst_attributes"]["units"] == "degree_Celsius"
    assert sources[0]["selected_latitude"] == {"minimum": 38.0, "maximum": 38.0, "n_centres": 1, "spacing_degrees": None}
    assert sources[0]["n_valid_pixels"] == 1
    assert "effective spatial resolution" in " ".join(support["grid_caveats"])
    target = tmp_path / "synthetic-summary.parquet"
    daily.to_parquet(target, index=False)
    saved = pd.read_parquet(target).iloc[0]
    assert json.loads(saved["spatial_support"]) == support
    assert json.loads(saved["input_provenance"]) == inputs


def test_daily_source_hashes_are_bound_to_their_actual_jst_day(tmp_path):
    first = tmp_path / "onagawa_sst_20240101_0000.nc"
    following_day = tmp_path / "onagawa_sst_20240101_1800.nc"
    _write_sst(first, 10.0)
    _write_sst(following_day, 20.0)

    daily = compute_daily_summary(tmp_path)

    assert len(daily) == 2
    assert [set(json.loads(row)) for row in daily["input_provenance"]] == [
        {str(first.resolve())}, {str(following_day.resolve())},
    ]
    assert [row["time_utc_from_filename"] for records in daily["source_metadata"] for row in json.loads(records)] == [
        "2024-01-01T00:00:00", "2024-01-01T18:00:00",
    ]


def test_matching_reviewed_region_preserves_geometry_decision_and_regional_semantics(tmp_path):
    from preprocessing.reliability_ensurance import _spatial_applicability
    _write_sst(tmp_path / "onagawa_sst_20240101_0000.nc", 10.0)
    area = _reviewed_region()

    row = compute_daily_summary(tmp_path, reviewed_area=area).iloc[0]

    support = json.loads(row["spatial_support"])
    assert support["reviewed"] is True
    assert support["kind"] == "reviewed_regional_context_rectangle"
    assert support["reference"] == "fixture://reviewed-regional-context"
    assert support["reviewed_area"] == area.model_dump(mode="json")
    assert support["reviewed_area_sha256"] == hashlib.sha256(json.dumps(
        area.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    assert _spatial_applicability({"lat": 38.5, "lon": 141.5}, row)[0] == "regional_context_only"
    assert _spatial_applicability({"lat": 40.9, "lon": 141.5}, row)[0] == "not_applicable"
    assert "not a point" in row["aggregation_semantics"]


def test_default_bounds_never_establish_reviewed_spatial_applicability(tmp_path):
    from preprocessing.reliability_ensurance import _spatial_applicability
    _write_sst(tmp_path / "onagawa_sst_20240101_0000.nc", 10.0)

    row = compute_daily_summary(tmp_path).iloc[0]

    assert _spatial_applicability({"lat": 38.5, "lon": 141.5}, row)[0] == "unknown"
    assert json.loads(row["spatial_support"])["reviewed"] is False


@pytest.mark.parametrize("area", [
    _reviewed_region(north=39.5),
    _reviewed_region(geometry_type="reviewed_cell_footprint", coordinate_uncertainty_km=1.0),
    _reviewed_region().model_dump(mode="json"),
    _reviewed_region().model_copy(update={"south": 40.0}),
])
def test_review_cannot_relabel_mismatching_or_unvalidated_calculation_geometry(tmp_path, area):
    with pytest.raises(ValueError):
        compute_daily_summary(tmp_path, reviewed_area=area)


@pytest.mark.parametrize("bounds", [
    {"lat_min": np.nan}, {"lon_max": np.inf}, {"lat_min": 40.0},
    {"lon_min": 142.0}, {"lat_min": True}, {"lat_max": 91.0},
])
def test_invalid_requested_spatial_bounds_fail_before_processing(tmp_path, bounds):
    with pytest.raises(ValueError):
        compute_daily_summary(tmp_path, **bounds)


def test_daily_values_and_receipts_use_same_bytes_when_source_path_is_replaced(tmp_path, monkeypatch):
    path = tmp_path / "onagawa_sst_20240101_0000.nc"
    replacement = tmp_path / "synthetic-replacement.snapshot"
    _write_sst(path, 10.0, title="Original synthetic product")
    _write_sst(replacement, 100.0, title="Replaced synthetic product")
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    open_dataset = xr.open_dataset
    calls = []

    def replace_path_after_dataset_opens(source, *args, **kwargs):
        dataset = open_dataset(source, *args, **kwargs)
        if not calls:
            # Replace the pathname after opening but before lazy values are read.
            # A separate pathname hash would now identify different source bytes.
            replacement.replace(path)
        calls.append(source)
        return dataset

    monkeypatch.setattr(xr, "open_dataset", replace_path_after_dataset_opens)

    row = compute_daily_summary(tmp_path).iloc[0]

    assert row["mean_sst"] == 11.5
    assert hashlib.sha256(path.read_bytes()).hexdigest() != original_hash
    assert json.loads(row["input_provenance"]) == {str(path.resolve()): original_hash}
    metadata = json.loads(row["source_metadata"])[0]
    assert metadata["file"] == path.name and metadata["path"] == str(path.resolve())
    assert metadata["sha256"] == original_hash
    assert metadata["product"]["title"] == "Original synthetic product"
    assert len(calls) == 1
