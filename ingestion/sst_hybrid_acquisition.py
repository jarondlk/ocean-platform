"""Private hybrid MUR acquisition; coarse context never becomes local evidence.

Uses new plan identities, bounded multi-day native patches, immutable receipts
and the existing request journal. No database or scientific publication access.
"""

from datetime import date, datetime, timedelta, timezone
import hashlib
from http.client import HTTPSConnection
import io
import json
import math
import os
from pathlib import Path
import socket
import tempfile
import time
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener

import numpy as np
import xarray as xr

from ingestion.artifact_store import ArtifactStore
from ingestion.immutable_bundle import canonical_bytes, digest
from ingestion.sst_acquisition import (
    MAX_FILE_BYTES,
    MAX_REQUESTS,
    VARIABLES,
    _download_locked,
)
from ingestion.sst_cloud_acquisition import worker_lease
from preprocessing.research_sst import _axis

PROVIDERS = {
    "noaa_coastwatch": "coastwatch.pfeg.noaa.gov",
    "noaa_upwell": "upwell.pfeg.noaa.gov",
}
ALGORITHM = "private-hybrid-mur-acquisition-v1"
MAX_GRID_VALUES = 300_000
MAX_RAW_BYTES = 32 * 1024**3
EXCLUDED_DAYS = ("2021-02-20", "2021-02-21")


def _footprint(location):
    # Native-cell envelope, not a reviewed physical sampling area/uncertainty.
    lat, lon = location["lat"], location["lon"]
    return {
        "south": round(math.floor(lat * 100) / 100 - 0.05, 6),
        "north": round(math.ceil(lat * 100) / 100 + 0.05, 6),
        "west": round(math.floor(lon * 100) / 100 - 0.05, 6),
        "east": round(math.ceil(lon * 100) / 100 + 0.05, 6),
    }


def _context_footprint(locations):
    return {
        "south": round(
            math.floor(min(x["lat"] for x in locations) * 20) / 20 - 0.05, 6
        ),
        "north": round(math.ceil(max(x["lat"] for x in locations) * 20) / 20 + 0.05, 6),
        "west": round(math.floor(min(x["lon"] for x in locations) * 20) / 20 - 0.05, 6),
        "east": round(math.ceil(max(x["lon"] for x in locations) * 20) / 20 + 0.05, 6),
    }


def request_plan(descriptor, provider):
    """One raw file: one context day or at most 12 consecutive native days."""
    if provider not in PROVIDERS or descriptor["role"] not in {
        "context",
        "native_patch",
    }:
        raise ValueError("Unsupported hybrid provider/role")
    days, footprint = descriptor["days"], descriptor["footprint"]
    dates = [date.fromisoformat(day) for day in days]
    stride = 5 if descriptor["role"] == "context" else 1
    limit = 1 if stride == 5 else 12
    if (
        not 1 <= len(days) <= limit
        or days != sorted(set(days))
        or any(d != dates[0] + timedelta(days=i) for i, d in enumerate(dates))
        or any(not date(2002, 6, 1) <= d <= date.today() for d in dates)
        or any(day in EXCLUDED_DAYS for day in days)
    ):
        raise ValueError("Hybrid dates must be exact, consecutive and non-excluded")
    south, north, west, east = (
        footprint[k] for k in ("south", "north", "west", "east")
    )
    if (
        any(
            isinstance(v, bool) or not math.isfinite(v)
            for v in (south, north, west, east)
        )
        or not -89.9 <= south < north <= 89.9
        or not -179.9 <= west < east <= 179.9
        or (stride == 1 and (north - south > 0.121 or east - west > 0.121))
    ):
        raise ValueError("Invalid hybrid acquisition envelope")
    step = 0.01 * stride
    grid_values = (
        len(days)
        * (math.ceil((north - south) / step) + 2)
        * (math.ceil((east - west) / step) + 2)
    )
    estimate = grid_values * 25 + 4096
    if grid_values > MAX_GRID_VALUES or estimate > MAX_FILE_BYTES:
        raise ValueError("Hybrid request requires explicit bounded partitioning")
    times = [day + "T09:00:00Z" for day in days]
    constraint = (
        f"[({times[0]}):1:({times[-1]})]"
        f"[({south:.6f}):{stride}:({north:.6f})]"
        f"[({west:.6f}):{stride}:({east:.6f})]"
    )
    endpoint = f"https://{PROVIDERS[provider]}/erddap/griddap/jplMURSST41.nc"
    query = ",".join(variable + constraint for variable in VARIABLES)
    plan = {
        "schema_version": 2,
        "kind": "hybrid_mur_request",
        "provider": provider,
        "product_id": "mur_l4_foundation_sst",
        "measurement_type": "satellite_in_situ_analysis",
        "role": descriptor["role"],
        "location_id": descriptor.get("location_id"),
        "footprint": footprint,
        "spatial_stride": stride,
        "spatial_operation": "native_grid_subsampling"
        if stride == 5
        else "native_grid_subset",
        "scientific_approval": False,
        "estimated_raw_bytes": estimate,
        "requests": [
            {
                "day": days[0],
                "days": days,
                "expected_time_utc": times[0],
                "expected_times_utc": times,
                "source_url": endpoint + "?" + quote(query, safe="(),:"),
            }
        ],
    }
    return {**plan, "plan_sha256": digest(plan)}


