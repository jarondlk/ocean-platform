"""C17 actual frozen-service context, recovery and ownership acceptance."""
from datetime import datetime, timedelta, timezone
import json
import uuid

import pytest
from sqlalchemy import create_engine, event, select, update

from db.app_models import AppBase, AppUser, AuditEvent, ResearchContextOperation, ResearchContextRevision, ResearchInvestigation
from orchestration.investigations import InvestigationError, RetainedArtifactBinding
from tests.investigation_support import make_investigation_fixture


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "true")
    engine = create_engine("sqlite+pysqlite:///" + str(tmp_path / "v1.sqlite"))

    @event.listens_for(engine, "connect")
    def keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    AppBase.metadata.create_all(engine)
    result = make_investigation_fixture(engine, tmp_path)
    yield result
    engine.dispose()


def key():
    return str(uuid.uuid4())


def create(fixture, *, user=None, **changes):
    data = {"name": "Independent investigation", "snapshot_id": fixture.snapshots[0], "scope": fixture.scope, "idempotency_key": key(), **changes}
    return fixture.service.invoke("create", data, user or fixture.user)


def change(fixture, created, op, reference=None, **extra):
    modification = {"op": op, **extra}
    if reference is not None:
        modification["reference"] = reference
    return {"investigation_id": created["investigation"]["id"], "expected_revision_id": created["context"]["id"], "idempotency_key": key(), "change": modification}


def reference(fixture, family="ctd"):
    return {"kind": "catalogue", "id": fixture.dataset_ids[family], "snapshot_id": fixture.snapshots[0]}


def invoke(fixture, name, data, user=None):
    return fixture.service.invoke(name, data, user or fixture.user)


def test_create_distinct_conversations_reload_and_recover_idempotent_reply(fixture):
    created = create(fixture)
    identity = created["investigation"]["id"]
    data = {"investigation_id": identity, "name": "First conversation", "idempotency_key": key()}
    first = invoke(fixture, "conversations/create", data)
    second = invoke(fixture, "conversations/create", {**data, "name": "Second", "idempotency_key": key()})
    assert first["conversation"]["id"] != second["conversation"]["id"]
    assert invoke(fixture, "conversations/create", data)["conversation"] == first["conversation"]
    # New application sessions reopen real persisted records, with no transcript lookup.
    listed = invoke(fixture, "conversations/list", {"investigation_id": identity})
    assert {item["id"] for item in listed["items"]} == {first["conversation"]["id"], second["conversation"]["id"]}
    assert all(item["history_status"] == "unavailable_until_c20_c21" for item in listed["items"])
    assert invoke(fixture, "get", {"investigation_id": identity})["legacy_history_import"] == "unavailable"


def test_attachments_and_pins_are_distinct_scope_unchanged_and_revisions_retained(fixture):
    initial = create(fixture)
    attached = invoke(fixture, "context/change", change(fixture, initial, "attach", reference(fixture)))
    assert attached["context"]["scope"] == initial["context"]["scope"]
    assert attached["context"]["attachments"] == [reference(fixture)] and attached["context"]["pins"] == []
    pinned = invoke(fixture, "context/change", change(fixture, attached, "pin", reference(fixture)))
    detached = invoke(fixture, "context/change", change(fixture, pinned, "detach", reference(fixture)))
    assert detached["context"]["attachments"] == [] and detached["context"]["pins"] == [reference(fixture)]
    old = invoke(fixture, "context/get", {"investigation_id": initial["investigation"]["id"], "revision_id": attached["context"]["id"]})
    assert old["context"]["attachments"] == [reference(fixture)]
    assert old["context"]["payload_sha256"] == attached["context"]["payload_sha256"]
    assert initial["context"]["sequence"] == 1 and detached["context"]["sequence"] == 4
    bindings = fixture.store.lifecycle()["references"]
    expected = len(fixture.service._bindings(fixture.snapshots[0], uuid.UUID(initial["investigation"]["id"])))
    assert len([name for name in bindings if name.startswith("c17:")]) == expected


