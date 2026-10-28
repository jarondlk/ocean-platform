"""Pure config/guard/evaluation tests; approved scientific code is AST-only."""

import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestration.experiment_sandbox import physical_termination as physical
from sandbox.experiment.gcp import run_retained_acceptance as module


def config():
    worker = {
        name: "a" * 64
        for name in physical.WORKER_FILES
        | {
            "orchestration/experiment_sandbox/retained_admission.py",
            "sandbox/experiment/gcp/run_retained_acceptance.py",
            "sandbox/experiment/gcp/run_operator_acceptance.py",
            "tests/research_experiment_support.py",
            "tests/investigation_support.py",
            "tests/catalogue_service_support.py",
            "tests/test_scientific_catalogue_sources.py",
        }
    }
    roles = {name: "c23_" + name for name in module.ROLE_KEYS}
    result = {
        "version": module.CONFIG_VERSION,
        "case": "scientific",
        "database_name": "ocean_c23_retained",
        "schema": "c23_retained",
        "roles": roles,
        "source_root": "/opt/ocean-c23-source",
        "worker_source_files": worker,
        "profile_source_files": {name: "a" * 64 for name in physical.PROFILE_FILES},
        "expected_worker_id": "b" * 64,
        "issuer_id": "operator-c23",
        "key_id": "ephemeral-c23",
        "issuer_public_key_hex": "c" * 64,
        "private_key_path": "/root/c23-control/seed.bin",
        "materials": {
            name: (
                "d" * 64 if name.endswith("sha256") else "/var/lib/ocean-c23/" + name
            )
            for name in module.MATERIAL_KEYS
        },
        "network": {
            name: (
                "e" * 64 if name.endswith("sha256") else "/var/lib/ocean-c23/" + name
            )
            for name in module.NETWORK_KEYS
        },
    }
    for field, role in (
        ("application_dsn", "serving_role"),
        ("controller_dsn", "controller_role"),
        ("verifier_dsn", "verifier_role"),
    ):
        result[field] = (
            "postgresql+psycopg2://"
            + roles[role]
            + ":"
            + "f" * 32
            + "@127.0.0.1:55432/ocean_c23_retained"
        )
    return result


def test_explicit_private_config_uses_distinct_loopback_roles_and_detached_pins():
    original = config()
    parsed = module.parse_config(original)
    assert parsed == original
    parsed["worker_source_files"].clear()
    assert original["worker_source_files"]
    assert "application_dsn" not in module.evaluate("scientific", {}, {}, {})


@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "version",
        "case",
        "database",
        "schema",
        "remote",
        "driver",
        "password",
        "query",
        "username",
        "roles",
        "source",
        "key",
        "material",
        "profile",
        "worker",
    ],
)
def test_unknown_credential_target_scope_and_source_changes_fail_before_connection(
    change,
):
    data = config()
    if change == "unknown":
        data["approve_all"] = True
    elif change == "version":
        data["version"] = "other"
    elif change == "case":
        data["case"] = "arbitrary-code"
    elif change == "database":
        data["database_name"] = "legacy"
    elif change == "schema":
        data["schema"] = "public"
    elif change == "remote":
        data["controller_dsn"] = data["controller_dsn"].replace("127.0.0.1", "8.8.8.8")
    elif change == "driver":
        data["controller_dsn"] = data["controller_dsn"].replace("+psycopg2", "+psycopg")
    elif change == "password":
        data["controller_dsn"] = data["controller_dsn"].replace("f" * 32, "short")
    elif change == "query":
        data["controller_dsn"] += "?options=-csearch_path%3Dpublic"
    elif change == "username":
        data["controller_dsn"] = data["controller_dsn"].replace(
            data["roles"]["controller_role"], "admin"
        )
    elif change == "roles":
        data["roles"]["controller_role"] = data["roles"]["serving_role"]
    elif change == "source":
        data["source_root"] = "relative"
    elif change == "key":
        data["issuer_public_key_hex"] = "A" * 64
    elif change == "material":
        data["materials"]["image_receipt_sha256"] = "0"
    elif change == "profile":
        data["profile_source_files"][next(iter(physical.PROFILE_FILES))] = "b" * 64
    else:
        data["worker_source_files"].pop(
            "orchestration/experiment_sandbox/retained_admission.py"
        )
    with pytest.raises((module.base.OperatorError, ValueError)):
        module.parse_config(data)


def test_worker_guard_precedes_private_config_reads_and_all_effects(monkeypatch):
    called = []

    def guard():
        called.append("guard")
        raise module.base.OperatorError("dedicated_linux_root_worker_required")

    def forbidden(*args, **kwargs):
        pytest.fail("Worker rejection reached a config read or DB effect")

    monkeypatch.setattr(module.base, "require_worker", guard)
    monkeypatch.setattr(module, "private_bytes", forbidden)
    monkeypatch.setattr(module, "_engine", forbidden)
    with pytest.raises(module.base.OperatorError, match="dedicated_linux"):
        module.run(
            SimpleNamespace(
                config=Path("/must-not-read"),
                config_sha256="a" * 64,
                attempt_dir=Path("/must-not-create"),
            )
        )
    assert called == ["guard"]


