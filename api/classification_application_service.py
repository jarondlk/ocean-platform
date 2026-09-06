"""Durable, resumable execution ledger for approved classification reviews."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import config
from api.auth import CurrentUser, ROLE_PERMISSIONS
from api.classification_review_service import (
    ClassificationReviewDomainError,
    _actor_identity,
    _load_review,
    _require_actor,
    record_application,
    review_response,
    validate_current_evidence,
    validate_evidence_rows,
)
from api.schemas import ClassificationReviewApplicationRequest
from db.app_models import (
    AppUser,
    ClassificationApplication,
    ClassificationApplicationEvent,
    ClassificationReview,
)


APPLICATION_STAGES = (
    "register_review",
    "normalize",
    "import",
    "materialize",
    "analyze",
    "embed",
    "provenance",
    "finalize",
)
OPERATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
RECOVERY = {
    "register_review": ["Verify the approved review and immutable artifact store, then replay the same operation ID."],
    "normalize": ["Verify the raw artifact registration and snapshot evidence, then replay the same operation ID."],
    "import": ["Inspect the database transaction and backup; replay the same operation ID only after consistency is confirmed."],
    "materialize": ["The eDNA publication may be pending. Replay the same operation ID to rebuild and publish one complete generation."],
    "analyze": ["Inspect the registered recipe and canonical input identities, then replay the same operation ID."],
    "embed": ["Inspect provider quota, model identity, and missing embeddings; replay with the same operation ID."],
    "provenance": ["Do not expose a partial provenance snapshot. Repair missing registered artifacts or embeddings and replay."],
    "finalize": ["Verify every published identifier, then replay the same operation ID to record the operational receipt."],
}


class ClassificationApplicationError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> None:
    raise ClassificationApplicationError(code, detail)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _event_payload(event: ClassificationApplicationEvent) -> dict[str, Any]:
    return {
        "application_id": str(event.application_id),
        "sequence": event.sequence,
        "event_type": event.event_type,
        "stage": event.stage,
        "occurred_at": _utc_iso(event.occurred_at),
        "result": event.result_json,
        "error_code": event.error_code,
        "recovery": event.recovery_json,
    }


def _application_contract(application: ClassificationApplication) -> dict[str, Any]:
    return {
        "application_id": str(application.id),
        "operation_id": application.operation_id,
        "review_id": str(application.review_id),
        "review_version": application.review_version,
        "review_content_sha256": application.review_content_sha256,
        "source_snapshot_id": application.source_snapshot_id,
        "sample_id": application.sample_id,
        "mode": application.mode,
        "rollback_of_application_id": (
            str(application.rollback_of_application_id)
            if application.rollback_of_application_id
            else None
        ),
        "actor_user_id": str(application.actor_user_id),
        "actor_identity": application.actor_identity_json,
        "started_at": _utc_iso(application.started_at),
    }


def _stage_artifacts(results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for stage, result in results.items():
        for key, value in result.items():
            if key.endswith(("_artifact_id", "_generation_id")) or key in {
                "manifest_id",
                "analysis_ids",
                "document_ids",
            }:
                artifacts[f"{stage}.{key}"] = value
    return artifacts


def _append_event(
    session: Session,
    application: ClassificationApplication,
    *,
    event_type: str,
    stage: Optional[str] = None,
    result: Optional[Mapping[str, Any]] = None,
    error_code: Optional[str] = None,
    recovery: Optional[list[str]] = None,
) -> ClassificationApplicationEvent:
    sequence = int(
        session.scalar(
            select(func.max(ClassificationApplicationEvent.sequence)).where(
                ClassificationApplicationEvent.application_id == application.id
            )
        )
        or 0
    ) + 1
    event = ClassificationApplicationEvent(
        id=uuid.uuid4(),
        application_id=application.id,
        sequence=sequence,
        event_type=event_type,
        stage=stage,
        occurred_at=datetime.now(timezone.utc),
        result_json=dict(result or {}),
        error_code=error_code,
        recovery_json=list(recovery or []),
        event_sha256="0" * 64,
    )
    event.event_sha256 = _digest(_event_payload(event))
    session.add(event)
    session.flush()
    return event


def _events(
    session: Session,
    application: ClassificationApplication,
) -> list[ClassificationApplicationEvent]:
    events = list(
        session.scalars(
            select(ClassificationApplicationEvent)
            .where(ClassificationApplicationEvent.application_id == application.id)
            .order_by(ClassificationApplicationEvent.sequence)
        )
    )
    if not events or [row.sequence for row in events] != list(range(1, len(events) + 1)):
        _fail("application_history_invalid", "Application event history is incomplete")
    if any(row.event_sha256 != _digest(_event_payload(row)) for row in events):
        _fail("application_history_invalid", "Application event history failed integrity validation")
    if events[0].event_type != "run_started" or events[0].result_json != _application_contract(
        application
    ):
        _fail("application_history_invalid", "Application identity does not match its event history")
    completed_events = [row for row in events if row.event_type == "stage_completed"]
    completed = [row.stage for row in completed_events if row.stage]
    if len(completed) != len(set(completed)):
        _fail("application_history_invalid", "Application stage history contains duplicate receipts")
    if completed != list(application.completed_stages_json or []):
        _fail("application_history_invalid", "Application stage state does not match its event history")
    recorded_results = {row.stage: row.result_json for row in completed_events if row.stage}
    if recorded_results != dict(application.results_json or {}):
        _fail("application_history_invalid", "Application results do not match their event receipts")
    if _stage_artifacts(recorded_results) != dict(application.artifacts_json or {}):
        _fail("application_history_invalid", "Application artifacts do not match their event receipts")
    if application.status in {"applied", "rolled_back"}:
        expected = "run_applied" if application.status == "applied" else "run_rolled_back"
        if completed != list(APPLICATION_STAGES) or events[-1].event_type != expected:
            _fail("application_history_invalid", "Application completion receipt is invalid")
    return events


def _load_application(
    session: Session,
    application_id: uuid.UUID,
    *,
    lock: bool = False,
) -> ClassificationApplication:
    statement = select(ClassificationApplication).where(
        ClassificationApplication.id == application_id
    )
    if lock:
        statement = statement.with_for_update()
    application = session.scalar(statement)
    if application is None:
        _fail("application_not_found", "Classification application was not found")
    _events(session, application)
    return application


def _review_for_application(
    session: Session,
    application: ClassificationApplication,
    *,
    lock: bool = True,
) -> ClassificationReview:
    review = _load_review(session, application.review_id, lock=lock)
    review_response(session, review)
    if (
        review.content_sha256 != application.review_content_sha256
        or review.source_snapshot_id != application.source_snapshot_id
        or review.sample_id != application.sample_id
    ):
        _fail("stale_approval", "The approved review no longer matches this application")
    if review.state == "applied" and review.application_reference == application.operation_id:
        return review
    if review.state not in {"approved", "failed"}:
        _fail("stale_approval", "The review is no longer approved for application")
    _validate_application_sample(session, review, application.review_version)
    return review


def _validate_application_sample(
    session: Session,
    review: ClassificationReview,
    approved_version: int,
) -> None:
    """Accept either the pre-import unknown row or this review's exact result."""
    from db.models import EdnaSample

    sample = session.get(EdnaSample, review.sample_id)
    if sample is None or not sample.active or sample.source_snapshot_id != review.source_snapshot_id:
        _fail("stale_approval", "The active canonical sample no longer matches the review snapshot")
    try:
        applied = json.loads(sample.classification_review_json or "null")
    except json.JSONDecodeError:
        applied = None
    decision = applied.get("decision") if isinstance(applied, dict) else None
    if (
        sample.sample_kind == "unknown"
        and sample.is_control is None
        and not isinstance(decision, dict)
    ):
        validate_current_evidence(
            session,
            source_snapshot_id=review.source_snapshot_id,
            sample_id=review.sample_id,
            evidence=review.evidence_json,
        )
        return
    expected_control = None if review.sample_kind == "unknown" else review.sample_kind != "environmental"
    applied_review_id = decision.get("review_id") if isinstance(decision, dict) else None
    predecessor = None
    if review.supersedes_review_id:
        predecessor = session.get(ClassificationReview, review.supersedes_review_id)
        if (
            predecessor is None
            or predecessor.sample_id != review.sample_id
            or predecessor.source_snapshot_id != review.source_snapshot_id
        ):
            _fail("canonical_application_mismatch", "Superseded classification provenance is unavailable")
    if applied_review_id == str(review.id):
        exact_decision = (
            sample.sample_kind == review.sample_kind
            and sample.is_control is expected_control
            and decision.get("review_version") == approved_version
            and decision.get("review_content_sha256") == review.content_sha256
        )
    else:
        exact_decision = predecessor is not None and applied_review_id == str(predecessor.id)
    if (
        sample.provider != "anemone"
        or not isinstance(applied, dict)
        or not isinstance(decision, dict)
        or not exact_decision
    ):
        _fail("canonical_application_mismatch", "Canonical classification does not match the approved review")
    validate_evidence_rows(session, sample=sample, evidence=review.evidence_json)


