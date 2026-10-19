"""C20 exact HTTP boundary, safe public DTOs and worker resource lifetime."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import threading

import anyio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from starlette.requests import Request

from api import auth
from api import research_run_routes as routes
from api.rate_limit import InMemoryRateLimiter, policy_for_request
import config
from orchestration.investigations import InvestigationService
from orchestration.research_runs import ResearchRunError, ResearchRunService
from schema.context_catalogue_fixtures import fixture_scope
from schema.research_runs import RUN_REQUEST_MODELS, validate_run_response
from tests.catalogue_service_support import fixture_user

INV = "11223344-5566-7788-99aa-bbccddeeff00"
CONV = "22334455-6677-8899-aabb-ccddeeff0011"
REV = "33445566-7788-99aa-bbcc-ddeeff001122"
RUN = "44556677-8899-aabb-ccdd-eeff00112233"
KEY = "55667788-99aa-bbcc-ddee-ff0011223344"
CHILD = "66778899-aabb-ccdd-eeff-001122334455"
PREFIX = "/research/runs/"


def payload(name):
    conversation = {"investigation_id": INV, "conversation_id": CONV}
    address = {**conversation, "run_id": RUN}
    mutation = {**address, "idempotency_key": KEY}
    return {
        "submit": {**conversation, "revision_id": REV, "expected_snapshot_id": "a" * 64,
                   "expected_payload_sha256": "b" * 64, "question": "Synthetic question 調査", "idempotency_key": KEY},
        "status": address, "events": {**address, "after_cursor": 0},
        "cancel": mutation, "continue": mutation,
        "clarify": {**mutation, "clarification_id": KEY, "answer": "Complete clarified question 調査"},
        "list": conversation,
    }[name]


def run():
    return {
        "id": RUN,
        "context": {"binding": {"investigation_id": INV, "conversation_id": CONV, "revision_id": REV,
                    "snapshot_id": "a" * 64, "payload_sha256": "b" * 64},
                    "scope": fixture_scope().canonical(), "attachments": [], "pins": []},
        "question": "Synthetic question 調査", "status": "queued", "active_elapsed_ms": 0,
        "event_cursor": 0, "latest_event_cursor": 1, "activity": [], "continuation_of": None,
        "clarification": None, "clarification_id": None, "result": None, "error": None, "synthetic": False,
    }


def envelope(name, body):
    current = run()
    if name == "continue":
        current.update(id=CHILD, continuation_of=RUN)
    if name == "list":
        return {"version": "research-runs-v1", "items": [current], "next_cursor": None}
    if name == "events":
        return {"version": "research-runs-v1", "run_id": RUN, "binding": current["context"]["binding"],
                "after_cursor": body["after_cursor"], "next_cursor": 1, "latest_event_cursor": 1,
                "has_more": False, "events": [{"cursor": 1, "run_id": RUN, "elapsed_ms": 0,
                "kind": "accepted", "summary": {"en": "Research question accepted", "ja": "質問を受け付けました"}}]}
    return {"version": "research-runs-v1", "run": current}


class TrustedTestService(ResearchRunService):
    def __init__(self, callback=None):
        self.calls, self.callback = [], callback
        self.investigations = object.__new__(InvestigationService)
        self.investigations.site_id = self.site_id = "v1:c20-http-test"
        self.queue, self.controller_factory = object(), lambda identity: None

    def invoke(self, name, body, user):
        self.calls.append((name, body, user, threading.get_ident()))
        return self.callback(name, body, user) if self.callback else envelope(name, body)


def application(service=None, investigations=None):
    app = FastAPI()
    app.middleware("http")(auth.authorization_middleware)
    app.include_router(routes.router)
    app.state.research_run_service = service
    app.state.investigation_service = investigations if investigations is not None else getattr(service, "investigations", None)
    return app


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    for flag in ("RUNS", "DISPATCH", "CONTROLLER"):
        monkeypatch.setenv("ENABLE_V1_RESEARCH_" + flag, "true")
    monkeypatch.setattr(auth, "authenticate_request", lambda request: fixture_user())


@pytest.mark.parametrize("name", RUN_REQUEST_MODELS)
def test_all_seven_exact_actions_return_strict_public_dtos_on_worker(name):
    service = TrustedTestService()
    caller = threading.get_ident()
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + name, json=payload(name))
    parsed = RUN_REQUEST_MODELS[name].model_validate(payload(name))
    assert response.status_code == 200, response.text
    assert response.json() == envelope(name, parsed.model_dump(mode="json", exclude_none=True))
    assert service.calls[0][:3] == (name, parsed.model_dump(mode="json", exclude_none=True), fixture_user())
    assert service.calls[0][3] != caller
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert auth.route_permission("POST", PREFIX + name) == "chat:use"


@pytest.mark.parametrize("field", ["owner_id", "binding", "scope", "permissions", "context", "checkpoint", "budget", "queue", "model"])
@pytest.mark.parametrize("name", RUN_REQUEST_MODELS)
def test_request_cannot_supply_authority_replay_or_dispatch_fields(name, field):
    with pytest.raises(ValidationError):
        RUN_REQUEST_MODELS[name].model_validate({**payload(name), field: "private-secret"})


@pytest.mark.parametrize("change", [
    {"question": ""}, {"question": " \t\n"}, {"question": "x" * 8001},
    {"question": "\udfff"}, {"question": "hello\x00world"}, {"question": "hello\x7fworld"},
    {"idempotency_key": KEY.upper()}, {"revision_id": REV.replace("-", "")},
    {"expected_snapshot_id": "A" * 64}, {"expected_payload_sha256": "x"},
])
def test_bounded_question_and_canonical_bindings(change):
    with pytest.raises(ValidationError):
        RUN_REQUEST_MODELS["submit"].model_validate({**payload("submit"), **change})


@pytest.mark.parametrize("name,field,value", [
    ("events", "after_cursor", True), ("events", "after_cursor", -1),
    ("events", "after_cursor", 9007199254740992), ("events", "after_cursor", "1"),
    ("list", "limit", 0), ("list", "limit", 501), ("list", "limit", True),
    ("events", "limit", 1.5), ("list", "cursor", ""), ("list", "cursor", "x" * 4097),
])
def test_page_bounds_are_strict_and_js_safe(name, field, value):
    with pytest.raises(ValidationError):
        RUN_REQUEST_MODELS[name].model_validate({**payload(name), field: value})


@pytest.mark.parametrize("raw", [
    b'{"limit":1,"limit":2}', b'{"limit":NaN}', b'{"limit":Infinity}',
    b'{"cursor":"\\udfff"}', b'{"cursor":"\xff"}', b'null', b'[]', b'',
    b'[' * 130 + b'0' + b']' * 130, b'{}' + b' ' * routes.MAX_REQUEST_BYTES,
])
def test_ambiguous_invalid_and_excessive_body_is_safe_before_service(raw):
    service = TrustedTestService()
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + "list", content=raw)
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "invalid_request", "message": "Research request is invalid"}}
    assert not service.calls


@pytest.mark.parametrize("method,suffix", [("GET", "status"), ("PUT", "cancel"), ("POST", "status/"), ("POST", "admin"), ("POST", "approve")])
def test_unknown_routes_or_experiment_approval_cannot_dispatch(method, suffix):
    assert auth.route_permission(method, PREFIX + suffix) is None
    service = TrustedTestService()
    with TestClient(application(service)) as client:
        response = client.request(method, PREFIX + suffix, json={})
    assert response.status_code == 403 and not service.calls


def test_query_cannot_change_fixed_operation_or_target():
    service = TrustedTestService()
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + "status?owner=private-secret", json=payload("status"))
    assert response.status_code == 422 and not service.calls
    assert "private-secret" not in response.text


@pytest.mark.parametrize("declared_length", [None, 2])
def test_chunked_request_limit_stops_before_unread_tail(declared_length):
    service = TrustedTestService()
    app = application(service)
    chunks = [b"{}", b" " * (routes.MAX_REQUEST_BYTES - 2), b" ", b"NEVER READ THIS TAIL"]
    received, sent = [], []
    headers = [(b"content-type", b"application/json")]
    if declared_length is not None:
        headers.append((b"content-length", str(declared_length).encode()))
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "http_version": "1.1", "method": "POST", "scheme": "http", "path": PREFIX + "list",
             "raw_path": (PREFIX + "list").encode(), "root_path": "", "query_string": b"", "headers": headers,
             "server": ("test", 80), "client": ("127.0.0.1", 1234)}

    async def receive():
        index = len(received)
        received.append(index)
        assert index < len(chunks)
        return {"type": "http.request", "body": chunks[index], "more_body": index < len(chunks) - 1}

    async def send(message):
        sent.append(message)

    async def scenario():
        await app(scope, receive, send)

    anyio.run(scenario)
    assert len(received) == 3 and not service.calls
    assert next(item["status"] for item in sent if item["type"] == "http.response.start") == 422
    result = json.loads(b"".join(item.get("body", b"") for item in sent if item["type"] == "http.response.body"))
    assert result["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("kind", ["missing", "suspended", "viewer", "chat_only"])
def test_current_identity_precedes_validation_and_configuration(monkeypatch, kind):
    user = None if kind == "missing" else fixture_user(role="viewer" if kind == "viewer" else "researcher")
    if kind == "suspended":
        user = replace(user, status="suspended")
    if kind == "chat_only":
        user = replace(user, permissions=frozenset({"chat:use"}))

    def current(_request):
        if user is None:
            raise auth.AuthenticationFailure(401, "private-secret")
        if user.status != "active":
            raise auth.AuthenticationFailure(403, "private-secret")
        return user

    monkeypatch.setattr(auth, "authenticate_request", current)
    monkeypatch.setenv("ENABLE_V1_RESEARCH_RUNS", "false")
    service = TrustedTestService()
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + "status", json={"private-invalid": "private-secret"})
    direct = routes.research_run_response(user, service, service.investigations, "status", {})
    assert response.status_code == direct.status_code == (401 if user is None else 403)
    assert "private-secret" not in response.text and not service.calls


@pytest.mark.parametrize("flag,value", [("RUNS", "false"), ("RUNS", "invalid"), ("DISPATCH", "false"), ("DISPATCH", "invalid"), ("CONTROLLER", "false")])
def test_disabled_execution_never_calls_dispatch(monkeypatch, flag, value):
    monkeypatch.setenv("ENABLE_V1_RESEARCH_" + flag, value)
    service = TrustedTestService()
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + "submit", json=payload("submit"))
    assert response.status_code == 503 and not service.calls


@pytest.mark.parametrize("name", ["status", "events", "cancel", "list"])
def test_dispatch_disable_preserves_history_and_cancel(monkeypatch, name):
    monkeypatch.setenv("ENABLE_V1_RESEARCH_DISPATCH", "false")
    monkeypatch.setenv("ENABLE_V1_RESEARCH_CONTROLLER", "false")
    service = TrustedTestService()
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + name, json=payload(name))
    assert response.status_code == 200, response.text
    assert len(service.calls) == 1


@pytest.mark.parametrize("kind", ["missing", "wrong", "mismatch", "no_queue", "no_controller"])
def test_unconfigured_dependency_has_no_ambient_fallback(kind):
    service = TrustedTestService()
    investigations = service.investigations
    if kind == "missing":
        service = None
    elif kind == "wrong":
        service = object()
    elif kind == "mismatch":
        investigations = object.__new__(InvestigationService)
    elif kind == "no_queue":
        service.queue = None
    elif kind == "no_controller":
        service.controller_factory = None
    with TestClient(application(service, investigations)) as client:
        response = client.post(PREFIX + "submit", json=payload("submit"))
    assert response.status_code == 503


@pytest.mark.parametrize("kind", ["raw_error", "nonfinite", "private_field", "synthesis", "wrong_run", "wrong_binding", "fake_flag", "bool_cursor", "truncated_activity"])
def test_worker_output_cannot_leak_private_data_or_fabricate_synthesis(kind):
    def callback(name, body, user):
        if kind == "raw_error":
            raise RuntimeError("private-secret")
        result = envelope(name, body)
        item = result["run"]
        if kind == "nonfinite":
            item["active_elapsed_ms"] = float("nan")
        elif kind == "private_field":
            item["checkpoint"] = "private-secret"
        elif kind == "synthesis":
            item["result"] = {"answer": "private-secret"}
        elif kind == "wrong_run":
            item["id"] = CHILD
        elif kind == "wrong_binding":
            item["context"]["binding"]["conversation_id"] = CHILD
        elif kind == "fake_flag":
            item["synthetic"] = 0
        elif kind == "bool_cursor":
            item["event_cursor"] = False
        else:
            item["activity"] = envelope("events", {"after_cursor": 0})["events"]
        return result

    service = TrustedTestService(callback)
    with TestClient(application(service)) as client:
        response = client.post(PREFIX + "status", json=payload("status"))
    assert response.status_code == 503
    assert "private-secret" not in response.text


@pytest.mark.parametrize("change", [
    {"next_cursor": 2}, {"latest_event_cursor": 0}, {"has_more": True},
    {"after_cursor": 1}, {"run_id": CHILD},
])
def test_events_must_be_consecutive_and_match_requested_highwater(change):
    data = RUN_REQUEST_MODELS["events"].model_validate(payload("events"))
    result = envelope("events", {"after_cursor": 0})
    with pytest.raises(ValueError):
        validate_run_response("events", {**result, **change}, data)
    result = deepcopy(result)
    result["events"][0]["cursor"] = 2
    with pytest.raises(ValueError):
        validate_run_response("events", result, data)


def test_controlled_service_error_is_safe_and_retains_status():
    def unavailable(*_args):
        raise ResearchRunError("conflict", 409)

    with TestClient(application(TrustedTestService(unavailable))) as client:
        response = client.post(PREFIX + "status", json=payload("status"))
    assert response.status_code == 409 and response.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize("cancel_kind", ["anyio", "asyncio"])
def test_disconnect_does_not_cancel_durable_operation_and_response_waits_for_close(cancel_kind):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    returned = []

    def callback(name, body, user):
        entered.set()
        try:
            assert release.wait(5)
            return envelope(name, body)
        finally:
            closed.set()

    service = TrustedTestService(callback)
    app = application(service)
    request = Request({"type": "http", "method": "POST", "path": PREFIX + "submit", "headers": [], "app": app,
                       "state": {"current_user": fixture_user()}})

    async def scenario():
        scope_holder = []

        async def invoke():
            with anyio.CancelScope() as scope:
                scope_holder.append(scope)
                returned.append(await routes._invoke(request, "submit", RUN_REQUEST_MODELS["submit"].model_validate(payload("submit"))))

        task = asyncio.create_task(invoke())
        try:
            with anyio.fail_after(5):
                while not entered.is_set():
                    await anyio.sleep(0.001)
            if cancel_kind == "anyio":
                scope_holder[0].cancel()
            else:
                task.cancel()
            release.set()
            await asyncio.gather(task, return_exceptions=True)
            with anyio.fail_after(5):
                while not closed.is_set():
                    await anyio.sleep(0.001)
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    anyio.run(scenario)
    assert closed.is_set() and not returned
    assert len(service.calls) == 1


@pytest.mark.parametrize("name,helper", [("ENABLE_V1_RESEARCH_RUNS", config.v1_research_runs_enabled), ("ENABLE_V1_RESEARCH_DISPATCH", config.v1_research_dispatch_enabled)])
def test_new_flags_are_strict_dynamic_and_default_closed(monkeypatch, name, helper):
    monkeypatch.setattr(config, name, "false")
    assert helper({}) is False
    for value, expected in (("true", True), ("false", False), ("1", True), ("0", False)):
        monkeypatch.setenv(name, value)
        assert helper() is expected
    with pytest.raises(config.SecurityConfigurationError):
        helper({name: "ambiguous"})


def test_new_dispatch_actions_share_one_identity_limit_separate_from_cancel_and_reads():
    limiter = InMemoryRateLimiter()
    for name in ["submit", "clarify", "continue", "submit", "submit", "clarify", "continue", "submit", "submit", "submit"]:
        assert limiter.retry_after(subject="owner", policy=policy_for_request("POST", PREFIX + name), now=100) is None
    assert limiter.retry_after(subject="owner", policy=policy_for_request("POST", PREFIX + "continue"), now=100) == 60
    assert limiter.retry_after(subject="other", policy=policy_for_request("POST", PREFIX + "submit"), now=100) is None
    for name in ("cancel", "status", "events", "list"):
        assert limiter.retry_after(subject="owner", policy=policy_for_request("POST", PREFIX + name), now=100) is None
    assert policy_for_request("POST", PREFIX + "approve") is None
