"""Actual C20 HTTP, durable store and sealed C17/C14 controller integration."""
from dataclasses import dataclass
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select

from api import auth
from api.research_run_routes import router
from db.app_models import AppBase, AppUser, ResearchRun, ResearchRunEvent, ResearchRunInputHistory, ResearchRunOutbox
from tests.research_run_support import make_run_fixture


def key():
    return str(uuid.uuid4())


@dataclass
class HttpRunFixture:
    fixture: object
    client: object
    state: dict

    def post(self, name, body, status=200):
        response = self.client.post("/research/runs/" + name, json=body)
        assert response.status_code == status, response.text
        assert response.headers["cache-control"] == "no-store"
        result = response.json()
        if status == 200:
            assert result["version"] == "research-runs-v1"
        return result


@pytest.fixture
def http(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    for flag in ("CATALOGUE", "INVESTIGATIONS", "RESEARCH_CONTROLLER", "RESEARCH_RUNS", "RESEARCH_DISPATCH"):
        monkeypatch.setenv("ENABLE_V1_" + flag, "true")
    engine = create_engine("sqlite+pysqlite:///" + str(tmp_path / "separate-c20-http.sqlite"))

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    AppBase.metadata.create_all(engine)
    fixture = make_run_fixture(engine, tmp_path)
    state = {"principal": fixture.user}

    def current(_request):
        if state["principal"] is None:
            raise auth.AuthenticationFailure(401, "Synthetic missing session")
        return state["principal"]

    monkeypatch.setattr(auth, "authenticate_request", current)
    app = FastAPI()
    app.middleware("http")(auth.authorization_middleware)
    app.include_router(router)
    app.state.research_run_service = fixture.service
    app.state.investigation_service = fixture.retained.service
    try:
        with TestClient(app) as client:
            yield HttpRunFixture(fixture, client, state)
    finally:
        engine.dispose()


def test_submit_discover_execute_backfill_and_terminal_redelivery_use_actual_stack(http):
    fixture = http.fixture
    body = fixture.request()
    accepted = http.post("submit", body)["run"]
    assert http.post("submit", body)["run"] == accepted
    address = fixture.address(accepted)
    assert accepted["activity"] == [] and accepted["event_cursor"] == 0 and accepted["latest_event_cursor"] == 1
    assert http.post("status", address)["run"] == accepted
    conversation = {name: body[name] for name in ("investigation_id", "conversation_id")}
    assert http.post("list", conversation)["items"] == [accepted]
    assert fixture.service.dispatch_outbox() == 1
    completed = fixture.queue.deliver_next(fixture.service)["run"]
    assert completed["status"] == "completed" and completed["result"] is None
    assert completed["context"] == accepted["context"] and completed["synthetic"] is False
    resumed = http.post("status", address)["run"]
    assert resumed == completed and resumed["activity"] == [] and resumed["event_cursor"] == 0
    cursor, events = 0, []
    while True:
        page = http.post("events", {**address, "after_cursor": cursor, "limit": 1})
        events += page["events"]
        assert page["binding"] == accepted["context"]["binding"]
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break
    assert [item["cursor"] for item in events] == list(range(1, cursor + 1))
    assert [item["kind"] for item in events] == ["accepted", "started", "progress", "completed"]
    assert cursor == completed["latest_event_cursor"]
    calls = fixture.state["factory_calls"]
    assert fixture.service.execute_delivery(**fixture.delivery(accepted))["run"] == completed
    assert fixture.state["factory_calls"] == calls
    assert http.post("cancel", {**address, "idempotency_key": key()})["run"] == completed
    with fixture.retained.factory() as session:
        assert len(session.scalars(select(ResearchRun)).all()) == 1
        assert len(session.scalars(select(ResearchRunOutbox)).all()) == 1
        assert len(session.scalars(select(ResearchRunEvent)).all()) == cursor


def test_queued_cancel_and_explicit_linked_continuation_preserve_parent(http):
    fixture = http.fixture
    accepted = http.post("submit", fixture.request())["run"]
    address = fixture.address(accepted)
    cancel_request = {**address, "idempotency_key": key()}
    cancelled = http.post("cancel", cancel_request)["run"]
    assert cancelled["status"] == "cancelled"
    assert http.post("cancel", cancel_request)["run"] == cancelled
    continuation = {**address, "idempotency_key": key()}
    child = http.post("continue", continuation)["run"]
    assert child["id"] != accepted["id"] and child["continuation_of"] == accepted["id"]
    assert child["context"] == accepted["context"] and child["active_elapsed_ms"] == 0
    assert http.post("continue", continuation)["run"] == child
    assert http.post("status", address)["run"] == cancelled
    assert fixture.service.execute_delivery(**fixture.delivery(child))["run"]["status"] == "completed"
    conversation = {name: address[name] for name in ("investigation_id", "conversation_id")}
    first = http.post("list", {**conversation, "limit": 1})
    second = http.post("list", {**conversation, "limit": 1, "cursor": first["next_cursor"]})
    assert second["next_cursor"] is None
    assert {first["items"][0]["id"], second["items"][0]["id"]} == {accepted["id"], child["id"]}


def test_clarification_preserves_original_input_and_rejects_stale_answer(http):
    fixture = http.fixture
    accepted = http.post("submit", fixture.request("Help me understand this"))["run"]
    address = fixture.address(accepted)
    waiting = fixture.service.execute_delivery(**fixture.delivery(accepted))["run"]
    assert waiting["status"] == "awaiting_clarification" and waiting["clarification_id"]
    before = waiting["active_elapsed_ms"]
    fixture.clock.advance(48 * 3600)
    assert http.post("status", address)["run"]["active_elapsed_ms"] == before
    answer = {**address, "idempotency_key": key(), "clarification_id": waiting["clarification_id"], "answer": "Count all datasets"}
    resumed = http.post("clarify", answer)["run"]
    assert resumed["status"] == "queued" and resumed["question"] == accepted["question"]
    assert resumed["context"] == accepted["context"]
    assert http.post("clarify", answer)["run"] == resumed
    http.post("clarify", {**answer, "idempotency_key": key()}, 409)
    http.post("clarify", {**answer, "answer": "Changed question"}, 409)
    completed = fixture.service.execute_delivery(**fixture.delivery(accepted))["run"]
    assert completed["status"] == "completed" and completed["question"] == accepted["question"]
    with fixture.retained.factory() as session:
        inputs = session.scalars(select(ResearchRunInputHistory).where(ResearchRunInputHistory.run_id == uuid.UUID(accepted["id"])).order_by(ResearchRunInputHistory.sequence)).all()
        assert [item.kind for item in inputs] == ["submit", "clarify"]
        assert [item.effective_question for item in inputs] == [accepted["question"], answer["answer"]]


@pytest.mark.parametrize("actor", ["other", "admin"])
def test_actual_run_history_is_owner_private_even_to_administrator(http, actor):
    fixture = http.fixture
    accepted = http.post("submit", fixture.request())["run"]
    address = fixture.address(accepted)
    http.state["principal"] = getattr(fixture.retained, actor)
    for name, body in (
        ("status", address), ("events", {**address, "after_cursor": 0}),
        ("cancel", {**address, "idempotency_key": key()}),
        ("list", {key: address[key] for key in ("investigation_id", "conversation_id")}),
    ):
        result = http.post(name, body, 404)
        assert accepted["question"] not in str(result)


@pytest.mark.parametrize("field,value", [("role", "viewer"), ("status", "suspended"), ("account_type", "commercial")])
def test_live_db_revocation_overrules_stale_authenticated_request(http, field, value):
    fixture = http.fixture
    accepted = http.post("submit", fixture.request())["run"]
    with fixture.retained.factory.begin() as session:
        setattr(session.get(AppUser, fixture.user.id), field, value)
    http.post("status", fixture.address(accepted), 403)


def test_new_context_head_does_not_rebind_an_existing_run(http):
    fixture = http.fixture
    body = fixture.request()
    accepted = http.post("submit", body)["run"]
    reference = {"kind": "catalogue", "id": fixture.retained.dataset_ids["ctd"], "snapshot_id": body["expected_snapshot_id"]}
    changed = fixture.retained.service.invoke("context/change", {
        "investigation_id": body["investigation_id"], "expected_revision_id": body["revision_id"],
        "idempotency_key": key(), "change": {"op": "pin", "reference": reference},
    }, fixture.user)
    assert changed["context"]["id"] != body["revision_id"]
    assert http.post("status", fixture.address(accepted))["run"]["context"] == accepted["context"]
    assert fixture.service.execute_delivery(**fixture.delivery(accepted))["run"]["context"] == accepted["context"]


@pytest.mark.parametrize("field", ["expected_snapshot_id", "expected_payload_sha256"])
def test_stale_expected_binding_fails_before_creating_durable_work(http, field):
    body = http.fixture.request()
    http.post("submit", {**body, field: "f" * 64}, 409)
    with http.fixture.retained.factory() as session:
        assert session.scalar(select(ResearchRun)) is None
        assert session.scalar(select(ResearchRunOutbox)) is None


def test_dispatch_disabled_keeps_actual_cancel_history_and_events(http, monkeypatch):
    accepted = http.post("submit", http.fixture.request())["run"]
    address = http.fixture.address(accepted)
    monkeypatch.setenv("ENABLE_V1_RESEARCH_DISPATCH", "false")
    monkeypatch.setenv("ENABLE_V1_RESEARCH_CONTROLLER", "false")
    assert http.post("status", address)["run"] == accepted
    assert http.post("events", {**address, "after_cursor": 0})["events"][0]["kind"] == "accepted"
    assert http.post("cancel", {**address, "idempotency_key": key()})["run"]["status"] == "cancelled"
    http.post("continue", {**address, "idempotency_key": key()}, 503)
