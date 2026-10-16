"""C15 runtime bootstrap checks using actual auth middleware and explicit hosts."""
from dataclasses import replace
import json
import threading
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import auth
from api.auth import CurrentUser, ROLE_PERMISSIONS
from api.v1_runtime_routes import (
    DEFERRED_REASONS, REQUIRED_PERMISSIONS, VERSION,
    V1RuntimeConfiguration, router, runtime_response,
)


def user(role="researcher", **changes):
    value = CurrentUser(
        id=uuid.UUID("f4d4245b-3ae5-4bd2-9c64-7c359d1a8791"),
        email="separate-v1@example.invalid", display_name="V1 Test User",
        role=role, account_type="commercial", status="active",
        permissions=ROLE_PERMISSIONS[role], auth_provider="synthetic-v1-tests",
    )
    return replace(value, **changes)


@pytest.fixture
def application(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("ENABLE_V1_SHELL", "true")
    state = {"user": user(), "calls": 0}

    def current(request):
        state["calls"] += 1
        if state["user"] is None:
            raise auth.AuthenticationFailure(401, "Authentication is required")
        if state["user"].status != "active":
            raise auth.AuthenticationFailure(403, "This account is suspended")
        return state["user"]

    monkeypatch.setattr(auth, "authenticate_request", current)
    app = FastAPI()
    app.state.v1_runtime_configuration = V1RuntimeConfiguration(
        site_id="v1:synthetic-shell-tests", revision="configuration-1"
    )
    app.middleware("http")(auth.authorization_middleware)
    @app.middleware("http")
    async def capture_loop_thread(request, call_next):
        state["loop_thread"] = threading.get_ident()
        return await call_next(request)
    app.include_router(router)
    return app, state


@pytest.mark.parametrize("role", ["viewer", "researcher", "admin"])
def test_runtime_uses_current_identity_and_fixed_permissions_before_capabilities(application, role):
    app, state = application
    state["user"] = user(role)
    with TestClient(app) as client:
        response = client.get("/v1/runtime")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    body = response.json()
    assert body["version"] == VERSION and body["deployment"] == "v1"
    assert body["identity"]["role"] == role
    assert body["identity"]["account_type"] == "commercial"
    assert "email" not in body["identity"]
    assert body["identity"]["permissions"] == sorted(ROLE_PERMISSIONS[role])
    assert set(body["capabilities"]) == set(REQUIRED_PERMISSIONS)
    for name, required in REQUIRED_PERMISSIONS.items():
        capability = body["capabilities"][name]
        assert capability["required_permissions"] == list(required)
        permitted = set(required) <= ROLE_PERMISSIONS[role]
        assert capability["status"] == (
            "forbidden" if not permitted else "unavailable" if name in DEFERRED_REASONS else "ready"
        )
        assert (capability["reason"] is None) == (capability["status"] == "ready")


def test_membership_identity_and_capability_changes_produce_fresh_revision(application):
    app, state = application
    with TestClient(app) as client:
        original = client.get("/v1/runtime").json()
        state["user"] = user("viewer")
        revoked = client.get("/v1/runtime").json()
        assert revoked["identity"]["id"] == original["identity"]["id"]
        assert revoked["permission_revision"] != original["permission_revision"]
        assert revoked["capabilities"]["catalogue"]["status"] == "forbidden"
        app.state.v1_runtime_configuration = V1RuntimeConfiguration(
            site_id="v1:synthetic-shell-tests", revision="configuration-2"
        )
        changed = client.get("/v1/runtime").json()
        assert changed["permission_revision"] != revoked["permission_revision"]
    assert state["calls"] == 3


@pytest.mark.parametrize("value,status", [(None, 401), (user(status="suspended"), 403)])
def test_missing_or_suspended_identity_cannot_receive_runtime_state(application, value, status):
    app, state = application
    state["user"] = value
    with TestClient(app) as client:
        response = client.get("/v1/runtime")
    assert response.status_code == status
    assert "capabilities" not in response.text


@pytest.mark.parametrize("flag", ["false", "not-a-boolean"])
def test_disabled_or_invalid_flag_never_invokes_runtime_configuration(application, monkeypatch, flag):
    app, _ = application
    monkeypatch.setenv("ENABLE_V1_SHELL", flag)
    calls = []
    app.state.v1_runtime_configuration = lambda identity: calls.append(identity)
    with TestClient(app) as client:
        response = client.get("/v1/runtime")
    assert response.status_code == 503
    assert calls == []


def test_missing_or_failed_explicit_configuration_has_no_discovery_or_preview_fallback(application):
    app, _ = application
    with TestClient(app) as client:
        del app.state.v1_runtime_configuration
        assert client.get("/v1/runtime").status_code == 503

        def failed(identity):
            raise OSError("/private/legacy-secret-path must not escape")

        app.state.v1_runtime_configuration = failed
        response = client.get("/v1/runtime")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "runtime_unavailable", "message": "V1 runtime is unavailable"}}


@pytest.mark.parametrize("query", ["role=admin", "account_type=internal", "preview=1", "permissions=users:manage"])
def test_query_parameters_cannot_choose_runtime_identity_or_preview(application, query):
    app, _ = application
    with TestClient(app) as client:
        response = client.get("/v1/runtime?" + query)
    assert response.status_code == 422
    assert "identity" not in response.json()


@pytest.mark.parametrize("method,path", [("POST", "/v1/runtime"), ("GET", "/v1/runtime/admin"), ("GET", "/v1/unknown")])
def test_unknown_runtime_paths_or_methods_remain_denied(application, method, path):
    app, _ = application
    with TestClient(app) as client:
        assert client.request(method, path).status_code == 403


@pytest.mark.parametrize("capability", list(DEFERRED_REASONS))
def test_configuration_cannot_enable_unintegrated_domain_workflows(capability):
    configuration = V1RuntimeConfiguration(site_id="v1:synthetic", revision="one")
    states = {**configuration.capabilities, capability: "ready"}
    with pytest.raises(ValueError):
        V1RuntimeConfiguration(site_id="v1:synthetic", revision="one", capabilities=states)


def test_configuration_is_detached_immutable_and_requires_v1_site_identity():
    original = dict(V1RuntimeConfiguration(site_id="v1:test", revision="one").capabilities)
    configuration = V1RuntimeConfiguration(site_id="v1:test", revision="one", capabilities=original)
    original["settings"] = "disabled"
    assert configuration.capabilities["settings"] == "ready"
    with pytest.raises(TypeError):
        configuration.capabilities["settings"] = "disabled"
    with pytest.raises(ValueError):
        V1RuntimeConfiguration(site_id="legacy", revision="one")


def test_complete_configuration_callback_and_response_encoding_run_on_worker(application):
    app, state = application
    threads = []

    def configured(identity):
        threads.append(threading.get_ident())
        return V1RuntimeConfiguration(site_id="v1:test", revision="worker-1")

    app.state.v1_runtime_configuration = configured
    with TestClient(app) as client:
        response = client.get("/v1/runtime")
    assert response.status_code == 200
    assert threads and threads[0] != state["loop_thread"]


def test_direct_builder_never_accepts_untrusted_or_inactive_identity(monkeypatch):
    monkeypatch.setenv("ENABLE_V1_SHELL", "true")
    configured = V1RuntimeConfiguration(site_id="v1:test", revision="one")
    assert runtime_response({"role": "admin"}, configured).status_code == 401
    denied = runtime_response(user(permissions=frozenset()), configured)
    assert denied.status_code == 403
    assert "identity" not in json.loads(denied.body)