def build_hybrid_plan(inventory, *, provider="noaa_coastwatch"):
    if inventory.get("inventory_id") != digest(
        {k: v for k, v in inventory.items() if k != "inventory_id"}
    ):
        raise ValueError("Hybrid acquisition inventory checksum mismatch")
    years, locations = inventory["sampling_years"], inventory["locations"]
    if (
        not years
        or years != sorted(set(years))
        or len(years) > 10
        or any(
            isinstance(y, bool)
            or not isinstance(y, int)
            or not 2003 <= y < date.today().year
            for y in years
        )
        or not 1 <= len(locations) <= 1000
        or len({x["location_id"] for x in locations}) != len(locations)
    ):
        raise ValueError(
            "Hybrid scope requires bounded locations and complete calendar years"
        )
    all_days = [
        (date(year, 1, 1) + timedelta(days=i)).isoformat()
        for year in years
        for i in range((date(year + 1, 1, 1) - date(year, 1, 1)).days)
    ]
    days = [d for d in all_days if d not in EXCLUDED_DAYS]
    requests = []

    def append(role, selected, footprint, location_id=None):
        descriptor = {
            "role": role,
            "days": selected,
            "footprint": footprint,
            "location_id": location_id,
        }
        child = request_plan(descriptor, provider)
        requests.append({**descriptor, "request_sha256": child["plan_sha256"]})
        return child["estimated_raw_bytes"]

    context = _context_footprint(locations)
    estimated = sum(append("context", [day], context) for day in days)
    for location in sorted(locations, key=lambda row: row["location_id"]):
        group = []
        footprint = _footprint(location)
        for day in days:
            if group and (
                len(group) == 12
                or date.fromisoformat(day)
                != date.fromisoformat(group[-1]) + timedelta(days=1)
            ):
                estimated += append(
                    "native_patch", group, footprint, location["location_id"]
                )
                group = []
            group.append(day)
        if group:
            estimated += append(
                "native_patch", group, footprint, location["location_id"]
            )
    if len(requests) > MAX_REQUESTS or estimated > MAX_RAW_BYTES:
        raise ValueError(
            "Hybrid plan exceeds request/storage envelope; partition explicitly"
        )
    expected = {
        "context_days": len(days),
        "native_location_days": len(locations) * len(days),
        "excluded_context_days": len(all_days) - len(days),
        "excluded_native_location_days": len(locations) * (len(all_days) - len(days)),
    }
    plan = {
        "schema_version": 1,
        "kind": "historical_hybrid_mur_acquisition",
        "algorithm": ALGORITHM,
        "provider": provider,
        "source_inventory": inventory,
        "context_footprint": context,
        "sampling_years": years,
        "excluded_days": [d for d in EXCLUDED_DAYS if d in all_days],
        "scientific_approval": False,
        "scientific_publication": False,
        "coarse_context_is_native_sample_evidence": False,
        "native_patch_basis": "unreviewed_coordinate_acquisition_envelope",
        "expected": expected,
        "request_count": len(requests),
        "estimated_raw_bytes": estimated,
        "maximum_raw_bytes": MAX_RAW_BYTES,
        "requests": requests,
    }
    return {**plan, "plan_sha256": digest(plan)}


def validate_hybrid_plan(plan):
    if (
        plan.get("plan_sha256")
        != digest({k: v for k, v in plan.items() if k != "plan_sha256"})
        or build_hybrid_plan(plan["source_inventory"], provider=plan["provider"])
        != plan
    ):
        raise ValueError("Hybrid acquisition preflight mismatch")


