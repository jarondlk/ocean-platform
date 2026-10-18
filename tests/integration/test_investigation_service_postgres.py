"""C17 real service transactions and lock ordering on the guarded v1 test DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import threading
import uuid

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError

from db.app_models import AppUser, AuditEvent, ResearchContextOperation, ResearchContextRevision, ResearchInvestigation
from orchestration.investigations import InvestigationError
from tests.investigation_support import make_investigation_fixture
from tests.integration import test_investigation_postgres as pg_support

disposable_database = pg_support.disposable_database
isolated = pg_support.isolated


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires explicitly verified disposable C17 PostgreSQL",
)


@pytest.fixture
def service_fixture(isolated, tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "true")
    pg_support.alembic(isolated, "upgrade", "head")
    return make_investigation_fixture(isolated["engine"], tmp_path)


def _key():
    return str(uuid.uuid4())


def _create(fixture):
    return fixture.service.invoke("create", {
        "name": "PostgreSQL private investigation", "snapshot_id": fixture.snapshots[0],
        "scope": fixture.scope, "idempotency_key": _key(),
    }, fixture.user)


def _change(fixture, initial, op):
    return {"investigation_id": initial["investigation"]["id"], "expected_revision_id": initial["context"]["id"],
            "idempotency_key": _key(), "change": {"op": op, "reference": {
                "kind": "catalogue", "id": fixture.dataset_ids["ctd"], "snapshot_id": fixture.snapshots[0],
            }}}


def _archive(fixture, initial):
    return fixture.service.invoke("archive", {
        "investigation_id": initial["investigation"]["id"],
        "expected_version": initial["investigation"]["metadata_version"], "idempotency_key": _key(),
    }, fixture.user)


def test_service_concurrent_prepared_revisions_have_one_actual_postgres_cas_winner(service_fixture):
    fixture = service_fixture
    initial = _create(fixture)
    operations = [fixture.service._prepare("context/change", _change(fixture, initial, op), fixture.user) for op in ("attach", "pin")]
    barrier = threading.Barrier(2)

    def activate(identity):
        barrier.wait(timeout=5)
        try:
            return (200, fixture.service._apply(identity, fixture.user))
        except InvestigationError as error:
            return (error.status_code, error.code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(activate, identity) for identity in operations]
        outcomes = [future.result(timeout=15) for future in futures]
    assert sorted(status for status, _ in outcomes) == [200, 409]
    with fixture.factory() as session:
        rows = list(session.scalars(select(ResearchContextRevision).order_by(ResearchContextRevision.sequence)))
        assert [row.sequence for row in rows] == [1, 2]
        assert sorted(session.scalars(select(ResearchContextOperation.state).where(ResearchContextOperation.id.in_(operations)))) == ["committed", "conflict"]
        assert session.get(ResearchInvestigation, uuid.UUID(initial["investigation"]["id"])).head_revision_id == rows[-1].id


@pytest.mark.parametrize("first", ["hold", "retire"])
def test_service_real_hold_and_retirement_transaction_ordering(service_fixture, monkeypatch, first):
    fixture = service_fixture
    initial = _create(fixture)
    _archive(fixture, initial)
    locked, release = threading.Event(), threading.Event()
    original = fixture.service._retention_lock

    def intercept(session):
        original(session)
        if threading.current_thread().name.startswith("c17-first"):
            locked.set()
            assert release.wait(5)

    monkeypatch.setattr(fixture.service, "_retention_lock", intercept)
    future_time = datetime.now(timezone.utc) + timedelta(days=100)

    def hold():
        try:
            fixture.service.set_hold(investigation_id=initial["investigation"]["id"], held=True, user=fixture.admin)
            return "held"
        except InvestigationError as error:
            return error.code

    def retire():
        return fixture.service.retire_expired(retention_days=30, user=fixture.admin, now=future_time, dry_run=False)

    actions = {"hold": hold, "retire": retire}
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="c17-first") as earlier, ThreadPoolExecutor(max_workers=1, thread_name_prefix="c17-later") as later:
        one = earlier.submit(actions[first])
        try:
            assert locked.wait(5)
            two = later.submit(actions["retire" if first == "hold" else "hold"])
            # The second transaction has to wait on the service advisory lock.
            assert not two.done()
        finally:
            release.set()
        first_result, second_result = one.result(timeout=10), two.result(timeout=10)
    if first == "hold":
        assert first_result == "held" and second_result["retired_count"] == 0
    else:
        assert first_result["retired_count"] == 1 and second_result == "not_found"
    with fixture.factory() as session:
        item = session.get(ResearchInvestigation, uuid.UUID(initial["investigation"]["id"]))
        assert (item.status, item.legal_hold) == (("archived", True) if first == "hold" else ("retired", False))
        assert session.get(ResearchContextRevision, uuid.UUID(initial["context"]["id"])) is not None


@pytest.mark.parametrize("ambiguous", [False, True])
def test_service_actual_database_commit_failure_and_uncertain_ack_reconcile(service_fixture, ambiguous):
    fixture = service_fixture
    state = {"activation": False, "fired": False}

    def before_flush(session, _flush_context, _instances):
        if any(isinstance(row, ResearchContextRevision) for row in session.new):
            session.info["c17_activation"] = True

    def before_commit(session):
        state["activation"] = session.info.get("c17_activation", False)
        if state["activation"] and not ambiguous and not state["fired"]:
            state["fired"] = True
            raise SQLAlchemyError("synthetic rollback before commit")

    def after_commit(session):
        if state["activation"] and ambiguous and not state["fired"]:
            state["fired"] = True
            raise SQLAlchemyError("synthetic acknowledgement lost after actual COMMIT")

    event.listen(fixture.factory, "before_flush", before_flush)
    event.listen(fixture.factory, "before_commit", before_commit)
    event.listen(fixture.factory, "after_commit", after_commit)
    request = {"name": "Recover exact committed identity", "snapshot_id": fixture.snapshots[0], "scope": fixture.scope, "idempotency_key": _key()}
    try:
        with pytest.raises(InvestigationError) as error:
            fixture.service.invoke("create", request, fixture.user)
        assert error.value.code == "operation_pending" and state["fired"]
    finally:
        event.remove(fixture.factory, "before_flush", before_flush)
        event.remove(fixture.factory, "before_commit", before_commit)
        event.remove(fixture.factory, "after_commit", after_commit)
    protected = {name: identity for name, identity in fixture.store.lifecycle()["references"].items() if name.startswith("c17:")}
    assert protected
    with fixture.factory() as session:
        before = list(session.scalars(select(ResearchContextRevision)))
        assert len(before) == int(ambiguous)
    recovered = fixture.service.invoke("create", request, fixture.user)
    assert recovered["operation"]["state"] == "committed"
    with fixture.factory() as session:
        revisions = list(session.scalars(select(ResearchContextRevision)))
        assert len(revisions) == 1 and str(revisions[0].id) == recovered["context"]["id"]
        assert len(list(session.scalars(select(AuditEvent).where(AuditEvent.action == "research.context_committed")))) == 1
    assert {name: identity for name, identity in fixture.store.lifecycle()["references"].items() if name.startswith("c17:")} == protected


def test_service_partial_reference_write_and_capacity_failure_do_not_publish_head(service_fixture, monkeypatch):
    fixture = service_fixture
    original = fixture.store.add_reference
    names = []

    def bounded(snapshot_id, reference):
        if reference.startswith("c17:"):
            names.append(reference)
            if len(names) == 2:
                raise ValueError("synthetic bounded ledger capacity reached")
        return original(snapshot_id, reference)

    monkeypatch.setattr(fixture.store, "add_reference", bounded)
    with pytest.raises(InvestigationError) as error:
        _create(fixture)
    assert error.value.code == "operation_pending"
    with fixture.factory() as session:
        operation = session.scalar(select(ResearchContextOperation))
        identity = operation.id
        assert operation.state == "unavailable"
        assert session.get(ResearchInvestigation, operation.investigation_id).head_revision_id is None
        assert session.scalar(select(ResearchContextRevision)) is None
    assert names[0] in fixture.store.lifecycle()["references"]
    monkeypatch.setattr(fixture.store, "add_reference", original)
    assert fixture.service.invoke("operations/retry", {"operation_id": str(identity)}, fixture.user)["operation"]["state"] == "committed"


def test_service_withdrawn_child_between_prepare_and_apply_preserves_pending_evidence(service_fixture):
    fixture = service_fixture
    request = {"name": "Withdrawal race", "snapshot_id": fixture.snapshots[0], "scope": fixture.scope, "idempotency_key": _key()}
    identity = fixture.service._prepare("create", request, fixture.user)
    child = fixture.registrations[fixture.snapshots[0]].child_snapshot_ids[0]
    fixture.store.revoke(child)
    with pytest.raises(InvestigationError):
        fixture.service.invoke("operations/retry", {"operation_id": str(identity)}, fixture.user)
    with fixture.factory() as session:
        operation = session.get(ResearchContextOperation, identity)
        assert operation.state == "prepared" and session.get(ResearchInvestigation, operation.investigation_id).head_revision_id is None
    assert fixture.store.lifecycle()["snapshots"][child]["revoked"] is True


@pytest.mark.parametrize("column,value", [("role", "viewer"), ("status", "suspended"), ("account_type", "commercial")])
def test_service_postgres_current_principal_revocation_governs_historical_access(service_fixture, column, value):
    fixture = service_fixture
    initial = _create(fixture)
    with fixture.factory.begin() as session:
        setattr(session.get(AppUser, fixture.user.id), column, value)
    with pytest.raises(InvestigationError) as error:
        fixture.service.invoke("context/get", {"investigation_id": initial["investigation"]["id"], "revision_id": initial["context"]["id"]}, fixture.user)
    assert error.value.status_code == 403


def test_service_refresh_branch_preserves_original_bytes_and_reports_unresolved_pin(service_fixture):
    fixture = service_fixture
    initial = _create(fixture)
    pinned = fixture.service.invoke("context/change", _change(fixture, initial, "pin"), fixture.user)
    with fixture.factory() as session:
        original = session.get(ResearchContextRevision, uuid.UUID(pinned["context"]["id"])).payload_json
    fixture.policy[fixture.snapshots[1]].add(fixture.source_dataset_ids["ctd"])
    branch = fixture.service.invoke("refresh", {"investigation_id": initial["investigation"]["id"],
        "expected_revision_id": pinned["context"]["id"], "target_snapshot_id": fixture.snapshots[1],
        "name": "Explicit new branch", "idempotency_key": _key()}, fixture.user)
    assert branch["context"]["resolution"][0]["status"] == "unavailable"
    assert branch["investigation"]["predecessor_revision_id"] == pinned["context"]["id"]
    with fixture.factory() as session:
        assert session.get(ResearchContextRevision, uuid.UUID(pinned["context"]["id"])).payload_json == original
        assert len(list(session.scalars(select(ResearchInvestigation)))) == 2
