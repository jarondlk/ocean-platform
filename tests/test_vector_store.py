"""Regression tests for the PostgreSQL vector-store query boundary."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from db import vector_store


class _Result:
    def fetchall(self) -> list[Any]:
        return []


class _Session:
    def __init__(self) -> None:
        self.statement = ""
        self.params: dict[str, Any] = {}

    def execute(self, statement: Any, params: dict[str, Any]) -> _Result:
        self.statement = str(statement)
        self.params = params
        return _Result()


def test_search_similar_binds_source_type(monkeypatch) -> None:
    session = _Session()

    @contextmanager
    def fake_session():
        yield session

    attack = "ctd' OR 1=1 --"
    monkeypatch.setattr(vector_store, "get_session", fake_session)
    monkeypatch.setattr(vector_store, "embed_text", lambda _query: [0.25, 0.75])

    assert vector_store.search_similar("temperature", source_type=attack) == []
    assert "source_type = :source_type" in session.statement
    assert attack not in session.statement
    assert session.params["source_type"] == attack
