#!/usr/bin/env python3
"""Copy only canonical scientific tables into an empty COP17 database.

No account, invitation, chat, audit, credential, review or rate-limit rows are
read or copied. Source connections enforce read-only transactions at login.
Run as a one-shot job with source and target URLs mounted from Secret Manager.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import CorpusBase  # noqa: E402
from db.app_models import AppBase  # noqa: E402
from scripts.bootstrap_database import bootstrap_database  # noqa: E402

SOURCE_INSTANCE = "data-infra-infobio:asia-northeast1:ocean-postgres"
TARGET_INSTANCE = "data-infra-infobio:asia-northeast1:ocean-cop17-postgres"
TARGET_DATABASE = "ocean_cop17"


def validate_endpoints(source, target, confirmation):
    src, dst = make_url(source), make_url(target)
    if confirmation != TARGET_INSTANCE:
        raise ValueError("Explicit COP17 target confirmation is required")
    if (src.query.get("host") != "/cloudsql/" + SOURCE_INSTANCE
            or src.database != "ocean_platform"
            or dst.query.get("host") != "/cloudsql/" + TARGET_INSTANCE
            or dst.database != TARGET_DATABASE
            or src.drivername != "postgresql+psycopg2"
            or dst.drivername != "postgresql+psycopg2"
            or src.host or dst.host):
        raise ValueError("Only the exact read-only source and isolated COP17 target are allowed")


def row_bytes(row):
    def convert(value):
        if hasattr(value, "tolist"):
            return value.tolist()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
    return json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=convert).encode() + b"\n"


def main():
    source = os.environ["COP17_SOURCE_DATABASE_URL"]
    target = os.environ["DATABASE_URL"]
    validate_endpoints(source, target, os.environ.get("CONFIRM_COP17_TARGET"))
    # This option applies to every source transaction, before any statement.
    source_engine = create_engine(source, connect_args={"options": "-c default_transaction_read_only=on"})
    target_engine = create_engine(target)
    with source_engine.connect() as src, src.begin():
        src.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        assert src.exec_driver_sql("SHOW transaction_read_only").scalar() == "on"
        source_heads = src.exec_driver_sql("SELECT version_num FROM alembic_version ORDER BY version_num").scalars().all()
        status = bootstrap_database()
        if not status["ready"] or source_heads != status["migration_current_heads"]:
            raise ValueError("Source/target schema identities differ")
        manifest = {"source_instance": SOURCE_INSTANCE, "target_instance": TARGET_INSTANCE,
                    "schema_heads": source_heads, "tables": {}, "excluded_application_tables": sorted(AppBase.metadata.tables)}
        with target_engine.begin() as dst:
            for table in list(CorpusBase.metadata.sorted_tables) + list(AppBase.metadata.sorted_tables):
                if dst.scalar(select(func.count()).select_from(table)):
                    raise ValueError("The target must have no existing scientific or application rows")
            for table in CorpusBase.metadata.sorted_tables:
                order = list(table.primary_key.columns)
                query = select(table).order_by(*order)
                expected = hashlib.sha256()
                count = 0
                result = src.execution_options(stream_results=True).execute(query).mappings()
                while rows := result.fetchmany(500):
                    batch = [dict(row) for row in rows]
                    for row in rows:
                        expected.update(row_bytes(row))
                    dst.execute(table.insert(), batch)
                    count += len(batch)
                actual = hashlib.sha256()
                copied = 0
                for row in dst.execute(query).mappings():
                    actual.update(row_bytes(row))
                    copied += 1
                if copied != count or actual.hexdigest() != expected.hexdigest():
                    raise ValueError("Scientific snapshot row/hash mismatch")
                for column in table.columns:
                    if column.primary_key and str(column.type) in {"INTEGER", "BIGINT"}:
                        sequence = dst.scalar(text("SELECT pg_get_serial_sequence(:table, :column)"), {"table": table.name, "column": column.name})
                        if sequence:
                            maximum = dst.scalar(select(func.max(column)))
                            dst.execute(text("SELECT setval(CAST(:sequence AS regclass), :value, :called)"),
                                        {"sequence": sequence, "value": maximum or 1, "called": maximum is not None})
                manifest["tables"][table.name] = {"rows": count, "sha256": expected.hexdigest()}
                print(json.dumps({"copied_table": table.name, "rows": count}), flush=True)
        print(json.dumps({"scientific_snapshot_verified": True, **manifest}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
