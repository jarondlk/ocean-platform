from __future__ import annotations

import uuid
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.auth as api_auth
import api.chat_records as chat_records
import api.feedback_routes as feedback_routes
import api.main as api_main
from api.auth import CurrentUser, ROLE_PERMISSIONS, resolve_identity
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

    monkeypatch.setattr(chat_records, "get_session", fake_get_session)
    monkeypatch.setattr(feedback_routes, "get_session", fake_get_session)


def _add_user(factory, email: str) -> CurrentUser:
    with factory() as session:
        user = AppUser(
            id=uuid.uuid4(),
            auth_provider="oidc",
            auth_subject=f"subject:{email}",
            email=email,
            role="researcher",
            account_type="research",
            status="active",
        )
        session.add(user)
        session.commit()
        return _current_user(user)


def _stub_chat_dependencies(monkeypatch):
    monkeypatch.setattr(
        api_main,
        "retrieve_with_expansion",
        lambda *args, **kwargs: {
            "primary": [
                {
                    "doc_id": "ctd:2024-01-O-s1",
                    "title": "CTD summary",
                    "source_type": "ctd",
                    "text": "The surface temperature was 12 C.",
                    "retrieval_role": "primary",
                }
            ],
            "linked": [],
            "diagnostics": {
                "expected_source_types": ["ctd"],
                "retrieved_source_types": ["ctd"],
                "missing_source_types": [],
            },
        },
    )


class _OllamaResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "message": {
                "content": "The temperature was 12 C [ctd:2024-01-O-s1]."
            }
        }


def test_chat_persists_completed_interaction_and_feedback_can_be_revised(
    monkeypatch,
):
    factory = _database()
    user = _add_user(factory, "researcher@example.org")
    _install_database(monkeypatch, factory)
    _stub_chat_dependencies(monkeypatch)
    monkeypatch.setattr(api_auth, "authenticate_request", lambda _request: user)
    monkeypatch.setattr(
        api_main.requests,
        "post",
        lambda *args, **kwargs: _OllamaResponse(),
    )
    client = TestClient(api_main.app)

    response = client.post(
        "/chat",
        json={
            "query": "What was the surface temperature?",
            "inject_analysis": False,
            "inject_reliability": False,
        },
    )

    assert response.status_code == 200
    interaction_id = uuid.UUID(response.json()["interaction_id"])
    with factory() as session:
        interaction = session.get(ChatInteraction, interaction_id)
        assert interaction is not None
        assert interaction.user_id == user.id
        assert interaction.status == "completed"
        assert interaction.answer.startswith("The temperature was")
        assert interaction.evidence_snapshot["sources"][0]["doc_id"] == (
            "ctd:2024-01-O-s1"
        )
        assert interaction.request_options["retrieval"]["k"] == 8
        assert len(interaction.prompt_sha256) == 64
        assert len(interaction.corpus_fingerprint) == 64
        assert interaction.latency_ms >= 0
        assert interaction.completed_at is not None

    missing_reason = client.put(
        f"/chat/interactions/{interaction_id}/feedback",
        json={"rating": -1, "reason_codes": []},
    )
    assert missing_reason.status_code == 422

    first = client.put(
        f"/chat/interactions/{interaction_id}/feedback",
        json={
            "rating": -1,
            "reason_codes": ["missing_evidence", "incomplete"],
            "comment": "Please include the observation date.",
        },
    )
    assert first.status_code == 200
    feedback_id = first.json()["id"]

    revised = client.put(
        f"/chat/interactions/{interaction_id}/feedback",
        json={"rating": 1, "reason_codes": ["helpful"], "comment": "Revised."},
    )
    assert revised.status_code == 200
    assert revised.json()["id"] == feedback_id
    assert revised.json()["rating"] == 1
    assert revised.json()["reason_codes"] == ["helpful"]

    fetched = client.get(f"/chat/interactions/{interaction_id}/feedback")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == feedback_id

    with factory() as session:
        assert session.scalar(select(ChatFeedback)).rating == 1
        events = session.scalars(
            select(AuditEvent).order_by(AuditEvent.created_at)
        ).all()
        assert [event.action for event in events] == [
            "chat.feedback_created",
            "chat.feedback_updated",
        ]


def test_database_backed_mock_identity_satisfies_chat_foreign_key(
    monkeypatch,
):
    factory = _database()
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("ENABLE_MOCK_LOGIN", "true")
    with factory() as session:
        user = resolve_identity(
            session,
            {
                "sub": "mock-login:viewer",
                "provider": "mock-credentials",
                "email": "viewer@mock.invalid",
                "email_verified": True,
                "name": "Mock Viewer",
                "mock_login_role": "viewer",
            },
        )
        session.commit()

    _install_database(monkeypatch, factory)
    interaction_id = chat_records.create_chat_interaction(
        user=user,
        query="Browser smoke test question",
        model="test-model",
        request_options={"test": True},
    )

    assert interaction_id is not None
    with factory() as session:
        interaction = session.get(ChatInteraction, interaction_id)
        assert interaction is not None
        assert interaction.user_id == user.id
        assert interaction.status == "running"


def test_chat_model_failure_is_persisted_and_returned_as_bad_gateway(monkeypatch):
    factory = _database()
    user = _add_user(factory, "failure@example.org")
    _install_database(monkeypatch, factory)
    _stub_chat_dependencies(monkeypatch)
    monkeypatch.setattr(api_auth, "authenticate_request", lambda _request: user)

    def fail_model(*args, **kwargs):
        raise ConnectionError("Ollama is offline")

    monkeypatch.setattr(api_main.requests, "post", fail_model)
    client = TestClient(api_main.app)

    response = client.post(
        "/chat",
        json={
            "query": "What was the surface temperature?",
            "inject_analysis": False,
            "inject_reliability": False,
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "llm_request_failed"
    interaction_id = uuid.UUID(response.json()["detail"]["interaction_id"])
    with factory() as session:
        interaction = session.get(ChatInteraction, interaction_id)
        assert interaction.status == "failed"
        assert interaction.error_code == "llm_request_failed"
        assert interaction.answer is None
        assert interaction.completed_at is not None

    feedback = client.put(
        f"/chat/interactions/{interaction_id}/feedback",
        json={"rating": 1, "reason_codes": []},
    )
    assert feedback.status_code == 409


def test_feedback_is_hidden_from_other_users(monkeypatch):
    factory = _database()
    owner = _add_user(factory, "owner@example.org")
    other_user = _add_user(factory, "other@example.org")
    _install_database(monkeypatch, factory)
    with factory() as session:
        interaction = ChatInteraction(
            id=uuid.uuid4(),
            user_id=owner.id,
            status="completed",
            query="Owner question",
            answer="Owner answer",
            request_options={},
            evidence_snapshot={},
        )
        session.add(interaction)
        session.commit()
        interaction_id = interaction.id

    monkeypatch.setattr(
        api_auth,
        "authenticate_request",
        lambda _request: other_user,
    )
    client = TestClient(api_main.app)

    assert (
        client.get(f"/chat/interactions/{interaction_id}/feedback").status_code
        == 404
    )
    assert (
        client.put(
            f"/chat/interactions/{interaction_id}/feedback",
            json={"rating": 1, "reason_codes": []},
        ).status_code
        == 404
    )
