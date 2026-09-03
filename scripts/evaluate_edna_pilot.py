#!/usr/bin/env python3
"""Check saved chat responses against registered evidence and human review."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evaluation.edna_pilot import evaluate_records
from api.provenance_snapshot_service import get_provenance_snapshot_service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "evaluation"
        / "edna_research_cases.json",
    )
    parser.add_argument("--max-latency-ms", type=int, default=120000)
    args = parser.parse_args()
    if (
        args.max_latency_ms <= 0
        or args.records.stat().st_size > 16 * 1024 * 1024
        or args.cases.stat().st_size > 1024 * 1024
    ):
        parser.error("Invalid latency bound or input file size limit exceeded")
    result = evaluate_records(
        json.loads(args.cases.read_bytes()),
        json.loads(args.records.read_bytes()),
        resolve_citation=get_provenance_snapshot_service().trace_payload,
        max_latency_ms=args.max_latency_ms,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
