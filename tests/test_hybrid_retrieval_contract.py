from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

import config
from db.embedding_identity import EmbeddingIdentity, IdentifiedEmbedding
import orchestration.unified as unified
import retrieval.hybrid_retriever as postgres_retriever
from retrieval.contract import RetrievalBackendError
from retrieval.local_retriever import LocalRetriever


def _row(doc_id: str):
    return SimpleNamespace(
        doc_id=doc_id,
        source_type="ctd",
        sample_id=f"sample-{doc_id}",
        event_id=None,
        time="2026-01-01",
        bay="O",
        station="s1",
        title=doc_id,
        text="query" if doc_id == "a" else "other",
        provider=None,
        provider_project_id=None,
        provider_run_id=None,
        assay_id=None,
        assignment_method=None,
        sample_kind=None,
        is_control=None,
        source_snapshot_id=None,
        fts_rank=1.0,
    )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Session:
    def __init__(self, branch: str, outcome):
        self.branch = branch
        self.outcome = outcome

    def execute(self, statement, _params):
        sql = str(statement)
        expected = "vector" if "embedding <=>" in sql else "fts"
        assert expected == self.branch
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return _Result(self.outcome)


def _sessions(monkeypatch, vector, fts):
    outcomes = iter((("vector", vector), ("fts", fts)))
    opened = []

    @contextmanager
    def session():
        branch, outcome = next(outcomes)
        opened.append(branch)
        yield _Session(branch, outcome)

    monkeypatch.setattr(postgres_retriever, "get_session", session)
    monkeypatch.setattr(postgres_retriever, "embed_query", lambda _query: IdentifiedEmbedding(
        [0.1, 0.2], EmbeddingIdentity("provider", "model", 2)))
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    return opened


@pytest.mark.parametrize(
    ("vector", "fts", "expected"),
    [
        (RuntimeError("vector failed"), [_row("a")], ["a"]),
        ([_row("a")], RuntimeError("fts failed"), ["a"]),
    ],
)
def test_postgres_retrieval_branches_fail_independently(
    monkeypatch, vector, fts, expected
):
    opened = _sessions(monkeypatch, vector, fts)

    results = postgres_retriever.hybrid_search("query")

    assert [row.doc_id for row in results] == expected
    assert opened == ["vector", "fts"]


def test_postgres_retrieval_reports_total_backend_failure(monkeypatch):
    opened = _sessions(
        monkeypatch,
        RuntimeError("vector failed"),
        RuntimeError("fts failed"),
    )

    with pytest.raises(RetrievalBackendError, match="vector, fts"):
        postgres_retriever.hybrid_search("query")

    assert opened == ["vector", "fts"]


def test_local_and_postgres_share_weight_rrf_and_order_contract(monkeypatch):
    # FTS ranks a before b; vectors rank b before a. Equal fusion scores must
    # therefore use doc_id as the final deterministic tie-breaker.
    local = LocalRetriever()
    local.documents = [
        {"doc_id": "a", "source_type": "ctd", "title": "a", "text": "query query"},
        {"doc_id": "b", "source_type": "ctd", "title": "b", "text": "query"},
    ]
    local.bm25.fit([row["text"] for row in local.documents])
    local._embed_available = True
    local._embeddings = np.array([[0.0, 1.0], [1.0, 0.0]], dtype="float32")
    monkeypatch.setattr("db.vector_store.embed_text", lambda _query: [1.0, 0.0])
    local_results = local.search(
        "query", vector_weight=0.2, fts_weight=0.2, rrf_k=10
    )

    _sessions(
        monkeypatch,
        [_row("b"), _row("a")],
        [_row("a"), _row("b")],
    )
    postgres_results = postgres_retriever.hybrid_search(
        "query", vector_weight=0.2, fts_weight=0.2, rrf_k=10
    )

    expected_score = 0.5 / 11 + 0.5 / 12
    assert [row["doc_id"] for row in local_results] == ["a", "b"]
    assert [row.doc_id for row in postgres_results] == ["a", "b"]
    assert [row["score"] for row in local_results] == pytest.approx(
        [expected_score, expected_score]
    )
    assert [row.score for row in postgres_results] == pytest.approx(
        [expected_score, expected_score]
    )
    assert local_results[0]["rank_sources"] == {"vector": 2, "fts": 1}
    assert postgres_results[0].rank_sources == {"vector": 2, "fts": 1}


