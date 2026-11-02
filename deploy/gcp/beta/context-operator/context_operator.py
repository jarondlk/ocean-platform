"""One exact beta context-grant transaction; no credentials, DDL or general SQL.

Runs as the existing restricted migrator over the existing private SQL proxy.
Only the reviewed C17 table/column grants can be added. Unexpected effective
rights, PUBLIC ACLs, role inheritance, ownership or schema drift fail closed;
no automatic revoke/reset is available. Ordinary errors never print private DSNs.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parent
PROJECT = "ocean-v1-beta-20261101"
DATABASE = "ocean_v1_beta"
CONNECTION = PROJECT + ":asia-northeast1:ocean-v1-beta-sql"
MIGRATOR = "ocean_v1_migrator"
SERVING = "ocean_v1_serving"
HEAD = "20261027_0021"
BASE_OPERATOR_REVISION = "8e2a1630d5d2a7028495ec7b56a422a38b1c0807"
BASE_OPERATOR_IMAGE = ("asia-northeast1-docker.pkg.dev/" + PROJECT + "/ocean-v1-beta/operator@sha256:"
    "0a89057b7459342e191e4b194628bee00cc7544749489df9f85f31508399e7b3")
API_REVISION = "7924a28e919b1fb751890c694f7b1f9b26b104ff"
FLAGS = ("ENABLE_V1_RESEARCH_CONTROLLER", "ENABLE_V1_RESEARCH_DISPATCH",
    "ENABLE_V1_SYNTHESIS", "ENABLE_V1_EXPERIMENT_DISPATCH")
BASE_TABLE_PRIVILEGES = {"app_user": frozenset({"SELECT"}), "alembic_version": frozenset({"SELECT"}),
    "rate_limit_bucket": frozenset({"SELECT", "INSERT", "UPDATE"})}
CONTEXT_TABLE_PRIVILEGES = {
    "research_investigation": frozenset({"SELECT", "INSERT"}),
    "research_conversation": frozenset({"SELECT", "INSERT"}),
    "research_context_revision": frozenset({"SELECT", "INSERT"}),
    "research_context_operation": frozenset({"SELECT", "INSERT"}),
    "audit_event": frozenset({"INSERT"}),
}
CONTEXT_COLUMN_PRIVILEGES = {
    "research_investigation": {"UPDATE": frozenset({"name", "metadata_version", "status", "head_revision_id",
        "legal_hold", "updated_at", "retired_at"})},
    "research_conversation": {"UPDATE": frozenset({"name", "metadata_version", "updated_at"})},
    "research_context_operation": {"UPDATE": frozenset({"state", "error_code", "updated_at"})},
    # Actual ORM AuditEvent INSERT uses RETURNING created_at. This is not audit
    # event metadata/history read access and is insufficient for SELECT *.
    "audit_event": {"SELECT": frozenset({"created_at"})},
}
EXPECTED_COLUMNS = {
    "research_investigation": frozenset({"id", "user_id", "name", "metadata_version", "status", "head_revision_id",
        "predecessor_investigation_id", "predecessor_revision_id", "legal_hold", "created_at", "updated_at", "retired_at"}),
    "research_conversation": frozenset({"id", "investigation_id", "name", "metadata_version", "created_at", "updated_at"}),
    "research_context_revision": frozenset({"id", "investigation_id", "sequence", "predecessor_revision_id", "snapshot_id",
        "payload_json", "payload_sha256", "created_by_user_id", "created_at"}),
    "research_context_operation": frozenset({"id", "user_id", "investigation_id", "idempotency_key", "kind", "expected_head_id",
        "candidate_revision_id", "request_json", "request_sha256", "candidate_json", "references_json", "state", "error_code",
        "created_at", "updated_at"}),
    "audit_event": frozenset({"id", "actor_user_id", "action", "target_type", "target_id", "metadata_json", "created_at"}),
}


class ContextOperatorError(ValueError):
    """Fixed credential-safe diagnostics only."""


@dataclass(frozen=True, repr=False)
class Configuration:
    dsn: str = field(repr=False)
    revision: str


def _document(path):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 65536:
        raise ValueError()
    return json.loads(path.read_text())


def load_base_operator():
    path = ROOT / "beta_operator.py"
    manifest = _document(ROOT / "operator-manifest.json")
    if (manifest.get("revision") != BASE_OPERATOR_REVISION
            or manifest.get("project_id") != PROJECT or path.is_symlink()
            or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["source_pins"]["operator.py"]):
        raise ContextOperatorError("Accepted base operator source binding rejected")
    spec = importlib.util.spec_from_file_location("ocean_beta_context_base_operator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configuration(env, *, confirm_project, confirm_database, confirm_source, confirm_operator):
    try:
        if (confirm_project != PROJECT or confirm_database != DATABASE or confirm_operator != BASE_OPERATOR_REVISION
                or env.get("DEPLOYMENT_ENV") != "production" or env.get("OCEAN_V1_PROJECT_ID") != PROJECT
                or env.get("OCEAN_V1_SQL_CONNECTION_NAME") != CONNECTION or "DATABASE_URL" in env
                or "config" in sys.modules or any(name in env for name in ("OCEAN_V1_MIGRATOR_PASSWORD", "OCEAN_V1_SERVING_PASSWORD"))
                or any(env.get(name, "false").strip().lower() != "false" for name in FLAGS)):
            raise ValueError()
        revision = env["OCEAN_V1_CONTEXT_OPERATOR_REVISION"]
        manifest = _document(ROOT / "context-operator-manifest.json")
        base = _document(ROOT / "operator-manifest.json")
        application = _document(ROOT / "source-manifest.json")
        if (not re.fullmatch(r"[a-f0-9]{40}", revision) or confirm_source != revision
                or manifest.get("version") != "ocean-v1-beta-context-operator-v1"
                or manifest.get("project_id") != PROJECT or manifest.get("revision") != revision
                or manifest.get("base_operator_revision") != BASE_OPERATOR_REVISION
                or manifest.get("base_operator_image") != BASE_OPERATOR_IMAGE
                or base.get("version") != "ocean-v1-beta-operator-context-v1"
                or base.get("revision") != BASE_OPERATOR_REVISION or base.get("api_revision") != API_REVISION
                or application.get("version") != "ocean-v1-beta-api-context-v1"
                or application.get("revision") != API_REVISION or application.get("project_id") != PROJECT
                or hashlib.sha256((ROOT / "context_operator.py").read_bytes()).hexdigest()
                    != manifest["source_pins"]["context_operator.py"]):
            raise ValueError()
        dsn = env["OCEAN_V1_OPERATOR_DATABASE_URL"]
        url = make_url(dsn)
        if (url.drivername != "postgresql+psycopg2" or url.database != DATABASE or url.username != MIGRATOR
                or not url.password or url.host != "127.0.0.1" or url.port != 5432
                or dict(url.query) not in ({}, {"sslmode": "disable"})):
            raise ValueError()
        return Configuration(dsn, revision)
    except Exception:
        raise ContextOperatorError("Exact beta context grant target and packaged source required") from None


def _policy_cte():
    tables, columns = [], []
    for table, privileges in {**BASE_TABLE_PRIVILEGES, **CONTEXT_TABLE_PRIVILEGES}.items():
        for privilege in sorted(privileges):
            tables.append("('public','" + table + "','" + privilege + "')")
    for table, kinds in CONTEXT_COLUMN_PRIVILEGES.items():
        for privilege, names in kinds.items():
            for name in sorted(names):
                columns.append("('public','" + table + "','" + name + "','" + privilege + "')")
    return ("WITH table_policy(schema_name,table_name,privilege_type) AS (VALUES " + ",".join(tables)
        + "),column_policy(schema_name,table_name,column_name,privilege_type) AS (VALUES " + ",".join(columns) + ") ")


def verify_privileges(connection, *, require_complete=False):
    """Audit effective table/column/PUBLIC rights without reading application data."""
    user_schema = "n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'"
    if connection.scalar(text(
        "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "CROSS JOIN LATERAL aclexplode(c.relacl) acl WHERE " + user_schema
        + " AND c.relkind IN ('r','p','v','m','f','S') AND acl.grantee=0) OR "
        "EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(a.attacl) acl WHERE "
        + user_schema + " AND a.attnum>0 AND NOT a.attisdropped AND acl.grantee=0)")):
        raise ContextOperatorError("PUBLIC relation or column access requires inspection; no automatic reset")
    parameters = {"role": SERVING}
    cte = _policy_cte()
    table_rights = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]
    if int(connection.scalar(text("SELECT current_setting('server_version_num')"))) >= 170000:
        table_rights.append("MAINTAIN")
    for privilege in table_rights:
        parameters.update(privilege=privilege, delegated=privilege + " WITH GRANT OPTION")
        if connection.scalar(text(cte +
            "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
            + user_schema + " AND c.relkind IN ('r','p','v','m','f') AND "
            "has_table_privilege(:role,c.oid,:privilege) AND (has_table_privilege(:role,c.oid,:delegated) OR NOT EXISTS "
            "(SELECT 1 FROM table_policy p WHERE p.schema_name=n.nspname AND p.table_name=c.relname "
            "AND p.privilege_type=:privilege)))"), parameters):
            raise ContextOperatorError("Unexpected effective table or delegation rights; no automatic reset")
    for privilege in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
        parameters.update(privilege=privilege, delegated=privilege + " WITH GRANT OPTION")
        if connection.scalar(text(cte +
            "SELECT EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE " + user_schema
            + " AND c.relkind IN ('r','p','v','m','f') AND a.attnum>0 AND NOT a.attisdropped AND "
            "has_column_privilege(:role,c.oid,a.attnum,:privilege) AND "
            "(has_column_privilege(:role,c.oid,a.attnum,:delegated) OR NOT (EXISTS "
            "(SELECT 1 FROM table_policy p WHERE p.schema_name=n.nspname AND p.table_name=c.relname "
            "AND p.privilege_type=:privilege) OR EXISTS(SELECT 1 FROM column_policy p WHERE "
            "p.schema_name=n.nspname AND p.table_name=c.relname AND p.column_name=a.attname AND p.privilege_type=:privilege))))"), parameters):
            raise ContextOperatorError("Unexpected effective column or delegation rights; no automatic reset")
    if connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
            + user_schema + " AND CASE WHEN c.relkind='S' THEN has_sequence_privilege(:role,c.oid,'USAGE,SELECT,UPDATE') ELSE false END)"),
            {"role": SERVING}):
        raise ContextOperatorError("Unexpected sequence rights; no automatic reset")
    if connection.scalar(text("SELECT has_database_privilege(:role,current_database(),'CREATE') OR "
            "has_database_privilege(:role,current_database(),'TEMP') OR has_schema_privilege(:role,'public','CREATE')"), {"role": SERVING}):
        raise ContextOperatorError("Serving must not create database or schema objects")
    if connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='public' AND p.proname LIKE 'ocean_%' AND has_function_privilege(:role,p.oid,'EXECUTE'))"), {"role": SERVING}):
        raise ContextOperatorError("Unexpected application function execution rights")
    if require_complete:
        for table, privileges in {**BASE_TABLE_PRIVILEGES, **CONTEXT_TABLE_PRIVILEGES}.items():
            for privilege in privileges:
                if connection.scalar(text("SELECT has_table_privilege(:role,:table,:privilege)"),
                        {"role": SERVING, "table": "public." + table, "privilege": privilege}) is not True:
                    raise ContextOperatorError("Required exact context table grants are incomplete")
        for table, kinds in CONTEXT_COLUMN_PRIVILEGES.items():
            for privilege, columns in kinds.items():
                for column in columns:
                    if connection.scalar(text("SELECT has_column_privilege(:role,:table,:column,:privilege)"),
                            {"role": SERVING, "table": "public." + table, "column": column, "privilege": privilege}) is not True:
                        raise ContextOperatorError("Required exact context column grants are incomplete")


def preflight(connection, base, *, _allow_test_postgres=False):
    if connection.dialect.name != "postgresql":
        raise ContextOperatorError("Explicit PostgreSQL context grant target required")
    base.identity(connection, MIGRATOR)
    roles = base.assert_restricted_roles(connection)
    version = int(connection.scalar(text("SELECT current_setting('server_version_num')")))
    if not (160000 <= version < 170000 or _allow_test_postgres and os.environ.get("DEPLOYMENT_ENV") == "test"):
        raise ContextOperatorError("Reviewed Cloud SQL PostgreSQL16 target required")
    if connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all() != [HEAD]:
        raise ContextOperatorError("Exact reviewed migration head required")
    for table, expected in EXPECTED_COLUMNS.items():
        columns = set(connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:table"), {"table": table}).scalars())
        owner = connection.scalar(text("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid=CAST(:table AS regclass)"), {"table": "public." + table})
        if columns != expected or owner != MIGRATOR:
            raise ContextOperatorError("Exact owned context table column inventory required")
    verify_privileges(connection)
    return roles


def apply_context_grants(connection, base, *, _allow_test_postgres=False):
    roles = preflight(connection, base, _allow_test_postgres=_allow_test_postgres)
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('ocean-v1-beta-context-grants-v1',0))"))
    for table, privileges in CONTEXT_TABLE_PRIVILEGES.items():
        for privilege in sorted(privileges):
            base.statement(connection, "GRANT " + privilege + " ON TABLE public.{} TO {}", table, SERVING)
    for table, kinds in CONTEXT_COLUMN_PRIVILEGES.items():
        for privilege, columns in kinds.items():
            for column in sorted(columns):
                base.statement(connection, "GRANT " + privilege + " ({}) ON TABLE public.{} TO {}", column, table, SERVING)
    verify_privileges(connection, require_complete=True)
    return {"stage": "context-grants", "roles": roles, "table_grants": {k: sorted(v) for k, v in CONTEXT_TABLE_PRIVILEGES.items()},
        "column_grants": {k: {p: sorted(v) for p, v in kinds.items()} for k, kinds in CONTEXT_COLUMN_PRIVILEGES.items()},
        "effective_privileges_verified": True, "schema_or_role_mutations": False, "sequence_grants": False,
        "password_sql_or_account_mutation": False, "application_data_read": False}


def run(settings, base):
    engine = create_engine(settings.dsn, hide_parameters=True, pool_pre_ping=True,
        connect_args={"connect_timeout": 10, "options": "-c statement_timeout=60000 -c lock_timeout=10000"})
    try:
        with engine.begin() as connection:
            result = apply_context_grants(connection, base)
        engine.dispose()
        with engine.connect() as connection:
            preflight(connection, base)
            verify_privileges(connection, require_complete=True)
        result["fresh_connection_readback_verified"] = True
        return result
    finally:
        engine.dispose()


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            raise ContextOperatorError("Exact context grant confirmations required")
    parser = Parser(description=__doc__)
    for name in ("project", "database", "source", "operator"):
        parser.add_argument("--confirm-" + name, required=True)
    report = {"version": "ocean-v1-beta-context-operator-result-v1", "project_id": PROJECT,
        "database": DATABASE, "state": "failed"}
    base, code = None, 2
    try:
        base = load_base_operator()
        args = parser.parse_args(argv)
        settings = configuration(os.environ, confirm_project=args.confirm_project, confirm_database=args.confirm_database,
            confirm_source=args.confirm_source, confirm_operator=args.confirm_operator)
        report["revision"] = settings.revision
        report["operation"] = run(settings, base)
        report["state"], code = "succeeded", 0
    except Exception:
        report["failure"] = "Context grants were not accepted; inspect retained state before retry"
    finally:
        if base is not None:
            try:
                report["proxy"] = base.stop_proxy()
            except Exception:
                report["state"], code = "failed", 2
                report["proxy_shutdown_acknowledged"] = False
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
