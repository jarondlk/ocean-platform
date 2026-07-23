"""Small single-process rate limiter for the invite-only MVP deployment."""
from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple


@dataclass(frozen=True)
class RateLimitPolicy:
    scope: str
    limit: int
    window_seconds: int = 60


def policy_for_request(method: str, path: str) -> Optional[RateLimitPolicy]:
    method = method.upper()
    if method == "POST" and path == "/chat":
        return RateLimitPolicy("chat", 10)
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
    if method == "POST" and path == "/database/query":
        return RateLimitPolicy("database_query", 30)
    return None


class InMemoryRateLimiter:
    """Sliding-window limiter suitable for the current one-process server.

    A shared backing store is required before the API is scaled to multiple
    workers or hosts.
    """

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


rate_limiter = InMemoryRateLimiter()
