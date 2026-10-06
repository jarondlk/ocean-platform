"""Bounded private raw acquisition with immutable per-batch checkpoints.

Operator-only; never accesses a database, scientific registry, corpus or model.
An incomplete batch stops the run. Resume verifies retained byte generations.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import uuid

import numpy as np
import xarray as xr

from ingestion.artifact_store import ArtifactStore
from ingestion.immutable_bundle import canonical_bytes, digest
from ingestion.sst_acquisition import (
    MAX_BATCH_DAYS,
    MAX_REQUESTS,
    VARIABLES,
    acquisition_plan,
    download_batch,
)
from preprocessing.research_sst import _axis

ALGORITHM = "private-historical-mur-acquisition-v1"
MAX_RAW_BYTES = 64 * 1024**3


@contextmanager
def worker_lease(destination, store_factory):
    """CAS writer exclusion; hard termination leaves an operator-reviewable lock."""
    store = store_factory(destination + "/acquisition-control")
    key = "operations/worker-lease.json"
    current, generation = store.pointer(key)
    if current and current.get("state") != "released":
        raise ValueError(
            "Historical worker already active; inspect stale lease before resuming"
        )
    holder = {
        "state": "active",
        "lease_id": str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    generation = store.replace_pointer(key, holder, generation)
    try:
        yield
    finally:
        observed, observed_generation = store.pointer(key)
        if observed != holder or observed_generation != generation:
            raise ValueError("Historical worker lease changed unexpectedly")
        store.replace_pointer(key, {**holder, "state": "released"}, generation)


def validate_history(plan):
    if (
        plan.get("plan_sha256")
        != digest({k: v for k, v in plan.items() if k != "plan_sha256"})
        or plan.get("kind") != "historical_mur_acquisition"
        or plan.get("schema_version") != 1
        or plan.get("scientific_publication") is not False
        or not 1 <= plan.get("request_count", 0) <= MAX_REQUESTS
        or len(plan.get("batches", [])) != plan.get("batch_count")
    ):
        raise ValueError("Historical acquisition preflight mismatch")
    seen, total = set(), 0
    for descriptor in plan["batches"]:
        child = acquisition_plan(descriptor["days"], **descriptor["footprint"])
        if (
            child["plan_sha256"] != descriptor["plan_sha256"]
            or child["plan_sha256"] in seen
            or len(child["requests"]) > MAX_BATCH_DAYS
        ):
            raise ValueError("Historical acquisition child mismatch")
        seen.add(child["plan_sha256"])
        total += len(child["requests"])
    if total != plan["request_count"]:
        raise ValueError("Historical acquisition request count mismatch")


def validate_raw(manifest, contents, child):
    if (
        manifest.get("status") != "complete_unapproved_acquisition"
        or manifest.get("plan") != child
    ):
        raise ValueError("Incomplete or mismatched raw acquisition")
    entries = manifest["files"]
    if len(entries) != len(child["requests"]):
        raise ValueError("Raw acquisition count mismatch")
    expected = {row["day"]: row for row in child["requests"]}
    seen, diagnostics = set(), []
    for entry in entries:
        request = expected.get(entry["day"])
        if (
            request is None
            or entry["day"] in seen
            or any(
                entry.get(k) != request[k]
                for k in ("day", "source_url", "expected_time_utc")
            )
        ):
            raise ValueError("Raw acquisition request binding mismatch")
        seen.add(entry["day"])
        data = contents[entry["filename"]]
        if (
            len(data) != entry["bytes"]
            or hashlib.sha256(data).hexdigest() != entry["raw_sha256"]
        ):
            raise ValueError("Raw acquisition byte mismatch")
        if (
            entry["granule_id"]
            != digest(
                {"source_url": entry["source_url"], "raw_sha256": entry["raw_sha256"]}
            )
            or entry["filename"] != entry["day"] + "-" + entry["raw_sha256"] + ".nc"
        ):
            raise ValueError("Raw acquisition granule identity mismatch")
        with xr.open_dataset(io.BytesIO(data)) as ds:
            if (
                "MUR" not in str(ds.attrs.get("title"))
                or "fv04.1" not in str(ds.attrs.get("title"))
                or set(("time", "latitude", "longitude", *VARIABLES))
                - set(ds.variables)
                or ds.time.size != 1
                or ds.analysed_sst.size > 100000
                or np.datetime_as_string(ds.time.values[0], unit="s") + "Z"
                != entry["expected_time_utc"]
                or ds.analysed_sst.attrs.get("units")
                not in (
                    "degree_C",
                    "degrees_C",
                    "degree_Celsius",
                    "degrees_Celsius",
                    "K",
                )
            ):
                raise ValueError("Raw MUR identity/time/field mismatch")
            for variable in VARIABLES:
                if set(ds[variable].dims) != {"time", "latitude", "longitude"}:
                    raise ValueError("Raw MUR field dimensions mismatch")
            lat, _ = _axis(ds, "latitude")
            lon, _ = _axis(ds, "longitude")
            footprint = child["footprint"]
            if (
                lat.min() < footprint["south"] - 0.011
                or lat.max() > footprint["north"] + 0.011
                or lon.min() < footprint["west"] - 0.011
                or lon.max() > footprint["east"] + 0.011
                or "nrt" in str(ds.attrs.get("product_version", "")).lower()
            ):
                raise ValueError("Raw MUR footprint/generation mismatch")
            diagnostics.append(
                {
                    "day": entry["day"],
                    "raw_sha256": entry["raw_sha256"],
                    "grid_values": int(ds.analysed_sst.size),
                    "finite_ocean_pixels": int(
                        (
                            (ds["mask"].values == 1)
                            & np.isfinite(ds.analysed_sst.values)
                        ).sum()
                    ),
                    "scientific_quality_threshold_applied": False,
                }
            )
    return diagnostics


def acquire_history(
    plan, destination, work_root, *, store_factory=ArtifactStore, **options
):
    validate_history(plan)
    if not destination.endswith("/" + plan["plan_sha256"]):
        raise ValueError("Historical destination binding mismatch")
    with worker_lease(destination, store_factory):
        return _acquire_history(
            plan, destination, work_root, store_factory=store_factory, **options
        )


def _acquire_history(
    plan,
    destination,
    work_root,
    *,
    excluded_days=(),
    max_raw_bytes=MAX_RAW_BYTES,
    max_batches=None,
    store_factory=ArtifactStore,
    downloader=download_batch,
    notify=lambda row: None,
):
    validate_history(plan)
    if (
        not destination.endswith("/" + plan["plan_sha256"])
        or not 0 < max_raw_bytes <= MAX_RAW_BYTES
        or len(set(excluded_days)) != len(excluded_days)
        or len(excluded_days) > 32
    ):
        raise ValueError("Historical destination/resource/exclusion mismatch")
    # Validate date strings and product interval even if no child contains them.
    for day in excluded_days:
        acquisition_plan([day], **plan["batches"][0]["footprint"])
    if max_batches is not None and (
        isinstance(max_batches, bool)
        or not isinstance(max_batches, int)
        or not 1 <= max_batches <= plan["batch_count"]
    ):
        raise ValueError("Invalid historical run batch limit")
    work_root = Path(work_root)
    if work_root.is_symlink():
        raise ValueError("Historical staging symlink forbidden")
    work_root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    report = {
        "algorithm": ALGORITHM,
        "history_plan_sha256": plan["plan_sha256"],
        "scientific_approval": False,
        "database_access": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "excluded_days": sorted(excluded_days),
        "excluded_request_count": 0,
        "maximum_raw_bytes": max_raw_bytes,
        "batch_results": [],
        "raw_bytes": 0,
        "files": 0,
    }
    for descriptor in plan["batches"][:max_batches]:
        parent = descriptor["plan_sha256"]
        omitted = sorted(set(descriptor["days"]) & set(excluded_days))
        days = sorted(set(descriptor["days"]) - set(excluded_days))
        report["excluded_request_count"] += len(omitted)
        if not days:
            raise ValueError(
                "An entirely excluded batch requires an explicit reviewed plan"
            )
        child = acquisition_plan(days, **descriptor["footprint"])
        checkpoint_id = digest(
            {
                "algorithm": ALGORITHM,
                "history": plan["plan_sha256"],
                "parent": parent,
                "child": child["plan_sha256"],
            }
        )
        checkpoint_store = store_factory(destination + "/batch-checkpoints/" + parent)
        checkpoints = checkpoint_store.entries("operations")
        raw_uri = destination + "/batches/" + parent
        raw_store = store_factory(raw_uri)
        if checkpoint_id in checkpoints:
            _, files = checkpoint_store.read(
                "operations", checkpoint_id, max_bytes=1024 * 1024
            )
            row = json.loads(files["checkpoint.json"])
            if (
                row["history_plan_sha256"] != plan["plan_sha256"]
                or row["child_plan_sha256"] != child["plan_sha256"]
                or row["store_uri"] != raw_uri
                or row["excluded_days"] != omitted
            ):
                raise ValueError("Historical checkpoint binding mismatch")
            receipt, contents = raw_store.read(
                "raw", row["artifact_id"], max_bytes=128 * 1024**2
            )
            if digest(receipt) != row["receipt_sha256"]:
                raise ValueError("Historical checkpoint raw receipt mismatch")
            resumed = True
        else:
            candidates = raw_store.entries("raw")
            matches = [
                key
                for key, value in candidates.items()
                if value.get("metadata", {}).get("history_plan_sha256")
                == plan["plan_sha256"]
                and value.get("metadata", {}).get("child_plan_sha256")
                == child["plan_sha256"]
            ]
            if len(matches) > 1:
                raise ValueError(
                    "Multiple raw generations require explicit operator selection"
                )
            if matches:
                receipt, contents = raw_store.read(
                    "raw", matches[0], max_bytes=128 * 1024**2
                )
                resumed = True
            else:
                with tempfile.TemporaryDirectory(prefix="mur-", dir=work_root) as name:
                    stage = Path(name)
                    manifest = downloader(child, stage, ipv4_only=True)
                    if manifest["status"] != "complete_unapproved_acquisition":
                        raise ValueError(
                            "Incomplete historical batch; prior checkpoints retained"
                        )
                    contents = {
                        row["filename"]: (stage / row["filename"]).read_bytes()
                        for row in manifest["files"]
                    }
                    diagnostics = validate_raw(manifest, contents, child)
                    contents.update(
                        {
                            "acquisition.json": canonical_bytes(manifest),
                            "journal.json": (stage / "journal.json").read_bytes(),
                            "diagnostics.json": canonical_bytes(diagnostics),
                        }
                    )
                    raw_bytes = sum(row["bytes"] for row in manifest["files"])
                    if report["raw_bytes"] + raw_bytes > max_raw_bytes:
                        raise ValueError(
                            "Historical raw storage cap reached; prior checkpoints retained"
                        )
                    identity = digest(
                        {"manifest": manifest, "diagnostics": diagnostics}
                    )
                    receipt = raw_store.publish(
                        "raw",
                        identity,
                        contents,
                        metadata={
                            "kind": "historical_mur_staged_acquisition",
                            "history_plan_sha256": plan["plan_sha256"],
                            "child_plan_sha256": child["plan_sha256"],
                            "scientific_approval": False,
                        },
                    )
                    observed, verified = raw_store.read(
                        "raw", identity, max_bytes=128 * 1024**2
                    )
                    if observed != receipt or verified != contents:
                        raise ValueError("Historical raw storage round-trip mismatch")
                    del verified
                resumed = False
        manifest = json.loads(contents["acquisition.json"])
        diagnostics = validate_raw(manifest, contents, child)
        if (
            receipt["metadata"].get("scientific_approval") is not False
            or digest({"manifest": manifest, "diagnostics": diagnostics})
            != receipt["id"]
            or json.loads(contents["diagnostics.json"]) != diagnostics
        ):
            raise ValueError("Historical raw identity/diagnostic mismatch")
        raw_bytes = sum(entry["bytes"] for entry in manifest["files"])
        if report["raw_bytes"] + raw_bytes > max_raw_bytes:
            raise ValueError(
                "Historical raw storage cap reached; prior checkpoints retained"
            )
        row = {
            "history_plan_sha256": plan["plan_sha256"],
            "parent_plan_sha256": parent,
            "child_plan_sha256": child["plan_sha256"],
            "artifact_id": receipt["id"],
            "receipt_sha256": digest(receipt),
            "store_uri": raw_uri,
            "excluded_days": omitted,
            "files": len(manifest["files"]),
            "raw_bytes": raw_bytes,
            "scientific_approval": False,
        }
        checkpoint_store.publish(
            "operations",
            checkpoint_id,
            {"checkpoint.json": canonical_bytes(row)},
            metadata={
                "kind": "historical_mur_raw_checkpoint",
                "scientific_approval": False,
            },
        )
        report["batch_results"].append(row)
        report["raw_bytes"] += raw_bytes
        report["files"] += row["files"]
        notify(
            {
                "batch_number": len(report["batch_results"]),
                "batch_count": plan["batch_count"],
                "files": report["files"],
                "raw_bytes": report["raw_bytes"],
                "resumed": resumed,
            }
        )
        del contents
    all_batches = len(report["batch_results"]) == plan["batch_count"]
    if (
        all_batches
        and report["files"] + report["excluded_request_count"] != plan["request_count"]
    ):
        raise ValueError("Historical reconciliation count mismatch")
    report["status"] = (
        "complete_raw_acquisition_with_explicit_exclusions"
        if all_batches
        else "bounded_partial_raw_acquisition"
    )
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report_id = digest(report)
    store_factory(destination + "/acquisition-runs").publish(
        "operations",
        report_id,
        {"reconciliation.json": canonical_bytes(report)},
        metadata={
            "kind": "historical_mur_raw_reconciliation",
            "scientific_approval": False,
        },
    )
    return {**report, "report_id": report_id}
