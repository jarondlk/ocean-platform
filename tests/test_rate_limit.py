import uuid

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import api.auth as api_auth
from api.auth import CurrentUser, ROLE_PERMISSIONS
from api.main import app
from api.rate_limit import (
    InMemoryRateLimiter,
    PostgresRateLimiter,
    policy_for_request,
)


def test_expensive_and_mutating_routes_have_scoped_limits():
    assert policy_for_request("POST", "/chat").scope == "chat"
    assert policy_for_request(
        "PUT",
        "/chat/interactions/interaction-id/feedback",
    ).scope == "feedback"
    assert policy_for_request("POST", "/pipeline/jobs").limit == 2
    assert policy_for_request("GET", "/chat") is None
    assert policy_for_request("GET", "/admin/users") is None


def test_rate_limiter_isolated_by_user_and_resets_after_window():
    limiter = InMemoryRateLimiter()
    policy = policy_for_request("POST", "/pipeline/jobs")

    assert limiter.retry_after(subject="admin-a", policy=policy, now=0) is None
    assert limiter.retry_after(subject="admin-a", policy=policy, now=1) is None
    assert limiter.retry_after(subject="admin-a", policy=policy, now=2) == 58
    assert limiter.retry_after(subject="admin-b", policy=policy, now=2) is None
    assert limiter.retry_after(subject="admin-a", policy=policy, now=61) is None


def test_postgres_rate_limiter_hashes_subject_and_uses_shared_counter():
    captured = {}

    class Result:
        def mappings(self):
            return self

        def one(self):
            return {"request_count": 3, "retry_after": 42}

    class Connection:
        def execute(self, _statement, params):
            captured.update(params)
            return Result()

    class Begin:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    class Engine:
        def begin(self):
            return Begin()

    limiter = PostgresRateLimiter(engine_factory=lambda: Engine())
    policy = policy_for_request("POST", "/pipeline/jobs")

    assert limiter.retry_after(subject="private-user-id", policy=policy) == 42
    assert captured["subject_hash"] != "private-user-id"
    assert len(captured["subject_hash"]) == 64


def test_postgres_rate_limiter_fails_closed_when_storage_is_unavailable():
    class Begin:
        def __enter__(self):
            raise OperationalError("select", {}, RuntimeError("offline"))

        def __exit__(self, *_args):
            return False

    class Engine:
        def begin(self):
            return Begin()

    limiter = PostgresRateLimiter(engine_factory=lambda: Engine())
    policy = policy_for_request("POST", "/chat")

    assert limiter.retry_after(subject="user", policy=policy) == 60


def test_production_middleware_returns_retry_after(monkeypatch):
    admin = CurrentUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name=None,
        role="admin",
        account_type="internal",
        status="active",
        permissions=ROLE_PERMISSIONS["admin"],
        auth_provider="oidc",
    )
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    monkeypatch.setattr(
        api_auth,
        "authenticate_request",
        lambda _request: admin,
    )
    limiter = InMemoryRateLimiter()
    monkeypatch.setattr(api_auth, "rate_limiter", limiter)
    client = TestClient(app)
    first = client.post("/pipeline/jobs", json={})
    second = client.post("/pipeline/jobs", json={})
    limited = client.post("/pipeline/jobs", json={})

    assert first.status_code == 422
    assert second.status_code == 422
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.headers["cache-control"] == "no-store"
