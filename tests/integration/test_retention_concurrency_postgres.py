"""C03 retention acceptance using isolated schemas in disposable PostgreSQL.

These tests deliberately never read DATABASE_URL. Opt in with
RUN_POSTGRES_INTEGRATION=1 and a verified loopback C03_TEST_DATABASE_URL whose
database name starts with ocean_c03_. No schema is created before identity checks.
SQL events coordinate transaction order; observed PostgreSQL lock waits establish
the competing operation has actually reached its lock before a barrier is lifted.
"""
from __future__ import annotations

import ipaddress
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from api import retention_routes
from api.auth import CurrentUser
from api.schemas import RetentionHoldRequest
from db import retention
from db.app_models import AppBase, AppUser, AuditEvent, ChatFeedback, ChatInteraction


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires an explicitly verified disposable C03 PostgreSQL database",
)

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)
TABLES = [
    AppUser.__table__, ChatInteraction.__table__,
    ChatFeedback.__table__, AuditEvent.__table__,
]


@pytest.fixture(scope="module")
def disposable_database():
    raw_url = os.environ.get("C03_TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail("C03_TEST_DATABASE_URL is required; DATABASE_URL is never used")
    url = make_url(raw_url)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or not re.fullmatch(r"ocean_c03_[a-z0-9_]+", url.database or "")
    ):
        pytest.fail("C03 URL must identify a dedicated ocean_c03_* loopback PostgreSQL database")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            identity = connection.execute(text(
                "SELECT current_database(), host(inet_server_addr()), "
                "inet_server_port(), current_setting('server_version'), "
                "current_setting('transaction_isolation')"
            )).one()
            assert identity[0] == url.database
            assert identity[1] and ipaddress.ip_address(identity[1]).is_loopback
            assert identity[4] == "read committed"
        print(
            "C03 disposable PostgreSQL identity: "
            f"database={identity[0]} address={identity[1]} port={identity[2]} "
            f"version={identity[3]} isolation={identity[4]}"
        )
        yield engine, url
    finally:
        engine.dispose()


@dataclass
class IsolatedDatabase:
    engine: object
    observer: object
    schema: str
    factory: object
    pids: dict = field(default_factory=dict)
    before_commit: object = None

    @contextmanager
    def session_context(self):
        session = self.factory()
        try:
            self.pids[threading.current_thread().name] = session.scalar(
                text("SELECT pg_backend_pid()")
            )
            yield session
            if self.before_commit:
                self.before_commit(session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def seed(self, *, query="old", status="completed", held=False, age_days=100):
        with self.factory.begin() as session:
            token = uuid.uuid4().hex
            user = AppUser(
                auth_provider="test", auth_subject=token,
                email=f"{token}@example.test", role="admin", account_type="research",
            )
            session.add(user)
            session.flush()
            interaction = ChatInteraction(
                user_id=user.id, status=status, query=query, legal_hold=held,
                created_at=NOW - timedelta(days=age_days),
                evidence_snapshot={"retained_source": token},
                answer_audit_snapshot={"trace": token},
            )
            session.add(interaction)
            session.flush()
            session.add(ChatFeedback(
                interaction_id=interaction.id, user_id=user.id, rating=1,
                comment="Dependent feedback fixture",
            ))
            return interaction.id, token

    def hold(self, interaction_id, value=True):
        return retention_routes.set_interaction_legal_hold(
            interaction_id, RetentionHoldRequest(legal_hold=value),
            CurrentUser(
                id=uuid.uuid4(), email="admin@example.test", display_name=None,
                role="admin", account_type="internal", status="active",
                permissions=frozenset(), auth_provider="disabled",
            ),
        )

    def cleanup(self, *, dry_run=False):
        return retention.cleanup_chat_interactions(
            retention_days=90, dry_run=dry_run, now=NOW,
        )

    def assert_retained(self, interaction_id, token, *, held=True):
        with self.factory() as session:
            row = session.get(ChatInteraction, interaction_id)
            assert row is not None
            assert row.legal_hold is held
            assert row.evidence_snapshot == {"retained_source": token}
            assert row.answer_audit_snapshot == {"trace": token}
            assert session.scalar(select(ChatFeedback.id).where(
                ChatFeedback.interaction_id == interaction_id,
            )) is not None

    def audit_counts(self):
        with self.factory() as session:
            events = session.scalars(select(AuditEvent)).all()
            return [
                row.metadata_json["deleted_count"]
                for row in events if row.action == "retention.chat_interactions_deleted"
            ], [row.action for row in events if row.action.startswith("admin.retention_hold_")]


@pytest.fixture
def isolated(disposable_database, monkeypatch):
    observer, url = disposable_database
    schema = f"c03_{uuid.uuid4().hex}"
    with observer.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, connect_args={"options": f"-csearch_path={schema} -clock_timeout=8000 -cstatement_timeout=12000"},
        pool_pre_ping=True,
    )
    try:
        AppBase.metadata.create_all(engine, tables=TABLES)
        database = IsolatedDatabase(
            engine=engine, observer=observer, schema=schema,
            factory=sessionmaker(bind=engine, expire_on_commit=False),
        )
        monkeypatch.setattr(retention, "get_session", database.session_context)
        monkeypatch.setattr(retention_routes, "get_session", database.session_context)
        yield database
    finally:
        engine.dispose()
        with observer.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


