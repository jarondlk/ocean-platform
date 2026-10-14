import asyncio
import hashlib
import threading
import uuid

import anyio
import pytest

from fastapi import Request
from fastapi.responses import JSONResponse
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
    assert policy_for_request("POST", "/retrieve").scope == "retrieval"
    assert policy_for_request("GET", "/documents").limit == 30
    assert policy_for_request(
        "PUT",
        "/chat/interactions/interaction-id/feedback",
    ).scope == "feedback"
    assert policy_for_request("POST", "/pipeline/jobs").limit == 2
    assert policy_for_request(
        "POST", "/classification-reviews/review-id/decision"
    ).scope == "classification_mutation"
    assert policy_for_request(
        "POST", "/classification-reviews/review-id/preview"
    ).scope == "classification_preview"
    assert policy_for_request(
        "POST", "/classification-reviews/review-id/preview"
    ).limit == 10
    assert policy_for_request("GET", "/chat") is None
    assert policy_for_request("GET", "/admin/users") is None


def test_retrieval_rate_limit_is_isolated_by_user():
    limiter = InMemoryRateLimiter()
    policy = policy_for_request("POST", "/retrieve")

    for request_index in range(policy.limit):
        assert limiter.retry_after(subject="researcher-a", policy=policy, now=request_index) is None
    assert limiter.retry_after(subject="researcher-a", policy=policy, now=policy.limit) == 30
    assert limiter.retry_after(subject="researcher-b", policy=policy, now=policy.limit) is None


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


def _limiter_user(identity: str = "limiter-user") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid5(uuid.NAMESPACE_URL, identity),
        email=f"{identity}@example.org",
        display_name=None,
        role="admin",
        account_type="internal",
        status="active",
        permissions=ROLE_PERMISSIONS["admin"],
        auth_provider="oidc",
    )


def _limiter_request(path: str = "/chat", identity: str = "limiter-user") -> Request:
    return Request({
        "type": "http",
        "method": "POST" if path == "/chat" else "GET",
        "path": path,
        "query_string": b"",
        "headers": [(b"x-test-identity", identity.encode())],
        "scheme": "http",
        "server": ("test", 80),
    })


class _GatedRateLimitStore:
    """A fake DB transaction used by the real PostgreSQL limiter.

    Worker entry wakes an event-loop observer. The transaction cannot finish
    until that observer releases it; a same-thread call fails immediately so
    regression runs cannot deadlock the event loop.
    """

    def __init__(self, *, request_count: int = 1, fail: bool = False):
        self.loop = asyncio.get_running_loop()
        self.loop_thread = threading.get_ident()
        self.entered = anyio.Event()
        self.closed = anyio.Event()
        self.release = threading.Event()
        self.calls = []
        self.parameters = None
        self.request_count = request_count
        self.fail = fail

    def _record(self, stage: str) -> None:
        self.calls.append((stage, threading.get_ident()))

    def engine(self):
        self._record("engine")
        return self

    def begin(self):
        self._record("begin")
        return self

    def __enter__(self):
        self._record("enter")
        return self

    def execute(self, _statement, parameters):
        self._record("execute")
        self.parameters = parameters
        assert threading.get_ident() != self.loop_thread, (
            "Production rate limiting blocked the event-loop thread"
        )
        self.loop.call_soon_threadsafe(self.entered.set)
        assert self.release.wait(10), "Test did not release the rate-limit worker"
        if self.fail:
            raise OperationalError("select", {}, RuntimeError("private DB details"))
        return self

    def mappings(self):
        self._record("mappings")
        return self

    def one(self):
        self._record("one")
        return {"request_count": self.request_count, "retry_after": 42}

    def __exit__(self, *_args):
        self._record("exit")
        self.loop.call_soon_threadsafe(self.closed.set)
        return False

    def assert_worker_lifetime(self):
        assert [stage for stage, _thread in self.calls] == (
            ["engine", "begin", "enter", "execute", "exit"] if self.fail else
            ["engine", "begin", "enter", "execute", "mappings", "one", "exit"]
        )
        worker_threads = {thread for _stage, thread in self.calls}
        assert len(worker_threads) == 1
        assert self.loop_thread not in worker_threads
        assert self.closed.is_set()


