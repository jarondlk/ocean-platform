from fastapi.testclient import TestClient

import api.main as api_main
import config
import model_runtime
from api.main import app


client = TestClient(app)


def test_retrieve_response_includes_rank_sources(monkeypatch):
    def fake_retrieve_with_expansion(*args, **kwargs):
        assert kwargs["vector_weight"] == 0.7
        assert kwargs["fts_weight"] == 0.3
        assert kwargs["expand_evidence"] is True
        return {
            "primary": [
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
                    "retrieval_role": "primary",
                }
            ],
            "linked": [
                {
                    "doc_id": "sst:2024-01-01",
                    "title": "Satellite SST 2024-01-01",
                    "source_type": "remote_sensing",
                    "event_id": "sst:2024-01-01",
                    "time": "2024-01-01",
                    "bay": "O",
                    "text": "satellite SST observation",
                    "retrieval_role": "linked",
                    "link_type": "same_day",
                    "linked_from_doc_id": "ctd:2024-01-O-s1",
                    "time_delta_days": 0,
                    "distance_km": 1.2,
                }
            ],
            "diagnostics": {
                "expected_source_types": ["ctd", "remote_sensing"],
                "retrieved_source_types": ["ctd", "remote_sensing"],
                "missing_source_types": [],
                "source_coverage_ratio": 1.0,
                "primary_count": 1,
                "linked_count": 1,
            },
        }

    monkeypatch.setattr(api_main, "retrieve_with_expansion", fake_retrieve_with_expansion)

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
    assert payload["linked_sources"][0]["retrieval_role"] == "linked"
    assert payload["linked_sources"][0]["linked_from_doc_id"] == "ctd:2024-01-O-s1"
    assert payload["diagnostics"]["source_coverage_ratio"] == 1.0


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

    def fake_retrieve_with_expansion(*args, **kwargs):
        return {
            "primary": [
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
                    "retrieval_role": "primary",
                }
            ],
            "linked": [
                {
                    "doc_id": "sst:2024-01-01",
                    "title": "Satellite SST 2024-01-01",
                    "source_type": "remote_sensing",
                    "event_id": "sst:2024-01-01",
                    "time": "2024-01-01",
                    "bay": "O",
                    "text": "SST corroborates surface temperature.",
                    "retrieval_role": "linked",
                    "link_type": "same_day",
                    "linked_from_doc_id": "ctd:2024-01-O-s1",
                }
            ],
            "diagnostics": {
                "expected_source_types": ["ctd", "remote_sensing"],
                "retrieved_source_types": ["ctd", "remote_sensing"],
                "missing_source_types": [],
                "source_coverage_ratio": 1.0,
                "primary_count": 1,
                "linked_count": 1,
            },
        }

    class FakeOllamaResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": (
                        "answer with citations [ctd:2024-01-O-s1] [sst:2024-01-01] "
                        "[analysis_trends] [reliability_sst_ctd]"
                    )
                }
            }

    def fake_post(*args, **kwargs):
        prompt = kwargs["json"]["messages"][0]["content"]
        assert "LINKED CROSS-SOURCE EVIDENCE" in prompt
        assert "sst:2024-01-01" in prompt
        return FakeOllamaResponse()

    monkeypatch.setattr(api_main, "retrieve_with_expansion", fake_retrieve_with_expansion)
    monkeypatch.setattr(config, "ANALYSIS_DIR", analysis_dir)
    monkeypatch.setattr(config, "RELIABILITY_DIR", reliability_dir)
    monkeypatch.setattr(model_runtime.requests, "post", fake_post)

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
    assert payload["n_linked_sources"] == 1
    assert payload["n_context_documents"] == 2
    assert payload["linked_sources"][0]["doc_id"] == "sst:2024-01-01"
    assert payload["analysis_context"][0]["doc_id"] == "analysis_trends"
    assert payload["reliability_context"][0]["doc_id"] == "reliability_sst_ctd"
    assert payload["prompt_diagnostics"]["retrieved_documents"] == 1
    assert payload["prompt_diagnostics"]["linked_documents"] == 1
    assert payload["prompt_diagnostics"]["context_documents"] == 2
    assert payload["retrieval_diagnostics"]["source_coverage_ratio"] == 1.0
    assert payload["answer_audit"]["trust_level"] == "strong"
    assert payload["answer_audit"]["citation_count"] == 4
    assert payload["answer_audit"]["invalid_citation_count"] == 0
    assert payload["answer_audit"]["linked_sources_cited"] == 1
    assert payload["answer_audit"]["analysis_context_cited"] == 1
    assert payload["answer_audit"]["reliability_context_cited"] == 1
    assert payload["answer_audit"]["citation_requirements"]["required_context_types"] == ["analysis", "reliability"]
    assert payload["answer_audit"]["citation_requirements"]["missing_source_types"] == []


def test_chat_can_disable_answer_audit(monkeypatch):
    def fake_retrieve_with_expansion(*args, **kwargs):
        return {
            "primary": [
                {
                    "doc_id": "ctd:2024-01-O-s1",
                    "title": "CTD summary 2024-01-O-s1",
                    "source_type": "ctd",
                    "text": "temperature profile",
                }
            ],
            "linked": [],
            "diagnostics": {
                "expected_source_types": ["ctd"],
                "retrieved_source_types": ["ctd"],
                "missing_source_types": [],
            },
        }

    class FakeOllamaResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "answer with citations [ctd:2024-01-O-s1]"}}

    monkeypatch.setattr(api_main, "retrieve_with_expansion", fake_retrieve_with_expansion)
    monkeypatch.setattr(
        model_runtime.requests,
        "post",
        lambda *args, **kwargs: FakeOllamaResponse(),
    )

    response = client.post(
        "/chat",
        json={
            "query": "What was the CTD temperature?",
            "k": 5,
            "inject_analysis": False,
            "inject_reliability": False,
            "run_answer_audit": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["answer_audit"] is None
