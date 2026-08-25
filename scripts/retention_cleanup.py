"""Review and execute chat retention cleanup.

The default mode is a read-only dry run. Execution requires an explicit
confirmation string so an accidental scheduled invocation cannot delete data.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from db.retention import cleanup_chat_interactions  # noqa: E402


CONFIRMATION = "DELETE EXPIRED CHAT DATA"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=config.CHAT_RETENTION_DAYS)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    if args.execute and args.confirm != CONFIRMATION:
        parser.error(f"--execute requires --confirm {CONFIRMATION!r}")

    report = cleanup_chat_interactions(
        retention_days=args.days,
        dry_run=not args.execute,
    )
    print(json.dumps({
        "cutoff": report.cutoff.isoformat(),
        "retention_days": report.retention_days,
        "eligible_count": report.eligible_count,
        "deleted_count": report.deleted_count,
        "dry_run": report.dry_run,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
