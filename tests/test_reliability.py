"""Tests for preprocessing/reliability_ensurance.py — cross-source validation logic."""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

import config
from preprocessing.reliability_ensurance import (
    RELIABILITY_METHOD_VERSION, SST_METHOD_VERSION, build_reliability_documents,
    corroborate_cross_source, predict_diversity_from_env, validate_sst_ctd_surface_temp, run_all,
)


# ---------------------------------------------------------------------------
# SST ↔ CTD agreement score logic
# ---------------------------------------------------------------------------
class TestSstCtdAgreementLogic:
    """Test the SST-CTD agreement scoring formula directly."""

    def test_perfect_agreement(self):
        """Delta=0 → agrees=True, score=1.0."""
        threshold = 2.0
        delta_t = 0.0
        abs_delta = abs(delta_t)
        agrees = abs_delta <= threshold
        score = round(max(0.0, min(1.0, 1.0 - abs_delta / (threshold * 2))), 4)

        assert agrees is True
        assert score == 1.0

    def test_within_threshold(self):
        """Delta=1.5°C (within 2.0 threshold) → agrees=True, score>0."""
        threshold = 2.0
        delta_t = 1.5
        abs_delta = abs(delta_t)
        agrees = abs_delta <= threshold
        score = round(max(0.0, min(1.0, 1.0 - abs_delta / (threshold * 2))), 4)

        assert agrees is True
        assert 0.0 < score < 1.0

    def test_exact_threshold(self):
        """Delta exactly at threshold → agrees=True."""
        threshold = 2.0
        delta_t = 2.0
        abs_delta = abs(delta_t)
        agrees = abs_delta <= threshold

        assert agrees is True

    def test_exceeds_threshold(self):
        """Delta=5.0°C → agrees=False, score=0."""
        threshold = 2.0
        delta_t = 5.0
        abs_delta = abs(delta_t)
        agrees = abs_delta <= threshold
        score = round(max(0.0, min(1.0, 1.0 - abs_delta / (threshold * 2))), 4)

        assert agrees is False
        assert score == 0.0

    def test_negative_delta(self):
        """Negative delta (CTD < SST) also works correctly."""
        threshold = 2.0
        delta_t = -1.0
        abs_delta = abs(delta_t)
        agrees = abs_delta <= threshold

        assert agrees is True
        assert abs_delta == 1.0


# ---------------------------------------------------------------------------
# Corroboration tier logic
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Diversity anomaly detection logic
# ---------------------------------------------------------------------------
class TestDiversityAnomalyLogic:
    """Test the anomaly detection threshold."""

    def test_normal_within_sigma(self):
        """Deviation of 1.5σ (below 2.0 threshold) → not anomaly."""
        sigma = 2.0
        deviation_sigma = 1.5
        assert abs(deviation_sigma) <= sigma

    def test_anomaly_exceeds_sigma(self):
        """Deviation of 2.5σ (above 2.0 threshold) → anomaly."""
        sigma = 2.0
        deviation_sigma = -2.5
        assert abs(deviation_sigma) > sigma

    def test_exact_sigma_boundary(self):
        """Deviation at exactly 2.0σ → not anomaly (>σ, not >=σ)."""
        sigma = 2.0
        deviation_sigma = 2.0
        # The code uses > not >=
        is_anomaly = abs(deviation_sigma) > sigma
        assert is_anomaly is False