@pytest.mark.parametrize("other", ["other", "admin"])
@pytest.mark.parametrize("name", ["get", "context/get", "conversations/list"])
def test_cross_owner_absence_is_identical_including_admin(fixture, other, name):
    created = create(fixture)
    actor = getattr(fixture, other)
    for identity in (created["investigation"]["id"], key()):
        with pytest.raises(InvestigationError) as error:
            invoke(fixture, name, {"investigation_id": identity}, actor)
        assert (error.value.status_code, error.value.code) == (404, "not_found")


def test_same_key_different_request_and_stale_context_cannot_overwrite(fixture):
    initial = create(fixture)
    data = change(fixture, initial, "attach", reference(fixture))
    first = invoke(fixture, "context/change", data)
    assert invoke(fixture, "context/change", data)["context"]["id"] == first["context"]["id"]
    with pytest.raises(InvestigationError, match="changed"):
        invoke(fixture, "context/change", {**data, "change": {"op": "pin", "reference": reference(fixture)}})
    with pytest.raises(InvestigationError) as error:
        invoke(fixture, "context/change", change(fixture, initial, "attach", reference(fixture, "metagenome")))
    assert error.value.status_code == 409
    assert invoke(fixture, "get", {"investigation_id": initial["investigation"]["id"]})["context"]["id"] == first["context"]["id"]


@pytest.mark.parametrize("mutation", ["role", "status", "account_type"])
def test_current_db_revocation_rejects_stale_principal_and_historical_access(fixture, mutation):
    initial = create(fixture)
    with fixture.factory.begin() as session:
        session.execute(update(AppUser).where(AppUser.id == fixture.user.id).values(**{mutation: {"role": "viewer", "status": "suspended", "account_type": "commercial"}[mutation]}))
    with pytest.raises(InvestigationError) as error:
        invoke(fixture, "context/get", {"investigation_id": initial["investigation"]["id"], "revision_id": initial["context"]["id"]})
    assert error.value.status_code == 403


def test_historical_reference_withdrawal_preserves_ids_but_no_protected_labels(fixture):
    initial = create(fixture)
    attached = invoke(fixture, "context/change", change(fixture, initial, "attach", reference(fixture)))
    fixture.policy[fixture.snapshots[0]].add(fixture.source_dataset_ids["ctd"])
    result = invoke(fixture, "context/get", {"investigation_id": initial["investigation"]["id"], "revision_id": attached["context"]["id"]})
    assert result["context"]["resolution"][0]["status"] == "unavailable"
    assert "title" not in json.dumps(result)
    with fixture.factory() as session:
        saved = session.get(ResearchContextRevision, uuid.UUID(attached["context"]["id"]))
        assert saved.payload_sha256 == attached["context"]["payload_sha256"]


def test_partial_reference_failure_keeps_prepared_operation_and_retry_recovers(fixture, monkeypatch):
    original = fixture.store.add_reference
    completed = []

    def fail_second(snapshot_id, name):
        if name.startswith("c17:"):
            completed.append(name)
            if len(completed) == 2:
                raise OSError("synthetic storage failure secret should not escape")
        return original(snapshot_id, name)

    monkeypatch.setattr(fixture.store, "add_reference", fail_second)
    with pytest.raises(InvestigationError) as error:
        create(fixture)
    assert error.value.code == "operation_pending" and "secret" not in str(error.value)
    with fixture.factory() as session:
        operation = session.scalar(select(ResearchContextOperation))
        identity, candidate = operation.id, operation.candidate_revision_id
        assert operation.state == "unavailable"
        assert session.get(ResearchInvestigation, operation.investigation_id).head_revision_id is None
    assert completed[0] in fixture.store.lifecycle()["references"]
    monkeypatch.setattr(fixture.store, "add_reference", original)
    recovered = invoke(fixture, "operations/retry", {"operation_id": str(identity)})
    assert recovered["context"]["id"] == str(candidate)
    assert fixture.service.reconcile(operation_id=identity, user=fixture.user)["reference_release"] == "unavailable_conservative_retention"


