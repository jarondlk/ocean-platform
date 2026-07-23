"""Administrator review and export endpoints for chat feedback."""
from __future__ import annotations

import csv
import io
import json
import uuid
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from api.auth import (
    CurrentUser,
    VALID_ACCOUNT_TYPES,
    VALID_ROLES,
    get_current_user,
)
from api.feedback_routes import REASON_CODES
from api.schemas import (
    AdminFeedbackDetail,
    AdminFeedbackListItem,
    AdminFeedbackListResponse,
    AdminFeedbackMetrics,
)
from db.app_models import AppUser, AuditEvent, ChatFeedback, ChatInteraction
from db.connection import get_session


router = APIRouter(prefix="/admin/feedback", tags=["admin feedback"])

VALID_REASON_CODES = frozenset().union(*REASON_CODES.values())
FeedbackRow = Tuple[ChatFeedback, ChatInteraction, AppUser]


def _validate_filters(
    *,
    rating: Optional[int],
    reason_code: Optional[str],
    role: Optional[str],
    account_type: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
) -> None:
    if rating is not None and rating not in {-1, 1}:
        raise HTTPException(status_code=422, detail="Rating must be -1 or 1")
    if reason_code is not None and reason_code not in VALID_REASON_CODES:
        raise HTTPException(status_code=422, detail="Unknown feedback reason")
    if role is not None and role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Unknown role")
    if account_type is not None and account_type not in VALID_ACCOUNT_TYPES:
        raise HTTPException(status_code=422, detail="Unknown account type")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="Start date must not be after end date",
        )


def _feedback_conditions(
    *,
    rating: Optional[int],
    reason_code: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    model: Optional[str],
    role: Optional[str],
    account_type: Optional[str],
    search: Optional[str],
) -> List[Any]:
    conditions: List[Any] = []
    if rating is not None:
        conditions.append(ChatFeedback.rating == rating)
    if reason_code is not None:
        # Values come from a fixed allow-list. Quoting the JSON string avoids
        # partial matches such as "clear" matching "unclear".
        conditions.append(
            cast(ChatFeedback.reason_codes, String).like(
                f'%"{reason_code}"%'
            )
        )
    if date_from is not None:
        conditions.append(
            ChatFeedback.created_at
            >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        )
    if date_to is not None:
        conditions.append(
            ChatFeedback.created_at
            < datetime.combine(
                date_to + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
            )
        )
    if model:
        conditions.append(ChatInteraction.model == model.strip())
    if role:
        conditions.append(AppUser.role == role)
    if account_type:
        conditions.append(AppUser.account_type == account_type)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        conditions.append(
            or_(
                ChatInteraction.query.ilike(pattern),
                ChatInteraction.answer.ilike(pattern),
                ChatFeedback.comment.ilike(pattern),
                AppUser.email.ilike(pattern),
                AppUser.display_name.ilike(pattern),
            )
        )
    return conditions


def _joined_feedback_query():
    return (
        select(ChatFeedback, ChatInteraction, AppUser)
        .join(
            ChatInteraction,
            ChatInteraction.id == ChatFeedback.interaction_id,
        )
        .join(AppUser, AppUser.id == ChatFeedback.user_id)
    )


def _item_from_row(row: FeedbackRow) -> AdminFeedbackListItem:
    feedback, interaction, user = row
    return AdminFeedbackListItem(
        feedback_id=feedback.id,
        interaction_id=interaction.id,
        rating=feedback.rating,
        reason_codes=list(feedback.reason_codes or []),
        comment=feedback.comment,
        feedback_created_at=feedback.created_at,
        feedback_updated_at=feedback.updated_at,
        query=interaction.query,
        model=interaction.model,
        latency_ms=interaction.latency_ms,
        interaction_created_at=interaction.created_at,
        user_id=user.id,
        user_email=user.email,
        user_display_name=user.display_name,
        user_role=user.role,
        user_account_type=user.account_type,
    )


def _detail_from_row(row: FeedbackRow) -> AdminFeedbackDetail:
    feedback, interaction, _user = row
    item = _item_from_row(row)
    return AdminFeedbackDetail(
        **item.model_dump(),
        interaction_status=interaction.status,
        answer=interaction.answer,
        request_options=interaction.request_options or {},
        evidence_snapshot=interaction.evidence_snapshot or {},
        answer_audit_snapshot=interaction.answer_audit_snapshot,
        corpus_fingerprint=interaction.corpus_fingerprint,
        prompt_version=interaction.prompt_version,
        prompt_sha256=interaction.prompt_sha256,
    )


