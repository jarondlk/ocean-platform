"""Pure password preparation/log-policy guards; no random values or network."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[7]


def run():
    spec = importlib.util.spec_from_file_location(
        "beta_password_operator", ROOT / "deploy/gcp/beta/operator/operator.py"
    )
    operator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(operator)
    passed = []

    def check(name, condition=True):
        assert condition, name
        passed.append(name)

    class Connection:
        def __init__(self, changed=None):
            self.settings = dict(operator.PASSWORD_LOGGING_POLICY, **(changed or {}))
            self.calls = []
            self.connection = SimpleNamespace(
                driver_connection=SimpleNamespace(server_version=160000)
            )

        def execute(self, statement, parameters):
            self.calls.append(str(statement))
            return SimpleNamespace(
                all=lambda: [
                    (name, self.settings.get(name)) for name in parameters["names"]
                ]
            )

        def scalar(self, statement):
            self.calls.append(str(statement))
            return bool(self.settings.get("extension_present", False))

    connection = Connection()
    with patch.object(operator, "libpq_version", return_value=170000):
        accepted = operator.attest_password_logging(connection)
        check(
            "accepted actual policy yields only fixed logging metadata",
            accepted["verified"]
            and accepted["settings"] == operator.PASSWORD_LOGGING_POLICY,
        )
        check(
            "logging attestation executes only readonly current_setting SELECT",
            all(
                statement.startswith("SELECT") and " SET " not in statement.upper()
                for statement in connection.calls
            ),
        )
        for name, expected in operator.PASSWORD_LOGGING_POLICY.items():
            if name == "password_encryption":
                unsafe = "md5"
            elif expected == "off":
                unsafe = "on"
            elif expected == "-1":
                unsafe = "0"
            elif name == "log_transaction_sample_rate":
                unsafe = "0.5"
            elif expected == "none":
                unsafe = "ddl"
            else:
                unsafe = "error"
            try:
                operator.attest_password_logging(Connection({name: unsafe}))
            except operator.OperatorError:
                check(name + " rejects unsafe policy")
            else:
                raise AssertionError(name)
        for changed in ({"pgaudit.log": "ddl"}, {"auto_explain.log_min_duration": "0"}):
            try:
                operator.attest_password_logging(Connection(changed))
            except operator.OperatorError:
                check("optional statement/audit logger fails closed")
            else:
                raise AssertionError("optional logger accepted")
        for changed in (
            {
                "shared_preload_libraries": "pg_stat_statements",
                "pg_stat_statements.track": "top",
                "pg_stat_statements.track_utility": "on",
            },
            {
                "pg_stat_statements.track": "top",
                "pg_stat_statements.track_utility": "on",
            },
            {"extension_present": True},
        ):
            try:
                operator.attest_password_logging(Connection(changed))
            except operator.OperatorError:
                check("active/preloaded utility query collection fails closed")
            else:
                raise AssertionError("utility query collector accepted")
        for changed in (
            {
                "shared_preload_libraries": "pg_stat_statements",
                "pg_stat_statements.track": "top",
                "pg_stat_statements.track_utility": "off",
            },
            {
                "shared_preload_libraries": "pg_stat_statements",
                "pg_stat_statements.track": "none",
                "pg_stat_statements.track_utility": "on",
            },
        ):
            accepted = operator.attest_password_logging(Connection(changed))
            check(
                "disabled utility collection is accepted",
                accepted["utility_query_collection"]["credential_utility_capture"]
                == "disabled",
            )
        unsafe = Connection({"log_min_error_statement": "error"})
        with (
            patch.object(
                operator,
                "encrypt_password",
                side_effect=AssertionError("must not prepare"),
            ) as prepare,
            patch.object(
                operator, "statement", side_effect=AssertionError("must not bind")
            ) as statement,
        ):
            try:
                operator.create_roles(
                    unsafe, {"OCEAN_V1_MIGRATOR_PASSWORD": "synthetic-raw-password"}
                )
            except operator.OperatorError:
                check(
                    "unsafe logging rejects before preparing/binding password",
                    not prepare.called and not statement.called,
                )
            else:
                raise AssertionError("unsafe role creation accepted")
    verifier = "SCRAM-SHA-256$4096:YWJjZA==$" + ("YQ==" * 11) + ":" + ("Yg==" * 11)
    with (
        patch.object(operator, "libpq_version", return_value=170000),
        patch.object(operator, "encrypt_password", return_value=verifier) as prepare,
    ):
        actual = operator.prepare_scram(
            connection, "synthetic-raw-password", operator.MIGRATOR
        )
        check(
            "explicit client SCRAM algorithm and driver scope used",
            actual == verifier
            and prepare.call_args.args == ("synthetic-raw-password", operator.MIGRATOR)
            and prepare.call_args.kwargs
            == {
                "scope": connection.connection.driver_connection,
                "algorithm": "scram-sha-256",
            },
        )
    for output in ("md5unsafe", "synthetic-raw-password", b"SCRAM-SHA-256$invalid"):
        with (
            patch.object(operator, "libpq_version", return_value=170000),
            patch.object(operator, "encrypt_password", return_value=output) as prepare,
        ):
            try:
                operator.prepare_scram(
                    connection, "synthetic-raw-password", operator.MIGRATOR
                )
            except operator.OperatorError:
                check(
                    "invalid preparation has no plaintext/MD5 fallback",
                    prepare.call_count == 1,
                )
            else:
                raise AssertionError("unsafe password preparation")
    with (
        patch.object(operator, "libpq_version", return_value=99999),
        patch.object(operator, "encrypt_password") as prepare,
    ):
        try:
            operator.prepare_scram(
                connection, "synthetic-raw-password", operator.MIGRATOR
            )
        except operator.OperatorError:
            check("unsupported libpq fails before crypto", not prepare.called)
        else:
            raise AssertionError("unsupported library accepted")
    old_server = Connection()
    old_server.connection.driver_connection.server_version = 90600
    with (
        patch.object(operator, "libpq_version", return_value=170000),
        patch.object(operator, "encrypt_password") as prepare,
    ):
        try:
            operator.prepare_scram(
                old_server, "synthetic-raw-password", operator.MIGRATOR
            )
        except operator.OperatorError:
            check("unsupported server fails before crypto", not prepare.called)
        else:
            raise AssertionError("unsupported server accepted")
    with (
        patch.object(operator, "libpq_version", return_value=170000),
        patch.object(
            operator,
            "encrypt_password",
            side_effect=RuntimeError("synthetic-private-canary"),
        ),
    ):
        try:
            operator.prepare_scram(
                connection, "synthetic-raw-password", operator.MIGRATOR
            )
        except operator.OperatorError as error:
            check(
                "crypto error detail is replaced by fixed diagnostic",
                "canary" not in str(error)
                and "password preparation rejected" in str(error),
            )
        else:
            raise AssertionError("crypto exception accepted")
    with (
        patch.object(
            operator, "attest_password_logging", return_value={"verified": True}
        ),
        patch.object(
            operator,
            "prepare_scram",
            side_effect=operator.OperatorError("fixed preparation rejection"),
        ),
        patch.object(operator, "statement") as statement,
    ):
        try:
            operator.create_roles(
                connection, {"OCEAN_V1_MIGRATOR_PASSWORD": "synthetic-raw-password"}
            )
        except operator.OperatorError:
            check("crypto rejection never binds raw password", not statement.called)
        else:
            raise AssertionError("crypto fallback permitted")
    return {
        "version": "beta-password-safety-pure-checks-v1",
        "passed": len(passed),
        "checks": passed,
        "cloud_or_network_calls": False,
        "actual_secret_generation": False,
        "crypto_calls": "mocked only; native rehearsal verifies real libpq and log policy",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
