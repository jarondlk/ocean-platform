from fastapi.testclient import TestClient

import api.main as api_main
from api.main import app


client = TestClient(app)


def test_provenance_manifest_endpoint_passes_controls(monkeypatch):
    captured = {}

    def fake_manifest(*, limit_documents, include_embeddings):
        captured["limit_documents"] = limit_documents
        captured["include_embeddings"] = include_embeddings
        return {
            "schema_version": 1,
            "generated_at": "2026-07-20T00:00:00+09:00",
            "project_root": "/repo",
            "summary": {"documents": 1, "artifacts": 1},
            "source_files": [{"id": "raw:ctd"}],
            "artifacts": [{"id": "serving:retrieval_parquet"}],
            "documents": [{"doc_id": "ctd_doc_1"}],
            "embeddings": [],
            "limitations": ["row-level hashes planned"],
        }

    monkeypatch.setattr(api_main, "build_provenance_manifest", fake_manifest)

    response = client.get("/provenance/manifest?limit_documents=7&include_embeddings=false")

    assert response.status_code == 200
    payload = response.json()
    assert captured == {"limit_documents": 7, "include_embeddings": False}
    assert payload["summary"]["documents"] == 1
    assert payload["source_files"][0]["id"] == "raw:ctd"


def test_provenance_trace_endpoint_returns_lineage_payload(monkeypatch):
    monkeypatch.setattr(
        api_main,
        "build_document_trace",
        lambda doc_id: {
            "doc_id": doc_id,
            "found": True,
            "trace": {
                "document": {"doc_id": doc_id, "content_hash": "abc"},
                "trace_path": [{"level": "citation", "key": doc_id}],
            },
        },
    )

    response = client.get("/provenance/trace/ctd_doc_1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert payload["trace"]["document"]["doc_id"] == "ctd_doc_1"


def test_provenance_upsert_dry_run_endpoint_returns_plan(monkeypatch):
    captured = {}

    def fake_plan(limit_keys):
        captured["limit_keys"] = limit_keys
        return {
            "generated_at": "2026-07-20T00:00:00+09:00",
            "dry_run": True,
            "ok": True,
            "database": {"available": True, "errors": []},
            "summary": {"planned_inserts": 2, "embedding_refresh_candidates": 1},
            "lineage_manifest_summary": {"documents": 10},
            "table_plans": [{"table": "retrieval_document", "planned_inserts": 2}],
            "warnings": ["read-only"],
        }

    monkeypatch.setattr(api_main, "build_upsert_dry_run_plan", fake_plan)

    response = client.get("/provenance/upsert-dry-run?limit_keys=3")

    assert response.status_code == 200
    payload = response.json()
    assert captured == {"limit_keys": 3}
    assert payload["dry_run"] is True
    assert payload["table_plans"][0]["table"] == "retrieval_document"
