from __future__ import annotations

import threading
import uuid

import anyio
import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

import api.auth as api_auth
import api.main as api_main
from api.auth import CurrentUser, ROLE_PERMISSIONS
from api.rate_limit import PostgresRateLimiter
import model_runtime


class _IdentifierPreparer:
    @staticmethod
    def quote(identifier: str) -> str:
        return f'"{identifier}"'


class _Dialect:
    identifier_preparer = _IdentifierPreparer()


class _ScalarResult:
    @staticmethod
    def scalar() -> int:
        return 1


class _RowsResult:
    @staticmethod
    def mappings() -> "_RowsResult":
        return _RowsResult()

    @staticmethod
    def all() -> list[dict[str, object]]:
        return []


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: object, _parameters: object = None) -> object:
        rendered = str(statement)
        self.statements.append(rendered)
        if rendered.startswith("SELECT count(*)"):
            return _ScalarResult()
        return _RowsResult()


class _Engine:
    dialect = _Dialect()

    def __init__(self) -> None:
        self.connection = _Connection()

    def connect(self) -> _Connection:
        return self.connection


def test_database_table_uses_constant_sort_tokens(monkeypatch: pytest.MonkeyPatch):
    engine = _Engine()
    monkeypatch.setattr(api_main, "_database_engine", lambda: engine)
    monkeypatch.setattr(
        api_main,
        "_validate_table_and_columns",
        lambda _engine, _table: ["id", "name"],
    )

    api_main.database_table(
        table_name="records",
        limit=25,
        offset=0,
        order_by="name",
        direction="desc",
        include_heavy=False,
    )

    assert 'ORDER BY "name" DESC' in engine.connection.statements[1]


def test_database_table_rejects_non_constant_sort_direction(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = _Engine()
    monkeypatch.setattr(api_main, "_database_engine", lambda: engine)
    monkeypatch.setattr(
        api_main,
        "_validate_table_and_columns",
        lambda _engine, _table: ["id", "name"],
    )

    with pytest.raises(HTTPException, match="Unknown sort direction"):
        api_main.database_table(
            table_name="records",
            limit=25,
            offset=0,
            order_by="name",
            direction="desc; drop table records",
            include_heavy=False,
        )

    assert engine.connection.statements == []


def test_dependency_errors_do_not_expose_exception_details(
    monkeypatch: pytest.MonkeyPatch,
):
    sensitive_detail = "postgresql://admin:secret@internal-db/private"

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(sensitive_detail)

    monkeypatch.setattr(api_main, "create_engine", fail)
    monkeypatch.setattr(model_runtime.requests, "get", fail)

    database = api_main._database_status()
    ollama = api_main._ollama_status()
    model_status = api_main.models()

    assert database == {
        "available": False,
        "error": "Database is unavailable",
    }
    assert ollama["error"] == "Model runtime is unavailable"
    assert model_status.error == "Model discovery is unavailable"
    assert sensitive_detail not in repr((database, ollama, model_status))


def test_database_schema_errors_do_not_expose_exception_details(
    monkeypatch: pytest.MonkeyPatch,
):
    sensitive_detail = "postgresql://admin:secret@internal-db/private"

    def fail() -> None:
        raise RuntimeError(sensitive_detail)

    monkeypatch.setattr(api_main, "_database_engine", fail)

    response = api_main.database_schema()

    assert response.available is False
    assert response.error == "Database schema is unavailable"
    assert sensitive_detail not in repr(response)


def test_free_form_database_query_route_is_not_registered():
    assert "/database/query" not in {
        getattr(route, "path", "")
        for route in api_main.app.routes
    }


@pytest.mark.parametrize(
    ("error_stage", "expected_retry_after"),
    [(None, "42"), ("enter", "60"), ("execute", "60"), ("exit", "60")],
)
def test_production_limiter_denials_preserve_headers_and_never_call_handler(
    monkeypatch: pytest.MonkeyPatch, error_stage: str | None,
    expected_retry_after: str,
):
    """Quota and SQL failures keep the same fail-closed HTTP boundary."""
    user = CurrentUser(
        id=uuid.uuid4(),
        email="limited@example.org",
        display_name=None,
        role="admin",
        account_type="internal",
        status="active",
        permissions=ROLE_PERMISSIONS["admin"],
        auth_provider="oidc",
    )
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    monkeypatch.setattr(api_auth, "authenticate_request", lambda _request: user)

    async def scenario():
        loop_thread = threading.get_ident()
        stages = []

        class Engine:
            def record(self, stage):
                stages.append((stage, threading.get_ident()))
                if error_stage == stage:
                    raise OperationalError(
                        "select", {}, RuntimeError("private storage connection details"),
                    )

            def begin(self):
                self.record("begin")
                return self

            def __enter__(self):
                self.record("enter")
                return self

            def execute(self, _statement, _parameters):
                self.record("execute")
                return self

            def mappings(self):
                return self

            def one(self):
                # POST /chat permits ten requests in the existing shared policy.
                return {"request_count": 11, "retry_after": 42}

            def __exit__(self, *_args):
                self.record("exit")
                return False

        engine = Engine()
        monkeypatch.setattr(
            api_auth, "rate_limiter", PostgresRateLimiter(engine_factory=lambda: engine),
        )
        request = Request({
            "type": "http", "method": "POST", "path": "/chat",
            "query_string": b"", "headers": [], "scheme": "http",
            "server": ("test", 80),
        })
        handled = []

        async def handler(_request):
            handled.append(True)
            return JSONResponse({"unexpected": True})

        response = await api_auth.authorization_middleware(request, handler)

        assert response.status_code == 429
        assert response.body == b'{"detail":"Request rate limit exceeded"}'
        assert response.headers["retry-after"] == expected_retry_after
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "www-authenticate" not in response.headers
        assert handled == []
        assert not hasattr(request.state, "current_user")
        assert len({thread for _stage, thread in stages}) == 1
        assert loop_thread not in {thread for _stage, thread in stages}
        assert [stage for stage, _thread in stages] == (
            ["begin", "enter"] if error_stage == "enter" else
            ["begin", "enter", "execute", "exit"]
        )

    anyio.run(scenario)


@pytest.mark.parametrize(
    ("method", "path"),
    [("OPTIONS", "/chat"), ("GET", "/health/live"), ("HEAD", "/health/live")],
)
def test_authentication_and_limiter_exemptions_do_not_touch_unavailable_stores(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str,
):
    touched = []

    def unavailable(*_args, **_kwargs):
        touched.append(True)
        raise RuntimeError("The exempt request must not contact identity or quota stores")

    class UnavailableLimiter:
        retry_after = staticmethod(unavailable)

    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    monkeypatch.setattr(api_auth, "authenticate_request", unavailable)
    monkeypatch.setattr(api_auth, "rate_limiter", UnavailableLimiter())

    async def scenario():
        request = Request({
            "type": "http", "method": method, "path": path,
            "query_string": b"", "headers": [], "scheme": "http",
            "server": ("test", 80),
        })
        handled = []

        async def handler(received_request):
            handled.append(received_request)
            return JSONResponse({"status": "ok"}, headers={"Cache-Control": "max-age=30"})

        response = await api_auth.authorization_middleware(request, handler)

        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "max-age=30"
        assert "www-authenticate" not in response.headers
        assert "retry-after" not in response.headers
        assert handled == [request]
        assert not hasattr(request.state, "current_user")
        assert touched == []

    anyio.run(scenario)
