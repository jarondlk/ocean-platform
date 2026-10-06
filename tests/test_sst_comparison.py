import hashlib

import numpy as np
import pytest
import xarray as xr

from ingestion.sst_comparison import build_comparison_packet, inspect_mur_file
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
