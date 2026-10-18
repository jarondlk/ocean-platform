"""C17 public contracts, exact permissions and complete worker boundaries."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import threading

import anyio
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from api import auth
import api.investigation_routes as routes
import config
from orchestration.investigations import InvestigationError, InvestigationService
from schema.context_catalogue_fixtures import fixture_scope
from schema.investigations import (
    ContextChangeRequest, INVESTIGATION_REQUEST_MODELS,
    InvestigationCreateRequest, InvestigationListRequest,
)
from tests.catalogue_service_support import fixture_user

INVESTIGATION = "11223344-5566-7788-99aa-bbccddeeff00"
CONVERSATION = "22334455-6677-8899-aabb-ccddeeff0011"
REVISION = "33445566-7788-99aa-bbcc-ddeeff001122"
OPERATION = "44556677-8899-aabb-ccdd-eeff00112233"
IDEMPOTENCY = "55667788-99aa-bbcc-ddee-ff0011223344"
SNAPSHOT = "a" * 64
PREFIX = "/research/investigations/"


def payload(name):
    investigation = {"investigation_id": INVESTIGATION}
    idempotent = {"idempotency_key": IDEMPOTENCY}
    conversation = {**investigation, "conversation_id": CONVERSATION}
    return {
        "create": {"name": "Synthetic investigation 調査", "snapshot_id": SNAPSHOT, "scope": fixture_scope().canonical(), **idempotent},
        "list": {},
        "get": investigation,
        "rename": {**investigation, "name": "Renamed 調査", "expected_version": 1, **idempotent},
        "archive": {**investigation, "expected_version": 1, **idempotent},
        "conversations/create": {**investigation, "name": "Synthetic conversation", **idempotent},
        "conversations/list": investigation,
        "conversations/get": conversation,
        "conversations/rename": {**conversation, "name": "Renamed conversation", "expected_version": 2, **idempotent},
        "context/get": investigation,
        "context/change": {
            **investigation, "expected_revision_id": REVISION, **idempotent,
            "change": {"op": "attach", "reference": {"kind": "catalogue", "id": "synthetic:dataset:1", "snapshot_id": SNAPSHOT}},
        },
        "refresh": {**investigation, "expected_revision_id": REVISION, "target_snapshot_id": "b" * 64, "name": "Updated branch", **idempotent},
        "operations/get": {"operation_id": OPERATION},
        "operations/retry": {"operation_id": OPERATION},
    }[name]


class TrustedTestService(InvestigationService):
    """Explicit configured test dependency, with no database or ambient target."""

    def __init__(self, callback=None):
        self.calls = []
        self.callback = callback

    def invoke(self, name, body, user):
        self.calls.append((name, body, user))
        if self.callback is not None:
            return self.callback(name, body, user)
        return {"version": "investigations-v1", "operation": name, "request": body}


def application(service=None):
    app = FastAPI()
    app.middleware("http")(auth.authorization_middleware)
    app.include_router(routes.router)
    if service is not None:
        app.state.investigation_service = service
    return app


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "true")
    monkeypatch.setattr(auth, "authenticate_request", lambda request: fixture_user())


@pytest.mark.parametrize("name", list(INVESTIGATION_REQUEST_MODELS))
@pytest.mark.parametrize("role", ["researcher", "admin"])
def test_every_exact_route_uses_current_identity_and_strict_json_payload(name, role, monkeypatch):
    service = TrustedTestService()
    identity = fixture_user(role=role)
    monkeypatch.setattr(auth, "authenticate_request", lambda request: identity)
    body = payload(name)
    expected = INVESTIGATION_REQUEST_MODELS[name].model_validate(body).model_dump(mode="json", exclude_none=True)
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + name, json=body)
    assert response.status_code == 200
    assert response.json() == {"version": "investigations-v1", "operation": name, "request": expected}
    assert service.calls == [(name, expected, identity)]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert auth.route_permission("POST", PREFIX + name) == "data:read"


@pytest.mark.parametrize("name", list(INVESTIGATION_REQUEST_MODELS))
def test_request_models_never_accept_server_owned_authorization_or_owner_fields(name):
    for field in ("owner_id", "role", "permissions", "account_type", "access_binding", "permission_revision"):
        with pytest.raises(ValidationError):
            INVESTIGATION_REQUEST_MODELS[name].model_validate({**payload(name), field: "private-secret"})


@pytest.mark.parametrize("kind,status,code", [("missing", 401, "authentication_required"), ("viewer", 403, "access_denied"), ("suspended", 403, "access_denied"), ("active", 422, "invalid_request")])
@pytest.mark.parametrize("flag", ["false", "true"])
def test_authentication_precedes_validation_flag_and_service_callbacks(monkeypatch, kind, status, code, flag):
    service = TrustedTestService()
    identity = None if kind == "missing" else fixture_user(role="viewer" if kind == "viewer" else "researcher")
    if kind == "suspended":
        identity = replace(identity, status="suspended")

    def current(request):
        if identity is None:
            raise auth.AuthenticationFailure(401, "Raw private authentication failure")
        if identity.status != "active":
            raise auth.AuthenticationFailure(403, "Raw private suspension failure")
        return identity

    monkeypatch.setattr(auth, "authenticate_request", current)
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", flag)
    body = {**payload("create"), "owner_id": "private-secret"}
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + "create", json=body)
    direct = routes.investigation_response(identity, service, "create", body)
    assert response.status_code == direct.status_code == status
    assert response.json() == json.loads(direct.body)
    assert response.json()["error"]["code"] == code
    assert "private" not in response.text and service.calls == []


@pytest.mark.parametrize("method,suffix", [("GET", "list"), ("PUT", "rename"), ("DELETE", "archive"), ("POST", "get/"), ("POST", "admin"), ("POST", "context/change/extra"), ("POST", "conversations/delete")])
def test_unknown_methods_and_paths_are_denied_by_default(method, suffix):
    assert auth.route_permission(method, PREFIX + suffix) is None
    service = TrustedTestService()
    with TestClient(application(service)) as client:
        response = client.request(method, PREFIX + suffix, json={})
    assert response.status_code == 403 and service.calls == []


@pytest.mark.parametrize("flag,code", [("false", "investigations_disabled"), ("nonsense", "investigations_unavailable")])
def test_disabled_or_invalid_configuration_does_not_call_service(monkeypatch, flag, code):
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", flag)
    service = TrustedTestService()
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + "list", json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == code and service.calls == []


@pytest.mark.parametrize("service", [None, object(), lambda: {"private": "secret"}])
def test_missing_or_wrong_configured_service_has_no_ambient_fallback(service):
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + "list", json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "investigations_unavailable"


@pytest.mark.parametrize("raw", [
    b'{"limit":1,"limit":100}',
    b'{"name":"private-secret","scope":{"sources":{},"sources":{}}}',
    b'{"limit":NaN}', b'{"limit":Infinity}', b'{"limit":-Infinity}',
    b'{"limit":true}', b'{"limit":"1"}', b'{"limit":1.5}',
    b'{"limit":0}', b'{"limit":101}', b'{"limit":9007199254740992}',
    b'{"after_id":"PRIVATE-SECRET"}', b'{"after_id":"112233445566778899aabbccddeeff00"}',
    b'{"after_id":"11223344-5566-7788-99AA-BBCCDDEEFF00"}',
    b'{"private":"\\ud800"}', b'{"private":"\xff"}', b'[]', b'null', b'',
    b'{"private":"' + b'x' * 262145 + b'"}',
    b'[' * 130 + b'0' + b']' * 130,
])
def test_malformed_or_ambiguous_input_is_sanitized_without_callback(raw):
    service = TrustedTestService()
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + "list", content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "invalid_request", "message": "Investigation request is invalid"}}
    assert service.calls == []


@pytest.mark.parametrize("patch", [
    {"name": ""}, {"name": " "}, {"name": " leading"}, {"name": "trailing "},
    {"name": "line\nbreak"}, {"name": "x" * 201}, {"name": "\udfff"},
    {"snapshot_id": "A" * 64}, {"snapshot_id": "abc"}, {"idempotency_key": "not-a-uuid"},
    {"scope": {"version": True, "sources": {}}},
])
def test_create_has_bounded_utf8_names_exact_snapshot_and_idempotency_contracts(patch):
    with pytest.raises(ValidationError):
        InvestigationCreateRequest.model_validate({**payload("create"), **patch})


@pytest.mark.parametrize("field,value", [("version", True), ("enabled", "true"), ("coordinate", "1"), ("coordinate", float("nan")), ("text", " surrounding ")])
def test_scope_keeps_c08_strict_scientific_meaning(field, value):
    body = payload("create")
    scope = body["scope"]
    if field == "version":
        scope["version"] = value
    elif field == "enabled":
        scope["sources"]["ctd"]["enabled"] = value
    elif field == "coordinate":
        scope["sources"]["remote_sensing"]["filters"]["lat_min"] = value
    else:
        scope["sources"]["ctd"]["filters"]["station"] = value
    with pytest.raises(ValidationError):
        InvestigationCreateRequest.model_validate(body)


@pytest.mark.parametrize("op", ["attach", "detach", "pin", "unpin", "scope"])
def test_context_operations_preserve_reference_scope_separation(op):
    body = payload("context/change")
    change = {"op": op, "scope": fixture_scope().canonical()} if op == "scope" else {**body["change"], "op": op}
    result = ContextChangeRequest.model_validate({**body, "change": change}).model_dump(mode="json")
    assert result["change"]["op"] == op
    assert ("reference" in result["change"]) == (op != "scope")
    assert ("scope" in result["change"]) == (op == "scope")
    wrong = {**change, "reference" if op == "scope" else "scope": body["change"]["reference"] if op == "scope" else fixture_scope().canonical()}
    with pytest.raises(ValidationError):
        ContextChangeRequest.model_validate({**body, "change": wrong})


@pytest.mark.parametrize("extra", ["label", "content_hash", "owner_id", "narrative", "review_approved"])
def test_references_cannot_trust_submitted_labels_hashes_or_narrative(extra):
    body = payload("context/change")
    body["change"]["reference"][extra] = "private-secret"
    with pytest.raises(ValidationError):
        ContextChangeRequest.model_validate(body)


def test_pagination_and_archive_defaults_are_explicit_and_restoration_is_boolean():
    assert InvestigationListRequest.model_validate({}).model_dump() == {"limit": 25, "after_id": None}
    archive = INVESTIGATION_REQUEST_MODELS["archive"]
    body = payload("archive")
    assert archive.model_validate(body).archived is True
    assert archive.model_validate({**body, "archived": False}).archived is False
    for value in ("false", 0, 1):
        with pytest.raises(ValidationError):
            archive.model_validate({**body, "archived": value})


@pytest.mark.parametrize("result", [[], None, {"value": float("inf")}, {"value": "\ud800"}, {"value": object()}, {"value": 9007199254740992}])
def test_unencodable_or_nonobject_service_results_fail_closed(result):
    service = TrustedTestService(lambda name, body, user: result)
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + "list", json={})
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "investigations_unavailable", "message": "Investigations are unavailable"}}


def test_unexpected_service_exception_does_not_expose_private_payload_or_paths():
    def failed(name, body, user):
        raise OSError("/private/legacy/secret-private-payload")
    with TestClient(application(TrustedTestService(failed))) as client:
        response = client.post(PREFIX + "list", json={})
    assert response.status_code == 503 and "private" not in response.text


@pytest.mark.parametrize("status,code,message", [
    (404, "not_found", "Investigation content is unavailable"),
    (409, "conflict", "Investigation version has changed"),
    (409, "unresolved_context", "Resolve unavailable context before submission"),
    (503, "operation_pending", "Investigation operation requires reconciliation"),
])
def test_safe_service_errors_keep_their_status_and_explicit_recovery_code(status, code, message):
    def failed(name, body, user):
        raise InvestigationError(status, code, message)
    with TestClient(application(TrustedTestService(failed))) as client:
        response = client.post(PREFIX + "list", json={})
    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": message}}


def test_explicit_flag_defaults_off_and_strictly_rejects_invalid_values(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_V1_INVESTIGATIONS", "false")
    assert config.v1_investigations_enabled({}) is False
    assert config.v1_investigations_enabled({"ENABLE_V1_INVESTIGATIONS": "true"}) is True
    with pytest.raises(config.SecurityConfigurationError):
        config.v1_investigations_enabled({"ENABLE_V1_INVESTIGATIONS": "sure"})


def test_exact_routes_are_registered_in_actual_application_without_research_ui_readiness():
    from api.main import app
    from api.v1_runtime_routes import V1RuntimeConfiguration

    paths = app.openapi()["paths"]
    assert all(set(paths[PREFIX + name]) == {"post"} for name in INVESTIGATION_REQUEST_MODELS)
    assert V1RuntimeConfiguration(site_id="v1:synthetic-c17", revision="one").capabilities["research"] == "unavailable"


def direct_request(service):
    app = application(service)
    request = Request({"type": "http", "method": "POST", "path": PREFIX + "list", "query_string": b"", "headers": [], "scheme": "http", "server": ("test", 80), "app": app})
    request.state.current_user = fixture_user()
    return request


@pytest.mark.parametrize("cancel", [None, "anyio", "native"])
def test_service_session_lifetime_and_json_encoding_stay_on_worker_until_cancellation_cleanup(monkeypatch, cancel):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    stages, delivered = [], []

    def blocked(name, body, user):
        stages.append(("service", threading.get_ident()))
        entered.set()
        try:
            assert release.wait(5)
            return {"version": "investigations-v1"}
        finally:
            closed.set()

    service = TrustedTestService(blocked)
    original = routes.JSONResponse

    class Encoded(original):
        def __init__(self, *args, **kwargs):
            stages.append(("response", threading.get_ident()))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(routes, "JSONResponse", Encoded)

    async def scenario():
        loop_thread = threading.get_ident()
        holder = []

        async def invoke():
            with anyio.CancelScope() as scope:
                holder.append(scope)
                delivered.append(await routes.list_investigations(direct_request(service), InvestigationListRequest()))

        task = asyncio.create_task(invoke())
        try:
            with anyio.fail_after(5):
                while not entered.is_set():
                    await anyio.sleep(0)
                assert delivered == []
                if cancel == "native":
                    task.cancel()
                elif cancel == "anyio":
                    holder[0].cancel()
                await anyio.sleep(0)
        finally:
            release.set()
        if cancel == "native":
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
        with anyio.fail_after(5):
            while not closed.is_set() or not any(stage == "response" for stage, _ in stages):
                await anyio.sleep(0)
        assert len({thread for _, thread in stages}) == 1 and stages[0][1] != loop_thread
        assert len(delivered) == (1 if cancel is None else 0)

    anyio.run(scenario)
