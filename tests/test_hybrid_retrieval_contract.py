from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

import config
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
    monkeypatch.setattr(postgres_retriever, "embed_text", lambda _query: [0.1, 0.2])
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
