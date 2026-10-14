"""Administrative legal-hold controls for chat retention."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update

from api.auth import CurrentUser, get_current_user
from api.schemas import RetentionHoldRequest, RetentionHoldResponse
from db.app_models import AuditEvent, ChatInteraction
from db.connection import get_session


router = APIRouter(prefix="/admin/retention", tags=["retention"])


@router.patch(
    "/interactions/{interaction_id}/hold",
    response_model=RetentionHoldResponse,
)
def set_interaction_legal_hold(
    interaction_id: uuid.UUID,
    request: RetentionHoldRequest,
    user: CurrentUser = Depends(get_current_user),
) -> RetentionHoldResponse:
    with get_session() as session:
        # Coordinate directly with cleanup's conditional DELETE. A deletion that
        # commits first returns no row, so it cannot receive a success audit.
        interaction = session.execute(
            update(ChatInteraction)
            .where(ChatInteraction.id == interaction_id)
            .values(legal_hold=request.legal_hold)
            .returning(ChatInteraction.id, ChatInteraction.legal_hold)
            .execution_options(synchronize_session=False)
        ).one_or_none()
        if interaction is None:
            raise HTTPException(status_code=404, detail="Chat interaction not found")

        session.add(
            AuditEvent(
                actor_user_id=user.id if user.auth_provider != "disabled" else None,
                action=(
                    "admin.retention_hold_enabled"
                    if request.legal_hold
                    else "admin.retention_hold_disabled"
                ),
                target_type="chat_interaction",
                target_id=str(interaction_id),
                metadata_json={"legal_hold": request.legal_hold},
            )
        )
        session.flush()
        updated_at = datetime.now(timezone.utc)
        return RetentionHoldResponse(
            interaction_id=interaction.id,
            legal_hold=interaction.legal_hold,
            updated_at=updated_at,
        )
