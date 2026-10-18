"""C17 actual authenticated HTTP over isolated application and frozen stores.

The TEST principal is injected at the authentication boundary. Everything after
that boundary is the actual router, service, application session and sealed
C09/C10-C13 catalogue; these tests make no real OIDC or PostgreSQL claim.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select, update

from api import auth
from api.investigation_routes import router
from db.app_models import AppBase, AppUser, ResearchContextOperation, ResearchContextRevision
from retrieval.source_scope import EvidenceScope
from tests.investigation_support import make_investigation_fixture

PREFIX = "/research/investigations/"


def key():
    return str(uuid.uuid4())


@pytest.fixture(scope="session")
def actual_http_ledger():
    ledger = []
    yield ledger
    print("C17_ACTUAL_HTTP_COUNTS=" + json.dumps({
        "requests": len(ledger),
        "routes": dict(sorted(Counter(name for name, _ in ledger).items())),
        "statuses": dict(sorted(Counter(status for _, status in ledger).items())),
    }, sort_keys=True))


@dataclass
class HttpFixture:
    retained: object
    client: object
    state: dict
    ledger: list

    def post(self, name, body, status=200):
        response = self.client.post(PREFIX + name, json=body)
        self.ledger.append((name, response.status_code))
        assert response.status_code == status, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        result = response.json()
        if status == 200:
            assert result["version"] == "investigations-v1"
        return result

    def create(self, **changes):
        return self.post("create", {
            "name": "Synthetic private research 調査", "snapshot_id": self.retained.snapshots[0],
            "scope": self.retained.scope, "idempotency_key": key(), **changes,
        })

    def reference(self, family="ctd"):
        return {"kind": "catalogue", "id": self.retained.dataset_ids[family], "snapshot_id": self.retained.snapshots[0]}

    def change(self, previous, change, **overrides):
        return {
            "investigation_id": previous["investigation"]["id"],
            "expected_revision_id": previous["context"]["id"],
            "idempotency_key": key(), "change": change, **overrides,
        }


@pytest.fixture
def http(tmp_path, monkeypatch, actual_http_ledger):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("ENABLE_MOCK_LOGIN", "false")
    monkeypatch.setenv("PERSIST_LOCAL_CHAT", "false")
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "true")
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused:unused@127.0.0.1:1/c17_http_unused")
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:1")
    engine = create_engine("sqlite+pysqlite:///" + str(tmp_path / "separate-v1-http.sqlite"))

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    AppBase.metadata.create_all(engine)
    retained = make_investigation_fixture(engine, tmp_path)
    state = {"principal": retained.user}

    def current(_request):
        if state["principal"] is None:
            raise auth.AuthenticationFailure(401, "Authentication is required")
        return state["principal"]

    monkeypatch.setattr(auth, "authenticate_request", current)
    app = FastAPI()
    app.middleware("http")(auth.authorization_middleware)
    app.include_router(router)
    app.state.investigation_service = retained.service
    try:
        with TestClient(app) as client:
            yield HttpFixture(retained, client, state, actual_http_ledger)
    finally:
        engine.dispose()


def test_complete_http_metadata_conversation_context_refresh_and_recovery_contract(http):
    initial = http.create()
    identity, initial_revision = initial["investigation"]["id"], initial["context"]["id"]
    owner = {"investigation_id": identity}
    assert http.post("list", {})["items"] == [initial["investigation"]]
    resumed = http.post("get", owner)
    assert resumed["context"] == initial["context"] and resumed["legacy_history_import"] == "unavailable"

    first_request = {**owner, "name": "Conversation one", "idempotency_key": key()}
    first = http.post("conversations/create", first_request)
    second = http.post("conversations/create", {**first_request, "name": "Conversation two", "idempotency_key": key()})
    assert first["conversation"]["id"] != second["conversation"]["id"]
    assert http.post("conversations/create", first_request)["conversation"] == first["conversation"]
    page1 = http.post("conversations/list", {**owner, "limit": 1})
    page2 = http.post("conversations/list", {**owner, "limit": 1, "after_id": page1["next_after_id"]})
    assert page2["next_after_id"] is None
    assert {page1["items"][0]["id"], page2["items"][0]["id"]} == {first["conversation"]["id"], second["conversation"]["id"]}
    conversation = {**owner, "conversation_id": first["conversation"]["id"]}
    assert http.post("conversations/get", conversation)["conversation"]["history_status"] == "unavailable_until_c20_c21"
    renamed_conversation = http.post("conversations/rename", {
        **conversation, "expected_version": first["conversation"]["metadata_version"],
        "name": "Renamed conversation", "idempotency_key": key(),
    })
    assert http.post("conversations/get", conversation)["conversation"] == renamed_conversation["conversation"]

    reference = http.reference()
    attached_request = http.change(initial, {"op": "attach", "reference": reference})
    attached = http.post("context/change", attached_request)
    assert attached["context"]["attachments"] == [reference] and attached["context"]["pins"] == []
    assert attached["context"]["scope"] == initial["context"]["scope"]
    assert http.post("context/change", attached_request)["context"] == attached["context"]
    pinned = http.post("context/change", http.change(attached, {"op": "pin", "reference": reference}))
    assert pinned["context"]["attachments"] == pinned["context"]["pins"] == [reference]
    selected_scope = json.loads(json.dumps(http.retained.scope))
    selected_scope["sources"]["metagenome"]["enabled"] = False
    scoped = http.post("context/change", http.change(pinned, {"op": "scope", "scope": selected_scope}))
    assert scoped["context"]["scope"] == EvidenceScope.model_validate(selected_scope).canonical()
    assert scoped["context"]["pins"] == scoped["context"]["attachments"] == [reference]
    historical = http.post("context/get", {**owner, "revision_id": initial_revision})
    assert historical["context"] == initial["context"]
    assert http.post("context/get", owner)["context"] == scoped["context"]

    refreshed = http.post("refresh", {
        **owner, "expected_revision_id": scoped["context"]["id"],
        "target_snapshot_id": http.retained.snapshots[1], "name": "Explicit refreshed branch", "idempotency_key": key(),
    })
    branch = refreshed["investigation"]
    assert branch["id"] != identity and branch["predecessor_investigation_id"] == identity
    assert branch["predecessor_revision_id"] == scoped["context"]["id"]
    assert refreshed["context"]["snapshot_id"] == http.retained.snapshots[1]
    assert refreshed["context"]["attachments"][0]["snapshot_id"] == http.retained.snapshots[1]
    assert http.post("get", owner)["context"] == scoped["context"]
    assert http.post("operations/get", {"operation_id": refreshed["operation"]["id"]})["operation"]["state"] == "committed"
    assert http.post("operations/retry", {"operation_id": refreshed["operation"]["id"]})["context"] == refreshed["context"]

    metadata = http.post("get", owner)["investigation"]
    renamed = http.post("rename", {**owner, "expected_version": metadata["metadata_version"], "name": "Retained original", "idempotency_key": key()})
    archived = http.post("archive", {**owner, "expected_version": renamed["investigation"]["metadata_version"], "idempotency_key": key()})
    assert archived["investigation"]["status"] == "archived"
    assert http.post("get", owner)["context"] == scoped["context"]
    restored = http.post("archive", {
        **owner, "archived": False, "expected_version": archived["investigation"]["metadata_version"], "idempotency_key": key(),
    })
    assert restored["investigation"]["status"] == "active"
    assert restored["investigation"]["name"] == "Retained original"
    page1 = http.post("list", {"limit": 1})
    page2 = http.post("list", {"limit": 1, "after_id": page1["next_after_id"]})
    assert page2["next_after_id"] is None
    assert {page1["items"][0]["id"], page2["items"][0]["id"]} == {identity, branch["id"]}


@pytest.mark.parametrize("actor", ["other", "admin"])
def test_cross_owner_read_write_operation_and_conversation_access_remain_absent(http, actor):
    initial = http.create()
    owner = {"investigation_id": initial["investigation"]["id"]}
    conversation = http.post("conversations/create", {**owner, "name": "Owner-only conversation", "idempotency_key": key()})
    conversation_ids = {**owner, "conversation_id": conversation["conversation"]["id"]}
    http.state["principal"] = getattr(http.retained, actor)
    assert http.post("list", {})["items"] == []
    requests = {
        "get": owner,
        "context/get": {**owner, "revision_id": initial["context"]["id"]},
        "context/change": http.change(initial, {"op": "attach", "reference": http.reference()}),
        "rename": {**owner, "name": "Forbidden rename", "expected_version": 1, "idempotency_key": key()},
        "archive": {**owner, "expected_version": 1, "idempotency_key": key()},
        "conversations/create": {**owner, "name": "Forbidden conversation", "idempotency_key": key()},
        "conversations/list": owner,
        "conversations/get": conversation_ids,
        "conversations/rename": {**conversation_ids, "name": "Forbidden rename", "expected_version": 1, "idempotency_key": key()},
        "refresh": {**owner, "expected_revision_id": initial["context"]["id"], "target_snapshot_id": http.retained.snapshots[1], "name": "Forbidden branch", "idempotency_key": key()},
        "operations/get": {"operation_id": initial["operation"]["id"]},
        "operations/retry": {"operation_id": initial["operation"]["id"]},
    }
    for name, body in requests.items():
        assert http.post(name, body, 404)["error"]["code"] == "not_found"
    assert http.post("get", {"investigation_id": key()}, 404)["error"]["code"] == "not_found"
    http.state["principal"] = http.retained.user
    assert http.post("get", owner)["context"] == initial["context"]
    assert http.post("conversations/get", conversation_ids)["conversation"] == conversation["conversation"]


@pytest.mark.parametrize("field,value", [("role", "viewer"), ("status", "suspended"), ("account_type", "commercial")])
def test_current_application_db_revocation_rejects_stale_http_principal_and_history(http, field, value):
    initial = http.create()
    owner = {"investigation_id": initial["investigation"]["id"]}
    with http.retained.factory.begin() as session:
        session.execute(update(AppUser).where(AppUser.id == http.retained.user.id).values(**{field: value}))
    # The trusted TEST principal deliberately remains the previous researcher:
    # the actual service must compare fresh application membership on each call.
    assert http.post("get", owner, 403)["error"]["code"] == "forbidden"
    assert http.post("context/get", {**owner, "revision_id": initial["context"]["id"]}, 403)["error"]["code"] == "forbidden"
    assert http.post("rename", {**owner, "name": "Forbidden after revocation", "expected_version": 1, "idempotency_key": key()}, 403)["error"]["code"] == "forbidden"
    assert http.post("operations/retry", {"operation_id": initial["operation"]["id"]}, 403)["error"]["code"] == "forbidden"


def test_http_context_revision_conflict_idempotency_and_wrong_conversation_binding(http):
    initial = http.create()
    request = http.change(initial, {"op": "attach", "reference": http.reference()})
    attached = http.post("context/change", request)
    assert http.post("context/change", request)["context"]["id"] == attached["context"]["id"]
    assert http.post("context/change", {**request, "change": {"op": "pin", "reference": http.reference()}}, 409)["error"]["code"] == "conflict"
    assert http.post("context/change", http.change(initial, {"op": "attach", "reference": http.reference("metagenome")}), 409)["error"]["code"] == "conflict"
    second = http.create(name="Another independent investigation")
    conversation = http.post("conversations/create", {"investigation_id": second["investigation"]["id"], "name": "Separate", "idempotency_key": key()})
    assert http.post("conversations/get", {"investigation_id": initial["investigation"]["id"], "conversation_id": conversation["conversation"]["id"]}, 404)["error"]["code"] == "not_found"
    assert http.post("context/get", {"investigation_id": initial["investigation"]["id"], "revision_id": second["context"]["id"]}, 404)["error"]["code"] == "not_found"


def test_http_source_withdrawal_and_refresh_unresolved_preserve_original_hash(http):
    initial = http.create()
    attached = http.post("context/change", http.change(initial, {"op": "attach", "reference": http.reference()}))
    http.retained.policy[http.retained.snapshots[1]].add(http.retained.source_dataset_ids["ctd"])
    branch = http.post("refresh", {
        "investigation_id": initial["investigation"]["id"], "expected_revision_id": attached["context"]["id"],
        "target_snapshot_id": http.retained.snapshots[1], "name": "Explicit unresolved branch", "idempotency_key": key(),
    })
    assert branch["context"]["refresh_unresolved"] and branch["context"]["resolution"][0]["status"] == "unavailable"
    before = http.post("context/get", {"investigation_id": initial["investigation"]["id"], "revision_id": attached["context"]["id"]})
    assert before["context"]["resolution"][0]["status"] == "available"
    http.retained.policy[http.retained.snapshots[0]].add(http.retained.source_dataset_ids["ctd"])
    withdrawn = http.post("context/get", {"investigation_id": initial["investigation"]["id"], "revision_id": attached["context"]["id"]})
    assert withdrawn["context"]["resolution"][0]["status"] == "unavailable"
    assert withdrawn["context"]["payload_sha256"] == before["context"]["payload_sha256"]
    assert "title" not in json.dumps(withdrawn)
    with http.retained.factory() as session:
        saved = session.get(ResearchContextRevision, uuid.UUID(attached["context"]["id"]))
        assert saved.payload_sha256 == attached["context"]["payload_sha256"]


def test_http_pending_reference_write_has_explicit_operation_and_retry_recovery(http, monkeypatch):
    original = http.retained.store.add_reference
    attempts = []

    def failed(snapshot_id, reference):
        if reference.startswith("c17:"):
            attempts.append(reference)
            if len(attempts) == 2:
                raise OSError("synthetic private storage failure")
        return original(snapshot_id, reference)

    monkeypatch.setattr(http.retained.store, "add_reference", failed)
    error = http.post("create", {
        "name": "Recover this exact operation", "snapshot_id": http.retained.snapshots[0],
        "scope": http.retained.scope, "idempotency_key": key(),
    }, 503)
    assert error["error"]["code"] == "operation_pending" and "private" not in json.dumps(error)
    with http.retained.factory() as session:
        operation = session.scalar(select(ResearchContextOperation))
        identity, revision = str(operation.id), str(operation.candidate_revision_id)
    assert identity in error["error"]["message"]
    assert http.post("operations/get", {"operation_id": identity})["operation"]["state"] == "unavailable"
    monkeypatch.setattr(http.retained.store, "add_reference", original)
    recovered = http.post("operations/retry", {"operation_id": identity})
    assert recovered["context"]["id"] == revision and recovered["operation"]["state"] == "committed"
    assert http.post("get", {"investigation_id": recovered["investigation"]["id"]})["context"] == recovered["context"]


@pytest.mark.parametrize("malformation", ["owner", "reference_label", "mixed_scope_pin", "snapshot", "revision"])
def test_malformed_real_http_requests_leave_committed_context_unchanged(http, malformation):
    initial = http.create()
    request = http.change(initial, {"op": "attach", "reference": http.reference()})
    if malformation == "owner":
        request["owner_id"] = str(http.retained.admin.id)
    elif malformation == "reference_label":
        request["change"]["reference"]["label"] = "Never trust this submitted label"
    elif malformation == "mixed_scope_pin":
        request["change"] = {"op": "pin", "reference": http.reference(), "scope": http.retained.scope}
    elif malformation == "snapshot":
        request["change"]["reference"]["snapshot_id"] = "not-a-sha256"
    else:
        request["expected_revision_id"] = True
    assert http.post("context/change", request, 422)["error"]["code"] == "invalid_request"
    assert http.post("get", {"investigation_id": initial["investigation"]["id"]})["context"] == initial["context"]
