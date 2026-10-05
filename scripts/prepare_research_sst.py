"""Preflight or acquire a bounded NOAA MUR pilot; no approval or cloud publication."""

import argparse
from datetime import date
import math
from pathlib import Path
import sys
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json, digest
from ingestion.anemone_catalogue import file_sha256

HOST = "coastwatch.pfeg.noaa.gov"
ENDPOINT = f"https://{HOST}/erddap/griddap/jplMURSST41.nc"
MAX_FILE_BYTES = 8 * 1024 * 1024


def acquisition_plan(days, south, north, west, east):
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
        query = ",".join(
            v + constraints
            for v in ("analysed_sst", "analysis_error", "mask", "sea_ice_fraction")
        )
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
            or target.username
            or target.password
        ):
            raise ValueError("Pilot redirect outside the approved provider")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_pilot(plan, directory):
    if plan.get("plan_sha256") != digest(
        {k: v for k, v in plan.items() if k != "plan_sha256"}
    ):
        raise ValueError("Pilot preflight checksum mismatch")
    expected = acquisition_plan(
        [r["day"] for r in plan["requests"]], **plan["footprint"]
    )
    if expected != plan:
        raise ValueError("Pilot preflight does not match the bounded provider contract")
    # A fresh directory prevents partial runs or prior manifests being overwritten.
    directory.mkdir(parents=True, exist_ok=False)
    opener = build_opener(SameProviderRedirect())
    files = []
    for request in plan["requests"]:
        path = directory / request["filename"]
        with opener.open(request["source_url"], timeout=30) as response:
            data = response.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES or not (
            data.startswith(b"CDF") or data.startswith(b"\x89HDF\r\n\x1a\n")
        ):
            raise ValueError("Pilot response is oversized or not NetCDF")
        with path.open("xb") as handle:
            handle.write(data)
        raw_sha256 = file_sha256(path)
        files.append(
            {
                **request,
                "raw_sha256": raw_sha256,
                "granule_id": digest(
                    {"source_url": request["source_url"], "raw_sha256": raw_sha256}
                ),
                "bytes": len(data),
            }
        )
    manifest = {"status": "complete_unapproved_pilot", "plan": plan, "files": files}
    atomic_json(directory / "pilot.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", action="append", required=True)
    for name in ("south", "north", "west", "east"):
        parser.add_argument("--" + name, type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    plan = acquisition_plan(args.day, args.south, args.north, args.west, args.east)
    if args.execute:
        result = download_pilot(plan, args.output)
        print(
            f"Downloaded {len(result['files'])} unapproved pilot granules: {args.output}"
        )
    else:
        atomic_json(args.output, plan)
        print(
            f"Preflight {plan['plan_sha256']}: maximum {plan['maximum_download_bytes']} bytes; no cloud writes"
        )


if __name__ == "__main__":
    main()
