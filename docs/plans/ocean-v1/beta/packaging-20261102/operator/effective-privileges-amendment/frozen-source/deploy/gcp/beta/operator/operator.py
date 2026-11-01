"""Explicit new-beta database stages; no general SQL or credential CLI input."""

from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parent
PROJECT = "ocean-v1-beta-20261101"
DATABASE = "ocean_v1_beta"
CONNECTION = PROJECT + ":asia-northeast1:ocean-v1-beta-sql"
MIGRATOR = "ocean_v1_migrator"
SERVING = "ocean_v1_serving"
HEAD = "20261027_0021"
ROLES = (MIGRATOR, SERVING)
FLAGS = (
    "ENABLE_V1_RESEARCH_CONTROLLER",
    "ENABLE_V1_RESEARCH_DISPATCH",
    "ENABLE_V1_SYNTHESIS",
    "ENABLE_V1_EXPERIMENT_DISPATCH",
)


class OperatorError(ValueError):
    """Fixed credential-safe diagnostic only."""


def validate(
    env, *, stage, confirm_project, confirm_database, confirm_source, confirm_operator
):
    if (
        stage not in {"bootstrap", "migrate", "finalize", "readback"}
        or confirm_project != PROJECT
        or confirm_database != DATABASE
        or env.get("DEPLOYMENT_ENV") != "production"
        or env.get("OCEAN_V1_PROJECT_ID") != PROJECT
        or env.get("OCEAN_V1_SQL_CONNECTION_NAME") != CONNECTION
        or "DATABASE_URL" in env
        or "config" in sys.modules
        or any(env.get(name, "false").strip().lower() != "false" for name in FLAGS)
    ):
        raise OperatorError("Explicit independent beta operator configuration required")
    try:
        manifest = json.loads((ROOT / "operator-manifest.json").read_text())
        application = json.loads((ROOT / "source-manifest.json").read_text())
        source, operator = (
            env["OCEAN_V1_SOURCE_REVISION"],
            env["OCEAN_V1_OPERATOR_REVISION"],
        )
        if (
            not re.fullmatch(r"[a-f0-9]{40}", source)
            or not re.fullmatch(r"[a-f0-9]{40}", operator)
            or confirm_source != source
            or confirm_operator != operator
            or manifest["version"] != "ocean-v1-beta-operator-context-v1"
            or manifest["project_id"] != PROJECT
            or manifest["revision"] != operator
            or manifest["api_revision"] != source
            or application["revision"] != source
            or application["project_id"] != PROJECT
            or application["version"] != "ocean-v1-beta-api-context-v1"
            or not re.fullmatch(
                r"asia-northeast1-docker\.pkg\.dev/"
                + PROJECT
                + r"/ocean-v1-beta/api@sha256:[a-f0-9]{64}",
                manifest["api_image"],
            )
        ):
            raise ValueError()
        dsn = env["OCEAN_V1_OPERATOR_DATABASE_URL"]
        url = make_url(dsn)
        expected_user = MIGRATOR if stage in {"migrate", "finalize"} else "postgres"
        if (
            url.drivername != "postgresql+psycopg2"
            or url.database != DATABASE
            or url.username != expected_user
            or not url.password
            or url.host != "127.0.0.1"
            or url.port != 5432
            or dict(url.query) not in ({}, {"sslmode": "disable"})
        ):
            raise ValueError()
        if stage == "bootstrap":
            passwords = (
                env["OCEAN_V1_MIGRATOR_PASSWORD"],
                env["OCEAN_V1_SERVING_PASSWORD"],
            )
            if (
                any(
                    not re.fullmatch(r"[A-Za-z0-9_-]{48,128}", password)
                    for password in passwords
                )
                or len(set((*passwords, url.password))) != 3
            ):
                raise ValueError()
    except Exception:
        raise OperatorError(
            "Operator target, private inputs or packaged source identity rejected"
        ) from None
    return {"dsn": dsn, "user": expected_user, "source": source, "operator": operator}


def connect(dsn):
    return create_engine(
        dsn,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 10,
            "options": "-c statement_timeout=480000 -c lock_timeout=10000",
        },
    )


