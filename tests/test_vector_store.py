"""Regression tests for the PostgreSQL vector-store query boundary."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from db import vector_store
from db.embedding_identity import EmbeddingIdentity, IdentifiedEmbedding, validate_embedding


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
    monkeypatch.setattr(vector_store, "embed_query", lambda _query: IdentifiedEmbedding(
        [0.25, 0.75], EmbeddingIdentity("provider", "model", 2)))

    assert vector_store.search_similar("temperature", source_type=attack) == []
    assert "source_type = :source_type" in session.statement
    assert attack not in session.statement
    assert session.params["source_type"] == attack


def test_embed_text_uses_query_task_type(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class _Runtime:
        def embed(self, text_input: str, **kwargs: Any) -> list[float]:
            calls.append({"text_input": text_input, **kwargs})
            return [0.25, 0.75]

    monkeypatch.setattr(vector_store, "get_model_runtime", lambda: _Runtime())

    assert vector_store.embed_text("temperature", model="embed-model") == [
        0.25,
        0.75,
    ]
    assert calls == [
        {
            "text_input": "temperature",
            "model": "embed-model",
            "task_type": "RETRIEVAL_QUERY",
        }
    ]


def test_embed_batch_propagates_provider_failure(monkeypatch) -> None:
    class _Runtime:
        def embed_batch(self, *_args: Any, **_kwargs: Any) -> list[list[float]]:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(vector_store, "get_model_runtime", lambda: _Runtime())

    try:
        vector_store.embed_batch(["document"])
    except RuntimeError as exc:
        assert str(exc) == "provider unavailable"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("provider failure should propagate")


def test_embedding_refresh_query_applies_sample_and_source_scope() -> None:
    class Query:
        def __init__(self) -> None:
            self.criteria: list[Any] = []

        def filter(self, *criteria: Any):
            self.criteria.extend(criteria)
            return self

    class Session:
        query_result = Query()

        def query(self, _model: Any) -> Query:
            return self.query_result

    session = Session()
    vector_store._embedding_refresh_query(
        session,
        sample_id="a" * 64,
        source_type="edna_metabarcoding",
    )
    compiled = " ".join(str(item) for item in session.query_result.criteria)
    assert "retrieval_document.sample_id" in compiled
    assert "retrieval_document.source_type" in compiled


@pytest.mark.parametrize("different", [
    {"embedding_provider": "other-provider"},
    {"embedding_model": "other-model"},
    {"embedding_dim": 3},
    {"embedding_provider": None},
    {"embedding_model": None},
    {"embedding_dim": None},
])
def test_search_similar_excludes_incompatible_embedding_identity(monkeypatch, different):
    """SQL-aware fake exercises candidate exclusion, including equal dimensions."""
    import config

    captured = {}
    identity = {"embedding_provider": "actual-provider", "embedding_model": "active-model", "embedding_dim": 2}

    def row(doc_id, **changes):
        return SimpleNamespace(doc_id=doc_id, source_type="ctd", sample_id="allowed", event_id=None,
            time=None, lat=None, lon=None, bay="O", station=None, title=doc_id,
            text="temperature", distance=0.2, active=True, embedding=[0.25, 0.75], **{**identity, **changes})

    candidates = [row("wrong", **different), row("compatible"), row("inactive")]
    # Keep fixtures explicit; inactive documents are excluded by the existing filter.
    candidates[-1].active = False

    class Session:
        def execute(self, statement, params):
            sql = str(statement)
            captured.update(sql=sql, params=params)
            selected = [r for r in candidates if r.active and r.source_type == params["source_type"]]
            for column in identity:
                if f"{column} = :{column}" in sql:
                    selected = [r for r in selected if getattr(r, column) == params[column]]
            return SimpleNamespace(fetchall=lambda: selected)

    @contextmanager
    def session():
        yield Session()

    class Runtime:
        provider = "actual-provider"

        def embed(self, _query, **kwargs):
            assert kwargs["model"] == "active-model"
            return [0.25, 0.75]

    monkeypatch.setattr(vector_store, "get_session", session)
    monkeypatch.setattr(vector_store, "get_model_runtime", lambda: Runtime())
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "active-model")
    monkeypatch.setattr(config, "EMBEDDING_DIM", 2)
    # The runtime, rather than a possibly outdated provider config, owns identity.
    monkeypatch.setattr(config, "MODEL_PROVIDER", "configured-provider")
    results = vector_store.search_similar("temperature", source_type="ctd")
    assert [r["doc_id"] for r in results] == ["compatible"]
    for column, value in identity.items():
        assert f"{column} = :{column}" in captured["sql"]
        assert captured["params"][column] == value


def test_embed_query_captures_actual_runtime_model_and_dimension(monkeypatch):
    import config

    calls = []

    class Runtime:
        provider = "actual-provider"

        def embed(self, query, **kwargs):
            calls.append((query, kwargs))
            return [0.25, 0.75]

    monkeypatch.setattr(vector_store, "get_model_runtime", lambda: Runtime())
    monkeypatch.setattr(config, "MODEL_PROVIDER", "wrong-provider")
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "wrong-model")
    monkeypatch.setattr(config, "EMBEDDING_DIM", 2)
    result = vector_store.embed_query("temperature", model="actual-model")
    assert result == [0.25, 0.75]
    assert result.identity == EmbeddingIdentity("actual-provider", "actual-model", 2)
    assert calls == [("temperature", {"model": "actual-model", "task_type": "RETRIEVAL_QUERY"})]


@pytest.mark.parametrize("vector", [[0.1], [0.1, float("nan")], [float("inf"), 0.2], [True, 0.2], ["0.1", 0.2], []])
def test_embed_query_rejects_invalid_or_schema_incompatible_vectors(monkeypatch, vector):
    import config

    class Runtime:
        provider = "actual-provider"

        def embed(self, *_args, **_kwargs):
            return vector

    monkeypatch.setattr(vector_store, "get_model_runtime", lambda: Runtime())
    monkeypatch.setattr(config, "EMBEDDING_DIM", 2)
    with pytest.raises(ValueError):
        vector_store.embed_query("temperature")


@pytest.mark.parametrize("identity", [
    ("", "model", 2), (None, "model", 2), ("provider", "", 2),
    ("provider", None, 2), ("provider", "model", 0),
    ("provider", "model", True), ("provider", "model", 2.0),
])
def test_embedding_identity_requires_complete_named_identity(identity):
    with pytest.raises(ValueError):
        EmbeddingIdentity(*identity)


def test_callback_vector_validation_cannot_infer_or_outlive_identity():
    with pytest.raises(ValueError, match="explicit"):
        validate_embedding([0.25, 0.75])
    vector = IdentifiedEmbedding([0.25, 0.75], EmbeddingIdentity("provider", "model", 2))
    vector.append(0.5)
    with pytest.raises(ValueError, match="dimension"):
        validate_embedding(vector)
