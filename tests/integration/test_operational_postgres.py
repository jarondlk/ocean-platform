"""PostgreSQL integration checks for shared operational controls."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from api.rate_limit import PostgresRateLimiter, RateLimitPolicy
from db.connection import get_engine


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Set RUN_POSTGRES_INTEGRATION=1 for PostgreSQL integration checks.",
)


def test_rate_limit_counter_is_shared_between_limiter_instances():
    scope = f"pytest_{uuid.uuid4().hex}"
    subject = str(uuid.uuid4())
    policy = RateLimitPolicy(scope=scope, limit=2, window_seconds=60)
    first_process = PostgresRateLimiter()
    second_process = PostgresRateLimiter()
    try:
        assert first_process.retry_after(
            subject=subject,
            policy=policy,
        ) is None
        assert second_process.retry_after(
            subject=subject,
            policy=policy,
        ) is None
        assert first_process.retry_after(
            subject=subject,
            policy=policy,
        ) is not None
    finally:
        with get_engine().begin() as connection:
            connection.execute(
                text("DELETE FROM rate_limit_bucket WHERE scope = :scope"),
                {"scope": scope},
            )
