"""Owned PG18 A/B creator qualification; root must launch after reviewing source.

Each invocation owns one disposable cluster and synthetic credentials. No cloud,
provider credentials, API migrations, vector bootstrap or application rows.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent
BIN = Path("/opt/homebrew/opt/postgresql@18/bin")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument(
        "--profile", choices=("other-grantor", "self-grantor"), required=True
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", args.run_directory):
        parser.error("New simple run-directory name required")
    output = HERE / args.run_directory
    output.mkdir(exist_ok=False)
    current = load(
        "qualified_current_operator", ROOT / "deploy/gcp/beta/operator/operator.py"
    )
    old = load("qualified_old_operator", HERE / "operator.before.py")
    temporary = Path(
        tempfile.mkdtemp(prefix="ocean-beta-creator-probe-", dir="/private/tmp")
    )
    cluster, unix = temporary / "pg", temporary / "socket"
    unix.mkdir()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    result = {
        "version": "beta-rollback-probe-native-v1",
        "profile": args.profile,
        "state": "failed",
        "checks": [],
        "commands": [],
        "cloud_actions": False,
        "managed_cloudsql_qualification_claimed": False,
        "vector_bootstrap_or_migrations_performed": False,
        "server_log_exported": False,
    }
    engines, sensitive = [], []

    def check(name, condition):
        result["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    def command(name, argv, expected=0):
        process = subprocess.run(
            argv, capture_output=True, text=True, timeout=60, check=False
        )
        # Commands have only fixed local paths/options, never credentials or SQL.
        (output / (name + ".stdout")).write_text(process.stdout)
        (output / (name + ".stderr")).write_text(process.stderr)
        result["commands"].append(
            {"name": name, "returncode": process.returncode, "expected": expected}
        )
        if process.returncode != expected:
            raise AssertionError(name)

    def role_inventory(engine):
        with engine.connect() as connection:
            return connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=ANY(:names))"),
                {"names": list(current.ROLES)},
            )

    def role_password(connection, role, password, attributes):
        current.attest_password_logging(connection)
        verifier = current.prepare_scram(connection, password, role)
        sensitive.append(verifier)
        current.attest_password_logging(connection)
        current.statement(
            connection,
            "CREATE ROLE {} " + attributes + " PASSWORD %s",
            role,
            parameters=(verifier,),
        )

    def exercise_order(module, engine, env):
        steps, after_revokes = [], []
        original = module.statement

        def tracked(connection, template, *names, parameters=None):
            if "PASSWORD %s" in template:
                sensitive.append(parameters[0])
                steps.append(("password", names[0]))
            elif template.startswith("ALTER ROLE"):
                steps.append(("alter_defaults", names[0]))
            elif template.startswith("REVOKE {} FROM"):
                steps.append(("revoke_creator", names[0]))
            value = original(connection, template, *names, parameters=parameters)
            if template.startswith("REVOKE {} FROM"):
                rows = connection.execute(
                    text(
                        "SELECT g.rolname,m.admin_option FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles g ON g.oid=m.grantor WHERE r.rolname=:role"
                    ),
                    {"role": names[0]},
                ).all()
                after_revokes.append(
                    {
                        "role": names[0],
                        "memberships": [
                            {"grantor": row[0], "admin": row[1]} for row in rows
                        ],
                    }
                )
            return value

        try:
            with patch.object(module, "statement", side_effect=tracked):
                with engine.begin() as connection:
                    roles = module.create_roles(connection, env)
            return {
                "outcome": "succeeded",
                "roles_count": len(roles),
                "steps": steps,
                "after_revokes": after_revokes,
            }
        except Exception as error:
            value = getattr(getattr(error, "orig", error), "pgcode", None)
            code = (
                value
                if isinstance(value, str) and re.fullmatch(r"[0-9A-Z]{5}", value)
                else None
            )
            return {
                "outcome": "refused",
                "error_type": type(error).__name__,
                "sqlstate": code,
                "steps": steps,
                "after_revokes": after_revokes,
            }

    try:
        passwords = {
            name: secrets.token_urlsafe(48)
            for name in ("initial", "alternate", "postgres", "migrator", "serving")
        }
        sensitive.extend(passwords.values())
        initial_user = "native_admin" if args.profile == "other-grantor" else "postgres"
        password_file = temporary / "initial-password"
        password_file.write_text(passwords["initial"] + "\n")
        password_file.chmod(0o600)
        command(
            "initdb",
            [
                str(BIN / "initdb"),
                "-D",
                str(cluster),
                "--username=" + initial_user,
                "--no-locale",
                "--auth-local=trust",
                "--auth-host=scram-sha-256",
                "--pwfile=" + str(password_file),
            ],
        )
        password_file.unlink()
        with (cluster / "postgresql.conf").open("a") as handle:
            for name, value in current.PASSWORD_LOGGING_POLICY.items():
                handle.write("\n" + name + " = '" + value + "'\n")
            handle.write(
                "shared_preload_libraries = 'pg_stat_statements'\npg_stat_statements.track_utility = 'off'\n"
            )
        command(
            "pg-start",
            [
                str(BIN / "pg_ctl"),
                "-D",
                str(cluster),
                "-l",
                str(temporary / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {port} -k {unix}",
                "-w",
                "start",
            ],
        )
        initial_url = URL.create(
            "postgresql+psycopg2",
            username=initial_user,
            password=passwords["initial"],
            host="127.0.0.1",
            port=port,
            database="postgres",
        )
        initial = create_engine(
            initial_url, isolation_level="AUTOCOMMIT", hide_parameters=True
        )
        engines.append(initial)
        with initial.connect() as connection:
            result["server_version"] = connection.scalar(text("SELECT version()"))
            check(
                "fixture uses actual PostgreSQL18, not a managed PostgreSQL16 claim",
                int(
                    connection.scalar(
                        text("SELECT current_setting('server_version_num')")
                    )
                )
                // 10000
                == 18,
            )
            if args.profile == "other-grantor":
                role_password(
                    connection,
                    "postgres",
                    passwords["postgres"],
                    "LOGIN NOSUPERUSER CREATEROLE CREATEDB NOREPLICATION NOBYPASSRLS",
                )
                admin = initial
            else:
                role_password(
                    connection,
                    "alternate_native_admin",
                    passwords["alternate"],
                    "LOGIN SUPERUSER",
                )
                alternate_url = initial_url.set(
                    username="alternate_native_admin", password=passwords["alternate"]
                )
                admin = create_engine(
                    alternate_url, isolation_level="AUTOCOMMIT", hide_parameters=True
                )
                engines.append(admin)
            connection.exec_driver_sql("CREATE DATABASE ocean_v1_beta OWNER postgres")
        with admin.connect() as connection:
            connection.exec_driver_sql("GRANT pg_read_all_settings TO postgres")
            if args.profile == "self-grantor":
                connection.exec_driver_sql(
                    "ALTER ROLE postgres NOSUPERUSER CREATEROLE CREATEDB NOREPLICATION NOBYPASSRLS"
                )
        postgres_url = initial_url.set(
            username="postgres",
            password=passwords["postgres"]
            if args.profile == "other-grantor"
            else passwords["initial"],
            database=current.DATABASE,
        )
        postgres = create_engine(postgres_url, hide_parameters=True)
        engines.append(postgres)
        with postgres.connect() as connection:
            metadata = current.readback(connection, "postgres")
            safety = metadata["provider_safety"]
            actor = safety["current_principal"]
            result["provider_before"] = safety
            check(
                "actual creator is non-superuser CREATEROLE and owns the new database",
                actor["superuser"] is False
                and actor["create_role"] is True
                and actor["create_database"] is True
                and safety["database_owner"] == "postgres",
            )
            check(
                "fixture distinguishes bootstrap-superuser OID10 identity",
                (actor["oid"] == 10) == (args.profile == "self-grantor"),
            )
            check(
                "strict password logging/utility collector attestation holds before role SQL",
                current.attest_password_logging(connection)["verified"],
            )
            check(
                "native-only read-all-settings fixture grant exposes finite metadata",
                not safety["protected_values_hidden"]
                and all(
                    {"source", "context", "pending_restart", "value"} <= set(row)
                    for row in safety["fixed_settings"]
                ),
            )
            check(
                "provider readback never authorizes password SQL",
                safety["password_sql_authorized_by_this_readback"] is False,
            )
        probe_steps = []
        original = current.statement

        def probe_statement(connection, template, *names, parameters=None):
            check(
                "qualifier SQL is fixed NOLOGIN/default/revoke with no password binding",
                names[0] == current.PROBE_ROLE
                and parameters is None
                and "PASSWORD" not in template
                and template.startswith(("CREATE ROLE", "ALTER ROLE", "REVOKE")),
            )
            probe_steps.append(template)
            return original(connection, template, *names, parameters=parameters)

        with (
            patch.object(current, "statement", side_effect=probe_statement),
            patch.object(
                current,
                "prepare_scram",
                side_effect=AssertionError("probe may not prepare passwords"),
            ),
        ):
            observed = current.qualify(postgres)
        result["probe_observation"] = observed
        supported = args.profile == "self-grantor"
        check(
            "rollback-only probe observes provider behavior without authorizing bootstrap",
            observed["sequence_supported"] == supported
            and observed["bootstrap_authorized"] is False
            and observed["password_sql_performed"] is False
            and observed["application_roles_created"] is False,
        )
        check(
            "probe ALTER precedes REVOKE and only three scoped statements run",
            len(probe_steps) == 3
            and probe_steps[1].startswith("ALTER ROLE")
            and probe_steps[2].startswith("REVOKE"),
        )
        check(
            "probe automatic grantor is OID10 in each distinct fixture",
            len(observed["memberships_after_create"]) == 1
            and observed["memberships_after_create"][0]["grantor_oid"] == 10
            and (observed["memberships_after_create"][0]["member_oid"] == 10)
            == supported,
        )
        check(
            "probe always rolls back and verifies absence in a new physical session",
            observed["transaction_rolled_back"]
            and observed["probe_absent_after_rollback"]
            and observed["application_role_inventory_unchanged"]
            and observed["application_table_inventory_unchanged"]
            and not role_inventory(postgres),
        )
        env = {
            "OCEAN_V1_MIGRATOR_PASSWORD": passwords["migrator"],
            "OCEAN_V1_SERVING_PASSWORD": passwords["serving"],
        }
        prior = exercise_order(old, postgres, env)
        result["old_order"] = prior
        if supported:
            check(
                "old REVOKE-before-ALTER fails42501 for actual limited OID10 creator",
                prior["outcome"] == "refused"
                and prior["sqlstate"] == "42501"
                and prior["steps"][-2:]
                == [
                    ("revoke_creator", current.MIGRATOR),
                    ("alter_defaults", current.MIGRATOR),
                ],
            )
        else:
            check(
                "old order honestly refuses remaining other-grantor memberships",
                prior["outcome"] == "refused"
                and prior["error_type"] == "OperatorError"
                and prior["sqlstate"] is None
                and all(row["memberships"] for row in prior["after_revokes"]),
            )
        check(
            "old order refusal rolls back both application roles",
            not role_inventory(postgres),
        )
        revised = exercise_order(current, postgres, env)
        result["corrected_order"] = revised
        expected_steps = [
            (step, role)
            for role in current.ROLES
            for step in ("password", "alter_defaults", "revoke_creator")
        ]
        check(
            "corrected source sets defaults before revoking each creator membership",
            revised["steps"] == expected_steps,
        )
        if supported:
            check(
                "corrected role helper succeeds without weakening final membership guard",
                revised["outcome"] == "succeeded"
                and revised["roles_count"] == 2
                and all(not row["memberships"] for row in revised["after_revokes"]),
            )
            with postgres.connect() as connection:
                check(
                    "final roles retain exact restricted attributes and zero memberships",
                    len(current.assert_restricted_roles(connection)) == 2,
                )
            for role, password in (
                (current.MIGRATOR, passwords["migrator"]),
                (current.SERVING, passwords["serving"]),
            ):
                client = create_engine(
                    postgres_url.set(username=role, password=password),
                    hide_parameters=True,
                )
                engines.append(client)
                with client.connect() as connection:
                    current.identity(connection, role)
                    check(
                        role
                        + " authenticates with client-prepared SCRAM and correct public default",
                        connection.scalar(text("SELECT current_schema()")) == "public",
                    )
                    if role == current.SERVING:
                        check(
                            "serving cannot create public schema objects",
                            not connection.scalar(
                                text(
                                    "SELECT has_schema_privilege(current_user,'public','CREATE')"
                                )
                            ),
                        )
            with postgres.connect() as connection:
                metadata = current.readback(connection, "postgres")
                paths = [
                    row
                    for row in metadata["provider_safety"][
                        "matching_role_database_overrides"
                    ]
                    if row["name"] == "search_path"
                ]
                check(
                    "finite readback reports both role database defaults",
                    {row["role"] for row in paths} == set(current.ROLES)
                    and all(row["value"] == "public, pg_catalog" for row in paths),
                )
                check(
                    "readback preserves gated execution and no migration/science claims",
                    metadata["migration_versions"] == []
                    and metadata["C23_execution_enabled"] is False
                    and metadata["cloudsql_limited_superuser_qualification_claimed"]
                    is False,
                )
        else:
            check(
                "corrected order preserves refusal for unsupported grantor profile",
                revised["outcome"] == "refused"
                and revised["error_type"] == "OperatorError"
                and revised["sqlstate"] is None
                and all(row["memberships"] for row in revised["after_revokes"]),
            )
            check(
                "unsupported corrected order rolls back both app roles",
                not role_inventory(postgres),
            )
        check(
            "exported metadata excludes synthetic plaintext and SCRAM material",
            not any(value in json.dumps(result) for value in sensitive)
            and "SCRAM-SHA-256$" not in json.dumps(result),
        )
        result["state"] = "passed"
    except Exception as error:
        result["failure_type"] = type(error).__name__
    finally:
        for engine in engines:
            engine.dispose()
        try:
            if (cluster / "postmaster.pid").exists():
                command(
                    "pg-stop",
                    [
                        str(BIN / "pg_ctl"),
                        "-D",
                        str(cluster),
                        "-m",
                        "immediate",
                        "-w",
                        "stop",
                    ],
                )
            if cluster.exists():
                command(
                    "pg-stopped",
                    [str(BIN / "pg_ctl"), "-D", str(cluster), "status"],
                    expected=3,
                )
        except Exception as error:
            result["cleanup_failure_type"] = type(error).__name__
            result["state"] = "failed"
        with socket.socket() as listener:
            closed = listener.connect_ex(("127.0.0.1", port)) != 0
        result["cleanup"] = {
            "port_closed": closed,
            "postmaster_pid_absent": not (cluster / "postmaster.pid").exists(),
        }
        if (temporary / "postgres.log").exists():
            log = (temporary / "postgres.log").read_bytes()
            safe = (
                not any(value.encode() in log for value in sensitive)
                and b"SCRAM-SHA-256$" not in log
            )
            result["checks"].append(
                {
                    "name": "whole multiline server-log byte stream excludes every synthetic plaintext and verifier",
                    "passed": safe,
                }
            )
            if not safe:
                result["state"] = "failed_sensitive_log_not_exported"
        shutil.rmtree(temporary)
        result["cleanup"]["temporary_removed"] = not temporary.exists()
        paths = [
            ROOT / "deploy/gcp/beta/operator/operator.py",
            HERE / "operator.before.py",
            Path(__file__).resolve(),
        ]
        result["source_pins"] = {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        }
        result["artifacts"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in output.iterdir()
            if path.is_file()
        }
        (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    if result["state"] != "passed" or not all(result["cleanup"].values()):
        raise SystemExit(
            "Native creator qualification failed; inspect fixed metadata only"
        )
    print(
        json.dumps(
            {
                "profile": args.profile,
                "state": result["state"],
                "checks": len(result["checks"]),
                "cleanup": result["cleanup"],
            }
        )
    )


if __name__ == "__main__":
    main()
