"""C14 typed tool exposure: identity refresh, errors and capability limits."""
from __future__ import annotations

import uuid

import pytest

import config
from api.auth import CurrentUser, ROLE_PERMISSIONS
from orchestration.catalogue_service import CatalogueServiceError
from orchestration.catalogue_tools import CatalogueTools, invoke_catalogue
from schema.context_catalogue_fixtures import fixture_scope


def identity(role="researcher", status="active"):
    return CurrentUser(
        id=uuid.UUID(int=5), email="synthetic@example.invalid", display_name=None,
        role=role, account_type="research", status=status,
        permissions=ROLE_PERMISSIONS[role], auth_provider="oidc",
    )


def request_payload(**changes):
    return {
        "snapshot_id": "synthetic:snapshot",
        "scope": fixture_scope("ctd").model_dump(mode="json"),
        **changes,
    }


class RecordingService:
    def __init__(self):
        self.calls = []

    def execute(self, name, payload, user):
        self.calls.append((name, payload, user))
        if user is None:
            raise CatalogueServiceError("authentication_required", "Authentication is required", 401)
        if user.status != "active" or "data:read" not in user.permissions:
            raise CatalogueServiceError("access_denied", "Catalogue access is denied", 403)
        return {
            "operation": name, "scope": payload["scope"], "total_matching": 100001,
            "returned_count": 1, "identities": ["synthetic:rank-beyond-25"],
            "qualification": "synthetic boundary fixture",
        }


CALLS = [
    ("overview", "catalogue.overview", {}),
    ("list", "catalogue.list", {}),
    ("open", "catalogue.open", {"object_id": "synthetic:dataset"}),
    ("coverage", "catalogue.coverage", {"object_id": "synthetic:dataset"}),
    ("query", "catalogue.query", {
        "operation_id": "c13.inventory", "operation_version": "c13-v1",
        "input_ids": ["synthetic:dataset"],
    }),
    ("relationships", "catalogue.relationships", {}),
    ("get_published", "analysis.get_published", {"analysis_id": "synthetic:analysis"}),
]


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")


@pytest.mark.parametrize("method,name,extra", CALLS)
def test_seven_tools_share_public_models_and_executor(method, name, extra):
    service = RecordingService()
    user = identity()
    tools = CatalogueTools(service, lambda: user)
    result = getattr(tools, method)(request_payload(**extra))
    assert result["operation"] == name
    assert result["total_matching"] == 100001
    assert service.calls[0][2] is user
    assert "access_binding" not in service.calls[0][1]
    assert "access_revision" not in service.calls[0][1]


def test_identity_provider_is_refreshed_for_every_tool_call():
    service = RecordingService()
    users = iter([identity(), identity("viewer"), identity(status="suspended"), None])
    tools = CatalogueTools(service, lambda: next(users))
    assert "error" not in tools.list(request_payload())
    assert tools.list(request_payload())["error"]["code"] == "access_denied"
    assert tools.list(request_payload())["error"]["code"] == "access_denied"
    assert tools.list(request_payload())["error"]["code"] == "authentication_required"
    assert len(service.calls) == 1


@pytest.mark.parametrize("field", ["access_binding", "access_revision", "role", "user", "sql"])
def test_untrusted_tool_authority_and_sql_fields_are_rejected(field):
    service = RecordingService()
    tools = CatalogueTools(service, lambda: identity())
    result = tools.list(request_payload(**{field: "forged-authority"}))
    assert result == {"error": {"code": "invalid_request", "message": "Catalogue request is invalid"}}
    assert service.calls == []


@pytest.mark.parametrize("flag", ["false", "0", "off", "", "not-a-boolean"])
def test_tool_feature_gate_cannot_be_bypassed(monkeypatch, flag):
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", flag)
    service = RecordingService()
    touched = []
    def provider():
        touched.append(True)
        return identity()
    tools = CatalogueTools(service, provider)
    result = tools.overview(request_payload())
    assert result["error"]["code"] in {"catalogue_disabled", "catalogue_unavailable"}
    assert service.calls == [] and touched == [True]


def test_flag_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_V1_CATALOGUE", raising=False)
    monkeypatch.setattr(config, "ENABLE_V1_CATALOGUE", "false")
    assert config.v1_catalogue_enabled() is False
    assert CatalogueTools(None, lambda: identity()).overview(request_payload())["error"]["code"] == "catalogue_disabled"


def test_unknown_operation_is_validated_before_disabled_flag_and_unavailable_service(monkeypatch):
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "false")
    touched = []
    def provider():
        touched.append(True)
        return identity()
    status, result = invoke_catalogue(None, "catalogue.sql", request_payload(), provider)
    assert status == 422
    assert result["error"]["code"] == "invalid_request"
    assert touched == [True]


def test_explicit_service_and_identity_provider_are_required():
    assert CatalogueTools(None, lambda: identity()).overview(request_payload()) == {
        "error": {"code": "catalogue_unavailable", "message": "Catalogue is unavailable"},
    }
    with pytest.raises(TypeError, match="trusted identity"):
        CatalogueTools(RecordingService(), identity())


def test_no_extra_database_model_or_administrative_tools_are_registered():
    schemas = CatalogueTools.schemas()
    assert [item["name"] for item in schemas] == [call[1] for call in CALLS]
    for item in schemas:
        assert item["parameters"]["additionalProperties"] is False
        properties = item["parameters"]["properties"]
        assert not set(properties) & {"access_binding", "access_revision", "role", "sql", "user"}


@pytest.mark.parametrize("kind", ["service", "identity", "nonfinite", "nonobject"])
def test_dependency_errors_and_invalid_outputs_fail_closed_without_private_details(kind):
    class Broken(RecordingService):
        def execute(self, *args):
            if kind == "nonfinite":
                return {"number": float("nan")}
            if kind == "nonobject":
                return ["wrong-shape"]
            raise RuntimeError("private connection and password")

    def provider():
        if kind == "identity":
            raise RuntimeError("private identity-store password")
        return identity()

    assert CatalogueTools(Broken(), provider).list(request_payload()) == {
        "error": {"code": "catalogue_unavailable", "message": "Catalogue is unavailable"},
    }


@pytest.mark.parametrize("code,status", [("not_found", 404), ("invalid_cursor", 409), ("invalid_request", 422)])
def test_service_errors_preserve_typed_code_and_safe_message(code, status):
    class Failed(RecordingService):
        def execute(self, *args):
            raise CatalogueServiceError(code, "Qualified public failure", status)

    assert CatalogueTools(Failed(), lambda: identity()).list(request_payload()) == {
        "error": {"code": code, "message": "Qualified public failure"},
    }
