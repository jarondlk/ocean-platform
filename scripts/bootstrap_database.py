#!/usr/bin/env python3
"""Create or upgrade every database object required by the application."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_engine, init_db  # noqa: E402


REQUIRED_TABLES = frozenset(
    {
        "app_user",
        "user_invitation",
        "chat_interaction",
        "chat_feedback",
        "audit_event",
        "rate_limit_bucket",
        "provenance_record",
        "anchor_event",
        "ctd_profile",
        "ctd_summary",
        "metagenome_sample",
        "external_source_snapshot",
        "external_source_file",
        "edna_sample",
        "edna_assay",
        "edna_detection",
        "edna_internal_standard",
        "sst_point_observation",
        "sst_daily_summary",
        "retrieval_document",
        "cross_source_link",
        "corpus_publication",
    }
)


def database_status() -> dict[str, object]:
    engine = get_engine()
    tables = set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        vector_installed = bool(
            connection.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                    ")"
                )
            ).scalar()
        )
    missing_tables = sorted(REQUIRED_TABLES - tables)
    return {
        "ready": vector_installed and not missing_tables,
        "vector_extension": vector_installed,
        "missing_tables": missing_tables,
        "table_count": len(tables),
    }


def bootstrap_database() -> dict[str, object]:
    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(alembic_config, "head")
    init_db()
    return database_status()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or validate the complete PostgreSQL/pgvector schema"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate without applying migrations or creating tables.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    status = database_status() if args.check_only else bootstrap_database()
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(f"ready={str(status['ready']).lower()}")
        print(f"vector_extension={str(status['vector_extension']).lower()}")
        print(f"missing_tables={','.join(status['missing_tables'])}")
        print(f"table_count={status['table_count']}")
    return 0 if status["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
