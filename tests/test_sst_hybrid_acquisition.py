from copy import deepcopy
import hashlib
import io
import json
from urllib.request import Request

import numpy as np
import pytest
import xarray as xr

from ingestion.artifact_store import ArtifactStore
from ingestion.immutable_bundle import canonical_bytes, digest
from ingestion.sst_hybrid_acquisition import (
    _Redirect,
    acquire_hybrid,
    build_hybrid_plan,
    download_hybrid_request,
    request_plan,
    validate_hybrid_plan,
    validate_hybrid_raw,
)
from ingestion.sst_inventory import build_inventory


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
    plan = build_hybrid_plan(inventory)
    return plan, (tmp_path / "archive" / plan["plan_sha256"]).as_uri()


def downloader(child, stage):
    request = child["requests"][0]
    step = child["spatial_stride"] * 0.01
    f = child["footprint"]
    lat = np.arange(f["south"], f["north"] + 1e-8, step)
    lon = np.arange(f["west"], f["east"] + 1e-8, step)
    times = np.asarray(
        [t.removesuffix("Z") for t in request["expected_times_utc"]],
        dtype="datetime64[s]",
    )
    ds = xr.Dataset(
        {
            v: (
                ("time", "latitude", "longitude"),
                np.ones((len(times), len(lat), len(lon))),
            )
            for v in ("analysed_sst", "analysis_error", "mask", "sea_ice_fraction")
        },
        coords={"time": times, "latitude": lat, "longitude": lon},
        attrs={"title": "MUR Global fv04.1", "product_version": "04.1"},
    )
    ds.analysed_sst.attrs["units"] = "degree_C"
    data = ds.to_netcdf(engine="scipy")
    sha = hashlib.sha256(data).hexdigest()
    entry = {
        **request,
        "filename": request["day"] + "-" + sha + ".nc",
        "raw_sha256": sha,
        "bytes": len(data),
        "granule_id": digest({"source_url": request["source_url"], "raw_sha256": sha}),
    }
    (stage / entry["filename"]).write_bytes(data)
    (stage / "journal.json").write_bytes(canonical_bytes({"fixture": True}))
    return {
        "status": "complete_unapproved_acquisition",
        "plan": child,
        "files": [entry],
    }


def test_full_calendar_roles_multiday_native_and_versioned_provider(tmp_path):
    plan, _ = setup(tmp_path)
    assert plan["expected"] == {
        "context_days": 366,
        "native_location_days": 366,
        "excluded_context_days": 0,
        "excluded_native_location_days": 0,
    }
    assert plan["request_count"] == 366 + 31
    fine = [r for r in plan["requests"] if r["role"] == "native_patch"]
    assert max(len(r["days"]) for r in fine) == 12
    assert sum(len(r["days"]) for r in fine) == 366
    assert plan["coarse_context_is_native_sample_evidence"] is False
    other = build_hybrid_plan(plan["source_inventory"], provider="noaa_upwell")
    assert other["plan_sha256"] != plan["plan_sha256"]
    changed = deepcopy(plan)
    changed["requests"][0]["role"] = "native_patch"
    changed["plan_sha256"] = digest(
        {k: v for k, v in changed.items() if k != "plan_sha256"}
    )
    with pytest.raises(ValueError, match="preflight"):
        validate_hybrid_plan(changed)


def test_excluded_dates_split_native_time_intervals_and_have_exact_counts(tmp_path):
    plan, _ = setup(tmp_path)
    inventory = plan["source_inventory"]
    inventory["sampling_years"] = [2021]
    inventory["inventory_id"] = digest(
        {k: v for k, v in inventory.items() if k != "inventory_id"}
    )
    result = build_hybrid_plan(inventory)
    assert result["expected"]["context_days"] == 363
    assert result["expected"]["excluded_native_location_days"] == 2
    for r in result["requests"]:
        assert "2021-02-20" not in r["days"] and "2021-02-21" not in r["days"]
        request_plan(r, result["provider"])
    assert result["scientific_approval"] is False


def test_native_only_acquisition_keeps_context_pending(tmp_path):
    plan, destination = setup(tmp_path)
    result = acquire_hybrid(
        plan,
        destination,
        tmp_path / "work",
        downloader=downloader,
        roles=["native_patch"],
    )
    assert result["selected_roles"] == ["native_patch"]
    assert result["selected_role_counts_reconciled"] is True
    assert result["counts"] == {"context_days": 0, "native_location_days": 366}
    assert result["status"] == "bounded_partial_hybrid_acquisition"