# ---------------------------------------------------------------------------
# build_reliability_documents
# ---------------------------------------------------------------------------
class TestBuildReliabilityDocuments:
    """Test reliability document generation from DataFrames."""

    def test_all_empty_inputs(self):
        """Empty DataFrames produce no documents."""
        docs = build_reliability_documents(
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        )
        assert docs == []

    def test_sst_ctd_document(self):
        """SST-CTD validation data produces a document."""
        sst_ctd = pd.DataFrame({
            "sample_id": ["2024-04-O-s1", "2024-05-O-s1"],
            "ctd_date": pd.to_datetime(["2024-04-15", "2024-05-10"]),
            "bay": ["O", "O"],
            "ctd_surface_t": [10.5, 14.2],
            "sst_daily_mean": [10.0, 13.8],
            "delta_t": [0.5, 0.4],
            "abs_delta_t": [0.5, 0.4],
            "agrees": [True, True],
            "reliability_score": [0.875, 0.9],
        })

        docs = build_reliability_documents(
            sst_ctd, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        )

        assert len(docs) == 1
        assert docs[0]["id"] == "reliability_sst_ctd_validation"
        assert "100%" in docs[0]["text"]
        assert "Onagawa Bay" in docs[0]["text"]

    def test_diversity_prediction_document_with_anomaly(self):
        """Diversity prediction with anomaly produces a document with details."""
        div_pred = pd.DataFrame({
            "sample_id": ["2024-04-O-s1", "2024-07-O-s1"],
            "bay": ["O", "O"],
            "predicted_shannon": [3.9, 3.5],
            "actual_shannon": [3.8, 1.6],
            "deviation": [-0.1, -1.9],
            "deviation_sigma": [-0.1, -2.3],
            "is_anomaly": [False, True],
            "n_supporting_vars": [3, 3],
            "supporting_env_summary": ["temp=10.5", "temp=22.1"],
        })

        docs = build_reliability_documents(
            pd.DataFrame(), pd.DataFrame(), div_pred, pd.DataFrame()
        )

        assert len(docs) == 1
        assert docs[0]["id"] == "reliability_diversity_prediction"
        assert "1" in docs[0]["text"]  # 1 anomaly
        assert "2024-07-O-s1" in docs[0]["text"]

    def test_corroboration_document(self):
        """Corroboration summary produces a document with tier counts."""
        corrob = pd.DataFrame({
            "event_id": ["sample_2024-04-O-s1", "sample_2024-05-O-s1", "sample_2024-06-O-s4"],
            "sample_id": ["2024-04-O-s1", "2024-05-O-s1", "2024-06-O-s4"],
            "source_type": ["ctd,metagenome", "ctd,metagenome", "ctd"],
            "reliability_tier": ["verified", "verified", "standalone"],
            "corroboration_sources": ["multi_modal,diversity", "multi_modal", ""],
            "reliability_score": [0.9, 0.8, 0.3],
            "n_checks": [2, 1, 0],
            "detail": ["Multi-modal", "Multi-modal", "No cross-validation"],
        })

        docs = build_reliability_documents(
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), corrob
        )

        assert len(docs) == 1
        assert docs[0]["id"] == "reliability_corroboration_summary"
        assert "Verified" in docs[0]["text"]

    def test_all_inputs_produce_four_documents(self):
        """All non-empty inputs produce 4 documents."""
        sst_ctd = pd.DataFrame({
            "sample_id": ["s1"], "ctd_date": pd.to_datetime(["2024-04-15"]),
            "bay": ["O"], "ctd_surface_t": [10.5], "sst_daily_mean": [10.0],
            "delta_t": [0.5], "abs_delta_t": [0.5], "agrees": [True],
            "reliability_score": [0.875],
        })
        gap = pd.DataFrame({
            "date": ["2024-04-16"], "sst_daily_mean": [10.2],
            "interpolated_surface_t": [10.7], "confidence": [0.9],
            "method": ["sst_offset_correction"], "nearest_ctd_days": [1.0],
            "in_ctd_gap": [True],
        })
        div = pd.DataFrame({
            "sample_id": ["s1"], "bay": ["O"],
            "predicted_shannon": [3.9], "actual_shannon": [3.8],
            "deviation": [-0.1], "deviation_sigma": [-0.1],
            "is_anomaly": [False], "n_supporting_vars": [3],
            "supporting_env_summary": ["temp=10.5"],
        })
        corrob = pd.DataFrame({
            "event_id": ["sample_s1"], "sample_id": ["s1"],
            "source_type": ["ctd"], "reliability_tier": ["verified"],
            "corroboration_sources": ["sst"], "reliability_score": [0.9],
            "n_checks": [2], "detail": ["SST agrees"],
        })

        docs = build_reliability_documents(sst_ctd, gap, div, corrob)
        assert len(docs) == 4
        ids = {d["id"] for d in docs}
        assert "reliability_sst_ctd_validation" in ids
        assert "reliability_gap_interpolation" in ids
        assert "reliability_diversity_prediction" in ids
        assert "reliability_corroboration_summary" in ids


