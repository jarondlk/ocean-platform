from copy import deepcopy
import hashlib
import json
import lzma
import io
import zipfile
from pathlib import Path
import sys

import pandas as pd
import pytest

import config

from preprocessing.anemone import (
    AnemoneNormalizationError,
    build_anemone_bundle,
    normalize_anemone_snapshot,
    resolve_normalized_bundle,
    stable_sha256,
)
from preprocessing.anemone_classification import (
    MAX_REVIEW_BYTES,
    ReviewError,
    parse_review,
    read_review,
    review_template,
)
from tests.test_anemone_normalization import _acquire_snapshot
from tests.test_anemone_ingestion import PROJECT, RUN, SAMPLE


def _remove_classification(payloads):
    path = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/sample.tsv.xz"
    rows = lzma.decompress(payloads[path]).decode().splitlines()
    payloads[path] = lzma.compress(
        ("\n".join(row for row in rows if "\tsample_type\t" not in row) + "\n").encode()
    )


def approve_fixture(draft, kind="environmental"):
    """Synthetic test review only; never approves a real provider sample."""
    review = deepcopy(draft)
    review["status"] = "approved"
    for decision in review["decisions"]:
        decision.update(
            sample_kind=kind,
            reviewer="Fixture researcher",
            reviewed_at="2026-09-03T08:00:00Z",
            rationale="Synthetic fixture protocol confirms this sample category.",
        )
        decision["evidence"] = decision["evidence"][:1]
    return parse_review(json.dumps(review).encode())


@pytest.fixture
def unknown_snapshot(tmp_path):
    raw = tmp_path / "raw"
    sid, contract = _acquire_snapshot(raw, mutate=_remove_classification)
    draft = review_template(sid, raw_root=raw, contract=contract)
    return sid, dict(raw_root=raw, contract=contract), draft


def test_draft_is_read_only_unapproved_and_source_remains_unknown(
    unknown_snapshot, tmp_path
):
    sid, kwargs, draft = unknown_snapshot
    assert draft["status"] == "draft"
    assert draft["decisions"][0]["sample_kind"] == "unknown"
    assert draft["decisions"][0]["reviewer"] == ""
    with pytest.raises(ReviewError):
        parse_review(json.dumps(draft).encode())
    with pytest.raises(AnemoneNormalizationError, match="unapproved"):
        normalize_anemone_snapshot(
            sid,
            **kwargs,
            classification_review=draft,
            execute=True,
            normalized_root=tmp_path / "normalized",
        )
    assert not (tmp_path / "normalized").exists()
    bundle = build_anemone_bundle(sid, **kwargs)
    assert bundle.frames["edna_sample"].iloc[0]["sample_kind"] == "unknown"
    assert bundle.frames["edna_sample"].iloc[0]["classification_review_json"] is None
    assert bundle.frames["edna_anchor_event"].empty


def test_review_preserves_source_creates_distinct_replayable_history(
    unknown_snapshot, tmp_path, monkeypatch
):
    from retrieval.edna_document_builder import build_edna_documents
    from preprocessing.edna_recipe import AnalysisRecipe
    from preprocessing.edna_analysis import build_analysis
    from ingestion import lineage

    sid, kwargs, draft = unknown_snapshot
    source_root = kwargs["raw_root"] / "snapshots" / sid
    source_hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source_root.iterdir()
    }
    review = approve_fixture(draft)
    plain = build_anemone_bundle(sid, **kwargs)
    reviewed = build_anemone_bundle(sid, **kwargs, classification_review=review)
    assert plain.normalization_id != reviewed.normalization_id
    sample = reviewed.frames["edna_sample"].iloc[0]
    assert sample["sample_id"] == plain.frames["edna_sample"].iloc[0]["sample_id"]
    assert (
        sample["raw_metadata_json"]
        == plain.frames["edna_sample"].iloc[0]["raw_metadata_json"]
    )
    assert sample["sample_kind"] == "environmental" and not bool(sample["is_control"])
    record = json.loads(sample["classification_review_json"])
    assert sample["classification_basis"] == "review:" + stable_sha256(record)
    assert (
        record["provider_classification_basis"] == "no_reviewed_classification_metadata"
    )
    pd.testing.assert_frame_equal(
        plain.frames["edna_detection"], reviewed.frames["edna_detection"]
    )
    assert len(reviewed.frames["edna_anchor_event"]) == 1
    normalized = tmp_path / "normalized"
    old = normalize_anemone_snapshot(
        sid, **kwargs, execute=True, normalized_root=normalized
    )
    options = dict(
        **kwargs, execute=True, normalized_root=normalized, classification_review=review
    )
    first = normalize_anemone_snapshot(sid, **options)
    second = normalize_anemone_snapshot(sid, **options)
    assert not first["reused_bundle"] and second["reused_bundle"]
    assert (
        resolve_normalized_bundle(
            first["normalization_id"], normalized_root=normalized
        )[1]["classification_review"]
        == review
    )
    assert resolve_normalized_bundle(
        old["normalization_id"], normalized_root=normalized
    )
    changed = deepcopy(review)
    changed["decisions"][0]["rationale"] += " Additional reviewed evidence."
    assert (
        build_anemone_bundle(
            sid, **kwargs, classification_review=changed
        ).normalization_id
        != reviewed.normalization_id
    )
    assert source_hashes == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source_root.iterdir()
    }

    documents = build_edna_documents(
        *(reviewed.frames[t] for t in ("edna_sample", "edna_assay", "edna_detection"))
    )
    assert all(d.metadata["classification_review"] == record for d in documents)
    assert all("researcher review" in d.text for d in documents)
    monkeypatch.setattr(
        lineage,
        "_resolve_anemone_lineage_bundle",
        lambda: resolve_normalized_bundle(
            first["normalization_id"], normalized_root=normalized
        ),
    )
    trace = next(
        t for t in lineage.build_anemone_row_traces() if t["table"] == "edna_sample"
    )
    assert trace["classification_review"] == record
    recipe = AnalysisRecipe.model_validate(
        {
            "cohort": {"sample_ids": [sample["sample_id"]]},
            "assignment_methods": ["qcauto_target", "qcauto_95pct_3nn_target"],
            "rank": "genus",
            "control_policy": "environmental_only",
        }
    )

    def analysis(b):
        return build_analysis(
            recipe,
            {k: json.loads(v.to_json(orient="records")) for k, v in b.frames.items()},
        )

    assert analysis(plain)["tables"]["diversity"] == []
    result = analysis(reviewed)
    assert len(result["tables"]["diversity"]) == 2
    assert (
        result["inputs"]["canonical"]["edna_sample"][0]["classification_review_json"]
        == sample["classification_review_json"]
    )