def test_two_prepared_heads_activate_exactly_one_and_retain_loser_refs(fixture):
    initial = create(fixture)
    one = fixture.service._prepare("context/change", change(fixture, initial, "attach", reference(fixture)), fixture.user)
    two = fixture.service._prepare("context/change", change(fixture, initial, "pin", reference(fixture)), fixture.user)
    result = fixture.service._apply(one, fixture.user)
    with pytest.raises(InvestigationError) as error:
        fixture.service._apply(two, fixture.user)
    assert error.value.status_code == 409
    assert invoke(fixture, "get", {"investigation_id": initial["investigation"]["id"]})["context"]["id"] == result["context"]["id"]
    assert invoke(fixture, "operations/get", {"operation_id": str(two)})["operation"]["state"] == "conflict"


def test_archive_between_prepare_and_activate_rejects_context_commit(fixture):
    initial = create(fixture)
    pending = fixture.service._prepare("context/change", change(fixture, initial, "attach", reference(fixture)), fixture.user)
    invoke(fixture, "archive", {"investigation_id": initial["investigation"]["id"], "expected_version": initial["investigation"]["metadata_version"], "idempotency_key": key()})
    with pytest.raises(InvestigationError) as error:
        fixture.service._apply(pending, fixture.user)
    assert error.value.status_code == 409
    assert invoke(fixture, "get", {"investigation_id": initial["investigation"]["id"]})["context"]["id"] == initial["context"]["id"]


@pytest.mark.parametrize("literal", ["false", "0", "off"])
def test_parsed_default_off_gate_also_protects_trusted_helpers(fixture, monkeypatch, literal):
    initial = create(fixture)
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", literal)
    with pytest.raises(InvestigationError) as error:
        invoke(fixture, "list", {})
    assert error.value.status_code == 503
    with pytest.raises(InvestigationError):
        fixture.service.reconcile(operation_id=initial["operation"]["id"], user=fixture.user)


def test_artifacts_need_trusted_current_resolver_and_preserve_hash(fixture):
    initial = create(fixture)
    ref = {"kind": "artifact", "id": "synthetic:retained:result", "snapshot_id": fixture.snapshots[0]}
    with pytest.raises(InvestigationError) as error:
        invoke(fixture, "context/change", change(fixture, initial, "attach", ref))
    assert error.value.status_code == 503
    fixture.service.artifact_resolver = lambda user, reference: RetainedArtifactBinding(ref["id"], ref["snapshot_id"], "a" * 64, user.id)
    attached = invoke(fixture, "context/change", change(fixture, initial, "attach", ref))
    fixture.service.artifact_resolver = lambda user, reference: RetainedArtifactBinding(ref["id"], ref["snapshot_id"], "b" * 64, user.id)
    with pytest.raises(InvestigationError) as error:
        invoke(fixture, "context/get", {"investigation_id": attached["investigation"]["id"]})
    assert error.value.status_code == 503


def test_submission_freezes_explicit_revision_while_conversations_share_only_context(fixture):
    initial = create(fixture)
    conversation = invoke(fixture, "conversations/create", {"investigation_id": initial["investigation"]["id"], "name": "A chat", "idempotency_key": key()})
    attached = invoke(fixture, "context/change", change(fixture, initial, "attach", reference(fixture)))
    frozen = fixture.service.load_for_submission(investigation_id=initial["investigation"]["id"], conversation_id=conversation["conversation"]["id"], revision_id=initial["context"]["id"], user=fixture.user)
    assert frozen["revision_id"] == initial["context"]["id"] and frozen["context"]["attachments"] == []
    assert attached["context"]["attachments"]


