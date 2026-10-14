from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api import retention_routes
from api.auth import CurrentUser, get_current_user
from api.schemas import RetentionHoldRequest
from db import retention
from db.app_models import AppBase, AppUser, AuditEvent, ChatFeedback, ChatInteraction


def _session_context(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def context():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return context


def test_cleanup_is_dry_run_by_default_and_respects_holds(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AppBase.metadata.create_all(engine)
    monkeypatch.setattr(retention, "get_session", _session_context(engine))
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)

    with factory.begin() as session:
        user = AppUser(
            auth_provider="test",
            auth_subject="user-1",
            email="retention@example.test",
            role="admin",
            account_type="research",
        )
        session.add(user)
        session.flush()
        old = ChatInteraction(
            user_id=user.id,
            status="completed",
            query="old",
            created_at=now - timedelta(days=100),
        )
        held = ChatInteraction(
            user_id=user.id,
            status="completed",
            query="held",
            legal_hold=True,
            created_at=now - timedelta(days=100),
        )
        running = ChatInteraction(
            user_id=user.id,
            status="running",
            query="running",
            created_at=now - timedelta(days=100),
        )
        recent = ChatInteraction(
            user_id=user.id,
            status="completed",
            query="recent",
            created_at=now - timedelta(days=2),
        )
        session.add_all([old, held, running, recent])
        session.flush()
        session.add(
            ChatFeedback(
                interaction_id=old.id,
                user_id=user.id,
                rating=1,
            )
        )

    report = retention.cleanup_chat_interactions(
        retention_days=90,
        dry_run=True,
        now=now,
    )
    assert report.eligible_count == 1
    assert report.deleted_count == 0

    with factory() as session:
        assert session.scalar(select(ChatInteraction.query).where(ChatInteraction.query == "old")) == "old"

    report = retention.cleanup_chat_interactions(
        retention_days=90,
        dry_run=False,
        now=now,
    )
    assert report.eligible_count == 1
    assert report.deleted_count == 1

    with factory() as session:
        queries = set(session.scalars(select(ChatInteraction.query)).all())
        assert "old" not in queries
        assert {"held", "running", "recent"}.issubset(queries)
        assert session.scalar(select(ChatFeedback.id)) is None
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "retention.chat_interactions_deleted")
        )
        assert event is not None
        assert event.metadata_json["deleted_count"] == 1


@pytest.fixture(params=[False, True], ids=["sqlite-fk-disabled", "sqlite-fk-enabled"])
def retention_database(tmp_path, monkeypatch, request):
    """Every fixture has a private SQLite file and two independent connections."""
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'retention.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    if request.param:
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    AppBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    context = _session_context(engine)
    monkeypatch.setattr(retention, "get_session", context)
    monkeypatch.setattr(retention_routes, "get_session", context)
    with factory.begin() as session:
        user = AppUser(
            auth_provider="test",
            auth_subject="retention-fixture",
            email="retention-fixture@example.test",
            role="admin",
            account_type="research",
        )
        session.add(user)
        session.flush()
        user_id = user.id
    yield engine, factory, user_id, datetime(2026, 10, 14, tzinfo=timezone.utc)
    engine.dispose()


def _interaction(factory, user_id, now, *, status="completed", age=100, hold=False):
    with factory.begin() as session:
        interaction = ChatInteraction(
            user_id=user_id,
            status=status,
            query="synthetic retention fixture",
            legal_hold=hold,
            created_at=now - timedelta(days=age),
            evidence_snapshot={"receipt": "synthetic-preserved-evidence"},
        )
        session.add(interaction)
        session.flush()
        session.add(ChatFeedback(interaction_id=interaction.id, user_id=user_id, rating=1))
        return interaction.id


def _current_user(user_id):
    return CurrentUser(
        id=user_id,
        email="retention-fixture@example.test",
        display_name=None,
        role="admin",
        account_type="research",
        status="active",
        permissions=frozenset({"retention:manage"}),
        auth_provider="test",
    )


