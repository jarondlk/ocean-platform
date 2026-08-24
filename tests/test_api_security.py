from __future__ import annotations

import pytest
from fastapi import HTTPException

import api.main as api_main
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
