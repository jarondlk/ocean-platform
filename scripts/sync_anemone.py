#!/usr/bin/env python3
"""Inventory or acquire a bounded ANEMONE MiFish sample/run snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from ingestion.anemone import (  # noqa: E402
    AnemoneError,
    resolve_credentials,
    sync_anemone,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Securely inventory or acquire bounded ANEMONE MiFish data."
    )
    parser.add_argument("--scope-url", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--inventory",
        action="store_true",
        help="Inventory only; this is the default and downloads no source files.",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Download contracted interpreted TSV files into an immutable snapshot.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=config.RAW_ANEMONE_DIR,
    )
    parser.add_argument("--max-files", type=int, default=config.ANEMONE_MAX_FILES)
    parser.add_argument("--max-bytes", type=int, default=config.ANEMONE_MAX_BYTES)
    parser.add_argument(
        "--username-file",
        type=Path,
        default=config.ANEMONE_DOWNLOAD_USERNAME_FILE,
    )
    parser.add_argument(
        "--password-file",
        type=Path,
        default=config.ANEMONE_DOWNLOAD_PASSWORD_FILE,
    )
    args = parser.parse_args()
    if args.max_files < 1 or args.max_bytes < 1:
        parser.error("--max-files and --max-bytes must be positive")
    try:
        credentials = resolve_credentials(
            username_file=args.username_file,
            password_file=args.password_file,
        )
        result = sync_anemone(
            args.scope_url,
            credentials=credentials,
            execute=args.execute,
            output_root=args.output_root,
            max_files=args.max_files,
            max_bytes=args.max_bytes,
        )
    except AnemoneError as exc:
        print(
            json.dumps(
                {"status": "failed", "code": exc.code, "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
