"""Preflight/acquire NASA daily regional context only; never publish scientific evidence."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json, canonical_bytes
from ingestion.sst_acquisition import MAX_PLAN_BYTES, _read_json
from ingestion.sst_nasa_context import (
    acquire_nasa_context,
    build_nasa_context_plan,
    validate_nasa_context_plan,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--inventory", required=True, type=Path)
    preflight.add_argument("--output", required=True, type=Path)
    run = commands.add_parser("acquire")
    run.add_argument("--plan", required=True, type=Path)
    run.add_argument("--destination", required=True)
    run.add_argument("--work-root", required=True, type=Path)
    run.add_argument("--credential-file", type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--max-requests", type=int)
    run.add_argument("--request-id", action="append")
    run.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.command == "preflight":
        plan = build_nasa_context_plan(_read_json(args.inventory, MAX_PLAN_BYTES))
        if len(canonical_bytes(plan)) > MAX_PLAN_BYTES:
            parser.error("NASA context plan exceeds byte bound")
        atomic_json(args.output, plan)
    else:
        plan = _read_json(args.plan, MAX_PLAN_BYTES)
        validate_nasa_context_plan(plan)
        if not args.destination.endswith("/" + plan["plan_sha256"]):
            parser.error("destination must end with exact context plan hash")
        if args.request_id and args.max_requests is not None:
            parser.error("choose request IDs or a prefix limit")
        if args.execute:
            if args.credential_file is None:
                parser.error("execute requires an owned private local credential file")
            result = acquire_nasa_context(
                plan,
                args.destination,
                args.work_root,
                args.credential_file,
                max_requests=args.max_requests,
                request_ids=args.request_id,
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
                            "raw_bytes",
                            "counts",
                            "processing_generation_counts",
                            "full_hybrid_acquisition_complete",
                        )
                    }
                )
            )
            return
    print(
        json.dumps(
            {
                "context_plan_sha256": plan["plan_sha256"],
                "request_count": plan["request_count"],
                "estimated_raw_bytes": plan["estimated_raw_bytes"],
                "maximum_raw_bytes": plan["maximum_raw_bytes"],
                "scientific_approval": False,
                "native_patch_acquisition_pending": True,
                "cloud_writes": False,
            }
        )
    )


if __name__ == "__main__":
    main()