def workload_actor(session: Session) -> CurrentUser:
    """Resolve the job principal from deployment configuration, never CLI input."""
    subject = os.environ.get("CLASSIFICATION_APPLICATION_ACTOR_SUBJECT", "").strip()
    if not subject:
        _fail("workload_identity_missing", "Classification application workload identity is not configured")
    if config.production_like_environment() and not os.environ.get("CLOUD_RUN_JOB"):
        _fail("cloud_run_boundary_required", "Production classification application must run as a Cloud Run job")
    user = session.scalar(
        select(AppUser).where(
            AppUser.auth_provider == "workload_identity",
            AppUser.auth_subject == subject,
        )
    )
    if user is None:
        _fail("workload_identity_unregistered", "The Cloud Run workload identity is not registered")
    actor = CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        account_type=user.account_type,
        status=user.status,
        permissions=ROLE_PERMISSIONS.get(user.role, frozenset()),
        auth_provider=user.auth_provider,
    )
    _require_actor(session, actor, role="admin", permission="classification:apply")
    return actor


def database_review_artifact(
    session: Session,
    review: ClassificationReview,
    *,
    approved_version: Optional[int] = None,
) -> dict[str, Any]:
    response = review_response(session, review)
    if response.state not in {"approved", "failed"}:
        _fail("stale_approval", "Only an approved scientific decision can be registered")
    decided_by = session.get(AppUser, review.scientific_decided_by_user_id)
    if decided_by is None or review.scientific_decided_at is None:
        _fail("review_identity_missing", "The scientific decision identity is unavailable")
    return {
        "schema_version": 1,
        "status": "approved",
        "source_snapshot_id": review.source_snapshot_id,
        "decisions": [
            {
                "provider_sample_id": review.provider_sample_id,
                "sample_kind": review.sample_kind,
                "review_id": str(review.id),
                "review_version": approved_version or review.version,
                "review_content_sha256": review.content_sha256,
                "reviewer": decided_by.display_name or decided_by.email,
                "reviewed_at": _utc_iso(review.scientific_decided_at),
                "rationale": review.rationale,
                "evidence": [
                    {
                        "source_role": row["source_role"],
                        "source_sha256": row["source_sha256"],
                        "row_number": row["row_number"],
                        "key": row["key"],
                        "value": row["value"],
                    }
                    for row in review.evidence_json
                ],
            }
        ],
    }


