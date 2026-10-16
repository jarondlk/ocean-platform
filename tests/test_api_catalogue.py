"""C14 route policy, API/tool equivalence and worker-owned execution."""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import replace

import anyio
import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import api.auth as auth
import api.catalogue_routes as routes
from api.auth import CurrentUser, ROLE_PERMISSIONS
from orchestration.catalogue_service import CatalogueServiceError
from orchestration.catalogue_tools import CatalogueTools, invoke_catalogue
from schema.catalogue_service import CatalogueListRequest
from schema.context_catalogue_fixtures import fixture_scope


def identity(role="researcher"):
    return CurrentUser(
        id=uuid.UUID(int=5), email="synthetic@example.invalid", display_name=None,
        role=role, account_type="research", status="active",
        permissions=ROLE_PERMISSIONS[role], auth_provider="oidc",
    )


def payload(**extra):
    return {
        "snapshot_id": "synthetic:snapshot",
        "scope": fixture_scope("ctd").model_dump(mode="json"), **extra,
    }


CALLS = [
    ("overview", "/catalogue/overview", {}),
    ("list", "/catalogue/list", {}),
    ("open", "/catalogue/open", {"object_id": "synthetic:dataset"}),
    ("coverage", "/catalogue/coverage", {"object_id": "synthetic:dataset"}),
    ("query", "/catalogue/query", {
        "operation_id": "c13.inventory", "operation_version": "c13-v1",
        "input_ids": ["synthetic:dataset"],
    }),
    ("relationships", "/catalogue/relationships", {}),
    ("get_published", "/catalogue/analysis/get-published", {"analysis_id": "synthetic:analysis"}),
]


class Service:
    def __init__(self):
        self.calls = []

    def execute(self, name, data, user):
        self.calls.append((name, data, user, threading.get_ident()))
        return {
            "operation": name, "identities": ["synthetic:target"],
            "total_matching": 100001, "returned_count": 1,
            "scope": data["scope"], "qualifications": ["Synthetic"],
        }


def application(service=None):
    app = FastAPI()
    app.middleware("http")(auth.authorization_middleware)
    app.include_router(routes.router)
    if service is not None:
        app.state.catalogue_service = service

    @app.get("/health/live")
    async def live():
        return {"status": "live"}

    return app


@pytest.fixture(autouse=True)
def safe_environment(monkeypatch):
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setattr(auth, "authenticate_request", lambda request: identity())


@pytest.mark.parametrize("method,path,extra", CALLS)
@pytest.mark.parametrize("role", ["researcher", "admin"])
def test_seven_api_operations_equal_typed_tools(monkeypatch, method, path, extra, role):
    user = identity(role)
    monkeypatch.setattr(auth, "authenticate_request", lambda request: user)
    service = Service()
    app = application(service)
    with TestClient(app) as client:
        response = client.post(path, json=payload(**extra))
    tool = getattr(CatalogueTools(service, lambda: user), method)(payload(**extra))
    assert response.status_code == 200
    assert response.json() == tool
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert service.calls[0][2] is user


@pytest.mark.parametrize("method,path,extra", CALLS)
def test_viewer_cannot_discover_catalogue_counts_or_objects(monkeypatch, method, path, extra):
    monkeypatch.setattr(auth, "authenticate_request", lambda request: identity("viewer"))
    service = Service()
    with TestClient(application(service)) as client:
        response = client.post(path, json=payload(**extra))
    assert response.status_code == 403
    assert response.json() == {"error": {"code": "access_denied", "message": "Catalogue access is denied"}}
    assert service.calls == []


@pytest.mark.parametrize("path", [call[1] for call in CALLS])
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH", "HEAD"])
def test_catalogue_routes_allow_only_explicit_post_policies(path, method):
    assert auth.route_permission(method, path) is None


