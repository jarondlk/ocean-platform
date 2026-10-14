"""Offline C02 regressions: generation is a candidate, never automatic approval."""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

import config
from orchestration import unified
from preprocessing import derived_artifacts as derived


@pytest.fixture
def local_roots(tmp_path, monkeypatch):
    for name in ("ANALYSIS_DIR", "RELIABILITY_DIR", "NORMALIZED_DIR", "SERVING_DIR"):
        root = tmp_path / name.lower()
        root.mkdir()
        monkeypatch.setattr(config, name, root)
    return tmp_path


def operation(inputs=None):
    return {"status": "computed", "method_version": derived.CURRENT_METHODS["taxa_env_correlation"],
            "inputs": inputs or {"fixture://full-abundance": "a" * 64}, "parameters": {"synthetic": True}}


def candidate(inputs=None):
    return derived.stamp_document({"id": "analysis_taxa_env_correlations", "analysis_type": "taxa_env_correlation",
                                   "title": "Synthetic correlation", "text": "SYNTHETIC_DERIVED_MARKER"},
                                  "taxa_env_correlation", operation(inputs))


def decision(generation):
    return {"reviewer": "Synthetic test reviewer", "rationale": "Offline eligibility regression; no scientific approval.",
            "references": ["fixture://C02"], "evidence_sha256": generation}


def reviewed(document):
    return derived.review_document(document, decision(document["derived_artifact"]["generation_sha256"]))


def test_regeneration_requires_an_explicit_bound_decision(local_roots):
    document = candidate()
    assert derived.document_eligibility(document).status == "review_required"
    selected = reviewed(document)
    assert derived.document_eligibility(selected).eligible
    assert selected["derived_artifact"]["scientific_approval"] is False
    with pytest.raises(ValueError, match="exact regenerated"):
        derived.review_document(document, decision("b" * 64))


@pytest.mark.parametrize("change", ["output", "inputs", "method", "review", "namespace"])
def test_tampering_or_receipt_substitution_cannot_restore_eligibility(local_roots, change):
    document = reviewed(candidate())
    raw = document["derived_artifact"]
    if change == "output":
        document["text"] = "different scientific result"
    elif change == "inputs":
        raw["inputs"]["fixture://full-abundance"] = "b" * 64
    elif change == "method":
        raw["method_version"] = "legacy-v1"
    elif change == "review":
        raw["review"]["evidence_sha256"] = "b" * 64
    else:
        document["derived_artifact"] = derived.stamp_document(
            derived._document_payload(document), "sst_ctd_validation",
            {**operation(), "method_version": derived.CURRENT_METHODS["sst_ctd_validation"]})["derived_artifact"]
    assert not derived.document_eligibility(document).eligible


def test_stale_selected_inputs_require_regeneration(local_roots):
    document = reviewed(candidate())
    assert derived.document_eligibility(document, expected_inputs={"fixture://full-abundance": "b" * 64}).status == "stale_inputs"


@pytest.mark.parametrize("kind", ["invalidated", "superseded"])
def test_invalidation_preserves_history_and_cannot_be_reauthorized(local_roots, kind):
    original = reviewed(candidate())
    changed = derived.invalidate_document(original, "Scientific method changed.",
                                          superseded_by="b" * 64 if kind == "superseded" else None)
    assert changed["text"] == original["text"]
    assert changed["derived_artifact"]["review"] == original["derived_artifact"]["review"]
    assert derived.document_eligibility(changed).status == kind
    with pytest.raises(ValueError, match="Invalidated historical"):
        reviewed(changed)


@pytest.mark.parametrize("role", ["analysis", "reliability", "linked", "primary"])
def test_unversioned_derived_documents_cannot_bypass_prompt_selection(local_roots, monkeypatch, role):
    document = {"id": "reliability_corroboration_summary", "analysis_type": "corroboration", "title": "Old tiers",
                "source_type": "reliability", "text": "SYNTHETIC_DERIVED_MARKER verified"}
    monkeypatch.setattr(unified, "analysis_context_documents", lambda query: [document] if role == "analysis" else [])
    monkeypatch.setattr(unified, "reliability_context_documents", lambda query: [document] if role == "reliability" else [])
    prompt, manifest = unified.build_prompt_with_context("temperature", [document] if role == "primary" else [],
                                                         linked_results=[document] if role == "linked" else [])
    assert "SYNTHETIC_DERIVED_MARKER" not in prompt
    assert any(row["reason"] == "legacy_unversioned" and row["role"] == role for row in manifest["omitted"])


