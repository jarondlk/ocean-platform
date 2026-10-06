#!/usr/bin/env python3
"""Create or upgrade every database object required by the application."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_engine, init_db  # noqa: E402
from db.app_models import AppBase  # noqa: E402
from db.models import CorpusBase  # noqa: E402


# Use both maintained model registries so new application tables cannot silently
# fall outside the deployment readiness boundary.
REQUIRED_TABLES = (
    frozenset(AppBase.metadata.tables) | frozenset(CorpusBase.metadata.tables)
)


def migration_status(connection) -> dict[str, object]:
    configuration = Config(str(PROJECT_ROOT / "alembic.ini"))
    expected = sorted(ScriptDirectory.from_config(configuration).get_heads())
    current = sorted(MigrationContext.configure(connection).get_current_heads())
    return {
        "migration_current_heads": current,
        "migration_expected_heads": expected,
        "migrations_current": current == expected,
    }


def database_status() -> dict[str, object]:
    engine = get_engine()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing_columns = []
    if "edna_sample" in tables and "classification_review_json" not in {
        column["name"] for column in inspector.get_columns("edna_sample")
    }:
        missing_columns.append("edna_sample.classification_review_json")
    if "chat_interaction" in tables:
        chat_columns = {
            column["name"] for column in inspector.get_columns("chat_interaction")
        }
        for column_name in ("outcome", "abstention_reason"):
            if column_name not in chat_columns:
                missing_columns.append(f"chat_interaction.{column_name}")
    with engine.connect() as connection:
        migrations = migration_status(connection)
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
        "ready": (
            vector_installed
            and not missing_tables
            and not missing_columns
            and migrations["migrations_current"]
        ),
        **migrations,
        "vector_extension": vector_installed,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
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
        print(f"missing_columns={','.join(status.get('missing_columns', []))}")
        print(f"table_count={status['table_count']}")
        print(f"migration_current_heads={','.join(status['migration_current_heads'])}")
        print(f"migration_expected_heads={','.join(status['migration_expected_heads'])}")
    return 0 if status["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
