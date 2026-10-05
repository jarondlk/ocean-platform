from datetime import datetime, timezone

import numpy as np
import pytest
from pydantic import ValidationError
import xarray as xr

from ingestion.anemone_catalogue import file_sha256
from ingestion.immutable_bundle import digest
from preprocessing.edna_detection_frequency import prepare_membership
from preprocessing.research_sst import (
    GranuleInput,
    SSTProductDefinition,
    link_sample_time,
    normalize_granule,
)
from tests.research_fixtures import h, research_fixture


def sst_fixture(tmp_path):
    path = tmp_path / "sst.nc"
    ds = xr.Dataset(
        {
            "analysed_sst": (
                ("time", "lat", "lon"),
                [[[283.15, 293.15], [303.15, np.nan]]],
                {"units": "K"},
            ),
            "mask": (("lat", "lon"), [[1, 1], [1, 0]]),
            "quality": (("lat", "lon"), [[5, 5], [5, 5]]),
        },
        coords={
            "time": [np.datetime64("2020-05-15T01:00:00")],
            "lat": [38.75, 38.25],
            "lon": [140.25, 140.75],
        },
        attrs={"title": "fixture foundation SST"},
    )
    ds.to_netcdf(path)
    areas = research_fixture()[2][:1]
    product = SSTProductDefinition(
        product_id="mur_l4_foundation_sst",
        provider="fixture",
        version="4.1",
        measurement_type="satellite_in_situ_analysis",
        processing_level="L4",
        source_reference="fixture://product",
        expected_title="fixture foundation SST",
        temperature_variable="analysed_sst",
        ocean_mask_variable="mask",
        ocean_mask_values=[1],
        quality_variable="quality",
        accepted_quality_values=[5],
        min_valid_fraction=0.5,
        min_ocean_pixels=1,
        decision=areas[0].decision,
    )
    granule = GranuleInput(
        granule_id=h("granule"),
        raw_sha256=file_sha256(path),
        source_url="fixture://granule",
        expected_time_utc=datetime(2020, 5, 15, 1, tzinfo=timezone.utc),
    )
    return path, ds, product, granule, areas


def test_kelvin_descending_axis_land_and_exact_pixel_trace(tmp_path):
    path, ds, product, granule, areas = sst_fixture(tmp_path)
    row = normalize_granule(path, granule, product, areas)[0]
    weights = np.cos(np.deg2rad([38.75, 38.75, 38.25]))
    assert row["sst_celsius"] == pytest.approx(
        np.average([10, 20, 30], weights=weights)
    )
    assert row["measurement_type"] == "satellite_in_situ_analysis"
    assert row["ocean_pixels"] == row["valid_ocean_pixels"] == 3
    assert row["pixel_rows"] == [0, 1] and row["pixel_columns"] == [0, 1]
    assert row["observation_id"] == digest(
        {k: v for k, v in row.items() if k != "observation_id"}
    )


def test_masks_and_footprint_cannot_be_bypassed(tmp_path):
    path, ds, product, granule, areas = sst_fixture(tmp_path)
    ds["quality"].values[:] = 0
    ds.to_netcdf(path)
    granule = granule.model_copy(update={"raw_sha256": file_sha256(path)})
    row = normalize_granule(path, granule, product, areas)[0]
    assert (
        row["status"] == "insufficient_valid_ocean_pixels"
        and row["sst_celsius"] is None
    )
    outside = research_fixture()[2][1]
    row = normalize_granule(path, granule, product, [outside])[0]
    assert row["status"] == "no_valid_footprint"


def test_time_product_units_and_tampering_fail_closed(tmp_path):
    path, ds, product, granule, areas = sst_fixture(tmp_path)
    with pytest.raises(ValueError, match="disagrees"):
        normalize_granule(
            path,
            granule.model_copy(
                update={"expected_time_utc": datetime(2020, 5, 16, tzinfo=timezone.utc)}
            ),
            product,
            areas,
        )
    with pytest.raises(ValidationError, match="measurement type"):
        SSTProductDefinition.model_validate(
            {
                **product.model_dump(mode="json"),
                "measurement_type": "satellite_retrieval",
            }
        )
    ds["analysed_sst"].attrs["units"] = "brightness_temperature"
    ds.to_netcdf(path)
    with pytest.raises(ValueError, match="checksum"):
        normalize_granule(path, granule, product, areas)
    granule = granule.model_copy(update={"raw_sha256": file_sha256(path)})
    with pytest.raises(ValueError, match="Unsupported SST units"):
        normalize_granule(path, granule, product, areas)


def test_indexed_time_link_retains_sample_time_and_gaps(tmp_path):
    path, ds, product, granule, areas = sst_fixture(tmp_path)
    rows = normalize_granule(path, granule, product, areas)
    recipe, source, all_areas, decisions, _, _ = research_fixture()
    members, _ = prepare_membership(recipe, source, all_areas, decisions)
    links, excluded = link_sample_time(members, rows, h("panel"), max_time_hours=24)
    assert len(links) == 3 and len(excluded) == 12
    assert all(link["time_difference_hours"] == 0 for link in links)
    assert all(link["source_granule_ids"] == [granule.granule_id] for link in links)
    assert len({link["physical_sample_id"] for link in links}) == 3
    with pytest.raises(ValueError, match="identity conflict"):
        link_sample_time(members, rows + rows, h("panel"), max_time_hours=24)


def test_mur_uncertainty_is_a_difference_and_noaa_celsius_is_supported(tmp_path):
    path, ds, product, granule, areas = sst_fixture(tmp_path)
    ds["analysed_sst"].values -= 273.15
    ds["analysed_sst"].attrs["units"] = "degree_C"
    ds["analysis_error"] = xr.DataArray(
        [[0.4, 2], [0.6, np.nan]], dims=("lat", "lon"), attrs={"units": "K"}
    )
    ds.to_netcdf(path)
    product = SSTProductDefinition.model_validate(
        {
            **product.model_dump(mode="json"),
            "quality_variable": None,
            "accepted_quality_values": [],
            "uncertainty_variable": "analysis_error",
            "max_uncertainty_celsius": 1,
        }
    )
    granule = granule.model_copy(update={"raw_sha256": file_sha256(path)})
    row = normalize_granule(path, granule, product, areas)[0]
    weights = np.cos(np.deg2rad([38.75, 38.25]))
    assert row["valid_ocean_pixels"] == 2
    assert row["sst_celsius"] == pytest.approx(np.average([10, 30], weights=weights))
    with pytest.raises(ValidationError, match="paired"):
        SSTProductDefinition.model_validate(
            {**product.model_dump(mode="json"), "uncertainty_variable": None}
        )


def test_float32_regular_coordinates_accept_quantization_but_not_irregularity():
    from preprocessing.research_sst import _axis

    ds = xr.Dataset(
        coords={"longitude": np.arange(141.37, 141.53, 0.01).astype(np.float32)}
    )
    _, spacing = _axis(ds, "longitude")
    assert spacing == pytest.approx(0.01, abs=0.00002)
    ds.longitude.values[5] += 0.002
    with pytest.raises(ValueError, match="regular"):
        _axis(ds, "longitude")
