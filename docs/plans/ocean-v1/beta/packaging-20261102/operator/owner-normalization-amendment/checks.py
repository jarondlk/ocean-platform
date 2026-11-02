"""Focused pure owner-normalization guards; no DB, cloud or credential generation."""

from __future__ import annotations

import ast
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def run():
    op = load(ROOT / "deploy/gcp/beta/operator/operator.py", "owner_operator")
    passed = []

    def check(name, condition):
        assert condition, name
        passed.append(name)

    class Connection:
        def __init__(self, **changed):
            self.owner = "cloudsqlsuperuser"
            self.schema_owner = "pg_database_owner"
            self.createdb = self.inherits_owner = self.only_plpgsql = True
            self.existing_roles = self.populated = self.extra_schema = False
            self.post_owner = "postgres"
            self.post_schema = "pg_database_owner"
            self.principal = "postgres"
            self.calls = []
            self.ddl = []
            self.__dict__.update(changed)

        def execute(self, query, parameters=None):
            query = str(query)
            self.calls.append(query)
            if "current_database(),current_user,session_user" in query:
                row = (op.DATABASE, self.principal, self.principal)
            elif "r.rolcreatedb" in query:
                row = (
                    self.owner,
                    self.schema_owner,
                    self.createdb,
                    self.inherits_owner,
                )
            else:
                row = (self.owner, self.schema_owner)
            return SimpleNamespace(one=lambda: row)

        def scalar(self, query):
            query = str(query)
            self.calls.append(query)
            if "FROM pg_roles" in query:
                return self.existing_roles
            if "FROM pg_class" in query:
                return self.populated
            if "FROM pg_extension" in query:
                return self.only_plpgsql
            if "FROM pg_namespace" in query:
                return self.extra_schema
            raise AssertionError("Unexpected scalar query")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Transaction:
        def __init__(self, engine):
            self.engine = engine
            self.before = (engine.connection.owner, engine.connection.schema_owner)

        def __enter__(self):
            return self.engine.connection

        def __exit__(self, kind, value, traceback):
            if kind is None:
                self.engine.commits += 1
            else:
                self.engine.rollbacks += 1
                self.engine.connection.owner, self.engine.connection.schema_owner = (
                    self.before
                )
            return False

    class Engine:
        def __init__(self, connection):
            self.connection = connection
            self.commits = self.rollbacks = self.begin_count = self.disposals = 0

        def begin(self):
            self.begin_count += 1
            return Transaction(self)

        def connect(self):
            return self.connection

        def dispose(self):
            self.disposals += 1

    def statement(connection, template, *names, parameters=None):
        assert template == "ALTER DATABASE {} OWNER TO {}"
        assert names == (op.DATABASE, "postgres") and parameters is None
        connection.ddl.append((template, names))
        connection.owner, connection.schema_owner = (
            connection.post_owner,
            connection.post_schema,
        )

    def readback(connection, principal):
        assert principal == "postgres" and connection.owner == "postgres"
        return {
            "database": op.DATABASE,
            "principal": principal,
            "owner": connection.owner,
        }

    with patch.object(op, "statement", side_effect=statement):
        connection = Connection()
        result = op.normalize_owner(connection)
        check(
            "exact empty beta owner changes to postgres with unchanged public owner",
            result["database_owner"] == "postgres"
            and result["public_schema_owner"] == "pg_database_owner"
            and result["public_schema_owner_unchanged"],
        )
        check(
            "only one fixed owner DDL and no password/role/grant SQL",
            len(connection.ddl) == 1
            and not result["explicit_role_grant_password_or_application_sql_performed"]
            and all(query.startswith("SELECT") for query in connection.calls),
        )
        for name, changes in (
            ("wrong principal", {"principal": "legacy"}),
            ("existing independent roles", {"existing_roles": True}),
            ("application objects or migration head", {"populated": True}),
            ("unexpected or absent default extension", {"only_plpgsql": False}),
            ("unexpected user schema", {"extra_schema": True}),
            ("unexpected current database owner", {"owner": "legacy_owner"}),
            (
                "already normalized owner is not silently accepted",
                {"owner": "postgres"},
            ),
            ("unexpected public schema owner", {"schema_owner": "postgres"}),
            ("missing actor CREATEDB", {"createdb": False}),
            ("missing inherited old-owner authority", {"inherits_owner": False}),
        ):
            connection = Connection(**changes)
            try:
                op.normalize_owner(connection)
            except op.OperatorError:
                check(name + " refuses before ALTER", not connection.ddl)
            else:
                raise AssertionError(name)
        engine = Engine(Connection())
        with (
            patch.object(op, "connect", return_value=engine),
            patch.object(op, "readback", side_effect=readback),
        ):
            result = op.run_stage(
                "normalize-owner", {"dsn": "not-printed", "user": "postgres"}, {}
            )
        check(
            "explicit transaction commits once then obtains normal owner readback",
            engine.begin_count == 1
            and engine.commits == 1
            and engine.rollbacks == 0
            and result["readback"]["owner"] == "postgres",
        )
        for changes in ({"post_owner": "unexpected"}, {"post_schema": "unexpected"}):
            engine = Engine(Connection(**changes))
            with patch.object(op, "connect", return_value=engine):
                try:
                    op.run_stage(
                        "normalize-owner",
                        {"dsn": "not-printed", "user": "postgres"},
                        {},
                    )
                except op.OperatorError:
                    check(
                        "owner/public-owner postcondition failure rolls back ALTER",
                        engine.commits == 0
                        and engine.rollbacks == 1
                        and engine.connection.owner == "cloudsqlsuperuser"
                        and engine.connection.schema_owner == "pg_database_owner",
                    )
                else:
                    raise AssertionError("Failed owner postcondition accepted")
    source, operator = "a" * 40, "b" * 40
    env = {
        "DEPLOYMENT_ENV": "production",
        "OCEAN_V1_PROJECT_ID": op.PROJECT,
        "OCEAN_V1_SQL_CONNECTION_NAME": op.CONNECTION,
        "OCEAN_V1_SOURCE_REVISION": source,
        "OCEAN_V1_OPERATOR_REVISION": operator,
        "OCEAN_V1_OPERATOR_DATABASE_URL": "postgresql+psycopg2://postgres:synthetic@127.0.0.1:5432/ocean_v1_beta",
    }
    confirmations = {
        "confirm_project": op.PROJECT,
        "confirm_database": op.DATABASE,
        "confirm_source": source,
        "confirm_operator": operator,
    }
    with tempfile.TemporaryDirectory(prefix="ocean-owner-guards-") as temporary:
        directory = Path(temporary)
        (directory / "source-manifest.json").write_text(
            json.dumps(
                {
                    "version": "ocean-v1-beta-api-context-v1",
                    "project_id": op.PROJECT,
                    "revision": source,
                }
            )
        )
        (directory / "operator-manifest.json").write_text(
            json.dumps(
                {
                    "version": "ocean-v1-beta-operator-context-v1",
                    "project_id": op.PROJECT,
                    "revision": operator,
                    "api_revision": source,
                    "api_image": "asia-northeast1-docker.pkg.dev/"
                    + op.PROJECT
                    + "/ocean-v1-beta/api@sha256:"
                    + "c" * 64,
                }
            )
        )
        with patch.object(op, "ROOT", directory):
            check(
                "owner stage validates fixed target/source/postgres without role passwords",
                op.validate(env, stage="normalize-owner", **confirmations)["user"]
                == "postgres",
            )
            for changed in (
                dict(env, OCEAN_V1_PROJECT_ID="legacy"),
                dict(env, DATABASE_URL="legacy"),
                dict(env, OCEAN_V1_OPERATOR_REVISION="d" * 40),
                dict(
                    env,
                    OCEAN_V1_OPERATOR_DATABASE_URL=env[
                        "OCEAN_V1_OPERATOR_DATABASE_URL"
                    ].replace("postgres:", "ocean_v1_migrator:"),
                ),
                dict(env, ENABLE_V1_EXPERIMENT_DISPATCH="true"),
            ):
                try:
                    op.validate(changed, stage="normalize-owner", **confirmations)
                except op.OperatorError:
                    check(
                        "owner stage retains identity/source/legacy/execution rejection",
                        True,
                    )
                else:
                    raise AssertionError("Invalid owner-stage config accepted")
            output = io.StringIO()
            argv = [
                "normalize-owner",
                "--confirm-project",
                op.PROJECT,
                "--confirm-database",
                op.DATABASE,
                "--confirm-source",
                source,
                "--confirm-operator",
                operator,
            ]
            with (
                patch.dict(os.environ, env, clear=True),
                redirect_stdout(output),
                patch.object(
                    op, "run_stage", return_value={"stage": "normalize-owner"}
                ),
                patch.object(
                    op, "stop_proxy", return_value={"shutdown_requested": True}
                ) as shutdown,
            ):
                code = op.main(argv)
            check(
                "explicit CLI stage completes with ordinary proxy finalizer",
                code == 0
                and json.loads(output.getvalue())["state"] == "stage_completed"
                and shutdown.call_count == 1,
            )

    def segments(path):
        source = path.read_text()
        return {
            node.name: ast.get_source_segment(source, node)
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
        }

    before = segments(HERE / "operator.before.py")
    after = segments(ROOT / "deploy/gcp/beta/operator/operator.py")
    names = (
        "attest_password_logging",
        "prepare_scram",
        "fresh_database",
        "create_roles",
        "assert_restricted_roles",
        "verify_serving_privileges",
        "bootstrap",
        "qualify",
        "provider_safety_readback",
        "readback",
        "stop_proxy",
    )
    check(
        "all eleven existing bootstrap/privacy/membership/inspection functions are byte-identical",
        all(before[name] == after[name] for name in names),
    )
    return {
        "version": "beta-owner-normalization-pure-v1",
        "passed": len(passed),
        "checks": passed,
        "security_function_source_hashes": {
            name: hashlib.sha256(after[name].encode()).hexdigest() for name in names
        },
        "cloud_database_native_or_secret_actions": False,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