@pytest.fixture
def reliability_inputs(tmp_path, monkeypatch):
    for setting, name in (("NORMALIZED_DIR", "normalized"), ("SERVING_DIR", "serving"), ("ANALYSIS_DIR", "analysis"), ("RELIABILITY_DIR", "reliability")):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setattr(config, setting, directory)
    monkeypatch.setattr(config, "SST_CTD_AGREEMENT_THRESHOLD", 2.0)
    monkeypatch.setattr(config, "DIVERSITY_ANOMALY_SIGMA", 2.0)
    context = pd.DataFrame([{"sample_id": "2024-04-O-s1", "has_ctd": True, "has_kraken": True, "has_metaeuk": False}])
    context.to_parquet(config.SERVING_DIR / "sample_multisource_context.parquet")
    return context


def write_temperature_inputs(*, lat=38.5, lon=141.5, delta=0.0, support=True, kind="reviewed_regional_context_rectangle"):
    ctd = pd.DataFrame([{"sample_id": "2024-04-O-s1", "ctd_date": "2024-04-15", "surface_temperature": 20.0 + delta, "lat": lat, "lon": lon}])
    satellite = {"date_jst": "2024-04-15", "mean_sst": 20.0, "min_sst": 19.0, "max_sst": 21.0}
    if support:
        satellite["spatial_support"] = {"kind": kind, "west": 141.0, "east": 142.0, "south": 38.0, "north": 39.0,
                                         "reviewed": True, "reference": "fixture://reviewed-regional-support"}
    ctd.to_parquet(config.NORMALIZED_DIR / "ctd_summary.parquet")
    pd.DataFrame([satellite]).to_parquet(config.NORMALIZED_DIR / "sst_daily_summary.parquet")


def diversity_check(sigma=0.0, **changes):
    values = {"sample_id": "2024-04-O-s1", "deviation_sigma": sigma, "is_anomaly": abs(sigma) > 2.0,
              "check_status": "fail" if abs(sigma) > 2.0 else "pass", "n_supporting_vars": 3,
              "method_version": RELIABILITY_METHOD_VERSION}
    values.update(changes)
    return pd.DataFrame([values])


def test_failed_audit_checks_never_manufacture_verified(reliability_inputs):
    disagreement = pd.DataFrame([{"sample_id": "2024-04-O-s1", "agrees": False, "delta_t": 8.0, "reliability_score": 0.0}])
    anomaly = pd.DataFrame([{"sample_id": "2024-04-O-s1", "is_anomaly": True, "deviation_sigma": 5.0}])
    row = corroborate_cross_source(disagreement, anomaly).iloc[0]
    assert row["reliability_tier"] == "standalone"
    assert row["n_checks"] == row["n_passed_checks"] == 0
    assert row["n_failed_checks"] == row["n_attempted_checks"] == 2
    assert row["has_conflicts"]
    checks = json.loads(row["checks"])
    assert [check["status"] for check in checks] == ["fail", "fail"]
    assert all(check["provenance"]["result_sha256"] for check in checks)
    assert "multi_modal" not in row["corroboration_sources"]
    assert not row["independent_researcher_approval"]


def test_modalities_alone_are_inventory_not_passed_checks(reliability_inputs):
    result = corroborate_cross_source(pd.DataFrame(), pd.DataFrame())
    row = result.iloc[0]
    assert row["source_type"] == "ctd,metagenome"
    assert row["n_checks"] == row["n_attempted_checks"] == 0
    assert row["n_unavailable_checks"] == 2
    assert row["reliability_tier"] == "standalone" and pd.isna(row["reliability_score"])
    assert result.attrs["operation"]["status"] == "unavailable"


@pytest.mark.parametrize("lat,lon,support,reason", [
    (40.9, 141.4, True, "outside"), (38.5, 143.0, True, "outside"),
    (38.5, 141.5, False, "unavailable"), (None, 141.5, True, "unavailable"),
    (91.0, 141.5, True, "invalid"),
])
def test_unsupported_spatial_pairing_is_unavailable(reliability_inputs, lat, lon, support, reason):
    write_temperature_inputs(lat=lat, lon=lon, support=support)
    result = validate_sst_ctd_surface_temp()
    row = result.iloc[0]
    assert row["check_status"] == "unavailable" and pd.isna(row["agrees"])
    assert pd.isna(row["reliability_score"]) and pd.isna(row["sst_daily_mean"])
    assert reason in row["check_reason"]
    assert result.attrs["operation"]["status"] == "unavailable"
    assert corroborate_cross_source(result, pd.DataFrame()).iloc[0]["n_checks"] == 0