def test_unknown_derived_types_fail_closed_and_unaffected_trends_survive(local_roots):
    assert not derived.document_eligibility({"id": "renamed", "analysis_type": "unknown"}, role="analysis").eligible
    assert derived.document_eligibility({"analysis_type": "ctd_temporal_trends"}, role="analysis").eligible


def test_history_snapshot_retains_bytes_and_blocks_copied_reviewed_generations(local_roots, monkeypatch):
    document = reviewed(candidate())
    monkeypatch.setattr(derived, "current_method_inputs", lambda method: document["derived_artifact"]["inputs"])
    current = config.ANALYSIS_DIR / "analysis_documents.jsonl"
    original = (json.dumps(document) + "\n").encode()
    current.write_bytes(original)
    assert unified._read_context_documents(current)
    history = derived.retain_artifact_history(config.ANALYSIS_DIR, [current.name])
    archived = config.ANALYSIS_DIR / "derived_history" / history["generation_sha256"] / current.name
    assert archived.read_bytes() == original
    assert history["files"][current.name] == hashlib.sha256(original).hexdigest()
    assert not unified._read_context_documents(archived)
    assert unified._read_context_documents(archived, include_ineligible=True)[0]["derived_eligibility"]["status"] == "superseded"
    # Even an unchanged copy of the formerly reviewed bytes cannot restore it.
    assert not unified._read_context_documents(current)
    alias = local_roots / "history-alias.jsonl"
    alias.symlink_to(archived)
    assert not unified._read_context_documents(alias)


@pytest.mark.parametrize("payload", ["not JSON", '{"schema_version": 1, "superseded_generations": "not-a-list"}',
                                     '{"schema_version": 1, "superseded_generations": ["bad-hash"]}'])
def test_corrupt_invalidation_registry_cannot_authorize_a_reviewed_generation(local_roots, payload):
    document = reviewed(candidate())
    (config.ANALYSIS_DIR / "derived_invalidations.json").write_text(payload)
    assert derived.document_eligibility(document).status == "invalid_registry"


def test_unvalidated_gap_cannot_borrow_a_current_method_or_review(local_roots):
    gap = derived.stamp_document({"id": "reliability_gap_interpolation", "analysis_type": "gap_interpolation", "text": "Old estimate"},
                                 "gap_interpolation", operation())
    assert derived.document_eligibility(gap).status == "legacy_method"
    with pytest.raises(ValueError, match="not eligible"):
        reviewed(gap)


def test_synthetic_regeneration_preserves_previous_output_and_requires_review(local_roots, monkeypatch):
    import preprocessing.pre_analysis as analysis
    # Full rectangular normalized measurements, including explicit zero.
    ids = [f"fixture-{index}" for index in range(12)]
    pd.DataFrame({"sample_id": ids, "has_ctd": True, "has_kraken": True,
                  "mean_temperature": list(range(12))}).to_parquet(config.SERVING_DIR / "sample_multisource_context.parquet")
    pd.DataFrame({"sample_id": ids, "genus": "Measured", "method": "kraken", "abundance_value": list(range(12))}).to_parquet(
        config.NORMALIZED_DIR / "kraken_genus_abundance.parquet")
    old = config.ANALYSIS_DIR / "taxa_env_correlations.parquet"
    pd.DataFrame({"genus": ["legacy-artifact"], "significant": [True]}).to_parquet(old)
    old_bytes = old.read_bytes()
    # Exercise the actual correlation algorithm and document generation, keeping
    # unrelated summaries outside this fixture's scope.
    for name in ("compute_ctd_monthly_trends", "compute_diversity_indices", "compute_bay_comparison", "compute_taxa_cooccurrence"):
        monkeypatch.setattr(analysis, name, lambda: pd.DataFrame())
    result = analysis.run_all()
    document = result["documents"][0]
    assert document["derived_artifact"]["method_version"] == "taxa-env-full-abundance-v2"
    assert derived.document_eligibility(document, expected_inputs=derived.current_method_inputs("taxa_env_correlation")).status == "review_required"
    assert derived.file_eligibility(old).status == "review_required"
    retained = list((config.ANALYSIS_DIR / "derived_history").glob("*/taxa_env_correlations.parquet"))
    assert len(retained) == 1 and retained[0].read_bytes() == old_bytes
    approved = reviewed(document)
    assert derived.document_eligibility(approved, expected_inputs=derived.current_method_inputs("taxa_env_correlation")).eligible


