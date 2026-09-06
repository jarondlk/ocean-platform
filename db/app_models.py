"""Application metadata models.

These tables are intentionally isolated from the scientific corpus metadata in
``db.models``. Corpus rebuilds may replace derived data, but must never erase
users, invitations, chat records, feedback, or security audit events.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
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
    event,
    func,
    text,
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
    outcome = Column(String(32))
    abstention_reason = Column(String(64))
    request_options = Column(JSON, nullable=False, default=dict)
    evidence_snapshot = Column(JSON, nullable=False, default=dict)
    answer_audit_snapshot = Column(JSON)
    corpus_fingerprint = Column(String(128))
    prompt_version = Column(String(64))
    prompt_sha256 = Column(String(64))
    latency_ms = Column(Integer)
    error_code = Column(String(64))
    legal_hold = Column(Boolean, nullable=False, default=False, server_default="false")
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
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('answered', 'abstained')",
            name="ck_chat_interaction_outcome",
        ),
        CheckConstraint(
            "abstention_reason IS NULL OR abstention_reason IN "
            "('no_matching_evidence', 'empty_analysis_cohort', "
            "'publication_pending')",
            name="ck_chat_interaction_abstention_reason",
        ),
        CheckConstraint(
            "(outcome IS NULL AND abstention_reason IS NULL) OR "
            "(outcome = 'answered' AND abstention_reason IS NULL) OR "
            "(outcome = 'abstained' AND abstention_reason IS NOT NULL)",
            name="ck_chat_interaction_outcome_reason",
        ),
        Index("ix_chat_interaction_retention", "created_at", "legal_hold", "status"),
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


class ClassificationReview(AppBase):
    """Current state of one authenticated scientific classification review."""

    __tablename__ = "classification_review"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_snapshot_id = Column(String(64), nullable=False, index=True)
    sample_id = Column(String(64), nullable=False, index=True)
    provider_sample_id = Column(Text, nullable=False)
    sample_kind = Column(String(32), nullable=False)
    rationale = Column(Text, nullable=False)
    evidence_json = Column(JSON, nullable=False)
    content_sha256 = Column(String(64), nullable=False, index=True)
    state = Column(String(32), nullable=False, default="draft", index=True)
    version = Column(Integer, nullable=False, default=1)
    supersedes_review_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("classification_review.id", ondelete="RESTRICT"),
    )
    created_by_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    scientific_decided_by_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        index=True,
    )
    scientific_decided_at = Column(DateTime(timezone=True))
    operational_actor_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        index=True,
    )
    operational_at = Column(DateTime(timezone=True))
    application_reference = Column(Text)
    failure_code = Column(String(64))
    failure_detail = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "sample_kind IN ('environmental', 'negative_control', "
            "'positive_control', 'mock_community', 'unknown')",
            name="ck_classification_review_sample_kind",
        ),
        CheckConstraint(
            "state IN ('draft', 'approved', 'rejected', 'superseded', "
            "'applied', 'failed')",
            name="ck_classification_review_state",
        ),
        CheckConstraint("version >= 1", name="ck_classification_review_version"),
        CheckConstraint(
            "(state IN ('approved', 'rejected', 'superseded', 'applied', 'failed') "
            "AND scientific_decided_by_user_id IS NOT NULL "
            "AND scientific_decided_at IS NOT NULL) OR state = 'draft'",
            name="ck_classification_review_scientific_decision",
        ),
        CheckConstraint(
            "(state = 'applied' AND operational_actor_user_id IS NOT NULL "
            "AND operational_at IS NOT NULL AND application_reference IS NOT NULL "
            "AND failure_code IS NULL) OR state <> 'applied'",
            name="ck_classification_review_applied",
        ),
        CheckConstraint(
            "(state = 'failed' AND operational_actor_user_id IS NOT NULL "
            "AND operational_at IS NOT NULL AND failure_code IS NOT NULL) "
            "OR state <> 'failed'",
            name="ck_classification_review_failed",
        ),
        Index(
            "uq_classification_review_current_sample",
            "sample_id",
            unique=True,
            postgresql_where=text(
                "state IN ('approved', 'applied', 'failed')"
            ),
            sqlite_where=text(
                "state IN ('approved', 'applied', 'failed')"
            ),
        ),
    )


class ClassificationReviewEvent(AppBase):
    """Immutable transition record for a classification review."""

    __tablename__ = "classification_review_event"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("classification_review.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(32), nullable=False)
    from_state = Column(String(32))
    to_state = Column(String(32), nullable=False)
    actor_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_role = Column(String(32), nullable=False)
    actor_identity_json = Column(JSON, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    event_sha256 = Column(String(64), nullable=False)
    review_snapshot_json = Column(JSON, nullable=False)
    details_json = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "review_id",
            "sequence",
            name="uq_classification_review_event_sequence",
        ),
        CheckConstraint(
            "event_type IN ('created', 'draft_updated', 'approved', "
            "'rejected', 'superseded', 'applied', 'failed')",
            name="ck_classification_review_event_type",
        ),
        CheckConstraint(
            "to_state IN ('draft', 'approved', 'rejected', 'superseded', "
            "'applied', 'failed')",
            name="ck_classification_review_event_state",
        ),
        CheckConstraint(
            "actor_role IN ('researcher', 'admin')",
            name="ck_classification_review_event_actor_role",
        ),
        CheckConstraint(
            "(event_type IN ('created', 'draft_updated', 'approved', "
            "'rejected', 'superseded') AND actor_role = 'researcher') OR "
            "(event_type IN ('applied', 'failed') AND actor_role = 'admin')",
            name="ck_classification_review_event_role",
        ),
        CheckConstraint(
            "(event_type = 'created' AND from_state IS NULL "
            "AND to_state = 'draft') OR "
            "(event_type = 'draft_updated' AND from_state = 'draft' "
            "AND to_state = 'draft') OR "
            "(event_type IN ('approved', 'rejected') "
            "AND from_state = 'draft' AND to_state = event_type) OR "
            "(event_type = 'superseded' "
            "AND from_state IN ('approved', 'applied', 'failed') "
            "AND to_state = 'superseded') OR "
            "(event_type IN ('applied', 'failed') "
            "AND from_state IN ('approved', 'failed') "
            "AND to_state = event_type)",
            name="ck_classification_review_event_transition",
        ),
        CheckConstraint(
            "sequence >= 1",
            name="ck_classification_review_event_sequence",
        ),
    )


@event.listens_for(ClassificationReviewEvent, "before_update")
@event.listens_for(ClassificationReviewEvent, "before_delete")
def _classification_review_event_is_append_only(*_args) -> None:
    raise ValueError("Classification review events are append-only")


class ClassificationApplication(AppBase):
    """Durable state for one manually launched review application."""

    __tablename__ = "classification_application"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_id = Column(String(100), nullable=False, unique=True, index=True)
    review_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("classification_review.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    review_version = Column(Integer, nullable=False)
    review_content_sha256 = Column(String(64), nullable=False)
    source_snapshot_id = Column(String(64), nullable=False)
    sample_id = Column(String(64), nullable=False, index=True)
    mode = Column(String(16), nullable=False)
    rollback_of_application_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("classification_application.id", ondelete="RESTRICT"),
    )
    actor_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_identity_json = Column(JSON, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    current_stage = Column(String(32))
    completed_stages_json = Column(JSON, nullable=False, default=list)
    artifacts_json = Column(JSON, nullable=False, default=dict)
    results_json = Column(JSON, nullable=False, default=dict)
    error_code = Column(String(64))
    recovery_json = Column(JSON, nullable=False, default=list)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "mode IN ('apply', 'rollback')",
            name="ck_classification_application_mode",
        ),
        CheckConstraint(
            "review_version >= 1",
            name="ck_classification_application_review_version",
        ),
        CheckConstraint(
            "status IN ('running', 'failed', 'applied', 'rolled_back')",
            name="ck_classification_application_status",
        ),
        CheckConstraint(
            "current_stage IS NULL OR current_stage IN ("
            "'register_review', 'normalize', 'import', 'materialize', "
            "'analyze', 'embed', 'provenance', 'finalize')",
            name="ck_classification_application_current_stage",
        ),
        CheckConstraint(
            "(mode = 'rollback' AND rollback_of_application_id IS NOT NULL) "
            "OR (mode = 'apply' AND rollback_of_application_id IS NULL)",
            name="ck_classification_application_rollback_target",
        ),
        CheckConstraint(
            "(status IN ('applied', 'rolled_back') AND finished_at IS NOT NULL "
            "AND error_code IS NULL) OR status NOT IN ('applied', 'rolled_back')",
            name="ck_classification_application_completion",
        ),
        CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL "
            "AND current_stage IS NOT NULL) OR status <> 'failed'",
            name="ck_classification_application_failure",
        ),
        Index(
            "uq_classification_application_running_review",
            "review_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )


class ClassificationApplicationEvent(AppBase):
    """Append-only stage and lifecycle receipt for an application run."""

    __tablename__ = "classification_application_event"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("classification_application.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(32), nullable=False)
    stage = Column(String(32))
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    result_json = Column(JSON, nullable=False, default=dict)
    error_code = Column(String(64))
    recovery_json = Column(JSON, nullable=False, default=list)
    event_sha256 = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "application_id",
            "sequence",
            name="uq_classification_application_event_sequence",
        ),
        CheckConstraint(
            "event_type IN ('run_started', 'run_resumed', 'stage_started', "
            "'stage_completed', 'stage_failed', 'run_applied', "
            "'run_rolled_back', 'run_failed')",
            name="ck_classification_application_event_type",
        ),
        CheckConstraint(
            "stage IS NULL OR stage IN ("
            "'register_review', 'normalize', 'import', 'materialize', "
            "'analyze', 'embed', 'provenance', 'finalize')",
            name="ck_classification_application_event_stage",
        ),
        CheckConstraint(
            "(event_type IN ('run_started', 'run_resumed', 'run_applied', "
            "'run_rolled_back') AND stage IS NULL) OR "
            "(event_type IN ('stage_started', 'stage_completed', "
            "'stage_failed', 'run_failed') AND stage IS NOT NULL)",
            name="ck_classification_application_event_stage_shape",
        ),
        CheckConstraint(
            "sequence >= 1",
            name="ck_classification_application_event_sequence",
        ),
    )


@event.listens_for(ClassificationApplicationEvent, "before_update")
@event.listens_for(ClassificationApplicationEvent, "before_delete")
def _classification_application_event_is_append_only(*_args) -> None:
    raise ValueError("Classification application events are append-only")


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