def test_required_fixture_modules_are_loaded_before_first_origin_check(monkeypatch):
    calls = []
    data = config()
    data["source_root"] = str(Path(module.__file__).resolve().parents[3])
    monkeypatch.setattr(
        physical, "_protected_sources", lambda *args: calls.append("hashes")
    )
    monkeypatch.setattr(
        module.importlib, "import_module", lambda name: calls.append(name)
    )

    def provenance(root, files, *, check):
        check()
        assert set(module.FIXTURE_MODULES) <= set(calls)
        calls.append("origins")

    monkeypatch.setattr(physical, "require_loaded_source_provenance", provenance)
    module._prepare_source_imports(data)
    assert calls[0] == "hashes" and calls[-1] == "origins"


def observations(case):
    report = {
        "state": "completed",
        "analysis_exit_code": 0,
        "host_runtime_exit_status": 0,
        "execution_started": True,
        "native_cleanup_recorded": True,
        "durable_terminal": {},
        "publication_status": "acknowledged"
        if case == "scientific"
        else "denied_or_uncertain",
        "capacity_release_status": "acknowledged",
        "reservation_released": True,
        "scientific_approval": "not_independently_verified",
    }
    events = [{"kind": "start_consumed"}, {"kind": "closed"}]
    if case == "scientific":
        events.append({"kind": "publication_retained"})
    database = {
        "research_experiment_execution_event": events,
        "research_experiment_termination_proof": [{}],
        "research_experiment_release": [{}],
        "fake_outbox_count": 0,
        "reservation": {"state": "released"},
    }
    return report, database, {"rootfs_unmounted": True, "cgroup_empty": True}


@pytest.mark.parametrize("case", sorted(module.CASES))
def test_case_evaluation_requires_actual_pipeline_ledger_and_cleanup(case):
    args = observations(case)
    assert module.evaluate(case, *args)["passed"]
    for key in (
        "analysis_exit_code",
        "execution_started",
        "native_cleanup_recorded",
        "durable_terminal",
        "capacity_release_status",
        "reservation_released",
        "publication_status",
    ):
        changed = deepcopy(args)
        changed[0][key] = None
        assert module.evaluate(case, *changed)["passed"] is False
    changed = deepcopy(args)
    changed[1]["research_experiment_execution_event"].append({"kind": "start_consumed"})
    assert module.evaluate(case, *changed)["passed"] is False
    changed = deepcopy(args)
    changed[2]["cgroup_empty"] = False
    assert module.evaluate(case, *changed)["passed"] is False
    assert module.evaluate(case, *args)["C23_complete"] is False


def test_scientific_program_is_stored_as_literal_ast_and_never_host_executed():
    tree = ast.parse(module.SCIENCE_CODE)
    imports = {
        node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)
    }
    assert {
        "numpy",
        "pandas",
        "pyarrow",
        "scipy.stats",
        "statsmodels.api",
        "matplotlib",
    } <= imports
    assert (
        "9223372036854775807" in module.SCIENCE_CODE
        and "/scratch/exact.parquet" in module.SCIENCE_CODE
    )
    assert all(
        not isinstance(node, ast.Call)
        or not isinstance(node.func, ast.Name)
        or node.func.id not in {"eval", "exec", "compile"}
        for node in ast.walk(tree)
    )


def test_authentic_fixture_setup_uses_valid_original_resource_defaults_and_no_dispatch(
    monkeypatch,
):
    from schema.research_experiments import ExperimentResources
    from tests import research_experiment_support

    calls = []

    def invoke(action, request, owner):
        calls.append((action, request))
        return {"experiment": {"id": "synthetic-only"}}

    fixture = SimpleNamespace(
        service=SimpleNamespace(environments={}, invoke=invoke),
        request=lambda: {"proposal": {}},
        user=object(),
        decision=lambda value: {"id": value["id"]},
        state={"dispatch_enabled": True},
        executor=SimpleNamespace(deliveries=[]),
    )
    monkeypatch.setattr(
        research_experiment_support, "make_experiment_fixture", lambda *args: fixture
    )
    image = {
        "python_version": "3.12.15",
        "image_digest": "sha256:" + "a" * 64,
        "lockfile_sha256": "b" * 64,
        "packages": {
            name: "1.0.0"
            for name in (
                "numpy",
                "pandas",
                "pyarrow",
                "scipy",
                "statsmodels",
                "matplotlib",
            )
        },
    }
    module._make_fixture(object(), Path("/inert-fixture"), image)
    assert [action for action, _ in calls] == ["create", "approve"]
    proposal = calls[0][1]["proposal"]
    assert (
        ExperimentResources.model_validate(proposal["resources"])
        == ExperimentResources()
    )
    assert (
        proposal["resources"]["cpus"] == 2
        and proposal["resources"]["memory_bytes"] == 4 * 1024**3
    )
    assert (
        proposal["resources"]["wall_seconds"] == 600
        and proposal["python_code"] == module.SCIENCE_CODE
    )
    assert fixture.state["dispatch_enabled"] is False


