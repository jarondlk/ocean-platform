"""One fixed beta Research grant transaction; never accepts SQL or credentials in argv."""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import privileges

PROJECT = "ocean-v1-beta-20261101"
DATABASE = "ocean_v1_beta"
MIGRATOR = "ocean_v1_migrator"
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Configuration:
    dsn: str = field(repr=False)
    revision: str
    manifest: dict = field(repr=False)


def configuration(env, *, confirm_project, confirm_source):
    try:
        if (confirm_project != PROJECT or env.get("OCEAN_V1_PROJECT_ID") != PROJECT
                or env.get("DEPLOYMENT_ENV") != "production" or "DATABASE_URL" in env
                or "config" in sys.modules or any(v.lower().strip() != "false" for k, v in env.items() if k.startswith("ENABLE_V1_"))):
            raise ValueError()
        revision = env["OCEAN_V1_RESEARCH_OPERATOR_REVISION"]
        if not re.fullmatch(r"[a-f0-9]{40}", revision) or revision != confirm_source:
            raise ValueError()
        manifest = json.loads((ROOT / "research-operator-manifest.json").read_text())
        if (manifest["version"] != "ocean-v1-beta-research-operator-v1"
                or manifest["revision"] != revision or manifest["project_id"] != PROJECT):
            raise ValueError()
        for name in ("research_operator.py", "privileges.py"):
            path = ROOT / name
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["source_pins"][name]:
                raise ValueError()
        connection = env["OCEAN_V1_SQL_CONNECTION_NAME"]
        if re.fullmatch(re.escape(PROJECT) + r":asia-northeast1:ocean-v1-beta-[a-z0-9-]+", connection) is None:
            raise ValueError()
        dsn = env["OCEAN_V1_OPERATOR_DATABASE_URL"]
        u = make_url(dsn)
        if (u.drivername != "postgresql+psycopg2" or u.username != MIGRATOR or not u.password
                or u.database != DATABASE or u.host != "127.0.0.1" or u.port != 5432
                or dict(u.query) not in ({}, {"sslmode": "disable"})):
            raise ValueError()
        return Configuration(dsn, revision, manifest)
    except Exception:
        raise ValueError("Exact beta Research operator source and target required") from None


def policies(manifest):
    result = {}
    for role, inserts in privileges.ROLES.items():
        tables = {name: {"SELECT"} for name in privileges.READ_TABLES}
        for name in (*inserts, *privileges.EVIDENCE_INSERT):
            tables[name].add("INSERT")
        columns = {name: {"UPDATE": set(names)} for name, names in privileges.COMMON_UPDATE.items()}
        if role == "ocean_v1_serving":
            for name, rights in manifest["existing_serving_table_privileges"].items():
                tables.setdefault(name, set()).update(rights)
            for name, kinds in manifest["existing_serving_column_privileges"].items():
                for kind, names in kinds.items():
                    columns.setdefault(name, {}).setdefault(kind, set()).update(names)
        else:
            for name, names in privileges.CONTROLLER_UPDATE.items():
                columns.setdefault(name, {}).setdefault("UPDATE", set()).update(names)
        result[role] = tables, columns
    return result