def _metrics(
    session: Session,
    conditions: Sequence[Any],
) -> AdminFeedbackMetrics:
    total, positive, negative = session.execute(
        select(
            func.count(ChatFeedback.id),
            func.coalesce(
                func.sum(case((ChatFeedback.rating == 1, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((ChatFeedback.rating == -1, 1), else_=0)),
                0,
            ),
        )
        .select_from(ChatFeedback)
        .join(
            ChatInteraction,
            ChatInteraction.id == ChatFeedback.interaction_id,
        )
        .join(AppUser, AppUser.id == ChatFeedback.user_id)
        .where(*conditions)
    ).one()
    reason_rows = session.scalars(
        select(ChatFeedback.reason_codes)
        .select_from(ChatFeedback)
        .join(
            ChatInteraction,
            ChatInteraction.id == ChatFeedback.interaction_id,
        )
        .join(AppUser, AppUser.id == ChatFeedback.user_id)
        .where(*conditions)
    ).all()
    reason_counts: Counter[str] = Counter()
    for codes in reason_rows:
        reason_counts.update(codes or [])
    return AdminFeedbackMetrics(
        total=int(total or 0),
        positive=int(positive or 0),
        negative=int(negative or 0),
        positive_rate=(
            round(int(positive or 0) / int(total), 4) if total else None
        ),
        reason_counts=dict(
            sorted(
                reason_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
    )


def _filter_metadata(
    *,
    rating: Optional[int],
    reason_code: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    model: Optional[str],
    role: Optional[str],
    account_type: Optional[str],
    search: Optional[str],
) -> Dict[str, Any]:
    return {
        key: value.isoformat() if isinstance(value, date) else value
        for key, value in {
            "rating": rating,
            "reason_code": reason_code,
            "date_from": date_from,
            "date_to": date_to,
            "model": model,
            "role": role,
            "account_type": account_type,
            "search": search,
        }.items()
        if value not in {None, ""}
    }


def _csv_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        text_value = "; ".join(str(item) for item in value)
    elif isinstance(value, dict):
        text_value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif isinstance(value, (datetime, date)):
        text_value = value.isoformat()
    else:
        text_value = str(value)
    if text_value.startswith(("=", "+", "-", "@")):
        return f"'{text_value}"
    return text_value


def _validated_conditions(
    *,
    rating: Optional[int],
    reason_code: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    model: Optional[str],
    role: Optional[str],
    account_type: Optional[str],
    search: Optional[str],
) -> List[Any]:
    _validate_filters(
        rating=rating,
        reason_code=reason_code,
        role=role,
        account_type=account_type,
        date_from=date_from,
        date_to=date_to,
    )
    return _feedback_conditions(
        rating=rating,
        reason_code=reason_code,
        date_from=date_from,
        date_to=date_to,
        model=model,
        role=role,
        account_type=account_type,
        search=search,
    )


@router.get("", response_model=AdminFeedbackListResponse)
def list_admin_feedback(
    rating: Optional[int] = Query(default=None),
    reason_code: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    model: Optional[str] = Query(default=None, max_length=255),
    role: Optional[str] = Query(default=None),
    account_type: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _actor: CurrentUser = Depends(get_current_user),
) -> AdminFeedbackListResponse:
    conditions = _validated_conditions(
        rating=rating,
        reason_code=reason_code,
        date_from=date_from,
        date_to=date_to,
        model=model,
        role=role,
        account_type=account_type,
        search=search,
    )
    with get_session() as session:
        metrics = _metrics(session, conditions)
        rows = session.execute(
            _joined_feedback_query()
            .where(*conditions)
            .order_by(
                ChatFeedback.created_at.desc(),
                ChatFeedback.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return AdminFeedbackListResponse(
            items=[_item_from_row(row) for row in rows],
            total=metrics.total,
            limit=limit,
            offset=offset,
            metrics=metrics,
        )


@router.get("/export")
def export_admin_feedback(
    rating: Optional[int] = Query(default=None),
    reason_code: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    model: Optional[str] = Query(default=None, max_length=255),
    role: Optional[str] = Query(default=None),
    account_type: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=200),
    actor: CurrentUser = Depends(get_current_user),
) -> Response:
    conditions = _validated_conditions(
        rating=rating,
        reason_code=reason_code,
        date_from=date_from,
        date_to=date_to,
        model=model,
        role=role,
        account_type=account_type,
        search=search,
    )
    export_limit = 10_000
    with get_session() as session:
        rows = session.execute(
            _joined_feedback_query()
            .where(*conditions)
            .order_by(
                ChatFeedback.created_at.desc(),
                ChatFeedback.id.desc(),
            )
            .limit(export_limit + 1)
        ).all()
        truncated = len(rows) > export_limit
        rows = rows[:export_limit]

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "feedback_id",
                "interaction_id",
                "rating",
                "reason_codes",
                "comment",
                "feedback_created_at",
                "user_email",
                "user_role",
                "user_account_type",
                "query",
                "answer",
                "model",
                "latency_ms",
            ]
        )
        for feedback, interaction, user in rows:
            writer.writerow(
                [
                    _csv_safe(feedback.id),
                    _csv_safe(interaction.id),
                    _csv_safe(feedback.rating),
                    _csv_safe(feedback.reason_codes or []),
                    _csv_safe(feedback.comment),
                    _csv_safe(feedback.created_at),
                    _csv_safe(user.email),
                    _csv_safe(user.role),
                    _csv_safe(user.account_type),
                    _csv_safe(interaction.query),
                    _csv_safe(interaction.answer),
                    _csv_safe(interaction.model),
                    _csv_safe(interaction.latency_ms),
                ]
            )

        session.add(
            AuditEvent(
                actor_user_id=(
                    actor.id if actor.auth_provider != "disabled" else None
                ),
                action="admin.feedback_exported",
                target_type="chat_feedback",
                metadata_json={
                    "filters": _filter_metadata(
                        rating=rating,
                        reason_code=reason_code,
                        date_from=date_from,
                        date_to=date_to,
                        model=model,
                        role=role,
                        account_type=account_type,
                        search=search,
                    ),
                    "row_count": len(rows),
                    "truncated": truncated,
                },
            )
        )

        filename = f"chat-feedback-{date.today().isoformat()}.csv"
        return Response(
            content="\ufeff" + output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{filename}"'
                ),
                "X-Export-Truncated": "true" if truncated else "false",
            },
        )


@router.get("/{feedback_id}", response_model=AdminFeedbackDetail)
def get_admin_feedback(
    feedback_id: uuid.UUID,
    _actor: CurrentUser = Depends(get_current_user),
) -> AdminFeedbackDetail:
    with get_session() as session:
        row = session.execute(
            _joined_feedback_query().where(
                ChatFeedback.id == feedback_id
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Feedback not found")
        return _detail_from_row(row)