def _install_gated_limiter(monkeypatch, store):
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    monkeypatch.setattr(
        api_auth,
        "authenticate_request",
        lambda request: _limiter_user(request.headers["x-test-identity"]),
    )
    monkeypatch.setattr(
        api_auth,
        "rate_limiter",
        PostgresRateLimiter(engine_factory=store.engine),
    )


def test_delayed_production_limiter_allows_heartbeat_and_other_requests(monkeypatch):
    async def scenario():
        store = _GatedRateLimitStore()
        _install_gated_limiter(monkeypatch, store)
        heartbeat = anyio.Event()
        slow_done = anyio.Event()
        handled = []
        slow_request = _limiter_request()

        async def handler(request):
            handled.append(request.url.path)
            return JSONResponse({"path": request.url.path})

        async def slow_request_task():
            response = await api_auth.authorization_middleware(slow_request, handler)
            assert response.status_code == 200
            assert slow_request.state.current_user == _limiter_user()
            slow_done.set()

        async def heartbeat_task():
            await anyio.lowlevel.checkpoint()
            heartbeat.set()

        try:
            with anyio.fail_after(5):
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(slow_request_task)
                    try:
                        await store.entered.wait()
                        tasks.start_soon(heartbeat_task)
                        live_request = _limiter_request("/health/live")
                        live_response = await api_auth.authorization_middleware(
                            live_request, handler,
                        )
                        independent_request = _limiter_request("/me", "independent-user")
                        independent_response = await api_auth.authorization_middleware(
                            independent_request, handler,
                        )
                        await heartbeat.wait()
                        assert live_response.status_code == 200
                        assert live_response.headers["x-content-type-options"] == "nosniff"
                        assert independent_response.status_code == 200
                        assert independent_request.state.current_user == _limiter_user(
                            "independent-user",
                        )
                        assert not hasattr(live_request.state, "current_user")
                        assert not hasattr(slow_request.state, "current_user")
                        assert not slow_done.is_set()
                        assert not store.release.is_set()
                        assert handled == ["/health/live", "/me"]
                        store.release.set()
                        await slow_done.wait()
                    finally:
                        # Release before TaskGroup waits for shielded workers,
                        # including when an observer or assertion fails.
                        store.release.set()
        finally:
            store.release.set()

        store.assert_worker_lifetime()
        assert store.parameters == {
            "scope": "chat",
            "subject_hash": hashlib.sha256(str(_limiter_user().id).encode()).hexdigest(),
            "window_seconds": 60,
        }
        assert handled == ["/health/live", "/me", "/chat"]

    anyio.run(scenario)


@pytest.mark.parametrize("cancellation", ["asyncio", "anyio"])
def test_cancelled_production_limiter_closes_worker_transaction_without_handler(
    monkeypatch, cancellation,
):
    async def scenario():
        store = _GatedRateLimitStore()
        _install_gated_limiter(monkeypatch, store)
        request = _limiter_request()
        handled = []
        task = None

        async def handler(_request):
            handled.append(True)
            return JSONResponse({"unexpected": True})

        async def authorize():
            await api_auth.authorization_middleware(request, handler)

        try:
            with anyio.fail_after(5):
                if cancellation == "asyncio":
                    task = asyncio.create_task(authorize())
                    await store.entered.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    store.release.set()
                    await store.closed.wait()
                else:
                    async with anyio.create_task_group() as tasks:
                        tasks.start_soon(authorize)
                        try:
                            await store.entered.wait()
                            tasks.cancel_scope.cancel()
                        finally:
                            store.release.set()
                    await store.closed.wait()
        finally:
            store.release.set()
            # A failed entry observer or cancellation assertion must not leave
            # a native task or its worker callbacks alive after anyio.run ends.
            with anyio.CancelScope(shield=True):
                with anyio.fail_after(5):
                    if task is not None:
                        if not task.done():
                            task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                    await anyio.lowlevel.checkpoint()
                    if store.entered.is_set():
                        await store.closed.wait()

        store.assert_worker_lifetime()
        assert handled == []
        assert not hasattr(request.state, "current_user")

    anyio.run(scenario)