def test_api_payload_is_bound_to_frozen_bytes_and_replacement_refreshes_rows(local_roots, monkeypatch):
    from api import main as api
    path = config.ANALYSIS_DIR / "taxa_env_correlations.parquet"
    pd.DataFrame({"genus": ["old"]}).to_parquet(path)
    first = api._read_parquet_artifact(str(path))
    pd.DataFrame({"genus": ["new"]}).to_parquet(path)
    derived.write_artifact_manifest(path.parent, {path.name: ("taxa_env_correlation", operation())})
    manifest_path = path.parent / "derived_artifacts.json"
    manifest = json.loads(manifest_path.read_text())
    receipt = manifest["artifacts"][path.name]
    receipt.update(eligibility="eligible", review=decision(receipt["generation_sha256"]))
    manifest_path.write_text(json.dumps(manifest))
    second = api._read_parquet_artifact(str(path))
    assert first.iloc[0]["genus"] == "old" and second.iloc[0]["genus"] == "new"
    assert derived.file_eligibility(path, output_sha256=first.attrs["artifact_sha256"]).status == "hash_mismatch"
    assert derived.file_eligibility(path, output_sha256=second.attrs["artifact_sha256"]).eligible
    # Path replacement during parsing cannot label different rows eligible.
    original_reader = pd.read_parquet
    def replacing_reader(raw, **kwargs):
        pd.DataFrame({"genus": ["raced"]}).to_parquet(path)
        return original_reader(raw, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", replacing_reader)
    frozen = api._read_parquet_artifact(str(path))
    assert frozen.iloc[0]["genus"] == "new"
    assert frozen.attrs["artifact_sha256"] == second.attrs["artifact_sha256"]


def test_api_sst_summary_does_not_count_unavailable_casts_as_pairs(local_roots, monkeypatch):
    from api import main as api
    frames = {
        "ctd_monthly_trends": pd.DataFrame(),
        "taxa_env_correlations": pd.DataFrame(columns=["significant", "p_value"]),
        "diversity_indices": pd.DataFrame(columns=["source", "year_month", "sample_id"]),
        "taxa_cooccurrence": pd.DataFrame(), "gap_interpolation": pd.DataFrame(columns=["date"]),
        "diversity_prediction": pd.DataFrame(columns=["sample_id"]),
        "corroboration": pd.DataFrame(columns=["reliability_tier", "sample_id"]),
        "sst_ctd_validation": pd.DataFrame({"ctd_date": ["2024-01-01"] * 3,
            "check_status": ["pass", "fail", "unavailable"], "agrees": [True, False, None],
            "abs_delta_t": [0.0, 8.0, None], "reliability_score": [1.0, 0.0, None]}),
    }
    monkeypatch.setattr(api, "_analysis_df", lambda name: frames[name])
    summary = api.analysis_state(cooccurrence_pairs=30, table_limit=500).reliability["sst_ctd"]["summary"]
    assert summary == {"paired": 2, "unavailable": 1, "agree": 1, "agreement_rate": 0.5,
                       "mean_abs_delta_t": 4.0, "mean_score": 0.5}


def test_sample_api_refreshes_historical_rows_and_binds_their_generation(local_roots, monkeypatch):
    from api import main as api
    inputs = {"fixture://sample-api": "a" * 64}
    monkeypatch.setattr(derived, "current_method_inputs", lambda method: inputs)
    monkeypatch.setattr(api, "_read_explore_dataset", lambda name: pd.DataFrame())
    monkeypatch.setattr(api, "_read_jsonl", lambda path: [])
    artifacts = {}
    for filename, method in (("corroboration.parquet", "corroboration"), ("sst_ctd_validation.parquet", "sst_ctd_validation")):
        path = config.RELIABILITY_DIR / filename
        pd.DataFrame({"sample_id": ["fixture"], "generation_label": ["old"], "reliability_tier": ["verified"]}).to_parquet(path)
        api._read_parquet_artifact(str(path))  # Warm the old path as a caller would.
        pd.DataFrame({"sample_id": ["fixture"], "generation_label": ["new"], "reliability_tier": ["standalone"]}).to_parquet(path)
        artifacts[filename] = (method, {"status": "computed", "method_version": derived.CURRENT_METHODS[method], "inputs": inputs, "parameters": {}})
    manifest = derived.write_artifact_manifest(config.RELIABILITY_DIR, artifacts)
    for receipt in manifest["artifacts"].values():
        receipt.update(eligibility="eligible", review=decision(receipt["generation_sha256"]))
    (config.RELIABILITY_DIR / "derived_artifacts.json").write_text(json.dumps(manifest))
    rows = api.explore_sample("fixture").reliability
    assert len(rows) == 2
    assert all(row["generation_label"] == "new" and row["reliability_tier"] == "standalone" for row in rows)
    assert all(row["derived_eligibility"]["eligible"] and row["derived_eligibility"]["scientific_approval"] is False for row in rows)


def test_analysis_api_inspects_unavailable_artifacts_without_result_columns(local_roots):
    from api import main as api
    from fastapi.testclient import TestClient
    artifacts = api._analysis_artifacts()
    for path in artifacts.values():
        pd.DataFrame().to_parquet(path)
    for directory in (config.ANALYSIS_DIR, config.RELIABILITY_DIR):
        entries = {
            path.name: (derived.FILE_METHODS[path.name], {
                "status": "unavailable",
                "method_version": derived.CURRENT_METHODS.get(derived.FILE_METHODS[path.name], "legacy-date-only-gap-v1"),
                "inputs": {}, "parameters": {}, "reason": "Synthetic source input is unavailable.",
            })
            for path in artifacts.values() if path.parent == directory and path.name in derived.FILE_METHODS
        }
        derived.write_artifact_manifest(directory, entries)
    response = TestClient(api.app).get("/analysis")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reliability"]["sst_ctd"]["summary"] == {
        "paired": 0, "unavailable": 0, "agree": 0, "agreement_rate": None,
        "mean_abs_delta_t": None, "mean_score": None,
    }
    for key in ("sst_ctd", "diversity_prediction", "corroboration", "gap"):
        assert payload["reliability"][key]["rows"] == []
    assert payload["reliability"]["diversity_prediction"]["summary"]["mean_abs_deviation_sigma"] is None
    assert payload["reliability"]["corroboration"]["mean_score"] is None
    for key in ("sst_ctd_validation", "diversity_prediction", "corroboration", "taxa_env_correlations"):
        decision = payload["catalog"][key]["derived_eligibility"]
        assert not decision["eligible"] and decision["status"] == "unavailable"
        assert not decision["scientific_approval"]


