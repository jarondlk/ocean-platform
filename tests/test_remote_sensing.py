from __future__ import annotations

import numpy as np
import xarray as xr

from preprocessing.remote_sensing import (
    compute_daily_summary,
    extract_point_timeseries,
    parse_sst_time_from_filename,
)


def _write_sst(path, value):
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
