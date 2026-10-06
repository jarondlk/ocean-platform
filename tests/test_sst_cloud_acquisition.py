import hashlib
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pytest
import xarray as xr

from ingestion.artifact_store import ArtifactStore
from ingestion.immutable_bundle import canonical_bytes, digest
from ingestion.sst_acquisition import build_history_plan
from ingestion.sst_cloud_acquisition import acquire_history, worker_lease
from ingestion.sst_inventory import build_inventory


def setup(tmp_path):
    inventory = build_inventory(
        [
            {
                "sample_id": digest("one"),
                "provider": "anemone",
                "active": True,
                "collection_date_utc": "2020-01-01T00:00:00Z",
                "temporal_precision": "datetime",
                "lat": 38.62,
                "lon": 141.44,
                "sample_kind": "unknown",
                "raw_metadata_json": {},
            }
        ],
        {},
    )
    plan = build_history_plan(inventory)
    destination = (tmp_path / "private" / plan["plan_sha256"]).as_uri()
    return plan, destination


def downloader(child, stage, *, ipv4_only, wrong_time=False):
    assert ipv4_only is True
    entries = []
    for request in child["requests"]:
        ds = xr.Dataset(
            {
                name: (("time", "latitude", "longitude"), np.ones((1, 2, 2)))
                for name in (
                    "analysed_sst",
                    "analysis_error",
                    "mask",
                    "sea_ice_fraction",
                )
            },
            coords={
                "time": [
                    np.datetime64(
                        "2020-02-01T09:00:00"
                        if wrong_time
                        else request["expected_time_utc"].removesuffix("Z")
                    )
                ],
                "latitude": [38.60, 38.61],
                "longitude": [141.40, 141.41],
            },
            attrs={"title": "MUR Global fv04.1"},
        )
        ds.analysed_sst.attrs["units"] = "degree_C"
        scratch = stage / "fixture.nc"
        ds.to_netcdf(scratch, engine="scipy")
        data = scratch.read_bytes()
        scratch.unlink()
        sha = hashlib.sha256(data).hexdigest()
        filename = request["day"] + "-" + sha + ".nc"
        (stage / filename).write_bytes(data)
        entries.append(
            {
                **request,
                "filename": filename,
                "bytes": len(data),
                "raw_sha256": sha,
                "granule_id": digest(
                    {"source_url": request["source_url"], "raw_sha256": sha}
                ),
            }
        )
    manifest = {
        "status": "complete_unapproved_acquisition",
        "plan": child,
        "files": entries,
    }
    (stage / "journal.json").write_bytes(canonical_bytes({"fixture": True}))
    return manifest


def test_private_acquisition_resume_exclusions_and_scientific_boundary(tmp_path):
    plan, destination = setup(tmp_path)
    options = {"excluded_days": ["2020-01-01"], "max_batches": 1}
    result = acquire_history(
        plan, destination, tmp_path / "work", downloader=downloader, **options
    )
    assert result["status"] == "bounded_partial_raw_acquisition"
    assert result["excluded_request_count"] == 1 and result["files"] == 11
    assert result["scientific_approval"] is False and result["database_access"] is False

    def never(*args, **kwargs):
        raise AssertionError("must reuse retained bytes")

    resumed = acquire_history(
        plan, destination, tmp_path / "work", downloader=never, **options
    )
    assert resumed["batch_results"] == result["batch_results"]
    assert resumed["raw_bytes"] == result["raw_bytes"]
    assert not list((tmp_path / "work").iterdir())
    root = ArtifactStore(destination + "/acquisition-control")
    assert root.pointer("operations/worker-lease.json")[0]["state"] == "released"


def test_corrupt_retained_bytes_stop_resume(tmp_path):
    plan, destination = setup(tmp_path)
    result = acquire_history(
        plan, destination, tmp_path / "work", max_batches=1, downloader=downloader
    )
    row = result["batch_results"][0]
    store = ArtifactStore(row["store_uri"])
    _, contents = store.read("raw", row["artifact_id"])
    filename = next(k for k in contents if k.endswith(".nc"))
    path = (
        Path(urlparse(row["store_uri"]).path)
        / "raw"
        / "objects"
        / row["artifact_id"]
        / filename
    )
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        acquire_history(
            plan, destination, tmp_path / "work", max_batches=1, downloader=downloader
        )


