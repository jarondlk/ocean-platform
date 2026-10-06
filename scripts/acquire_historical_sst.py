"""Preflight/resume bounded historical MUR batches; no cloud/scientific publication."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json, digest
from ingestion.sst_acquisition import (
    MAX_PLAN_BYTES,
    _read_json,
    acquisition_plan,
    build_history_plan,
    download_batch,
    mur_time_axis,
    mur_source_gap_inventory,
    validate_batch,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--inventory", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    axis = commands.add_parser("time-axis")
    axis.add_argument("--from-date", required=True)
    axis.add_argument("--to-date", required=True)
    axis.add_argument("--output-dir", type=Path, required=True)
    gaps = commands.add_parser("source-gap-check")
    gaps.add_argument("--day", action="append", required=True)
    gaps.add_argument("--output-dir", type=Path, required=True)
    run = commands.add_parser("batch")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument(
        "--batch-id", required=True, help="Exact child plan_sha256 from preflight"
    )
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--execute", action="store_true")
    run.add_argument(
        "--recheck",
        action="store_true",
        help="Fetch again, preserving changed generations",
    )
    args = parser.parse_args()
    if args.command == "preflight":
        plan = build_history_plan(_read_json(args.inventory, MAX_PLAN_BYTES))
        atomic_json(args.output, plan)
        print(
            f"Preflight {plan['plan_sha256']}: {plan['request_count']} requests in {plan['batch_count']} batches; maximum {plan['maximum_download_bytes']} bytes"
        )
    elif args.command in {"time-axis", "source-gap-check"}:
        report, data = (
            mur_time_axis(args.from_date, args.to_date)
            if args.command == "time-axis"
            else mur_source_gap_inventory(args.day)
        )
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (
            args.output_dir
            / (
                "time-axis.csv"
                if args.command == "time-axis"
                else "source-metadata.json"
            )
        ).write_bytes(data)
        atomic_json(args.output_dir / "receipt.json", report)
        if args.command == "time-axis":
            print(
                f"Mirror {report['available_dates']}/{report['expected_dates']} dates; gaps {report['missing_mirror_dates']}"
            )
        else:
            print(
                f"NASA catalogue matches: {len(report['granules'])}; unmatched dates: {report['dates_without_catalogue_match']}; binaries not downloaded"
            )
    else:
        plan = _read_json(args.plan, MAX_PLAN_BYTES)
        if plan.get("plan_sha256") != digest(
            {k: v for k, v in plan.items() if k != "plan_sha256"}
        ):
            raise ValueError("Historical preflight checksum mismatch")
        matches = [b for b in plan["batches"] if b["plan_sha256"] == args.batch_id]
        if len(matches) != 1:
            raise ValueError("Select exactly one existing bounded batch")
        child = validate_batch(
            acquisition_plan(matches[0]["days"], **matches[0]["footprint"])
        )
        if child["plan_sha256"] != args.batch_id:
            raise ValueError("Historical batch identity mismatch")
        if not args.execute:
            print(
                f"Batch {args.batch_id}: {len(child['requests'])} requests; maximum {child['maximum_download_bytes']} bytes; no downloads"
            )
            return
        result = download_batch(child, args.output_dir, recheck=args.recheck)
        print(
            f"{result['status']}: {result['outcomes']}; reconciliation {args.output_dir / 'reconciliation.json'}"
        )
        if result["status"] != "complete_unapproved_acquisition":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
