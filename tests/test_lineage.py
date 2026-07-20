import hashlib
import importlib
import json
import sys

import pandas as pd

import ingestion.lineage as lineage


def _configure_lineage_paths(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    raw_ctd = data_dir / "raw" / "ctd" / "CTD_Onagawa.tsv"
    raw_ctd.parent.mkdir(parents=True)
    raw_ctd.write_text("sample_id\ttemp\nS1\t12.4\n", encoding="utf-8")

    for name in [
        "normalized",
        "canonical",
        "serving",
        "analysis",
        "reliability",
        "provenance",
    ]:
        (data_dir / name).mkdir(parents=True)
    (tmp_path / "sst_subset").mkdir()
    (tmp_path / "himawari_raw").mkdir()

    monkeypatch.setattr(lineage.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(lineage.config, "DATA_DIR", data_dir)
    monkeypatch.setattr(lineage.config, "NORMALIZED_DIR", data_dir / "normalized")
    monkeypatch.setattr(lineage.config, "CANONICAL_DIR", data_dir / "canonical")
    monkeypatch.setattr(lineage.config, "SERVING_DIR", data_dir / "serving")
    monkeypatch.setattr(lineage.config, "ANALYSIS_DIR", data_dir / "analysis")
    monkeypatch.setattr(lineage.config, "RELIABILITY_DIR", data_dir / "reliability")
    monkeypatch.setattr(lineage.config, "PROVENANCE_DIR", data_dir / "provenance")
    monkeypatch.setattr(lineage.config, "SST_NETCDF_DIR", tmp_path / "sst_subset")
    monkeypatch.setattr(lineage.config, "HIMAWARI_RAW_DIR", tmp_path / "himawari_raw")
    monkeypatch.setattr(lineage.config, "RAW_FILES", {"ctd": raw_ctd})
    return data_dir, raw_ctd


def _write_minimal_artifacts(data_dir):
    pd.DataFrame(
        [
            {
                "sample_id": "S1",
                "ctd_date": "2024-01-01",
                "depth_m": 0,
                "temperature_c": 12.4,
            }
        ]
    ).to_parquet(data_dir / "normalized" / "ctd_profile_standardized.parquet")
    pd.DataFrame(
        [
            {
                "sample_id": "S1",
                "event_id": "ctd_event_1",
                "ctd_date": "2024-01-01",
                "bay": "Onagawa",
            }
        ]
    ).to_parquet(data_dir / "normalized" / "ctd_summary.parquet")
    pd.DataFrame(
        [
            {
                "event_id": "ctd_event_1",
                "source_type": "ctd",
                "sample_id": "S1",
                "time": "2024-01-01T00:00:00",
            }
        ]
    ).to_parquet(data_dir / "canonical" / "anchor_events.parquet")
    pd.DataFrame(
        [
            {
                "doc_id": "ctd_doc_1",
                "source_type": "ctd",
                "sample_id": "S1",
                "event_id": "ctd_event_1",
                "time": "2024-01-01T00:00:00",
                "bay": "Onagawa",
                "station": "St.1",
                "title": "CTD profile S1",
                "text": "Temperature was 12.4 C at the surface.",
            }
        ]
    ).to_parquet(data_dir / "serving" / "retrieval_documents.parquet")


def test_provenance_manifest_links_sources_artifacts_documents_and_embeddings(tmp_path, monkeypatch):
    data_dir, raw_ctd = _configure_lineage_paths(tmp_path, monkeypatch)
    _write_minimal_artifacts(data_dir)
    raw_sha = hashlib.sha256(raw_ctd.read_bytes()).hexdigest()
    (data_dir / "provenance" / "provenance.jsonl").write_text(
        json.dumps(
            {
                "source_dataset": "ctd",
                "source_file": str(raw_ctd),
                "sha256": raw_sha,
                "file_size_bytes": raw_ctd.stat().st_size,
                "ingested_at": "2026-07-20T00:00:00+09:00",
                "processing_run": "pytest-lineage",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        lineage,
        "_database_embedding_status",
        lambda: {"available": True, "rows": {"ctd_doc_1": True}},
    )

    manifest = lineage.build_provenance_manifest(limit_documents=10, include_embeddings=True)

    assert manifest["schema_version"] == 1
    assert manifest["summary"]["registered_source_records"] == 1
    assert any(row["id"] == "raw:ctd" and row["registry_seen"] for row in manifest["source_files"])
    assert any(row["id"] == "serving:retrieval_parquet" and row["exists"] for row in manifest["artifacts"])
    assert manifest["documents"][0]["doc_id"] == "ctd_doc_1"
    assert manifest["documents"][0]["source_file_ids"] == ["raw:ctd"]
    assert len(manifest["documents"][0]["content_hash"]) == 64
    assert manifest["embeddings"][0]["embedding_status"] == "embedded"


def test_document_trace_returns_artifact_and_source_file_path(tmp_path, monkeypatch):
    data_dir, _ = _configure_lineage_paths(tmp_path, monkeypatch)
    _write_minimal_artifacts(data_dir)
    monkeypatch.setattr(
        lineage,
        "_database_embedding_status",
        lambda: {"available": True, "rows": {"ctd_doc_1": False}},
    )

    trace = lineage.build_document_trace("ctd_doc_1")

    assert trace["found"] is True
    assert trace["trace"]["document"]["doc_id"] == "ctd_doc_1"
    assert any(row["id"] == "serving:retrieval_parquet" for row in trace["trace"]["artifacts"])
    assert any(row["id"] == "raw:ctd" for row in trace["trace"]["source_files"])
    assert trace["trace"]["embedding"]["embedding_status"] == "missing"


def test_upsert_dry_run_uses_lineage_keys_and_content_hashes(tmp_path, monkeypatch):
    data_dir, _ = _configure_lineage_paths(tmp_path, monkeypatch)
    _write_minimal_artifacts(data_dir)

    def fake_database_rows(table_name, columns):
        if table_name == "ctd_summary":
            return True, None, [{"sample_id": "S1"}]
        if table_name == "retrieval_document":
            return True, None, [{"doc_id": "ctd_doc_1", "title": "Old title", "text": "Old text", "embedded": True}]
        return True, None, []

    monkeypatch.setattr(lineage, "_database_rows", fake_database_rows)

    plan = lineage.build_upsert_dry_run_plan(limit_keys=2)

    assert plan["dry_run"] is True
    assert plan["ok"] is True
    by_table = {row["table"]: row for row in plan["table_plans"]}
    assert by_table["ctd_profile"]["planned_inserts"] == 1
    assert by_table["ctd_summary"]["matched_existing"] == 1
    assert by_table["retrieval_document"]["candidate_updates"] == 1
    assert by_table["retrieval_document"]["embedding_refresh_candidates"] == 1


def test_load_db_upsert_dry_run_cli_delegates_to_lineage_plan(monkeypatch, capsys):
    load_db = importlib.import_module("scripts.load_db")
    captured = {}

    def fake_plan(limit_keys):
        captured["limit_keys"] = limit_keys
        return {
            "generated_at": "2026-07-20T00:00:00+09:00",
            "dry_run": True,
            "ok": True,
            "database": {"available": True, "errors": []},
            "summary": {
                "database_available": True,
                "incoming_rows": 1,
                "planned_inserts": 1,
                "candidate_updates": 0,
                "stale_existing": 0,
                "embedding_refresh_candidates": 1,
            },
            "lineage_manifest_summary": {"documents": 1},
            "table_plans": [{"table": "retrieval_document", "planned_inserts": 1}],
            "warnings": ["read-only"],
        }

    monkeypatch.setattr(lineage, "build_upsert_dry_run_plan", fake_plan)
    monkeypatch.setattr(
        sys,
        "argv",
        ["load_db.py", "--upsert", "--dry-run", "--limit-keys", "2", "--json"],
    )

    load_db.main()

    payload = json.loads(capsys.readouterr().out)
    assert captured == {"limit_keys": 2}
    assert payload["dry_run"] is True
    assert payload["summary"]["planned_inserts"] == 1
