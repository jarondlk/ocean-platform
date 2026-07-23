"""User-owned feedback routes for completed chat interactions."""
from __future__ import annotations

import uuid
from typing import Dict, FrozenSet, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.auth import CurrentUser, get_current_user
from api.schemas import ChatFeedbackRequest, ChatFeedbackResponse
from db.app_models import AuditEvent, ChatFeedback, ChatInteraction
from db.connection import get_session


router = APIRouter(prefix="/chat/interactions", tags=["chat feedback"])

REASON_CODES: Dict[int, FrozenSet[str]] = {
    1: frozenset({"accurate", "relevant", "well_cited", "clear", "helpful"}),
    -1: frozenset(
        {
            "incorrect",
            "missing_evidence",
            "incorrect_citation",
            "incomplete",
            "irrelevant",
            "unclear",
            "outdated",
            "other",
        }
    ),
}


def _feedback_response(feedback: ChatFeedback) -> ChatFeedbackResponse:
    return ChatFeedbackResponse(
        id=feedback.id,
        interaction_id=feedback.interaction_id,
        rating=feedback.rating,
        reason_codes=list(feedback.reason_codes or []),
        comment=feedback.comment,
        created_at=feedback.created_at,
        updated_at=feedback.updated_at,
    )


def _owned_interaction(
    session,
    *,
    interaction_id: uuid.UUID,
    user: CurrentUser,
) -> ChatInteraction:
    interaction = session.get(ChatInteraction, interaction_id)
    if interaction is None or interaction.user_id != user.id:
        # Do not disclose whether another user's interaction exists.
        raise HTTPException(status_code=404, detail="Chat interaction not found")
    return interaction


def _normalized_reasons(request: ChatFeedbackRequest) -> List[str]:
    reasons = list(dict.fromkeys(request.reason_codes))
    unknown = sorted(set(reasons) - REASON_CODES[request.rating])
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid reason code for this rating: {unknown[0]}",
        )
    if request.rating == -1 and not reasons:
        raise HTTPException(
            status_code=422,
            detail="At least one reason is required for negative feedback",
        )
    return reasons


def _set_feedback_values(
    feedback: ChatFeedback,
    *,
    request: ChatFeedbackRequest,
    reasons: List[str],
    comment: Optional[str],
) -> None:
    feedback.rating = request.rating
    feedback.reason_codes = reasons
    feedback.comment = comment


@router.get(
    "/{interaction_id}/feedback",
    response_model=Optional[ChatFeedbackResponse],
)
def get_feedback(
    interaction_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> Optional[ChatFeedbackResponse]:
    with get_session() as session:
        _owned_interaction(session, interaction_id=interaction_id, user=user)
        feedback = session.scalar(
            select(ChatFeedback).where(
                ChatFeedback.interaction_id == interaction_id,
                ChatFeedback.user_id == user.id,
            )
        )
        return _feedback_response(feedback) if feedback is not None else None


@router.put(
    "/{interaction_id}/feedback",
    response_model=ChatFeedbackResponse,
)
def put_feedback(
    interaction_id: uuid.UUID,
    request: ChatFeedbackRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ChatFeedbackResponse:
    reasons = _normalized_reasons(request)
    comment = request.comment.strip() if request.comment else None
    comment = comment or None

    with get_session() as session:
        interaction = _owned_interaction(
            session,
            interaction_id=interaction_id,
            user=user,
        )
        if interaction.status != "completed":
            raise HTTPException(
                status_code=409,
                detail="Feedback is only accepted for completed chat interactions",
            )

        feedback = session.scalar(
            select(ChatFeedback).where(
                ChatFeedback.interaction_id == interaction_id,
                ChatFeedback.user_id == user.id,
            )
        )
        previous_rating = feedback.rating if feedback is not None else None
        action = "chat.feedback_updated" if feedback is not None else "chat.feedback_created"
        if feedback is None:
            feedback = ChatFeedback(
                interaction_id=interaction_id,
                user_id=user.id,
            )
            session.add(feedback)
        _set_feedback_values(
            feedback,
            request=request,
            reasons=reasons,
            comment=comment,
        )
        try:
            session.flush()
        except IntegrityError:
            # A retry or double-submit can race another first write. Recover
            # the row created by the other transaction and apply this PUT.
            session.rollback()
            interaction = _owned_interaction(
                session,
                interaction_id=interaction_id,
                user=user,
            )
            if interaction.status != "completed":
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Feedback is only accepted for completed "
                        "chat interactions"
                    ),
                )
            feedback = session.scalar(
                select(ChatFeedback).where(
                    ChatFeedback.interaction_id == interaction_id,
                    ChatFeedback.user_id == user.id,
                )
            )
            if feedback is None:
                raise
            previous_rating = feedback.rating
            action = "chat.feedback_updated"
            _set_feedback_values(
                feedback,
                request=request,
                reasons=reasons,
                comment=comment,
            )
            session.flush()
        session.add(
            AuditEvent(
                actor_user_id=user.id,
                action=action,
                target_type="chat_feedback",
                target_id=str(feedback.id),
                metadata_json={
                    "interaction_id": str(interaction_id),
                    "rating": request.rating,
                    "previous_rating": previous_rating,
                    "reason_codes": reasons,
                    "has_comment": comment is not None,
                },
            )
        )
        session.flush()
        return _feedback_response(feedback)
