from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.auth as api_auth
import api.auth_routes as auth_routes
import config
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


TOKEN_SECRET = "test-secret-that-is-at-least-thirty-two-characters"


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
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", TOKEN_SECRET)
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
        TOKEN_SECRET,
        algorithm="HS256",
    )
    claims = decode_internal_token(token)
    assert claims["sub"] == "subject"


@pytest.mark.parametrize(
    "failure",
    [
        "wrong_issuer",
        "wrong_audience",
        "missing_email",
        "expired",
        "future_iat",
        "excessive_lifetime",
        "wrong_signature",
        "wrong_algorithm",
    ],
)
def test_internal_token_rejects_adversarial_claims(monkeypatch, failure):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", TOKEN_SECRET)
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "subject",
        "provider": "oidc",
        "email": "person@example.org",
        "email_verified": True,
        "iss": "onagawa-source-chat-frontend",
        "aud": "onagawa-source-chat-api",
        "iat": now,
        "exp": now + timedelta(seconds=60),
    }
    signing_secret = TOKEN_SECRET
    algorithm = "HS256"

    if failure == "wrong_issuer":
        claims["iss"] = "untrusted-frontend"
    elif failure == "wrong_audience":
        claims["aud"] = "other-api"
    elif failure == "missing_email":
        claims.pop("email")
    elif failure == "expired":
        claims["iat"] = now - timedelta(minutes=2)
        claims["exp"] = now - timedelta(minutes=1)
    elif failure == "future_iat":
        claims["iat"] = now + timedelta(minutes=1)
        claims["exp"] = now + timedelta(minutes=2)
    elif failure == "excessive_lifetime":
        claims["exp"] = now + timedelta(minutes=10)
    elif failure == "wrong_signature":
        signing_secret = "different-secret-that-is-also-at-least-thirty-two"
    elif failure == "wrong_algorithm":
        algorithm = "HS384"

    token = jwt.encode(claims, signing_secret, algorithm=algorithm)
    with pytest.raises(
        AuthenticationFailure,
        match="Invalid or expired identity token",
    ):
        decode_internal_token(token)


@pytest.mark.parametrize(
    ("status", "expires_delta", "message"),
    [
        ("accepted", timedelta(days=1), "not been invited"),
        ("revoked", timedelta(days=1), "not been invited"),
        ("expired", timedelta(days=1), "not been invited"),
        ("pending", timedelta(seconds=-1), "expired"),
    ],
)
def test_invitation_must_be_pending_and_unexpired(
    status,
    expires_delta,
    message,
):
    with _session() as session:
        session.add(
            UserInvitation(
                email="person@example.org",
                role="viewer",
                account_type="commercial",
                status=status,
                expires_at=datetime.now(timezone.utc) + expires_delta,
            )
        )
        session.commit()

        with pytest.raises(AuthenticationFailure, match=message):
            resolve_identity(
                session,
                {
                    "sub": "subject",
                    "provider": "oidc",
                    "email": "person@example.org",
                    "email_verified": True,
                },
            )
        assert session.query(AppUser).count() == 0