def test_raw_cap_and_actual_date_are_checked_before_private_publication(tmp_path):
    plan, destination = setup(tmp_path)
    with pytest.raises(ValueError, match="storage cap"):
        acquire_history(
            plan,
            destination,
            tmp_path / "work",
            max_batches=1,
            max_raw_bytes=1,
            downloader=downloader,
        )
    first = plan["batches"][0]["plan_sha256"]
    assert ArtifactStore(destination + "/batches/" + first).entries("raw") == {}

    def wrong(child, stage, **options):
        return downloader(child, stage, wrong_time=True, **options)

    with pytest.raises(ValueError, match="identity/time"):
        acquire_history(
            plan, destination, tmp_path / "work", max_batches=1, downloader=wrong
        )
    assert ArtifactStore(destination + "/batches/" + first).entries("raw") == {}


def test_competing_worker_and_tampered_plan_fail_closed(tmp_path):
    plan, destination = setup(tmp_path)
    with worker_lease(destination, ArtifactStore):
        with pytest.raises(ValueError, match="already active"):
            acquire_history(
                plan,
                destination,
                tmp_path / "work",
                max_batches=1,
                downloader=downloader,
            )
    plan["request_count"] += 1
    with pytest.raises(ValueError, match="preflight"):
        acquire_history(
            plan, destination, tmp_path / "work", max_batches=1, downloader=downloader
        )


def test_preexisting_raw_pilot_is_reverified_and_registered_without_download(tmp_path):
    plan, destination = setup(tmp_path)
    result = acquire_history(
        plan, destination, tmp_path / "work", max_batches=1, downloader=downloader
    )
    row = result["batch_results"][0]
    # Put the same verified raw generation in an independent operator destination,
    # simulating a pilot archive that predates cloud-worker checkpoints.
    second = (tmp_path / "pilot" / plan["plan_sha256"]).as_uri()
    receipt, contents = ArtifactStore(row["store_uri"]).read("raw", row["artifact_id"])
    ArtifactStore(second + "/batches/" + row["parent_plan_sha256"]).publish(
        "raw", row["artifact_id"], contents, metadata=receipt["metadata"]
    )

    def never(*args, **kwargs):
        raise AssertionError("pilot bytes must be reused")

    resumed = acquire_history(
        plan, second, tmp_path / "work", max_batches=1, downloader=never
    )
    assert (
        resumed["files"] == result["files"]
        and resumed["raw_bytes"] == result["raw_bytes"]
    )


def test_complete_explicit_plan_reconciles_all_requests_and_exclusions(tmp_path):
    plan, _ = setup(tmp_path)
    # A small explicit fixture plan exercises terminal reconciliation, including
    # an excluded date, without hundreds of redundant network-container fixtures.
    plan["batches"] = plan["batches"][:2]
    plan["batch_count"] = 2
    plan["request_count"] = sum(len(row["days"]) for row in plan["batches"])
    plan["plan_sha256"] = digest({k: v for k, v in plan.items() if k != "plan_sha256"})
    destination = (tmp_path / "complete" / plan["plan_sha256"]).as_uri()
    result = acquire_history(
        plan,
        destination,
        tmp_path / "work",
        excluded_days=["2020-01-01"],
        downloader=downloader,
    )
    assert result["status"] == "complete_raw_acquisition_with_explicit_exclusions"
    assert result["files"] + result["excluded_request_count"] == plan["request_count"]
    store = ArtifactStore(destination + "/acquisition-runs")
    _, files = store.read("operations", result["report_id"])
    assert files["reconciliation.json"] == canonical_bytes(
        {k: v for k, v in result.items() if k != "report_id"}
    )