def begin_application(
    session: Session,
    *,
    review_id: uuid.UUID,
    operation_id: str,
    actor: CurrentUser,
    rollback_of_application_id: Optional[uuid.UUID] = None,
) -> ClassificationApplication:
    if not OPERATION_PATTERN.fullmatch(operation_id):
        _fail("invalid_operation_id", "Operation ID must be 1-100 safe characters")
    _require_actor(session, actor, role="admin", permission="classification:apply")
    existing = session.scalar(
        select(ClassificationApplication)
        .where(ClassificationApplication.operation_id == operation_id)
        .with_for_update()
    )
    if existing is not None:
        _events(session, existing)
        if existing.review_id != review_id or existing.rollback_of_application_id != rollback_of_application_id:
            _fail("operation_identity_conflict", "Operation ID is registered to different inputs")
        if existing.actor_user_id != actor.id:
            _fail("operation_actor_conflict", "Operation ID is registered to another workload identity")
        if existing.status in {"applied", "rolled_back"}:
            return existing
        _review_for_application(session, existing)
        existing.status = "running"
        existing.current_stage = None
        existing.error_code = None
        existing.recovery_json = []
        existing.finished_at = None
        _append_event(session, existing, event_type="run_resumed")
        return existing

    review = _load_review(session, review_id, lock=True)
    review_response(session, review)
    if review.state not in {"approved", "failed"}:
        _fail("stale_approval", "Only an approved review can start an application")
    validate_current_evidence(
        session,
        source_snapshot_id=review.source_snapshot_id,
        sample_id=review.sample_id,
        evidence=review.evidence_json,
        supersedes_review_id=review.supersedes_review_id,
    )
    mode = "rollback" if rollback_of_application_id else "apply"
    if rollback_of_application_id:
        target = _load_application(session, rollback_of_application_id, lock=True)
        if target.status not in {"applied", "rolled_back"}:
            _fail("invalid_rollback_target", "Rollback target is not a completed application")
        if review.supersedes_review_id != target.review_id or review.sample_id != target.sample_id:
            _fail("invalid_rollback_review", "Rollback review must supersede the applied decision for the same sample")
    application = ClassificationApplication(
        id=uuid.uuid4(),
        operation_id=operation_id,
        review_id=review.id,
        review_version=review.version,
        review_content_sha256=review.content_sha256,
        source_snapshot_id=review.source_snapshot_id,
        sample_id=review.sample_id,
        mode=mode,
        rollback_of_application_id=rollback_of_application_id,
        actor_user_id=actor.id,
        actor_identity_json=_actor_identity(actor),
        status="running",
        current_stage=None,
        completed_stages_json=[],
        artifacts_json={},
        results_json={},
        error_code=None,
        recovery_json=[],
        started_at=datetime.now(timezone.utc),
    )
    session.add(application)
    try:
        session.flush()
    except IntegrityError:
        _fail("concurrent_application", "Another application is already running for this review")
    _append_event(
        session,
        application,
        event_type="run_started",
        result=_application_contract(application),
    )
    return application