@pytest.mark.parametrize(
    "change",
    [{"legal_hold": True}, {"status": "running"}, {"created_at": "at_cutoff"}],
    ids=["hold-committed-first", "no-longer-terminal", "no-longer-expired"],
)
def test_cleanup_rechecks_complete_predicate_after_observation(retention_database, change):
    engine, factory, user_id, now = retention_database
    protected_id = _interaction(factory, user_id, now)
    deleted_id = _interaction(factory, user_id, now, status="failed")
    changes = dict(change)
    if changes.get("created_at") == "at_cutoff":
        changes["created_at"] = now - timedelta(days=90)
    barrier_seen = False

    def commit_change_before_delete(connection, cursor, statement, parameters, context, executemany):
        nonlocal barrier_seen
        if barrier_seen or not statement.lstrip().upper().startswith("DELETE "):
            return
        barrier_seen = True
        with factory.begin() as peer:
            peer.execute(update(ChatInteraction).where(ChatInteraction.id == protected_id).values(**changes))

    event.listen(engine, "before_cursor_execute", commit_change_before_delete)
    try:
        report = retention.cleanup_chat_interactions(retention_days=90, dry_run=False, now=now)
    finally:
        event.remove(engine, "before_cursor_execute", commit_change_before_delete)

    assert barrier_seen, "The committed peer update must precede destructive SQL."
    assert report.eligible_count == 2  # An observation, not a reserved deletion count.
    assert report.deleted_count == 1
    with factory() as session:
        protected = session.get(ChatInteraction, protected_id)
        assert protected is not None
        assert protected.evidence_snapshot == {"receipt": "synthetic-preserved-evidence"}
        assert session.get(ChatInteraction, deleted_id) is None
        assert session.scalar(select(ChatFeedback.interaction_id)) == protected_id
        audits = session.scalars(select(AuditEvent)).all()
        assert len(audits) == 1
        assert audits[0].metadata_json["deleted_count"] == 1


def test_hold_committed_after_dry_run_protects_execution(retention_database):
    _, factory, user_id, now = retention_database
    interaction_id = _interaction(factory, user_id, now)
    preview = retention.cleanup_chat_interactions(retention_days=90, now=now)
    assert preview.dry_run is True
    assert (preview.eligible_count, preview.deleted_count) == (1, 0)
    with factory() as session:
        assert session.scalar(select(AuditEvent.id)) is None

    response = retention_routes.set_interaction_legal_hold(
        interaction_id, RetentionHoldRequest(legal_hold=True), _current_user(user_id)
    )
    assert response.interaction_id == interaction_id
    assert response.legal_hold is True
    report = retention.cleanup_chat_interactions(retention_days=90, dry_run=False, now=now)
    assert report.deleted_count == 0
    with factory() as session:
        assert session.get(ChatInteraction, interaction_id) is not None
        assert session.scalar(select(ChatFeedback.interaction_id)) == interaction_id
        assert session.scalars(select(AuditEvent.action)).all() == ["admin.retention_hold_enabled"]


def test_all_candidates_held_before_delete_yields_no_success_audit(retention_database):
    engine, factory, user_id, now = retention_database
    interaction_id = _interaction(factory, user_id, now)
    barrier_seen = False

    def commit_hold_before_delete(connection, cursor, statement, parameters, context, executemany):
        nonlocal barrier_seen
        if barrier_seen or not statement.lstrip().upper().startswith("DELETE "):
            return
        barrier_seen = True
        retention_routes.set_interaction_legal_hold(
            interaction_id, RetentionHoldRequest(legal_hold=True), _current_user(user_id)
        )

    event.listen(engine, "before_cursor_execute", commit_hold_before_delete)
    try:
        report = retention.cleanup_chat_interactions(retention_days=90, dry_run=False, now=now)
    finally:
        event.remove(engine, "before_cursor_execute", commit_hold_before_delete)
    assert barrier_seen
    assert (report.eligible_count, report.deleted_count) == (1, 0)
    with factory() as session:
        assert session.get(ChatInteraction, interaction_id).legal_hold is True
        assert session.scalar(select(ChatFeedback.interaction_id)) == interaction_id
        assert session.scalars(select(AuditEvent.action)).all() == ["admin.retention_hold_enabled"]


def test_cutoff_terminal_status_and_repeated_execution(retention_database):
    _, factory, user_id, now = retention_database
    expired_completed = _interaction(factory, user_id, now)
    expired_failed = _interaction(factory, user_id, now, status="failed")
    preserved = {
        _interaction(factory, user_id, now, hold=True),
        _interaction(factory, user_id, now, status="running"),
        _interaction(factory, user_id, now, age=90),
        _interaction(factory, user_id, now, age=2),
    }
    first = retention.cleanup_chat_interactions(retention_days=90, dry_run=False, now=now)
    second = retention.cleanup_chat_interactions(retention_days=90, dry_run=False, now=now)
    assert (first.eligible_count, first.deleted_count) == (2, 2)
    assert (second.eligible_count, second.deleted_count) == (0, 0)
    with factory() as session:
        assert set(session.scalars(select(ChatInteraction.id))) == preserved
        assert set(session.scalars(select(ChatFeedback.interaction_id))) == preserved
        assert session.get(ChatInteraction, expired_completed) is None
        assert session.get(ChatInteraction, expired_failed) is None
        assert session.scalar(select(func.count(AuditEvent.id))) == 1


