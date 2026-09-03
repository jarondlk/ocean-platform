from __future__ import annotations

import importlib
import hashlib
import json
import sys

import pandas as pd


def _write_normalized_bundle(root, normalization_id="a" * 64):
    bundle_root = root / "snapshots" / normalization_id
    bundle_root.mkdir(parents=True)
    frames = {
        "external_source_snapshot": pd.DataFrame([{"snapshot_id": "b" * 64}]),
        "external_source_file": pd.DataFrame([{"source_file_id": "c" * 64}]),
        "edna_sample": pd.DataFrame([{"sample_id": "d" * 64}]),
        "edna_assay": pd.DataFrame([{"assay_id": "e" * 64}]),
        "edna_detection": pd.DataFrame([{"detection_id": "f" * 64}]),
        "edna_internal_standard": pd.DataFrame(
            [{"internal_standard_id": "1" * 64}]
        ),
        "edna_anchor_event": pd.DataFrame(columns=["event_id"]),
    }
    artifacts = {}
    for name, frame in frames.items():
        path = bundle_root / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        artifacts[name] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "row_count": len(frame),
        }
    manifest = {
        "normalization_id": normalization_id,
        "source_snapshot_id": "b" * 64,
        "source_scope_level": "sample",
        "status": "complete",
        "artifacts": artifacts,
    }
    (bundle_root / "normalization_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (root / "current.json").write_text(
        json.dumps({"normalization_id": normalization_id}),
        encoding="utf-8",
    )
    return bundle_root, manifest


def test_source_row_hash_is_stable_and_content_sensitive():
    load_db = importlib.import_module("scripts.load_db")
    frame = pd.DataFrame(
        [
            {
                "sample_id": "2024-01-O-s1",
                "temperature": 12.3,
                "observed_at": pd.Timestamp("2024-01-18"),
            }
        ]
    )

    first = load_db.add_source_row_hash(frame)
    second = load_db.add_source_row_hash(frame.copy())
    changed = load_db.add_source_row_hash(
        frame.assign(temperature=12.4)
    )

    assert first.loc[0, "source_row_hash"] == second.loc[0, "source_row_hash"]
    assert len(first.loc[0, "source_row_hash"]) == 64
    assert first.loc[0, "source_row_hash"] != changed.loc[0, "source_row_hash"]


def test_upsert_counts_do_not_double_count_replaced_rows():
    load_db = importlib.import_module("scripts.load_db")

    counts = load_db._upsert_count_summary(
        matched=82,
        replaced=82,
        inserted_after_delete=85,
    )

    assert counts == {
        "updated": 82,
        "inserted": 3,
        "unchanged": 0,
    }


def test_upsert_counts_reject_inconsistent_database_results():
    load_db = importlib.import_module("scripts.load_db")

    try:
        load_db._upsert_count_summary(
            matched=1,
            replaced=2,
            inserted_after_delete=2,
        )
    except RuntimeError as exc:
        assert "inconsistent row counts" in str(exc)
    else:
        raise AssertionError("Inconsistent upsert counts were accepted")


def test_mutating_upsert_cli_delegates_to_transactional_loader(
    monkeypatch,
    capsys,
):
    load_db = importlib.import_module("scripts.load_db")
    monkeypatch.setattr(
        load_db,
        "upsert_corpus",
        lambda: {
            "mode": "upsert",
            "incoming_rows": 3,
            "inserted_rows": 1,
            "updated_rows": 1,
            "unchanged_rows": 1,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["load_db.py", "--upsert", "--json"],
    )

    load_db.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "upsert"
    assert payload["inserted_rows"] == 1


def test_database_loader_requires_explicit_safe_mutation_mode(
    monkeypatch,
):
    load_db = importlib.import_module("scripts.load_db")
    monkeypatch.setattr(sys, "argv", ["load_db.py"])

    try:
        load_db.main()
    except SystemExit as exc:
        assert "Choose a safe database mutation mode" in str(exc)
    else:
        raise AssertionError("Unsafe implicit append mode was accepted")


def test_prepare_dataframe_preserves_normalizer_source_hash(monkeypatch):
    load_db = importlib.import_module("scripts.load_db")
    monkeypatch.setattr(
        load_db,
        "_database_column_definitions",
        lambda _table: {
            "sample_id": {"name": "sample_id", "type": load_db.String()},
            "source_row_hash": {
                "name": "source_row_hash",
                "type": load_db.String(),
            },
        },
    )
    expected_hash = "9" * 64

    prepared = load_db._prepare_dataframe(
        pd.DataFrame(
            [{"sample_id": "sample-1", "source_row_hash": expected_hash}]
        ),
        "edna_sample",
    )

    assert prepared.loc[0, "source_row_hash"] == expected_hash


def test_anemone_bundle_resolution_checks_pointer_and_artifact_hash(
    tmp_path,
    monkeypatch,
):
    load_db = importlib.import_module("scripts.load_db")
    bundle_root, manifest = _write_normalized_bundle(tmp_path)
    monkeypatch.setattr(load_db.config, "ANEMONE_NORMALIZED_DIR", tmp_path)

    frames, loaded_manifest = load_db._load_anemone_bundle_frames(
        None,
        allow_noncurrent=False,
    )

    assert loaded_manifest["normalization_id"] == manifest["normalization_id"]
    assert len(frames["edna_sample"]) == 1

    (bundle_root / "edna_sample.parquet").write_bytes(b"changed")
    try:
        load_db._load_anemone_bundle_frames(None, allow_noncurrent=False)
    except Exception as exc:
        assert "artifact" in str(exc).lower()
    else:
        raise AssertionError("Tampered normalized artifact was accepted")


def test_anemone_scope_is_provider_and_sample_or_run():
    load_db = importlib.import_module("scripts.load_db")
    samples = pd.DataFrame(
        [
            {
                "provider": "anemone",
                "provider_sample_id": "sample-1",
                "provider_project_id": "project-1",
                "provider_run_id": "run-1",
            }
        ]
    )

    sample_scope, sample_parameters = load_db._scope_parameters(
        samples,
        {"source_scope_level": "sample"},
    )
    run_scope, run_parameters = load_db._scope_parameters(
        samples,
        {"source_scope_level": "run"},
    )

    assert "provider_sample_id" in sample_scope
    assert sample_parameters["provider"] == "anemone"
    assert "provider_project_id" in run_scope
    assert run_parameters["provider_run_id"] == "run-1"


def test_anemone_cli_forwards_explicit_noncurrent_override(monkeypatch, capsys):
    load_db = importlib.import_module("scripts.load_db")
    captured = {}

    def fake_upsert(**kwargs):
        captured.update(kwargs)
        return {
            "mode": "upsert",
            "incoming_rows": 0,
            "inserted_rows": 0,
            "updated_rows": 0,
            "unchanged_rows": 0,
        }

    monkeypatch.setattr(load_db, "upsert_corpus", fake_upsert)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "load_db.py",
            "--upsert",
            "--json",
            "--anemone-normalization-id",
            "a" * 64,
            "--allow-anemone-noncurrent",
        ],
    )

    load_db.main()

    json.loads(capsys.readouterr().out)
    assert captured == {
        "anemone_normalization_id": "a" * 64,
        "allow_anemone_noncurrent": True,
    }
