#!/usr/bin/env python3
"""Prepare a full, isolated ANEMONE candidate from a verified source archive."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.anemone_catalogue import prepare_catalogue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()
    result = prepare_catalogue(
        args.archive,
        args.work_dir,
        batch_size=args.batch_size,
        progress=lambda item: print(json.dumps(item), flush=True),
    )
    print(json.dumps({k: v for k, v in result.items() if k != "units"}, indent=2))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
