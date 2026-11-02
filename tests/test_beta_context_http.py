"""Actual ASGI context mutations and closed execution in the explicit beta mode."""
import uuid

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest
from sqlalchemy import select, update

from api import v1_catalogue_host, v1_host
from api.auth import current_user_from_model
from api.v1_beta_research_host import SITE_ID
from db.app_models import AppUser, ResearchContextOperation, ResearchInvestigation
from ingestion.artifact_store import BoundedLocalStore
from ingestion.beta_catalogue_retention import BetaCatalogueRetentionStore
from ingestion.catalogue_snapshot import SnapshotCommitUncertain
from tests.test_beta_snapshot_catalogue import PREPARE, load
from tests.test_beta_snapshot_catalogue import sealed as sealed
from tests.test_v1_host import SECRET, headers, settings
from tests.test_v1_host import independent as independent


@pytest.fixture
def live(sealed, independent, monkeypatch):
    _, factory = independent
    with factory.begin() as session:
        row = session.scalar(select(AppUser))
        row.role = "admin"
        session.flush()
        actor = current_user_from_model(row)
    original = v1_catalogue_host.load_snapshot_catalogue
    monkeypatch.setattr(v1_catalogue_host, "load_snapshot_catalogue", lambda *a, **kw:
        original(*a, **kw, _allow_test_owner=True, _test_store=BoundedLocalStore(sealed[1] / "store")))
    host = settings(project_id=PREPARE.PROJECT, site_id=SITE_ID)
    services = v1_host.catalogue_services_from_environment(host, SecretStr(SECRET), {
        "OCEAN_V1_CATALOGUE_MODE": "sealed-gcs-context-v1", "OCEAN_V1_CATALOGUE_CONFIG": str(sealed[0])},
        session_factory=factory)
    application = v1_host.create_host_app(settings=host, session_factory=factory,
        internal_secret=SecretStr(SECRET), services=services, context_mutations=True, _allow_test_sqlite=True)
    with TestClient(application, base_url="http://127.0.0.1:8000") as client:
        yield {"client": client, "services": services, "host": host,
            "factory": factory, "actor": actor, "sealed": sealed}


def key():
    return str(uuid.uuid4())


def post(live, operation, data, **kwargs):
    return live["client"].post("/research/investigations/" + operation,
        json=data, headers=headers(), **kwargs)


def create(live, **changes):
    return post(live, "create", {"name": "Actual ASGI beta context", "snapshot_id": live["sealed"][2]["index_id"],
        "scope": PREPARE.scope().model_dump(mode="json"), "idempotency_key": key(), **changes})


def test_http_context_create_list_get_conversation_attach_rename_and_archive(live):
    response = create(live)
    assert response.status_code == 200, response.text
    created = response.json()
    identity = created["investigation"]["id"]
    listed = post(live, "list", {})
    assert listed.status_code == 200 and [r["id"] for r in listed.json()["items"]] == [identity]
    current = post(live, "get", {"investigation_id": identity})
    assert current.status_code == 200 and current.json()["context"]["id"] == created["context"]["id"]
    conversation = post(live, "conversations/create", {"investigation_id": identity,
        "name": "Saved chat", "idempotency_key": key()})
    assert conversation.status_code == 200
    chat = conversation.json()["conversation"]
    renamed_chat = post(live, "conversations/rename", {"investigation_id": identity,
        "conversation_id": chat["id"], "expected_version": chat["metadata_version"],
        "name": "Renamed chat", "idempotency_key": key()})
    assert renamed_chat.status_code == 200
    assert post(live, "conversations/list", {"investigation_id": identity}).json()["items"][0]["name"] == "Renamed chat"
    ref = {"kind": "catalogue", "id": live["sealed"][2]["dataset"].dataset_id,
        "snapshot_id": live["sealed"][2]["index_id"]}
    attached = post(live, "context/change", {"investigation_id": identity,
        "expected_revision_id": created["context"]["id"], "idempotency_key": key(),
        "change": {"op": "attach", "reference": ref}})
    assert attached.status_code == 200 and attached.json()["context"]["attachments"] == [ref]
    historical = post(live, "context/get", {"investigation_id": identity, "revision_id": created["context"]["id"]})
    assert historical.status_code == 200 and historical.json()["context"]["attachments"] == []
    renamed = post(live, "rename", {"investigation_id": identity, "name": "Saved renamed context",
        "expected_version": attached.json()["investigation"]["metadata_version"], "idempotency_key": key()})
    assert renamed.status_code == 200 and renamed.json()["investigation"]["name"] == "Saved renamed context"
    archived = post(live, "archive", {"investigation_id": identity, "archived": True,
        "expected_version": renamed.json()["investigation"]["metadata_version"], "idempotency_key": key()})
    assert archived.status_code == 200 and archived.json()["investigation"]["status"] == "archived"
    assert post(live, "get", {"investigation_id": identity}).status_code == 200
    assert post(live, "conversations/create", {"investigation_id": identity,
        "name": "Cannot mutate archived", "idempotency_key": key()}).status_code == 409
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert isinstance(live["services"].investigation_service.store, BetaCatalogueRetentionStore)
    runtime = live["client"].get("/v1/runtime", headers=headers()).json()
    assert runtime["capabilities"]["research"]["status"] == "ready"
    assert runtime["research_runs"]["submit_enabled"] is False
    assert runtime["research_runs"]["dispatch_enabled"] is False


