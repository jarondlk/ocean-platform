#!/usr/bin/env python3
"""Validate or publish canonical artifacts from one completed ANEMONE snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from preprocessing.anemone import (  # noqa: E402
    AnemoneNormalizationError,
    normalize_anemone_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize one completed ANEMONE MiFish snapshot."
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Publish an immutable normalized bundle; default is validation only.",
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Activate the published bundle for later database loading.",
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=config.RAW_ANEMONE_DIR,
    )
    parser.add_argument(
        "--normalized-root",
        type=Path,
        default=config.ANEMONE_NORMALIZED_DIR,
    )
    args = parser.parse_args()
    try:
        result = normalize_anemone_snapshot(
            args.snapshot_id,
            execute=args.execute,
            activate=args.activate,
            raw_root=args.raw_root,
            normalized_root=args.normalized_root,
        )
    except AnemoneNormalizationError as exc:
        print(
            json.dumps(
                {"status": "failed", "code": exc.code, "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
