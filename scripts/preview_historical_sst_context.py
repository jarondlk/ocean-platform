"""Inspect verified regional SST context locally; no DB, provider or publication."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json
from ingestion.sst_acquisition import MAX_PLAN_BYTES, _read_json
from preprocessing.sst_context_review import build_context_diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-plan", required=True, type=Path)
    parser.add_argument("--reconciliation", required=True, type=Path)
    parser.add_argument("--staging-receipt", required=True, type=Path)
    parser.add_argument(
        "--bounds", type=Path, help="Optional unreviewed rectangle JSON"
    )
    parser.add_argument(
        "--proposed-quality",
        type=Path,
        help="Optional explicit draft QC/weighting JSON; never publication",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    # Do not overwrite inputs or allow an output path through a symlink.
    output = args.output.absolute()
    inputs = [
        args.context_plan,
        args.reconciliation,
        args.staging_receipt,
        args.bounds,
        args.proposed_quality,
    ]
    if any(p.is_symlink() for p in (output, *output.parents)) or any(
        p and output.resolve() == p.resolve() for p in inputs
    ):
        parser.error("output must be a separate non-symlink local path")
    plan = _read_json(args.context_plan, MAX_PLAN_BYTES)
    report = _read_json(args.reconciliation, 4 * 1024**2)
    staging = _read_json(args.staging_receipt, 64 * 1024)
    package = Path(staging["package_path"])
    output = output.resolve()
    if output == package or package in output.parents:
        parser.error("output cannot modify the sealed review package")
    result = build_context_diagnostics(
        plan,
        report.get("result", report),
        staging,
        bounds=_read_json(args.bounds, 4096) if args.bounds else None,
        proposed_quality=_read_json(args.proposed_quality, 4096)
        if args.proposed_quality
        else None,
    )
    atomic_json(output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "diagnostics_id": result["diagnostics_id"],
                "final_days": len(result["daily"]),
                "scientific_publication": False,
            }
        )
    )


if __name__ == "__main__":
    main()