@pytest.mark.parametrize("delta,expected", [(0.0, "pass"), (2.0, "pass"), (2.0001, "fail"), (8.0, "fail")])
def test_reviewed_spatial_comparison_preserves_threshold(reliability_inputs, delta, expected):
    write_temperature_inputs(delta=delta)
    result = validate_sst_ctd_surface_temp()
    row = result.iloc[0]
    assert row["check_status"] == expected
    assert row["applicability"] == "regional_context_only"
    assert row["comparison_kind"] == "regional_temperature_consistency"
    receipt = result.attrs["operation"]
    assert receipt["status"] == "computed" and receipt["method_version"] == SST_METHOD_VERSION
    assert receipt["parameters"]["agreement_threshold_celsius"] == 2.0
    for name, digest in receipt["inputs"].items():
        from pathlib import Path
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
    assert not row["independent_researcher_approval"]


def test_in_sample_model_and_regional_context_do_not_count_as_independent(reliability_inputs):
    write_temperature_inputs()
    regional = validate_sst_ctd_surface_temp()
    row = corroborate_cross_source(regional, diversity_check()).iloc[0]
    assert row["n_passed_checks"] == 2 and row["n_checks"] == 0
    assert row["reliability_tier"] == "standalone"
    assert all(not check["independent"] for check in json.loads(row["checks"]))
    write_temperature_inputs(kind="reviewed_cell_footprint")
    cell = validate_sst_ctd_surface_temp()
    row = corroborate_cross_source(cell, diversity_check()).iloc[0]
    assert row["n_passed_checks"] == 2 and row["n_checks"] == 1
    assert row["reliability_tier"] == "supported"


def test_stale_positive_result_cannot_establish_current_check(reliability_inputs):
    old = pd.DataFrame([{"sample_id": "2024-04-O-s1", "agrees": True, "delta_t": 0.0, "reliability_score": 1.0}])
    row = corroborate_cross_source(old, pd.DataFrame()).iloc[0]
    assert row["n_checks"] == 0 and row["n_unavailable_checks"] == 2


@pytest.mark.parametrize("sigma,expected", [(2.0, "pass"), (2.0001, "fail"), (5.0, "fail")])
def test_diversity_sigma_and_independence_are_explicit(reliability_inputs, sigma, expected):
    row = corroborate_cross_source(pd.DataFrame(), diversity_check(sigma, is_anomaly=False)).iloc[0]
    check = next(check for check in json.loads(row["checks"]) if check["check_id"] == "diversity_prediction")
    assert check["status"] == expected and not check["independent"]
    assert row["reliability_tier"] != "verified"


def test_duplicate_daily_support_and_missing_measurements_do_not_pass(reliability_inputs):
    write_temperature_inputs()
    path = config.NORMALIZED_DIR / "sst_daily_summary.parquet"
    sst = pd.read_parquet(path)
    pd.concat([sst, sst]).to_parquet(path)
    assert validate_sst_ctd_surface_temp().iloc[0]["check_status"] == "unavailable"
    write_temperature_inputs(delta=float("nan"))
    assert validate_sst_ctd_surface_temp().iloc[0]["check_status"] == "unavailable"


