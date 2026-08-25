"""Durable lifecycle records for authenticated chat requests."""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from api.auth import CurrentUser
from db.app_models import AppUser, ChatInteraction
from db.connection import get_session


# Existing ``onagawa-chat-v1`` rows remain unchanged as historical provenance.
PROMPT_VERSION = "ocean-chat-v1"


def json_safe(value: Any) -> Any:
    """Convert nested request/retrieval values into JSON-column-safe values."""
    if hasattr(value, "model_dump"):
        return json_safe(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        return json_safe(value.item())
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def content_sha256(value: Any) -> str:
    payload = json.dumps(
        json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _persistence_enabled(user: CurrentUser) -> bool:
    if user.auth_provider != "disabled":
        return True
    return os.environ.get("PERSIST_LOCAL_CHAT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def create_chat_interaction(
    *,
    user: CurrentUser,
    query: str,
    model: str,
    request_options: Dict[str, Any],
) -> Optional[uuid.UUID]:
    if not _persistence_enabled(user):
        return None

    interaction = ChatInteraction(
        user_id=user.id,
        status="running",
        query=query,
        model=model,
        request_options=json_safe(request_options),
        prompt_version=PROMPT_VERSION,
    )
    with get_session() as session:
        if user.auth_provider == "disabled":
            local_user = session.get(AppUser, user.id)
            if local_user is None:
                session.add(
                    AppUser(
                        id=user.id,
                        auth_provider="disabled",
                        auth_subject="local-preview",
                        email=user.email,
                        display_name=user.display_name,
                        role=user.role,
                        account_type=user.account_type,
                        status=user.status,
                    )
                )
                session.flush()
        session.add(interaction)
        session.flush()
        return interaction.id


def record_chat_context(
    *,
    interaction_id: Optional[uuid.UUID],
    user: CurrentUser,
    evidence_snapshot: Dict[str, Any],
    prompt: str,
) -> None:
    if interaction_id is None:
        return

    safe_snapshot = json_safe(evidence_snapshot)
    with get_session() as session:
        interaction = session.get(ChatInteraction, interaction_id)
        if interaction is None or interaction.user_id != user.id:
            raise RuntimeError("Chat interaction disappeared before generation")
        if interaction.status != "running":
            raise RuntimeError("Chat interaction is no longer running")
        interaction.evidence_snapshot = safe_snapshot
        interaction.corpus_fingerprint = content_sha256(safe_snapshot)
        interaction.prompt_sha256 = hashlib.sha256(
            prompt.encode("utf-8")
        ).hexdigest()


def complete_chat_interaction(
    *,
    interaction_id: Optional[uuid.UUID],
    user: CurrentUser,
    answer: str,
    answer_audit_snapshot: Optional[Dict[str, Any]],
    latency_ms: int,
) -> None:
    if interaction_id is None:
        return

    with get_session() as session:
        interaction = session.get(ChatInteraction, interaction_id)
        if interaction is None or interaction.user_id != user.id:
            raise RuntimeError("Chat interaction disappeared before completion")
        if interaction.status != "running":
            raise RuntimeError("Chat interaction is no longer running")
        interaction.status = "completed"
        interaction.answer = answer
        interaction.answer_audit_snapshot = json_safe(answer_audit_snapshot)
        interaction.latency_ms = max(0, latency_ms)
        interaction.error_code = None
        interaction.completed_at = datetime.now(timezone.utc)


def fail_chat_interaction(
    *,
    interaction_id: Optional[uuid.UUID],
    user: CurrentUser,
    error_code: str,
    latency_ms: int,
) -> None:
    if interaction_id is None:
        return

    with get_session() as session:
        interaction = session.get(ChatInteraction, interaction_id)
        if interaction is None or interaction.user_id != user.id:
            return
        if interaction.status == "completed":
            return
        interaction.status = "failed"
        interaction.error_code = error_code[:64]
        interaction.latency_ms = max(0, latency_ms)
        interaction.completed_at = datetime.now(timezone.utc)