def test_request_resolves_postgres_availability_once(monkeypatch):
    probes = []

    def available():
        probes.append(True)
        return False

    def retrieve(_query, **kwargs):
        assert kwargs["pg_available"] is False
        return []

    monkeypatch.setattr(unified, "_pg_available", available)
    monkeypatch.setattr(unified, "retrieve", retrieve)
    monkeypatch.setattr(unified, "publication_status", lambda: {"status": "absent"})

    result = unified.retrieve_with_expansion("query", expand_evidence=False)

    assert probes == [True]
    assert result["diagnostics"]["backend"] == "local"


def test_local_vector_failure_recovers_with_fts_and_vector_only_fails_closed():
    local = LocalRetriever()
    local.documents = [
        {"doc_id": "a", "source_type": "ctd", "title": "a", "text": "query"}
    ]
    local.bm25.fit(["query"])

    assert [row["doc_id"] for row in local.search("query")] == ["a"]
    assert local.search("absent-term") == []
    with pytest.raises(RetrievalBackendError, match="vector"):
        local.search("query", vector_weight=1, fts_weight=0)


@pytest.mark.parametrize("different", [
    {"embedding_provider": "other-provider"},
    {"embedding_model": "other-model"},
    {"embedding_dim": 3},
    {"embedding_provider": None},
    {"embedding_model": None},
    {"embedding_dim": None},
])
def test_hybrid_excludes_incompatible_embedding_identity_and_keeps_scoped_fts(monkeypatch, different):
    from db import vector_store

    captured = []
    identity = {"embedding_provider": "actual-provider", "embedding_model": "active-model", "embedding_dim": 2}
    incompatible = _row("wrong")
    outside = _row("outside")
    for candidate in (incompatible, outside):
        candidate.__dict__.update(identity)
        candidate.active = True
        candidate.embedding = [0.25, 0.75]
    incompatible.__dict__.update(different)
    incompatible.sample_id = "allowed"

    class Session:
        def execute(self, statement, params):
            sql = str(statement)
            captured.append((sql, dict(params)))
            candidates = [r for r in (incompatible, outside)
                if r.active and r.source_type == params["source_type"]
                and r.sample_id in params["allowed_sample_id"]]
            if "embedding <=>" in sql:
                for column in identity:
                    if f"{column} = :{column}" in sql:
                        candidates = [r for r in candidates if getattr(r, column) == params[column]]
            return _Result(candidates)

    @contextmanager
    def session():
        yield Session()

    class Runtime:
        provider = "actual-provider"

        def embed(self, _query, **kwargs):
            assert kwargs["model"] == "active-model"
            return [0.25, 0.75]

    monkeypatch.setattr(postgres_retriever, "get_session", session)
    monkeypatch.setattr(vector_store, "get_model_runtime", lambda: Runtime())
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "active-model")
    monkeypatch.setattr(config, "EMBEDDING_DIM", 2)
    monkeypatch.setattr(config, "MODEL_PROVIDER", "configured-provider")
    diagnostics = {}
    results = postgres_retriever.hybrid_search("query", source_type="ctd", sample_ids=["allowed"], branch_diagnostics=diagnostics)
    assert [(r.doc_id, r.rank_sources) for r in results] == [("wrong", {"fts": 1})]
    assert diagnostics["failed_branches"] == []
    assert diagnostics["vector"] == {
        "status": "no_compatible_candidates",
        "identity": {"provider": "actual-provider", "model": "active-model", "dimension": 2},
        "compatible_result_count": 0,
    }
    vector_sql, vector_params = captured[0]
    fts_sql, _ = captured[1]
    for column, value in identity.items():
        assert f"{column} = :{column}" in vector_sql
        assert vector_params[column] == value
        assert f"{column} = :{column}" not in fts_sql
    assert "sample_id = ANY(:allowed_sample_id)" in vector_sql
    assert "sample_id = ANY(:allowed_sample_id)" in fts_sql