@pytest.mark.parametrize(
    "kind", ["negative_control", "positive_control", "mock_community"]
)
def test_reviewed_controls_never_gain_environmental_anchor(unknown_snapshot, kind):
    sid, kwargs, draft = unknown_snapshot
    bundle = build_anemone_bundle(
        sid, **kwargs, classification_review=approve_fixture(draft, kind)
    )
    sample = bundle.frames["edna_sample"].iloc[0]
    assert sample["sample_kind"] == kind and bool(sample["is_control"])
    assert bundle.frames["edna_anchor_event"].empty


@pytest.mark.parametrize("change", ["snapshot", "sample", "sha", "row", "key", "value"])
def test_review_rejects_wrong_evidence_scope(unknown_snapshot, change):
    sid, kwargs, draft = unknown_snapshot
    review = approve_fixture(draft)
    decision = review["decisions"][0]
    if change == "snapshot":
        review["source_snapshot_id"] = "a" * 64
    elif change == "sample":
        decision["provider_sample_id"] = "different-sample"
    else:
        decision["evidence"][0][
            {"sha": "source_sha256", "row": "row_number"}.get(change, change)
        ] = "a" * 64 if change == "sha" else 9999 if change == "row" else "incorrect"
    with pytest.raises(AnemoneNormalizationError) as exc:
        build_anemone_bundle(sid, **kwargs, classification_review=review)
    assert exc.value.code == "classification_review_invalid"


def test_review_cannot_override_provider_classification(tmp_path):
    raw = tmp_path / "raw"
    sid, contract = _acquire_snapshot(raw)
    assert review_template(sid, raw_root=raw, contract=contract)["decisions"] == []
    review = minimal_review()
    review["source_snapshot_id"] = sid
    review["decisions"][0]["provider_sample_id"] = SAMPLE
    with pytest.raises(AnemoneNormalizationError, match="override"):
        build_anemone_bundle(
            sid, raw_root=raw, contract=contract, classification_review=review
        )