@pytest.mark.parametrize("path", ["/catalogue", "/catalogue/sql", "/catalogue/list/extra", "/catalogue/analysis/run"])
def test_unknown_catalogue_paths_are_denied_before_service(path):
    service = Service()
    with TestClient(application(service)) as client:
        response = client.post(path, json=payload())
    assert response.status_code == 403
    assert service.calls == []


def test_authentication_failure_has_typed_catalogue_error_and_security_headers(monkeypatch):
    def denied(request):
        raise auth.AuthenticationFailure(401, "private identity details")

    monkeypatch.setattr(auth, "authenticate_request", denied)
    with TestClient(application(Service())) as client:
        response = client.post("/catalogue/list", json=payload())
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "authentication_required", "message": "Authentication is required"}}
    assert response.headers["www-authenticate"] == "Bearer"
    assert "private" not in response.text


@pytest.mark.parametrize("field", ["access_binding", "access_revision", "role", "user", "sql"])
def test_forged_public_authority_has_same_error_on_api_and_tool(field):
    service = Service()
    data = payload(**{field: "forged"})
    with TestClient(application(service)) as client:
        response = client.post("/catalogue/list", json=data)
    assert response.status_code == 422
    assert response.json() == CatalogueTools(service, lambda: identity()).list(data)
    assert service.calls == []


def test_malformed_json_is_typed_and_does_not_echo_input():
    service = Service()
    with TestClient(application(service)) as client:
        response = client.post("/catalogue/list", content=b'{"private":"secret"', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "invalid_request", "message": "Catalogue request is invalid"}}
    assert service.calls == []


@pytest.mark.parametrize("flag", ["false", "0", "nonsense"])
def test_catalogue_feature_gate_is_fail_closed(monkeypatch, flag):
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", flag)
    service = Service()
    with TestClient(application(service)) as client:
        response = client.post("/catalogue/list", json=payload())
    assert response.status_code == 503
    assert response.json() == CatalogueTools(service, lambda: identity()).list(payload())
    assert service.calls == []


def test_enabled_flag_without_explicit_service_returns_unavailable():
    with TestClient(application()) as client:
        response = client.post("/catalogue/list", json=payload())
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "catalogue_unavailable", "message": "Catalogue is unavailable"}}


@pytest.mark.parametrize("flag", ["false", "true", "nonsense"])
@pytest.mark.parametrize("registered", [False, True])
def test_public_validation_precedes_feature_and_service_gates_on_both_boundaries(
    monkeypatch, flag, registered,
):
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", flag)
    service = Service() if registered else None
    data = payload(role="forged-admin")
    with TestClient(application(service)) as client:
        response = client.post("/catalogue/list", json=data)
    assert response.status_code == 422
    assert response.json() == CatalogueTools(service, lambda: identity()).list(data) == {
        "error": {"code": "invalid_request", "message": "Catalogue request is invalid"},
    }
    if service is not None:
        assert service.calls == []


@pytest.mark.parametrize("flag", ["false", "true"])
@pytest.mark.parametrize("kind", ["missing", "viewer", "suspended", "active"])
def test_authorization_precedes_invalid_body_and_feature_gate_for_api_and_tools(
    monkeypatch, flag, kind,
):
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", flag)
    user = None if kind == "missing" else identity("viewer" if kind == "viewer" else "researcher")
    if kind == "suspended":
        user = replace(user, status="suspended")

    def authenticate(request):
        if user is None:
            raise auth.AuthenticationFailure(401, "Authentication required")
        if user.status != "active":
            raise auth.AuthenticationFailure(403, "This account is suspended")
        return user

    monkeypatch.setattr(auth, "authenticate_request", authenticate)
    service = Service()
    data = payload(role="forged-admin")
    with TestClient(application(service)) as client:
        response = client.post("/catalogue/list", json=data)
    resolutions = []

    def provider():
        resolutions.append(True)
        return user

    status, result = invoke_catalogue(service, "catalogue.list", data, provider)
    assert status == response.status_code == {
        "missing": 401, "viewer": 403, "suspended": 403, "active": 422,
    }[kind]
    assert result == response.json()
    assert resolutions == [True]
    assert service.calls == []


