from __future__ import annotations

import csv
import io
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.admin_feedback_routes as admin_feedback_routes
import api.auth as api_auth
from api.auth import CurrentUser, ROLE_PERMISSIONS, route_permission
from api.main import app
from db.app_models import (
    AppBase,
    AppUser,
    AuditEvent,
    ChatFeedback,
    ChatInteraction,
)


def _database():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AppBase.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _current_user(user: AppUser) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        account_type=user.account_type,
        status=user.status,
        permissions=ROLE_PERMISSIONS[user.role],
        auth_provider=user.auth_provider,
    )


def _install_database(monkeypatch, factory):
    @contextmanager
    def fake_get_session():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(
        admin_feedback_routes,
        "get_session",
        fake_get_session,
    )


def _seed_feedback(factory):
    with factory() as session:
        admin = AppUser(
            id=uuid.uuid4(),
            auth_provider="oidc",
            auth_subject="admin-subject",
            email="admin@example.org",
            display_name="Admin User",
            role="admin",
            account_type="internal",
            status="active",
        )
        researcher = AppUser(
            id=uuid.uuid4(),
            auth_provider="oidc",
            auth_subject="researcher-subject",
            email="researcher@example.org",
            display_name="Research User",
            role="researcher",
            account_type="research",
            status="active",
        )
        commercial = AppUser(
            id=uuid.uuid4(),
            auth_provider="oidc",
            auth_subject="commercial-subject",
            email="commercial@example.org",
            role="viewer",
            account_type="commercial",
            status="active",
        )
        session.add_all([admin, researcher, commercial])
        session.flush()

        definitions = [
            {
                "user": researcher,
                "rating": 1,
                "reasons": ["accurate", "clear"],
                "comment": "=HYPERLINK(\"https://example.invalid\")",
                "query": "Was the temperature reliable?",
                "model": "qwen2.5:14b-instruct",
                "created_at": datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
            },
            {
                "user": researcher,
                "rating": -1,
                "reasons": ["incorrect", "missing_evidence"],
                "comment": "The answer needs a source.",
                "query": "Compare salinity observations",
                "model": "qwen2.5:14b-instruct",
                "created_at": datetime(2026, 1, 2, 10, tzinfo=timezone.utc),
            },
            {
                "user": commercial,
                "rating": -1,
                "reasons": ["unclear"],
                "comment": "Please simplify this answer.",
                "query": "Summarize the monitoring program",
                "model": "llama3.2:latest",
                "created_at": datetime(2026, 1, 3, 10, tzinfo=timezone.utc),
            },
        ]
        feedback_ids = []
        for definition in definitions:
            interaction = ChatInteraction(
                id=uuid.uuid4(),
                user_id=definition["user"].id,
                status="completed",
                query=definition["query"],
                answer=f"Answer for {definition['query']}",
                model=definition["model"],
                request_options={"retrieval": {"k": 8}},
                evidence_snapshot={"sources": [{"doc_id": "ctd:test"}]},
                answer_audit_snapshot={"trust_level": "strong"},
                prompt_version="onagawa-chat-v1",
                prompt_sha256="a" * 64,
                corpus_fingerprint="b" * 64,
                latency_ms=125,
                created_at=definition["created_at"],
                completed_at=definition["created_at"],
            )
            session.add(interaction)
            session.flush()
            feedback = ChatFeedback(
                id=uuid.uuid4(),
                interaction_id=interaction.id,
                user_id=definition["user"].id,
                rating=definition["rating"],
                reason_codes=definition["reasons"],
                comment=definition["comment"],
                created_at=definition["created_at"],
                updated_at=definition["created_at"],
            )
            session.add(feedback)
            feedback_ids.append(feedback.id)
        session.commit()
        return _current_user(admin), _current_user(researcher), feedback_ids


def test_admin_feedback_list_metrics_filters_and_detail(monkeypatch):
    factory = _database()
    admin, _researcher, feedback_ids = _seed_feedback(factory)
    _install_database(monkeypatch, factory)
    monkeypatch.setattr(
        api_auth,
        "authenticate_request",
        lambda _request: admin,
    )
    client = TestClient(app)

    response = client.get(
        "/admin/feedback",
        params={
            "rating": -1,
            "reason_code": "incorrect",
            "role": "researcher",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["metrics"] == {
        "total": 1,
        "positive": 0,
        "negative": 1,
        "positive_rate": 0.0,
        "reason_counts": {
            "incorrect": 1,
            "missing_evidence": 1,
        },
    }
    assert payload["items"][0]["query"] == "Compare salinity observations"
    assert payload["items"][0]["user_email"] == "researcher@example.org"

    # Exact quoted JSON matching prevents "clear" from matching "unclear".
    exact_reason = client.get(
        "/admin/feedback",
        params={"reason_code": "clear", "account_type": "commercial"},
    )
    assert exact_reason.status_code == 200
    assert exact_reason.json()["total"] == 0

    date_filtered = client.get(
        "/admin/feedback",
        params={"date_from": "2026-01-03", "limit": 1},
    )
    assert date_filtered.status_code == 200
    assert date_filtered.json()["total"] == 1
    assert date_filtered.json()["items"][0]["model"] == "llama3.2:latest"

    detail = client.get(f"/admin/feedback/{feedback_ids[1]}")
    assert detail.status_code == 200
    assert detail.json()["answer"].startswith("Answer for")
    assert detail.json()["evidence_snapshot"]["sources"][0]["doc_id"] == (
        "ctd:test"
    )
    assert detail.json()["answer_audit_snapshot"]["trust_level"] == "strong"


def test_admin_feedback_export_is_safe_and_audited(monkeypatch):
    factory = _database()
    admin, _researcher, _feedback_ids = _seed_feedback(factory)
    _install_database(monkeypatch, factory)
    monkeypatch.setattr(
        api_auth,
        "authenticate_request",
        lambda _request: admin,
    )
    client = TestClient(app)

    response = client.get("/admin/feedback/export", params={"rating": 1})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "chat-feedback-" in response.headers["content-disposition"]
    rows = list(
        csv.DictReader(
            io.StringIO(response.content.decode("utf-8-sig"))
        )
    )
    assert len(rows) == 1
    assert rows[0]["rating"] == "1"
    assert rows[0]["comment"].startswith("'=")

    with factory() as session:
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "admin.feedback_exported"
            )
        )
        assert event is not None
        assert event.actor_user_id == admin.id
        assert event.metadata_json["row_count"] == 1
        assert event.metadata_json["filters"] == {"rating": 1}


def test_non_admin_cannot_review_or_export_feedback(monkeypatch):
    factory = _database()
    _admin, researcher, _feedback_ids = _seed_feedback(factory)
    _install_database(monkeypatch, factory)
    monkeypatch.setattr(
        api_auth,
        "authenticate_request",
        lambda _request: researcher,
    )
    client = TestClient(app)

    assert client.get("/admin/feedback").status_code == 403
    assert client.get("/admin/feedback/export").status_code == 403
    assert route_permission("GET", "/admin/feedback") == "feedback:review"
    assert (
        route_permission("GET", "/admin/feedback/export")
        == "feedback:export"
    )