def test_review_variants_link_exact_normalization_and_export_attestation(
    unknown_snapshot, tmp_path, monkeypatch
):
    from ingestion import lineage
    from retrieval.edna_document_builder import build_edna_documents
    from retrieval.edna_materializer import _document_frame
    from preprocessing.edna_analysis import build_analysis
    from preprocessing.edna_recipe import AnalysisRecipe
    from ingestion.edna_analysis_bundle import publish_analysis
    from api.edna_analysis_routes import export

    sid, kwargs, draft = unknown_snapshot
    normalized = tmp_path / "normalized"
    old = normalize_anemone_snapshot(
        sid, **kwargs, execute=True, activate=True, normalized_root=normalized
    )
    review = approve_fixture(draft)
    new = normalize_anemone_snapshot(
        sid,
        **kwargs,
        execute=True,
        classification_review=review,
        normalized_root=normalized,
    )
    bundle = build_anemone_bundle(sid, **kwargs, classification_review=review)
    documents = build_edna_documents(
        *(bundle.frames[t] for t in ("edna_sample", "edna_assay", "edna_detection"))
    )
    monkeypatch.setattr(config, "ANEMONE_NORMALIZED_DIR", normalized)
    monkeypatch.setattr(
        lineage, "_read_retrieval_documents", lambda: _document_frame(documents)
    )
    traces = lineage.build_document_traces()
    for trace in traces:
        artifacts = [
            a for a in trace.source_artifact_ids if a.startswith("normalized:anemone:")
        ]
        assert len(artifacts) == 7
        assert all(
            new["normalization_id"] in a and old["normalization_id"] not in a
            for a in artifacts
        )
        assert (
            trace.metadata["classification_review"]["decision"]
            == review["decisions"][0]
        )

    sample_id = bundle.frames["edna_sample"].iloc[0]["sample_id"]
    recipe = AnalysisRecipe.model_validate(
        {
            "cohort": {"sample_ids": [sample_id]},
            "assignment_methods": ["qcauto_target"],
            "rank": "genus",
            "control_policy": "environmental_only",
        }
    )
    result = build_analysis(
        recipe,
        {k: json.loads(v.to_json(orient="records")) for k, v in bundle.frames.items()},
    )
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path / "analysis")
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    publish_analysis(result)
    response = export(result["analysis_id"], format="bundle")
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        inputs = json.loads(archive.read("inputs.json"))
    exported = json.loads(
        inputs["canonical"]["edna_sample"][0]["classification_review_json"]
    )
    assert exported["decision"] == review["decisions"][0]


def minimal_review():
    return {
        "schema_version": 1,
        "status": "approved",
        "source_snapshot_id": "a" * 64,
        "decisions": [
            {
                "provider_sample_id": "fixture",
                "sample_kind": "environmental",
                "reviewer": "Fixture reviewer",
                "reviewed_at": "2026-09-03T08:00:00+00:00",
                "rationale": "Synthetic protocol confirms sample type.",
                "evidence": [
                    {
                        "source_role": "sample_metadata",
                        "source_sha256": "b" * 64,
                        "row_number": 2,
                        "key": "sample_type",
                        "value": "fixture_field",
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("reviewer", " "),
        ("reviewed_at", "2026-09-03"),
        ("reviewed_at", "not-a-time"),
        ("rationale", ""),
        ("sample_kind", "unknown"),
        ("sample_kind", "field"),
        ("evidence", []),
        ("is_control", False),
    ],
)
def test_invalid_decisions_are_sanitized(field, value):
    review = minimal_review()
    review["decisions"][0][field] = value
    with pytest.raises(ReviewError) as exc:
        parse_review(json.dumps(review).encode())
    assert "Fixture reviewer" not in str(exc.value)


def test_review_rejects_duplicates_oversize_symlinks_and_unknown_fields(tmp_path):
    review = minimal_review()
    review["decisions"].append(deepcopy(review["decisions"][0]))
    with pytest.raises(ReviewError, match="duplicate samples"):
        parse_review(json.dumps(review).encode())
    review = minimal_review()
    review["decisions"][0]["evidence"] *= 2
    with pytest.raises(ReviewError, match="duplicate evidence"):
        parse_review(json.dumps(review).encode())
    with pytest.raises(ReviewError):
        parse_review(b'{"status":"draft","status":"approved"}')
    path = tmp_path / "large.json"
    path.write_bytes(b" " * (MAX_REVIEW_BYTES + 1))
    with pytest.raises(ReviewError, match="limit"):
        read_review(path)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(ReviewError, match="regular file"):
        read_review(link)


def test_review_manifest_tamper_is_rejected(unknown_snapshot, tmp_path):
    sid, kwargs, draft = unknown_snapshot
    result = normalize_anemone_snapshot(
        sid,
        **kwargs,
        classification_review=approve_fixture(draft),
        execute=True,
        normalized_root=tmp_path / "normalized",
    )
    path = Path(result["bundle_path"]) / "normalization_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["classification_review"]["decisions"][0]["reviewer"] = "Different reviewer"
    path.write_text(json.dumps(manifest))
    with pytest.raises(AnemoneNormalizationError, match="inconsistent"):
        resolve_normalized_bundle(
            result["normalization_id"], normalized_root=tmp_path / "normalized"
        )


def test_normalize_cli_passes_review_and_rejects_template_mutations(
    tmp_path, monkeypatch, capsys
):
    from scripts import normalize_anemone as cli

    review = minimal_review()
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))

    def normalize(sid, **kwargs):
        assert sid == "a" * 64 and kwargs["classification_review"] == review
        assert kwargs["execute"] is False
        return {"mode": "validate"}

    monkeypatch.setattr(cli, "normalize_anemone_snapshot", normalize)
    monkeypatch.setattr(
        sys,
        "argv",
        ["normalize", "--snapshot-id", "a" * 64, "--classification-review", str(path)],
    )
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "validate"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "normalize",
            "--snapshot-id",
            "a" * 64,
            "--classification-review-template",
            "--execute",
        ],
    )
    with pytest.raises(SystemExit):
        cli.main()