def test_owner_admin_hold_and_logical_retirement_preserve_rows_and_refs(fixture):
    initial = create(fixture, user=fixture.admin)
    identity = initial["investigation"]["id"]
    invoke(fixture, "archive", {"investigation_id": identity, "expected_version": initial["investigation"]["metadata_version"], "idempotency_key": key()}, fixture.admin)
    fixture.service.set_hold(investigation_id=identity, held=True, user=fixture.admin)
    future = datetime.now(timezone.utc) + timedelta(days=100)
    assert fixture.service.retire_expired(retention_days=30, user=fixture.admin, now=future, dry_run=False)["retired_count"] == 0
    fixture.service.set_hold(investigation_id=identity, held=False, user=fixture.admin)
    refs = dict(fixture.store.lifecycle()["references"])
    report = fixture.service.retire_expired(retention_days=30, user=fixture.admin, now=future)
    assert report["eligible_count"] == 1 and report["retired_count"] == 0
    report = fixture.service.retire_expired(retention_days=30, user=fixture.admin, now=future, dry_run=False)
    assert report["retired_count"] == 1 and report["physical_deleted_count"] == report["released_reference_count"] == 0
    assert fixture.store.lifecycle()["references"] == refs
    with fixture.factory() as session:
        assert session.get(ResearchInvestigation, uuid.UUID(identity)).status == "retired"
        assert session.scalar(select(ResearchContextRevision)) is not None
        assert session.scalar(select(AuditEvent).where(AuditEvent.action == "research.investigation_retired")) is not None


def test_refresh_preserves_predecessor_and_exposes_unresolved_selection_before_submission(fixture):
    initial = create(fixture)
    attached = invoke(fixture, "context/change", change(fixture, initial, "pin", reference(fixture)))
    fixture.policy[fixture.snapshots[1]].add(fixture.source_dataset_ids["ctd"])
    refreshed = invoke(fixture, "refresh", {
        "investigation_id": initial["investigation"]["id"], "expected_revision_id": attached["context"]["id"],
        "target_snapshot_id": fixture.snapshots[1], "name": "Refreshed branch", "idempotency_key": key(),
    })
    assert refreshed["investigation"]["id"] != initial["investigation"]["id"]
    assert refreshed["investigation"]["predecessor_revision_id"] == attached["context"]["id"]
    assert refreshed["context"]["refresh_unresolved"][0]["status"] == "unavailable"
    conversation = invoke(fixture, "conversations/create", {"investigation_id": refreshed["investigation"]["id"], "name": "New narrative", "idempotency_key": key()})
    with pytest.raises(InvestigationError) as error:
        fixture.service.load_for_submission(investigation_id=refreshed["investigation"]["id"], conversation_id=conversation["conversation"]["id"], revision_id=refreshed["context"]["id"], user=fixture.user)
    assert error.value.code == "unresolved_context"
    original = invoke(fixture, "context/get", {"investigation_id": initial["investigation"]["id"], "revision_id": attached["context"]["id"]})
    assert original["context"]["snapshot_id"] == fixture.snapshots[0]
    assert original["context"]["payload_sha256"] == attached["context"]["payload_sha256"]
    assert invoke(fixture, "conversations/list", {"investigation_id": initial["investigation"]["id"]})["items"] == []


def test_metadata_only_operator_holds_researcher_records_without_private_read(fixture):
    initial = create(fixture)
    identity = initial["investigation"]["id"]
    fixture.service.set_hold(investigation_id=identity, held=True, user=fixture.admin)
    with fixture.factory() as session:
        assert session.get(ResearchInvestigation, uuid.UUID(identity)).legal_hold is True
    with pytest.raises(InvestigationError) as error:
        invoke(fixture, "get", {"investigation_id": identity}, fixture.admin)
    assert error.value.status_code == 404
    with pytest.raises(InvestigationError):
        fixture.service.set_hold(investigation_id=identity, held=False, user=fixture.user)


