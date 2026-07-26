from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

import config
from api.auth import AuthenticationFailure, resolve_identity
from db.app_models import AppUser, AuditEvent, UserInvitation


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires the disposable PostgreSQL integration service",
)


def test_migrations_and_invite_acceptance_persist_app_metadata():
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    table_names = set(inspect(engine).get_table_names())
    assert {
        "app_user",
        "user_invitation",
        "chat_interaction",
        "chat_feedback",
        "audit_event",
    }.issubset(table_names)

    unique = uuid.uuid4().hex
    email = f"integration-{unique}@example.org"
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
            ) as session:
                invitation = UserInvitation(
                    email=email,
                    role="researcher",
                    account_type="research",
                    status="pending",
                    expires_at=(
                        datetime.now(timezone.utc) + timedelta(minutes=5)
                    ),
                )
                session.add(invitation)
                session.commit()

                current = resolve_identity(
                    session,
                    {
                        "sub": f"integration-subject-{unique}",
                        "provider": "oidc",
                        "email": email,
                        "email_verified": True,
                        "name": "PostgreSQL integration user",
                    },
                )
                session.commit()

                user = session.scalar(
                    select(AppUser).where(AppUser.id == current.id)
                )
                event = session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.action == "auth.invitation_accepted",
                        AuditEvent.actor_user_id == current.id,
                    )
                )
                session.refresh(invitation)

                assert user is not None
                assert user.role == "researcher"
                assert invitation.status == "accepted"
                assert invitation.accepted_at is not None
                assert event is not None
        finally:
            if transaction.is_active:
                transaction.rollback()


def test_mock_identity_is_database_backed_for_audited_mutations(
    monkeypatch,
):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("ENABLE_MOCK_LOGIN", "true")
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
            ) as session:
                current = resolve_identity(
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

                invitation = UserInvitation(
                    email=f"mock-audit-{uuid.uuid4().hex}@example.org",
                    role="viewer",
                    account_type="research",
                    status="pending",
                    expires_at=(
                        datetime.now(timezone.utc) + timedelta(minutes=5)
                    ),
                    invited_by_user_id=current.id,
                )
                session.add(invitation)
                session.flush()
                session.add(
                    AuditEvent(
                        actor_user_id=current.id,
                        action="integration.mock_audit",
                        target_type="invitation",
                        target_id=str(invitation.id),
                    )
                )
                session.commit()

                user = session.get(AppUser, current.id)
                assert user is not None
                assert user.auth_provider == "mock-credentials"
                assert session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.action == "integration.mock_audit",
                        AuditEvent.actor_user_id == current.id,
                    )
                ) is not None

                user.status = "suspended"
                session.commit()
                with pytest.raises(AuthenticationFailure, match="suspended"):
                    resolve_identity(
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
        finally:
            if transaction.is_active:
                transaction.rollback()
