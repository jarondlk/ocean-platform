"""Verify a retained canonical candidate and write a read-only research census."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json
from ingestion.research_readiness import build_readiness, read_candidate_metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, provenance = read_candidate_metadata(args.candidate_root)
    report = build_readiness(source, provenance)
    atomic_json(args.output, report)
    print(
        f"Readiness {report['report_id']}: {report['counts']['source_occurrences']} source occurrences; "
        f"{len(report['case_dispositions'])} data-blocked cases. Report: {args.output}"
    )


if __name__ == "__main__":
    main()