def test_blocked_legacy_correlation_remains_inspectable_in_analysis_api(local_roots):
    from api import main as api
    from fastapi.testclient import TestClient
    from preprocessing.reliability_ensurance import predict_diversity_from_env
    for path in api._analysis_artifacts().values():
        pd.DataFrame().to_parquet(path)
    ids = [f"fixture-{index}" for index in range(4)]
    pd.DataFrame({"sample_id": ids, "has_ctd": True, "has_kraken": True,
                  "mean_temperature": [10., 12., 14., 16.]}).to_parquet(
        config.SERVING_DIR / "sample_multisource_context.parquet")
    pd.DataFrame({"sample_id": ids, "source": "kraken", "shannon_h": [2., 3., 4., 5.]}).to_parquet(
        config.ANALYSIS_DIR / "diversity_indices.parquet")
    pd.DataFrame({"genus": ["Synthetic"], "significant": [True], "p_value": [.01],
                  "env_variable": ["mean_temperature"], "spearman_rho": [.7]}).to_parquet(
        config.ANALYSIS_DIR / "taxa_env_correlations.parquet")
    prediction = predict_diversity_from_env()
    assert prediction.empty and not len(prediction.columns)
    assert prediction.attrs["operation"]["status"] == "unavailable"
    path = config.RELIABILITY_DIR / "diversity_prediction.parquet"
    prediction.to_parquet(path)
    derived.write_artifact_manifest(path.parent, {
        path.name: ("diversity_prediction", prediction.attrs["operation"]),
    })
    response = TestClient(api.app).get("/analysis")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reliability"]["diversity_prediction"]["rows"] == []
    assert payload["reliability"]["diversity_prediction"]["summary"]["mean_abs_deviation_sigma"] is None
    assert payload["catalog"]["diversity_prediction"]["derived_eligibility"]["status"] == "unavailable"
    assert not payload["catalog"]["diversity_prediction"]["derived_eligibility"]["eligible"]
    assert payload["catalog"]["taxa_env_correlations"]["derived_eligibility"]["status"] == "legacy_unversioned"