def identity(connection, expected_user):
    observed = connection.execute(
        text("SELECT current_database(),current_user,session_user")
    ).one()
    if tuple(observed) != (DATABASE, expected_user, expected_user):
        raise OperatorError("Live database or principal identity mismatch")


def role_readback(connection):
    rows = connection.execute(
        text(
            "SELECT rolname,rolsuper,rolcreaterole,rolcreatedb,rolreplication,"
            "rolbypassrls,rolcanlogin FROM pg_roles WHERE rolname=ANY(:names) ORDER BY rolname"
        ),
        {"names": list(ROLES)},
    ).all()
    return [
        dict(
            zip(
                (
                    "name",
                    "superuser",
                    "create_role",
                    "create_database",
                    "replication",
                    "bypass_rls",
                    "login",
                ),
                row,
            )
        )
        for row in rows
    ]


def assert_restricted_roles(connection):
    roles = role_readback(connection)
    if len(roles) != 2 or any(
        not role["login"]
        or any(
            role[name]
            for name in (
                "superuser",
                "create_role",
                "create_database",
                "replication",
                "bypass_rls",
            )
        )
        for role in roles
    ):
        raise OperatorError("Restricted independent role attributes are not ready")
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_auth_members WHERE "
            "member IN (SELECT oid FROM pg_roles WHERE rolname=ANY(:names)) OR "
            "roleid IN (SELECT oid FROM pg_roles WHERE rolname=ANY(:names)))"
        ),
        {"names": list(ROLES)},
    ):
        raise OperatorError("Independent roles must have no memberships or members")
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba "
            "WHERE d.datname=current_database() AND r.rolname=ANY(:names)) OR "
            "EXISTS(SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner "
            "WHERE n.nspname='public' AND r.rolname=ANY(:names))"
        ),
        {"names": list(ROLES)},
    ):
        raise OperatorError(
            "Runtime and migrator roles must not own the bootstrap database or schema"
        )
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname='public' AND r.rolname=:role)"
        ),
        {"role": SERVING},
    ):
        raise OperatorError("Serving role must not own application objects")
    return roles


def statement(connection, template, *identifiers, parameters=None):
    """Identifiers are composed separately; passwords are DB-driver parameters."""
    cursor = connection.connection.driver_connection.cursor()
    try:
        cursor.execute(
            sql.SQL(template).format(*(sql.Identifier(value) for value in identifiers)),
            parameters,
        )
    finally:
        cursor.close()


def fresh_database(connection):
    identity(connection, "postgres")
    connection.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended('ocean-v1-beta-bootstrap',0))"
        )
    )
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname LIKE 'ocean\\_v1\\_%' ESCAPE '\\')"
        )
    ):
        raise OperatorError("Fresh bootstrap refuses existing independent roles")
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public') OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public')"
        )
    ):
        raise OperatorError("Fresh bootstrap refuses populated application schema")
    if connection.scalar(
        text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname <> 'plpgsql')")
    ):
        raise OperatorError("Fresh bootstrap refuses unexpected installed extensions")
    if (
        connection.scalar(
            text(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()"
            )
        )
        != "postgres"
    ):
        raise OperatorError(
            "Fresh bootstrap database must belong to the explicit bootstrap principal"
        )
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema') AND nspname NOT LIKE 'pg_toast%' AND nspname NOT LIKE 'pg_temp_%')"
        )
    ):
        raise OperatorError("Fresh bootstrap refuses unexpected user schema")