class Worker:
    def __init__(self, name, operation):
        self.name = name
        self.value = None
        self.error = None
        self.done = threading.Event()

        def run():
            try:
                self.value = operation()
            except BaseException as error:
                self.error = error
            finally:
                self.done.set()

        self.thread = threading.Thread(target=run, name=name, daemon=True)
        self.thread.start()

    def result(self):
        assert self.done.wait(15), f"{self.name} did not finish"
        self.thread.join()
        if self.error:
            raise self.error
        return self.value


class SQLBarrier:
    """Pause one named transaction immediately before or after a SQL command."""
    def __init__(self, engine, worker_name, command, *, after=False):
        self.engine = engine
        self.worker_name = worker_name
        self.command = command
        self.event_name = "after_cursor_execute" if after else "before_cursor_execute"
        self.entered = threading.Event()
        self.release = threading.Event()

    def _callback(self, connection, cursor, statement, parameters, context, executemany):
        normalized = statement.upper().replace('"', '')
        if (
            threading.current_thread().name == self.worker_name
            and normalized.startswith(self.command)
            and not self.entered.is_set()
        ):
            self.entered.set()
            assert self.release.wait(12), "SQL transaction barrier was not released"

    def __enter__(self):
        event.listen(self.engine, self.event_name, self._callback)
        return self

    def wait(self):
        assert self.entered.wait(10), f"{self.command} did not reach the transaction barrier"

    def __exit__(self, *_):
        self.release.set()
        event.remove(self.engine, self.event_name, self._callback)


def assert_lock_wait(database, waiter, blocker):
    """Assert a real PostgreSQL blocking relationship, rather than elapsed time."""
    deadline = time.monotonic() + 10
    observed = None
    while time.monotonic() < deadline:
        waiting_pid = database.pids.get(waiter.name)
        blocker_pid = database.pids.get(blocker.name)
        if waiting_pid and blocker_pid:
            with database.observer.connect() as connection:
                observed = connection.execute(text(
                    "SELECT wait_event_type, pg_blocking_pids(pid) "
                    "FROM pg_stat_activity WHERE pid = :pid"
                ), {"pid": waiting_pid}).first()
            if observed and observed[0] == "Lock" and blocker_pid in observed[1]:
                assert not waiter.done.is_set()
                return
        if waiter.done.is_set():
            pytest.fail(f"{waiter.name} completed without the required PostgreSQL lock wait")
        threading.Event().wait(0.01)
    pytest.fail(f"PostgreSQL blocking relationship was not observed: {observed}")


def legacy_selection_cleanup(database):
    """Retain the audited pre-C03 stale ORM-selection algorithm as a red probe."""
    with database.session_context() as session:
        conditions = (
            ChatInteraction.created_at < NOW - timedelta(days=90),
            ChatInteraction.status.in_(("completed", "failed")),
            ChatInteraction.legal_hold.is_(False),
        )
        count = session.scalar(select(func.count(ChatInteraction.id)).where(*conditions))
        selected = session.scalars(select(ChatInteraction).where(*conditions)).all()
        for interaction in selected:
            session.delete(interaction)
        session.flush()
        session.add(AuditEvent(
            action="retention.chat_interactions_deleted", target_type="chat_interaction",
            target_id="batch", metadata_json={"deleted_count": len(selected)},
        ))
        return count, len(selected)


