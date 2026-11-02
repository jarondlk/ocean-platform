"""Owned PostgreSQL18 qualification of16+ non-superuser creator semantics."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
from unittest.mock import patch

from psycopg2 import Error as DriverError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent
BIN = Path("/opt/homebrew/opt/postgresql@18/bin")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", required=True)
    args = parser.parse_args()
    if not args.run_directory.replace("-", "").isalnum():
        parser.error("New simple run name required")
    output = HERE / args.run_directory
    output.mkdir(exist_ok=False)
    current = load("new_order_operator", ROOT / "deploy/gcp/beta/operator/operator.py")
    old = load("old_order_operator", HERE / "operator.before.py")
    temporary = Path(
        tempfile.mkdtemp(prefix="ocean-beta-role-order-", dir="/private/tmp")
    )
    cluster, unix = temporary / "pg", temporary / "socket"
    unix.mkdir()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    result = {
        "version": "beta-bootstrap-order-native-v1",
        "state": "failed",
        "checks": [],
        "commands": [],
        "native_version": "PostgreSQL18.3, qualifies16+ core role semantics; notCloudSQL",
        "cloud_actions": False,
        "managed_vector_extension_bootstrap_qualified": False,
    }
    engines = []
    started = False
    sensitive = []

    def check(name, condition):
        result["checks"].append({"name": name, "passed": bool(condition)})
        assert condition, name

    def command(name, argv, expected=0):
        value = subprocess.run(
            argv, capture_output=True, text=True, timeout=60, check=False
        )
        (output / (name + ".stdout")).write_text(value.stdout)
        (output / (name + ".stderr")).write_text(value.stderr)
        result["commands"].append(
            {"name": name, "returncode": value.returncode, "expected": expected}
        )
        assert value.returncode == expected, name

    try:
        admin_password, postgres_password, migrator_password, serving_password = (
            secrets.token_urlsafe(48) for _ in range(4)
        )
        sensitive.extend(
            (admin_password, postgres_password, migrator_password, serving_password)
        )
        password_file = temporary / "password"
        password_file.write_text(admin_password + "\n")
        password_file.chmod(0o600)
        command(
            "initdb",
            [
                str(BIN / "initdb"),
                "-D",
                str(cluster),
                "--username=native_admin",
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
        started = True
        admin_url = URL.create(
            "postgresql+psycopg2",
            username="native_admin",
            password=admin_password,
            host="127.0.0.1",
            port=port,
            database="postgres",
        )
        admin = create_engine(
            admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True
        )
        engines.append(admin)
        with admin.connect() as connection:
            current.attest_password_logging(connection)
            verifier = current.prepare_scram(connection, postgres_password, "postgres")
            sensitive.append(verifier)
            current.statement(
                connection,
                "CREATE ROLE {} LOGIN NOSUPERUSER CREATEROLE CREATEDB NOREPLICATION NOBYPASSRLS PASSWORD %s",
                "postgres",
                parameters=(verifier,),
            )
            connection.exec_driver_sql("GRANT pg_read_all_settings TO postgres")
            connection.exec_driver_sql("CREATE DATABASE ocean_v1_beta OWNER postgres")
        postgres_url = admin_url.set(
            username="postgres", password=postgres_password, database=current.DATABASE
        )
        postgres = create_engine(postgres_url, hide_parameters=True)
        engines.append(postgres)
        env = {
            "OCEAN_V1_MIGRATOR_PASSWORD": migrator_password,
            "OCEAN_V1_SERVING_PASSWORD": serving_password,
        }
        with postgres.connect() as connection:
            current.identity(connection, "postgres")
            flags = connection.execute(
                text(
                    "SELECT rolsuper,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user"
                )
            ).one()
            check(
                "actual creator is non-superuser CREATEROLE and database owner",
                tuple(flags) == (False, True, True),
            )
            check(
                "logging policy attested for the limited creator",
                current.attest_password_logging(connection)["verified"],
            )
        old_steps = []
        old_statement = old.statement

        def old_spy(connection, template, *identifiers, parameters=None):
            old_steps.append(
                "alter_defaults"
                if template.startswith("ALTER ROLE")
                else "revoke_creator"
                if template.startswith("REVOKE {} FROM")
                else "other"
            )
            if "PASSWORD %s" in template:
                sensitive.append(parameters[0])
            return old_statement(
                connection, template, *identifiers, parameters=parameters
            )

        try:
            with patch.object(old, "statement", side_effect=old_spy):
                with postgres.begin() as connection:
                    old.create_roles(connection, env)
        except (DBAPIError, DriverError) as error:
            code = getattr(getattr(error, "orig", error), "pgcode", None)
            check(
                "old order fails specifically at defaults after creator revocation",
                code == "42501"
                and old_steps[-2:] == ["revoke_creator", "alter_defaults"],
            )
            result["old_order_error_code"] = code
        else:
            raise AssertionError("old order unexpectedly succeeded")
        with postgres.connect() as connection:
            check(
                "old-order failure rolls back both new roles",
                not connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=ANY(:names))"
                    ),
                    {"names": list(current.ROLES)},
                ),
            )
        new_steps = []
        new_statement = current.statement

        def new_spy(connection, template, *identifiers, parameters=None):
            if "PASSWORD %s" in template:
                sensitive.append(parameters[0])
                new_steps.append(("password", identifiers[0]))
            elif template.startswith("ALTER ROLE"):
                new_steps.append(("alter_defaults", identifiers[0]))
            elif template.startswith("REVOKE {} FROM"):
                new_steps.append(("revoke_creator", identifiers[0]))
            return new_statement(
                connection, template, *identifiers, parameters=parameters
            )

        with patch.object(current, "statement", side_effect=new_spy):
            with postgres.begin() as connection:
                roles = current.create_roles(connection, env)
        expected = [
            (stage, role)
            for role in current.ROLES
            for stage in ("password", "alter_defaults", "revoke_creator")
        ]
        check(
            "corrected order sets defaults before revoking each new creator membership",
            new_steps == expected,
        )
        check(
            "corrected restricted role creation succeeds as non-superuser",
            len(roles) == 2,
        )
        with postgres.connect() as connection:
            check(
                "final role memberships and attributes remain restricted",
                len(current.assert_restricted_roles(connection)) == 2,
            )
        clients = {}
        for role, password in [
            (current.MIGRATOR, migrator_password),
            (current.SERVING, serving_password),
        ]:
            engine = create_engine(
                postgres_url.set(username=role, password=password), hide_parameters=True
            )
            engines.append(engine)
            clients[role] = engine
            with engine.connect() as connection:
                current.identity(connection, role)
                check(role + " actually authenticates with SCRAM", True)
                check(
                    role + " database default resolves public schema",
                    connection.scalar(text("SELECT current_schema()")) == "public",
                )
        with clients[current.MIGRATOR].begin() as connection:
            connection.exec_driver_sql(
                "ALTER ROLE ocean_v1_migrator IN DATABASE ocean_v1_beta SET application_name='native-unexported-marker'"
            )
        with postgres.connect() as connection:
            metadata = current.readback(connection, "postgres")
            safety = metadata["provider_safety"]
            check(
                "additive readback preserves original metadata meaning",
                metadata["database"] == current.DATABASE
                and metadata["principal"] == "postgres"
                and metadata["migration_versions"] == []
                and metadata["C23_execution_enabled"] is False,
            )
            check(
                "provider readback reports actual database and public schema owners",
                safety["database_owner"] == "postgres"
                and safety["public_schema_owner"] == "pg_database_owner",
            )
            check(
                "provider readback identifies limited creator attributes",
                safety["current_principal"]["superuser"] is False
                and safety["current_principal"]["create_role"] is True,
            )
            check(
                "fixed settings include context/source/pending restart without hidden values",
                not safety["protected_values_hidden"]
                and all(
                    {"name", "value", "context", "source", "pending_restart"}
                    <= set(row)
                    for row in safety["fixed_settings"]
                ),
            )
            paths = [
                row
                for row in safety["matching_role_database_overrides"]
                if row["name"] == "search_path"
            ]
            check(
                "finite role/database defaults show both corrected search paths",
                {row["role"] for row in paths} == set(current.ROLES)
                and all(row["value"] == "public, pg_catalog" for row in paths),
            )
            check(
                "unlisted role setting values are not exported",
                "native-unexported-marker" not in json.dumps(metadata),
            )
            check(
                "readback never authorizes password SQL by itself",
                safety["password_sql_authorized_by_this_readback"] is False,
            )
            check(
                "provider metadata contains neither credentials nor verifier material",
                not any(marker in json.dumps(metadata) for marker in sensitive)
                and "SCRAM-SHA-256$" not in json.dumps(metadata),
            )
            result["provider_readback"] = metadata
        with clients[current.SERVING].connect() as connection:
            check(
                "serving still cannot create public schema objects",
                not connection.scalar(
                    text("SELECT has_schema_privilege(current_user,'public','CREATE')")
                ),
            )
        result["state"] = "passed"
    except Exception as error:
        result["failure_type"] = type(error).__name__
    finally:
        for engine in engines:
            engine.dispose()
        if started:
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
            command(
                "pg-stopped",
                [str(BIN / "pg_ctl"), "-D", str(cluster), "status"],
                expected=3,
            )
        with socket.socket() as probe:
            closed = probe.connect_ex(("127.0.0.1", port)) != 0
        result["cleanup"] = {
            "port_closed": closed,
            "postmaster_pid_absent": not (cluster / "postmaster.pid").exists(),
        }
        if (temporary / "postgres.log").exists():
            log = (temporary / "postgres.log").read_text()
            safe = (
                not any(marker in log for marker in sensitive)
                and "SCRAM-SHA-256$" not in log
            )
            check(
                "whole owned server log excludes synthetic plaintext and verifier material",
                safe,
            )
            if safe:
                shutil.copyfile(temporary / "postgres.log", output / "postgres.stdout")
            else:
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
    assert all(result["cleanup"].values())
    if result["state"] != "passed":
        raise SystemExit(
            "Owned non-superuser qualification failed; inspect fixed metadata"
        )
    print(
        json.dumps(
            {
                "state": result["state"],
                "checks": len(result["checks"]),
                "cleanup": result["cleanup"],
            }
        )
    )


if __name__ == "__main__":
    main()
