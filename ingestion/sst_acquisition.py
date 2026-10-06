"""Bounded, resumable operator acquisition. Never approve or publish SST data."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

from ingestion.anemone_catalogue import file_sha256
from ingestion.immutable_bundle import atomic_json, digest, validate_id

HOST = "coastwatch.pfeg.noaa.gov"
ENDPOINT = f"https://{HOST}/erddap/griddap/jplMURSST41.nc"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PLAN_BYTES = 64 * 1024 * 1024
MAX_REQUESTS = 250_000
MAX_BATCH_DAYS = 12  # <=96 MiB raw upper bound, leaving room in a 128 MiB panel.
VARIABLES = ("analysed_sst", "analysis_error", "mask", "sea_ice_fraction")


def acquisition_plan(days, south, north, west, east):
    """Preserve the version-one pilot wire contract for existing operators."""
    days = sorted({date.fromisoformat(day).isoformat() for day in days})
    bounds = (south, north, west, east)
    if not all(math.isfinite(v) for v in bounds) or not (
        1 <= len(days) <= 32
        and -89.9 <= south < north <= 89.9
        and -179.9 <= west < east <= 179.9
        and north - south <= 2
        and east - west <= 2
    ):
        raise ValueError(
            "Pilot requires 1–32 days and a bounded footprint ≤2° per axis"
        )
    if any(not "2002-06-01" <= day <= date.today().isoformat() for day in days):
        raise ValueError("Pilot dates are outside the daily MUR product interval")
    requests = []
    for day in days:
        stamp = day + "T09:00:00Z"
        constraints = (
            f"[({stamp})][({south:.6f}):1:({north:.6f})][({west:.6f}):1:({east:.6f})]"
        )
        query = ",".join(v + constraints for v in VARIABLES)
        requests.append(
            {
                "day": day,
                "expected_time_utc": stamp,
                "filename": day + ".nc",
                "source_url": ENDPOINT + "?" + quote(query, safe="(),:"),
            }
        )
    plan = {
        "schema_version": 1,
        "product_id": "mur_l4_foundation_sst",
        "measurement_type": "satellite_in_situ_analysis",
        "status": "unapproved_pilot",
        "footprint": dict(zip(("south", "north", "west", "east"), bounds)),
        "maximum_download_bytes": len(days) * MAX_FILE_BYTES,
        "estimated_uncompressed_grid_bytes": len(days)
        * (math.ceil((north - south) / 0.01) + 2)
        * (math.ceil((east - west) / 0.01) + 2)
        * 25,
        "cloud_writes": False,
        "requests": requests,
    }
    return {**plan, "plan_sha256": digest(plan)}


class SameProviderRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if (
            target.scheme != "https"
            or target.hostname != HOST
            or target.port not in (None, 443)
            or target.username
            or target.password
        ):
            raise ValueError("Pilot redirect outside the approved provider")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_batch(plan):
    if plan != acquisition_plan(
        [r["day"] for r in plan["requests"]], **plan["footprint"]
    ):
        raise ValueError(
            "Acquisition preflight does not match the bounded provider contract"
        )
    return plan


def build_history_plan(inventory):
    if inventory.get("inventory_id") != digest(
        {k: v for k, v in inventory.items() if k != "inventory_id"}
    ):
        raise ValueError("Acquisition inventory checksum mismatch")
    years = inventory["sampling_years"]
    if (
        not years
        or years != sorted(set(years))
        or len(years) > 10
        or any(
            isinstance(y, bool)
            or not isinstance(y, int)
            or y < 2003
            or y >= date.today().year
            for y in years
        )
    ):
        raise ValueError(
            "Historical preflight requires 1–10 complete calendar years after 2002"
        )
    tiles = inventory["tiles"]
    if not 1 <= len(tiles) <= 1000:
        raise ValueError(
            "Historical acquisition requires 1–1000 reported-coordinate tiles"
        )
    batches, seen, total = [], set(), 0
    for tile in sorted(tiles, key=lambda row: row["tile_id"]):
        if tile["tile_id"] != digest(tile["footprint"]) or tile["tile_id"] in seen:
            raise ValueError("Invalid or duplicate acquisition tile")
        seen.add(tile["tile_id"])
        for year in years:
            for month in range(1, 13):
                start = date(year, month, 1)
                end = date(year + (month == 12), month % 12 + 1, 1)
                days = [
                    (start + timedelta(days=i)).isoformat()
                    for i in range((end - start).days)
                ]
                for offset in range(0, len(days), MAX_BATCH_DAYS):
                    child = acquisition_plan(
                        days[offset : offset + MAX_BATCH_DAYS], **tile["footprint"]
                    )
                    # URLs are deterministic and regenerated for one batch at
                    # execution; do not expand 191,700 URLs into the root plan.
                    batches.append(
                        {
                            "tile_id": tile["tile_id"],
                            "month": start.strftime("%Y-%m"),
                            "days": [r["day"] for r in child["requests"]],
                            "footprint": child["footprint"],
                            "plan_sha256": child["plan_sha256"],
                            "maximum_download_bytes": child["maximum_download_bytes"],
                            "estimated_uncompressed_grid_bytes": child[
                                "estimated_uncompressed_grid_bytes"
                            ],
                        }
                    )
                    total += len(child["requests"])
                    if total > MAX_REQUESTS:
                        raise ValueError(
                            "Historical acquisition request limit exceeded; split the inventory explicitly"
                        )
    result = {
        "schema_version": 1,
        "kind": "historical_mur_acquisition",
        "status": "unapproved_preflight",
        "inventory_id": inventory["inventory_id"],
        "sampling_years": years,
        "scientific_publication": False,
        "cloud_writes": False,
        "request_count": total,
        "batch_count": len(batches),
        "maximum_download_bytes": total * MAX_FILE_BYTES,
        "estimated_uncompressed_grid_bytes": sum(
            b["estimated_uncompressed_grid_bytes"] for b in batches
        ),
        "batches": batches,
    }
    if len(json.dumps(result).encode()) > MAX_PLAN_BYTES:
        raise ValueError("Historical preflight byte limit exceeded")
    return {**result, "plan_sha256": digest(result)}


def _read_json(path, limit=2 * 1024 * 1024):
    if path.is_symlink():
        raise ValueError("Acquisition symlink is forbidden")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Acquisition JSON byte limit exceeded")
    return json.loads(data)


def _netcdf(path):
    with path.open("rb") as handle:
        magic = handle.read(8)
    return (
        magic[:4] in (b"CDF\x01", b"CDF\x02", b"CDF\x05")
        or magic == b"\x89HDF\r\n\x1a\n"
    )


def _verified(directory, entry):
    sha = validate_id(entry["raw_sha256"])
    filename = entry["day"] + "-" + sha + ".nc"
    path = directory / filename
    return (
        entry.get("filename") == filename
        and not path.is_symlink()
        and path.is_file()
        and 8 <= entry["bytes"] <= MAX_FILE_BYTES
        and path.stat().st_size == entry["bytes"]
        and file_sha256(path) == sha
        and _netcdf(path)
        and entry["granule_id"]
        == digest({"source_url": entry["source_url"], "raw_sha256": sha})
    )


def _retry_delay(error, attempt):
    # Excessive Retry-After is deferred to a later operator run, never ignored.
    raw = (
        error.headers.get("Retry-After")
        if isinstance(error, HTTPError) and error.headers
        else None
    )
    if raw:
        try:
            seconds = float(raw)
        except ValueError:
            try:
                seconds = (
                    parsedate_to_datetime(raw) - datetime.now(timezone.utc)
                ).total_seconds()
            except (TypeError, ValueError):
                seconds = 2**attempt
        if math.isfinite(seconds):
            return max(0, seconds)
    return min(30, 2**attempt)


def download_batch(
    plan, directory, *, attempts=3, recheck=False, opener=None, sleep=time.sleep
):
    """Resume a pilot-sized batch with atomic generations and an explicit journal.

    A complete acquisition means all requested raw containers were received.
    NetCDF scientific identity/time/quality validation remains a separate gate.
    """
    validate_batch(plan)
    if (
        isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or not 1 <= attempts <= 5
    ):
        raise ValueError("Acquisition attempts must be between one and five")
    if directory.is_symlink():
        raise ValueError("Acquisition symlink is forbidden")
    directory.mkdir(parents=True, exist_ok=True)
    directory = directory.resolve()
    lock = directory / ".acquisition.lock"
    # An interrupted process leaves a reviewable lock; operator removes it only
    # after checking no active process owns this batch. Never race another writer.
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(str(os.getpid()))
    try:
        return _download_locked(plan, directory, attempts, recheck, opener, sleep)
    finally:
        lock.unlink()


def _download_locked(plan, directory, attempts, recheck, opener, sleep):
    journal_path = directory / "journal.json"
    journal = (
        _read_json(journal_path)
        if journal_path.exists()
        else {"schema_version": 1, "plan_sha256": plan["plan_sha256"], "requests": {}}
    )
    if (
        journal.get("plan_sha256") != plan["plan_sha256"]
        or journal.get("schema_version") != 1
        or not isinstance(journal.get("requests"), dict)
    ):
        raise ValueError("Acquisition journal belongs to a different plan")
    requests = {digest(request): request for request in plan["requests"]}
    if set(journal["requests"]) - requests.keys():
        raise ValueError("Unexpected request in acquisition journal")
    completed = directory / "acquisition.json"
    if completed.is_symlink() or journal_path.is_symlink():
        raise ValueError("Acquisition symlink is forbidden")
    # Revalidation or a new generation invalidates the old current receipt.
    completed.unlink(missing_ok=True)
    opener = opener or build_opener(SameProviderRedirect())
    for identity, request in requests.items():
        state = journal["requests"].get(
            identity, {"status": "pending", "generations": []}
        )
        for entry in state["generations"]:
            if any(
                entry.get(k) != request[k]
                for k in ("day", "source_url", "expected_time_utc")
            ):
                raise ValueError("Acquisition journal request identity mismatch")
        latest = state["generations"][-1] if state["generations"] else None
        if latest and not _verified(directory, latest):
            state["status"] = "local_integrity_failure"
            journal["requests"][identity] = state
            atomic_json(journal_path, journal)
            continue  # Do not overwrite a damaged immutable generation.
        if latest and not recheck and state["status"] == "acquired":
            continue
        state["status"] = "in_progress"
        journal["requests"][identity] = state
        atomic_json(journal_path, journal)
        for attempt in range(attempts):
            temporary = None
            try:
                with opener.open(request["source_url"], timeout=30) as response:
                    fd, name = tempfile.mkstemp(prefix=".download-", dir=directory)
                    temporary = Path(name)
                    used = 0
                    with os.fdopen(fd, "wb") as handle:
                        while chunk := response.read(
                            min(65536, MAX_FILE_BYTES + 1 - used)
                        ):
                            used += len(chunk)
                            if used > MAX_FILE_BYTES:
                                raise ValueError("oversized")
                            handle.write(chunk)
                        handle.flush()
                        os.fsync(handle.fileno())
                    headers = getattr(response, "headers", {})
                    declared = headers.get("Content-Length")
                    if declared and int(declared) != used:
                        raise OSError("Truncated provider response")
                    if not _netcdf(temporary):
                        raise ValueError("invalid_netcdf")
                    sha = file_sha256(temporary)
                    filename = request["day"] + "-" + sha + ".nc"
                    target = directory / filename
                    if target.exists() or target.is_symlink():
                        if target.is_symlink() or file_sha256(target) != sha:
                            raise ValueError("local_integrity_failure")
                        temporary.unlink()
                    else:
                        temporary.replace(target)
                    entry = {
                        **request,
                        "filename": filename,
                        "raw_sha256": sha,
                        "bytes": used,
                        "granule_id": digest(
                            {"source_url": request["source_url"], "raw_sha256": sha}
                        ),
                        "acquired_at": datetime.now(timezone.utc).isoformat(),
                        "provider_etag": headers.get("ETag"),
                        "provider_last_modified": headers.get("Last-Modified"),
                    }
                    if latest is None or latest["raw_sha256"] != sha:
                        if len(state["generations"]) >= 100:
                            raise ValueError("generation_limit_exceeded")
                        state["generations"].append(entry)
                    state.update(status="acquired", last_error=None)
                    break
            except HTTPError as error:
                state["http_status"] = error.code
                state["status"] = (
                    "provider_missing"
                    if error.code in (404, 410)
                    else (
                        "access_denied"
                        if error.code in (401, 403)
                        else "retryable"
                        if error.code in (408, 429) or error.code >= 500
                        else "provider_rejected"
                    )
                )
                state["last_error"] = state["status"]
                delay = _retry_delay(error, attempt)
                error.close()
                if (
                    state["status"] != "retryable"
                    or attempt == attempts - 1
                    or delay > 30
                ):
                    break
                sleep(delay)
            except (URLError, OSError, TimeoutError) as error:
                # Only record exception type: URLs or credential-bearing text
                # from provider/transport exceptions must not enter receipts.
                state.update(status="retryable", last_error=type(error).__name__)
                if attempt == attempts - 1:
                    break
                sleep(2**attempt)
            except ValueError as error:
                reason = str(error)
                safe_reason = (
                    reason
                    if reason
                    in {
                        "oversized",
                        "invalid_netcdf",
                        "local_integrity_failure",
                        "generation_limit_exceeded",
                    }
                    else type(error).__name__
                )
                state.update(
                    status="oversized" if reason == "oversized" else "invalid_response",
                    last_error=safe_reason,
                )
                break
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        atomic_json(journal_path, journal)
    states = Counter(state["status"] for state in journal["requests"].values())
    files = [
        journal["requests"][key]["generations"][-1]
        for key in requests
        if journal["requests"][key]["status"] == "acquired"
    ]
    manifest = {
        "schema_version": 1,
        "status": "complete_unapproved_acquisition"
        if len(files) == len(requests)
        else "incomplete_unapproved_acquisition",
        "scientific_validation": "pending",
        "plan": plan,
        "files": files,
        "outcomes": dict(sorted(states.items())),
        "journal_sha256": digest(journal),
    }
    atomic_json(directory / "reconciliation.json", manifest)
    if len(files) == len(requests):
        atomic_json(completed, manifest)
    return manifest


def mur_time_axis(start, end, *, opener=None):
    """A bounded public mirror inventory, not evidence of source-archive absence."""
    import csv
    import io

    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if (
        not date(2002, 6, 1) <= start <= end <= date.today()
        or (end - start).days > 3660
    ):
        raise ValueError(
            "MUR time inventory requires an ordered interval of at most ten years"
        )
    query = f"time[({start}T09:00:00Z):1:({end}T09:00:00Z)]"
    url = ENDPOINT.removesuffix(".nc") + ".csv?" + quote(query, safe="(),:")
    opener = opener or build_opener(SameProviderRedirect())
    with opener.open(url, timeout=30) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("MUR time inventory byte limit exceeded")
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    if rows[:2] != [["time"], ["UTC"]]:
        raise ValueError("Unexpected MUR time inventory format")
    stamps = [row[0] for row in rows[2:] if len(row) == 1]
    if len(stamps) != len(rows) - 2 or len(stamps) != len(set(stamps)):
        raise ValueError("Duplicate or malformed MUR timestamps")
    expected = {
        (start + timedelta(days=i)).isoformat() + "T09:00:00Z"
        for i in range((end - start).days + 1)
    }
    if set(stamps) - expected:
        raise ValueError("MUR timestamps do not match the expected analysis time")
    report = {
        "schema_version": 1,
        "product_id": "mur_l4_foundation_sst",
        "source_url": url,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "expected_dates": len(expected),
        "available_dates": len(stamps),
        "missing_mirror_dates": sorted(s[:10] for s in expected - set(stamps)),
        "response_sha256": hashlib.sha256(data).hexdigest(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "absence_basis": "mirror_only_source_archive_not_checked",
    }
    return report, data


def mur_source_gap_inventory(days, *, open_url=None):
    """Check the official NASA metadata catalogue; never fetch protected binaries."""
    from urllib.parse import urlencode
    from urllib.request import urlopen

    days = sorted({date.fromisoformat(day).isoformat() for day in days})
    if (
        not days
        or len(days) > 32
        or (date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days > 31
        or days[0] < "2002-06-01"
        or days[-1] > date.today().isoformat()
    ):
        raise ValueError(
            "NASA gap inventory requires at most 32 adjacent historical dates"
        )
    end = date.fromisoformat(days[-1]) + timedelta(days=1)
    query = urlencode(
        {
            "short_name": "MUR-JPL-L4-GLOB-v4.1",
            "temporal": f"{days[0]}T00:00:00Z,{end}T00:00:00Z",
            "page_size": 200,
        }
    )
    url = "https://cmr.earthdata.nasa.gov/search/granules.json?" + query
    with (open_url or urlopen)(url, timeout=30) as response:
        data = response.read(2 * 1024 * 1024 + 1)
        hits = response.headers.get("CMR-Hits")
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("NASA gap inventory byte limit exceeded")
    entries = json.loads(data)["feed"]["entry"]
    if hits is None or int(hits) != len(entries) or len(entries) > 200:
        raise ValueError("NASA catalogue response is incomplete")
    expected = {
        day.replace("-", "") + "090000-JPL-L4_GHRSST-SSTfnd-MUR-GLOB-v02.0-fv04.1": day
        for day in days
    }
    granules = []
    for entry in entries:
        title = entry["title"]
        if title not in expected:
            continue
        urls = []
        for link in entry.get("links", []):
            href = link.get("href", "")
            target = urlsplit(href)
            if (
                target.scheme == "https"
                and target.hostname == "archive.podaac.earthdata.nasa.gov"
                and target.port in (None, 443)
                and not target.username
                and not target.password
                and not target.query
                and not target.fragment
                and target.path.endswith("/" + title + ".nc")
            ):
                urls.append(href)
        granules.append(
            {
                "day": expected[title],
                "concept_id": entry["id"],
                "title": title,
                "time_start": entry.get("time_start"),
                "time_end": entry.get("time_end"),
                "binary_urls": sorted(set(urls)),
                "binary_verified": False,
            }
        )
    found = {g["day"] for g in granules}
    return {
        "schema_version": 1,
        "product_id": "mur_l4_foundation_sst",
        "source_url": url,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "response_sha256": hashlib.sha256(data).hexdigest(),
        "requested_days": days,
        "granules": sorted(granules, key=lambda g: (g["day"], g["concept_id"])),
        "dates_without_catalogue_match": sorted(set(days) - found),
        "basis": "source_archive_metadata_only_binary_not_downloaded",
    }, data
