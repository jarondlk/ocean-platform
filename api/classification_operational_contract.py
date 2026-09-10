"""Immutable binding between review outcomes and application-ledger receipts."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from db.app_models import (
    ClassificationApplication,
    ClassificationApplicationEvent,
    ClassificationReview,
    ClassificationReviewEvent,
)


OPERATIONAL_EVENT_TYPES = frozenset({"applied", "failed"})
TERMINAL_EVENT_TYPES = frozenset({"run_applied", "run_rolled_back", "run_failed"})
RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "application_id",
        "application_event_id",
        "application_event_sequence",
        "application_event_sha256",
        "operation_id",
        "review_id",
        "approved_review_version",
        "expected_review_version",
        "review_content_sha256",
        "workload_actor_user_id",
        "workload_actor_identity",
        "terminal_event_type",
        "application_status",
        "stage",
        "stage_result",
        "error_code",
        "recovery",
    }
)


class OperationalContractError(ValueError):
    """An operational review event is not backed by its claimed ledger row."""


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def application_event_payload(event: ClassificationApplicationEvent) -> dict[str, Any]:
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


def application_event_sha256(event: ClassificationApplicationEvent) -> str:
    return hashlib.sha256(_canonical(application_event_payload(event))).hexdigest()


def operational_receipt_details(
    application: ClassificationApplication,
    terminal_event: ClassificationApplicationEvent,
    *,
    expected_review_version: int,
) -> dict[str, Any]:
    if terminal_event.application_id != application.id:
        raise OperationalContractError("Terminal event belongs to another application")
    if terminal_event.event_type not in TERMINAL_EVENT_TYPES:
        raise OperationalContractError("Application event is not terminal")
    status = {
        "run_applied": "applied",
        "run_rolled_back": "rolled_back",
        "run_failed": "failed",
    }[terminal_event.event_type]
    stage = terminal_event.stage or "finalize"
    return {
        "schema_version": 1,
        "application_id": str(application.id),
        "application_event_id": str(terminal_event.id),
        "application_event_sequence": terminal_event.sequence,
        "application_event_sha256": terminal_event.event_sha256,
        "operation_id": application.operation_id,
        "review_id": str(application.review_id),
        "approved_review_version": application.review_version,
        "expected_review_version": expected_review_version,
        "review_content_sha256": application.review_content_sha256,
        "workload_actor_user_id": str(application.actor_user_id),
        "workload_actor_identity": dict(application.actor_identity_json),
        "terminal_event_type": terminal_event.event_type,
        "application_status": status,
        "stage": stage,
        "stage_result": dict(terminal_event.result_json or {}),
        "error_code": terminal_event.error_code,
        "recovery": list(terminal_event.recovery_json or []),
    }


def validate_operational_event_binding(
    session: Session,
    review: ClassificationReview,
    review_event: ClassificationReviewEvent,
) -> None:
    """Fail unless an operational review event exactly matches a durable receipt."""
    if review_event.event_type not in OPERATIONAL_EVENT_TYPES:
        return
    details = review_event.details_json
    if not isinstance(details, dict) or set(details) != RECEIPT_KEYS:
        raise OperationalContractError("Operational receipt has an invalid shape")
    try:
        application_id = uuid.UUID(details["application_id"])
        application_event_id = uuid.UUID(details["application_event_id"])
    except (AttributeError, TypeError, ValueError) as exc:
        raise OperationalContractError("Operational receipt identifiers are invalid") from exc
    application = session.get(ClassificationApplication, application_id)
    terminal_event = session.get(ClassificationApplicationEvent, application_event_id)
    if application is None or terminal_event is None:
        raise OperationalContractError("Operational receipt ledger row is missing")
    try:
        expected = operational_receipt_details(
            application,
            terminal_event,
            expected_review_version=review_event.sequence - 1,
        )
    except OperationalContractError:
        raise
    if details != expected:
        raise OperationalContractError("Operational receipt does not match the application ledger")
    if terminal_event.event_sha256 != application_event_sha256(terminal_event):
        raise OperationalContractError("Operational application receipt failed integrity validation")
    if (
        application.review_id != review.id
        or application.review_content_sha256 != review.content_sha256
        or application.source_snapshot_id != review.source_snapshot_id
        or application.sample_id != review.sample_id
        or application.review_version > details["expected_review_version"]
        or review_event.actor_user_id != application.actor_user_id
        or review_event.actor_identity_json != application.actor_identity_json
        or review_event.review_snapshot_json.get("application_reference")
        != application.operation_id
    ):
        raise OperationalContractError("Operational receipt identity does not match the review")
    expected_types = (
        {"run_applied", "run_rolled_back"}
        if review_event.event_type == "applied"
        else {"run_failed"}
    )
    snapshot = review_event.review_snapshot_json
    if terminal_event.event_type not in expected_types:
        raise OperationalContractError("Operational receipt outcome does not match the review event")
    if review_event.event_type == "applied":
        if snapshot.get("failure_code") is not None or snapshot.get("failure_detail") is not None:
            raise OperationalContractError("Applied receipt contains failure fields")
    elif (
        snapshot.get("failure_code") != terminal_event.error_code
        or snapshot.get("failure_detail")
        != f"Controlled application stopped at {terminal_event.stage}."
    ):
        raise OperationalContractError("Failed receipt does not match the terminal failure")