def test_unavailable_spatial_rows_are_not_document_disagreements(reliability_inputs):
    write_temperature_inputs(lat=40.9)
    unavailable = validate_sst_ctd_surface_temp()
    docs = build_reliability_documents(unavailable, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert "Unavailable checks: 1" in docs[0]["text"]
    assert "no applicable comparison" in docs[0]["text"]
    assert "Notable disagreements" not in docs[0]["text"]


def write_prediction_inputs():
    from preprocessing.derived_artifacts import current_method_inputs, write_artifact_manifest
    ids = [f"sample-{i}" for i in range(4)]
    pd.DataFrame({"sample_id": ids, "source": ["kraken"] * 4, "shannon_h": [2., 3., 4., 5.]}).to_parquet(config.ANALYSIS_DIR / "diversity_indices.parquet")
    pd.DataFrame({"significant": [True], "env_variable": ["mean_temperature"], "spearman_rho": [.7]}).to_parquet(config.ANALYSIS_DIR / "taxa_env_correlations.parquet")
    pd.DataFrame({"sample_id": ids, "has_ctd": [True] * 4, "has_kraken": [True] * 4, "mean_temperature": [10., 12., 14., 16.]}).to_parquet(config.SERVING_DIR / "sample_multisource_context.parquet")
    pd.DataFrame({"sample_id": ids, "genus": ["fixture-genus"] * 4, "abundance_value": [.1] * 4}).to_parquet(config.NORMALIZED_DIR / "kraken_genus_abundance.parquet")
    operation = {"status": "computed", "method_version": "taxa-env-full-abundance-v2",
                 "inputs": current_method_inputs("taxa_env_correlation"), "parameters": {"fixture": "synthetic only"}}
    write_artifact_manifest(config.ANALYSIS_DIR, {"taxa_env_correlations.parquet": ("taxa_env_correlation", operation)})


def test_diversity_prediction_retains_inputs_and_in_sample_qualification(reliability_inputs):
    write_prediction_inputs()
    result = predict_diversity_from_env()
    assert len(result) == 4
    assert not result["independent"].any() and not result["independent_researcher_approval"].any()
    assert set(result["applicability"]) == {"in_sample_model_consistency"}
    assert len(result.attrs["operation"]["inputs"]) == 5
    assert result.attrs["operation"]["status"] == "computed"
    assert result.attrs["operation"]["parameters"]["correlation_status"] == "computed_candidate"
    docs = build_reliability_documents(pd.DataFrame(), pd.DataFrame(), result, pd.DataFrame())
    assert docs[0]["derived_artifact"]["eligibility"] == "review_required"
    assert not docs[0]["derived_artifact"]["scientific_approval"]


def test_source_changes_invalidate_a_previously_reviewed_prediction(reliability_inputs):
    from preprocessing.derived_artifacts import document_eligibility, review_document, current_method_inputs
    write_prediction_inputs()
    result = predict_diversity_from_env()
    document = build_reliability_documents(pd.DataFrame(), pd.DataFrame(), result, pd.DataFrame())[0]
    receipt = document["derived_artifact"]
    reviewed = review_document(document, {
        "reviewer": "synthetic reviewer", "rationale": "Synthetic eligibility test only",
        "references": ["fixture://prediction-review"], "evidence_sha256": receipt["generation_sha256"],
    })
    assert document_eligibility(reviewed, expected_inputs=current_method_inputs("diversity_prediction")).eligible
    abundance = config.NORMALIZED_DIR / "kraken_genus_abundance.parquet"
    changed = pd.read_parquet(abundance)
    changed["abundance_value"] = .9
    changed.to_parquet(abundance)
    decision = document_eligibility(reviewed, expected_inputs=current_method_inputs("diversity_prediction"))
    assert not decision.eligible and decision.status == "stale_inputs"
    assert not decision.scientific_approval


@pytest.mark.parametrize("mutation", ["missing_receipt", "legacy_method", "invalidated", "unavailable", "wrong_method", "output_changed", "source_changed"])
def test_prediction_cannot_launder_unverifiable_correlation(reliability_inputs, mutation):
    from preprocessing.derived_artifacts import make_receipt, current_method_inputs, file_hash
    write_prediction_inputs()
    manifest_path = config.ANALYSIS_DIR / "derived_artifacts.json"
    corr_path = config.ANALYSIS_DIR / "taxa_env_correlations.parquet"
    if mutation == "missing_receipt":
        manifest_path.unlink()
    elif mutation == "output_changed":
        pd.DataFrame({"significant": [True], "env_variable": ["mean_temperature"], "spearman_rho": [-.7]}).to_parquet(corr_path)
    elif mutation == "source_changed":
        pd.DataFrame({"sample_id": ["altered"], "genus": ["fixture-genus"], "abundance_value": [.9]}).to_parquet(config.NORMALIZED_DIR / "kraken_genus_abundance.parquet")
    else:
        method = "corroboration" if mutation == "wrong_method" else "taxa_env_correlation"
        operation = {"status": "unavailable" if mutation == "unavailable" else "computed",
                     "method_version": "legacy-top-ten-v1" if mutation == "legacy_method" else "taxa-env-full-abundance-v2",
                     "inputs": current_method_inputs("taxa_env_correlation"), "parameters": {}}
        receipt = make_receipt(method, file_hash(corr_path), operation)
        if mutation == "invalidated":
            receipt["eligibility"] = "invalidated"
        manifest_path.write_text(json.dumps({"schema_version": 1, "artifacts": {corr_path.name: receipt}}))
    result = predict_diversity_from_env()
    assert result.empty and result.attrs["operation"]["status"] == "unavailable"
    assert "correlation is unavailable" in result.attrs["operation"]["reason"]


def test_sst_computation_hashes_the_bytes_it_actually_consumes(reliability_inputs, monkeypatch):
    write_temperature_inputs()
    path = config.NORMALIZED_DIR / "ctd_summary.parquet"
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    original_reader = pd.read_parquet
    altered = False
    def read_and_replace(source, *args, **kwargs):
        nonlocal altered
        frame = original_reader(source, *args, **kwargs)
        if not altered:
            altered = True
            changed = frame.copy()
            changed["surface_temperature"] = 28.0
            changed.to_parquet(path)
        return frame
    monkeypatch.setattr(pd, "read_parquet", read_and_replace)
    result = validate_sst_ctd_surface_temp()
    assert result.iloc[0]["delta_t"] == 0.0
    assert result.attrs["operation"]["inputs"][str(path.resolve())] == original_hash
    assert hashlib.sha256(path.read_bytes()).hexdigest() != original_hash


def test_corroboration_hashes_frozen_source_inventory(reliability_inputs, monkeypatch):
    path = config.SERVING_DIR / "sample_multisource_context.parquet"
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    original_reader = pd.read_parquet
    def read_and_replace(source, *args, **kwargs):
        frame = original_reader(source, *args, **kwargs)
        changed = frame.copy()
        changed["has_ctd"] = changed["has_kraken"] = False
        changed.to_parquet(path)
        return frame
    monkeypatch.setattr(pd, "read_parquet", read_and_replace)
    result = corroborate_cross_source(pd.DataFrame(), pd.DataFrame())
    assert result.iloc[0]["source_type"] == "ctd,metagenome"
    assert result.attrs["operation"]["inputs"][str(path.resolve())] == original_hash
    assert hashlib.sha256(path.read_bytes()).hexdigest() != original_hash


def test_prediction_uses_frozen_correlation_and_binds_its_manifest(reliability_inputs, monkeypatch):
    write_prediction_inputs()
    corr_path = config.ANALYSIS_DIR / "taxa_env_correlations.parquet"
    manifest_path = config.ANALYSIS_DIR / "derived_artifacts.json"
    old_hash = hashlib.sha256(corr_path.read_bytes()).hexdigest()
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    original_reader = pd.read_parquet
    count = 0
    def read_and_replace(source, *args, **kwargs):
        nonlocal count
        frame = original_reader(source, *args, **kwargs)
        count += 1
        if count == 2:
            changed = frame.copy()
            changed["spearman_rho"] = -.7
            changed.to_parquet(corr_path)
        return frame
    monkeypatch.setattr(pd, "read_parquet", read_and_replace)
    result = predict_diversity_from_env()
    assert not result.empty
    assert result.iloc[-1]["predicted_shannon"] > result.iloc[0]["predicted_shannon"]
    inputs = result.attrs["operation"]["inputs"]
    assert inputs[str(corr_path.resolve())] == old_hash
    assert inputs[str(manifest_path.resolve())] == manifest_hash
    assert hashlib.sha256(corr_path.read_bytes()).hexdigest() != old_hash


def test_repeated_local_regeneration_has_distinct_generation_ids(reliability_inputs):
    write_prediction_inputs()
    write_temperature_inputs()
    first = run_all()
    second = run_all()
    for method in ("sst_ctd_validation", "diversity_prediction", "corroboration"):
        first_id = first[method].attrs["operation"]["parameters"]["regeneration_id"]
        second_id = second[method].attrs["operation"]["parameters"]["regeneration_id"]
        assert first_id != second_id and len(first_id) == len(second_id) == 32
    gap = pd.DataFrame({"date": ["2024-04-16"], "sst_daily_mean": [20.0], "interpolated_surface_t": [20.5],
                        "confidence": [.9], "method": ["sst_offset_correction"], "nearest_ctd_days": [1.0], "in_ctd_gap": [True]})
    gap_doc = build_reliability_documents(pd.DataFrame(), gap, pd.DataFrame(), pd.DataFrame())[0]
    assert "unvalidated" in gap_doc["title"] and "not validated sample-point" in gap_doc["text"]
    assert "not validated confidence" in gap_doc["text"]
