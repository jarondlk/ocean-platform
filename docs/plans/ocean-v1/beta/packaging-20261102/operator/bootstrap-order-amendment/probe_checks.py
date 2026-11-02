"""Pure rollback-probe guards; no credential generation, DB or cloud calls."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[7]


def load():
    spec = importlib.util.spec_from_file_location(
        "probe_operator_checks", ROOT / "deploy/gcp/beta/operator/operator.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def run():
    op = load()
    passed = []

    def check(name, condition=True):
        assert condition, name
        passed.append(name)

    class Controlled(Exception):
        pgcode = "42501"

    class Transaction:
        def __init__(self, engine):
            self.engine = engine
            self.is_active = True
            self.before = engine.probe

        def rollback(self):
            self.engine.rollback_count += 1
            self.is_active = False
            if not self.engine.retain_probe:
                self.engine.probe = self.before

    class Connection:
        def __init__(self, engine):
            self.engine = engine
            self.connection = SimpleNamespace(
                driver_connection=SimpleNamespace(autocommit=False)
            )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def begin(self):
            return Transaction(self.engine)

        def scalar(self, statement, parameters):
            return self.engine.probe

        def execute(self, statement, parameters):
            return SimpleNamespace(
                one=lambda: (op.PROBE_ROLE, False, False, False, False, False, False)
            )

    class Engine:
        def __init__(
            self, clears=False, fail_alter=False, preexisting=False, retain_probe=False
        ):
            self.probe = preexisting
            self.clears = clears
            self.fail_alter = fail_alter
            self.retain_probe = retain_probe
            self.rollback_count = 0
            self.disposals = 0
            self.statements = []
            self.connections = 0

        def connect(self):
            self.connections += 1
            return Connection(self)

        def dispose(self):
            self.disposals += 1

    def metadata(connection, user):
        return {
            "roles": [],
            "tables": [],
            "provider_safety": {"database_owner": "postgres"},
        }

    def memberships(connection):
        engine = connection.engine
        return (
            []
            if engine.clears
            and any(text.startswith("REVOKE") for text in engine.statements)
            else [
                {
                    "role": op.PROBE_ROLE,
                    "member": "postgres",
                    "grantor": "native_admin",
                    "admin": True,
                    "inherit": False,
                    "set": False,
                }
            ]
        )

    def statement(connection, template, *names, parameters=None):
        engine = connection.engine
        engine.statements.append(template)
        assert "PASSWORD" not in template and parameters is None
        assert names[0] == op.PROBE_ROLE
        if template.startswith("CREATE"):
            engine.probe = True
        if template.startswith("ALTER") and engine.fail_alter:
            raise Controlled("private error text must not be exported")

    with (
        patch.object(op, "identity"),
        patch.object(op, "readback", side_effect=metadata),
        patch.object(op, "probe_memberships", side_effect=memberships),
        patch.object(op, "statement", side_effect=statement),
        patch.object(
            op,
            "prepare_scram",
            side_effect=AssertionError("probe may not prepare passwords"),
        ),
    ):
        for clear in (False, True):
            engine = Engine(clears=clear)
            result = op.qualify(engine)
            check(
                "probe captures creator-grantor behavior without claiming bootstrap",
                result["sequence_supported"] == clear
                and result["bootstrap_authorized"] is False
                and result["password_sql_performed"] is False,
            )
            check(
                "probe always rolls back and verifies from another connection",
                engine.rollback_count == 1
                and engine.disposals == 1
                and engine.connections == 2
                and result["probe_absent_after_rollback"],
            )
            check(
                "probe touches only fixed NOLOGIN role/default/membership",
                len(engine.statements) == 3
                and "NOLOGIN" in engine.statements[0]
                and not any(
                    "DROP" in value or "TABLE" in value for value in engine.statements
                ),
            )
            check(
                "provider refusal and original inventories remain explicit",
                result["application_role_inventory_unchanged"]
                and result["application_table_inventory_unchanged"],
            )
        engine = Engine(fail_alter=True)
        result = op.qualify(engine)
        check(
            "SQL refusal is metadata-only and still rolls back",
            result["error_code"] == "42501"
            and engine.rollback_count == 1
            and result["probe_absent_after_rollback"]
            and "private error text" not in json.dumps(result),
        )
        engine = Engine(preexisting=True)
        try:
            op.qualify(engine)
        except op.OperatorError:
            check(
                "existing probe is refused without altering/deleting it",
                engine.probe and not engine.statements and engine.rollback_count == 1,
            )
        else:
            raise AssertionError("existing probe accepted")
        engine = Engine()
        with patch.object(
            op, "readback", side_effect=Controlled("private baseline error")
        ):
            try:
                op.qualify(engine)
            except op.OperatorError:
                check(
                    "unreadable baseline rolls back before any probe mutation",
                    engine.rollback_count == 1 and not engine.statements,
                )
            else:
                raise AssertionError("unreadable baseline accepted")
        engine = Engine(clears=True, retain_probe=True)
        result = op.qualify(engine)
        check(
            "failed absence verification closes qualification",
            not result["sequence_supported"]
            and not result["probe_absent_after_rollback"],
        )
    source, operator = "a" * 40, "b" * 40
    env = {
        "DEPLOYMENT_ENV": "production",
        "OCEAN_V1_PROJECT_ID": op.PROJECT,
        "OCEAN_V1_SQL_CONNECTION_NAME": op.CONNECTION,
        "OCEAN_V1_SOURCE_REVISION": source,
        "OCEAN_V1_OPERATOR_REVISION": operator,
        "OCEAN_V1_OPERATOR_DATABASE_URL": "postgresql+psycopg2://postgres:synthetic@127.0.0.1:5432/ocean_v1_beta",
    }
    with tempfile.TemporaryDirectory(prefix="ocean-probe-guards-") as temporary:
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
        confirmations = {
            "confirm_project": op.PROJECT,
            "confirm_database": op.DATABASE,
            "confirm_source": source,
            "confirm_operator": operator,
        }
        with patch.object(op, "ROOT", directory):
            check(
                "qualify keeps exact target/source confirmations without application passwords",
                op.validate(env, stage="qualify", **confirmations)["user"]
                == "postgres",
            )
            for invalid in (
                dict(env, OCEAN_V1_PROJECT_ID="legacy"),
                dict(env, DATABASE_URL="legacy"),
                dict(env, ENABLE_V1_EXPERIMENT_DISPATCH="true"),
            ):
                try:
                    op.validate(invalid, stage="qualify", **confirmations)
                except op.OperatorError:
                    check("qualify preserves source/target/execution rejection")
                else:
                    raise AssertionError("unsafe qualifier config accepted")
            args = [
                "qualify",
                "--confirm-project",
                op.PROJECT,
                "--confirm-database",
                op.DATABASE,
                "--confirm-source",
                source,
                "--confirm-operator",
                operator,
            ]
            for supported, expected in ((False, 2), (True, 0)):
                output = io.StringIO()
                with (
                    patch.dict(os.environ, env, clear=True),
                    redirect_stdout(output),
                    patch.object(
                        op,
                        "run_stage",
                        return_value={
                            "sequence_supported": supported,
                            "bootstrap_authorized": False,
                        },
                    ),
                    patch.object(
                        op, "stop_proxy", return_value={"shutdown_requested": True}
                    ) as shutdown,
                ):
                    code = op.main(args)
                report = json.loads(output.getvalue())
                check(
                    "qualifier inspection result controls exit while finalizer always runs",
                    code == expected
                    and shutdown.call_count == 1
                    and report["result"]["bootstrap_authorized"] is False,
                )
    # The additive metadata query must remain finite and avoid credential/query catalogues.
    queries = []

    class Metadata:
        def execute(self, query, parameters=None):
            text = str(query)
            queries.append(text)
            if "pg_get_userbyid" in text:
                return SimpleNamespace(one=lambda: ("postgres", "pg_database_owner"))
            if "WHERE rolname=current_user" in text:
                return SimpleNamespace(
                    one=lambda: ("postgres", 10, False, True, True, False, False, True)
                )
            if "FROM pg_settings" in text:
                return [
                    (
                        "shared_preload_libraries",
                        None,
                        None,
                        "configuration file",
                        "postmaster",
                        False,
                    )
                ]
            return []

    metadata = op.provider_safety_readback(Metadata())
    check(
        "hidden settings remain explicit without an authorization claim",
        metadata["protected_values_hidden"]
        and not metadata["password_sql_authorized_by_this_readback"]
        and metadata["current_principal"]["oid"] == 10,
    )
    check(
        "metadata has no password or query catalogue read",
        not any(
            "pg_authid" in text or "rolpassword" in text or "SELECT *" in text
            for text in queries
        ),
    )
    return {
        "version": "beta-rollback-capability-probe-pure-v1",
        "passed": len(passed),
        "checks": passed,
        "cloud_database_or_native_actions": False,
        "secret_generation_or_password_sql": False,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
