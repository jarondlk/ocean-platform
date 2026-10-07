"""Preflight/acquire private hybrid MUR data; dry-run by default, never publish Chat."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json, canonical_bytes
from ingestion.sst_acquisition import MAX_PLAN_BYTES, _read_json
from ingestion.sst_hybrid_acquisition import (
    PROVIDERS,
    acquire_hybrid,
    build_hybrid_plan,
    validate_hybrid_plan,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--inventory", required=True, type=Path)
    preflight.add_argument("--provider", choices=PROVIDERS, default="noaa_coastwatch")
    preflight.add_argument("--output", required=True, type=Path)
    run = commands.add_parser("acquire")
    run.add_argument("--plan", required=True, type=Path)
    run.add_argument("--destination", required=True)
    run.add_argument("--work-root", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--max-requests", type=int)
    run.add_argument(
        "--role",
        choices=("context", "native_patch"),
        action="append",
        help="Acquire only the selected role; does not complete the combined archive",
    )
    run.add_argument(
        "--request-id", action="append", help="Select at most 16 exact pilot requests"
    )
    run.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.command == "preflight":
        plan = build_hybrid_plan(
            _read_json(args.inventory, MAX_PLAN_BYTES), provider=args.provider
        )
        if len(canonical_bytes(plan)) > MAX_PLAN_BYTES:
            parser.error("hybrid preflight exceeds plan byte bound")
        atomic_json(args.output, plan)
    else:
        plan = _read_json(args.plan, MAX_PLAN_BYTES)
        validate_hybrid_plan(plan)
        if not args.destination.endswith("/" + plan["plan_sha256"]):
            parser.error("destination must end with exact hybrid plan hash")
        if args.request_id and args.max_requests is not None:
            parser.error("choose request IDs or a prefix limit")
        if args.execute:
            result = acquire_hybrid(
                plan,
                args.destination,
                args.work_root,
                max_requests=args.max_requests,
                request_ids=args.request_id,
                roles=args.role,
                notify=lambda row: print(json.dumps(row), flush=True),
            )
            atomic_json(args.output, result)
            print(
                json.dumps(
                    {
                        k: result[k]
                        for k in ("status", "report_id", "raw_bytes", "counts")
                    }
                )
            )
            return
    print(
        json.dumps(
            {
                "history_plan_sha256": plan["plan_sha256"],
                "provider": plan["provider"],
                "request_count": plan["request_count"],
                "estimated_raw_bytes": plan["estimated_raw_bytes"],
                "maximum_raw_bytes": plan["maximum_raw_bytes"],
                "expected": plan["expected"],
                "scientific_approval": False,
                "cloud_writes": False,
            }
        )
    )


if __name__ == "__main__":
    main()
