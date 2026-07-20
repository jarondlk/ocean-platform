from fastapi.testclient import TestClient

import api.main as api_main
import config
from api.main import app


client = TestClient(app)


def test_retrieve_response_includes_rank_sources(monkeypatch):
    def fake_retrieve(*args, **kwargs):
        assert kwargs["vector_weight"] == 0.7
        assert kwargs["fts_weight"] == 0.3
        return [
            {
                "doc_id": "ctd:2024-01-O-s1",
                "title": "CTD summary 2024-01-O-s1",
                "source_type": "ctd",
                "sample_id": "2024-01-O-s1",
                "time": "2024-01-01",
                "bay": "O",
                "station": "s1",
                "text": "temperature and salinity profile",
                "score": 0.42,
                "rank_sources": {"vector": 1, "fts": 4},
            }
        ]

    monkeypatch.setattr(api_main, "retrieve", fake_retrieve)

    response = client.post(
        "/retrieve",
        json={
            "query": "temperature salinity",
            "k": 5,
            "source_type": "ctd",
            "vector_weight": 0.7,
            "fts_weight": 0.3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "temperature salinity"
    assert payload["sources"][0]["doc_id"] == "ctd:2024-01-O-s1"
    assert payload["sources"][0]["rank_sources"] == {"vector": 1, "fts": 4}


def test_chat_response_includes_context_ledger(tmp_path, monkeypatch):
    analysis_dir = tmp_path / "analysis"
    reliability_dir = tmp_path / "reliability"
    analysis_dir.mkdir()
    reliability_dir.mkdir()
    (analysis_dir / "analysis_documents.jsonl").write_text(
        '{"id":"analysis_trends","analysis_type":"trend","title":"Trends","text":"Temperature trend context."}\n',
        encoding="utf-8",
    )
    (reliability_dir / "reliability_documents.jsonl").write_text(
        '{"id":"reliability_sst_ctd","analysis_type":"cross_source_validation","title":"SST CTD","text":"SST validates CTD context."}\n',
        encoding="utf-8",
    )

    def fake_retrieve(*args, **kwargs):
        return [
            {
                "doc_id": "ctd:2024-01-O-s1",
                "title": "CTD summary 2024-01-O-s1",
                "source_type": "ctd",
                "sample_id": "2024-01-O-s1",
                "time": "2024-01-01",
                "bay": "O",
                "station": "s1",
                "text": "temperature profile",
                "score": 0.42,
                "rank_sources": {"vector": 1},
            }
        ]

    class FakeOllamaResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "answer with citations [ctd:2024-01-O-s1]"}}

    monkeypatch.setattr(api_main, "retrieve", fake_retrieve)
    monkeypatch.setattr(config, "ANALYSIS_DIR", analysis_dir)
    monkeypatch.setattr(config, "RELIABILITY_DIR", reliability_dir)
    monkeypatch.setattr(api_main.requests, "post", lambda *args, **kwargs: FakeOllamaResponse())

    response = client.post(
        "/chat",
        json={
            "query": "Compare temperature trend reliability",
            "k": 5,
            "inject_analysis": True,
            "inject_reliability": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["n_sources"] == 1
    assert payload["n_context_documents"] == 2
    assert payload["analysis_context"][0]["doc_id"] == "analysis_trends"
    assert payload["reliability_context"][0]["doc_id"] == "reliability_sst_ctd"
    assert payload["prompt_diagnostics"]["retrieved_documents"] == 1
    assert payload["prompt_diagnostics"]["context_documents"] == 2