def start_stage(
    session: Session,
    application_id: uuid.UUID,
    stage: str,
) -> tuple[ClassificationApplication, bool]:
    if stage not in APPLICATION_STAGES:
        _fail("invalid_application_stage", "Unknown classification application stage")
    application = _load_application(session, application_id, lock=True)
    if application.status in {"applied", "rolled_back"}:
        return application, False
    _review_for_application(session, application)
    completed = list(application.completed_stages_json or [])
    expected = APPLICATION_STAGES[len(completed)] if len(completed) < len(APPLICATION_STAGES) else None
    if stage in completed:
        return application, False
    if stage != expected:
        _fail("application_stage_order", f"Expected application stage {expected}")
    application.current_stage = stage
    application.status = "running"
    application.error_code = None
    application.recovery_json = []
    _append_event(session, application, event_type="stage_started", stage=stage)
    return application, True


def complete_stage(
    session: Session,
    application_id: uuid.UUID,
    stage: str,
    result: Mapping[str, Any],
) -> ClassificationApplication:
    encoded = _canonical(result)
    if len(encoded) > 64 * 1024:
        _fail("application_result_too_large", "Application stage result exceeds 64 KiB")
    application = _load_application(session, application_id, lock=True)
    _review_for_application(session, application)
    completed = list(application.completed_stages_json or [])
    if stage in completed:
        if dict(application.results_json or {}).get(stage) != dict(result):
            _fail("application_replay_conflict", "Replayed stage result does not match its receipt")
        return application
    if application.current_stage != stage:
        _fail("application_stage_order", "Application stage was not started")
    completed.append(stage)
    results = dict(application.results_json or {})
    results[stage] = dict(result)
    application.completed_stages_json = completed
    application.results_json = results
    application.artifacts_json = _stage_artifacts(results)
    application.current_stage = None
    _append_event(
        session,
        application,
        event_type="stage_completed",
        stage=stage,
        result=result,
    )
    return application


