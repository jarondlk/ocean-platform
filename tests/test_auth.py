from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import threading
import uuid

import anyio
import jwt
import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
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
from db.app_models import AppBase, AppUser, AuditEvent, UserInvitation
import db.connection as db_connection
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
        "classification_review",
        "classification_review_event",
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


def test_identity_provider_must_be_explicitly_allowed(monkeypatch):
    monkeypatch.setenv("AUTH_ALLOWED_PROVIDERS", "google")
    with _session() as session:
        session.add(
            UserInvitation(
                email="person@example.org",
                role="viewer",
                account_type="research",
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        session.commit()

        with pytest.raises(AuthenticationFailure, match="provider is not allowed"):
            resolve_identity(
                session,
                {
                    "sub": "subject",
                    "provider": "oidc",
                    "email": "person@example.org",
                    "email_verified": True,
                },
            )

        current = resolve_identity(
            session,
            {
                "sub": "subject",
                "provider": "google",
                "email": "person@example.org",
                "email_verified": True,
            },
        )
        assert current.auth_provider == "google"


@pytest.mark.parametrize("role", ["viewer", "researcher", "admin"])
def test_mock_login_identity_is_signed_database_backed_and_role_scoped(
    monkeypatch,
    role,
):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("ENABLE_MOCK_LOGIN", "true")

    with _session() as session:
        current = resolve_identity(
            session,
            {
                "sub": f"mock-login:{role}",
                "provider": "mock-credentials",
                "email": f"{role}@mock.invalid",
                "email_verified": True,
                "name": f"Mock {role.title()}",
                "mock_login_role": role,
            },
        )
        assert current.role == role
        assert current.permissions == ROLE_PERMISSIONS[role]
        assert current.auth_provider == "mock-credentials"
        assert current.account_type == "internal"
        user = session.query(AppUser).one()
        assert user.id == current.id
        assert user.auth_subject == f"mock-login:{role}"
        assert user.email == f"{role}@mock.invalid"
        assert session.query(UserInvitation).count() == 0


def test_mock_login_identity_fails_closed_when_disabled_or_malformed(
    monkeypatch,
):
    claims = {
        "sub": "mock-login:viewer",
        "provider": "mock-credentials",
        "email": "viewer@mock.invalid",
        "email_verified": True,
        "mock_login_role": "viewer",
    }
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("ENABLE_MOCK_LOGIN", "false")
    with _session() as session:
        with pytest.raises(AuthenticationFailure, match="disabled"):
            resolve_identity(session, claims)

    monkeypatch.setenv("ENABLE_MOCK_LOGIN", "true")
    with _session() as session:
        with pytest.raises(AuthenticationFailure, match="claims are invalid"):
            resolve_identity(
                session,
                {
                    **claims,
                    "sub": "mock-login:admin",
                },
            )


@pytest.mark.parametrize("role", ["viewer", "researcher", "admin"])
def test_mock_login_internal_token_reaches_me_with_database_fixture(
    monkeypatch,
    role,
):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AppBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

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

    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("ENABLE_MOCK_LOGIN", "true")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", TOKEN_SECRET)
    monkeypatch.setattr(api_auth, "get_session", fake_get_session)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": f"mock-login:{role}",
            "provider": "mock-credentials",
            "email": f"{role}@mock.invalid",
            "email_verified": True,
            "name": f"Mock {role.title()}",
            "mock_login_role": role,
            "iss": "ocean-platform-frontend",
            "aud": "ocean-platform-api",
            "iat": now,
            "exp": now + timedelta(seconds=60),
        },
        TOKEN_SECRET,
        algorithm="HS256",
    )
    response = TestClient(app).get(
        "/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == role
    assert response.json()["email"] == f"{role}@mock.invalid"
    assert response.json()["account_type"] == "internal"
    with factory() as session:
        assert session.query(AppUser).count() == 1


def test_mock_login_uses_database_role_and_suspension(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("ENABLE_MOCK_LOGIN", "true")
    claims = {
        "sub": "mock-login:viewer",
        "provider": "mock-credentials",
        "email": "viewer@mock.invalid",
        "email_verified": True,
        "name": "Mock Viewer",
        "mock_login_role": "viewer",
    }

    with _session() as session:
        current = resolve_identity(session, claims)
        user = session.get(AppUser, current.id)
        user.role = "researcher"
        session.commit()

        updated = resolve_identity(session, claims)
        assert updated.role == "researcher"
        assert updated.permissions == ROLE_PERMISSIONS["researcher"]

        user.status = "suspended"
        session.commit()
        with pytest.raises(AuthenticationFailure, match="suspended"):
            resolve_identity(session, claims)


def test_internal_token_requires_expected_issuer_audience_and_claims(monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", TOKEN_SECRET)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "subject",
            "provider": "oidc",
            "email": "person@example.org",
            "email_verified": True,
            "iss": "ocean-platform-frontend",
            "aud": "ocean-platform-api",
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
        "iss": "ocean-platform-frontend",
        "aud": "ocean-platform-api",
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


@pytest.mark.parametrize("role", ["viewer", "researcher", "admin"])
def test_chat_settings_contract_and_filter_choices_use_chat_permission(monkeypatch, role):
    from retrieval.source_scope import FAMILIES
    user = CurrentUser(id=uuid.uuid4(), email=f"{role}@test.invalid", display_name=None,
                       role=role, account_type="research", status="active",
                       permissions=ROLE_PERMISSIONS[role], auth_provider="test")
    monkeypatch.setattr(api_auth, "authenticate_request", lambda request: user)
    monkeypatch.setattr("orchestration.unified._pg_available", lambda: False)
    monkeypatch.setattr("retrieval.filter_options.filter_options", lambda *a, **kw: {"backend": "local", "sources": {}})
    client = TestClient(app)
    assert client.get("/chat/capabilities").status_code == 200
    envelope = {"version": 1, "sources": {family: {"enabled": True, "filters": {}} for family in FAMILIES}}
    assert client.post("/chat/filter-options", json={"evidence_scope": envelope}).status_code == 200
    assert api_auth.route_permission("POST", "/chat/filter-options") == "chat:use"
    assert api_auth.route_permission("GET", "/chat/capabilities") == "chat:use"


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


def test_database_backed_mock_admin_can_create_and_revoke_invitation(
    monkeypatch,
):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AppBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        admin = AppUser(
            auth_provider="mock-credentials",
            auth_subject="mock-login:admin",
            email="admin@mock.invalid",
            display_name="Mock Admin",
            role="admin",
            account_type="internal",
            status="active",
        )
        session.add(admin)
        session.commit()
        admin_id = admin.id

    actor = CurrentUser(
        id=admin_id,
        email="admin@mock.invalid",
        display_name="Mock Admin",
        role="admin",
        account_type="internal",
        status="active",
        permissions=ROLE_PERMISSIONS["admin"],
        auth_provider="mock-credentials",
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

    created = client.post(
        "/admin/invitations",
        json={
            "email": "browser-smoke@mock.invalid",
            "role": "viewer",
            "account_type": "research",
        },
    )
    assert created.status_code == 201
    invitation_id = created.json()["id"]

    revoked = client.post(
        f"/admin/invitations/{invitation_id}/revoke",
        json={},
    )
    repeated = client.post(
        f"/admin/invitations/{invitation_id}/revoke",
        json={},
    )

    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "revoked"
    with factory() as session:
        invitation = session.get(
            UserInvitation,
            uuid.UUID(invitation_id),
        )
        assert invitation.status == "revoked"
        actions = [
            event.action
            for event in session.query(AuditEvent)
            .order_by(AuditEvent.created_at)
            .all()
        ]
        assert actions == [
            "admin.invitation_created",
            "admin.invitation_revoked",
        ]


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
            "iss": "ocean-platform-frontend",
            "aud": "ocean-platform-api",
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
    assert route_permission("POST", "/database/query") is None
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
        (
            "GET",
            "/classification-reviews",
            "classification:read",
            {"researcher", "admin"},
        ),
        (
            "POST",
            "/classification-reviews",
            "classification:decide",
            {"researcher"},
        ),
        (
            "POST",
            "/classification-reviews/00000000-0000-0000-0000-000000000000/decision",
            "classification:decide",
            {"researcher"},
        ),
        (
            "POST",
            "/classification-reviews/00000000-0000-0000-0000-000000000000/preview",
            "classification:read",
            {"researcher", "admin"},
        ),
        (
            "POST",
            "/classification-reviews/00000000-0000-0000-0000-000000000000/application",
            None,
            set(),
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


def _c04_request(*, path="/me", token="synthetic-token"):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "scheme": "http",
            "server": ("test.invalid", 80),
            "client": ("127.0.0.1", 12345),
            "query_string": b"",
        }
    )


async def _c04_wait_for_worker(started, *requests):
    """Fail promptly on the old synchronous boundary without hanging a barrier."""
    waiting = asyncio.create_task(started.wait())
    try:
        completed, _ = await asyncio.wait(
            [waiting, *requests], timeout=5, return_when=asyncio.FIRST_COMPLETED
        )
        for request in requests:
            if request in completed:
                await request
                pytest.fail("Authentication completed before its barrier was released")
        assert waiting in completed, "Authentication worker never reached its barrier"
    finally:
        waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)


def test_c04_delayed_authentication_allows_heartbeat_and_public_liveness(monkeypatch):
    release = threading.Event()
    handlers = []
    user = CurrentUser(
        id=uuid.uuid4(), email="viewer@synthetic.invalid", display_name=None,
        role="viewer", account_type="research", status="active",
        permissions=ROLE_PERMISSIONS["viewer"], auth_provider="oidc",
    )
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")

    async def scenario():
        loop = asyncio.get_running_loop()
        loop_thread = threading.get_ident()
        started = asyncio.Event()
        heartbeat = asyncio.Event()

        def delayed_authentication(_request):
            # The old path fails this guard instead of deadlocking the test's
            # event loop. The fixed path remains blocked until sibling work runs.
            assert threading.get_ident() != loop_thread, "Authentication blocks the event loop"
            loop.call_soon_threadsafe(started.set)
            assert release.wait(5), "Authentication barrier was never released"
            return user

        async def protected(request):
            handlers.append(api_auth.get_current_user(request).id)
            return JSONResponse({"ok": True})

        async def live(_request):
            return JSONResponse({"status": "live"})

        monkeypatch.setattr(api_auth, "authenticate_request", delayed_authentication)
        request = _c04_request()
        pending = asyncio.create_task(api_auth.authorization_middleware(request, protected))
        try:
            await _c04_wait_for_worker(started, pending)
            loop.call_soon(heartbeat.set)
            response = await api_auth.authorization_middleware(
                _c04_request(path="/health/live"), live
            )
            await asyncio.wait_for(heartbeat.wait(), 5)
            assert response.status_code == 200
            assert not pending.done()
            assert handlers == []
            assert not hasattr(request.state, "current_user")
            release.set()
            response = await pending
            assert response.status_code == 200
            assert handlers == [user.id]
        finally:
            release.set()
            await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(scenario())


class _C04AuthStore:
    """Synthetic store controls; no session or ORM object reaches a handler."""

    def __init__(self, engine):
        self.engine = engine
        self.traces = []
        self.lock = threading.Lock()
        self.release = threading.Event()
        self.block_lookup = False
        self.failure = None
        self.expected_waiters = 1
        self.waiters = 0
        self.closed = 0

    def bind_loop(self, *, block_lookup=False, expected_waiters=1):
        self.loop = asyncio.get_running_loop()
        self.loop_thread = threading.get_ident()
        self.started = asyncio.Event()
        self.all_closed = asyncio.Event()
        self.block_lookup = block_lookup
        self.expected_waiters = expected_waiters

    def wait_for_release(self):
        assert threading.get_ident() != self.loop_thread, "Authentication lookup blocks the event loop"
        with self.lock:
            self.waiters += 1
            if self.waiters == self.expected_waiters:
                self.loop.call_soon_threadsafe(self.started.set)
        assert self.release.wait(5), "Authentication lookup barrier was never released"

    def assert_closed_on_workers(self):
        assert self.traces
        for trace in self.traces:
            assert trace["owner"] != self.loop_thread
            assert trace["operations"][0] == "create"
            assert trace["operations"][-1] == "close"
            assert len(set(trace["threads"])) == 1
        assert self.closed == len(self.traces)


@pytest.fixture
def c04_auth_store(monkeypatch, tmp_path):
    """Real transactions use a disposable SQLite file and checked sessions."""
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'c04-auth.sqlite'}")
    AppBase.metadata.create_all(engine)
    with Session(engine) as session:
        now = datetime.now(timezone.utc)
        for subject, role, status in (
            ("viewer", "viewer", "active"),
            ("researcher", "researcher", "active"),
            ("suspended", "viewer", "suspended"),
        ):
            session.add(
                AppUser(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, f"c04-synthetic:{subject}"),
                    auth_provider="oidc", auth_subject=subject,
                    email=f"{subject}@synthetic.invalid", role=role,
                    account_type="research", status=status, last_login_at=now,
                )
            )
        for subject, status in (("invited", "pending"), ("revoked", "revoked")):
            session.add(
                UserInvitation(
                    email=f"{subject}@synthetic.invalid", role="viewer",
                    account_type="research", status=status,
                    expires_at=now + timedelta(days=1),
                )
            )
        session.commit()

    store = _C04AuthStore(engine)

    class CheckedSession(Session):
        def __init__(self):
            super().__init__(bind=engine, expire_on_commit=False)
            self.trace = {"owner": threading.get_ident(), "operations": [], "threads": []}
            with store.lock:
                store.traces.append(self.trace)
            self.record("create")
            self.waited = False

        def record(self, operation):
            thread = threading.get_ident()
            assert thread == self.trace["owner"], f"Session crossed threads during {operation}"
            self.trace["operations"].append(operation)
            self.trace["threads"].append(thread)

        def scalar(self, *args, **kwargs):
            self.record("query")
            if store.block_lookup and not self.waited:
                self.waited = True
                store.wait_for_release()
            if store.failure == "query":
                raise SQLAlchemyError("Synthetic identity lookup failure")
            return super().scalar(*args, **kwargs)

        def flush(self, *args, **kwargs):
            self.record("flush")
            return super().flush(*args, **kwargs)

        def commit(self):
            self.record("commit")
            if store.failure == "commit":
                raise SQLAlchemyError("Synthetic identity commit failure")
            return super().commit()

        def rollback(self):
            self.record("rollback")
            return super().rollback()

        def close(self):
            self.record("close")
            try:
                return super().close()
            finally:
                with store.lock:
                    store.closed += 1
                    if store.closed >= store.expected_waiters:
                        store.loop.call_soon_threadsafe(store.all_closed.set)

    resolve = api_auth.resolve_identity

    def checked_resolve(session, claims):
        session.trace["subject"] = claims["sub"]
        session.record("resolve")
        current = resolve(session, claims)
        session.record("materialize")
        assert isinstance(current, CurrentUser)
        return current

    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("AUTH_ALLOWED_PROVIDERS", "oidc")
    monkeypatch.setenv("PERSIST_LOCAL_CHAT", "false")
    monkeypatch.setenv("ENABLE_MOCK_LOGIN", "false")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", TOKEN_SECRET)
    monkeypatch.setenv("INTERNAL_AUTH_ISSUER", "ocean-platform-frontend")
    monkeypatch.setenv("INTERNAL_AUTH_AUDIENCE", "ocean-platform-api")
    # Exercise the actual transaction context manager, including context exit
    # commit errors, rather than replacing it with a fake lifecycle.
    monkeypatch.setattr(db_connection, "get_session_factory", lambda: CheckedSession)
    monkeypatch.setattr(api_auth, "get_session", db_connection.get_session)
    monkeypatch.setattr(api_auth, "resolve_identity", checked_resolve)
    try:
        yield store
    finally:
        store.release.set()
        engine.dispose()


