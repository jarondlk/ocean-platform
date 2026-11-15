"""Fixed beta owner-read lock amendment; no grants, account writes or caller SQL.

FOR SHARE permits concurrent owner readers and still fences every UPDATE and
DELETE of that owner. Run/job mutation locks and the C09 retention fence remain
in their owning services. This is a separately qualified SQL source supersession,
not a replay of the original immutable Research grant operation.
"""
import hashlib
import json

from sqlalchemy import text

import privileges
import research_operator as operator

VERSION = "ocean-beta-b1-shared-owner-lock-v1"
ORIGINAL_BODY = privileges.OWNER_LOCK_SQL.split("$body$")[1].strip()
SHARED_BODY = ORIGINAL_BODY.replace("FOR NO KEY UPDATE", "FOR SHARE")
STATEMENT = (privileges.OWNER_LOCK_SQL.split(";\nREVOKE")[0] + ";").replace(
    "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1).replace("FOR NO KEY UPDATE", "FOR SHARE")


def metadata(connection):
    row = connection.execute(text("SELECT to_jsonb(p)-'prosrc',p.prosrc FROM pg_proc p WHERE "
        "p.oid=to_regprocedure('public.ocean_v1_beta_research_owner_lock(uuid)')")).one()
    return row[0], row[1].strip()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_target(connection):
    if (connection.dialect.name != "postgresql" or tuple(connection.execute(text(
            "SELECT current_database(),current_user")).one()) != (operator.DATABASE, operator.MIGRATOR)
            or not 160000 <= int(connection.scalar(text("SHOW server_version_num"))) < 170000
            or any(connection.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
                "FROM pg_roles WHERE rolname=current_user")).one())
            or connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all() != ["20261027_0021"]):
        raise ValueError("Exact restricted beta PG16 migrator and migration head required")


def amend(connection, manifest, *, verify_only=False):
    """One transaction; an uncertain application must be inspected, never replayed."""
    validate_target(connection)
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('ocean-v1-beta-research-grants-v1',0))"))
    before, body = metadata(connection)
    if verify_only:
        if body != SHARED_BODY:
            raise ValueError("Shared owner-lock amendment not present")
    else:
        if body != ORIGINAL_BODY:
            raise ValueError("Original owner lock required; inspect rather than replay")
        operator.verify(connection, manifest, complete=True)
        # Admission must also be drained and provider-side quiescence checked by
        # the operator. These DB fences reject active/prepared work independently.
        for table in ("research_run", "research_answer_job"):
            if connection.scalar(text(f"SELECT EXISTS(SELECT 1 FROM public.{table} WHERE "
                    "status IN ('queued','running') OR lease_until IS NOT NULL OR active_started_at IS NOT NULL)")):
                raise ValueError("Closed Research leases required")
        for table in ("research_run_step", "research_answer_step"):
            if connection.scalar(text(f"SELECT EXISTS(SELECT 1 FROM public.{table} WHERE state='prepared')")):
                raise ValueError("No prepared model step permitted")
        connection.exec_driver_sql(STATEMENT)
    operator.verify(connection, manifest, complete=True, owner_lock_mode="shared")
    after, body = metadata(connection)
    if body != SHARED_BODY or after != before:
        raise ValueError("Function identity, ACL or security metadata changed")
    return {"version": VERSION, "state": "shared_owner_lock_verified", "verification_only": verify_only,
        "original_body_sha256": hashlib.sha256(ORIGINAL_BODY.encode()).hexdigest(),
        "shared_body_sha256": hashlib.sha256(SHARED_BODY.encode()).hexdigest(),
        "function_metadata_sha256": fingerprint(after), "oid_acl_owner_security_metadata_preserved": True,
        "grants_account_data_or_runtime_source_changed": False}