def test_baseline_stale_orm_selection_reproduces_committed_hold_loss(isolated):
    interaction_id, _ = isolated.seed()
    with SQLBarrier(isolated.engine, "legacy", "DELETE FROM CHAT_INTERACTION") as barrier:
        cleanup = Worker("legacy", lambda: legacy_selection_cleanup(isolated))
        barrier.wait()
        assert isolated.hold(interaction_id).legal_hold is True
        barrier.release.set()
        assert cleanup.result() == (1, 1)
    with isolated.factory() as session:
        assert session.get(ChatInteraction, interaction_id) is None
        assert session.scalar(select(func.count(ChatFeedback.id))) == 0
    assert isolated.audit_counts() == ([1], ["admin.retention_hold_enabled"])


def test_hold_committed_after_count_before_delete_preserves_evidence_and_feedback(isolated):
    interaction_id, token = isolated.seed()
    with SQLBarrier(isolated.engine, "cleanup", "DELETE FROM CHAT_INTERACTION") as barrier:
        cleanup = Worker("cleanup", isolated.cleanup)
        barrier.wait()
        response = isolated.hold(interaction_id)
        assert response.legal_hold is True
        barrier.release.set()
        report = cleanup.result()
    assert report.eligible_count == 1  # observation before the hold; not a reservation
    assert report.deleted_count == 0
    isolated.assert_retained(interaction_id, token)
    assert isolated.audit_counts() == ([], ["admin.retention_hold_enabled"])


def test_hold_update_locks_first_delete_waits_and_rechecks_committed_hold(isolated):
    interaction_id, token = isolated.seed()
    with SQLBarrier(isolated.engine, "hold", "UPDATE CHAT_INTERACTION", after=True) as barrier:
        hold = Worker("hold", lambda: isolated.hold(interaction_id))
        barrier.wait()
        cleanup = Worker("cleanup", isolated.cleanup)
        assert_lock_wait(isolated, cleanup, hold)
        barrier.release.set()
        assert hold.result().legal_hold is True
        report = cleanup.result()
    assert report.eligible_count == 1
    assert report.deleted_count == 0
    isolated.assert_retained(interaction_id, token)
    assert isolated.audit_counts() == ([], ["admin.retention_hold_enabled"])


def test_delete_locks_first_hold_waits_then_reports_not_found_without_success_audit(isolated):
    interaction_id, _ = isolated.seed()
    with SQLBarrier(isolated.engine, "cleanup", "DELETE FROM CHAT_INTERACTION", after=True) as barrier:
        cleanup = Worker("cleanup", isolated.cleanup)
        barrier.wait()
        hold = Worker("hold", lambda: isolated.hold(interaction_id))
        assert_lock_wait(isolated, hold, cleanup)
        barrier.release.set()
        assert cleanup.result().deleted_count == 1
        with pytest.raises(HTTPException) as error:
            hold.result()
        assert error.value.status_code == 404
    with isolated.factory() as session:
        assert session.get(ChatInteraction, interaction_id) is None
        assert session.scalar(select(func.count(ChatFeedback.id))) == 0
    assert isolated.audit_counts() == ([1], [])


def test_concurrent_cleanup_workers_count_actual_deleted_parents_and_audit_once(isolated):
    for _ in range(3):
        isolated.seed()
    with SQLBarrier(isolated.engine, "first", "DELETE FROM CHAT_INTERACTION", after=True) as barrier:
        first = Worker("first", isolated.cleanup)
        barrier.wait()
        second = Worker("second", isolated.cleanup)
        assert_lock_wait(isolated, second, first)
        barrier.release.set()
        reports = [first.result(), second.result()]
    assert [report.eligible_count for report in reports] == [3, 3]
    assert sum(report.deleted_count for report in reports) == 3
    assert sorted(report.deleted_count for report in reports) == [0, 3]
    assert isolated.audit_counts() == ([3], [])
    with isolated.factory() as session:
        assert session.scalar(select(func.count(ChatInteraction.id))) == 0
        assert session.scalar(select(func.count(ChatFeedback.id))) == 0


@pytest.mark.parametrize("failure_point", ["audit_insert", "commit"])
def test_failed_cleanup_rolls_back_parent_feedback_evidence_and_success_audit(isolated, failure_point):
    interaction_id, token = isolated.seed()

    def fail_audit(connection, cursor, statement, parameters, context, executemany):
        if statement.upper().startswith("INSERT INTO AUDIT_EVENT"):
            raise RuntimeError("forced audit insertion failure")

    def fail_commit(session):
        session.flush()
        raise RuntimeError("forced transaction commit failure")

    if failure_point == "audit_insert":
        event.listen(isolated.engine, "before_cursor_execute", fail_audit)
    else:
        isolated.before_commit = fail_commit
    try:
        with pytest.raises(RuntimeError, match="forced"):
            isolated.cleanup()
    finally:
        isolated.before_commit = None
        if failure_point == "audit_insert":
            event.remove(isolated.engine, "before_cursor_execute", fail_audit)
    isolated.assert_retained(interaction_id, token, held=False)
    assert isolated.audit_counts() == ([], [])
    assert isolated.cleanup().deleted_count == 1
    assert isolated.audit_counts() == ([1], [])