@pytest.mark.parametrize("failure", [False, True])
def test_c22_observer_uses_separate_application_readonly_transaction_and_disposes(
    monkeypatch, failure
):
    from contextlib import contextmanager

    calls = []
    data = config()

    class Engine:
        @contextmanager
        def begin(self):
            calls.append("begin")
            yield self

        def exec_driver_sql(self, sql):
            assert sql == "SET TRANSACTION READ ONLY"
            calls.append("read_only")

        def execute(self, sql):
            return SimpleNamespace(
                one=lambda: (
                    data["roles"]["serving_role"],
                    data["roles"]["serving_role"],
                    data["schema"],
                )
            )

        def scalar(self, sql, *args):
            assert "research_experiment_execution" not in str(sql)
            calls.append("select")
            if failure:
                raise RuntimeError("observation failed")
            return 0 if "count" in str(sql) else {"state": "released"}

        def dispose(self):
            calls.append("dispose")

    def engine(document, field):
        assert document is data and field == "application_dsn"
        return Engine()

    def boundary(engine, document, *, require_empty):
        assert require_empty is False
        calls.append("boundary")
        return {"C23_write_privilege": False}

    monkeypatch.setattr(module, "_engine", engine)
    monkeypatch.setattr(module, "_application_boundary", boundary)
    identity = SimpleNamespace(
        document={"reservation_id": "00000000-0000-4000-8000-000000000001"}
    )
    if failure:
        with pytest.raises(RuntimeError):
            module._c22_observation(data, identity)
    else:
        assert module._c22_observation(data, identity)["fake_outbox_count"] == 0
    assert calls[:3] == ["boundary", "begin", "read_only"] and calls[-1] == "dispose"


@pytest.mark.parametrize("lost_ack", [False, True])
def test_owner_revocation_requires_actual_application_write_commit_and_fresh_status_readback(
    monkeypatch, lost_ack
):
    from contextlib import contextmanager

    calls = []
    data = config()

    class Engine:
        transactions = 0

        @contextmanager
        def begin(self):
            self.transactions += 1
            number = self.transactions
            calls.append("begin" + str(number))
            yield self
            calls.append("commit" + str(number))
            if lost_ack and number == 1:
                raise OSError("lost revocation acknowledgement")

        def exec_driver_sql(self, sql):
            assert self.transactions == 2 and sql == "SET TRANSACTION READ ONLY"

        def scalar(self, sql, parameters):
            assert parameters["id"] == "00000000-0000-4000-8000-000000000001"
            if self.transactions == 1:
                assert "UPDATE app_user SET status='suspended'" in str(sql)
                return {
                    "status": "suspended",
                    "owner_user_id": parameters["id"],
                    "database_observed_at": "operator-test",
                }
            assert str(sql).startswith("SELECT status FROM app_user")
            return "suspended"

        def dispose(self):
            calls.append("dispose")

    monkeypatch.setattr(
        module,
        "_engine",
        lambda value, field: (
            Engine()
            if value is data and field == "application_dsn"
            else pytest.fail("wrong principal")
        ),
    )
    monkeypatch.setattr(
        module,
        "_application_boundary",
        lambda *args, **kwargs: {"C23_write_privilege": False},
    )
    if lost_ack:
        with pytest.raises(OSError):
            module._revoke_owner(data, "00000000-0000-4000-8000-000000000001")
        assert calls == ["begin1", "commit1", "dispose"]
    else:
        result = module._revoke_owner(data, "00000000-0000-4000-8000-000000000001")
        assert (
            result["feature_flag_enabled"] and result["readback_status"] == "suspended"
        )
        assert calls == ["begin1", "commit1", "begin2", "commit2", "dispose"]


@pytest.mark.parametrize(
    "root", ["source_root", "rootfs", "oci_layout", "runtime_directory", "attempt"]
)
def test_control_secrets_are_rejected_inside_every_guest_or_source_tree(root):
    data = config()
    attempt = Path("/var/lib/ocean-c23/operator-acceptance/example")
    directory = (
        Path(data[root])
        if root == "source_root"
        else attempt
        if root == "attempt"
        else Path(data["materials"][root])
    )
    data["private_key_path"] = str(directory / "secret-seed")
    with pytest.raises(module.base.OperatorError, match="secret_mount_boundary"):
        module._secret_boundary(data, "/root/private-config.json", attempt)


@pytest.mark.parametrize("passed,exitcode", [(True, 0), (False, 1)])
def test_cli_returns_case_failure_and_never_prints_credentials(
    monkeypatch, capsys, passed, exitcode
):
    monkeypatch.setattr(
        module,
        "run",
        lambda args: {"case": "scientific", "evaluation": {"passed": passed}},
    )
    assert (
        module.main(
            [
                "--config",
                "/root/private.json",
                "--config-sha256",
                "a" * 64,
                "--attempt-dir",
                "/var/lib/ocean-c23/operator-acceptance/example",
            ]
        )
        == exitcode
    )
    output = capsys.readouterr().out
    assert "dsn" not in output and "private_key" not in output
    source = ast.parse(Path(module.__file__).read_text())
    assert any(
        isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "SystemExit"
        for node in ast.walk(source)
    )
