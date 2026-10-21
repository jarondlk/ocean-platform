"""C16 route policy, shared direct parity and responsive worker boundaries."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import threading

import anyio
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api import auth
import api.catalogue_browser_routes as routes
from orchestration.catalogue_browser import CatalogueBrowser
from schema.catalogue_browser import CatalogueSnapshotsRequest
from tests.catalogue_service_support import fixture_user
from tests.test_catalogue_browser import configured, payload


def application(browser=None):
    app = FastAPI()
    app.middleware("http")(auth.authorization_middleware)
    app.include_router(routes.router)
    if browser is not None:
        app.state.catalogue_browser = browser
        app.state.catalogue_service = browser.service
    return app


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setenv("ENABLE_V1_CATALOGUE_BROWSER", "true")
    monkeypatch.setattr(auth, "authenticate_request", lambda request: fixture_user())


@pytest.mark.parametrize("role", ["researcher", "admin"])
def test_snapshot_api_and_direct_service_return_identical_permitted_pages(tmp_path, monkeypatch, role):
    _, _, browser, _, _, _ = configured(tmp_path)
    identity = fixture_user(role=role)
    monkeypatch.setattr(auth, "authenticate_request", lambda request: identity)
    body = payload(limit=1)
    with TestClient(application(browser)) as client:
        for _ in range(3):
            response = client.post("/catalogue/snapshots", json=body)
            assert response.status_code == 200
            assert response.json() == browser.discover(body, identity)
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            body = {**body, "cursor": response.json()["next_cursor"]}
    assert body["cursor"] is None


@pytest.mark.parametrize("kind,status,code", [("missing", 401, "authentication_required"), ("viewer", 403, "access_denied"), ("suspended", 403, "access_denied"), ("active", 422, "invalid_request")])
@pytest.mark.parametrize("flag", ["false", "true"])
def test_route_and_shared_builder_preserve_auth_validation_gate_order(tmp_path, monkeypatch, kind, status, code, flag):
    _, _, browser, _, state, _ = configured(tmp_path)
    identity = None if kind == "missing" else fixture_user(role="viewer" if kind == "viewer" else "researcher")
    if kind == "suspended":
        identity = replace(identity, status="suspended")

    def current(request):
        if identity is None:
            raise auth.AuthenticationFailure(401, "Authentication required")
        if identity.status != "active":
            raise auth.AuthenticationFailure(403, "Suspended")
        return identity

    monkeypatch.setattr(auth, "authenticate_request", current)
    monkeypatch.setenv("ENABLE_V1_CATALOGUE_BROWSER", flag)
    body = payload(role="admin")
    with TestClient(application(browser)) as client:
        response = client.post("/catalogue/snapshots", json=body)
    direct = routes.snapshots_response(identity, browser, body, browser.service)
    assert response.status_code == direct.status_code == status
    assert response.json() == json.loads(direct.body)
    assert response.json()["error"]["code"] == code and state["calls"] == []


@pytest.mark.parametrize("method,path", [("GET", "/catalogue/snapshots"), ("POST", "/catalogue/snapshots/private"), ("POST", "/catalogue/snapshots/admin")])
def test_unknown_snapshot_methods_and_paths_remain_denied(method, path):
    assert auth.route_permission(method, path) is None
    with TestClient(application()) as client:
        assert client.request(method, path, json=payload()).status_code == 403


@pytest.mark.parametrize("flag", ["false", "true", "nonsense"])
def test_missing_browser_has_no_implicit_store_discovery(monkeypatch, flag):
    monkeypatch.setenv("ENABLE_V1_CATALOGUE_BROWSER", flag)
    with TestClient(application()) as client:
        response = client.post("/catalogue/snapshots", json=payload())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == ("catalogue_disabled" if flag == "false" else "catalogue_unavailable")
    assert "snapshots" not in response.json()


def test_snapshot_endpoint_is_registered_in_actual_api():
    from api.main import app
    assert "/catalogue/snapshots" in app.openapi()["paths"]


@pytest.mark.parametrize("mismatch", ["absent", "different"])
def test_snapshot_discovery_requires_same_explicit_service_as_c14_routes(tmp_path, mismatch):
    from tests.catalogue_service_support import synthetic_service

    _, _, browser, _, state, _ = configured(tmp_path)
    app = application(browser)
    if mismatch == "absent":
        del app.state.catalogue_service
    else:
        app.state.catalogue_service = synthetic_service(1)[2]
    with TestClient(app) as client:
        response = client.post("/catalogue/snapshots", json=payload())
    assert response.status_code == 503 and state["calls"] == []


def direct_request(browser):
    app = application(browser)
    request = Request({"type": "http", "method": "POST", "path": "/catalogue/snapshots", "query_string": b"", "headers": [], "scheme": "http", "server": ("test", 80), "app": app})
    request.state.current_user = fixture_user()
    return request


@pytest.mark.parametrize("cancel", [None, "anyio", "native"])
def test_policy_and_complete_response_stay_in_worker_with_cancellation_cleanup(tmp_path, monkeypatch, cancel):
    _, service, _, descriptors, _, _ = configured(tmp_path, count=1)
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    encoded = threading.Event()
    stages, delivered = [], []

    def blocked(user, descriptor):
        stages.append(("policy", threading.get_ident()))
        entered.set()
        try:
            assert release.wait(5)
            return True
        finally:
            closed.set()

    browser = CatalogueBrowser(service=service, snapshots=descriptors, permitted=blocked, revision="p1")
    original = routes.JSONResponse

    class Encoded(original):
        def __init__(self, *args, **kwargs):
            stages.append(("response", threading.get_ident()))
            super().__init__(*args, **kwargs)
            encoded.set()

    monkeypatch.setattr(routes, "JSONResponse", Encoded)

    async def scenario():
        loop_thread = threading.get_ident()
        holder = []

        async def invoke():
            with anyio.CancelScope() as scope:
                holder.append(scope)
                delivered.append(await routes.snapshots(direct_request(browser), CatalogueSnapshotsRequest.model_validate(payload())))

        task = asyncio.create_task(invoke())
        try:
            with anyio.fail_after(5):
                assert await anyio.to_thread.run_sync(entered.wait, 5)
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
            assert await anyio.to_thread.run_sync(encoded.wait, 5)
            assert closed.is_set()
        assert len({thread for _, thread in stages}) == 1 and stages[0][1] != loop_thread
        assert len(delivered) == (1 if cancel is None else 0)

    anyio.run(scenario)
