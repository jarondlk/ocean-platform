"""Pure configuration/package boundaries for the exact context-grant operator.

Actual role/column/transaction semantics are separately exercised by the owned
native PostgreSQL harness; these tests perform no database or cloud call.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "deploy/gcp/beta/context-operator"


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


OP = module("beta_context_operator_checks", "context_operator.py")
PREP = module("beta_context_operator_package_checks", "prepare_context.py")
REVISION = "f" * 40
PRIVATE = "synthetic-private-password-never-output"
DSN = "postgresql+psycopg2://ocean_v1_migrator:" + PRIVATE + "@127.0.0.1:5432/ocean_v1_beta"


@pytest.fixture
def configuration(tmp_path, monkeypatch):
    # The production executable starts fresh; pytest's shared process may have
    # imported config in unrelated tests. Remove it only within this test scope.
    monkeypatch.delitem(sys.modules, "config", raising=False)
    monkeypatch.setattr(OP, "ROOT", tmp_path)
    code = (HERE / "context_operator.py").read_bytes()
    (tmp_path / "context_operator.py").write_bytes(code)
    document = {"version": "ocean-v1-beta-context-operator-v1", "project_id": OP.PROJECT,
        "revision": REVISION, "base_operator_revision": OP.BASE_OPERATOR_REVISION,
        "base_operator_image": OP.BASE_OPERATOR_IMAGE,
        "source_pins": {"context_operator.py": hashlib.sha256(code).hexdigest()}}
    (tmp_path / "context-operator-manifest.json").write_text(json.dumps(document))
    (tmp_path / "operator-manifest.json").write_text(json.dumps({
        "version": "ocean-v1-beta-operator-context-v1", "project_id": OP.PROJECT,
        "revision": OP.BASE_OPERATOR_REVISION, "api_revision": OP.API_REVISION}))
    (tmp_path / "source-manifest.json").write_text(json.dumps({
        "version": "ocean-v1-beta-api-context-v1", "project_id": OP.PROJECT, "revision": OP.API_REVISION}))
    env = {"DEPLOYMENT_ENV": "production", "OCEAN_V1_PROJECT_ID": OP.PROJECT,
        "OCEAN_V1_SQL_CONNECTION_NAME": OP.CONNECTION,
        "OCEAN_V1_CONTEXT_OPERATOR_REVISION": REVISION, "OCEAN_V1_OPERATOR_DATABASE_URL": DSN}
    confirms = {"confirm_project": OP.PROJECT, "confirm_database": OP.DATABASE,
        "confirm_source": REVISION, "confirm_operator": OP.BASE_OPERATOR_REVISION}
    return env, confirms, tmp_path


def test_configuration_is_pure_and_private_values_are_not_represented(configuration, monkeypatch):
    env, confirms, _ = configuration
    monkeypatch.setattr(OP, "create_engine", lambda *a, **k: pytest.fail("No database during configuration"))
    result = OP.configuration(env, **confirms)
    assert result.dsn == DSN and result.revision == REVISION
    assert PRIVATE not in repr(result) and "postgresql" not in repr(result)


@pytest.mark.parametrize("name,value", [("confirm_project", "data-infra-infobio"),
    ("confirm_database", "postgres"), ("confirm_source", "a" * 40), ("confirm_operator", "a" * 40)])
def test_exact_target_source_and_base_operator_confirmations_required(configuration, name, value):
    env, confirms, _ = configuration
    with pytest.raises(OP.ContextOperatorError) as error:
        OP.configuration(env, **{**confirms, name: value})
    assert PRIVATE not in str(error.value)


@pytest.mark.parametrize("name,value", [("DEPLOYMENT_ENV", "development"),
    ("OCEAN_V1_PROJECT_ID", "data-infra-infobio"), ("OCEAN_V1_SQL_CONNECTION_NAME", "other:region:sql"),
    ("OCEAN_V1_CONTEXT_OPERATOR_REVISION", "short"), ("DATABASE_URL", "ambient-private-target"),
    ("OCEAN_V1_MIGRATOR_PASSWORD", PRIVATE), ("OCEAN_V1_SERVING_PASSWORD", PRIVATE),
    *[(flag, "true") for flag in OP.FLAGS]])
def test_ambient_credentials_flags_or_wrong_identity_are_rejected(configuration, name, value):
    env, confirms, _ = configuration
    with pytest.raises(OP.ContextOperatorError) as error:
        OP.configuration({**env, name: value}, **confirms)
    assert value not in str(error.value)


@pytest.mark.parametrize("dsn", [
    DSN.replace("ocean_v1_migrator", "postgres"), DSN.replace("127.0.0.1", "legacy.invalid"),
    DSN.replace(":5432/", ":5433/"), DSN.replace("/ocean_v1_beta", "/postgres"),
    DSN.replace("postgresql+psycopg2", "postgresql+psycopg"), DSN + "?options=unsafe",
    DSN.replace(PRIVATE + "@", "@"),
])
def test_only_exact_migrator_loopback_dsn_is_accepted(configuration, dsn):
    env, confirms, _ = configuration
    with pytest.raises(OP.ContextOperatorError):
        OP.configuration({**env, "OCEAN_V1_OPERATOR_DATABASE_URL": dsn}, **confirms)


@pytest.mark.parametrize("filename,field,value", [
    ("context-operator-manifest.json", "revision", "a" * 40),
    ("context-operator-manifest.json", "base_operator_revision", "a" * 40),
    ("context-operator-manifest.json", "base_operator_image", "mutable:latest"),
    ("operator-manifest.json", "revision", "a" * 40),
    ("operator-manifest.json", "api_revision", "a" * 40),
    ("source-manifest.json", "project_id", "data-infra-infobio"),
])
def test_source_manifests_cannot_retarget_accepted_operator(configuration, filename, field, value):
    env, confirms, output = configuration
    path = output / filename
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(OP.ContextOperatorError):
        OP.configuration(env, **confirms)


def test_tampered_code_and_ambient_legacy_import_are_rejected(configuration, monkeypatch):
    env, confirms, output = configuration
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace())
    with pytest.raises(OP.ContextOperatorError):
        OP.configuration(env, **confirms)
    monkeypatch.delitem(sys.modules, "config")
    with (output / "context_operator.py").open("ab") as handle:
        handle.write(b"\n# tampered")
    with pytest.raises(OP.ContextOperatorError):
        OP.configuration(env, **confirms)


def test_grant_policy_matches_c17_contract_and_has_only_narrow_audit_returning_read():
    from api.v1_beta_research_host import CONTEXT_TABLE_PRIVILEGES, CONTEXT_UPDATE_COLUMNS
    from db.app_models import AppBase
    assert OP.CONTEXT_TABLE_PRIVILEGES == CONTEXT_TABLE_PRIVILEGES
    assert {name: value["UPDATE"] for name, value in OP.CONTEXT_COLUMN_PRIVILEGES.items()
        if "UPDATE" in value} == CONTEXT_UPDATE_COLUMNS
    assert OP.CONTEXT_COLUMN_PRIVILEGES["audit_event"] == {"SELECT": frozenset({"created_at"})}
    assert "SELECT" not in OP.CONTEXT_TABLE_PRIVILEGES["audit_event"]
    for table, columns in OP.EXPECTED_COLUMNS.items():
        assert columns == set(AppBase.metadata.tables[table].columns.keys())
    assert all(not rights.intersection({"UPDATE", "DELETE", "TRUNCATE", "TRIGGER", "REFERENCES"})
        for rights in OP.CONTEXT_TABLE_PRIVILEGES.values())
    assert not {"research_context_revision", "audit_event"}.intersection(
        name for name, kinds in OP.CONTEXT_COLUMN_PRIVILEGES.items() if "UPDATE" in kinds)


def test_apply_has_only_fixed_grants_and_metadata_lock_no_general_sql(monkeypatch):
    calls, verification = [], []
    connection = SimpleNamespace(execute=lambda query: calls.append(str(query)))
    base = SimpleNamespace(statement=lambda _connection, template, *ids: calls.append((template, ids)))
    monkeypatch.setattr(OP, "preflight", lambda *a, **k: ["restricted-role-metadata"])
    monkeypatch.setattr(OP, "verify_privileges", lambda _connection, **k: verification.append(k))
    result = OP.apply_context_grants(connection, base)
    assert result["effective_privileges_verified"] and not result["sequence_grants"]
    assert result["password_sql_or_account_mutation"] is False
    statements = [item for item in calls if isinstance(item, tuple)]
    assert all(item[0].startswith("GRANT ") and item[1][-1] == OP.SERVING for item in statements)
    assert not any(any(value in item[0] for value in ("ROLE", "PASSWORD", "DELETE", "SEQUENCE", "GRANT OPTION")) for item in statements)
    assert verification == [{"require_complete": True}]


def test_postgres_version_test_override_requires_explicit_test_environment(monkeypatch):
    class Connection:
        dialect = SimpleNamespace(name="postgresql")
        def scalar(self, query, *args):
            return 180003
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    base = SimpleNamespace(identity=lambda *a: None, assert_restricted_roles=lambda *a: [])
    with pytest.raises(OP.ContextOperatorError, match="PostgreSQL16"):
        OP.preflight(Connection(), base, _allow_test_postgres=True)


def test_main_error_redacts_private_diagnostics_and_always_stops_accepted_proxy(monkeypatch, capsys):
    stopped = []
    monkeypatch.setattr(OP, "load_base_operator", lambda: SimpleNamespace(stop_proxy=lambda:
        stopped.append(True) or {"shutdown_requested": True}))
    monkeypatch.setattr(OP, "configuration", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(PRIVATE)))
    code = OP.main(["--confirm-project", OP.PROJECT, "--confirm-database", OP.DATABASE,
        "--confirm-source", REVISION, "--confirm-operator", OP.BASE_OPERATOR_REVISION])
    output = capsys.readouterr().out
    assert code == 2 and stopped == [True]
    assert json.loads(output)["state"] == "failed" and PRIVATE not in output


def test_packaging_is_source_bound_to_fixed_base_and_contains_no_private_inputs(tmp_path, monkeypatch):
    def committed(arguments, **kwargs):
        name = arguments[-1].split(":", 1)[1]
        return (ROOT / name).read_bytes()
    monkeypatch.setattr(PREP.subprocess, "check_output", committed)
    output = tmp_path / "context"
    result = PREP.prepare(revision=REVISION, output=output)
    assert result["credentials_included"] is False and result["cloud_calls"] is False
    assert {p.name for p in output.iterdir()} == {"Dockerfile", "context_operator.py", "context-operator-manifest.json"}
    manifest = json.loads((output / "context-operator-manifest.json").read_text())
    assert manifest["base_operator_revision"] == OP.BASE_OPERATOR_REVISION
    assert manifest["base_operator_image"] == OP.BASE_OPERATOR_IMAGE
    assert "FROM " + OP.BASE_OPERATOR_IMAGE in (output / "Dockerfile").read_text()
    assert all(PRIVATE not in p.read_text() for p in output.iterdir())
    with pytest.raises(ValueError):
        PREP.prepare(revision=REVISION, output=output)
