"""Per-identity request limits with a shared PostgreSQL production backend."""
from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import config
from db.connection import get_engine


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitPolicy:
    scope: str
    limit: int
    window_seconds: int = 60


def policy_for_request(method: str, path: str) -> Optional[RateLimitPolicy]:
    method = method.upper()
    if method == "POST" and path == "/chat":
        return RateLimitPolicy("chat", 10)
    if method == "POST" and path == "/retrieve":
        return RateLimitPolicy("retrieval", 30)
    if method == "GET" and path == "/documents":
        return RateLimitPolicy("retrieval", 30)
    if method == "PUT" and path.startswith("/chat/interactions/"):
        return RateLimitPolicy("feedback", 30)
    if method == "POST" and path == "/admin/invitations":
        return RateLimitPolicy("admin_mutation", 10)
    if method == "PATCH" and path.startswith("/admin/users/"):
        return RateLimitPolicy("admin_mutation", 10)
    if method == "POST" and path == "/pipeline/jobs":
        return RateLimitPolicy("pipeline_start", 2)
    if method == "POST" and path.startswith("/evaluation/"):
        return RateLimitPolicy("evaluation_mutation", 5)
    return None


class InMemoryRateLimiter:
    """Sliding-window limiter for isolated development and test processes."""

    def __init__(self) -> None:
        self._events: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def retry_after(
        self,
        *,
        subject: str,
        policy: RateLimitPolicy,
        now: Optional[float] = None,
    ) -> Optional[int]:
        observed_at = time.monotonic() if now is None else now
        cutoff = observed_at - policy.window_seconds
        key = (policy.scope, subject)
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= policy.limit:
                return max(
                    1,
                    math.ceil(
                        policy.window_seconds - (observed_at - events[0])
                    ),
                )
            events.append(observed_at)
            return None

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


class PostgresRateLimiter:
    """Atomic shared fixed-window limiter backed by PostgreSQL."""

    def __init__(
        self,
        engine_factory: Callable[[], Any] = get_engine,
    ) -> None:
        self._engine_factory = engine_factory

    def retry_after(
        self,
        *,
        subject: str,
        policy: RateLimitPolicy,
        now: Optional[float] = None,
    ) -> Optional[int]:
        if now is not None:
            raise ValueError("PostgresRateLimiter uses the database clock")
        subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        statement = text(
            """
            INSERT INTO rate_limit_bucket (
                scope,
                subject_hash,
                window_started_at,
                request_count,
                updated_at
            )
            VALUES (
                :scope,
                :subject_hash,
                CURRENT_TIMESTAMP,
                1,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (scope, subject_hash) DO UPDATE
            SET
                request_count = CASE
                    WHEN rate_limit_bucket.window_started_at
                         <= CURRENT_TIMESTAMP
                            - (:window_seconds * INTERVAL '1 second')
                    THEN 1
                    ELSE rate_limit_bucket.request_count + 1
                END,
                window_started_at = CASE
                    WHEN rate_limit_bucket.window_started_at
                         <= CURRENT_TIMESTAMP
                            - (:window_seconds * INTERVAL '1 second')
                    THEN CURRENT_TIMESTAMP
                    ELSE rate_limit_bucket.window_started_at
                END,
                updated_at = CURRENT_TIMESTAMP
            RETURNING
                request_count,
                GREATEST(
                    1,
                    CEIL(
                        EXTRACT(
                            EPOCH FROM (
                                window_started_at
                                + (:window_seconds * INTERVAL '1 second')
                                - CURRENT_TIMESTAMP
                            )
                        )
                    )::integer
                ) AS retry_after
            """
        )
        try:
            with self._engine_factory().begin() as connection:
                row = connection.execute(
                    statement,
                    {
                        "scope": policy.scope,
                        "subject_hash": subject_hash,
                        "window_seconds": policy.window_seconds,
                    },
                ).mappings().one()
        except SQLAlchemyError:
            logger.exception(
                "Shared rate-limit storage failed for scope %s; denying request",
                policy.scope,
            )
            return policy.window_seconds
        return (
            int(row["retry_after"])
            if int(row["request_count"]) > policy.limit
            else None
        )


class DeploymentRateLimiter:
    """Use shared storage in production and memory for local development."""

    def __init__(self) -> None:
        self._memory = InMemoryRateLimiter()
        self._postgres = PostgresRateLimiter()

    def retry_after(
        self,
        *,
        subject: str,
        policy: RateLimitPolicy,
        now: Optional[float] = None,
    ) -> Optional[int]:
        if config.production_like_environment():
            return self._postgres.retry_after(
                subject=subject,
                policy=policy,
                now=now,
            )
        return self._memory.retry_after(
            subject=subject,
            policy=policy,
            now=now,
        )

    def reset(self) -> None:
        """Reset only disposable local state; shared counters expire naturally."""
        self._memory.reset()


rate_limiter = DeploymentRateLimiter()
