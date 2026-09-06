from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import DBAPIError
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
        "classification_review",
        "classification_review_event",
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


def test_classification_review_events_are_database_append_only():
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    user_id = uuid.uuid4()
    review_id = uuid.uuid4()
    event_id = uuid.uuid4()
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                text(
                    """
                    INSERT INTO app_user (
                        id, auth_provider, auth_subject, email, role,
                        account_type, status
                    ) VALUES (
                        :user_id, 'oidc', :subject, :email, 'researcher',
                        'research', 'active'
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "subject": f"append-only-{user_id}",
                    "email": f"append-only-{user_id}@example.org",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO classification_review (
                        id, source_snapshot_id, sample_id, provider_sample_id,
                        sample_kind, rationale, evidence_json, content_sha256,
                        state, version, created_by_user_id
                    ) VALUES (
                        :review_id, :snapshot_id, :sample_id, 'sample',
                        'unknown', 'Evidence is inconclusive.',
                        CAST(:evidence AS json), :content_sha256,
                        'draft', 1, :user_id
                    )
                    """
                ),
                {
                    "review_id": review_id,
                    "snapshot_id": "1" * 64,
                    "sample_id": "2" * 64,
                    "evidence": "[]",
                    "content_sha256": "3" * 64,
                    "user_id": user_id,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO classification_review_event (
                        id, review_id, sequence, event_type, from_state,
                        to_state, actor_user_id, actor_role,
                        actor_identity_json, occurred_at, content_sha256,
                        event_sha256, review_snapshot_json, details_json
                    ) VALUES (
                        :event_id, :review_id, 1, 'created', NULL,
                        'draft', :user_id, 'researcher',
                        CAST(:identity AS json), CURRENT_TIMESTAMP,
                        :content_sha256, :event_sha256,
                        CAST(:snapshot AS json), CAST(:details AS json)
                    )
                    """
                ),
                {
                    "event_id": event_id,
                    "review_id": review_id,
                    "user_id": user_id,
                    "identity": "{}",
                    "content_sha256": "3" * 64,
                    "event_sha256": "4" * 64,
                    "snapshot": "{}",
                    "details": "{}",
                },
            )

            for mutation in (
                "UPDATE classification_review_event "
                "SET details_json = '{}' WHERE id = :event_id",
                "DELETE FROM classification_review_event WHERE id = :event_id",
            ):
                savepoint = connection.begin_nested()
                with pytest.raises(DBAPIError, match="append-only"):
                    connection.execute(text(mutation), {"event_id": event_id})
                savepoint.rollback()
        finally:
            transaction.rollback()
