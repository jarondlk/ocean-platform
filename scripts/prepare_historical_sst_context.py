"""Plan or locally stage verified final context files; no scientific publication."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json
from ingestion.sst_acquisition import MAX_PLAN_BYTES, _read_json
from ingestion.sst_context_integration import (
    build_context_integration_plan,
    stage_context_batch,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-plan", required=True, type=Path)
    parser.add_argument("--reconciliation", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--archive-uri")
    parser.add_argument("--batch-id")
    parser.add_argument("--staging-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    plan = _read_json(args.context_plan, MAX_PLAN_BYTES)
    report = _read_json(args.reconciliation, 4 * 1024**2)
    report = report.get("result", report)
    integration = build_context_integration_plan(plan, report)
    if args.execute:
        if not all((args.archive_uri, args.batch_id, args.staging_root)):
            parser.error(
                "execute requires archive URI, exact batch ID and local staging root"
            )
        result = stage_context_batch(
            plan,
            report,
            integration,
            args.archive_uri,
            args.batch_id,
            args.staging_root,
        )
    else:
        result = integration
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "status",
                    "integration_plan_id",
                    "batch_id",
                    "selected_final_days",
                    "final_days",
                    "raw_bytes",
                    "scientific_approval",
                    "scientific_publication",
                )
                if k in result
            }
        )
    )


if __name__ == "__main__":
    main()