@pytest.mark.parametrize("code,status", [("not_found", 404), ("invalid_cursor", 409), ("invalid_request", 422)])
def test_api_and_tool_preserve_identical_service_error(code, status):
    class Denied(Service):
        def execute(self, *args):
            raise CatalogueServiceError(code, "Qualified public error", status)

    service = Denied()
    with TestClient(application(service)) as client:
        response = client.post("/catalogue/list", json=payload())
    assert response.status_code == status
    assert response.json() == CatalogueTools(service, lambda: identity()).list(payload())


def test_routes_are_registered_in_application():
    from api.main import app

    assert {call[1] for call in CALLS} <= set(app.openapi()["paths"])


def direct_request(app):
    request = Request({
        "type": "http", "method": "POST", "path": "/catalogue/list",
        "query_string": b"", "headers": [], "scheme": "http",
        "server": ("test", 80), "app": app,
    })
    request.state.current_user = identity()
    return request


def test_complete_service_execution_and_response_serialization_use_one_worker(monkeypatch):
    stages = []
    entered, release = threading.Event(), threading.Event()
    original = routes.JSONResponse

    class RecordingJSONResponse(original):
        def __init__(self, *args, **kwargs):
            stages.append(("serialize", threading.get_ident()))
            super().__init__(*args, **kwargs)

    class Blocked(Service):
        def execute(self, *args):
            stages.append(("resolve-read-query", threading.get_ident()))
            entered.set()
            assert release.wait(5)
            return super().execute(*args)

    monkeypatch.setattr(routes, "JSONResponse", RecordingJSONResponse)

    async def scenario():
        loop_thread = threading.get_ident()
        app = application(Blocked())
        completed = []
        async with anyio.create_task_group() as group:
            async def invoke():
                completed.append(await routes.list_entries(direct_request(app), CatalogueListRequest.model_validate(payload())))
            group.start_soon(invoke)
            try:
                with anyio.fail_after(5):
                    while not entered.is_set():
                        await anyio.sleep(0)
                    # Liveness and the event loop progress before the worker is released.
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                        assert (await client.get("/health/live")).json() == {"status": "live"}
                    assert completed == []
            finally:
                release.set()
        assert len(completed) == 1
        assert stages[0][0] == "resolve-read-query" and stages[-1][0] == "serialize"
        assert len({thread for _, thread in stages}) == 1
        assert loop_thread not in {thread for _, thread in stages}
        assert json.loads(completed[0].body)["total_matching"] == 100001

    anyio.run(scenario)


@pytest.mark.parametrize("native", [False, True])
def test_cancelled_service_closes_worker_before_any_response_is_delivered(native):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    responses = []

    class Blocked(Service):
        def execute(self, *args):
            entered.set()
            try:
                assert release.wait(5)
                return super().execute(*args)
            finally:
                closed.set()

    async def scenario():
        app = application(Blocked())
        scope_holder = []

        async def invoke():
            with anyio.CancelScope() as scope:
                scope_holder.append(scope)
                responses.append(await routes.list_entries(direct_request(app), CatalogueListRequest.model_validate(payload())))

        task = asyncio.create_task(invoke())
        try:
            with anyio.fail_after(5):
                while not entered.is_set():
                    await anyio.sleep(0)
                if native:
                    task.cancel()
                else:
                    scope_holder[0].cancel()
                await anyio.sleep(0)
                assert responses == []
        finally:
            release.set()
        if native:
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
        with anyio.fail_after(5):
            while not closed.is_set():
                await anyio.sleep(0)
        assert responses == []
        # Cancellation does not poison a following independent invocation.
        app.state.catalogue_service = Service()
        assert (await routes.list_entries(direct_request(app), CatalogueListRequest.model_validate(payload()))).status_code == 200

    anyio.run(scenario)
