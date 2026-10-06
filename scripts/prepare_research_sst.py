"""Preflight or acquire a bounded NOAA MUR pilot; no approval or cloud publication."""

import argparse
from pathlib import Path
import sys
from urllib.request import build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json, digest
from ingestion.anemone_catalogue import file_sha256

# Re-export the established pilot contract for existing callers and receipts.
from ingestion.sst_acquisition import (
    ENDPOINT as ENDPOINT,
    HOST as HOST,
    MAX_FILE_BYTES,
    SameProviderRedirect,
    acquisition_plan,
)


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
