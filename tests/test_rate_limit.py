import uuid

from fastapi.testclient import TestClient

import api.auth as api_auth
from api.auth import CurrentUser, ROLE_PERMISSIONS
from api.main import app
from api.rate_limit import InMemoryRateLimiter, policy_for_request
from api.rate_limit import rate_limiter


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
    rate_limiter.reset()
    client = TestClient(app)
    try:
        first = client.post("/pipeline/jobs", json={})
        second = client.post("/pipeline/jobs", json={})
        limited = client.post("/pipeline/jobs", json={})
    finally:
        rate_limiter.reset()

    assert first.status_code == 422
    assert second.status_code == 422
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.headers["cache-control"] == "no-store"
