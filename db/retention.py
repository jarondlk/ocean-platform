"""Transactional retention cleanup for completed chat interactions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select

from db.app_models import AuditEvent, ChatFeedback, ChatInteraction
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

        # The count is an observation, not a reservation. A committed hold or
        # status/cutoff change must still protect the row when deletion starts.
        # DELETE coordinates with the hold UPDATE on the same row, and PostgreSQL
        # rechecks this full predicate after waiting for a concurrent row writer.
        deleted_ids = list(
            session.scalars(
                delete(ChatInteraction)
                .where(*conditions)
                .returning(ChatInteraction.id)
                .execution_options(synchronize_session=False)
            ).all()
        )
        if deleted_ids:
            # PostgreSQL's FK CASCADE removes dependent feedback. Explicitly
            # remove only feedback for actually deleted parents as well, keeping
            # SQLite fixtures with foreign-key enforcement disabled compatible.
            # Both deletions and the audit commit or roll back together.
            session.execute(
                delete(ChatFeedback)
                .where(ChatFeedback.interaction_id.in_(deleted_ids))
                .execution_options(synchronize_session=False)
            )
            session.add(
                AuditEvent(
                    action="retention.chat_interactions_deleted",
                    target_type="chat_interaction",
                    target_id="batch",
                    metadata_json={
                        "cutoff": cutoff.isoformat(),
                        "retention_days": retention_days,
                        "deleted_count": len(deleted_ids),
                    },
                )
            )
        return RetentionCleanupReport(
            cutoff=cutoff,
            retention_days=retention_days,
            eligible_count=eligible_count,
            deleted_count=len(deleted_ids),
            dry_run=False,
        )