def test_archived_conversation_cannot_change_and_parent_hold_protects_branch(fixture):
    initial = create(fixture)
    conversation = invoke(fixture, "conversations/create", {"investigation_id": initial["investigation"]["id"], "name": "Separate", "idempotency_key": key()})
    current = invoke(fixture, "get", {"investigation_id": initial["investigation"]["id"]})
    invoke(fixture, "archive", {"investigation_id": initial["investigation"]["id"], "expected_version": current["investigation"]["metadata_version"], "idempotency_key": key()})
    with pytest.raises(InvestigationError) as error:
        invoke(fixture, "conversations/rename", {"investigation_id": initial["investigation"]["id"], "conversation_id": conversation["conversation"]["id"], "name": "Changed", "expected_version": 1, "idempotency_key": key()})
    assert error.value.status_code == 409
    branch = invoke(fixture, "refresh", {"investigation_id": initial["investigation"]["id"], "expected_revision_id": initial["context"]["id"], "target_snapshot_id": fixture.snapshots[1], "name": "Branch", "idempotency_key": key()})
    invoke(fixture, "archive", {"investigation_id": branch["investigation"]["id"], "expected_version": branch["investigation"]["metadata_version"], "idempotency_key": key()})
    fixture.service.set_hold(investigation_id=initial["investigation"]["id"], held=True, user=fixture.admin)
    report = fixture.service.retire_expired(retention_days=30, user=fixture.admin, now=datetime.now(timezone.utc) + timedelta(days=100), dry_run=False)
    assert report["eligible_count"] == report["retired_count"] == 0


@pytest.mark.parametrize("ambiguous", [False, True])
def test_database_commit_failure_never_releases_refs_and_exact_retry_recovers(fixture, ambiguous):
    from sqlalchemy.exc import SQLAlchemyError

    flag = {"activation": False, "fired": False}

    def before_flush(session, _flush_context, _instances):
        if any(isinstance(row, ResearchContextRevision) for row in session.new):
            session.info["c17_activation"] = True

    def before_commit(session):
        activation = session.info.get("c17_activation", False)
        flag["activation"] = activation
        if activation and not ambiguous and not flag["fired"]:
            flag["fired"] = True
            raise SQLAlchemyError("synthetic confirmed failure")

    def after_commit(session):
        if ambiguous and flag["activation"] and not flag["fired"]:
            flag["fired"] = True
            raise SQLAlchemyError("synthetic lost commit acknowledgement")

    event.listen(fixture.factory, "before_flush", before_flush)
    event.listen(fixture.factory, "before_commit", before_commit)
    event.listen(fixture.factory, "after_commit", after_commit)
    data = {"name": "Interrupted", "snapshot_id": fixture.snapshots[0], "scope": fixture.scope, "idempotency_key": key()}
    try:
        with pytest.raises(InvestigationError) as error:
            invoke(fixture, "create", data)
        assert error.value.code == "operation_pending"
    finally:
        event.remove(fixture.factory, "before_flush", before_flush)
        event.remove(fixture.factory, "before_commit", before_commit)
        event.remove(fixture.factory, "after_commit", after_commit)
    refs = {name: value for name, value in fixture.store.lifecycle()["references"].items() if name.startswith("c17:")}
    assert refs
    recovered = invoke(fixture, "create", data)
    assert recovered["operation"]["state"] == "committed" and recovered["context"]["sequence"] == 1
    assert {name: value for name, value in fixture.store.lifecycle()["references"].items() if name.startswith("c17:")} == refs
    with fixture.factory() as session:
        assert len(list(session.scalars(select(ResearchContextRevision)))) == 1
        assert len(list(session.scalars(select(AuditEvent).where(AuditEvent.action == "research.context_committed")))) == 1


@pytest.mark.parametrize("field,value", [("payload_sha256", "0" * 64), ("snapshot_id", "1" * 64)])
def test_committed_retry_verifies_same_revision_integrity_as_historical_reads(fixture, field, value):
    request = {"name": "Integrity binding", "snapshot_id": fixture.snapshots[0], "scope": fixture.scope, "idempotency_key": key()}
    created = invoke(fixture, "create", request)
    # SQLite has fixture ORM guards only; direct SQL models external corruption.
    # Actual PostgreSQL rejects these writes in the independently tested triggers.
    with fixture.factory.begin() as session:
        session.execute(update(ResearchContextRevision).where(ResearchContextRevision.id == uuid.UUID(created["context"]["id"])).values(**{field: value}))
    for name, data in [("create", request), ("operations/retry", {"operation_id": created["operation"]["id"]}), ("context/get", {"investigation_id": created["investigation"]["id"]})]:
        with pytest.raises(InvestigationError) as error:
            invoke(fixture, name, data)
        assert error.value.status_code == 503