def test_byte_verified_resume_and_failure_evidence_do_not_publish_science(tmp_path):
    plan, destination = setup(tmp_path)
    ids = [
        plan["requests"][0]["request_sha256"],
        plan["requests"][-1]["request_sha256"],
    ]
    notices = []
    result = acquire_hybrid(
        plan,
        destination,
        tmp_path / "work",
        downloader=downloader,
        request_ids=ids,
        notify=notices.append,
    )
    assert result["counts"] == {"context_days": 1, "native_location_days": 6}
    assert result["status"] == "bounded_partial_hybrid_acquisition"
    assert result["database_access"] is False

    def never(*args, **kwargs):
        raise AssertionError("must reuse verified retained bytes")

    resumed = acquire_hybrid(
        plan, destination, tmp_path / "work", downloader=never, request_ids=ids
    )
    assert resumed["request_results"] == result["request_results"]
    store = ArtifactStore(destination + "/requests/" + ids[0])
    receipt, files = store.read("raw", result["request_results"][0]["artifact_id"])
    file = next(k for k in files if k.endswith(".nc"))
    store.store.root.joinpath("raw", "objects", receipt["id"], file).write_bytes(
        b"tamper"
    )
    with pytest.raises(ValueError, match="integrity"):
        acquire_hybrid(
            plan, destination, tmp_path / "work", downloader=never, request_ids=ids
        )

    failure_id = plan["requests"][1]["request_sha256"]

    def failed(child, stage):
        (stage / "journal.json").write_bytes(
            canonical_bytes({"status": "retryable", "last_error": "URLError"})
        )
        return {
            "status": "incomplete_unapproved_acquisition",
            "plan": child,
            "files": [],
            "outcomes": {"retryable": 1},
        }

    with pytest.raises(ValueError, match="failure journal"):
        acquire_hybrid(
            plan,
            destination,
            tmp_path / "work",
            downloader=failed,
            request_ids=[failure_id],
            notify=notices.append,
        )
    failure_store = ArtifactStore(destination + "/requests/" + failure_id)
    entries = failure_store.entries("operations")
    _, evidence = failure_store.read("operations", next(iter(entries)))
    assert json.loads(evidence["failure.json"])["scientific_approval"] is False
    assert json.loads(evidence["journal.json"])["last_error"] == "URLError"
    assert failure_store.entries("raw") == {}
    lease = ArtifactStore(destination + "/acquisition-control").pointer(
        "operations/worker-lease.json"
    )[0]
    assert lease["state"] == "released"


def test_actual_days_stride_nrt_and_byte_identity_are_verified(tmp_path):
    plan, _ = setup(tmp_path)
    child = request_plan(plan["requests"][-1], plan["provider"])
    stage = tmp_path / "fixture"
    stage.mkdir()
    manifest = downloader(child, stage)
    data = {
        row["filename"]: (stage / row["filename"]).read_bytes()
        for row in manifest["files"]
    }
    assert validate_hybrid_raw(manifest, data, child)["scientific_approval"] is False
    for change in ("time", "stride", "nrt"):
        ds = xr.open_dataset(io.BytesIO(next(iter(data.values())))).load()
        if change == "time":
            ds = ds.isel(time=slice(1, None))
        elif change == "stride":
            ds = ds.isel(latitude=slice(None, None, 2))
        else:
            ds.attrs["product_version"] = "04.1nrt"
        raw = ds.to_netcdf(engine="scipy")
        bad = deepcopy(manifest)
        entry = bad["files"][0]
        entry.update(raw_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        entry["filename"] = entry["day"] + "-" + entry["raw_sha256"] + ".nc"
        entry["granule_id"] = digest(
            {"source_url": entry["source_url"], "raw_sha256": entry["raw_sha256"]}
        )
        with pytest.raises(ValueError):
            validate_hybrid_raw(bad, {entry["filename"]: raw}, child)


def test_provider_redirect_boundary_and_complete_reconciliation(tmp_path):
    request = Request("https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.nc")
    for target in (
        "http://coastwatch.pfeg.noaa.gov/a",
        "https://upwell.pfeg.noaa.gov/a",
        "https://user:pass@coastwatch.pfeg.noaa.gov/a",
    ):
        with pytest.raises(ValueError, match="pinned provider"):
            _Redirect("coastwatch.pfeg.noaa.gov").redirect_request(
                request, None, 302, "", {}, target
            )
    plan, destination = setup(tmp_path)
    result = acquire_hybrid(plan, destination, tmp_path / "work", downloader=downloader)
    assert result["status"] == "complete_unapproved_hybrid_acquisition"
    assert (
        result["counts"]["context_days"]
        == result["counts"]["native_location_days"]
        == 366
    )
    assert result["scientific_approval"] is False
    _, files = ArtifactStore(destination + "/acquisition-runs").read(
        "operations", result["report_id"]
    )
    assert files["reconciliation.json"] == canonical_bytes(
        {k: v for k, v in result.items() if k != "report_id"}
    )


def test_multi_day_request_is_one_journal_entry_and_binding_is_checked(tmp_path):
    plan, _ = setup(tmp_path)
    child = request_plan(plan["requests"][-1], plan["provider"])
    stage = tmp_path / "fake"
    stage.mkdir()
    fixture = downloader(child, stage)
    raw = (stage / fixture["files"][0]["filename"]).read_bytes()

    class Opener:
        def open(self, url, timeout):
            assert url == child["requests"][0]["source_url"]
            return io.BytesIO(raw)

    manifest = download_hybrid_request(child, tmp_path / "download", opener=Opener())
    assert len(manifest["files"]) == 1
    assert manifest["files"][0]["days"] == child["requests"][0]["days"]
    assert validate_hybrid_raw(manifest, {manifest["files"][0]["filename"]: raw}, child)
    child["requests"][0]["source_url"] = "https://example.org/secret"
    with pytest.raises(ValueError, match="binding"):
        download_hybrid_request(child, tmp_path / "bad")
