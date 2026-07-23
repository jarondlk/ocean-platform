from __future__ import annotations

from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.auth as api_auth
from api.auth import (
    AuthenticationFailure,
    CurrentUser,
    ROLE_PERMISSIONS,
    decode_internal_token,
    resolve_identity,
    route_permission,
)
from api.main import app
from db.app_models import AppBase, AppUser, UserInvitation
from db.models import CorpusBase


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AppBase.metadata.create_all(engine)
    return Session(engine)


def test_corpus_and_application_metadata_are_isolated():
    assert set(CorpusBase.metadata.tables).isdisjoint(AppBase.metadata.tables)
    assert {
        "app_user",
        "user_invitation",
        "chat_interaction",
        "chat_feedback",
        "audit_event",
    }.issubset(AppBase.metadata.tables)


def test_invited_verified_identity_creates_user_and_consumes_invite():
    with _session() as session:
        session.add(
            UserInvitation(
                email="researcher@example.org",
                role="researcher",
                account_type="research",
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
        )
        session.commit()

        current = resolve_identity(
            session,
            {
                "sub": "provider-subject",
                "provider": "oidc",
                "email": "Researcher@Example.org",
                "email_verified": True,
                "name": "Example Researcher",
            },
        )
        session.commit()

        assert current.role == "researcher"
        assert "evaluation:run" in current.permissions
        user = session.query(AppUser).one()
        invitation = session.query(UserInvitation).one()
        assert user.email == "researcher@example.org"
        assert invitation.status == "accepted"
        assert invitation.accepted_at is not None


def test_uninvited_or_unverified_identity_is_rejected():
    with _session() as session:
        with pytest.raises(AuthenticationFailure, match="verified"):
            resolve_identity(
                session,
                {
                    "sub": "subject",
                    "provider": "oidc",
                    "email": "person@example.org",
                    "email_verified": False,
                },
            )
        with pytest.raises(AuthenticationFailure, match="not been invited"):
            resolve_identity(
                session,
                {
                    "sub": "subject",
                    "provider": "oidc",
                    "email": "person@example.org",
                    "email_verified": True,
                },
            )


def test_internal_token_requires_expected_issuer_audience_and_claims(monkeypatch):
    secret = "test-secret-that-is-at-least-thirty-two-characters"
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", secret)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "subject",
            "provider": "oidc",
            "email": "person@example.org",
            "email_verified": True,
            "iss": "onagawa-source-chat-frontend",
            "aud": "onagawa-source-chat-api",
            "iat": now,
            "exp": now + timedelta(seconds=60),
        },
        secret,
        algorithm="HS256",
    )
    claims = decode_internal_token(token)
    assert claims["sub"] == "subject"


def test_api_is_default_deny_and_liveness_stays_public(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/stats").status_code == 401


def test_viewer_cannot_access_admin_pipeline(monkeypatch):
    viewer = CurrentUser(
        id=__import__("uuid").uuid4(),
        email="viewer@example.org",
        display_name=None,
        role="viewer",
        account_type="commercial",
        status="active",
        permissions=ROLE_PERMISSIONS["viewer"],
        auth_provider="oidc",
    )
    monkeypatch.setattr(api_auth, "authenticate_request", lambda _request: viewer)
    client = TestClient(app)
    response = client.get("/pipeline/status")
    assert response.status_code == 403
    assert "pipeline:read" in response.text


def test_invited_identity_can_enter_me_and_suspension_is_immediate(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AppBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            UserInvitation(
                email="invited@example.org",
                role="viewer",
                account_type="commercial",
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
        )
        session.commit()

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

    secret = "integration-secret-that-is-at-least-thirty-two-characters"
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", secret)
    monkeypatch.setattr(api_auth, "get_session", fake_get_session)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "invited-subject",
            "provider": "oidc",
            "email": "invited@example.org",
            "email_verified": True,
            "iss": "onagawa-source-chat-frontend",
            "aud": "onagawa-source-chat-api",
            "iat": now,
            "exp": now + timedelta(seconds=60),
        },
        secret,
        algorithm="HS256",
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["account_type"] == "commercial"

    with factory() as session:
        user = session.query(AppUser).one()
        user.status = "suspended"
        session.commit()

    response = client.get("/me", headers=headers)
    assert response.status_code == 403
    assert "suspended" in response.text


def test_route_permission_map_is_explicit_for_sensitive_surfaces():
    assert route_permission("POST", "/pipeline/jobs") == "pipeline:execute"
    assert route_permission("POST", "/database/query") == "database:query"
    assert route_permission("GET", "/admin/users") == "users:manage"
    assert route_permission("GET", "/unknown") is None


def test_every_registered_api_route_has_an_explicit_policy():
    missing = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if path == "/health/live":
            continue
        methods = (getattr(route, "methods", set()) or set()) - {
            "HEAD",
            "OPTIONS",
        }
        for method in methods:
            if route_permission(method, path) is None:
                missing.append((method, path))
    assert missing == []