def test_bare_callback_has_no_vector_authority_and_preserves_scoped_fts(monkeypatch):
    queries = []
    row = _row("authorized")
    row.sample_id = "allowed"

    class Session:
        def execute(self, statement, params):
            sql = str(statement)
            assert "embedding <=>" not in sql
            assert "sample_id = ANY(:allowed_sample_id)" in sql
            assert params["allowed_sample_id"] == ["allowed"]
            assert params["source_type"] == "ctd"
            assert not any(key.startswith("embedding_") for key in params)
            queries.append(sql)
            return _Result([row])

    @contextmanager
    def session():
        yield Session()

    monkeypatch.setattr(postgres_retriever, "get_session", session)
    monkeypatch.setattr(postgres_retriever, "embed_query", lambda _query: pytest.fail("supplied callback must own identity"))
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    diagnostics = {}
    results = postgres_retriever.hybrid_search("query", query_embedding=lambda: [0.1, 0.2],
        source_type="ctd", sample_ids=["allowed"], branch_diagnostics=diagnostics)
    assert len(queries) == 1
    assert [(r.doc_id, r.rank_sources) for r in results] == [("authorized", {"fts": 1})]
    assert diagnostics["failed_branches"] == ["vector"]
    assert diagnostics["vector"] == {"status": "unavailable", "identity": None, "compatible_result_count": None}
    with pytest.raises(RetrievalBackendError, match="vector"):
        postgres_retriever.hybrid_search("query", query_embedding=lambda: [0.1, 0.2],
            vector_weight=1, fts_weight=0)
    assert len(queries) == 1


def test_explicit_callback_binds_its_actual_identity_including_equal_dimension_model(monkeypatch):
    captured = {}
    provider = "provider'; DROP TABLE retrieval_document; --"
    model = "callback-model"
    embedding = IdentifiedEmbedding([0.25, 0.75], EmbeddingIdentity(provider, model, 2))

    class Session:
        def execute(self, statement, params):
            captured.update(sql=str(statement), params=params)
            return _Result([_row("compatible")])

    @contextmanager
    def session():
        yield Session()

    monkeypatch.setattr(postgres_retriever, "get_session", session)
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(config, "MODEL_PROVIDER", "different-configured-provider")
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "different-configured-model")
    diagnostics = {}
    results = postgres_retriever.hybrid_search("query", query_embedding=lambda: embedding,
        vector_weight=1, fts_weight=0, branch_diagnostics=diagnostics)
    assert results[0].rank_sources == {"vector": 1}
    assert provider not in captured["sql"]
    assert captured["params"]["embedding_provider"] == provider
    assert captured["params"]["embedding_model"] == model
    assert captured["params"]["embedding_dim"] == 2
    assert diagnostics["vector"] == {
        "status": "retrieved", "identity": {"provider": provider, "model": model, "dimension": 2},
        "compatible_result_count": 1,
    }


def test_fts_only_never_computes_query_embedding(monkeypatch):
    @contextmanager
    def session():
        yield _Session("fts", [_row("a")])

    monkeypatch.setattr(postgres_retriever, "get_session", session)
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    diagnostics = {}
    results = postgres_retriever.hybrid_search("query", vector_weight=0, fts_weight=1,
        query_embedding=lambda: pytest.fail("FTS needs no embedding"), branch_diagnostics=diagnostics)
    assert results[0].rank_sources == {"fts": 1}
    assert diagnostics["vector"] == {"status": "disabled", "identity": None, "compatible_result_count": None}