def create_roles(connection, env):
    for role, key in (
        (MIGRATOR, "OCEAN_V1_MIGRATOR_PASSWORD"),
        (SERVING, "OCEAN_V1_SERVING_PASSWORD"),
    ):
        statement(
            connection,
            "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %s",
            role,
            parameters=(env[key],),
        )
        # PostgreSQL may automatically make a non-superuser role creator a member.
        # Remove only the newly created role's creator membership, never a pre-existing role.
        statement(connection, "REVOKE {} FROM {}", role, "postgres")
        statement(
            connection,
            "ALTER ROLE {} IN DATABASE {} SET search_path TO public, pg_catalog",
            role,
            DATABASE,
        )
    statement(connection, "REVOKE ALL ON DATABASE {} FROM PUBLIC", DATABASE)
    statement(
        connection,
        "GRANT CONNECT ON DATABASE {} TO {}, {}",
        DATABASE,
        MIGRATOR,
        SERVING,
    )
    connection.exec_driver_sql("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    statement(connection, "GRANT USAGE, CREATE ON SCHEMA public TO {}", MIGRATOR)
    statement(connection, "GRANT USAGE ON SCHEMA public TO {}", SERVING)
    return assert_restricted_roles(connection)


def bootstrap(connection, env):
    fresh_database(connection)
    connection.exec_driver_sql("CREATE EXTENSION vector WITH SCHEMA public")
    version = connection.scalar(
        text("SELECT extversion FROM pg_extension WHERE extname='vector'")
    )
    roles = create_roles(connection, env)
    return {
        "stage": "bootstrap",
        "extension": {"name": "vector", "version": version},
        "roles": roles,
        "public_schema_owner_unchanged": True,
        "application_rows_created": False,
    }


def readback(connection, expected_user):
    identity(connection, expected_user)
    tables = connection.execute(
        text(
            "SELECT tablename,tableowner FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
    ).all()
    head = connection.scalar(
        text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
    )
    versions = (
        connection.execute(text("SELECT version_num FROM public.alembic_version"))
        .scalars()
        .all()
        if head
        else []
    )
    return {
        "database": DATABASE,
        "principal": expected_user,
        "roles": role_readback(connection),
        "tables": [{"name": row[0], "owner": row[1]} for row in tables],
        "migration_versions": versions,
        "extensions": [
            dict(zip(("name", "version"), row))
            for row in connection.execute(
                text("SELECT extname,extversion FROM pg_extension ORDER BY extname")
            )
        ],
        "C23_execution_enabled": False,
        "cloudsql_limited_superuser_qualification_claimed": False,
    }


def finalize(connection):
    identity(connection, MIGRATOR)
    roles = assert_restricted_roles(connection)
    if connection.execute(
        text("SELECT version_num FROM public.alembic_version")
    ).scalars().all() != [HEAD]:
        raise OperatorError("Exact reviewed migration head required before grants")
    allowed = {
        "app_user": {"SELECT"},
        "alembic_version": {"SELECT"},
        "rate_limit_bucket": {"SELECT", "INSERT", "UPDATE"},
    }
    existing = connection.execute(
        text(
            "SELECT table_name,privilege_type,is_grantable FROM information_schema.role_table_grants WHERE grantee=:role AND table_schema='public'"
        ),
        {"role": SERVING},
    ).all()
    if any(
        table not in allowed or privilege not in allowed[table] or grantable != "NO"
        for table, privilege, grantable in existing
    ):
        raise OperatorError(
            "Serving has unexpected privileges; refusing an automatic reset"
        )
    if connection.scalar(
        text(
            "SELECT has_database_privilege(:role,current_database(),'CREATE') OR has_database_privilege(:role,current_database(),'TEMP') OR has_schema_privilege(:role,'public','CREATE')"
        ),
        {"role": SERVING},
    ):
        raise OperatorError("Serving has unexpected schema/database creation rights")
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'ocean_%' AND has_function_privilege(:role,p.oid,'EXECUTE'))"
        ),
        {"role": SERVING},
    ):
        raise OperatorError(
            "Serving unexpectedly inherits application function execution"
        )
    for table, privileges in allowed.items():
        statement(
            connection,
            "GRANT " + ", ".join(sorted(privileges)) + " ON TABLE public.{} TO {}",
            table,
            SERVING,
        )
    return {
        "stage": "finalize",
        "roles": roles,
        "serving_grants": {table: sorted(rights) for table, rights in allowed.items()},
        "all_tables_grant": False,
        "account_enrollment_performed": False,
    }


