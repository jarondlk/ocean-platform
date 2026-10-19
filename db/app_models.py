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
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class AppBase(DeclarativeBase):
    pass


class EdnaAggregateEvidence(AppBase):
    """Immutable chat evidence survives scientific corpus rebuilds."""
    __tablename__ = "edna_aggregate_evidence"
    aggregate_id = Column(String(64), primary_key=True)
    algorithm_version = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


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
            "'publication_pending', 'aggregate_scope_required', 'aggregate_unavailable', 'no_sources_selected', 'source_disabled', 'freshness_unavailable', 'incomplete_source_coverage', 'overlap_unverified')",
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


class ResearchRegistryReview(AppBase):
    """Human scientific approval is independent of operational application."""
    __tablename__ = "research_registry_review"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind = Column(String(32), nullable=False)
    registry_key = Column(String(255), nullable=False, index=True)
    definition_json = Column(JSON, nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    state = Column(String(16), nullable=False, default="draft")
    version = Column(Integer, nullable=False, default=1)
    created_by_user_id = Column(Uuid(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)
    decided_by_user_id = Column(Uuid(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"))
    applied_by_user_id = Column(Uuid(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("kind IN ('sampling', 'sst_product')", name="ck_research_registry_review_kind"),
        CheckConstraint("state IN ('draft', 'approved', 'rejected', 'applied')", name="ck_research_registry_review_state"),
        CheckConstraint("version >= 1", name="ck_research_registry_review_version"),
        CheckConstraint("state = 'draft' OR decided_by_user_id IS NOT NULL", name="ck_research_registry_review_decided"),
        CheckConstraint("state <> 'applied' OR applied_by_user_id IS NOT NULL", name="ck_research_registry_review_applied"),
    )


class ResearchRegistryEvent(AppBase):
    __tablename__ = "research_registry_event"
    review_id = Column(Uuid(as_uuid=True), ForeignKey("research_registry_review.id", ondelete="RESTRICT"), primary_key=True)
    sequence = Column(Integer, primary_key=True)
    event_sha256 = Column(String(64), nullable=False, unique=True)
    payload_json = Column(JSON, nullable=False)
    __table_args__ = (CheckConstraint("sequence >= 1", name="ck_research_registry_event_sequence"),)


class ResearchRegistryVersion(AppBase):
    """Immutable evidence ledger survives canonical refreshes and corpus rebuilds."""
    __tablename__ = "research_registry_version"
    registry_id = Column(String(64), primary_key=True)
    review_id = Column(Uuid(as_uuid=True), ForeignKey("research_registry_review.id", ondelete="RESTRICT"), nullable=False, unique=True)
    registry_key = Column(String(255), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)


class ResearchRegistryHead(AppBase):
    __tablename__ = "research_registry_head"
    registry_key = Column(String(255), primary_key=True)
    registry_id = Column(String(64), ForeignKey("research_registry_version.registry_id", ondelete="RESTRICT"), nullable=False)


class ResearchPhysicalMembership(AppBase):
    __tablename__ = "research_physical_membership"
    registry_id = Column(String(64), ForeignKey("research_registry_version.registry_id", ondelete="RESTRICT"), primary_key=True)
    sample_id = Column(String(64), primary_key=True)
    physical_sample_id = Column(String(64), nullable=False, index=True)
    scientific_content_sha256 = Column(String(64), nullable=False)
    representative_assay_id = Column(String(64), nullable=False)
    representative_assay_sha256 = Column(String(64), nullable=False)
    area_id = Column(String(255), nullable=False)
    area_version = Column(String(64), nullable=False)


class ResearchAreaDefinition(AppBase):
    __tablename__ = "research_area_definition"
    registry_id = Column(String(64), ForeignKey("research_registry_version.registry_id", ondelete="RESTRICT"), primary_key=True)
    area_id = Column(String(255), primary_key=True)
    area_version = Column(String(64), nullable=False)
    definition_json = Column(JSON, nullable=False)


def _research_record_is_immutable(*_args):
    raise ValueError("Research evidence records are immutable")


for _research_model in (ResearchRegistryEvent, ResearchRegistryVersion, ResearchPhysicalMembership, ResearchAreaDefinition):
    event.listen(_research_model, "before_update", _research_record_is_immutable)
    event.listen(_research_model, "before_delete", _research_record_is_immutable)


def _context_sha256_check(column: str) -> str:
    """Portable exact lowercase hex check for application metadata fixtures."""
    remaining = column
    for character in "0123456789abcdef":
        remaining = f"replace({remaining}, '{character}', '')"
    return f"length({column}) = 64 AND {remaining} = ''"


class ResearchInvestigation(AppBase):
    """Private v1 context head; retirement preserves its immutable evidence."""

    __tablename__ = "research_investigation"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    metadata_version = Column(Integer, nullable=False, default=1)
    status = Column(String(16), nullable=False, default="preparing")
    head_revision_id = Column(Uuid(as_uuid=True))
    predecessor_investigation_id = Column(Uuid(as_uuid=True))
    predecessor_revision_id = Column(Uuid(as_uuid=True))
    legal_hold = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    retired_at = Column(DateTime(timezone=True))

    __mapper_args__ = {"version_id_col": metadata_version}
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_research_investigation_owner"),
        CheckConstraint("length(name) BETWEEN 1 AND 255 AND length(trim(name)) >= 1", name="ck_research_investigation_name"),
        CheckConstraint("metadata_version >= 1", name="ck_research_investigation_version"),
        CheckConstraint("status IN ('preparing', 'active', 'archived', 'retired')", name="ck_research_investigation_status"),
        CheckConstraint(
            "(predecessor_investigation_id IS NULL AND predecessor_revision_id IS NULL) OR "
            "(predecessor_investigation_id IS NOT NULL AND predecessor_revision_id IS NOT NULL)",
            name="ck_research_investigation_predecessor_pair",
        ),
        CheckConstraint("predecessor_investigation_id IS NULL OR predecessor_investigation_id <> id", name="ck_research_investigation_predecessor_other"),
        ForeignKeyConstraint(
            ["id", "head_revision_id"],
            ["research_context_revision.investigation_id", "research_context_revision.id"],
            name="fk_research_investigation_head", ondelete="RESTRICT",
            deferrable=True, initially="DEFERRED", use_alter=True,
        ),
        ForeignKeyConstraint(
            ["predecessor_investigation_id", "user_id"],
            ["research_investigation.id", "research_investigation.user_id"],
            name="fk_research_investigation_predecessor_owner", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["predecessor_investigation_id", "predecessor_revision_id"],
            ["research_context_revision.investigation_id", "research_context_revision.id"],
            name="fk_research_investigation_predecessor_revision", ondelete="RESTRICT",
            deferrable=True, initially="DEFERRED", use_alter=True,
        ),
        Index("ix_research_investigation_retention", "updated_at", "legal_hold", "status"),
    )


class ResearchConversation(AppBase):
    """Conversation identity shares investigation context, never other narratives."""

    __tablename__ = "research_conversation"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id = Column(Uuid(as_uuid=True), ForeignKey("research_investigation.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    metadata_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __mapper_args__ = {"version_id_col": metadata_version}
    __table_args__ = (
        UniqueConstraint("investigation_id", "id", name="uq_research_conversation_identity"),
        CheckConstraint("length(name) BETWEEN 1 AND 255 AND length(trim(name)) >= 1", name="ck_research_conversation_name"),
        CheckConstraint("metadata_version >= 1", name="ck_research_conversation_version"),
    )


class ResearchContextRevision(AppBase):
    """Append-only canonical selected context and snapshot identity."""

    __tablename__ = "research_context_revision"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id = Column(Uuid(as_uuid=True), ForeignKey("research_investigation.id", ondelete="RESTRICT"), nullable=False)
    sequence = Column(Integer, nullable=False)
    predecessor_revision_id = Column(Uuid(as_uuid=True))
    snapshot_id = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    created_by_user_id = Column(Uuid(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("investigation_id", "sequence", name="uq_research_context_revision_sequence"),
        UniqueConstraint("investigation_id", "id", name="uq_research_context_revision_identity"),
        UniqueConstraint("investigation_id", "id", "snapshot_id", "payload_sha256", name="uq_research_context_revision_binding"),
        CheckConstraint("sequence >= 1", name="ck_research_context_revision_sequence"),
        CheckConstraint(_context_sha256_check("snapshot_id"), name="ck_research_context_revision_snapshot"),
        CheckConstraint(_context_sha256_check("payload_sha256"), name="ck_research_context_revision_payload_hash"),
        CheckConstraint("predecessor_revision_id IS NULL OR predecessor_revision_id <> id", name="ck_research_context_revision_predecessor_other"),
        ForeignKeyConstraint(
            ["investigation_id", "created_by_user_id"],
            ["research_investigation.id", "research_investigation.user_id"],
            name="fk_research_context_revision_owner", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["investigation_id", "predecessor_revision_id"],
            ["research_context_revision.investigation_id", "research_context_revision.id"],
            name="fk_research_context_revision_predecessor", ondelete="RESTRICT",
        ),
    )


class ResearchContextOperation(AppBase):
    """Durable immutable preparation inputs; only delivery state can advance."""

    __tablename__ = "research_context_operation"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)
    investigation_id = Column(Uuid(as_uuid=True), ForeignKey("research_investigation.id", ondelete="RESTRICT"), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False)
    kind = Column(String(32), nullable=False)
    expected_head_id = Column(Uuid(as_uuid=True))
    # A prepared candidate reserves its UUID before the immutable revision exists.
    candidate_revision_id = Column(Uuid(as_uuid=True))
    request_json = Column(Text, nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    candidate_json = Column(Text, nullable=False)
    references_json = Column(Text, nullable=False)
    state = Column(String(16), nullable=False, default="prepared")
    error_code = Column(String(64))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_research_context_operation_idempotency"),
        CheckConstraint("length(idempotency_key) BETWEEN 1 AND 128", name="ck_research_context_operation_key"),
        CheckConstraint("length(kind) BETWEEN 1 AND 32", name="ck_research_context_operation_kind"),
        CheckConstraint(_context_sha256_check("request_sha256"), name="ck_research_context_operation_request_hash"),
        CheckConstraint("state IN ('prepared', 'committed', 'conflict', 'unavailable', 'uncertain')", name="ck_research_context_operation_state"),
        CheckConstraint("error_code IS NULL OR length(error_code) BETWEEN 1 AND 64", name="ck_research_context_operation_error"),
        ForeignKeyConstraint(
            ["investigation_id", "user_id"],
            ["research_investigation.id", "research_investigation.user_id"],
            name="fk_research_context_operation_owner", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["investigation_id", "expected_head_id"],
            ["research_context_revision.investigation_id", "research_context_revision.id"],
            name="fk_research_context_operation_expected_head", ondelete="RESTRICT",
        ),
    )


_CONTEXT_IMMUTABLE_COLUMNS = {
    ResearchInvestigation: ("id", "user_id", "predecessor_investigation_id", "predecessor_revision_id", "created_at"),
    ResearchConversation: ("id", "investigation_id", "created_at"),
    ResearchContextOperation: (
        "id", "user_id", "investigation_id", "idempotency_key", "kind",
        "expected_head_id", "candidate_revision_id", "request_json", "request_sha256",
        "candidate_json", "references_json", "created_at",
    ),
}


def _research_context_identity_is_immutable(_mapper, _connection, target):
    state = inspect(target)
    if any(state.attrs[column].history.has_changes() for column in _CONTEXT_IMMUTABLE_COLUMNS[type(target)]):
        raise ValueError("Research context identity and prepared inputs are immutable")


for _context_model in (ResearchInvestigation, ResearchConversation, ResearchContextOperation):
    event.listen(_context_model, "before_update", _research_context_identity_is_immutable)
    event.listen(_context_model, "before_delete", _research_record_is_immutable)
event.listen(ResearchContextRevision, "before_update", _research_record_is_immutable)
event.listen(ResearchContextRevision, "before_delete", _research_record_is_immutable)


class ResearchRun(AppBase):
    """C20 private execution head; frozen context and original input never move."""

    __tablename__ = "research_run"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    investigation_id = Column(Uuid(as_uuid=True), nullable=False)
    conversation_id = Column(Uuid(as_uuid=True), nullable=False)
    revision_id = Column(Uuid(as_uuid=True), nullable=False)
    snapshot_id = Column(String(64), nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    context_json = Column(Text, nullable=False)
    original_question = Column(Text, nullable=False)
    effective_question = Column(Text, nullable=False)
    continuation_of = Column(Uuid(as_uuid=True))
    status = Column(String(32), nullable=False, default="queued")
    version = Column(Integer, nullable=False, default=1)
    input_version = Column(Integer, nullable=False, default=1)
    clarification_id = Column(Uuid(as_uuid=True))
    event_cursor = Column(Integer, nullable=False, default=0)
    active_elapsed_ms = Column(Integer, nullable=False, default=0)
    tool_actions = Column(Integer, nullable=False, default=0)
    model_calls = Column(Integer, nullable=False, default=0)
    malformed_repairs = Column(Integer, nullable=False, default=0)
    lease_epoch = Column(Integer, nullable=False, default=0)
    lease_until = Column(DateTime(timezone=True))
    active_started_at = Column(DateTime(timezone=True))
    cancellation_requested = Column(Boolean, nullable=False, default=False)
    checkpoint_json = Column(Text, nullable=False, default="{}")
    manifest_json = Column(Text)
    controller_result_json = Column(Text)
    reason_code = Column(String(64))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_research_run_owner"),
        UniqueConstraint("id", "investigation_id", "conversation_id", "revision_id", name="uq_research_run_binding"),
        ForeignKeyConstraint(["investigation_id", "user_id"], ["research_investigation.id", "research_investigation.user_id"], ondelete="RESTRICT", name="fk_research_run_owner"),
        ForeignKeyConstraint(["investigation_id", "conversation_id"], ["research_conversation.investigation_id", "research_conversation.id"], ondelete="RESTRICT", name="fk_research_run_conversation"),
        ForeignKeyConstraint(["investigation_id", "revision_id", "snapshot_id", "payload_sha256"], ["research_context_revision.investigation_id", "research_context_revision.id", "research_context_revision.snapshot_id", "research_context_revision.payload_sha256"], ondelete="RESTRICT", name="fk_research_run_revision"),
        ForeignKeyConstraint(["continuation_of", "user_id"], ["research_run.id", "research_run.user_id"], ondelete="RESTRICT", name="fk_research_run_continuation_owner"),
        ForeignKeyConstraint(["continuation_of", "investigation_id", "conversation_id", "revision_id"], ["research_run.id", "research_run.investigation_id", "research_run.conversation_id", "research_run.revision_id"], ondelete="RESTRICT", name="fk_research_run_continuation_binding"),
        CheckConstraint("status IN ('queued','running','awaiting_clarification','awaiting_approval','completed','partial','cancelled','failed')", name="ck_research_run_status"),
        CheckConstraint("version >= 1 AND input_version >= 1 AND event_cursor >= 0 AND lease_epoch >= 0", name="ck_research_run_versions"),
        CheckConstraint("active_elapsed_ms >= 0 AND tool_actions BETWEEN 0 AND 12 AND model_calls BETWEEN 0 AND 14 AND malformed_repairs BETWEEN 0 AND 1", name="ck_research_run_budget"),
        CheckConstraint("length(original_question) BETWEEN 1 AND 8000 AND length(effective_question) BETWEEN 1 AND 8000", name="ck_research_run_question"),
        CheckConstraint(_context_sha256_check("snapshot_id"), name="ck_research_run_snapshot"),
        CheckConstraint(_context_sha256_check("payload_sha256"), name="ck_research_run_payload_hash"),
        CheckConstraint("continuation_of IS NULL OR continuation_of <> id", name="ck_research_run_continuation_other"),
        Index("ix_research_run_conversation", "user_id", "investigation_id", "conversation_id", "created_at", "id"),
    )


class ResearchRunInputHistory(AppBase):
    __tablename__ = "research_run_input_history"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    run_id = Column(Uuid(as_uuid=True), nullable=False)
    sequence = Column(Integer, nullable=False)
    kind = Column(String(16), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_json = Column(Text, nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    effective_question = Column(Text, nullable=False)
    result_run_id = Column(Uuid(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_research_run_input_key"),
        UniqueConstraint("run_id", "sequence", name="uq_research_run_input_sequence"),
        ForeignKeyConstraint(["run_id", "user_id"], ["research_run.id", "research_run.user_id"], ondelete="RESTRICT", name="fk_research_run_input_owner"),
        ForeignKeyConstraint(["result_run_id", "user_id"], ["research_run.id", "research_run.user_id"], ondelete="RESTRICT", name="fk_research_run_input_result_owner"),
        CheckConstraint("sequence >= 1 AND kind IN ('submit','clarify','continue','cancel')", name="ck_research_run_input_kind"),
        CheckConstraint(_context_sha256_check("request_sha256"), name="ck_research_run_input_hash"),
    )


class ResearchRunEvent(AppBase):
    __tablename__ = "research_run_event"
    run_id = Column(Uuid(as_uuid=True), ForeignKey("research_run.id", ondelete="RESTRICT"), primary_key=True)
    cursor = Column(Integer, primary_key=True)
    kind = Column(String(32), nullable=False)
    elapsed_ms = Column(Integer, nullable=False)
    summary_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (CheckConstraint("cursor >= 1 AND elapsed_ms >= 0", name="ck_research_run_event_cursor"),)


class ResearchRunPayload(AppBase):
    __tablename__ = "research_run_payload"
    run_id = Column(Uuid(as_uuid=True), ForeignKey("research_run.id", ondelete="RESTRICT"), primary_key=True)
    sha256 = Column(String(64), primary_key=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (CheckConstraint(_context_sha256_check("sha256"), name="ck_research_run_retained_hash"),)


class ResearchRunStep(AppBase):
    __tablename__ = "research_run_step"
    run_id = Column(Uuid(as_uuid=True), ForeignKey("research_run.id", ondelete="RESTRICT"), primary_key=True)
    step_id = Column(String(255), primary_key=True)
    kind = Column(String(16), nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    request_json = Column(Text, nullable=False)
    outcome_sha256 = Column(String(64))
    state = Column(String(16), nullable=False, default="prepared")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["run_id", "outcome_sha256"], ["research_run_payload.run_id", "research_run_payload.sha256"], ondelete="RESTRICT", name="fk_research_run_step_payload"),
        CheckConstraint("kind IN ('tool','model','repair')", name="ck_research_run_step_kind"),
        CheckConstraint("(state = 'prepared' AND outcome_sha256 IS NULL) OR (state = 'committed' AND outcome_sha256 IS NOT NULL)", name="ck_research_run_step_state"),
        CheckConstraint(_context_sha256_check("request_sha256"), name="ck_research_run_step_hash"),
    )


class ResearchRunAttempt(AppBase):
    """Append-only physical reservations; uncertain calls never become free."""
    __tablename__ = "research_run_attempt"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(Uuid(as_uuid=True), nullable=False)
    step_id = Column(String(255), nullable=False)
    ordinal = Column(Integer, nullable=False)
    lease_epoch = Column(Integer, nullable=False)
    budget_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("run_id", "step_id", "ordinal", name="uq_research_run_attempt_ordinal"),
        ForeignKeyConstraint(["run_id", "step_id"], ["research_run_step.run_id", "research_run_step.step_id"], ondelete="RESTRICT", name="fk_research_run_attempt_step"),
        CheckConstraint("ordinal >= 1 AND lease_epoch >= 1", name="ck_research_run_attempt_version"),
    )


class ResearchRunManifest(AppBase):
    __tablename__ = "research_run_manifest"
    run_id = Column(Uuid(as_uuid=True), ForeignKey("research_run.id", ondelete="RESTRICT"), primary_key=True)
    input_version = Column(Integer, primary_key=True)
    manifest_json = Column(Text, nullable=False)
    manifest_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("input_version >= 1", name="ck_research_run_manifest_version"),
        CheckConstraint(_context_sha256_check("manifest_sha256"), name="ck_research_run_manifest_hash"),
    )


class ResearchRunOutbox(AppBase):
    __tablename__ = "research_run_outbox"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(Uuid(as_uuid=True), ForeignKey("research_run.id", ondelete="RESTRICT"), nullable=False)
    input_version = Column(Integer, nullable=False)
    delivery_id = Column(Uuid(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4)
    state = Column(String(16), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sent_at = Column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("run_id", "input_version", name="uq_research_run_outbox_input"),
        CheckConstraint("input_version >= 1 AND attempts >= 0 AND state IN ('pending','sent')", name="ck_research_run_outbox_state"),
    )


_RUN_IMMUTABLE_COLUMNS = {
    ResearchRun: ("id", "user_id", "investigation_id", "conversation_id", "revision_id", "snapshot_id", "payload_sha256", "context_json", "original_question", "continuation_of", "created_at"),
    ResearchRunStep: ("run_id", "step_id", "kind", "request_sha256", "request_json", "created_at"),
    ResearchRunOutbox: ("id", "run_id", "input_version", "delivery_id", "created_at"),
}


def _research_run_update_guard(_mapper, _connection, target):
    state = inspect(target)
    if any(state.attrs[column].history.has_changes() for column in _RUN_IMMUTABLE_COLUMNS[type(target)]):
        raise ValueError("Research run identity and prepared requests are immutable")
    if isinstance(target, ResearchRunStep) and (state.attrs.state.history.deleted == ["committed"] or (target.state == "committed" and not state.attrs.state.history.has_changes())):
        raise ValueError("Committed research steps are immutable")
    if isinstance(target, ResearchRun) and state.attrs.manifest_json.history.deleted and state.attrs.manifest_json.history.deleted[0] is not None:
        raise ValueError("Research run execution manifest is immutable")
    if isinstance(target, ResearchRun):
        for column in ("version", "input_version", "event_cursor", "active_elapsed_ms", "tool_actions", "model_calls", "malformed_repairs", "lease_epoch"):
            history = state.attrs[column].history
            if history.deleted and getattr(target, column) < history.deleted[0]:
                raise ValueError("Research run counters are monotonic")
        old_status = state.attrs.status.history.deleted
        previous = old_status[0] if old_status else target.status
        if previous in {"completed", "partial", "cancelled", "failed"} and any(item.history.has_changes() for item in state.attrs):
            raise ValueError("Terminal research runs are immutable")


for _run_model in _RUN_IMMUTABLE_COLUMNS:
    event.listen(_run_model, "before_update", _research_run_update_guard)
    event.listen(_run_model, "before_delete", _research_record_is_immutable)
for _run_model in (ResearchRunInputHistory, ResearchRunEvent, ResearchRunPayload, ResearchRunAttempt, ResearchRunManifest):
    event.listen(_run_model, "before_update", _research_record_is_immutable)
    event.listen(_run_model, "before_delete", _research_record_is_immutable)