def test_failed_hold_rolls_back_update_and_does_not_report_success(isolated):
    interaction_id, token = isolated.seed()

    def fail_commit(session):
        session.flush()
        raise RuntimeError("forced hold commit failure")

    isolated.before_commit = fail_commit
    try:
        with pytest.raises(RuntimeError, match="forced hold commit failure"):
            isolated.hold(interaction_id)
    finally:
        isolated.before_commit = None
    isolated.assert_retained(interaction_id, token, held=False)
    assert isolated.audit_counts() == ([], [])


def test_dry_run_observation_full_cutoff_status_predicate_and_repeat_cleanup(isolated):
    completed, _ = isolated.seed(query="expired completed")
    failed, _ = isolated.seed(query="expired failed", status="failed")
    held, held_token = isolated.seed(query="held", held=True)
    running, running_token = isolated.seed(query="running", status="running")
    recent, recent_token = isolated.seed(query="recent", age_days=89)
    boundary, boundary_token = isolated.seed(query="exact cutoff", age_days=90)
    observed = isolated.cleanup(dry_run=True)
    assert (observed.eligible_count, observed.deleted_count, observed.dry_run) == (2, 0, True)
    assert isolated.audit_counts() == ([], [])
    with isolated.factory() as session:
        assert session.scalar(select(func.count(ChatInteraction.id))) == 6
        assert session.scalar(select(func.count(ChatFeedback.id))) == 6
    isolated.hold(completed)
    report = isolated.cleanup()
    assert (report.eligible_count, report.deleted_count, report.dry_run) == (1, 1, False)
    assert isolated.cleanup().deleted_count == 0
    isolated.assert_retained(held, held_token)
    for interaction_id, token in [(running, running_token), (recent, recent_token), (boundary, boundary_token)]:
        isolated.assert_retained(interaction_id, token, held=False)
    with isolated.factory() as session:
        assert session.get(ChatInteraction, completed).legal_hold is True
        assert session.get(ChatInteraction, failed) is None
        assert session.scalar(select(func.count(ChatFeedback.id))) == 5
    assert isolated.audit_counts() == ([1], ["admin.retention_hold_enabled"])


@pytest.mark.parametrize("changed_field", ["status", "created_at"])
def test_full_delete_predicate_rechecks_eligibility_changed_after_count(isolated, changed_field):
    interaction_id, token = isolated.seed()
    with SQLBarrier(isolated.engine, "cleanup", "DELETE FROM CHAT_INTERACTION") as barrier:
        cleanup = Worker("cleanup", isolated.cleanup)
        barrier.wait()
        with isolated.factory.begin() as session:
            row = session.get(ChatInteraction, interaction_id)
            if changed_field == "status":
                row.status = "running"
            else:
                row.created_at = NOW
        barrier.release.set()
        report = cleanup.result()
    assert report.eligible_count == 1
    assert report.deleted_count == 0
    isolated.assert_retained(interaction_id, token, held=False)
    assert isolated.audit_counts() == ([], [])


def test_cleanup_cannot_reach_unrelated_user_fixtures_in_another_schema(isolated, disposable_database):
    observer, url = disposable_database
    other_schema = f"c03_unrelated_{uuid.uuid4().hex}"
    with observer.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{other_schema}"'))
    other_engine = create_engine(url, connect_args={"options": f"-csearch_path={other_schema}"})
    try:
        AppBase.metadata.create_all(other_engine, tables=TABLES)
        unrelated = IsolatedDatabase(
            engine=other_engine, observer=observer, schema=other_schema,
            factory=sessionmaker(bind=other_engine, expire_on_commit=False),
        )
        interaction_id, token = unrelated.seed(query="unrelated user's expired interaction")
        isolated.seed()
        assert isolated.cleanup().deleted_count == 1
        unrelated.assert_retained(interaction_id, token, held=False)
        assert unrelated.audit_counts() == ([], [])
    finally:
        other_engine.dispose()
        with observer.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{other_schema}" CASCADE'))
