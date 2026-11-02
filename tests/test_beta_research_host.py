"""Actual C17 composition over canonical synthetic sealed sources and SQL.

SQLite fixtures prove application composition/persistence semantics only. Live
PostgreSQL grants and actual GCS conditional writes remain separate deployment
acceptance gates.
"""
import uuid

import pytest
from sqlalchemy import select, update

from api.auth import current_user_from_model
from api.v1_beta_research_host import (
    CONTEXT_MUTATION_PATHS, CONTEXT_TABLE_PRIVILEGES, CONTEXT_UPDATE_COLUMNS,
    SITE_ID, compose_beta_context_services,
)
from api.v1_host import HostConfigurationError
from db.app_models import AppUser, ResearchContextOperation, ResearchInvestigation
from ingestion.beta_catalogue_retention import BetaCatalogueRetentionStore
from ingestion.catalogue_snapshot import SnapshotCommitUncertain
from orchestration.investigations import InvestigationError
from tests.test_beta_snapshot_catalogue import PREPARE, load
from tests.test_beta_snapshot_catalogue import sealed as sealed
from tests.test_v1_host import independent as independent


@pytest.fixture
def context(sealed, independent, monkeypatch):
    from ingestion import gcs_catalogue_snapshot
    monkeypatch.setattr(gcs_catalogue_snapshot, "GcsCatalogueSnapshotStore", BetaCatalogueRetentionStore)
    catalogue, browser = load(sealed)
    _, factory = independent
    with factory.begin() as session:
        model = session.scalar(select(AppUser))
        model.role = "admin"
        session.flush()
        actor = current_user_from_model(model)
    before = catalogue.resolver.store.lifecycle()
    services = compose_beta_context_services(session_factory=factory, site_id=SITE_ID,
        catalogue_service=catalogue, catalogue_browser=browser)
    assert catalogue.resolver.store.lifecycle() == before
    return services, actor, factory, sealed


def create(context, **changes):
    services, actor, _, sealed = context
    return services.investigation_service.invoke("create", {
        "name": "Saved beta context", "snapshot_id": sealed[2]["index_id"],
        "scope": PREPARE.scope().model_dump(mode="json"),
        "idempotency_key": str(uuid.uuid4()), **changes}, actor)


def test_durable_c17_create_context_and_conversation_survive_recomposition(context):
    services, actor, factory, sealed = context
    created = create(context)
    identity = created["investigation"]["id"]
    conversation = services.investigation_service.invoke("conversations/create", {
        "investigation_id": identity, "name": "Saved conversation", "idempotency_key": str(uuid.uuid4())}, actor)
    attachment = {"kind": "catalogue", "snapshot_id": sealed[2]["index_id"],
        "id": sealed[2]["dataset"].dataset_id}
    attached = services.investigation_service.invoke("context/change", {
        "investigation_id": identity, "expected_revision_id": created["context"]["id"],
        "idempotency_key": str(uuid.uuid4()), "change": {"op": "attach", "reference": attachment}}, actor)
    reopened = compose_beta_context_services(session_factory=factory, site_id=SITE_ID,
        catalogue_service=services.catalogue_service, catalogue_browser=services.catalogue_browser)
    result = reopened.investigation_service.invoke("get", {"investigation_id": identity}, actor)
    assert result["context"]["attachments"] == [attachment]
    assert result["context"]["id"] == attached["context"]["id"]
    old = reopened.investigation_service.invoke("context/get", {
        "investigation_id": identity, "revision_id": created["context"]["id"]}, actor)
    assert old["context"]["attachments"] == []
    chats = reopened.investigation_service.invoke("conversations/list", {"investigation_id": identity}, actor)
    assert [item["id"] for item in chats["items"]] == [conversation["conversation"]["id"]]
    lifecycle = services.catalogue_service.resolver.store.lifecycle()
    assert len([r for r in lifecycle["references"] if r.startswith("c17:dependency:")]) == 2
    assert not reopened.research_run_service and not reopened.research_evidence_service
    assert not reopened.research_answer_service and not reopened.research_experiment_service
    assert not reopened.experiment_workspace_service


def test_same_context_key_is_idempotent_without_duplicate_references(context):
    key = str(uuid.uuid4())
    first = create(context, idempotency_key=key)
    second = create(context, idempotency_key=key)
    assert first["context"]["id"] == second["context"]["id"]
    refs = context[0].catalogue_service.resolver.store.lifecycle()["references"]
    assert len([r for r in refs if r.startswith("c17:dependency:")]) == 2


