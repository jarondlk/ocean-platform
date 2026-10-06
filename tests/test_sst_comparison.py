import hashlib

import numpy as np
import pytest
import xarray as xr

from ingestion.sst_comparison import (
    build_comparison_packet,
    inspect_mur_file,
    inspect_himawari_file,
)
from ingestion.himawari_probe import parse_remote_file
from ingestion.sst_inventory import build_inventory
from tests.test_historical_sst_acquisition import sample


def test_probe_plan_is_deterministic_and_never_approves_product_or_areas():
    rows = [
        sample("north", lat=45.5),
        sample("south", lat=17.4),
        sample("miyagi", lat=38.62, collection_date_utc="2017-12-18T01:00:00Z"),
    ]
    inventory = build_inventory(rows, {"basis": "fixture"})
    report = build_comparison_packet(inventory)
    assert report == build_comparison_packet(
        build_inventory(rows[::-1], {"basis": "fixture"})
    )
    assert report["scientific_approval"] is False
    assert len(report["cases"]) == 3
    assert {r["day"] for r in report["cases"][0]["mur_plan"]["requests"]} == {
        "2017-12-18",
        "2021-07-15",
    }
    assert all(
        case["himawari_access_status"] == "requires_authenticated_historical_file_probe"
        for case in report["cases"]
    )


