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
    (data_dir / "raw" / "anemone").mkdir(parents=True)
    (data_dir / "normalized" / "anemone").mkdir(parents=True)

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
    monkeypatch.setattr(
        lineage.config,
        "RAW_ANEMONE_DIR",
        data_dir / "raw" / "anemone",
    )
    monkeypatch.setattr(
        lineage.config,
        "ANEMONE_NORMALIZED_DIR",
        data_dir / "normalized" / "anemone",
    )
    monkeypatch.setattr(lineage.config, "RAW_FILES", {"ctd": raw_ctd})
    return data_dir, raw_ctd


def _write_anemone_bundle(data_dir):
    normalization_id = "a" * 64
    snapshot_id = "b" * 64
    source_file_id = "c" * 64
    sample_id = "d" * 64
    assay_id = "e" * 64
    detection_id = "f" * 64
    root = (
        data_dir
        / "normalized"
        / "anemone"
        / "snapshots"
        / normalization_id
    )
    root.mkdir(parents=True)
    relative = "project/run/sample/community_qc_target.tsv.xz"
    raw_path = data_dir / "raw" / "anemone" / "snapshots" / snapshot_id / relative
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"fixture")
    common = {
        "source_snapshot_id": snapshot_id,
        "source_file_id": source_file_id,
        "active": True,
        "first_seen_snapshot_id": snapshot_id,
        "last_seen_snapshot_id": snapshot_id,
        "scientific_content_sha256": "1" * 64,
        "source_row_hash": "2" * 64,
    }
    frames = {
        "external_source_snapshot": pd.DataFrame(
            [{"snapshot_id": snapshot_id}]
        ),
        "external_source_file": pd.DataFrame(
            [
                {
                    "source_file_id": source_file_id,
                    "relative_path": relative,
                    "source_url": "https://db.anemone.bio/dist/example",
                    "role": "community_qc",
                    "selection_status": "selected",
                    "sha256": hashlib.sha256(b"fixture").hexdigest(),
                    "size_bytes": 7,
                }
            ]
        ),
        "edna_sample": pd.DataFrame(
            [
                {
                    "sample_id": sample_id,
                    "provider": "anemone",
                    "provider_sample_id": "sample",
                    "provider_project_id": "project",
                    "provider_run_id": "run",
                    "source_row_numbers_json": "[2,3]",
                    **common,
                }
            ]
        ),
        "edna_assay": pd.DataFrame(
            [
                {
                    "assay_id": assay_id,
                    "sample_id": sample_id,
                    "source_row_numbers_json": "[2,3]",
                    **common,
                }
            ]
        ),
        "edna_detection": pd.DataFrame(
            [
                {
                    "detection_id": detection_id,
                    "assay_id": assay_id,
                    "source_row_number": 2,
                    **common,
                }
            ]
        ),
        "edna_internal_standard": pd.DataFrame(
            columns=[
                "internal_standard_id",
                "source_snapshot_id",
                "source_file_id",
                "source_row_number",
                "active",
                "first_seen_snapshot_id",
                "last_seen_snapshot_id",
                "scientific_content_sha256",
                "source_row_hash",
            ]
        ),
        "edna_anchor_event": pd.DataFrame(columns=["event_id"]),
    }
    artifacts = {}
    for name, frame in frames.items():
        path = root / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        artifacts[name] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "row_count": len(frame),
        }
    manifest = {
        "normalization_id": normalization_id,
        "source_snapshot_id": snapshot_id,
        "source_scope_level": "sample",
        "source_scope_url": "https://db.anemone.bio/dist/MiFish/ANEMONE/project/run/sample",
        "status": "complete",
        "artifacts": artifacts,
    }
    (root / "normalization_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (data_dir / "normalized" / "anemone" / "current.json").write_text(
        json.dumps({"normalization_id": normalization_id}),
        encoding="utf-8",
    )
    return {
        "normalization_id": normalization_id,
        "snapshot_id": snapshot_id,
        "source_file_id": source_file_id,
        "detection_id": detection_id,
    }


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


def test_anemone_lineage_and_dry_run_keep_exact_source_row_trace(
    tmp_path,
    monkeypatch,
):
    data_dir, _ = _configure_lineage_paths(tmp_path, monkeypatch)
    identifiers = _write_anemone_bundle(data_dir)
    monkeypatch.setattr(lineage, "_database_embedding_status", lambda: {"available": True, "rows": {}})

    def fake_scoped(table_name, columns, **_kwargs):
        if table_name == "edna_detection":
            return (
                True,
                None,
                [
                    {
                        "detection_id": identifiers["detection_id"],
                        "scientific_content_sha256": "0" * 64,
                        "source_row_hash": "2" * 64,
                        "active": True,
                    }
                ],
            )
        return True, None, []

    monkeypatch.setattr(
        lineage,
        "_database_scoped_anemone_rows",
        fake_scoped,
    )
    monkeypatch.setattr(
        lineage,
        "_database_rows",
        lambda _table, _columns: (True, None, []),
    )

    manifest = lineage.build_provenance_manifest(
        limit_documents=0,
        include_embeddings=False,
    )
    plan = lineage.build_upsert_dry_run_plan(limit_keys=2)

    assert any(
        row["id"] == f"raw:anemone:{identifiers['source_file_id']}"
        for row in manifest["source_files"]
    )
    detection_trace = next(
        row
        for row in manifest["anemone_canonical_rows"]
        if row["table"] == "edna_detection"
    )
    assert detection_trace["source_row_locator"] == 2
    assert detection_trace["source_snapshot_id"] == identifiers["snapshot_id"]
    by_table = {row["table"]: row for row in plan["table_plans"]}
    assert by_table["edna_detection"]["scientific_corrections"] == 1
    assert plan["anemone"]["normalization_id"] == identifiers["normalization_id"]


def test_edna_document_trace_and_snapshot_retain_exact_source_records(tmp_path, monkeypatch):
    from retrieval.edna_document_builder import build_edna_documents
    from retrieval.edna_materializer import _document_frame, _write_artifacts
    from ingestion.provenance_snapshot import prepare_snapshot

    data_dir, _ = _configure_lineage_paths(tmp_path, monkeypatch)
    identifiers = _write_anemone_bundle(data_dir)
    root = data_dir / "normalized" / "anemone" / "snapshots" / identifiers["normalization_id"]
    samples = pd.read_parquet(root / "edna_sample.parquet")
    assays = pd.read_parquet(root / "edna_assay.parquet")
    detections = pd.read_parquet(root / "edna_detection.parquet")
    detections["assignment_method"] = "qcauto_target"
    detections["read_count"] = 10
    documents = build_edna_documents(samples, assays, detections)
    _write_artifacts(documents, _document_frame(documents))
    monkeypatch.setattr(lineage, "_database_anemone_source_file_traces", lambda: [])
    monkeypatch.setattr(lineage, "_database_embedding_status", lambda: {"available": True, "rows": {documents[0].doc_id: False}})
    trace = lineage.build_document_trace(documents[0].doc_id)
    assert trace["found"] is True
    document = trace["trace"]["document"]
    assert document["metadata"]["canonical_records"][-1]["source_row_locator"] == 2
    assert document["source_file_ids"] == [f"raw:anemone:{identifiers['source_file_id']}"]
    assert len(document["source_artifact_ids"]) == 8
    snapshot = prepare_snapshot(lineage.build_provenance_manifest(), manifest_id="edna-fixture")
    assert snapshot.documents[0]["metadata"] == document["metadata"]
