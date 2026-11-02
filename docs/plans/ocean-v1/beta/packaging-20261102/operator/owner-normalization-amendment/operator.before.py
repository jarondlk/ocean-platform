"""Explicit new-beta database stages; no general SQL or credential CLI input."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from psycopg2 import sql
from psycopg2.extensions import encrypt_password, libpq_version
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
PROBE_ROLE = "ocean_v1_beta_setup_probe"
FLAGS = (
    "ENABLE_V1_RESEARCH_CONTROLLER",
    "ENABLE_V1_RESEARCH_DISPATCH",
    "ENABLE_V1_SYNTHESIS",
    "ENABLE_V1_EXPERIMENT_DISPATCH",
)

PASSWORD_LOGGING_POLICY = {
    "log_statement": "none",
    "log_min_error_statement": "panic",
    "log_duration": "off",
    "log_min_duration_statement": "-1",
    "log_min_duration_sample": "-1",
    "log_transaction_sample_rate": "0",
    "debug_print_parse": "off",
    "debug_print_rewritten": "off",
    "debug_print_plan": "off",
    "log_parser_stats": "off",
    "log_planner_stats": "off",
    "log_executor_stats": "off",
    "log_statement_stats": "off",
    "password_encryption": "scram-sha-256",
}


def attest_password_logging(connection):
    """Read actual session policy before any password-bearing SQL; never SET it.

    SCRAM verifiers are sensitive too. This verifies the reviewed ordinary
    statement/error/duration/sampling/debug paths, not universal log redaction
    or host-memory/crash-dump confidentiality.
    """
    optional = (
        "pgaudit.log",
        "auto_explain.log_min_duration",
        "shared_preload_libraries",
        "pg_stat_statements.track",
        "pg_stat_statements.track_utility",
    )
    names = list(PASSWORD_LOGGING_POLICY) + list(optional)
    observed = dict(
        connection.execute(
            text(
                "SELECT setting_name,current_setting(setting_name,true) FROM "
                "unnest(CAST(:names AS text[])) AS settings(setting_name)"
            ),
            {"names": names},
        ).all()
    )
    for name, expected in PASSWORD_LOGGING_POLICY.items():
        actual = observed.get(name)
        if name == "log_transaction_sample_rate":
            try:
                matches = Decimal(actual) == Decimal(expected)
            except (TypeError, InvalidOperation):
                matches = False
        else:
            matches = actual == expected
        if not matches:
            raise OperatorError(
                "Password SQL logging policy is not attested; no password statement is allowed"
            )
    if observed.get("pgaudit.log") not in {None, "", "none", "off"} or observed.get(
        "auto_explain.log_min_duration"
    ) not in {None, "", "-1"}:
        raise OperatorError(
            "Optional query/audit statement logging is not attested for password SQL"
        )
    pgss_extension = bool(
        connection.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='pg_stat_statements')"
            )
        )
    )
    pgss_preloaded = "pg_stat_statements" in (
        observed.get("shared_preload_libraries") or ""
    )
    pgss_present = (
        pgss_extension
        or pgss_preloaded
        or any(
            observed.get(name) is not None
            for name in ("pg_stat_statements.track", "pg_stat_statements.track_utility")
        )
    )
    if pgss_present and not (
        observed.get("pg_stat_statements.track") == "none"
        or observed.get("pg_stat_statements.track_utility") == "off"
    ):
        raise OperatorError(
            "Credential utility query collection is not attested; no password SQL is allowed"
        )
    if libpq_version() < 100000:
        raise OperatorError("Client SCRAM password preparation is unavailable")
    if connection.connection.driver_connection.server_version < 100000:
        raise OperatorError("Server SCRAM password support is unavailable")
    return {
        "version": "beta-password-sql-log-policy-v1",
        "verified": True,
        "settings": {name: observed[name] for name in PASSWORD_LOGGING_POLICY},
        "optional_statement_traces": "disabled_or_not_loaded",
        "client_scram_supported": True,
        "server_scram_supported": True,
        "utility_query_collection": {
            "pg_stat_statements_present_or_preloaded": pgss_present,
            "present_in_current_database": pgss_extension,
            "preloaded": pgss_preloaded,
            "credential_utility_capture": "disabled" if pgss_present else "not_loaded",
        },
        "qualification": "actual session settings before password SQL; no universal redaction claim",
    }


def prepare_scram(connection, password, role):
    """Use libpq client-side SCRAM only; plaintext never reaches role SQL."""
    try:
        if (
            libpq_version() < 100000
            or connection.connection.driver_connection.server_version < 100000
        ):
            raise ValueError()
        verifier = encrypt_password(
            password,
            role,
            scope=connection.connection.driver_connection,
            algorithm="scram-sha-256",
        )
        if not isinstance(verifier, str) or not re.fullmatch(
            r"SCRAM-SHA-256\$[1-9][0-9]*:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+",
            verifier,
        ):
            raise ValueError()
        return verifier
    except Exception:
        raise OperatorError(
            "Client SCRAM password preparation rejected; no fallback is allowed"
        ) from None


class OperatorError(ValueError):
    """Fixed credential-safe diagnostic only."""


def validate(
    env, *, stage, confirm_project, confirm_database, confirm_source, confirm_operator
):
    if (
        stage not in {"bootstrap", "migrate", "finalize", "readback", "qualify"}
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
    attest_password_logging(connection)
    for role, key in (
        (MIGRATOR, "OCEAN_V1_MIGRATOR_PASSWORD"),
        (SERVING, "OCEAN_V1_SERVING_PASSWORD"),
    ):
        verifier = prepare_scram(connection, env[key], role)
        # Recheck the actual session immediately before binding sensitive material.
        attest_password_logging(connection)
        statement(
            connection,
            "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %s",
            role,
            parameters=(verifier,),
        )
        verifier = None
        statement(
            connection,
            "ALTER ROLE {} IN DATABASE {} SET search_path TO public, pg_catalog",
            role,
            DATABASE,
        )
        # PostgreSQL16+ requires the creator's ADMIN OPTION for another role's
        # defaults. Finish that setup before removing only this new membership.
        statement(connection, "REVOKE {} FROM {}", role, "postgres")
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
    logging_policy = attest_password_logging(connection)
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
        "password_logging_policy": logging_policy,
        "password_preparation": "client-side SCRAM-SHA-256 only",
    }


def provider_safety_readback(connection):
    """Finite provider qualification metadata, with no password/query catalogues.

    pg_settings may hide protected values from a limited principal. Preserve
    that fact rather than bypassing permissions or asserting a privacy pass.
    The strict password-SQL attestation remains independently enforced.
    """
    names = list(PASSWORD_LOGGING_POLICY) + [
        "shared_preload_libraries",
        "pg_stat_statements.track",
        "pg_stat_statements.track_utility",
        "pgaudit.log",
        "auto_explain.log_min_duration",
        "search_path",
    ]
    owners = connection.execute(
        text(
            "SELECT pg_get_userbyid(d.datdba),pg_get_userbyid(n.nspowner) FROM pg_database d "
            "JOIN pg_namespace n ON n.nspname='public' WHERE d.datname=current_database()"
        )
    ).one()
    principal = connection.execute(
        text(
            "SELECT rolname,oid,rolsuper,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls,rolcanlogin "
            "FROM pg_roles WHERE rolname=current_user"
        )
    ).one()
    settings = [
        dict(
            zip(("name", "value", "unit", "source", "context", "pending_restart"), row)
        )
        for row in connection.execute(
            text(
                "SELECT name,setting,unit,source,context,pending_restart FROM pg_settings "
                "WHERE name=ANY(:names) ORDER BY name"
            ),
            {"names": names},
        )
    ]
    overrides = [
        dict(zip(("database", "role", "name", "value"), row))
        for row in connection.execute(
            text(
                "SELECT CASE WHEN s.setdatabase=0 THEN '*' ELSE d.datname END,"
                "CASE WHEN s.setrole=0 THEN '*' ELSE r.rolname END,split_part(v.setting,'=',1),"
                "substring(v.setting FROM position('=' IN v.setting)+1) FROM pg_db_role_setting s "
                "LEFT JOIN pg_database d ON d.oid=s.setdatabase LEFT JOIN pg_roles r ON r.oid=s.setrole "
                "CROSS JOIN LATERAL unnest(s.setconfig) AS v(setting) "
                "WHERE (s.setdatabase=0 OR d.datname=current_database()) "
                "AND (s.setrole=0 OR r.rolname=current_user OR r.rolname=ANY(:roles)) "
                "AND split_part(v.setting,'=',1)=ANY(:names) ORDER BY 1,2,3"
            ),
            {"names": names, "roles": list(ROLES)},
        )
    ]
    return {
        "version": "beta-provider-safety-metadata-v1",
        "database_owner": owners[0],
        "public_schema_owner": owners[1],
        "current_principal": dict(
            zip(
                (
                    "name",
                    "oid",
                    "superuser",
                    "create_role",
                    "create_database",
                    "replication",
                    "bypass_rls",
                    "login",
                ),
                principal,
            )
        ),
        "fixed_settings": settings,
        "matching_role_database_overrides": overrides,
        "protected_values_hidden": any(row["value"] is None for row in settings),
        "password_sql_authorized_by_this_readback": False,
        "qualification": "Metadata only; actual password SQL still requires strict separate attestation",
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
        "provider_safety": provider_safety_readback(connection),
    }


def probe_memberships(connection):
    """Only memberships involving the fixed probe; never password catalogues."""
    rows = connection.execute(
        text(
            "SELECT r.rolname,u.rolname,g.rolname,m.admin_option,m.inherit_option,m.set_option,"
            "r.oid,u.oid,g.oid "
            "FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid "
            "JOIN pg_roles u ON u.oid=m.member JOIN pg_roles g ON g.oid=m.grantor "
            "WHERE r.rolname=:probe OR u.rolname=:probe ORDER BY 1,2,3"
        ),
        {"probe": PROBE_ROLE},
    )
    return [
        dict(
            zip(
                (
                    "role",
                    "member",
                    "grantor",
                    "admin",
                    "inherit",
                    "set",
                    "role_oid",
                    "member_oid",
                    "grantor_oid",
                ),
                row,
            )
        )
        for row in rows
    ]


def qualify(engine):
    """Rollback-only NOLOGIN capability observation; never authorizes bootstrap.

    A creator's automatic ADMIN membership can be granted by another principal.
    Observe that provider behavior instead of assuming REVOKE removes it or
    changing grantors/privileges to force the existing role guard to pass.
    """
    result = {
        "stage": "qualify",
        "probe_role": PROBE_ROLE,
        "sequence_supported": False,
        "bootstrap_authorized": False,
        "password_sql_performed": False,
        "application_roles_created": False,
        "attempted_steps": [],
    }
    with engine.connect() as connection:
        if connection.connection.driver_connection.autocommit is not False:
            raise OperatorError("Qualification requires a real explicit transaction")
        transaction = connection.begin()
        before = None
        try:
            identity(connection, "postgres")
            if connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:probe)"),
                {"probe": PROBE_ROLE},
            ):
                raise OperatorError(
                    "Existing fixed capability probe is refused; it will not be changed"
                )
            before = readback(connection, "postgres")
            result["provider_before"] = before["provider_safety"]
            result["attempted_steps"].append("create_nologin_probe")
            statement(
                connection,
                "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS",
                PROBE_ROLE,
            )
            row = connection.execute(
                text(
                    "SELECT rolname,rolsuper,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls,rolcanlogin FROM pg_roles WHERE rolname=:probe"
                ),
                {"probe": PROBE_ROLE},
            ).one()
            result["probe_attributes"] = dict(
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
            result["memberships_after_create"] = probe_memberships(connection)
            result["attempted_steps"].append("alter_probe_database_defaults")
            statement(
                connection,
                "ALTER ROLE {} IN DATABASE {} SET search_path TO public, pg_catalog",
                PROBE_ROLE,
                DATABASE,
            )
            result["defaults_set"] = True
            result["attempted_steps"].append("revoke_creator_probe_membership")
            statement(connection, "REVOKE {} FROM {}", PROBE_ROLE, "postgres")
            result["memberships_after_revoke"] = probe_memberships(connection)
            result["sequence_supported"] = (
                not any(row[1:]) and not result["memberships_after_revoke"]
            )
            if not result["sequence_supported"]:
                result["refusal_reason"] = (
                    "Restricted probe attributes or zero-membership guard not satisfied"
                )
        except OperatorError:
            raise
        except Exception as error:
            value = getattr(getattr(error, "orig", error), "pgcode", None)
            result["error_code"] = (
                value
                if isinstance(value, str) and re.fullmatch(r"[0-9A-Z]{5}", value)
                else "unclassified"
            )
            result["refusal_reason"] = (
                "Provider refused a scoped capability step; no error text is exported"
            )
        finally:
            transaction.rollback()
            result["transaction_rolled_back"] = not transaction.is_active
        if before is None:
            raise OperatorError(
                "Qualification baseline could not be read; no capability claim is permitted"
            )
    # A distinct physical session must verify absence, not a pooled old snapshot.
    engine.dispose()
    with engine.connect() as connection:
        identity(connection, "postgres")
        result["probe_absent_after_rollback"] = not connection.scalar(
            text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:probe)"),
            {"probe": PROBE_ROLE},
        )
        after = readback(connection, "postgres")
        result["application_role_inventory_unchanged"] = (
            after["roles"] == before["roles"]
        )
        result["application_table_inventory_unchanged"] = (
            after["tables"] == before["tables"]
        )
        result["readback"] = after
    if not all(
        result.get(name) is True
        for name in (
            "transaction_rolled_back",
            "probe_absent_after_rollback",
            "application_role_inventory_unchanged",
            "application_table_inventory_unchanged",
        )
    ):
        result["sequence_supported"] = False
        result["refusal_reason"] = (
            "Rollback/absence or unchanged inventory not established; inspect target"
        )
    return result


def verify_serving_privileges(connection, allowed):
    """Audit effective rights, including PUBLIC and column-only delegations.

    information_schema.role_table_grants excludes PUBLIC and column-only ACLs.
    Use PostgreSQL's effective privilege functions and inspect PUBLIC ACLs on
    every non-system relation/column instead. The policy has no sequence rights.
    """
    user_schema = "n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'"
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "CROSS JOIN LATERAL aclexplode(c.relacl) acl WHERE "
            + user_schema
            + " AND c.relkind IN ('r','p','v','m','f','S') AND acl.grantee=0) OR "
            "EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(a.attacl) acl "
            "WHERE "
            + user_schema
            + " AND a.attnum>0 AND NOT a.attisdropped AND acl.grantee=0)"
        )
    ):
        raise OperatorError(
            "PUBLIC has unexpected relation or column access; refusing an automatic reset"
        )
    policy = [
        ("public", table, privilege)
        for table, privileges in allowed.items()
        for privilege in sorted(privileges)
    ]
    parameters = {"role": SERVING}
    policy_rows = []
    for number, (schema, table, privilege) in enumerate(policy):
        parameters.update(
            {f"s{number}": schema, f"t{number}": table, f"p{number}": privilege}
        )
        policy_rows.append(f"(:s{number},:t{number},:p{number})")
    cte = (
        "WITH policy(schema_name,table_name,privilege_type) AS (VALUES "
        + ",".join(policy_rows)
        + ") "
    )
    table_privileges = [
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "REFERENCES",
        "TRIGGER",
    ]
    if (
        int(connection.scalar(text("SELECT current_setting('server_version_num')")))
        >= 170000
    ):
        table_privileges.append("MAINTAIN")
    for privilege in table_privileges:
        parameters["privilege"] = privilege
        parameters["grantable_privilege"] = privilege + " WITH GRANT OPTION"
        unexpected = connection.scalar(
            text(
                cte
                + "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
                + user_schema
                + " AND c.relkind IN ('r','p','v','m','f') "
                "AND has_table_privilege(:role,c.oid,:privilege) AND "
                "(has_table_privilege(:role,c.oid,:grantable_privilege) OR NOT EXISTS "
                "(SELECT 1 FROM policy p WHERE p.schema_name=n.nspname AND p.table_name=c.relname "
                "AND p.privilege_type=:privilege)))"
            ),
            parameters,
        )
        if unexpected:
            raise OperatorError(
                "Serving has unexpected effective table rights; refusing an automatic reset"
            )
    for privilege in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
        parameters["privilege"] = privilege
        parameters["grantable_privilege"] = privilege + " WITH GRANT OPTION"
        unexpected = connection.scalar(
            text(
                cte
                + "SELECT EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
                + user_schema
                + " AND c.relkind IN ('r','p','v','m','f') AND a.attnum>0 AND NOT a.attisdropped "
                "AND has_column_privilege(:role,c.oid,a.attnum,:privilege) AND "
                "(has_column_privilege(:role,c.oid,a.attnum,:grantable_privilege) OR NOT EXISTS "
                "(SELECT 1 FROM policy p WHERE p.schema_name=n.nspname AND p.table_name=c.relname "
                "AND p.privilege_type=:privilege)))"
            ),
            parameters,
        )
        if unexpected:
            raise OperatorError(
                "Serving has unexpected effective column rights; refusing an automatic reset"
            )
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE " + user_schema + " AND CASE WHEN c.relkind='S' "
            "THEN has_sequence_privilege(:role,c.oid,'USAGE,SELECT,UPDATE') ELSE false END)"
        ),
        {"role": SERVING},
    ):
        raise OperatorError(
            "Serving has unexpected sequence rights; refusing an automatic reset"
        )


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
    verify_serving_privileges(connection, allowed)
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
    verify_serving_privileges(connection, allowed)
    return {
        "stage": "finalize",
        "roles": roles,
        "serving_grants": {table: sorted(rights) for table, rights in allowed.items()},
        "all_tables_grant": False,
        "effective_table_and_column_rights_verified": True,
        "public_relation_and_column_acl_absent": True,
        "account_enrollment_performed": False,
    }


def run_stage(stage, validated, env):
    if stage == "qualify":
        engine = connect(validated["dsn"])
        try:
            return qualify(engine)
        finally:
            engine.dispose()
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
        "stage", choices=("bootstrap", "migrate", "finalize", "readback", "qualify")
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
        if args.stage == "qualify":
            report["state"], code = (
                ("qualification_observed", 0)
                if report["result"]["sequence_supported"]
                else ("qualification_refused", 2)
            )
        else:
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