def finalize_application(
    session: Session,
    application_id: uuid.UUID,
    actor: CurrentUser,
) -> ClassificationApplication:
    application = _load_application(session, application_id, lock=True)
    review = _review_for_application(session, application)
    if review.state != "applied":
        record_application(
            session,
            review_id=review.id,
            request=ClassificationReviewApplicationRequest(
                expected_version=review.version,
                outcome="applied",
                application_reference=application.operation_id,
            ),
            actor=actor,
            canonical_applied=True,
        )
    complete_stage(
        session,
        application.id,
        "finalize",
        {"application_reference": application.operation_id},
    )
    application = _load_application(session, application.id, lock=True)
    application.status = "rolled_back" if application.mode == "rollback" else "applied"
    application.finished_at = datetime.now(timezone.utc)
    application.current_stage = None
    application.error_code = None
    application.recovery_json = []
    _append_event(
        session,
        application,
        event_type="run_rolled_back" if application.mode == "rollback" else "run_applied",
    )
    return application


def fail_application(
    session: Session,
    application_id: uuid.UUID,
    *,
    stage: str,
    error_code: str,
    actor: CurrentUser,
) -> ClassificationApplication:
    application = _load_application(session, application_id, lock=True)
    recovery = RECOVERY.get(stage, ["Inspect the application record and replay the same operation ID."])
    application.status = "failed"
    application.current_stage = stage
    application.error_code = error_code
    application.recovery_json = recovery
    application.finished_at = datetime.now(timezone.utc)
    _append_event(session, application, event_type="stage_failed", stage=stage, error_code=error_code, recovery=recovery)
    _append_event(session, application, event_type="run_failed", stage=stage, error_code=error_code, recovery=recovery)
    try:
        review = _review_for_application(session, application)
        if review.state != "applied":
            record_application(
                session,
                review_id=review.id,
                request=ClassificationReviewApplicationRequest(
                    expected_version=review.version,
                    outcome="failed",
                    application_reference=application.operation_id,
                    failure_code=error_code,
                    failure_detail=f"Controlled application stopped at {stage}.",
                ),
                actor=actor,
            )
    except (ClassificationApplicationError, ClassificationReviewDomainError):
        pass
    return application


def application_summary(application: ClassificationApplication) -> dict[str, Any]:
    return {
        "application_id": str(application.id),
        "operation_id": application.operation_id,
        "review_id": str(application.review_id),
        "mode": application.mode,
        "rollback_of_application_id": (
            str(application.rollback_of_application_id)
            if application.rollback_of_application_id
            else None
        ),
        "status": application.status,
        "current_stage": application.current_stage,
        "completed_stages": list(application.completed_stages_json or []),
        "artifacts": dict(application.artifacts_json or {}),
        "results": dict(application.results_json or {}),
        "error_code": application.error_code,
        "recovery": list(application.recovery_json or []),
        "started_at": _utc_iso(application.started_at),
        "finished_at": _utc_iso(application.finished_at) if application.finished_at else None,
    }