def test_diagnostics_verify_product_time_hash_and_ocean_support(tmp_path):
    path = tmp_path / "probe.nc"
    dataset = xr.Dataset(
        {
            "analysed_sst": (
                ("time", "latitude", "longitude"),
                [[[283.15, 293.15]]],
                {"units": "K"},
            ),
            "analysis_error": (
                ("time", "latitude", "longitude"),
                [[[0.2, 0.3]]],
                {"units": "degree_C"},
            ),
            "mask": (("time", "latitude", "longitude"), [[[1, 0]]]),
            "sea_ice_fraction": (("time", "latitude", "longitude"), [[[0, 0]]]),
        },
        coords={
            "time": [np.datetime64("2020-05-15T09:00:00")],
            "latitude": [38.5],
            "longitude": [141.4, 141.5],
        },
        attrs={"title": "MUR analysis fv04.1"},
    )
    dataset.to_netcdf(path)
    entry = {
        "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "expected_time_utc": "2020-05-15T09:00:00Z",
        "source_url": "fixture://mur",
    }
    report = inspect_mur_file(path, entry)
    assert report["ocean_pixels"] == report["finite_ocean_sst_pixels"] == 1
    assert report["sst_celsius_min"] == pytest.approx(10)
    assert report["scientific_quality_threshold_applied"] is False
    with pytest.raises(ValueError, match="timestamp"):
        inspect_mur_file(path, {**entry, "expected_time_utc": "2020-05-15T00:00:00Z"})
    dataset.attrs["title"] = "A different product"
    dataset.to_netcdf(path)
    with pytest.raises(ValueError, match="checksum"):
        inspect_mur_file(path, entry)
    with pytest.raises(ValueError, match="product/version"):
        inspect_mur_file(
            path, {**entry, "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )


def himawari_fixture(path):
    shape = (1, 4, 7)
    temperature = np.full(shape, 293.15)
    temperature[0, 1, 1] = np.nan
    dataset = xr.Dataset(
        {
            "sea_surface_temperature": (
                ("time", "lat", "lon"),
                temperature,
                {
                    "units": "kelvin",
                    "long_name": "Daily mean skin sea surface temperature",
                },
            ),
            "sst_daily_min": (
                ("time", "lat", "lon"),
                temperature - 1,
                {
                    "units": "kelvin",
                    "long_name": "Daily minimum skin sea surface temperature",
                },
            ),
            "quality_level": (
                ("time", "lat", "lon"),
                np.full(shape, 5),
                {"flag_values": [0, 1, 2, 3, 4, 5]},
            ),
            "l2p_flags": (
                ("time", "lat", "lon"),
                np.zeros(shape),
                {"long_name": "L2P flags at sst_daily_min"},
            ),
            "sses_standard_deviation": (
                ("time", "lat", "lon"),
                np.full(shape, 0.2),
                {
                    "units": "kelvin",
                    "long_name": "SSES standard deviation at sst_daily_min",
                },
            ),
            "sst_dtime": (
                ("time", "lat", "lon"),
                np.full(shape, 3600),
                {"units": "seconds"},
            ),
        },
        coords={
            "time": (
                "time",
                [np.datetime64("2023-07-15T00:00:18")],
                {"comment": "Includes leap seconds since 1981"},
            ),
            "lat": [60, 38.6, 38.58, -60],
            "lon": [80, 141.4, 141.42, 179.98, -180, -179.98, -160],
        },
        attrs={
            "title": "Sea Surface Temperature from AHI onboard Himawari-9",
            "product_version": "2.2",
            "id": "H09_AHI-JAXA-L3C-v02.2_daily",
            "time_coverage_start": "20230715T000000Z",
            "time_coverage_end": "20230716T000000Z",
        },
    )
    dataset.to_netcdf(path)
    return dataset


def himawari_entry(path):
    remote = "/pub/himawari/L3/SST/v201_nc4_normal_std_daily/202307/15/20230715000000-JAXA-L3C_GHRSST-SSTskin-H09_AHI-v2.2_daily-v02.0-fv01.0.nc"
    return {
        **parse_remote_file(remote),
        "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "byte_count": path.stat().st_size,
        "source_uri": "fixture://himawari",
    }


FOOTPRINT = {"south": 38.57, "north": 38.63, "west": 141.39, "east": 141.43}


def test_himawari_native_footprint_retains_leap_seconds_and_minimum_uncertainty_basis(
    tmp_path,
):
    path = tmp_path / "probe.nc"
    himawari_fixture(path)
    report = inspect_himawari_file(path, himawari_entry(path), FOOTPRINT)
    assert report["grid_values"] == 4
    assert (
        report["temperature_variables"]["sea_surface_temperature"]["celsius"][
            "finite_pixels"
        ]
        == 3
    )
    assert report["temperature_variables"]["sea_surface_temperature"]["celsius"][
        "mean"
    ] == pytest.approx(20)
    assert report["temperature_variables"]["sst_daily_min"]["celsius"][
        "mean"
    ] == pytest.approx(19)
    assert report["longitude_axis_unwrapped_for_selection"] is True
    assert report["reference_time_cf_offset_seconds"] == 18
    assert report["time_decoding_status"].endswith("no_correction_applied")
    assert report["diagnostics"]["sses_standard_deviation"]["long_name"].endswith(
        "sst_daily_min"
    )
    assert report["scientific_quality_threshold_applied"] is False
    west_of_dateline = {**FOOTPRINT, "west": -160.01, "east": -159.99}
    # End-of-grid checks retain an explicit unsupported footprint instead of clipping.
    with pytest.raises(ValueError, match="outside grid"):
        inspect_himawari_file(path, himawari_entry(path), west_of_dateline)


@pytest.mark.parametrize(
    "tamper",
    ["version", "coverage", "units", "leap_comment", "bad_offset", "axis", "flags"],
)
def test_himawari_product_time_axis_and_field_contract_fail_closed(tmp_path, tamper):
    path = tmp_path / "probe.nc"
    dataset = himawari_fixture(path)
    if tamper == "version":
        dataset.attrs["product_version"] = "2.1"
    elif tamper == "coverage":
        dataset.attrs["time_coverage_start"] = "20230716T000000Z"
    elif tamper == "units":
        dataset.sea_surface_temperature.attrs["units"] = "unknown"
    elif tamper == "leap_comment":
        dataset.time.attrs.clear()
    elif tamper == "bad_offset":
        dataset = dataset.assign_coords(time=[np.datetime64("2023-07-15T01:00:00")])
    elif tamper == "axis":
        dataset = dataset.assign_coords(lat=[60, 38.6, 38.6, -60])
    else:
        dataset["quality_level"] = dataset.quality_level + 0.5
    dataset.to_netcdf(path)
    with pytest.raises(ValueError):
        inspect_himawari_file(path, himawari_entry(path), FOOTPRINT)


def test_himawari_hash_and_footprint_cannot_be_silently_changed(tmp_path):
    path = tmp_path / "probe.nc"
    himawari_fixture(path)
    entry = himawari_entry(path)
    with pytest.raises(ValueError, match="checksum"):
        inspect_himawari_file(path, {**entry, "raw_sha256": "0" * 64}, FOOTPRINT)
    with pytest.raises(ValueError, match="footprint limit"):
        inspect_himawari_file(path, entry, {**FOOTPRINT, "east": 150})
