"""Application metadata models.

These tables are intentionally isolated from the scientific corpus metadata in
``db.models``. Corpus rebuilds may replace derived data, but must never erase
users, invitations, chat records, feedback, or security audit events.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class AppBase(DeclarativeBase):
    pass


class AppUser(AppBase):
    __tablename__ = "app_user"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auth_provider = Column(String(64), nullable=False)
    auth_subject = Column(String(255), nullable=False)
    email = Column(String(320), nullable=False, unique=True, index=True)
    display_name = Column(String(255))
    role = Column(String(32), nullable=False, default="viewer")
    account_type = Column(String(32), nullable=False, default="research")
    status = Column(String(32), nullable=False, default="active")
    invited_by_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_login_at = Column(DateTime(timezone=True))

    invited_by = relationship("AppUser", remote_side=[id])

    __table_args__ = (
        UniqueConstraint(
            "auth_provider",
            "auth_subject",
            name="uq_app_user_provider_subject",
        ),
        CheckConstraint(
            "role IN ('viewer', 'researcher', 'admin')",
            name="ck_app_user_role",
        ),
        CheckConstraint(
            "account_type IN ('research', 'commercial', 'internal')",
            name="ck_app_user_account_type",
        ),
        CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_app_user_status",
        ),
    )


class UserInvitation(AppBase):
    __tablename__ = "user_invitation"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), nullable=False, unique=True, index=True)
    role = Column(String(32), nullable=False, default="viewer")
    account_type = Column(String(32), nullable=False, default="research")
    status = Column(String(32), nullable=False, default="pending")
    invited_by_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    invited_by = relationship("AppUser")

    __table_args__ = (
        CheckConstraint(
            "role IN ('viewer', 'researcher', 'admin')",
            name="ck_user_invitation_role",
        ),
        CheckConstraint(
            "account_type IN ('research', 'commercial', 'internal')",
            name="ck_user_invitation_account_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_user_invitation_status",
        ),
    )


class ChatInteraction(AppBase):
    __tablename__ = "chat_interaction"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status = Column(String(32), nullable=False, default="running")
    query = Column(Text, nullable=False)
    answer = Column(Text)
    model = Column(String(255))
    request_options = Column(JSON, nullable=False, default=dict)
    evidence_snapshot = Column(JSON, nullable=False, default=dict)
    answer_audit_snapshot = Column(JSON)
    corpus_fingerprint = Column(String(128))
    prompt_version = Column(String(64))
    prompt_sha256 = Column(String(64))
    latency_ms = Column(Integer)
    error_code = Column(String(64))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    user = relationship("AppUser")
    feedback = relationship(
        "ChatFeedback",
        back_populates="interaction",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_chat_interaction_status",
        ),
    )


class ChatFeedback(AppBase):
    __tablename__ = "chat_feedback"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interaction_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("chat_interaction.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rating = Column(Integer, nullable=False)
    reason_codes = Column(JSON, nullable=False, default=list)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    interaction = relationship("ChatInteraction", back_populates="feedback")
    user = relationship("AppUser")

    __table_args__ = (
        UniqueConstraint(
            "interaction_id",
            "user_id",
            name="uq_chat_feedback_interaction_user",
        ),
        CheckConstraint("rating IN (-1, 1)", name="ck_chat_feedback_rating"),
    )


class AuditEvent(AppBase):
    __tablename__ = "audit_event"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = Column(String(128), nullable=False, index=True)
    target_type = Column(String(64))
    target_id = Column(String(255))
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    actor = relationship("AppUser")

    __table_args__ = (
        Index("ix_audit_event_created_at", "created_at"),
    )


class RateLimitBucket(AppBase):
    """Shared fixed-window request counters for multi-worker deployments."""

    __tablename__ = "rate_limit_bucket"

    scope = Column(String(64), primary_key=True)
    subject_hash = Column(String(64), primary_key=True)
    window_started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    request_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "request_count >= 0",
            name="ck_rate_limit_bucket_request_count",
        ),
        Index("ix_rate_limit_bucket_updated_at", "updated_at"),
    )
