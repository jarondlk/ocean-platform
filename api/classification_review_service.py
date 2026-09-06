"""Authenticated, evidence-bound ANEMONE classification review domain."""
from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, NoReturn, Optional

from sqlalchemy import func, inspect as sa_inspect, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.auth import CurrentUser, ROLE_PERMISSIONS
from api.schemas import (
    ClassificationEvidenceInput,
    ClassificationReviewApplicationRequest,
    ClassificationReviewDecisionRequest,
    ClassificationReviewDraftCreate,
    ClassificationReviewDraftUpdate,
    ClassificationReviewEventResponse,
    ClassificationReviewPreviewRequest,
    ClassificationReviewPreviewResponse,
    ClassificationPreviewMethod,
    ClassificationPreviewScenario,
    ClassificationReviewResponse,
)
from db.app_models import AppUser, ClassificationReview, ClassificationReviewEvent
from db.models import (
    EdnaAssay,
    EdnaDetection,
    EdnaInternalStandard,
    EdnaSample,
    ExternalSourceFile,
    ExternalSourceSnapshot,
)
from ingestion.immutable_bundle import digest as scientific_digest
from preprocessing.edna_analysis import ALGORITHM_VERSION, build_analysis
from preprocessing.edna_recipe import AnalysisRecipe


CURRENT_STATES = frozenset({"approved", "applied", "failed"})
REPLACEABLE_STATES = CURRENT_STATES
PREVIEWABLE_STATES = frozenset({"draft", "approved", "failed"})
PREVIEW_SAMPLE_LIMIT = 1_000
PREVIEW_ASSAY_LIMIT = 1_000
PREVIEW_DETECTION_LIMIT = 250_000
PREVIEW_STANDARD_LIMIT = 10_000
PREVIEW_SOURCE_LIMIT = 10_000


