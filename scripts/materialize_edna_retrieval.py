#!/usr/bin/env python3
"""Plan or materialize retrieval documents for all active canonical eDNA rows."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from retrieval.edna_materializer import materialize_edna_retrieval  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize active eDNA retrieval documents"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Upsert PostgreSQL documents and publish local fallback artifacts.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    result = materialize_edna_retrieval(execute=args.execute)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"execute={str(args.execute).lower()}")
        print(f"documents={result['documents']}")
        if result["merge"]:
            for key, value in result["merge"].items():
                print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
