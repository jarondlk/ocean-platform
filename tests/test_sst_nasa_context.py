from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest
import xarray as xr

from ingestion.artifact_store import ArtifactStore
from ingestion.immutable_bundle import canonical_bytes, digest
from ingestion.sst_hybrid_acquisition import acquire_hybrid
from ingestion.sst_inventory import build_inventory
from ingestion.sst_nasa_context import (
    acquire_nasa_context,
    build_nasa_context_plan,
    context_child,
    validate_nasa_context_plan,
)
from ingestion.sst_nasa_subset import validate_nasa_pilot


def setup(tmp_path):
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
    return plan, (tmp_path / "archive" / plan["plan_sha256"]).as_uri()


def download(child, stage):
    r = child["requests"][0]
    f = r["footprint"]
    lat = np.arange(round(f["south"] * 100), round(f["north"] * 100) + 1, 5) / 100
    lon = np.arange(round(f["west"] * 100), round(f["east"] * 100) + 1, 5) / 100
    nrt = r["day"].endswith("01-01")
    ds = xr.Dataset(
        {
            v: (("time", "lat", "lon"), np.ones((1, len(lat), len(lon))))
            for v in ("analysed_sst", "analysis_error", "mask", "sea_ice_fraction")
        },
        coords={
            "time": [np.datetime64(r["expected_time_utc"].removesuffix("Z"))],
            "lat": lat,
            "lon": lon,
        },
        attrs={
            "title": "Daily MUR SST, Interim near-real-time (nrt) product"
            if nrt
            else "Daily MUR SST, Final product",
            "product_version": "04.1nrt" if nrt else "04.1",
        },
    )
    ds.analysed_sst.attrs["units"] = "kelvin"
    ds.analysis_error.attrs["units"] = "kelvin"
    path = stage / "fixture.nc"
    ds.to_netcdf(path, engine="netcdf4")
    data = path.read_bytes()
    path.unlink()
    sha = hashlib.sha256(data).hexdigest()
    entry = {
        **r,
        "raw_sha256": sha,
        "bytes": len(data),
        "filename": r["day"] + "-" + sha + ".nc",
        "granule_id": digest({"source_url": r["source_url"], "raw_sha256": sha}),
    }
    (stage / entry["filename"]).write_bytes(data)
    (stage / "journal.json").write_bytes(canonical_bytes({"fixture": True}))
    return {
        "status": "complete_unapproved_acquisition",
        "plan": child,
        "files": [entry],
    }


def test_nasa_context_scope_bindings_and_interim_separation(tmp_path):
    plan, destination = setup(tmp_path)
    assert plan["request_count"] == 366
    assert plan["acquisition_scope"] == "context_only"
    assert plan["expected"]["native_location_days"] == 0
    ids = [r["request_sha256"] for r in plan["requests"][:2]]
    result = acquire_nasa_context(
        plan,
        destination,
        tmp_path / "work",
        tmp_path / "unused-credential",
        downloader=download,
        request_ids=ids,
    )
    assert result["status"] == "bounded_partial_context_acquisition"
    assert result["processing_generation_counts"] == {"final": 1, "interim": 1}
    assert result["full_hybrid_acquisition_complete"] is False
    assert result["native_patch_acquisition_pending"] is True
    assert result["scientific_approval"] is False
    first = result["request_results"][0]
    store = ArtifactStore(destination + "/requests/" + first["request_sha256"])
    _, contents = store.read("raw", first["artifact_id"])
    manifest = json.loads(contents["acquisition.json"])
    assert (
        json.loads(contents["diagnostics.json"])["requests"][0][
            "eligible_for_final_series"
        ]
        is False
    )
    with pytest.raises(ValueError, match="final MUR"):
        validate_nasa_pilot(manifest, contents, manifest["plan"])

    def never(*args, **kwargs):
        raise AssertionError("must resume retained bytes")

    resumed = acquire_nasa_context(
        plan,
        destination,
        tmp_path / "work",
        tmp_path / "unused",
        downloader=never,
        request_ids=ids,
    )
    assert resumed["request_results"] == result["request_results"]
    changed = deepcopy(plan)
    changed["scientific_approval"] = True
    changed["plan_sha256"] = digest(
        {k: v for k, v in changed.items() if k != "plan_sha256"}
    )
    with pytest.raises(ValueError, match="preflight"):
        validate_nasa_context_plan(changed)


def test_context_complete_terminal_is_not_full_hybrid_acceptance(tmp_path):
    plan, destination = setup(tmp_path)
    result = acquire_nasa_context(
        plan, destination, tmp_path / "work", tmp_path / "unused", downloader=download
    )
    assert result["status"] == "complete_unapproved_context_acquisition"
    assert result["counts"] == {"context_days": 366, "native_location_days": 0}
    assert result["processing_generation_counts"] == {"final": 365, "interim": 1}
    assert result["full_hybrid_acquisition_complete"] is False


def test_cumulative_budget_includes_prior_disjoint_pilots(tmp_path):
    plan, _ = setup(tmp_path)
    stage = tmp_path / "size"
    stage.mkdir()
    child = context_child(plan["requests"][0], plan["provider"])
    manifest = download(child, stage)
    plan["maximum_raw_bytes"] = manifest["files"][0]["bytes"]
    plan["plan_sha256"] = digest({k: v for k, v in plan.items() if k != "plan_sha256"})
    destination = (tmp_path / "budget" / plan["plan_sha256"]).as_uri()
    kwargs = dict(
        downloader=download,
        plan_validator=lambda p: None,
        child_planner=context_child,
        raw_validator=lambda m, c, p: validate_nasa_pilot(
            m, c, p, archive_interim=True
        ),
    )
    acquire_hybrid(
        plan,
        destination,
        tmp_path / "work",
        request_ids=[plan["requests"][0]["request_sha256"]],
        **kwargs,
    )
    with pytest.raises(ValueError, match="storage cap"):
        acquire_hybrid(
            plan,
            destination,
            tmp_path / "work",
            request_ids=[plan["requests"][1]["request_sha256"]],
            **kwargs,
        )
    assert (
        ArtifactStore(
            destination + "/requests/" + plan["requests"][1]["request_sha256"]
        ).entries("raw")
        == {}
    )
