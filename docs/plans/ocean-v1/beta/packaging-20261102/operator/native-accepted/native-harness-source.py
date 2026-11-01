"""Owned native PostgreSQL/SCRAM/grant and loopback-finalizer qualification."""

from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
from threading import Thread
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent
BIN = Path("/opt/homebrew/opt/postgresql@18/bin")
VECTOR = Path("/opt/homebrew/Cellar/pgvector/0.8.7")


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", required=True)
    arguments = parser.parse_args()
    if not arguments.run_directory.replace("-", "").isalnum():
        parser.error("Use a new simple owned run directory name")
    output = HERE / arguments.run_directory
    output.mkdir(exist_ok=False)
    owned = Path(tempfile.mkdtemp(prefix="ocean-beta-operator-pg-", dir="/private/tmp"))
    cluster, unix = owned / "pg", owned / "socket"
    unix.mkdir()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    result = {
        "version": "beta-operator-native-v1",
        "state": "failed",
        "checks": [],
        "commands": [],
        "native_version": "PostgreSQL18.3 and pgvector0.8.7, not CloudSQL16",
        "cloud_actions": False,
        "scientific_data": False,
        "owned_directory": str(owned),
    }
    started = False
    engines = []

    def check(name, condition):
        result["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    def command(name, argv, expected=0):
        child = subprocess.run(
            argv, capture_output=True, text=True, timeout=60, check=False
        )
        (output / (name + ".stdout")).write_text(child.stdout)
        (output / (name + ".stderr")).write_text(child.stderr)
        result["commands"].append(
            {"name": name, "returncode": child.returncode, "expected": expected}
        )
        if child.returncode != expected:
            raise AssertionError(name)

    try:
        password = secrets.token_urlsafe(48)
        password_file = owned / "postgres-password"
        password_file.write_text(password + "\n")
        password_file.chmod(0o600)
        command(
            "initdb",
            [
                str(BIN / "initdb"),
                "-D",
                str(cluster),
                "--username=postgres",
                "--auth-local=trust",
                "--auth-host=scram-sha-256",
                "--pwfile=" + str(password_file),
                "--no-locale",
            ],
        )
        password_file.unlink()
        extension = owned / "extension"
        extension.mkdir()
        for source in (VECTOR / "share/postgresql@18/extension").glob("vector*"):
            shutil.copyfile(source, extension / source.name)
        control = extension / "vector.control"
        control.write_text(
            control.read_text().replace(
                "'$libdir/vector'", repr(str(VECTOR / "lib/postgresql@18/vector"))
            )
        )
        with (cluster / "postgresql.conf").open("a") as handle:
            handle.write(
                "\nextension_control_path = '" + str(extension) + ":$system'\n"
            )
        command(
            "pg-start",
            [
                str(BIN / "pg_ctl"),
                "-D",
                str(cluster),
                "-l",
                str(owned / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {port} -k {unix}",
                "-w",
                "start",
            ],
        )
        started = True
        operator = module(
            "beta_native_operator", ROOT / "deploy/gcp/beta/operator/operator.py"
        )
        context = module(
            "beta_native_api_context", ROOT / "deploy/gcp/beta/api/prepare_context.py"
        )
        admin_url = URL.create(
            "postgresql+psycopg2",
            username="postgres",
            password=password,
            host="127.0.0.1",
            port=port,
            database="postgres",
        )
        admin = create_engine(
            admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True
        )
        engines.append(admin)
        with admin.connect() as connection:
            connection.exec_driver_sql("CREATE DATABASE ocean_v1_beta OWNER postgres")
        postgres_url = admin_url.set(database="ocean_v1_beta")
        postgres = create_engine(postgres_url, hide_parameters=True)
        engines.append(postgres)
        env = {key: value for key, value in os.environ.items() if key != "DATABASE_URL"}
        env.update(
            DEPLOYMENT_ENV="production",
            OCEAN_V1_PROJECT_ID=operator.PROJECT,
            OCEAN_V1_SQL_CONNECTION_NAME=operator.CONNECTION,
            OCEAN_V1_MIGRATOR_PASSWORD=secrets.token_urlsafe(48),
            OCEAN_V1_SERVING_PASSWORD=secrets.token_urlsafe(48),
        )
        for name in operator.FLAGS:
            env[name] = "false"
        with postgres.begin() as connection:
            observed = operator.bootstrap(connection, env)
        check(
            "fresh bootstrap creates actual vector extension",
            observed["extension"]["version"] == "0.8.7",
        )
        with postgres.connect() as connection:
            check(
                "bootstrap creates no application table",
                not operator.readback(connection, "postgres")["tables"],
            )
            roles = operator.assert_restricted_roles(connection)
            check(
                "two actual restricted roles have no admin attributes or memberships",
                len(roles) == 2,
            )
        try:
            with postgres.begin() as connection:
                operator.bootstrap(connection, env)
        except operator.OperatorError:
            check(
                "bootstrap retry refuses existing state rather than resetting roles",
                True,
            )
        else:
            raise AssertionError("bootstrap retry accepted")
        migrator_url = postgres_url.set(
            username=operator.MIGRATOR, password=env["OCEAN_V1_MIGRATOR_PASSWORD"]
        )
        serving_url = postgres_url.set(
            username=operator.SERVING, password=env["OCEAN_V1_SERVING_PASSWORD"]
        )
        migrator = create_engine(migrator_url, hide_parameters=True)
        serving = create_engine(serving_url, hide_parameters=True)
        engines.extend([migrator, serving])
        with migrator.connect() as connection:
            operator.identity(connection, operator.MIGRATOR)
            check("migrator authenticates over actual SCRAM connection", True)
        with serving.connect() as connection:
            operator.identity(connection, operator.SERVING)
            check("serving authenticates over actual distinct SCRAM connection", True)
        application = owned / "application"
        for source in context.selected_sources():
            destination = application / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        shutil.copyfile(
            ROOT / "deploy/gcp/beta/api/entry.py", application / "beta_entry.py"
        )
        with patch.object(operator, "ROOT", application):
            migrated = operator.run_stage(
                "migrate",
                {
                    "dsn": migrator_url.render_as_string(hide_password=False),
                    "user": operator.MIGRATOR,
                },
                env,
            )
        check(
            "existing guarded migration runs as restricted object owner",
            migrated["migration_subprocess_returncode"] == 0,
        )
        check(
            "actual head is exact reviewed head",
            migrated["readback"]["migration_versions"] == [operator.HEAD],
        )
        with migrator.begin() as connection:
            finalized = operator.finalize(connection)
        check(
            "restricted migrator can grant exact initial serving rights",
            set(finalized["serving_grants"])
            == {"app_user", "alembic_version", "rate_limit_bucket"},
        )
        with serving.begin() as connection:
            check(
                "serving can read current account table without enrolling anyone",
                connection.scalar(text("SELECT count(*) FROM public.app_user")) == 0,
            )
            check(
                "serving can read migration head",
                connection.scalar(
                    text("SELECT version_num FROM public.alembic_version")
                )
                == operator.HEAD,
            )
            connection.exec_driver_sql(
                "INSERT INTO public.rate_limit_bucket(scope,subject_hash,window_started_at,request_count,updated_at) VALUES('native','synthetic',CURRENT_TIMESTAMP,1,CURRENT_TIMESTAMP)"
            )
            connection.exec_driver_sql(
                "UPDATE public.rate_limit_bucket SET request_count=2 WHERE scope='native' AND subject_hash='synthetic'"
            )
            check(
                "serving can use only accepted limiter DML",
                connection.scalar(
                    text(
                        "SELECT request_count FROM public.rate_limit_bucket WHERE scope='native'"
                    )
                )
                == 2,
            )
        denied = [
            (
                "serving cannot create table",
                "CREATE TABLE public.forbidden_table(id integer)",
            ),
            (
                "serving cannot change account authority",
                "UPDATE public.app_user SET role='admin'",
            ),
            (
                "serving cannot read unrelated private history",
                "SELECT * FROM public.audit_event",
            ),
            (
                "serving cannot read C23 execution state",
                "SELECT * FROM public.research_experiment_execution_state",
            ),
        ]
        for name, statement in denied:
            try:
                with serving.begin() as connection:
                    connection.exec_driver_sql(statement)
            except DBAPIError as error:
                check(name, getattr(error.orig, "pgcode", None) == "42501")
            else:
                raise AssertionError(name)
        with migrator.connect() as connection:
            check(
                "serving cannot execute app definer functions",
                not connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'ocean_%' AND has_function_privilege(:role,p.oid,'EXECUTE'))"
                    ),
                    {"role": operator.SERVING},
                ),
            )
        with migrator.begin() as connection:
            connection.exec_driver_sql(
                "GRANT SELECT ON public.audit_event TO ocean_v1_serving"
            )
        try:
            with migrator.begin() as connection:
                operator.finalize(connection)
        except operator.OperatorError:
            check(
                "finalize refuses unexpected grants without silently resetting them",
                True,
            )
        else:
            raise AssertionError("unexpected grants accepted")
        with migrator.connect() as connection:
            check(
                "unexpected grant remains inspectable after refusal",
                connection.scalar(
                    text(
                        "SELECT has_table_privilege('ocean_v1_serving','public.audit_event','SELECT')"
                    )
                ),
            )
            result["database_readback"] = operator.readback(
                connection, operator.MIGRATOR
            )
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"proxy-stopping")

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        original = operator.http.client.HTTPConnection

        def redirected(host, port, timeout):
            assert (host, port) == ("127.0.0.1", 9091)
            return original(host, server.server_port, timeout=timeout)

        try:
            with patch.object(
                operator.http.client, "HTTPConnection", side_effect=redirected
            ):
                proxy = operator.stop_proxy()
            check(
                "actual owned loopback HTTP shutdown transport succeeds",
                proxy["shutdown_requested"] and requests == ["/quitquitquit"],
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        check("owned proxy fixture terminates", not thread.is_alive())
        result["state"] = "passed"
    except Exception as error:
        result["failure_type"] = type(error).__name__
        # No exception text or private DSN/password values are emitted.
        raise
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
        if (owned / "postgres.log").exists():
            shutil.copyfile(owned / "postgres.log", output / "postgres.stdout")
        shutil.rmtree(owned)
        result["cleanup"]["owned_temporary_directory_removed"] = not owned.exists()
        paths = [
            ROOT / "deploy/gcp/beta/operator/operator.py",
            ROOT / "deploy/gcp/beta/api/entry.py",
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
