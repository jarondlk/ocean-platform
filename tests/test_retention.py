from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
