from __future__ import annotations

import json
import lzma
import sys
from pathlib import Path

import pandas as pd
import pytest

from ingestion.anemone import load_contract, sync_anemone
from preprocessing.anemone import (
    AnemoneNormalizationError,
    build_anemone_bundle,
    normalize_anemone_snapshot,
    resolve_normalized_bundle,
)
from tests.test_anemone_ingestion import (
    PASSWORD,
    PROJECT,
    RUN,
    SAMPLE,
    USERNAME,
    _credentials,
    _fixture_server,
    _local_contract,
    _scope,
)


def _replace_xz_text(payload: bytes, old: str, new: str) -> bytes:
    text = lzma.decompress(payload).decode("utf-8")
    assert old in text
    return lzma.compress(text.replace(old, new).encode("utf-8"))


def _acquire_snapshot(
    raw_root: Path,
    *,
    mutate=None,
) -> tuple[str, dict]:
    contract = load_contract()
    with _fixture_server(contract) as (base, payloads, _):
        if mutate:
            mutate(payloads)
        result = sync_anemone(
            _scope(base),
            credentials=_credentials(),
            execute=True,
            output_root=raw_root,
            contract=_local_contract(base),
            allow_insecure_http=True,
            generated_at="2026-09-01T00:00:00+00:00",
        )
    return result["snapshot_id"], _local_contract(base)