def verify(connection, manifest, *, complete):
    if connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "CROSS JOIN LATERAL aclexplode(c.relacl) a WHERE n.nspname='public' AND a.grantee=0) OR "
            "EXISTS(SELECT 1 FROM pg_attribute c JOIN pg_class t ON t.oid=c.attrelid "
            "JOIN pg_namespace n ON n.oid=t.relnamespace CROSS JOIN LATERAL aclexplode(c.attacl) a "
            "WHERE n.nspname='public' AND a.grantee=0)")):
        raise ValueError("PUBLIC table or column access requires inspection")
    relations = connection.execute(text("SELECT n.nspname, c.relname, c.relkind, c.oid "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname <> 'information_schema' AND n.nspname !~ '^pg_' "
        "AND c.relkind IN ('r','p','v','m','f','S')")).all()
    for role, (tables, columns) in policies(manifest).items():
        attrs = connection.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
            "FROM pg_roles WHERE rolname=:role"), {"role": role}).one()
        if any(attrs) or connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_auth_members m "
                "JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=:role)"), {"role": role}):
            raise ValueError("Restricted runtime roles required")
        if connection.scalar(text("SELECT has_database_privilege(:role,current_database(),'CREATE,TEMP') "
                "OR has_schema_privilege(:role,'public','CREATE')"), {"role": role}):
            raise ValueError("Runtime DDL rights are forbidden")
        for schema, name, kind, oid in relations:
            if kind == "S":
                if connection.scalar(text("SELECT has_sequence_privilege(:role,:oid,'SELECT,UPDATE,USAGE')"), {"role": role, "oid": oid}):
                    raise ValueError("Unexpected sequence access")
                continue
            for right in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                params = {"role": role, "oid": oid, "right": right}
                actual = connection.scalar(text("SELECT has_table_privilege(:role,:oid,:right)"), params)
                expected = schema == "public" and right in tables.get(name, set())
                delegated = connection.scalar(text("SELECT has_table_privilege(:role,:oid,:right)"),
                    {**params, "right": right + " WITH GRANT OPTION"})
                if delegated or actual and not expected or complete and expected and not actual:
                    raise ValueError("Unexpected or incomplete runtime table grants")
            for column in connection.execute(text("SELECT attname FROM pg_attribute "
                    "WHERE attrelid=:oid AND attnum>0 AND NOT attisdropped"), {"oid": oid}).scalars():
                for right in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
                    params = {"role": role, "oid": oid, "column": column, "right": right}
                    actual = connection.scalar(text("SELECT has_column_privilege(:role,:oid,:column,:right)"), params)
                    expected = schema == "public" and (right in tables.get(name, set()) or column in columns.get(name, {}).get(right, set()))
                    delegated = connection.scalar(text("SELECT has_column_privilege(:role,:oid,:column,:right)"),
                        {**params, "right": right + " WITH GRANT OPTION"})
                    if delegated or actual and not expected or complete and expected and not actual:
                        raise ValueError("Unexpected or incomplete runtime column grants")
        for oid, name in connection.execute(text("SELECT p.oid,p.proname FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'ocean_%'")):
            allowed = complete and name == "ocean_v1_beta_research_owner_lock"
            actual = connection.scalar(text("SELECT has_function_privilege(:role,:oid,'EXECUTE')"), {"role": role, "oid": oid})
            if actual != allowed:
                raise ValueError("Unexpected application function rights")


def apply(connection, manifest):
    if connection.dialect.name != "postgresql" or tuple(connection.execute(text("SELECT current_database(), current_user")).one()) != (DATABASE, MIGRATOR):
        raise ValueError("Exact beta migrator identity required")
    if not 160000 <= int(connection.scalar(text("SHOW server_version_num"))) < 170000:
        raise ValueError("Reviewed PostgreSQL16 required")
    if any(connection.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
            "FROM pg_roles WHERE rolname=current_user")).one()):
        raise ValueError("Restricted migrator role required")
    if connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all() != ["20261027_0021"]:
        raise ValueError("Exact migration head required")
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('ocean-v1-beta-research-grants-v1',0))"))
    if connection.scalar(text("SELECT to_regprocedure('public.ocean_v1_beta_research_owner_lock(uuid)')")) is not None:
        raise ValueError("Research grant outcome already exists; inspect rather than replay")
    for table, expected in manifest["expected_columns"].items():
        columns = set(connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:table"), {"table": table}).scalars())
        owner = connection.scalar(text("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid=CAST(:table AS regclass)"), {"table": "public." + table})
        if columns != set(expected) or owner != MIGRATOR:
            raise ValueError("Exact owned application table inventory required")
    verify(connection, manifest, complete=False)
    for statement in privileges.statements():
        connection.exec_driver_sql(statement)
    verify(connection, manifest, complete=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-project", required=True)
    parser.add_argument("--confirm-source", required=True)
    args = parser.parse_args()
    engine = None
    try:
        selected = configuration(os.environ, confirm_project=args.confirm_project, confirm_source=args.confirm_source)
        engine = create_engine(selected.dsn, hide_parameters=True, pool_pre_ping=True,
            connect_args={"connect_timeout": 10, "options": "-c statement_timeout=60000 -c lock_timeout=10000"})
        with engine.begin() as connection:
            apply(connection, selected.manifest)
        with engine.connect() as connection:
            verify(connection, selected.manifest, complete=True)
        print(json.dumps({"state": "research_grants_verified", "revision": selected.revision,
            "account_writes_granted": False, "password_sql_or_data_mutation": False}))
        return 0
    except Exception:
        print("Beta Research grant operation rejected or uncertain; inspect the target before retrying", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
