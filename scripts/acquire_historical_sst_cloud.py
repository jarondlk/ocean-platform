"""Preflight/execute a private, capped historical MUR archive with byte-verified resume."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.immutable_bundle import atomic_json
from ingestion.sst_acquisition import MAX_PLAN_BYTES, _read_json
from ingestion.sst_cloud_acquisition import acquire_history, validate_history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude-day", action="append", default=[])
    parser.add_argument("--max-raw-gib", type=int, default=64, choices=range(1, 65))
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    plan = _read_json(args.plan, MAX_PLAN_BYTES)
    validate_history(plan)
    if not args.destination.endswith("/" + plan["plan_sha256"]):
        parser.error("destination must end with the exact history plan hash")
    if len(set(args.exclude_day)) != len(args.exclude_day):
        parser.error("duplicate excluded date")
    excluded = sum(
        len(set(row["days"]) & set(args.exclude_day)) for row in plan["batches"]
    )
    if not args.execute:
        print(
            json.dumps(
                {
                    "history_plan_sha256": plan["plan_sha256"],
                    "expected_requests": plan["request_count"],
                    "excluded_requests": excluded,
                    "maximum_raw_gib": args.max_raw_gib,
                    "batch_count": plan["batch_count"],
                    "maximum_batches": args.max_batches,
                    "destination": args.destination,
                    "cloud_writes": False,
                    "scientific_approval": False,
                }
            )
        )
        return
    result = acquire_history(
        plan,
        args.destination,
        args.work_root,
        excluded_days=args.exclude_day,
        max_raw_bytes=args.max_raw_gib * 1024**3,
        max_batches=args.max_batches,
        notify=lambda row: print(json.dumps(row), flush=True),
    )
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "status",
                    "report_id",
                    "files",
                    "raw_bytes",
                    "excluded_request_count",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