def _c04_identity_token(subject, *, verified=True):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": subject, "provider": "oidc",
            "email": f"{subject}@synthetic.invalid", "email_verified": verified,
            "iss": "ocean-platform-frontend", "aud": "ocean-platform-api",
            "iat": now, "exp": now + timedelta(seconds=60),
        },
        TOKEN_SECRET,
        algorithm="HS256",
    )


def _c04_assert_security_headers(response):
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    if response.status_code == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"
    else:
        assert "WWW-Authenticate" not in response.headers


def test_c04_complete_identity_session_lifetime_runs_on_one_worker(c04_auth_store):
    store = c04_auth_store

    async def scenario():
        store.bind_loop()
        request = _c04_request(token=_c04_identity_token("invited"))

        async def protected(request):
            store.assert_closed_on_workers()
            assert isinstance(api_auth.get_current_user(request), CurrentUser)
            assert threading.get_ident() == store.loop_thread
            return JSONResponse({"ok": True})

        response = await api_auth.authorization_middleware(request, protected)
        assert response.status_code == 200
        _c04_assert_security_headers(response)
        operations = store.traces[0]["operations"]
        assert {"create", "resolve", "query", "flush", "materialize", "commit", "close"} <= set(operations)
        assert operations.index("materialize") < operations.index("commit") < operations.index("close")

    asyncio.run(scenario())
    with Session(store.engine) as session:
        invited = session.query(AppUser).filter_by(auth_subject="invited").one()
        invitation = session.query(UserInvitation).filter_by(email=invited.email).one()
        assert invitation.status == "accepted"


