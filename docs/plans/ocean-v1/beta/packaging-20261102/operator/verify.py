"""Local operator guards and proxy-finalizer logic; no DB/cloud connection."""

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

ROOT = Path(__file__).resolve().parents[6]
PACKAGE = ROOT / "deploy/gcp/beta/operator"


def load():
    spec = importlib.util.spec_from_file_location(
        "beta_operator_checks", PACKAGE / "operator.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run():
    module = load()
    checks = []
    source, operator = "a" * 40, "b" * 40
    confirmations = dict(
        confirm_project=module.PROJECT,
        confirm_database=module.DATABASE,
        confirm_source=source,
        confirm_operator=operator,
    )
    base = {
        "DEPLOYMENT_ENV": "production",
        "OCEAN_V1_PROJECT_ID": module.PROJECT,
        "OCEAN_V1_SQL_CONNECTION_NAME": module.CONNECTION,
        "OCEAN_V1_SOURCE_REVISION": source,
        "OCEAN_V1_OPERATOR_REVISION": operator,
        "OCEAN_V1_OPERATOR_DATABASE_URL": "postgresql+psycopg2://postgres:"
        + "p" * 64
        + "@127.0.0.1:5432/ocean_v1_beta",
        "OCEAN_V1_MIGRATOR_PASSWORD": "m" * 64,
        "OCEAN_V1_SERVING_PASSWORD": "s" * 64,
    }
    with tempfile.TemporaryDirectory(prefix="ocean-beta-operator-guard-") as temporary:
        directory = Path(temporary)
        (directory / "operator-manifest.json").write_text(
            json.dumps(
                {
                    "version": "ocean-v1-beta-operator-context-v1",
                    "project_id": module.PROJECT,
                    "revision": operator,
                    "api_revision": source,
                    "api_image": "asia-northeast1-docker.pkg.dev/"
                    + module.PROJECT
                    + "/ocean-v1-beta/api@sha256:"
                    + "c" * 64,
                }
            )
        )
        (directory / "source-manifest.json").write_text(
            json.dumps(
                {
                    "version": "ocean-v1-beta-api-context-v1",
                    "project_id": module.PROJECT,
                    "revision": source,
                }
            )
        )
        with (
            patch.object(module, "ROOT", directory),
            patch.object(
                module,
                "create_engine",
                side_effect=AssertionError("unexpected DB access"),
            ),
        ):
            module.validate(base, stage="bootstrap", **confirmations)
            checks.append(
                "exact source/target bootstrap config accepted without connection"
            )
            migrator = dict(
                base,
                OCEAN_V1_OPERATOR_DATABASE_URL=base[
                    "OCEAN_V1_OPERATOR_DATABASE_URL"
                ].replace("postgres:", "ocean_v1_migrator:"),
            )
            for stage in ("migrate", "finalize"):
                module.validate(migrator, stage=stage, **confirmations)
                checks.append(stage + " requires its own restricted migrator principal")
            variants = [
                dict(base, OCEAN_V1_PROJECT_ID="data-infra-infobio"),
                dict(base, DATABASE_URL="legacy"),
                dict(base, OCEAN_V1_SOURCE_REVISION="d" * 40),
                dict(base, OCEAN_V1_OPERATOR_REVISION="d" * 40),
                dict(base, ENABLE_V1_RESEARCH_CONTROLLER="true"),
                dict(base, DEPLOYMENT_ENV="test"),
                dict(
                    base,
                    OCEAN_V1_SQL_CONNECTION_NAME=module.PROJECT
                    + ":asia-northeast1:other",
                ),
                dict(
                    base,
                    OCEAN_V1_OPERATOR_DATABASE_URL=base[
                        "OCEAN_V1_OPERATOR_DATABASE_URL"
                    ].replace("127.0.0.1", "8.8.8.8"),
                ),
                dict(
                    base,
                    OCEAN_V1_OPERATOR_DATABASE_URL=base[
                        "OCEAN_V1_OPERATOR_DATABASE_URL"
                    ].replace(":5432", ":6543"),
                ),
                dict(
                    base,
                    OCEAN_V1_OPERATOR_DATABASE_URL=base[
                        "OCEAN_V1_OPERATOR_DATABASE_URL"
                    ].replace("ocean_v1_beta", "ocean_platform"),
                ),
                dict(
                    base, OCEAN_V1_SERVING_PASSWORD=base["OCEAN_V1_MIGRATOR_PASSWORD"]
                ),
                dict(base, OCEAN_V1_MIGRATOR_PASSWORD="short"),
                dict(
                    base,
                    OCEAN_V1_OPERATOR_DATABASE_URL=base[
                        "OCEAN_V1_OPERATOR_DATABASE_URL"
                    ]
                    + "?options=unsafe",
                ),
            ]
            for number, env in enumerate(variants):
                try:
                    module.validate(env, stage="bootstrap", **confirmations)
                except module.OperatorError:
                    checks.append("unsafe config rejected " + str(number + 1))
                else:
                    raise AssertionError("unsafe config accepted")
            try:
                module.validate(
                    base,
                    stage="bootstrap",
                    **dict(confirmations, confirm_project="data-infra-infobio"),
                )
            except module.OperatorError:
                checks.append("wrong explicit project confirmation rejected")
            else:
                raise AssertionError("wrong confirmation accepted")
            arguments = [
                "bootstrap",
                "--confirm-project",
                module.PROJECT,
                "--confirm-database",
                module.DATABASE,
                "--confirm-source",
                source,
                "--confirm-operator",
                operator,
            ]
            for failed_stage, failed_proxy in (
                (False, False),
                (True, False),
                (False, True),
                (True, True),
            ):
                output = io.StringIO()
                with (
                    patch.dict(os.environ, base, clear=True),
                    redirect_stdout(output),
                    patch.object(
                        module,
                        "run_stage",
                        side_effect=module.OperatorError("controlled stage failure")
                        if failed_stage
                        else None,
                        return_value={"stage": "bootstrap"},
                    ),
                    patch.object(
                        module,
                        "stop_proxy",
                        side_effect=module.OperatorError("controlled shutdown failure")
                        if failed_proxy
                        else None,
                        return_value={"shutdown_requested": True},
                    ) as shutdown,
                ):
                    code = module.main(arguments)
                report = json.loads(output.getvalue())
                assert code == (3 if failed_proxy else 2 if failed_stage else 0)
                assert shutdown.call_count == 1
                assert all(
                    value not in output.getvalue()
                    for value in (
                        base["OCEAN_V1_MIGRATOR_PASSWORD"],
                        base["OCEAN_V1_SERVING_PASSWORD"],
                        base["OCEAN_V1_OPERATOR_DATABASE_URL"],
                    )
                )
                assert report["state"] == (
                    "failed_proxy_shutdown"
                    if failed_proxy
                    else "failed"
                    if failed_stage
                    else "stage_completed"
                )
                checks.append(
                    "stage/proxy finalizer outcome " + str((failed_stage, failed_proxy))
                )
    client = SimpleNamespace(
        request=lambda *args, **kwargs: None,
        getresponse=lambda: SimpleNamespace(status=200, read=lambda size: b"closed"),
        close=lambda: None,
    )
    with patch.object(
        module.http.client, "HTTPConnection", return_value=client
    ) as connection:
        assert module.stop_proxy()["shutdown_requested"]
        connection.assert_called_once_with("127.0.0.1", 9091, timeout=3)
    checks.append("proxy shutdown has fixed loopback target")
    output = io.StringIO()
    with (
        redirect_stdout(output),
        patch.object(
            module, "stop_proxy", return_value={"shutdown_requested": True}
        ) as shutdown,
    ):
        assert module.main([]) == 2
    assert (
        shutdown.call_count == 1 and json.loads(output.getvalue())["state"] == "failed"
    )
    checks.append("malformed operator invocation still signals proxy shutdown")
    for status in (403, 500):
        failed = SimpleNamespace(
            request=lambda *args, **kwargs: None,
            getresponse=lambda: SimpleNamespace(
                status=status, read=lambda size: b"failed"
            ),
            close=lambda: None,
        )
        with (
            patch.object(module.http.client, "HTTPConnection", return_value=failed),
            patch.object(module.time, "sleep"),
        ):
            try:
                module.stop_proxy()
            except module.OperatorError:
                checks.append("proxy non-success status rejected " + str(status))
            else:
                raise AssertionError("failed shutdown accepted")
    # Capture the subprocess contract without a DB connection or child execution.
    connection = SimpleNamespace(
        exec_driver_sql=lambda statement: None, scalar=lambda statement: "public"
    )

    class Transaction:
        def __enter__(self):
            return connection

        def __exit__(self, *args):
            return None

    engine = SimpleNamespace(
        begin=lambda: Transaction(), connect=lambda: Transaction(), dispose=lambda: None
    )
    captured = {}

    def child(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0)

    with (
        patch.object(module, "connect", return_value=engine),
        patch.object(module, "identity"),
        patch.object(module, "assert_restricted_roles"),
        patch.object(module, "readback", return_value={}),
        patch.object(module.subprocess, "run", side_effect=child),
    ):
        module.run_stage(
            "migrate",
            {"dsn": "synthetic-private-migrator", "user": module.MIGRATOR},
            base,
        )
    assert captured["timeout"] == 480 and captured["capture_output"]
    assert captured["env"]["OCEAN_V1_DATABASE_URL"] == "synthetic-private-migrator"
    assert (
        "OCEAN_V1_MIGRATOR_PASSWORD" not in captured["env"]
        and "OCEAN_V1_SERVING_PASSWORD" not in captured["env"]
    )
    assert "synthetic-private-migrator" not in captured["command"]
    checks.append(
        "migration subprocess receives only own private DSN and bounded fixed command"
    )
    return {
        "version": "beta-operator-local-guards-v1",
        "passed": len(checks),
        "checks": checks,
        "database_connections": False,
        "cloud_calls": False,
        "image_build": False,
        "proxy_transport": "mocked; actual loopback transport checked in native rehearsal",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
