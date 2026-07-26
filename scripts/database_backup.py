#!/usr/bin/env python3
"""Create, verify, and restore-test PostgreSQL backups."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from db.backup import (  # noqa: E402
    BackupError,
    create_backup,
    restore_test,
    verify_backup,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and verify recoverable PostgreSQL custom archives"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create an atomic verified backup")
    create.add_argument(
        "--output-dir",
        type=Path,
        default=config.DATABASE_BACKUP_DIR,
    )
    create.add_argument("--label", default="manual")
    create.add_argument("--container")
    create.add_argument(
        "--restore-test",
        action="store_true",
        help="Restore into a temporary isolated database and compare row counts.",
    )

    verify = subparsers.add_parser("verify", help="Verify archive structure and digest")
    verify.add_argument("archive", type=Path)
    verify.add_argument("--container")

    restore = subparsers.add_parser(
        "restore-test",
        help="Restore into a disposable database, compare row counts, and remove it",
    )
    restore.add_argument("archive", type=Path)
    restore.add_argument("--container")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "create":
            result = create_backup(
                output_dir=args.output_dir,
                label=args.label,
                container=args.container,
            )
            payload = asdict(result)
            if args.restore_test:
                payload["restore_test"] = restore_test(
                    Path(result.archive_path),
                    container=args.container,
                )
        elif args.command == "verify":
            payload = verify_backup(args.archive, container=args.container)
        else:
            payload = restore_test(args.archive, container=args.container)
    except BackupError as exc:
        print(f"backup_error={exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
