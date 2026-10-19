"""C20 execution bootstrap is explicit, fresh and separate from history access."""
from fastapi.testclient import TestClient
import pytest

from api.v1_runtime_routes import V1RuntimeConfiguration
from orchestration.research_dispatch import FakeResearchQueue
from orchestration.research_runs import ResearchRunService
from tests import test_v1_runtime as runtime_fixtures

application = runtime_fixtures.application
research_application = runtime_fixtures.research_application
user = runtime_fixtures.user


@pytest.fixture
def runs_application(research_application, monkeypatch):
    app, state = research_application
    for flag in ("RUNS", "DISPATCH", "CONTROLLER"):
        monkeypatch.setenv("ENABLE_V1_RESEARCH_" + flag, "true")
    investigations = app.state.investigation_service
    app.state.research_run_service = ResearchRunService(
        session_factory=investigations.session_factory, site_id=investigations.site_id,
        investigations=investigations, queue=FakeResearchQueue(),
        controller_factory=lambda identity: pytest.fail("Bootstrap cannot execute a controller"),
    )
    return app, state


@pytest.mark.parametrize("gate", [
    "ready", "runs_disabled", "runs_invalid", "dispatch_disabled", "dispatch_invalid",
    "controller_disabled", "controller_invalid", "queue_missing", "factory_missing",
    "service_missing", "service_wrong", "store_mismatch", "site_mismatch",
    "context_disabled", "viewer", "no_data", "no_chat",
])
def test_bootstrap_requires_actual_matching_store_and_explicit_dispatch(runs_application, monkeypatch, gate):
    app, state = runs_application
    service = app.state.research_run_service
    flag_changes = {
        "runs_disabled": ("RUNS", "false"), "runs_invalid": ("RUNS", "invalid"),
        "dispatch_disabled": ("DISPATCH", "false"), "dispatch_invalid": ("DISPATCH", "invalid"),
        "controller_disabled": ("CONTROLLER", "false"), "controller_invalid": ("CONTROLLER", "invalid"),
    }
    if gate in flag_changes:
        flag, value = flag_changes[gate]
        monkeypatch.setenv("ENABLE_V1_RESEARCH_" + flag, value)
    elif gate == "queue_missing":
        service.queue = None
    elif gate == "factory_missing":
        service.controller_factory = None
    elif gate == "service_missing":
        del app.state.research_run_service
    elif gate == "service_wrong":
        app.state.research_run_service = object()
    elif gate == "store_mismatch":
        service.investigations = object()
    elif gate == "site_mismatch":
        service.site_id = "v1:unrelated-site"
    elif gate == "context_disabled":
        configuration = app.state.v1_runtime_configuration
        app.state.v1_runtime_configuration = V1RuntimeConfiguration(
            site_id=configuration.site_id, revision=configuration.revision,
            capabilities={**configuration.capabilities, "research": "disabled"},
        )
    elif gate == "viewer":
        state["user"] = user("viewer")
    elif gate in {"no_chat", "no_data"}:
        removed = "chat:use" if gate == "no_chat" else "data:read"
        state["user"] = user(permissions=state["user"].permissions - {removed})
    with TestClient(app) as client:
        response = client.get("/v1/runtime")
    assert response.status_code == 200, response.text
    capability = response.json()["research_runs"]
    history = gate in {"ready", "dispatch_disabled", "dispatch_invalid", "controller_disabled", "controller_invalid", "queue_missing", "factory_missing"}
    assert capability["transport"] == ("http-v1" if history else "unavailable")
    assert capability["submit_enabled"] is capability["dispatch_enabled"] is (gate == "ready")
    assert capability["version"] == "research-runs-v1" and capability["synthesis"] == "unavailable"
    assert (capability["reason"] is None) is (gate == "ready")


def test_dispatch_toggle_changes_permission_revision_but_preserves_history(runs_application, monkeypatch):
    app, _ = runs_application
    with TestClient(app) as client:
        first = client.get("/v1/runtime").json()
        monkeypatch.setenv("ENABLE_V1_RESEARCH_DISPATCH", "false")
        disabled = client.get("/v1/runtime").json()
        monkeypatch.setenv("ENABLE_V1_RESEARCH_DISPATCH", "true")
        restored = client.get("/v1/runtime").json()
    assert first == restored
    assert disabled["research_runs"]["transport"] == "http-v1"
    assert first["permission_revision"] != disabled["permission_revision"]
