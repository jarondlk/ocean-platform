"""Transactional retention cleanup for completed chat interactions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select

from db.app_models import AuditEvent, ChatInteraction
from db.connection import get_session


@dataclass(frozen=True)
class RetentionCleanupReport:
    cutoff: datetime
    retention_days: int
    eligible_count: int
    deleted_count: int
    dry_run: bool


def cleanup_chat_interactions(
    *,
    retention_days: int,
    dry_run: bool = True,
    now: Optional[datetime] = None,
) -> RetentionCleanupReport:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=retention_days)

    with get_session() as session:
        conditions = (
            ChatInteraction.created_at < cutoff,
            ChatInteraction.status.in_(("completed", "failed")),
            ChatInteraction.legal_hold.is_(False),
        )
        eligible_count = int(
            session.scalar(
                select(func.count(ChatInteraction.id)).where(*conditions)
            )
            or 0
        )
        if dry_run or eligible_count == 0:
            return RetentionCleanupReport(
                cutoff=cutoff,
                retention_days=retention_days,
                eligible_count=eligible_count,
                deleted_count=0,
                dry_run=dry_run,
            )

        interactions = list(
            session.scalars(select(ChatInteraction).where(*conditions)).all()
        )
        for interaction in interactions:
            session.delete(interaction)
        session.flush()
        session.add(
            AuditEvent(
                action="retention.chat_interactions_deleted",
                target_type="chat_interaction",
                target_id="batch",
                metadata_json={
                    "cutoff": cutoff.isoformat(),
                    "retention_days": retention_days,
                    "deleted_count": len(interactions),
                },
            )
        )
        return RetentionCleanupReport(
            cutoff=cutoff,
            retention_days=retention_days,
            eligible_count=eligible_count,
            deleted_count=len(interactions),
            dry_run=False,
        )
