from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pytest
import xarray as xr

from ingestion.anemone_catalogue import file_sha256
from ingestion.immutable_bundle import digest
from preprocessing.research_sst import (
    GranuleInput,
    SSTProductDefinition,
    normalize_granule,
)
from scripts.run_research_context_panel import context_granules
from tests.test_research_sst import sst_fixture
from tests.test_sst_context_integration import stage_args
from ingestion.sst_context_integration import stage_context_batch


def context_product(area, plan_id=None):
    return SSTProductDefinition(
        product_id="mur_l4_foundation_sst",
        provider="NASA/JPL",
        version="04.1",
        measurement_type="satellite_in_situ_analysis",
        processing_level="L4",
        source_reference="https://podaac.jpl.nasa.gov/dataset/MUR-JPL-L4-GLOB-v4.1",
        expected_title="Daily MUR SST, Final product",
        temperature_variable="analysed_sst",
        ocean_mask_variable="mask",
        ocean_mask_values=(1,),
        uncertainty_variable="analysis_error",
        max_uncertainty_celsius=1.0,
        min_valid_fraction=0.8,
        min_ocean_pixels=5,
        decision=area.decision,
        regional_context={
            "source_plan_sha256": plan_id or digest("plan"),
            "max_sea_ice_fraction": 0.15,
            "missing_ice_policy": "use_open_sea_mask_with_warning",
        },
    )


@pytest.fixture
def context(tmp_path):
    _, _, legacy, _, areas = sst_fixture(tmp_path)
    area = areas[0].model_copy(
        update={"west": 140.0, "east": 140.15, "south": 38.0, "north": 38.15}
    )
    shape = (1, 5, 5)
    ds = xr.Dataset(
        {
            "analysed_sst": (
                ("time", "lat", "lon"),
                np.full(shape, 283.15),
                {"units": "kelvin"},
            ),
            "analysis_error": (
                ("time", "lat", "lon"),
                np.full(shape, 0.6),
                {"units": "kelvin"},
            ),
            "mask": (("time", "lat", "lon"), np.ones(shape)),
            "sea_ice_fraction": (("time", "lat", "lon"), np.full(shape, np.nan)),
        },
        coords={
            "time": [np.datetime64("2020-05-15T09:00:00")],
            "lat": 38 + np.arange(5) * 0.05,
            "lon": 140 + np.arange(5) * 0.05,
        },
        attrs={"title": "Daily MUR SST, Final product", "product_version": "04.1"},
    )
    path = tmp_path / "context.nc"
    ds.to_netcdf(path)
    granule = GranuleInput(
        granule_id=digest("granule"),
        raw_sha256=file_sha256(path),
        source_url="fixture://context",
        expected_time_utc=datetime(2020, 5, 15, 9, tzinfo=timezone.utc),
    )
    return path, ds, context_product(area), granule, [area]


def test_missing_ice_is_warning_and_context_is_not_native(context):
    row = normalize_granule(*context[:1], context[3], context[2], context[4])[0]
    assert row["sst_celsius"] == pytest.approx(10)
    assert row["warnings"] == ["missing_ice_fraction_open_sea_mask_used"]
    assert row["native_sample_area_evidence"] is False
    assert row["weighting"] == "cosine_latitude_grid_point_approximation"
    assert row["source_plan_sha256"] == context[2].regional_context.source_plan_sha256


@pytest.mark.parametrize("mutation", ["interim", "grid", "title"])
def test_wrong_generation_or_resolution_cannot_enter_context_panel(context, mutation):
    path, ds, product, granule, areas = context
    if mutation == "interim":
        ds.attrs["product_version"] = "04.1nrt"
    elif mutation == "grid":
        ds = ds.assign_coords(lon=140 + np.arange(5) * 0.01)
    else:
        ds.attrs["title"] = "Daily MUR SST, Interim near-real-time (nrt) product"
    ds.to_netcdf(path)
    granule = granule.model_copy(update={"raw_sha256": file_sha256(path)})
    with pytest.raises(ValueError):
        normalize_granule(path, granule, product, areas)


def test_invalid_ice_and_low_support_remain_explicit(context):
    path, ds, product, granule, areas = context
    ds.sea_ice_fraction.values[:] = 0.5
    ds.sea_ice_fraction.values[0, 0, :3] = 0
    ds.to_netcdf(path)
    granule = granule.model_copy(update={"raw_sha256": file_sha256(path)})
    row = normalize_granule(path, granule, product, areas)[0]
    assert row["valid_ocean_pixels"] == 3
    assert row["status"] == "insufficient_valid_ocean_pixels"
    assert row["sst_celsius"] is None
    assert row["sparse_summary_celsius"] == pytest.approx(10)
    assert row["warnings"] == ["insufficient_regional_support"]


def test_opt_in_contract_does_not_change_existing_product_hashes(tmp_path):
    product = sst_fixture(tmp_path)[2]
    legacy = product.model_dump(mode="json")
    assert "regional_context" not in legacy
    assert SSTProductDefinition.model_validate(legacy).model_dump(mode="json") == legacy
    assert digest(
        SSTProductDefinition.model_validate(legacy).model_dump(mode="json")
    ) == digest(legacy)


def test_context_inventory_requires_applied_exact_delivery_review(tmp_path):
    args = stage_args(tmp_path)
    staging = stage_context_batch(*args)
    area = sst_fixture(tmp_path)[4][0]
    product = context_product(area, args[0]["plan_sha256"])
    payload = {
        "schema_version": 1,
        "kind": "sst_product",
        "registry_key": "sst_product:mur_l4_foundation_sst",
        "definition": product.model_dump(mode="json"),
        "review_id": "00000000-0000-0000-0000-000000000001",
        "scientific_approval_sha256": digest("fixture-approved"),
    }
    granules = context_granules(args[0], args[1], staging, payload)
    assert len(granules) == 2
    bad = deepcopy(payload)
    bad["definition"]["regional_context"]["source_plan_sha256"] = digest("another-plan")
    with pytest.raises(ValueError, match="exact context"):
        context_granules(args[0], args[1], staging, bad)
    with pytest.raises(ValueError, match="applied"):
        context_granules(
            args[0], args[1], staging, {"definition": product.model_dump(mode="json")}
        )


def test_region_rectangle_does_not_invent_coordinate_uncertainty(context, tmp_path):
    from preprocessing.research_recipe import ReviewedArea

    path, _, product, granule, areas = context
    definition = areas[0].model_dump(mode="json")
    region = ReviewedArea.model_validate(
        {
            **definition,
            "geometry_type": "reviewed_regional_context_rectangle",
            "coordinate_uncertainty_km": None,
        }
    )
    assert (
        normalize_granule(path, granule, product, [region])[0][
            "native_sample_area_evidence"
        ]
        is False
    )
    with pytest.raises(ValueError, match="uncertainty"):
        ReviewedArea.model_validate({**definition, "coordinate_uncertainty_km": None})
    old = sst_fixture(tmp_path)[2]
    with pytest.raises(ValueError, match="Regional rectangles"):
        normalize_granule(
            path,
            granule,
            old.model_copy(update={"expected_title": product.expected_title}),
            [region],
        )