def test_identity_claim_lengths_are_bounded_and_display_name_is_truncated():
    with _session() as session:
        session.add(
            UserInvitation(
                email="person@example.org",
                role="viewer",
                account_type="commercial",
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        session.commit()

        with pytest.raises(AuthenticationFailure, match="subject is invalid"):
            resolve_identity(
                session,
                {
                    "sub": "s" * 256,
                    "provider": "oidc",
                    "email": "person@example.org",
                    "email_verified": True,
                },
            )

        current = resolve_identity(
            session,
            {
                "sub": "subject",
                "provider": "oidc",
                "email": "person@example.org",
                "email_verified": True,
                "name": "n" * 500,
            },
        )
        assert current.display_name == "n" * 255


def test_api_is_default_deny_and_liveness_stays_public(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.post("/health/live").status_code == 401
    assert client.get("/stats").status_code == 401


def test_production_auth_bypass_is_rejected_at_startup_and_request_time(
    monkeypatch,
):
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("PERSIST_LOCAL_CHAT", "false")
    client = TestClient(app)

    assert client.get("/health/live").status_code == 200
    response = client.get("/stats")
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Authentication security configuration is invalid"
    )

    with pytest.raises(
        config.SecurityConfigurationError,
        match="AUTH_MODE=disabled",
    ):
        with TestClient(app):
            pass


def test_oversized_or_malformed_bearer_tokens_are_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")
    client = TestClient(app)

    oversized = client.get(
        "/me",
        headers={"Authorization": f"Bearer {'x' * 8193}"},
    )
    malformed = client.get(
        "/me",
        headers={"Authorization": "Bearer token with spaces"},
    )

    assert oversized.status_code == 401
    assert malformed.status_code == 401


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


def test_non_admin_cannot_access_user_administration(monkeypatch):
    researcher = CurrentUser(
        id=__import__("uuid").uuid4(),
        email="researcher@example.org",
        display_name=None,
        role="researcher",
        account_type="research",
        status="active",
        permissions=ROLE_PERMISSIONS["researcher"],
        auth_provider="oidc",
    )
    monkeypatch.setattr(
        api_auth,
        "authenticate_request",
        lambda _request: researcher,
    )
    client = TestClient(app)

    assert client.get("/admin/users").status_code == 403
    assert client.get("/admin/invitations").status_code == 403
    assert (
        client.post(
            "/admin/invitations",
            json={"email": "new-user@example.org"},
        ).status_code
        == 403
    )


def test_admin_cannot_demote_or_suspend_self(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AppBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        admin = AppUser(
            auth_provider="oidc",
            auth_subject="admin-subject",
            email="admin@example.org",
            role="admin",
            account_type="internal",
            status="active",
        )
        session.add(admin)
        session.commit()
        admin_id = admin.id

    actor = CurrentUser(
        id=admin_id,
        email="admin@example.org",
        display_name=None,
        role="admin",
        account_type="internal",
        status="active",
        permissions=ROLE_PERMISSIONS["admin"],
        auth_provider="oidc",
    )

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
        api_auth,
        "authenticate_request",
        lambda _request: actor,
    )
    monkeypatch.setattr(auth_routes, "get_session", fake_get_session)
    client = TestClient(app)

    demotion = client.patch(
        f"/admin/users/{admin_id}",
        json={"role": "researcher"},
    )
    suspension = client.patch(
        f"/admin/users/{admin_id}",
        json={"status": "suspended"},
    )

    assert demotion.status_code == 400
    assert suspension.status_code == 400
    with factory() as session:
        unchanged = session.get(AppUser, admin_id)
        assert unchanged.role == "admin"
        assert unchanged.status == "active"


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


@pytest.mark.parametrize(
    ("method", "path", "permission", "allowed_roles"),
    [
        ("GET", "/me", "profile:read", {"viewer", "researcher", "admin"}),
        ("POST", "/chat", "chat:use", {"viewer", "researcher", "admin"}),
        (
            "PUT",
            "/chat/interactions/00000000-0000-0000-0000-000000000000/feedback",
            "feedback:write",
            {"viewer", "researcher", "admin"},
        ),
        (
            "GET",
            "/data/ctd",
            "data:read",
            {"researcher", "admin"},
        ),
        (
            "POST",
            "/evaluation/runs",
            "evaluation:run",
            {"researcher", "admin"},
        ),
        ("GET", "/pipeline/status", "pipeline:read", {"admin"}),
        ("POST", "/pipeline/jobs", "pipeline:execute", {"admin"}),
        ("GET", "/database/schema", "database:read", {"admin"}),
        ("POST", "/database/query", "database:query", {"admin"}),
        ("GET", "/admin/users", "users:manage", {"admin"}),
        (
            "GET",
            "/admin/feedback",
            "feedback:review",
            {"admin"},
        ),
        (
            "GET",
            "/admin/feedback/export",
            "feedback:export",
            {"admin"},
        ),
    ],
)
def test_role_permission_matrix(
    method,
    path,
    permission,
    allowed_roles,
):
    assert route_permission(method, path) == permission
    actual_roles = {
        role
        for role, permissions in ROLE_PERMISSIONS.items()
        if permission in permissions
    }
    assert actual_roles == allowed_roles


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