@pytest.mark.parametrize("operation", ["cleanup", "hold"])
@pytest.mark.parametrize("failure_phase", ["audit-insert", "commit"])
def test_failed_transaction_preserves_interaction_feedback_and_audit(
    retention_database, monkeypatch, operation, failure_phase
):
    engine, factory, user_id, now = retention_database
    interaction_id = _interaction(factory, user_id, now)

    def reject_audit(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO AUDIT_EVENT"):
            raise RuntimeError("synthetic audit insert failure")

    @contextmanager
    def fail_commit():
        with factory() as session:
            try:
                yield session
                session.flush()
                raise RuntimeError("synthetic commit failure")
            except Exception:
                session.rollback()
                raise

    if failure_phase == "audit-insert":
        event.listen(engine, "before_cursor_execute", reject_audit)
    else:
        monkeypatch.setattr(retention, "get_session", fail_commit)
        monkeypatch.setattr(retention_routes, "get_session", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="synthetic .* failure"):
            if operation == "cleanup":
                retention.cleanup_chat_interactions(retention_days=90, dry_run=False, now=now)
            else:
                retention_routes.set_interaction_legal_hold(
                    interaction_id, RetentionHoldRequest(legal_hold=True), _current_user(user_id)
                )
    finally:
        if failure_phase == "audit-insert":
            event.remove(engine, "before_cursor_execute", reject_audit)
    with factory() as session:
        interaction = session.get(ChatInteraction, interaction_id)
        assert interaction is not None
        assert interaction.legal_hold is False
        assert interaction.evidence_snapshot == {"receipt": "synthetic-preserved-evidence"}
        assert session.scalar(select(ChatFeedback.interaction_id)) == interaction_id
        assert session.scalar(select(AuditEvent.id)) is None


def test_deletion_committed_before_hold_update_returns_not_found(retention_database):
    engine, factory, user_id, now = retention_database
    interaction_id = _interaction(factory, user_id, now)
    barrier_seen = False

    def delete_before_hold_update(connection, cursor, statement, parameters, context, executemany):
        nonlocal barrier_seen
        if barrier_seen or not statement.lstrip().upper().startswith("UPDATE CHAT_INTERACTION"):
            return
        barrier_seen = True
        # A separate transaction commits deletion before the hold's write begins.
        report = retention.cleanup_chat_interactions(retention_days=90, dry_run=False, now=now)
        assert report.deleted_count == 1

    event.listen(engine, "before_cursor_execute", delete_before_hold_update)
    try:
        with pytest.raises(HTTPException) as error:
            retention_routes.set_interaction_legal_hold(
                interaction_id, RetentionHoldRequest(legal_hold=True), _current_user(user_id)
            )
    finally:
        event.remove(engine, "before_cursor_execute", delete_before_hold_update)
    assert barrier_seen
    assert error.value.status_code == 404
    with factory() as session:
        assert session.get(ChatInteraction, interaction_id) is None
        assert session.scalar(select(ChatFeedback.id)) is None
        assert session.scalars(select(AuditEvent.action)).all() == ["retention.chat_interactions_deleted"]


def test_hold_endpoint_preserves_response_shape_and_missing_record_404(retention_database):
    _, factory, user_id, now = retention_database
    interaction_id = _interaction(factory, user_id, now)
    app = FastAPI()
    app.include_router(retention_routes.router)
    app.dependency_overrides[get_current_user] = lambda: _current_user(user_id)
    with TestClient(app) as client:
        enabled = client.patch(
            f"/admin/retention/interactions/{interaction_id}/hold", json={"legal_hold": True}
        )
        assert enabled.status_code == 200
        assert set(enabled.json()) == {"interaction_id", "legal_hold", "updated_at"}
        assert enabled.json()["interaction_id"] == str(interaction_id)
        assert enabled.json()["legal_hold"] is True
        assert datetime.fromisoformat(enabled.json()["updated_at"]).tzinfo is not None
        disabled = client.patch(
            f"/admin/retention/interactions/{interaction_id}/hold", json={"legal_hold": False}
        )
        assert disabled.status_code == 200
        assert disabled.json()["legal_hold"] is False
        missing = client.patch(
            f"/admin/retention/interactions/{uuid.uuid4()}/hold", json={"legal_hold": True}
        )
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Chat interaction not found"}
    with factory() as session:
        assert session.get(ChatInteraction, interaction_id).legal_hold is False
        assert sorted(session.scalars(select(AuditEvent.action)).all()) == [
            "admin.retention_hold_disabled", "admin.retention_hold_enabled"
        ]


@pytest.mark.parametrize("retention_days", [0, -1])
def test_invalid_retention_days_never_open_database(monkeypatch, retention_days):
    def unexpected_database_access():
        raise AssertionError("Invalid retention must be rejected before database access.")

    monkeypatch.setattr(retention, "get_session", unexpected_database_access)
    with pytest.raises(ValueError, match="at least 1"):
        retention.cleanup_chat_interactions(retention_days=retention_days, dry_run=False)