def test_partial_uncertain_reference_preserves_preparation_then_recovers(context, monkeypatch):
    services, actor, factory, _ = context
    store = services.catalogue_service.resolver.store
    original = store.add_reference
    calls = []
    def fail_second(identity, reference):
        calls.append(reference)
        if len(calls) == 2:
            state = store.lifecycle()
            raise SnapshotCommitUncertain(action="reference", details={"snapshot_id": identity,
                "reference": reference}, proposed_revision=state["revision"] + 1,
                proposed_latest_generation=state["latest_generation"])
        return original(identity, reference)
    monkeypatch.setattr(store, "add_reference", fail_second)
    with pytest.raises(InvestigationError) as error:
        create(context)
    assert error.value.code == "operation_pending"
    with factory() as session:
        operation = session.scalar(select(ResearchContextOperation))
        op_id, revision_id = operation.id, operation.candidate_revision_id
        assert operation.state == "uncertain"
        assert session.get(ResearchInvestigation, operation.investigation_id).head_revision_id is None
    assert calls[0] in store.lifecycle()["references"]
    monkeypatch.setattr(store, "add_reference", original)
    retried = services.investigation_service.invoke("operations/retry", {"operation_id": str(op_id)}, actor)
    assert retried["context"]["id"] == str(revision_id)
    assert len([r for r in store.lifecycle()["references"] if r.startswith("c17:dependency:")]) == 2


def test_current_database_revocation_denies_saved_context(context):
    services, actor, factory, _ = context
    saved = create(context)
    with factory.begin() as session:
        session.execute(update(AppUser).where(AppUser.id == actor.id).values(status="suspended"))
    with pytest.raises(InvestigationError) as error:
        services.investigation_service.invoke("get", {"investigation_id": saved["investigation"]["id"]}, actor)
    assert error.value.status_code == 403


def test_artifact_attachment_stays_unavailable_without_real_artifact_authority(context):
    services, actor, _, sealed = context
    saved = create(context)
    with pytest.raises(InvestigationError) as error:
        services.investigation_service.invoke("context/change", {
            "investigation_id": saved["investigation"]["id"], "expected_revision_id": saved["context"]["id"],
            "idempotency_key": str(uuid.uuid4()), "change": {"op": "attach", "reference": {
                "kind": "artifact", "id": "synthetic:artifact", "snapshot_id": sealed[2]["index_id"]}}}, actor)
    assert error.value.status_code == 503


def test_withdrawn_registry_cannot_be_composed(context):
    services, _, factory, sealed = context
    sealed[3]["store"].revoke(sealed[2]["child_id"])
    with pytest.raises(HostConfigurationError, match="Explicit durable"):
        compose_beta_context_services(session_factory=factory, site_id=SITE_ID,
            catalogue_service=services.catalogue_service, catalogue_browser=services.catalogue_browser)


def test_readonly_store_cannot_masquerade_as_durable_context(sealed, independent):
    catalogue, browser = load(sealed)
    with pytest.raises(HostConfigurationError, match="Explicit durable"):
        compose_beta_context_services(session_factory=independent[1], site_id=SITE_ID,
            catalogue_service=catalogue, catalogue_browser=browser)


def test_foreign_site_and_mismatched_browser_fail_closed(context):
    services, _, factory, _ = context
    for site, browser in (("v1:data-infra-infobio", services.catalogue_browser), (SITE_ID, None)):
        with pytest.raises(HostConfigurationError, match="Explicit durable"):
            compose_beta_context_services(session_factory=factory, site_id=site,
                catalogue_service=services.catalogue_service, catalogue_browser=browser)


def test_grants_and_request_surface_are_only_the_owned_c17_context_mutations():
    assert all(path.startswith("/research/investigations/") for path in CONTEXT_MUTATION_PATHS)
    assert not any("retire" in path or "hold" in path or "submit" in path for path in CONTEXT_MUTATION_PATHS)
    assert set(CONTEXT_TABLE_PRIVILEGES) == {"research_investigation", "research_conversation",
        "research_context_revision", "research_context_operation", "audit_event"}
    assert all(not rights.intersection({"UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"})
        for rights in CONTEXT_TABLE_PRIVILEGES.values())
    assert not {"audit_event", "research_context_revision"}.intersection(CONTEXT_UPDATE_COLUMNS)
    from db.app_models import AppBase
    for table, columns in CONTEXT_UPDATE_COLUMNS.items():
        assert columns <= set(AppBase.metadata.tables[table].columns.keys())
