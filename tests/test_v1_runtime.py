"""C15 runtime bootstrap checks using actual auth middleware and explicit hosts."""
from dataclasses import replace
import asyncio
import json
import threading
import uuid

import pytest
import anyio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from api import auth
from api import v1_runtime_routes as routes
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


@pytest.mark.parametrize("capability", [name for name in DEFERRED_REASONS if name not in {"catalogue", "research"}])
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


@pytest.mark.parametrize("gate", ["ready", "catalogue_flag", "browser_flag", "invalid_flag", "service_missing", "browser_missing", "different_service", "not_requested", "viewer"])
def test_catalogue_ready_requires_explicit_configuration_flags_and_same_service(application, tmp_path, monkeypatch, gate):
    from tests.test_catalogue_browser import configured
    from tests.catalogue_service_support import synthetic_service

    app, state = application
    _, service, browser, _, _, _ = configured(tmp_path, count=1)
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setenv("ENABLE_V1_CATALOGUE_BROWSER", "true")
    app.state.catalogue_service = service
    app.state.catalogue_browser = browser
    initial = V1RuntimeConfiguration(site_id="v1:browser-tests", revision="configuration-1")
    app.state.v1_runtime_configuration = V1RuntimeConfiguration(
        site_id=initial.site_id, revision=initial.revision,
        capabilities={**initial.capabilities, "catalogue": "ready"},
    )
    if gate == "catalogue_flag":
        monkeypatch.setenv("ENABLE_V1_CATALOGUE", "false")
    elif gate == "browser_flag":
        monkeypatch.setenv("ENABLE_V1_CATALOGUE_BROWSER", "false")
    elif gate == "invalid_flag":
        monkeypatch.setenv("ENABLE_V1_CATALOGUE_BROWSER", "invalid")
    elif gate == "service_missing":
        del app.state.catalogue_service
    elif gate == "browser_missing":
        del app.state.catalogue_browser
    elif gate == "different_service":
        app.state.catalogue_service = synthetic_service(1)[2]
    elif gate == "not_requested":
        app.state.v1_runtime_configuration = initial
    elif gate == "viewer":
        state["user"] = user("viewer")
    with TestClient(app) as client:
        response = client.get("/v1/runtime")
    assert response.status_code == 200
    capabilities = response.json()["capabilities"]
    assert capabilities["catalogue"]["status"] == ("ready" if gate == "ready" else "forbidden" if gate == "viewer" else "unavailable")
    for name in DEFERRED_REASONS:
        if name != "catalogue":
            assert capabilities[name]["status"] != "ready"


@pytest.fixture
def research_application(application, tmp_path, monkeypatch):
    """Real compatible configured services; bootstrap must never open a session."""
    from orchestration.investigations import InvestigationService
    from tests.test_catalogue_browser import configured

    app, state = application
    for flag in ("ENABLE_V1_CATALOGUE", "ENABLE_V1_CATALOGUE_BROWSER", "ENABLE_V1_INVESTIGATIONS"):
        monkeypatch.setenv(flag, "true")
    store, catalogue, browser, _, _, _ = configured(tmp_path, count=1)

    def no_database_session():
        pytest.fail("Runtime context readiness must not connect to a database")

    investigations = InvestigationService(
        session_factory=no_database_session, site_id="v1:runtime-context-tests",
        catalogue_service=catalogue, snapshot_store=store,
        registrations=catalogue.resolver.registrations,
    )
    app.state.catalogue_service = catalogue
    app.state.catalogue_browser = browser
    app.state.investigation_service = investigations
    initial = V1RuntimeConfiguration(site_id=investigations.site_id, revision="context-ready-1")
    app.state.v1_runtime_configuration = V1RuntimeConfiguration(
        site_id=initial.site_id, revision=initial.revision,
        capabilities={**initial.capabilities, "research": "ready", "catalogue": "ready"},
    )
    return app, state


