"""Qualify at most 16 NASA subsets selected from a hybrid preflight; dry-run default."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json
from ingestion.sst_acquisition import MAX_PLAN_BYTES, _read_json
from ingestion.sst_hybrid_acquisition import validate_hybrid_plan
from ingestion.sst_nasa_subset import (
    download_nasa_pilot,
    nasa_subset_plan,
    validate_nasa_pilot,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hybrid-plan", required=True, type=Path)
    parser.add_argument("--request-id", required=True, action="append")
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    hybrid = _read_json(args.hybrid_plan, MAX_PLAN_BYTES)
    validate_hybrid_plan(hybrid)
    if len(set(args.request_id)) != len(args.request_id):
        parser.error("duplicate hybrid request selection")
    selected = [r for r in hybrid["requests"] if r["request_sha256"] in args.request_id]
    if len(selected) != len(args.request_id):
        parser.error("request not in hybrid preflight")
    plan = nasa_subset_plan(
        [
            {
                "day": day,
                "role": r["role"],
                "footprint": r["footprint"],
                "location_id": r["location_id"],
            }
            for r in selected
            for day in r["days"]
        ]
    )
    if not args.execute:
        print(
            json.dumps(
                {
                    "nasa_plan_sha256": plan["plan_sha256"],
                    "hybrid_plan_sha256": hybrid["plan_sha256"],
                    "raw_file_requests": len(plan["requests"]),
                    "maximum_download_bytes": plan["maximum_download_bytes"],
                    "scientific_approval": False,
                    "cloud_writes": False,
                }
            )
        )
        return
    if args.credential_file is None:
        parser.error("execute requires a private local credential file")
    manifest = download_nasa_pilot(plan, args.directory, args.credential_file)
    contents = {
        r["filename"]: (args.directory / r["filename"]).read_bytes()
        for r in manifest["files"]
    }
    result = validate_nasa_pilot(manifest, contents, plan)
    result["hybrid_plan_sha256"] = hybrid["plan_sha256"]
    result["selected_hybrid_requests"] = args.request_id
    atomic_json(args.directory / "qualification.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