def test_c04_parallel_authentication_preserves_each_users_identity(c04_auth_store):
    store = c04_auth_store
    observed = []

    async def scenario():
        store.bind_loop(block_lookup=True, expected_waiters=2)
        requests = [
            _c04_request(token=_c04_identity_token(subject))
            for subject in ("viewer", "researcher")
        ]

        async def protected(request):
            current = api_auth.get_current_user(request)
            trace = next(trace for trace in store.traces if trace["subject"] == current.role)
            assert trace["operations"][-1] == "close"
            observed.append((current.id, current.email, current.role, current.permissions))
            return JSONResponse({"ok": True})

        pending = [
            asyncio.create_task(api_auth.authorization_middleware(request, protected))
            for request in requests
        ]
        try:
            await _c04_wait_for_worker(store.started, *pending)
            assert observed == []
            assert all(not hasattr(request.state, "current_user") for request in requests)
            store.release.set()
            responses = await asyncio.gather(*pending)
            assert all(response.status_code == 200 for response in responses)
            assert requests[0].state.current_user is not requests[1].state.current_user
        finally:
            store.release.set()
            await asyncio.gather(*pending, return_exceptions=True)
        store.assert_closed_on_workers()

    asyncio.run(scenario())
    assert set(observed) == {
        (
            uuid.uuid5(uuid.NAMESPACE_URL, f"c04-synthetic:{subject}"),
            f"{subject}@synthetic.invalid", subject, ROLE_PERMISSIONS[subject],
        )
        for subject in ("viewer", "researcher")
    }