@pytest.mark.parametrize("gate", [
    "ready", "catalogue_flag", "browser_flag", "investigations_flag", "invalid_catalogue_flag",
    "invalid_browser_flag", "invalid_investigations_flag", "catalogue_missing", "browser_missing",
    "investigations_missing", "catalogue_wrong_type", "browser_wrong_type", "investigations_wrong_type",
    "browser_mismatch", "investigations_mismatch", "site_mismatch", "not_requested", "disabled",
    "without_chat", "without_data", "viewer", "admin", "no_profile",
])
def test_research_context_ready_requires_all_explicit_bindings_and_current_permissions(research_application, monkeypatch, gate):
    from tests.catalogue_service_support import synthetic_service

    app, state = research_application
    initial = app.state.v1_runtime_configuration
    flags = {
        "catalogue_flag": ("ENABLE_V1_CATALOGUE", "false"),
        "browser_flag": ("ENABLE_V1_CATALOGUE_BROWSER", "false"),
        "investigations_flag": ("ENABLE_V1_INVESTIGATIONS", "false"),
        "invalid_catalogue_flag": ("ENABLE_V1_CATALOGUE", "invalid"),
        "invalid_browser_flag": ("ENABLE_V1_CATALOGUE_BROWSER", "invalid"),
        "invalid_investigations_flag": ("ENABLE_V1_INVESTIGATIONS", "invalid"),
    }
    if gate in flags:
        monkeypatch.setenv(*flags[gate])
    if gate.endswith("_missing"):
        delattr(app.state, {"catalogue_missing": "catalogue_service", "browser_missing": "catalogue_browser", "investigations_missing": "investigation_service"}[gate])
    elif gate.endswith("_wrong_type"):
        setattr(app.state, {"catalogue_wrong_type": "catalogue_service", "browser_wrong_type": "catalogue_browser", "investigations_wrong_type": "investigation_service"}[gate], object())
    elif gate == "browser_mismatch":
        app.state.catalogue_browser.service = synthetic_service(1)[2]
    elif gate == "investigations_mismatch":
        app.state.investigation_service.catalogue = synthetic_service(1)[2]
    elif gate == "site_mismatch":
        app.state.investigation_service.site_id = "v1:another-independent-site"
    elif gate in {"not_requested", "disabled"}:
        app.state.v1_runtime_configuration = V1RuntimeConfiguration(
            site_id=initial.site_id, revision=initial.revision,
            capabilities={**initial.capabilities, "research": "disabled" if gate == "disabled" else "unavailable"},
        )
    elif gate in {"without_chat", "without_data", "no_profile"}:
        removed = {"without_chat": "chat:use", "without_data": "data:read", "no_profile": "profile:read"}[gate]
        state["user"] = user(permissions=ROLE_PERMISSIONS["researcher"] - {removed})
    elif gate in {"viewer", "admin"}:
        state["user"] = user(gate)
    with TestClient(app) as client:
        response = client.get("/v1/runtime")
    if gate == "no_profile":
        assert response.status_code == 403 and "identity" not in response.json()
        return
    assert response.status_code == 200
    research = response.json()["capabilities"]["research"]
    expected = "ready" if gate in {"ready", "admin"} else "disabled" if gate == "disabled" else "forbidden" if gate in {"viewer", "without_chat", "without_data"} else "unavailable"
    assert research["status"] == expected
    assert research["required_permissions"] == ["chat:use", "data:read"]
    if expected == "ready":
        assert research["reason"] is None
    else:
        assert isinstance(research["reason"], str) and research["reason"]
    assert all(response.json()["capabilities"][name]["status"] != "ready" for name in ("tools", "administration", "feedback"))


def test_research_readiness_changes_with_fresh_permissions_and_configuration(research_application, monkeypatch):
    app, state = research_application
    with TestClient(app) as client:
        ready = client.get("/v1/runtime").json()
        state["user"] = user(permissions=ROLE_PERMISSIONS["researcher"] - {"data:read"})
        revoked = client.get("/v1/runtime").json()
        assert revoked["capabilities"]["research"]["status"] == "forbidden"
        state["user"] = user()
        monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "false")
        unavailable = client.get("/v1/runtime").json()
        assert unavailable["capabilities"]["research"]["status"] == "unavailable"
        monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "yes")
        recovered = client.get("/v1/runtime").json()
    assert ready["permission_revision"] == recovered["permission_revision"]
    assert len({ready["permission_revision"], revoked["permission_revision"], unavailable["permission_revision"]}) == 3
    assert state["calls"] == 4


def test_c17_service_configuration_keeps_research_unavailable_by_default(research_application):
    app, _ = research_application
    app.state.v1_runtime_configuration = V1RuntimeConfiguration(
        site_id=app.state.investigation_service.site_id, revision="c17-default",
    )
    with TestClient(app) as client:
        response = client.get("/v1/runtime")
    assert response.status_code == 200
    assert response.json()["capabilities"]["research"]["status"] == "unavailable"


@pytest.mark.parametrize("cancel", [None, "anyio", "native"])
def test_context_configuration_guard_and_encoding_share_worker_and_cancel_suppresses_delivery(research_application, monkeypatch, cancel):
    app, state = research_application
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    stages, delivered = [], []
    configuration = app.state.v1_runtime_configuration

    def configured(identity):
        stages.append(("callback", threading.get_ident()))
        assert identity is state["user"]
        entered.set()
        try:
            assert release.wait(5)
            return configuration
        finally:
            closed.set()

    app.state.v1_runtime_configuration = configured
    original_guard, original_response = routes._research_available, routes.JSONResponse

    def guard(current_configuration, catalogue, browser, investigations):
        stages.append(("guard", threading.get_ident()))
        assert investigations is app.state.investigation_service
        return original_guard(current_configuration, catalogue, browser, investigations)

    class Encoded(original_response):
        def __init__(self, *args, **kwargs):
            stages.append(("response", threading.get_ident()))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(routes, "_research_available", guard)
    monkeypatch.setattr(routes, "JSONResponse", Encoded)
    request = Request({"type": "http", "method": "GET", "path": "/v1/runtime", "query_string": b"", "headers": [], "scheme": "http", "server": ("test", 80), "app": app})
    request.state.current_user = state["user"]

    async def scenario():
        loop_thread = threading.get_ident()
        holder = []

        async def invoke():
            with anyio.CancelScope() as scope:
                holder.append(scope)
                delivered.append(await routes.runtime(request))

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
        assert [name for name, _ in stages] == ["callback", "guard", "response"]
        assert len({thread for _, thread in stages}) == 1 and stages[0][1] != loop_thread
        assert len(delivered) == (1 if cancel is None else 0)
        if delivered:
            assert json.loads(delivered[0].body)["capabilities"]["research"]["status"] == "ready"

    anyio.run(scenario)