def test_validate_only_builds_complete_frames_without_writing(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    normalized_root = tmp_path / "normalized"
    snapshot_id, contract = _acquire_snapshot(raw_root)

    result = normalize_anemone_snapshot(
        snapshot_id,
        raw_root=raw_root,
        normalized_root=normalized_root,
        contract=contract,
        generated_at="2026-09-01T01:00:00+00:00",
    )

    assert result["mode"] == "validate"
    assert result["row_counts"] == {
        "external_source_snapshot": 1,
        "external_source_file": 13,
        "edna_sample": 1,
        "edna_assay": 1,
        "edna_detection": 2,
        "edna_internal_standard": 1,
        "edna_anchor_event": 1,
    }
    assert result["sample_kind_counts"] == {"environmental": 1}
    assert result["control_count"] == 0
    assert result["assignment_method_counts"] == {
        "qcauto_95pct_3nn_target": 1,
        "qcauto_target": 1,
    }
    assert len(result["source_file_hashes"]) == 13
    assert result["validation"] == {"errors": 0, "warnings": 0}
    assert not normalized_root.exists()
    serialized = json.dumps(result)
    assert USERNAME not in serialized
    assert PASSWORD not in serialized


def test_execute_publishes_deterministic_bundle_and_activation_pointer(
    tmp_path: Path,
) -> None:
    raw_root = tmp_path / "raw"
    normalized_root = tmp_path / "normalized"
    snapshot_id, contract = _acquire_snapshot(raw_root)
    arguments = {
        "execute": True,
        "activate": True,
        "raw_root": raw_root,
        "normalized_root": normalized_root,
        "contract": contract,
        "generated_at": "2026-09-01T01:00:00+00:00",
    }

    first = normalize_anemone_snapshot(snapshot_id, **arguments)
    second = normalize_anemone_snapshot(snapshot_id, **arguments)

    assert first["normalization_id"] == second["normalization_id"]
    assert first["reused_bundle"] is False
    assert second["reused_bundle"] is True
    root, manifest = resolve_normalized_bundle(
        normalized_root=normalized_root
    )
    assert root == Path(first["bundle_path"])
    assert manifest["status"] == "complete"
    assert len(list(root.glob("*.parquet"))) == 7
    detections = pd.read_parquet(root / "edna_detection.parquet")
    assert set(detections["assignment_method"]) == {
        "qcauto_target",
        "qcauto_95pct_3nn_target",
    }
    assert set(detections["read_count"]) == {17}
    assert set(detections["copies_per_ml"]) == {2.5}
    assert all(detections["assigned_taxon_name"] == "Fixture fish")
    sample = pd.read_parquet(root / "edna_sample.parquet").iloc[0]
    assert sample["sample_kind"] == "environmental"
    assert bool(sample["is_control"]) is False
    assert sample["collection_date_utc"] == "2024-01-01"
    assert sample["temporal_precision"] == "date"


def test_provider_ids_and_scientific_hashes_ignore_metadata_row_order(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_id, first_contract = _acquire_snapshot(first_root)

    def reverse_metadata(payloads: dict[str, bytes]) -> None:
        path = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/sample.tsv.xz"
        text = lzma.decompress(payloads[path]).decode("utf-8")
        header, *rows = text.strip().splitlines()
        payloads[path] = lzma.compress(
            ("\n".join([header, *reversed(rows)]) + "\n").encode("utf-8")
        )

    second_id, second_contract = _acquire_snapshot(
        second_root,
        mutate=reverse_metadata,
    )
    first = build_anemone_bundle(
        first_id,
        raw_root=first_root,
        contract=first_contract,
    )
    second = build_anemone_bundle(
        second_id,
        raw_root=second_root,
        contract=second_contract,
    )
    for table, key in (
        ("edna_sample", "sample_id"),
        ("edna_assay", "assay_id"),
        ("edna_detection", "detection_id"),
        ("edna_internal_standard", "internal_standard_id"),
    ):
        assert list(first.frames[table][key]) == list(second.frames[table][key])
        assert list(first.frames[table]["scientific_content_sha256"]) == list(
            second.frames[table]["scientific_content_sha256"]
        )


def test_control_is_preserved_without_anchor(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"

    def make_control(payloads: dict[str, bytes]) -> None:
        path = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/sample.tsv.xz"
        payloads[path] = _replace_xz_text(
            payloads[path],
            "sample_type\tenvironmental",
            "sample_type\tnegative_control",
        )

    snapshot_id, contract = _acquire_snapshot(raw_root, mutate=make_control)
    bundle = build_anemone_bundle(
        snapshot_id,
        raw_root=raw_root,
        contract=contract,
    )
    sample = bundle.frames["edna_sample"].iloc[0]
    assert sample["sample_kind"] == "negative_control"
    assert bool(sample["is_control"]) is True
    assert pd.isna(sample["anchor_event_id"])
    assert bundle.frames["edna_anchor_event"].empty
    assert len(bundle.frames["edna_detection"]) == 2


def test_unknown_classification_is_explicit_and_preserved(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"

    def remove_classification(payloads: dict[str, bytes]) -> None:
        path = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/sample.tsv.xz"
        text = lzma.decompress(payloads[path]).decode("utf-8")
        rows = [line for line in text.splitlines() if "\tsample_type\t" not in line]
        payloads[path] = lzma.compress(("\n".join(rows) + "\n").encode("utf-8"))

    snapshot_id, contract = _acquire_snapshot(
        raw_root,
        mutate=remove_classification,
    )
    bundle = build_anemone_bundle(
        snapshot_id,
        raw_root=raw_root,
        contract=contract,
    )
    assert bundle.frames["edna_sample"].iloc[0]["sample_kind"] == "unknown"
    assert bundle.frames["edna_anchor_event"].empty
    assert {issue.code for issue in bundle.issues} == {
        "sample_classification_unknown"
    }


def test_invalid_coordinate_fails_normalization_without_output(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    normalized_root = tmp_path / "normalized"

    def invalid_coordinate(payloads: dict[str, bytes]) -> None:
        path = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/sample.tsv.xz"
        payloads[path] = _replace_xz_text(
            payloads[path],
            "lat_lon\t38.4 141.5",
            "lat_lon\t138.4 141.5",
        )

    snapshot_id, contract = _acquire_snapshot(raw_root, mutate=invalid_coordinate)
    with pytest.raises(AnemoneNormalizationError) as failure:
        normalize_anemone_snapshot(
            snapshot_id,
            execute=True,
            raw_root=raw_root,
            normalized_root=normalized_root,
            contract=contract,
        )
    assert failure.value.code == "coordinate_out_of_range"
    assert not normalized_root.exists()


def test_tampered_completed_snapshot_is_rejected(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    snapshot_id, contract = _acquire_snapshot(raw_root)
    snapshot_root = raw_root / "snapshots" / snapshot_id
    with (snapshot_root / "sample.tsv.xz").open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(AnemoneNormalizationError) as failure:
        build_anemone_bundle(
            snapshot_id,
            raw_root=raw_root,
            contract=contract,
        )
    assert failure.value.code == "snapshot_source_size_mismatch"


def test_normalize_cli_defaults_to_validation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import scripts.normalize_anemone as command

    captured: dict = {}

    def fake_normalize(snapshot_id: str, **kwargs: object) -> dict:
        captured.update({"snapshot_id": snapshot_id, **kwargs})
        return {"ok": True, "mode": "validate"}

    monkeypatch.setattr(command, "normalize_anemone_snapshot", fake_normalize)
    monkeypatch.setattr(
        sys,
        "argv",
        ["normalize_anemone.py", "--snapshot-id", "a" * 64],
    )
    assert command.main() == 0
    assert captured["execute"] is False
    assert captured["activate"] is False
    assert json.loads(capsys.readouterr().out)["mode"] == "validate"