def run_stage(stage, validated, env):
    if stage == "migrate":
        engine = connect(validated["dsn"])
        try:
            with engine.begin() as connection:
                identity(connection, MIGRATOR)
                assert_restricted_roles(connection)
                if connection.scalar(text("SELECT current_schema()")) != "public":
                    raise OperatorError(
                        "Migration requires the explicit writable public schema first"
                    )
                # A schema-specific REVOKE cannot subtract the global default
                # PUBLIC EXECUTE privilege. Set this owner's database-wide default.
                connection.exec_driver_sql(
                    "ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
                )
        finally:
            engine.dispose()
        child_env = dict(
            env, OCEAN_V1_DATABASE_URL=validated["dsn"], OCEAN_V1_DATABASE_USER=MIGRATOR
        )
        # The migration subprocess only receives its own DSN, not bootstrap/serving passwords.
        child_env.pop("OCEAN_V1_MIGRATOR_PASSWORD", None)
        child_env.pop("OCEAN_V1_SERVING_PASSWORD", None)
        child = subprocess.run(
            [
                sys.executable,
                str(ROOT / "beta_entry.py"),
                "migrate",
                "--confirm-project",
                PROJECT,
                "--confirm-database",
                DATABASE,
            ],
            cwd=ROOT,
            env=child_env,
            text=True,
            capture_output=True,
            timeout=480,
            check=False,
        )
        if child.returncode != 0:
            raise OperatorError(
                "Reviewed migration subprocess failed; private target remains for inspection"
            )
        result = {
            "stage": "migrate",
            "migration_subprocess_returncode": child.returncode,
        }
    else:
        engine = connect(validated["dsn"])
        try:
            with engine.begin() as connection:
                if stage == "bootstrap":
                    result = bootstrap(connection, env)
                elif stage == "finalize":
                    result = finalize(connection)
                else:
                    result = {"stage": "readback"}
        finally:
            engine.dispose()
    engine = connect(validated["dsn"])
    try:
        with engine.connect() as connection:
            result["readback"] = readback(connection, validated["user"])
    finally:
        engine.dispose()
    return result


def stop_proxy():
    # Fixed same-instance loopback admin endpoint; never a caller-supplied URL.
    for attempt in range(3):
        client = http.client.HTTPConnection("127.0.0.1", 9091, timeout=3)
        try:
            client.request(
                "POST", "/quitquitquit", body=b"", headers={"Content-Length": "0"}
            )
            response = client.getresponse()
            response.read(4096)
            if 200 <= response.status < 300:
                return {
                    "shutdown_requested": True,
                    "http_status": response.status,
                    "proxy_process_exit_observation": "requires Cloud Run per-container execution readback",
                }
        except (OSError, http.client.HTTPException):
            pass
        finally:
            client.close()
        if attempt < 2:
            time.sleep(0.5)
    raise OperatorError(
        "Proxy shutdown was not acknowledged; job completion is not accepted"
    )


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            raise OperatorError("Exact operator stage and confirmations required")

    parser = Parser(description=__doc__)
    parser.add_argument(
        "stage", choices=("bootstrap", "migrate", "finalize", "readback")
    )
    for name in ("project", "database", "source", "operator"):
        parser.add_argument("--confirm-" + name, required=True)
    report = {
        "version": "ocean-v1-beta-operator-result-v1",
        "stage": None,
        "project_id": PROJECT,
        "database": DATABASE,
        "state": "failed",
    }
    code = 2
    try:
        args = parser.parse_args(argv)
        report["stage"] = args.stage
        validated = validate(
            os.environ,
            stage=args.stage,
            confirm_project=args.confirm_project,
            confirm_database=args.confirm_database,
            confirm_source=args.confirm_source,
            confirm_operator=args.confirm_operator,
        )
        report["source_revision"], report["operator_revision"] = (
            validated["source"],
            validated["operator"],
        )
        report["result"] = run_stage(args.stage, validated, os.environ)
        report["state"], code = "stage_completed", 0
    except OperatorError as exc:
        report["error"] = str(exc)
    except Exception:
        report["error"] = (
            "Beta operator stage failed; retain the private target and inspect safe readbacks"
        )
    finally:
        try:
            report["proxy"] = stop_proxy()
        except Exception:
            report["proxy"] = {
                "shutdown_requested": False,
                "error": "Proxy shutdown not acknowledged",
            }
            report["state"], code = "failed_proxy_shutdown", 3
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