class ClassificationReviewDomainError(ValueError):
    def __init__(self, status_code: int, code: str, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


def _fail(status_code: int, code: str, detail: str) -> NoReturn:
    raise ClassificationReviewDomainError(status_code, code, detail)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _timestamp(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _evidence_rows(
    evidence: Iterable[ClassificationEvidenceInput | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = [
        row.model_dump(mode="json")
        if isinstance(row, ClassificationEvidenceInput)
        else dict(row)
        for row in evidence
    ]
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("source_role") or ""),
            str(row.get("source_file_id") or ""),
            int(row.get("row_number") or 0),
        ),
    )


def _content_payload(
    *,
    source_snapshot_id: str,
    sample_id: str,
    provider_sample_id: str,
    sample_kind: str,
    rationale: str,
    evidence: Iterable[ClassificationEvidenceInput | Mapping[str, Any]],
    supersedes_review_id: Optional[uuid.UUID | str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_snapshot_id": source_snapshot_id,
        "sample_id": sample_id,
        "provider_sample_id": provider_sample_id,
        "sample_kind": sample_kind,
        "rationale": rationale,
        "evidence": _evidence_rows(evidence),
        "supersedes_review_id": (
            str(supersedes_review_id) if supersedes_review_id else None
        ),
    }


def _review_content_payload(review: ClassificationReview) -> dict[str, Any]:
    return _content_payload(
        source_snapshot_id=review.source_snapshot_id,
        sample_id=review.sample_id,
        provider_sample_id=review.provider_sample_id,
        sample_kind=review.sample_kind,
        rationale=review.rationale,
        evidence=review.evidence_json,
        supersedes_review_id=review.supersedes_review_id,
    )


def _review_snapshot(review: ClassificationReview) -> dict[str, Any]:
    return {
        **_review_content_payload(review),
        "id": str(review.id),
        "content_sha256": review.content_sha256,
        "state": review.state,
        "version": review.version,
        "created_by_user_id": str(review.created_by_user_id),
        "scientific_decided_by_user_id": (
            str(review.scientific_decided_by_user_id)
            if review.scientific_decided_by_user_id
            else None
        ),
        "scientific_decided_at": _timestamp(review.scientific_decided_at),
        "operational_actor_user_id": (
            str(review.operational_actor_user_id)
            if review.operational_actor_user_id
            else None
        ),
        "operational_at": _timestamp(review.operational_at),
        "application_reference": review.application_reference,
        "failure_code": review.failure_code,
        "failure_detail": review.failure_detail,
    }


def _actor_identity(actor: CurrentUser) -> dict[str, Any]:
    return {
        "user_id": str(actor.id),
        "email": actor.email,
        "display_name": actor.display_name,
        "role": actor.role,
        "account_type": actor.account_type,
        "auth_provider": actor.auth_provider,
    }


def _require_actor(
    session: Session,
    actor: CurrentUser,
    *,
    role: str,
    permission: str,
) -> None:
    stored = session.get(AppUser, actor.id)
    if (
        actor.auth_provider == "disabled"
        or actor.status != "active"
        or actor.role != role
        or permission not in actor.permissions
        or actor.permissions != ROLE_PERMISSIONS.get(actor.role, frozenset())
        or stored is None
        or stored.status != "active"
        or stored.role != actor.role
        or stored.email != actor.email
        or stored.display_name != actor.display_name
        or stored.account_type != actor.account_type
        or stored.auth_provider != actor.auth_provider
    ):
        _fail(
            403,
            "authenticated_role_required",
            f"An authenticated {role} identity is required",
        )


def _event_payload(
    *,
    review_id: uuid.UUID,
    sequence: int,
    event_type: str,
    from_state: Optional[str],
    to_state: str,
    actor_user_id: uuid.UUID,
    actor_role: str,
    actor_identity: Mapping[str, Any],
    occurred_at: datetime,
    content_sha256: str,
    review_snapshot: Mapping[str, Any],
    details: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "review_id": str(review_id),
        "sequence": sequence,
        "event_type": event_type,
        "from_state": from_state,
        "to_state": to_state,
        "actor_user_id": str(actor_user_id),
        "actor_role": actor_role,
        "actor_identity": dict(actor_identity),
        "occurred_at": _timestamp(occurred_at),
        "content_sha256": content_sha256,
        "review_snapshot": dict(review_snapshot),
        "details": dict(details),
    }


def _append_event(
    session: Session,
    *,
    review: ClassificationReview,
    actor: CurrentUser,
    event_type: str,
    from_state: Optional[str],
    occurred_at: datetime,
    details: Optional[Mapping[str, Any]] = None,
) -> ClassificationReviewEvent:
    identity = _actor_identity(actor)
    snapshot = _review_snapshot(review)
    event_details = dict(details or {})
    payload = _event_payload(
        review_id=review.id,
        sequence=review.version,
        event_type=event_type,
        from_state=from_state,
        to_state=review.state,
        actor_user_id=actor.id,
        actor_role=actor.role,
        actor_identity=identity,
        occurred_at=occurred_at,
        content_sha256=review.content_sha256,
        review_snapshot=snapshot,
        details=event_details,
    )
    event = ClassificationReviewEvent(
        id=uuid.uuid4(),
        review_id=review.id,
        sequence=review.version,
        event_type=event_type,
        from_state=from_state,
        to_state=review.state,
        actor_user_id=actor.id,
        actor_role=actor.role,
        actor_identity_json=identity,
        occurred_at=occurred_at,
        content_sha256=review.content_sha256,
        event_sha256=_digest(payload),
        review_snapshot_json=snapshot,
        details_json=event_details,
    )
    session.add(event)
    return event


def _json_record(raw: Any, *, label: str) -> Any:
    if not isinstance(raw, str):
        _fail(409, "canonical_evidence_corrupt", f"{label} is not valid JSON")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        _fail(409, "canonical_evidence_corrupt", f"{label} is not valid JSON")


def _active_sample(
    session: Session,
    *,
    sample_id: str,
    source_snapshot_id: str,
    supersedes_review_id: Optional[uuid.UUID] = None,
) -> EdnaSample:
    sample = session.get(EdnaSample, sample_id)
    if sample is None:
        _fail(404, "sample_not_found", "ANEMONE sample not found")
    if not sample.active or sample.source_snapshot_id != source_snapshot_id:
        _fail(
            409,
            "stale_source_snapshot",
            "The review does not reference the active sample snapshot",
        )
    if sample.provider != "anemone":
        _fail(422, "provider_not_supported", "Only ANEMONE samples are supported")
    try:
        applied = json.loads(sample.classification_review_json or "null")
    except json.JSONDecodeError:
        applied = None
    decision = applied.get("decision") if isinstance(applied, dict) else None
    applied_review_id = decision.get("review_id") if isinstance(decision, dict) else None
    if applied_review_id is not None:
        if (
            supersedes_review_id is None
            or applied_review_id != str(supersedes_review_id)
        ):
            _fail(
                409,
                "classification_already_known",
                "A review cannot override an existing sample classification",
            )
    elif sample.sample_kind != "unknown" or sample.is_control is not None:
        _fail(
            409,
            "classification_already_known",
            "A review cannot override an existing sample classification",
        )
    snapshot = session.get(ExternalSourceSnapshot, source_snapshot_id)
    if snapshot is None or snapshot.status != "complete":
        _fail(409, "snapshot_unavailable", "Source snapshot is not complete")
    return sample


def _evidence_entity(
    session: Session,
    *,
    sample: EdnaSample,
    source_role: str,
    source_file_id: str,
) -> tuple[dict[str, Any], list[int]]:
    if source_role == "sample_metadata":
        if sample.source_file_id != source_file_id:
            _fail(422, "evidence_file_mismatch", "Evidence file does not match sample")
        entity = sample
    else:
        entity = session.scalar(
            select(EdnaAssay).where(
                EdnaAssay.sample_id == sample.sample_id,
                EdnaAssay.source_snapshot_id == sample.source_snapshot_id,
                EdnaAssay.source_file_id == source_file_id,
                EdnaAssay.active.is_(True),
            )
        )
        if entity is None:
            _fail(
                422,
                "evidence_file_mismatch",
                "Evidence file does not match an active sample experiment",
            )
    metadata = _json_record(entity.raw_metadata_json, label="Canonical metadata")
    row_numbers = _json_record(
        entity.source_row_numbers_json,
        label="Canonical row locators",
    )
    if not isinstance(metadata, dict) or not isinstance(row_numbers, list):
        _fail(409, "canonical_evidence_corrupt", "Canonical evidence is invalid")
    return metadata, [int(value) for value in row_numbers]


def validate_current_evidence(
    session: Session,
    *,
    source_snapshot_id: str,
    sample_id: str,
    evidence: Iterable[ClassificationEvidenceInput | Mapping[str, Any]],
    supersedes_review_id: Optional[uuid.UUID] = None,
) -> EdnaSample:
    sample = _active_sample(
        session,
        sample_id=sample_id,
        source_snapshot_id=source_snapshot_id,
        supersedes_review_id=supersedes_review_id,
    )
    validate_evidence_rows(session, sample=sample, evidence=evidence)
    return sample


def validate_evidence_rows(
    session: Session,
    *,
    sample: EdnaSample,
    evidence: Iterable[ClassificationEvidenceInput | Mapping[str, Any]],
) -> None:
    """Recheck immutable evidence against an already resolved sample row."""
    for row in _evidence_rows(evidence):
        source = session.get(ExternalSourceFile, row["source_file_id"])
        if (
            source is None
            or source.snapshot_id != sample.source_snapshot_id
            or source.sample_name != sample.provider_sample_id
            or source.role != row["source_role"]
            or source.sha256 != row["source_sha256"]
            or source.validation_status != "valid"
        ):
            _fail(
                422,
                "evidence_source_mismatch",
                "Classification evidence does not match the verified source file",
            )
        metadata, row_numbers = _evidence_entity(
            session,
            sample=sample,
            source_role=row["source_role"],
            source_file_id=row["source_file_id"],
        )
        if (
            row["row_number"] not in row_numbers
            or metadata.get(row["key"]) != row["value"]
            or (
                source.row_count is not None
                and row["row_number"] > source.row_count + 1
            )
        ):
            _fail(
                422,
                "evidence_row_mismatch",
                "Classification evidence row does not match canonical metadata",
            )


def _events(session: Session, review_id: uuid.UUID) -> list[ClassificationReviewEvent]:
    return list(
        session.scalars(
            select(ClassificationReviewEvent)
            .where(ClassificationReviewEvent.review_id == review_id)
            .order_by(ClassificationReviewEvent.sequence)
        )
    )


def _verify_integrity(
    session: Session,
    review: ClassificationReview,
) -> list[ClassificationReviewEvent]:
    if _digest(_review_content_payload(review)) != review.content_sha256:
        _fail(409, "review_integrity_failed", "Classification review integrity failed")
    events = _events(session, review.id)
    if len(events) != review.version:
        _fail(409, "event_history_incomplete", "Classification review history is incomplete")
    for expected, event in enumerate(events, start=1):
        snapshot = event.review_snapshot_json
        if not isinstance(snapshot, dict):
            _fail(409, "event_integrity_failed", "Classification review event integrity failed")
        try:
            snapshot_content = _content_payload(
                source_snapshot_id=snapshot["source_snapshot_id"],
                sample_id=snapshot["sample_id"],
                provider_sample_id=snapshot["provider_sample_id"],
                sample_kind=snapshot["sample_kind"],
                rationale=snapshot["rationale"],
                evidence=snapshot["evidence"],
                supersedes_review_id=snapshot.get("supersedes_review_id"),
            )
        except (KeyError, TypeError, ValueError):
            _fail(409, "event_integrity_failed", "Classification review event integrity failed")
        payload = _event_payload(
            review_id=event.review_id,
            sequence=event.sequence,
            event_type=event.event_type,
            from_state=event.from_state,
            to_state=event.to_state,
            actor_user_id=event.actor_user_id,
            actor_role=event.actor_role,
            actor_identity=event.actor_identity_json,
            occurred_at=event.occurred_at,
            content_sha256=event.content_sha256,
            review_snapshot=snapshot,
            details=event.details_json,
        )
        if (
            event.sequence != expected
            or snapshot.get("version") != expected
            or snapshot.get("state") != event.to_state
            or _digest(snapshot_content) != event.content_sha256
            or snapshot.get("content_sha256") != event.content_sha256
            or _digest(payload) != event.event_sha256
        ):
            _fail(409, "event_integrity_failed", "Classification review event integrity failed")
    latest = events[-1].review_snapshot_json
    if (
        latest.get("state") != review.state
        or latest.get("version") != review.version
        or latest.get("content_sha256") != review.content_sha256
    ):
        _fail(409, "review_history_mismatch", "Classification review history does not match")
    return events


def _load_review(
    session: Session,
    review_id: uuid.UUID,
    *,
    lock: bool = False,
) -> ClassificationReview:
    statement = select(ClassificationReview).where(ClassificationReview.id == review_id)
    if lock:
        statement = statement.with_for_update()
    review = session.scalar(statement)
    if review is None:
        _fail(404, "review_not_found", "Classification review not found")
    _verify_integrity(session, review)
    return review


def _check_version(review: ClassificationReview, expected_version: int) -> None:
    if review.version != expected_version:
        _fail(
            409,
            "stale_review_version",
            "Classification review changed; reload before continuing",
        )


def _event_response(event: ClassificationReviewEvent) -> ClassificationReviewEventResponse:
    return ClassificationReviewEventResponse(
        id=event.id,
        review_id=event.review_id,
        sequence=event.sequence,
        event_type=event.event_type,
        from_state=event.from_state,
        to_state=event.to_state,
        actor_user_id=event.actor_user_id,
        actor_role=event.actor_role,
        actor_identity=event.actor_identity_json,
        occurred_at=event.occurred_at,
        content_sha256=event.content_sha256,
        event_sha256=event.event_sha256,
        details=event.details_json or {},
    )


def review_response(
    session: Session,
    review: ClassificationReview,
) -> ClassificationReviewResponse:
    events = _verify_integrity(session, review)
    return ClassificationReviewResponse(
        id=review.id,
        source_snapshot_id=review.source_snapshot_id,
        sample_id=review.sample_id,
        provider_sample_id=review.provider_sample_id,
        sample_kind=review.sample_kind,
        rationale=review.rationale,
        evidence=[ClassificationEvidenceInput.model_validate(row) for row in review.evidence_json],
        content_sha256=review.content_sha256,
        state=review.state,
        version=review.version,
        supersedes_review_id=review.supersedes_review_id,
        created_by_user_id=review.created_by_user_id,
        scientific_decided_by_user_id=review.scientific_decided_by_user_id,
        scientific_decided_at=review.scientific_decided_at,
        operational_actor_user_id=review.operational_actor_user_id,
        operational_at=review.operational_at,
        application_reference=review.application_reference,
        failure_code=review.failure_code,
        failure_detail=review.failure_detail,
        created_at=review.created_at,
        updated_at=review.updated_at,
        events=[_event_response(event) for event in events],
    )


def create_draft(
    session: Session,
    *,
    request: ClassificationReviewDraftCreate,
    actor: CurrentUser,
) -> ClassificationReviewResponse:
    _require_actor(
        session,
        actor,
        role="researcher",
        permission="classification:decide",
    )
    sample = validate_current_evidence(
        session,
        source_snapshot_id=request.source_snapshot_id,
        sample_id=request.sample_id,
        evidence=request.evidence,
        supersedes_review_id=request.supersedes_review_id,
    )
    if request.supersedes_review_id:
        previous = _load_review(session, request.supersedes_review_id)
        if previous.sample_id != request.sample_id or previous.state not in REPLACEABLE_STATES:
            _fail(
                409,
                "invalid_superseded_review",
                "The referenced review cannot be superseded by this draft",
            )
    payload = _content_payload(
        source_snapshot_id=request.source_snapshot_id,
        sample_id=request.sample_id,
        provider_sample_id=sample.provider_sample_id,
        sample_kind=request.sample_kind,
        rationale=request.rationale,
        evidence=request.evidence,
        supersedes_review_id=request.supersedes_review_id,
    )
    now = datetime.now(timezone.utc)
    review = ClassificationReview(
        id=uuid.uuid4(),
        source_snapshot_id=request.source_snapshot_id,
        sample_id=request.sample_id,
        provider_sample_id=sample.provider_sample_id,
        sample_kind=request.sample_kind,
        rationale=request.rationale,
        evidence_json=payload["evidence"],
        content_sha256=_digest(payload),
        state="draft",
        version=1,
        supersedes_review_id=request.supersedes_review_id,
        created_by_user_id=actor.id,
    )
    session.add(review)
    session.flush()
    _append_event(
        session,
        review=review,
        actor=actor,
        event_type="created",
        from_state=None,
        occurred_at=now,
    )
    session.flush()
    return review_response(session, review)


def update_draft(
    session: Session,
    *,
    review_id: uuid.UUID,
    request: ClassificationReviewDraftUpdate,
    actor: CurrentUser,
) -> ClassificationReviewResponse:
    _require_actor(
        session,
        actor,
        role="researcher",
        permission="classification:decide",
    )
    review = _load_review(session, review_id, lock=True)
    _check_version(review, request.expected_version)
    if review.state != "draft":
        _fail(409, "invalid_review_transition", "Only draft reviews can be edited")
    validate_current_evidence(
        session,
        source_snapshot_id=review.source_snapshot_id,
        sample_id=review.sample_id,
        evidence=request.evidence,
        supersedes_review_id=review.supersedes_review_id,
    )
    from_state = review.state
    review.sample_kind = request.sample_kind
    review.rationale = request.rationale
    review.evidence_json = _evidence_rows(request.evidence)
    review.content_sha256 = _digest(_review_content_payload(review))
    review.version += 1
    _append_event(
        session,
        review=review,
        actor=actor,
        event_type="draft_updated",
        from_state=from_state,
        occurred_at=datetime.now(timezone.utc),
    )
    session.flush()
    return review_response(session, review)


def decide_review(
    session: Session,
    *,
    review_id: uuid.UUID,
    request: ClassificationReviewDecisionRequest,
    actor: CurrentUser,
) -> ClassificationReviewResponse:
    _require_actor(
        session,
        actor,
        role="researcher",
        permission="classification:decide",
    )
    review = _load_review(session, review_id, lock=True)
    _check_version(review, request.expected_version)
    if review.state != "draft":
        _fail(409, "invalid_review_transition", "Only draft reviews can be decided")
    validate_current_evidence(
        session,
        source_snapshot_id=review.source_snapshot_id,
        sample_id=review.sample_id,
        evidence=review.evidence_json,
        supersedes_review_id=review.supersedes_review_id,
    )
    now = datetime.now(timezone.utc)
    if request.decision == "approved":
        current = session.scalar(
            select(ClassificationReview)
            .where(
                ClassificationReview.sample_id == review.sample_id,
                ClassificationReview.id != review.id,
                ClassificationReview.state.in_(CURRENT_STATES),
            )
            .with_for_update()
        )
        if current is not None and current.id != review.supersedes_review_id:
            _fail(
                409,
                "supersession_required",
                "An approved review already exists for this sample",
            )
        if review.supersedes_review_id:
            previous = _load_review(session, review.supersedes_review_id, lock=True)
            if previous.sample_id != review.sample_id or previous.state not in REPLACEABLE_STATES:
                _fail(
                    409,
                    "invalid_superseded_review",
                    "The referenced review can no longer be superseded",
                )
            previous_state = previous.state
            previous.state = "superseded"
            previous.version += 1
            _append_event(
                session,
                review=previous,
                actor=actor,
                event_type="superseded",
                from_state=previous_state,
                occurred_at=now,
                details={"replacement_review_id": str(review.id)},
            )
            session.flush()
    from_state = review.state
    review.state = request.decision
    review.scientific_decided_by_user_id = actor.id
    review.scientific_decided_at = now
    review.version += 1
    _append_event(
        session,
        review=review,
        actor=actor,
        event_type=request.decision,
        from_state=from_state,
        occurred_at=now,
    )
    try:
        session.flush()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        sqlite_unique = "classification_review.sample_id" in str(exc.orig)
        if request.decision == "approved" and (
            constraint == "uq_classification_review_current_sample"
            or sqlite_unique
        ):
            _fail(
                409,
                "concurrent_review_decision",
                "Another review was approved for this sample",
            )
        raise
    return review_response(session, review)


def record_application(
    session: Session,
    *,
    review_id: uuid.UUID,
    request: ClassificationReviewApplicationRequest,
    actor: CurrentUser,
    canonical_applied: bool = False,
) -> ClassificationReviewResponse:
    _require_actor(
        session,
        actor,
        role="admin",
        permission="classification:apply",
    )
    review = _load_review(session, review_id, lock=True)
    _check_version(review, request.expected_version)
    if review.state not in {"approved", "failed"}:
        _fail(
            409,
            "invalid_review_transition",
            "Only approved or failed reviews can record an application outcome",
        )
    if request.outcome == "applied":
        if not canonical_applied:
            _fail(
                409,
                "controlled_application_required",
                "Applied outcomes are recorded only by the controlled processing job",
            )
    now = datetime.now(timezone.utc)
    from_state = review.state
    review.state = request.outcome
    review.operational_actor_user_id = actor.id
    review.operational_at = now
    review.application_reference = request.application_reference
    review.failure_code = request.failure_code
    review.failure_detail = request.failure_detail
    review.version += 1
    _append_event(
        session,
        review=review,
        actor=actor,
        event_type=request.outcome,
        from_state=from_state,
        occurred_at=now,
        details={
            "application_reference": request.application_reference,
            "failure_code": request.failure_code,
            "failure_detail": request.failure_detail,
        },
    )
    session.flush()
    return review_response(session, review)


def get_review(
    session: Session,
    review_id: uuid.UUID,
) -> ClassificationReviewResponse:
    return review_response(session, _load_review(session, review_id))


def list_reviews(
    session: Session,
    *,
    sample_id: Optional[str],
    state: Optional[str],
    limit: int,
    offset: int,
) -> tuple[list[ClassificationReviewResponse], int]:
    conditions = []
    if sample_id:
        conditions.append(ClassificationReview.sample_id == sample_id)
    if state:
        conditions.append(ClassificationReview.state == state)
    total = int(
        session.scalar(
            select(func.count(ClassificationReview.id)).where(*conditions)
        )
        or 0
    )
    reviews = session.scalars(
        select(ClassificationReview)
        .where(*conditions)
        .order_by(ClassificationReview.created_at.desc(), ClassificationReview.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [review_response(session, review) for review in reviews], total


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _model_record(instance: Any) -> dict[str, Any]:
    return {
        attribute.columns[0].name: _json_value(getattr(instance, attribute.key))
        for attribute in sa_inspect(instance).mapper.column_attrs
    }


def _bounded_records(
    session: Session,
    statement: Any,
    *,
    limit: int,
    label: str,
) -> list[Any]:
    records = list(session.scalars(statement.limit(limit + 1)))
    if len(records) > limit:
        _fail(
            413,
            "preview_resource_limit",
            f"Classification preview exceeds the {label} limit",
        )
    return records


def _preview_source(
    session: Session,
    sample: EdnaSample,
) -> dict[str, list[dict[str, Any]]]:
    samples = _bounded_records(
        session,
        select(EdnaSample).where(
            EdnaSample.active.is_(True),
            EdnaSample.provider == sample.provider,
            EdnaSample.provider_project_id == sample.provider_project_id,
            EdnaSample.provider_run_id == sample.provider_run_id,
            or_(
                EdnaSample.sample_id == sample.sample_id,
                EdnaSample.sample_kind != "environmental",
            ),
        ),
        limit=PREVIEW_SAMPLE_LIMIT,
        label="sample",
    )
    sample_ids = [row.sample_id for row in samples]
    assays = _bounded_records(
        session,
        select(EdnaAssay).where(
            EdnaAssay.active.is_(True),
            EdnaAssay.sample_id.in_(sample_ids),
        ),
        limit=PREVIEW_ASSAY_LIMIT,
        label="assay",
    )
    assay_ids = [row.assay_id for row in assays]
    detections = _bounded_records(
        session,
        select(EdnaDetection).where(
            EdnaDetection.active.is_(True),
            EdnaDetection.assay_id.in_(assay_ids),
        ),
        limit=PREVIEW_DETECTION_LIMIT,
        label="detection",
    )
    standards = _bounded_records(
        session,
        select(EdnaInternalStandard).where(
            EdnaInternalStandard.active.is_(True),
            EdnaInternalStandard.assay_id.in_(assay_ids),
        ),
        limit=PREVIEW_STANDARD_LIMIT,
        label="internal-standard",
    )
    scientific_records = [*samples, *assays, *detections, *standards]
    source_file_ids = sorted(
        {row.source_file_id for row in scientific_records}
    )
    snapshot_ids = sorted(
        {row.source_snapshot_id for row in scientific_records}
    )
    source_files = _bounded_records(
        session,
        select(ExternalSourceFile).where(
            ExternalSourceFile.source_file_id.in_(source_file_ids)
        ),
        limit=PREVIEW_SOURCE_LIMIT,
        label="source-file",
    )
    snapshots = _bounded_records(
        session,
        select(ExternalSourceSnapshot).where(
            ExternalSourceSnapshot.snapshot_id.in_(snapshot_ids)
        ),
        limit=PREVIEW_SOURCE_LIMIT,
        label="source-snapshot",
    )
    if len(source_files) != len(source_file_ids) or len(snapshots) != len(snapshot_ids):
        _fail(
            409,
            "preview_provenance_incomplete",
            "Classification preview source provenance is incomplete",
        )
    if any(
        row.validation_status != "valid" or not row.sha256
        for row in source_files
    ) or any(row.status != "complete" for row in snapshots):
        _fail(
            409,
            "preview_provenance_unverified",
            "Classification preview source provenance is not verified",
        )
    return {
        "edna_sample": [_model_record(row) for row in samples],
        "edna_assay": [_model_record(row) for row in assays],
        "edna_detection": [_model_record(row) for row in detections],
        "edna_internal_standard": [_model_record(row) for row in standards],
        "external_source_file": [_model_record(row) for row in source_files],
        "external_source_snapshot": [_model_record(row) for row in snapshots],
    }


def _control_status(sample_kind: str) -> Optional[bool]:
    if sample_kind == "environmental":
        return False
    if sample_kind == "unknown":
        return None
    return True


def _scenario(
    result: Mapping[str, Any],
    *,
    sample_id: str,
    sample_kind: str,
    is_control: Optional[bool],
    top_taxa_limit: int,
) -> ClassificationPreviewScenario:
    tables = result["tables"]
    membership = [
        row for row in tables["membership"] if row.get("sample_id") == sample_id
    ]
    methods: list[ClassificationPreviewMethod] = []
    for member in sorted(
        membership,
        key=lambda row: (
            row.get("assay_id") or "",
            row.get("assignment_method") or "",
        ),
    ):
        assay_id = member.get("assay_id") or ""
        assignment_method = member.get("assignment_method") or ""
        exclusions = [
            row
            for row in tables["exclusions"]
            if row.get("assay_id") == assay_id
            and row.get("assignment_method") == assignment_method
        ]
        diversity = next(
            (
                row
                for row in tables["diversity"]
                if row.get("assay_id") == assay_id
                and row.get("assignment_method") == assignment_method
            ),
            None,
        )
        composition = sorted(
            (
                row
                for row in tables["composition"]
                if row.get("assay_id") == assay_id
                and row.get("assignment_method") == assignment_method
            ),
            key=lambda row: (-int(row["read_count"]), str(row["taxon"])),
        )
        source_detection_count = int(member.get("detection_count") or 0)
        excluded_detection_count = len(exclusions)
        retained_detection_count = max(
            0,
            source_detection_count - excluded_detection_count,
        )
        excluded_reads = int(
            (diversity or {}).get("excluded_reads")
            or sum(int(row.get("read_count") or 0) for row in exclusions)
        )
        retained_reads = int((diversity or {}).get("retained_reads") or 0)
        methods.append(
            ClassificationPreviewMethod(
                assay_id=assay_id,
                assignment_method=assignment_method,
                status=str(member.get("status") or "sample_excluded"),
                reason=member.get("reason"),
                source_detection_count=source_detection_count,
                retained_detection_count=retained_detection_count,
                excluded_detection_count=excluded_detection_count,
                source_reads=int(
                    (diversity or {}).get("source_reads")
                    or retained_reads + excluded_reads
                ),
                retained_reads=retained_reads,
                excluded_reads=excluded_reads,
                richness=(
                    int(diversity["richness"]) if diversity is not None else None
                ),
                shannon=(diversity or {}).get("shannon"),
                simpson_1d=(diversity or {}).get("simpson_1d"),
                evenness=(diversity or {}).get("evenness"),
                metric_status=str(
                    (diversity or {}).get("metric_status")
                    or member.get("reason")
                    or "sample_excluded"
                ),
                top_taxa=[
                    {
                        "taxon": str(row["taxon"]),
                        "read_count": int(row["read_count"]),
                        "read_proportion": float(row["read_proportion"]),
                    }
                    for row in composition[:top_taxa_limit]
                ],
            )
        )
    included = any(row.status == "included" for row in methods)
    return ClassificationPreviewScenario(
        sample_kind=sample_kind,
        is_control=is_control,
        eligibility="included" if included else "excluded",
        exclusion_reasons=sorted(
            {row.reason for row in methods if row.reason is not None}
        ),
        analysis_id=str(result["analysis_id"]),
        input_sha256=str(result["input_sha256"]),
        table_counts={name: len(rows) for name, rows in tables.items()},
        methods=methods,
    )


def preview_review(
    session: Session,
    *,
    review_id: uuid.UUID,
    request: ClassificationReviewPreviewRequest,
    actor: CurrentUser,
) -> ClassificationReviewPreviewResponse:
    if session.get_bind().dialect.name == "postgresql":
        connection = session.connection()
        if connection.get_isolation_level().upper() != "REPEATABLE READ":
            session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
    if actor.role not in {"researcher", "admin"}:
        _fail(
            403,
            "authenticated_role_required",
            "An authenticated researcher or admin identity is required",
        )
    _require_actor(
        session,
        actor,
        role=actor.role,
        permission="classification:read",
    )
    review = _load_review(session, review_id, lock=True)
    _check_version(review, request.expected_version)
    if review.state not in PREVIEWABLE_STATES:
        _fail(
            409,
            "invalid_preview_state",
            "Only draft, approved, or failed reviews can be previewed",
        )
    sample = validate_current_evidence(
        session,
        source_snapshot_id=review.source_snapshot_id,
        sample_id=review.sample_id,
        evidence=review.evidence_json,
        supersedes_review_id=review.supersedes_review_id,
    )
    source = _preview_source(session, sample)
    recipe = AnalysisRecipe.model_validate(
        {
            "cohort": {"sample_ids": [review.sample_id]},
            "assignment_methods": request.assignment_methods,
            "rank": request.rank,
            "control_policy": "environmental_only",
            "min_read_count": request.min_read_count,
        }
    )
    proposed_source = deepcopy(source)
    proposed_sample = next(
        row
        for row in proposed_source["edna_sample"]
        if row["sample_id"] == review.sample_id
    )
    proposed_sample["sample_kind"] = review.sample_kind
    proposed_sample["is_control"] = _control_status(review.sample_kind)
    proposed_sample["classification_basis"] = f"preview:{review.content_sha256}"
    proposed_sample["classification_review_json"] = json.dumps(
        {
            "review_id": str(review.id),
            "review_version": review.version,
            "content_sha256": review.content_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    proposed_sample["scientific_content_sha256"] = scientific_digest(
        {
            key: value
            for key, value in proposed_sample.items()
            if key not in {"scientific_content_sha256", "source_row_hash"}
        }
    )
    try:
        baseline_result = build_analysis(recipe, source)
        proposed_result = build_analysis(recipe, proposed_source)
    except ValueError as exc:
        if "limit" in str(exc).casefold():
            _fail(413, "preview_resource_limit", str(exc))
        _fail(
            409,
            "preview_computation_failed",
            "Classification preview could not be computed from canonical data",
        )
    baseline = _scenario(
        baseline_result,
        sample_id=review.sample_id,
        sample_kind=sample.sample_kind,
        is_control=sample.is_control,
        top_taxa_limit=request.top_taxa_limit,
    )
    proposed = _scenario(
        proposed_result,
        sample_id=review.sample_id,
        sample_kind=review.sample_kind,
        is_control=_control_status(review.sample_kind),
        top_taxa_limit=request.top_taxa_limit,
    )
    table_names = sorted(
        set(baseline.table_counts) | set(proposed.table_counts)
    )
    table_count_delta = {
        name: proposed.table_counts.get(name, 0)
        - baseline.table_counts.get(name, 0)
        for name in table_names
    }
    canonical_input_sha256 = scientific_digest(
        baseline_result["inputs"]["canonical"]
    )
    preview_payload = {
        "schema_version": 1,
        "review_id": str(review.id),
        "review_state": review.state,
        "review_version": review.version,
        "review_content_sha256": review.content_sha256,
        "source_snapshot_id": review.source_snapshot_id,
        "sample_id": review.sample_id,
        "algorithm_version": ALGORITHM_VERSION,
        "recipe": recipe.model_dump(mode="json"),
        "canonical_input_sha256": canonical_input_sha256,
        "baseline": baseline.model_dump(mode="json"),
        "proposed": proposed.model_dump(mode="json"),
        "table_count_delta": table_count_delta,
    }
    return ClassificationReviewPreviewResponse(
        review_id=review.id,
        review_state=review.state,
        review_version=review.version,
        review_content_sha256=review.content_sha256,
        source_snapshot_id=review.source_snapshot_id,
        sample_id=review.sample_id,
        provider_sample_id=review.provider_sample_id,
        algorithm_version=ALGORITHM_VERSION,
        recipe=recipe.model_dump(mode="json"),
        canonical_input_sha256=canonical_input_sha256,
        preview_sha256=scientific_digest(preview_payload),
        eligibility_changed=baseline.eligibility != proposed.eligibility,
        table_count_delta=table_count_delta,
        baseline=baseline,
        proposed=proposed,
        limitations=[
            "Preview only; no review, corpus, analysis, retrieval, or publication record was changed.",
            "Metrics describe assigned sequence-read composition, not organism abundance.",
            "Taxonomic accuracy and contamination clearance are not assessed.",
            "Environmental observations and CTD/SST linkage are not included.",
        ],
    )