def test_http_uncertain_partial_references_are_retried_without_duplicate_context(live, monkeypatch):
    store = live["services"].investigation_service.store
    original = store.add_reference
    calls = []
    def uncertain(identity, reference):
        calls.append(reference)
        if len(calls) == 2:
            state = store.lifecycle()
            raise SnapshotCommitUncertain(action="reference", details={"snapshot_id": identity, "reference": reference},
                proposed_revision=state["revision"] + 1, proposed_latest_generation=state["latest_generation"])
        return original(identity, reference)
    monkeypatch.setattr(store, "add_reference", uncertain)
    response = create(live)
    assert response.status_code == 503 and response.json()["error"]["code"] == "operation_pending"
    with live["factory"]() as session:
        operation = session.scalar(select(ResearchContextOperation))
        identity, candidate = operation.id, operation.candidate_revision_id
        assert operation.state == "uncertain"
    monkeypatch.setattr(store, "add_reference", original)
    retried = post(live, "operations/retry", {"operation_id": str(identity)})
    assert retried.status_code == 200 and retried.json()["context"]["id"] == str(candidate)
    assert post(live, "operations/get", {"operation_id": str(identity)}).json()["operation"]["state"] == "committed"
    assert len([r for r in store.lifecycle()["references"] if r.startswith("c17:")]) == 2


def test_context_route_requires_explicit_host_mutation_mode(live):
    application = v1_host.create_host_app(settings=live["host"], session_factory=live["factory"],
        internal_secret=SecretStr(SECRET), services=live["services"], context_mutations=False,
        _allow_test_sqlite=True)
    with TestClient(application, base_url="http://127.0.0.1:8000") as client:
        response = client.post("/research/investigations/create", json={}, headers=headers())
        assert response.status_code == 403 and response.json()["error"]["code"] == "readonly_stage"
    with live["factory"]() as session:
        assert session.scalar(select(ResearchInvestigation)) is None


def test_investigation_flag_alone_cannot_supply_durable_service(sealed, independent, monkeypatch):
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "true")
    catalogue, browser = load(sealed)
    services = v1_host.V1ReadServices(catalogue_service=catalogue, catalogue_browser=browser)
    with pytest.raises(v1_host.HostConfigurationError):
        v1_host.create_host_app(settings=settings(project_id=PREPARE.PROJECT, site_id=SITE_ID),
            session_factory=independent[1], internal_secret=SecretStr(SECRET), services=services,
            context_mutations=True, _allow_test_sqlite=True)


def test_feature_flag_off_denies_context_even_with_valid_composition(live, monkeypatch):
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "false")
    response = create(live)
    assert response.status_code == 503 and response.json()["error"]["code"] == "investigations_disabled"
    with live["factory"]() as session:
        assert session.scalar(select(ResearchInvestigation)) is None


@pytest.mark.parametrize("change", [{"status": "suspended"}, {"role": "viewer"}])
def test_current_database_owner_revocation_closes_http_mutations_and_reads(live, change):
    response = create(live)
    assert response.status_code == 200
    with live["factory"].begin() as session:
        session.execute(update(AppUser).where(AppUser.id == live["actor"].id).values(**change))
    assert create(live).status_code == 403
    assert post(live, "get", {"investigation_id": response.json()["investigation"]["id"]}).status_code == 403


def test_authentication_wrong_host_query_and_ambiguous_json_have_no_context_effect(live, monkeypatch):
    client = live["client"]
    monkeypatch.setenv("AUTH_MODE", "disabled")
    assert client.post("/research/investigations/create", json={}).status_code == 401
    assert client.post("/research/investigations/create", json={},
        headers={"Authorization": "Bearer forged"}).status_code == 401
    assert client.post("/research/investigations/create", json={},
        headers={**headers(), "Host": "oceaninfobio.com"}).status_code == 421
    assert client.post("/research/investigations/create?target=legacy", json={},
        headers=headers()).status_code == 422
    assert client.post("/research/investigations/create", content='{"name":"a","name":"b"}',
        headers={**headers(), "Content-Type": "application/json"}).status_code == 422
    with live["factory"]() as session:
        assert session.scalar(select(ResearchInvestigation)) is None


@pytest.mark.parametrize("path", ["/research/runs/submit", "/research/runs/clarify", "/research/runs/continue",
    "/research/answers/submit", "/research/experiments/create", "/research/experiments/approve",
    "/research/experiments/dispatch", "/research/experiments/retry", "/research/investigations/retire",
    "/research/investigations/hold", "/admin", "/chat"])
def test_only_c17_context_mutations_are_admitted_never_model_or_dispatch(live, path):
    response = live["client"].post(path, json={}, headers=headers())
    assert response.status_code == 403 and response.json()["error"]["code"] == "readonly_stage"


@pytest.mark.parametrize("flag", v1_host.EXECUTION_FLAGS)
def test_execution_flag_cannot_be_enabled_after_startup(live, monkeypatch, flag):
    monkeypatch.setenv(flag, "true")
    response = create(live)
    assert response.status_code == 503 and response.json()["error"]["code"] == "host_configuration_unavailable"
    with live["factory"]() as session:
        assert session.scalar(select(ResearchInvestigation)) is None


def test_host_context_selection_is_a_strict_boolean(live):
    with pytest.raises(v1_host.HostConfigurationError, match="Explicit context mutation"):
        v1_host.create_host_app(settings=live["host"], session_factory=live["factory"],
            internal_secret=SecretStr(SECRET), services=live["services"], context_mutations="true",
            _allow_test_sqlite=True)