@pytest.mark.parametrize(
    ("subject", "verified", "status_code"),
    [("bad-token", True, 401), ("suspended", True, 403), ("revoked", True, 403), ("viewer", False, 403)],
)
def test_c04_rejected_identity_never_sets_state_or_reaches_handler(
    c04_auth_store, subject, verified, status_code,
):
    store = c04_auth_store
    handlers = []

    async def scenario():
        store.bind_loop()
        token = "invalid.jwt.token" if subject == "bad-token" else _c04_identity_token(subject, verified=verified)
        request = _c04_request(token=token)

        async def protected(_request):
            handlers.append("unauthorized")
            return JSONResponse({"ok": True})

        response = await api_auth.authorization_middleware(request, protected)
        assert response.status_code == status_code
        _c04_assert_security_headers(response)
        assert handlers == []
        assert not hasattr(request.state, "current_user")
        if subject == "bad-token":
            assert store.traces == []
        else:
            store.assert_closed_on_workers()
            assert "rollback" in store.traces[0]["operations"]
            assert "commit" not in store.traces[0]["operations"]

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["query", "commit"])
def test_c04_authentication_database_errors_roll_back_and_fail_closed(c04_auth_store, failure):
    store = c04_auth_store
    store.failure = failure
    handlers = []

    async def scenario():
        store.bind_loop()
        request = _c04_request(token=_c04_identity_token("invited"))

        async def protected(_request):
            handlers.append("uncommitted")
            return JSONResponse({"ok": True})

        response = await api_auth.authorization_middleware(request, protected)
        assert response.status_code == 503
        assert b"Authentication database is unavailable" in response.body
        _c04_assert_security_headers(response)
        assert handlers == []
        assert not hasattr(request.state, "current_user")
        store.assert_closed_on_workers()
        assert "rollback" in store.traces[0]["operations"]
        if failure == "commit":
            assert "materialize" in store.traces[0]["operations"]
            assert "commit" in store.traces[0]["operations"]

    asyncio.run(scenario())
    with Session(store.engine) as session:
        assert session.query(AppUser).filter_by(auth_subject="invited").count() == 0
        assert session.query(UserInvitation).filter_by(email="invited@synthetic.invalid").one().status == "pending"