class _Redirect(HTTPRedirectHandler):
    def __init__(self, host):
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if (
            target.scheme != "https"
            or target.hostname != self.host
            or target.port not in (None, 443)
            or target.username
            or target.password
        ):
            raise ValueError("Hybrid redirect outside pinned provider")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def hybrid_opener(provider):
    host = PROVIDERS[provider]

    class Connection(HTTPSConnection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._create_connection = self.connect_ipv4

        @staticmethod
        def connect_ipv4(address, timeout=30, source_address=None):
            if address != (host, 443):
                raise ValueError("Hybrid connection outside pinned provider")
            errors = []
            for family, kind, protocol, _, target in socket.getaddrinfo(
                host, 443, socket.AF_INET, socket.SOCK_STREAM
            ):
                connection = socket.socket(family, kind, protocol)
                try:
                    connection.settimeout(timeout)
                    if source_address:
                        connection.bind(source_address)
                    connection.connect(target)
                    return connection
                except OSError as error:
                    connection.close()
                    errors.append(error)
            raise errors[-1] if errors else OSError("Provider has no IPv4 address")

    class Handler(HTTPSHandler):
        def https_open(self, req):
            return self.do_open(Connection, req, context=self._context)

    return build_opener(_Redirect(host), Handler())


def download_hybrid_request(
    plan, directory, *, opener=None, attempts=3, sleep=time.sleep
):
    descriptor = {
        "role": plan["role"],
        "days": plan["requests"][0]["days"],
        "footprint": plan["footprint"],
        "location_id": plan["location_id"],
    }
    if plan != request_plan(descriptor, plan["provider"]):
        raise ValueError("Hybrid request binding mismatch")
    if (
        isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or not 1 <= attempts <= 5
    ):
        raise ValueError("Invalid hybrid retry limit")
    directory = Path(directory)
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("Hybrid staging symlink forbidden")
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".acquisition.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(str(os.getpid()))
    try:
        return _download_locked(
            plan,
            directory,
            attempts,
            False,
            opener or hybrid_opener(plan["provider"]),
            sleep,
        )
    finally:
        lock.unlink()


def validate_hybrid_raw(manifest, contents, child):
    if (
        manifest.get("status") != "complete_unapproved_acquisition"
        or manifest.get("plan") != child
        or len(manifest.get("files", [])) != 1
    ):
        raise ValueError("Incomplete/mismatched hybrid raw acquisition")
    entry, request = manifest["files"][0], child["requests"][0]
    if any(entry.get(k) != v for k, v in request.items()):
        raise ValueError("Hybrid raw request binding mismatch")
    data = contents[entry["filename"]]
    sha = hashlib.sha256(data).hexdigest()
    if (
        len(data) != entry["bytes"]
        or len(data) > MAX_FILE_BYTES
        or sha != entry["raw_sha256"]
        or entry["filename"] != entry["day"] + "-" + sha + ".nc"
        or entry["granule_id"]
        != digest({"source_url": request["source_url"], "raw_sha256": sha})
    ):
        raise ValueError("Hybrid raw byte/identity mismatch")
    with xr.open_dataset(io.BytesIO(data)) as ds:
        title = str(ds.attrs.get("title", ""))
        version = str(ds.attrs.get("product_version", ""))
        if (
            "MUR" not in title
            or "fv04.1" not in title
            or "nrt" in (version + title).lower()
            or (version and version not in {"04.1", "4.1"})
            or set(("time", "latitude", "longitude", *VARIABLES)) - set(ds.variables)
            or ds.analysed_sst.size > MAX_GRID_VALUES
            or ds.analysed_sst.attrs.get("units")
            not in {"degree_C", "degrees_C", "degree_Celsius", "degrees_Celsius", "K"}
        ):
            raise ValueError("Hybrid MUR product/generation/field mismatch")
        times = [np.datetime_as_string(t, unit="s") + "Z" for t in ds.time.values]
        if times != request["expected_times_utc"]:
            raise ValueError(
                "Hybrid actual timestamps mismatch; missing days remain explicit"
            )
        if any(ds[v].dims != ("time", "latitude", "longitude") for v in VARIABLES):
            raise ValueError("Hybrid MUR dimensions mismatch")
        lat, lat_step = _axis(ds, "latitude")
        lon, lon_step = _axis(ds, "longitude")
        expected_step = 0.01 * child["spatial_stride"]
        f = child["footprint"]
        if (
            not np.isclose(lat_step, expected_step, rtol=0.002, atol=1e-5)
            or not np.isclose(lon_step, expected_step, rtol=0.002, atol=1e-5)
            or abs(lat.min() - f["south"]) > 0.006
            or abs(lon.min() - f["west"]) > 0.006
            or not -0.006 <= f["north"] - lat.max() <= expected_step + 0.006
            or not -0.006 <= f["east"] - lon.max() <= expected_step + 0.006
        ):
            raise ValueError("Hybrid grid stride/coverage mismatch")
        finite = ((ds["mask"].values == 1) & np.isfinite(ds.analysed_sst.values)).sum(
            axis=(1, 2)
        )
    return {
        "role": child["role"],
        "location_id": child["location_id"],
        "spatial_operation": child["spatial_operation"],
        "days": request["days"],
        "finite_ocean_pixels": [int(n) for n in finite],
        "scientific_quality_threshold_applied": False,
        "scientific_approval": False,
    }


def _budget_total(budget):
    return sum(r[2] for r in budget["ranges"])


def _budget_add(budget, ordinal, size):
    # Consecutive acquisition checkpoints need only one compact range. This
    # avoids rewriting a growing multi-megabyte request map on every upload.
    rows = sorted([*budget["ranges"], [ordinal, ordinal, size]])
    merged = []
    for row in rows:
        if merged and merged[-1][1] + 1 == row[0]:
            merged[-1][1] = row[1]
            merged[-1][2] += row[2]
        else:
            merged.append(row.copy())
    budget["ranges"] = merged


def acquire_hybrid(
    plan,
    destination,
    work_root,
    *,
    store_factory=ArtifactStore,
    downloader=download_hybrid_request,
    max_requests=None,
    request_ids=None,
    roles=None,
    notify=lambda row: None,
    plan_validator=validate_hybrid_plan,
    child_planner=request_plan,
    raw_validator=validate_hybrid_raw,
):
    plan_validator(plan)
    raw_ceiling = plan["maximum_raw_bytes"]
    if not 1 <= raw_ceiling <= MAX_RAW_BYTES:
        raise ValueError("Invalid acquisition raw storage ceiling")
    if not destination.endswith("/" + plan["plan_sha256"]):
        raise ValueError("Hybrid destination binding mismatch")
    if max_requests is not None and (
        isinstance(max_requests, bool)
        or not isinstance(max_requests, int)
        or not 1 <= max_requests <= plan["request_count"]
    ):
        raise ValueError("Invalid hybrid request limit")
    selected = plan["requests"]
    if roles is not None:
        if (
            not roles
            or len(set(roles)) != len(roles)
            or set(roles) - {"context", "native_patch"}
        ):
            raise ValueError("Invalid hybrid role selection")
        selected = [r for r in selected if r["role"] in roles]
    if request_ids is not None:
        if (
            max_requests is not None
            or not 1 <= len(request_ids) <= 16
            or len(set(request_ids)) != len(request_ids)
        ):
            raise ValueError("Select at most 16 unique pilot requests")
        selected = [r for r in selected if r["request_sha256"] in request_ids]
        if len(selected) != len(request_ids):
            raise ValueError("Pilot request not in hybrid plan")
    selected = selected[:max_requests]
    work_root = Path(work_root)
    if any(p.is_symlink() for p in (work_root, *work_root.parents)):
        raise ValueError("Hybrid staging symlink forbidden")
    work_root.mkdir(parents=True, exist_ok=True)
    with worker_lease(destination, store_factory):
        budget_store = store_factory(destination + "/acquisition-control")
        budget_key = "operations/raw-budget.json"
        budget, budget_generation = budget_store.pointer(budget_key)
        ordinals = {r["request_sha256"]: i for i, r in enumerate(plan["requests"])}
        if budget is None:
            budget = {"history_plan_sha256": plan["plan_sha256"], "ranges": []}
        if "requests" in budget:
            # Compact the initial pilot ledger without losing its exact totals.
            old = budget["requests"]
            if (
                budget.get("history_plan_sha256") != plan["plan_sha256"]
                or not isinstance(old, dict)
                or set(old) - ordinals.keys()
                or sum(old.values()) > raw_ceiling
                or any(
                    isinstance(n, bool)
                    or not isinstance(n, int)
                    or not 1 <= n <= MAX_FILE_BYTES
                    for n in old.values()
                )
            ):
                raise ValueError("Hybrid cumulative raw budget binding mismatch")
            legacy = budget
            budget = {"history_plan_sha256": plan["plan_sha256"], "ranges": []}
            for identity, size in sorted(
                old.items(), key=lambda item: ordinals[item[0]]
            ):
                _budget_add(budget, ordinals[identity], size)
            budget_store.publish(
                "operations",
                digest(legacy),
                {"legacy-budget.json": canonical_bytes(legacy)},
                metadata={
                    "kind": "raw_budget_compaction",
                    "scientific_approval": False,
                },
            )
            budget_generation = budget_store.replace_pointer(
                budget_key, budget, budget_generation
            )
        ranges = budget.get("ranges")
        if (
            budget.get("history_plan_sha256") != plan["plan_sha256"]
            or not isinstance(ranges, list)
            or any(
                not isinstance(r, list)
                or len(r) != 3
                or any(isinstance(n, bool) or not isinstance(n, int) for n in r)
                or not 0 <= r[0] <= r[1] < plan["request_count"]
                or not r[1] - r[0] + 1 <= r[2] <= (r[1] - r[0] + 1) * MAX_FILE_BYTES
                for r in ranges
            )
            or any(a[1] + 1 >= b[0] for a, b in zip(ranges, ranges[1:]))
            or _budget_total(budget) > raw_ceiling
        ):
            raise ValueError("Hybrid cumulative raw budget binding mismatch")
        started = time.monotonic()
        rows = []
        counts = {"context_days": 0, "native_location_days": 0}
        raw_bytes = 0
        for descriptor in selected:
            child = child_planner(descriptor, plan["provider"])
            ordinal = ordinals[child["plan_sha256"]]
            accounted = any(a <= ordinal <= b for a, b, _ in budget["ranges"])
            store = store_factory(destination + "/requests/" + child["plan_sha256"])
            checkpoint, _ = store.pointer("operations/checkpoint.json")
            entries = store.entries("raw")
            if (checkpoint is not None or accounted) and not entries:
                raise ValueError("Hybrid checkpoint has no retained raw generation")
            if len(entries) > 1:
                raise ValueError(
                    "Multiple hybrid raw generations require operator selection"
                )
            resumed = bool(entries)
            if entries:
                receipt, contents = store.read(
                    "raw", next(iter(entries)), max_bytes=16 * 1024**2
                )
            else:
                with tempfile.TemporaryDirectory(
                    prefix="hybrid-mur-", dir=work_root
                ) as stage:
                    stage = Path(stage)
                    manifest = downloader(child, stage)
                    if manifest["status"] != "complete_unapproved_acquisition":
                        # Preserve a bounded journal before temporary staging is removed.
                        failure = {
                            "kind": "hybrid_request_failure",
                            "history_plan_sha256": plan["plan_sha256"],
                            "request_sha256": child["plan_sha256"],
                            "role": child["role"],
                            "scientific_approval": False,
                            "manifest": manifest,
                        }
                        failure_id = digest(failure)
                        store.publish(
                            "operations",
                            failure_id,
                            {
                                "failure.json": canonical_bytes(failure),
                                "journal.json": (stage / "journal.json").read_bytes(),
                            },
                            metadata={
                                "kind": "hybrid_request_failure",
                                "scientific_approval": False,
                            },
                        )
                        notify(
                            {
                                "event": "hybrid_request_failure",
                                "request_number": len(rows) + 1,
                                "request_sha256": child["plan_sha256"],
                                "failure_id": failure_id,
                                "outcomes": manifest.get("outcomes", {}),
                            }
                        )
                        raise ValueError(
                            "Incomplete hybrid request; failure journal and prior checkpoints retained"
                        )
                    contents = {
                        r["filename"]: (stage / r["filename"]).read_bytes()
                        for r in manifest["files"]
                    }
                    diagnostics = raw_validator(manifest, contents, child)
                    contents.update(
                        {
                            "acquisition.json": canonical_bytes(manifest),
                            "journal.json": (stage / "journal.json").read_bytes(),
                            "diagnostics.json": canonical_bytes(diagnostics),
                        }
                    )
                    used = manifest["files"][0]["bytes"]
                    if _budget_total(budget) + used > raw_ceiling:
                        raise ValueError("Hybrid raw storage cap reached")
                    identity = digest(
                        {"manifest": manifest, "diagnostics": diagnostics}
                    )
                    receipt = store.publish(
                        "raw",
                        identity,
                        contents,
                        metadata={
                            "history_plan_sha256": plan["plan_sha256"],
                            "role": child["role"],
                            "request_sha256": child["plan_sha256"],
                            "scientific_approval": False,
                        },
                    )
                    observed, verified = store.read(
                        "raw", identity, max_bytes=16 * 1024**2
                    )
                    if observed != receipt or verified != contents:
                        raise ValueError("Hybrid private storage round-trip mismatch")
            manifest = json.loads(contents["acquisition.json"])
            diagnostics = raw_validator(manifest, contents, child)
            if (
                receipt["metadata"]
                != {
                    "history_plan_sha256": plan["plan_sha256"],
                    "role": child["role"],
                    "request_sha256": child["plan_sha256"],
                    "scientific_approval": False,
                }
                or receipt["id"]
                != digest({"manifest": manifest, "diagnostics": diagnostics})
                or json.loads(contents["diagnostics.json"]) != diagnostics
            ):
                raise ValueError("Hybrid retained receipt binding mismatch")
            used = manifest["files"][0]["bytes"]
            if _budget_total(budget) + (0 if accounted else used) > raw_ceiling:
                raise ValueError("Hybrid retained raw storage cap reached")
            if not accounted:
                _budget_add(budget, ordinal, used)
                budget_generation = budget_store.replace_pointer(
                    budget_key, budget, budget_generation
                )
            if raw_bytes + used > _budget_total(budget):
                raise ValueError("Hybrid retained raw budget mismatch")
            row = {
                "history_plan_sha256": plan["plan_sha256"],
                "request_sha256": child["plan_sha256"],
                "artifact_id": receipt["id"],
                "receipt_sha256": digest(receipt),
                "role": child["role"],
                "days": len(descriptor["days"]),
                "raw_bytes": used,
            }
            if "processing_generation" in diagnostics:
                row["processing_generation"] = diagnostics["processing_generation"]
            if checkpoint is not None and checkpoint != row:
                raise ValueError("Hybrid checkpoint binding mismatch")
            if checkpoint is None:
                store.replace_pointer("operations/checkpoint.json", row, 0)
            rows.append(row)
            raw_bytes += used
            counts[
                "context_days" if child["role"] == "context" else "native_location_days"
            ] += row["days"]
            notify(
                {
                    "request_number": len(rows),
                    "request_count": plan["request_count"],
                    "raw_bytes": raw_bytes,
                    "resumed": resumed,
                    **counts,
                }
            )
            del contents
        complete = len(rows) == plan["request_count"]
        if complete and any(counts[k] != plan["expected"][k] for k in counts):
            raise ValueError("Hybrid terminal coverage reconciliation mismatch")
        report = {
            "algorithm": plan["algorithm"],
            "history_plan_sha256": plan["plan_sha256"],
            "status": "complete_unapproved_hybrid_acquisition"
            if complete
            else "bounded_partial_hybrid_acquisition",
            "scientific_approval": False,
            "database_access": False,
            "coarse_context_is_native_sample_evidence": False,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "raw_bytes": raw_bytes,
            "counts": counts,
            "expected": plan["expected"],
            "request_results": rows,
        }
        if roles is not None:
            report["selected_roles"] = sorted(roles)
            report["selected_role_counts_reconciled"] = all(
                counts[k] == plan["expected"][k]
                for role, k in (
                    ("context", "context_days"),
                    ("native_patch", "native_location_days"),
                )
                if role in roles
            )
        if plan.get("acquisition_scope") == "context_only":
            report.update(
                acquisition_scope="context_only",
                full_hybrid_acquisition_complete=False,
                native_patch_acquisition_pending=True,
                status="complete_unapproved_context_acquisition"
                if complete
                else "bounded_partial_context_acquisition",
                processing_generation_counts={
                    generation: sum(
                        r.get("processing_generation") == generation for r in rows
                    )
                    for generation in ("final", "interim")
                },
            )
        report_id = digest(report)
        store_factory(destination + "/acquisition-runs").publish(
            "operations",
            report_id,
            {"reconciliation.json": canonical_bytes(report)},
            metadata={
                "kind": "hybrid_raw_reconciliation",
                "scientific_approval": False,
            },
        )
        return {**report, "report_id": report_id}