@pytest.mark.parametrize("cancellation", ["asyncio", "anyio"])
def test_c04_cancelled_authentication_closes_session_without_handler_or_state(
    c04_auth_store, cancellation,
):
    store = c04_auth_store
    handlers = []

    async def scenario():
        store.bind_loop(block_lookup=True)
        request = _c04_request(token=_c04_identity_token("viewer"))

        async def protected(request):
            handlers.append(api_auth.get_current_user(request).email)
            return JSONResponse({"ok": True})

        if cancellation == "asyncio":
            pending = asyncio.create_task(api_auth.authorization_middleware(request, protected))
            try:
                await _c04_wait_for_worker(store.started, pending)
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
            finally:
                store.release.set()
                await asyncio.gather(pending, return_exceptions=True)
                await asyncio.wait_for(store.all_closed.wait(), 5)
        else:
            scopes = []
            finished = anyio.Event()

            async def scoped_request():
                with anyio.CancelScope() as scope:
                    scopes.append(scope)
                    await api_auth.authorization_middleware(request, protected)
                finished.set()

            async with anyio.create_task_group() as group:
                group.start_soon(scoped_request)
                try:
                    await asyncio.wait_for(store.started.wait(), 5)
                    scopes[0].cancel()
                finally:
                    # Release before task-group cleanup: AnyIO shields worker
                    # completion, so scope cancellation alone cannot stop it.
                    store.release.set()
                with anyio.fail_after(5):
                    await finished.wait()
                    await store.all_closed.wait()

        store.assert_closed_on_workers()
        assert handlers == []
        assert not hasattr(request.state, "current_user")

        # A later request uses a fresh state and session after the cancelled one.
        store.block_lookup = False
        later = _c04_request(token=_c04_identity_token("researcher"))
        response = await api_auth.authorization_middleware(later, protected)
        assert response.status_code == 200
        assert handlers == ["researcher@synthetic.invalid"]
        assert later.state.current_user.role == "researcher"
        assert not hasattr(request.state, "current_user")
        store.assert_closed_on_workers()

    anyio.run(scenario)
