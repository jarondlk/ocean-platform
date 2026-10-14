"""
Reliability Ensurance layer – cross-source validation and corroboration.

Uses overlapping data between CTD, metagenome, and SST sources to
predict, interpolate, and validate observations. Produces reliability
scores and corroboration documents injected into RAG prompts.

Outputs are saved to data/reliability/ as parquet + JSONL text summaries.
"""
from __future__ import annotations

import json
import logging
import hashlib
import math
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import numpy as np
import pandas as pd

import config
from preprocessing.derived_artifacts import (stamp_document, retain_artifact_history, write_artifact_manifest,
                                             input_receipts, receipt_eligibility, current_method_inputs)

logger = logging.getLogger(__name__)

RELIABILITY_METHOD_VERSION = "reliability-checks-v2"
SST_METHOD_VERSION = "sst-ctd-spatial-v2"


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _flag(value):
    """Missing flags and strings such as 'False' never establish a passed check."""
    return isinstance(value, (bool, np.bool_)) and bool(value)


def _input_hashes(paths):
    return {str(Path(path).resolve()): hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in paths if Path(path).is_file()}


def _frame_hash(frame):
    return hashlib.sha256(frame.to_json(orient="records", date_format="iso").encode()).hexdigest()


def _frozen_parquet_inputs(paths):
    """Parse and hash the identical retained bytes, never a second mutable read."""
    frames, inputs = [], {}
    for path in paths:
        path = Path(path)
        payload = path.read_bytes()
        inputs[str(path.resolve())] = hashlib.sha256(payload).hexdigest()
        frames.append(pd.read_parquet(BytesIO(payload)))
    return frames, inputs


def _operation(frame, method_version, paths, parameters, *, reason=None, inputs=None):
    if "check_status" in frame:
        computed = frame["check_status"].isin({"pass", "fail"}).any()
    elif "n_attempted_checks" in frame:
        computed = frame["n_attempted_checks"].gt(0).any()
    else:
        computed = not frame.empty
    frame.attrs["operation"] = {
        "status": "computed" if computed else "unavailable",
        "reason": reason or ("Algorithmic checks computed; independent scientific approval is not established."
                             if computed else "No scientifically applicable check is available."),
        "method_version": method_version, "inputs": _input_hashes(paths) if inputs is None else inputs, "parameters": parameters,
    }
    return frame


def _spatial_applicability(ctd_row, sst_row):
    """Require retained, reviewed support; current config is not historical evidence."""
    support = sst_row.get("spatial_support")
    if isinstance(support, str):
        try:
            support = json.loads(support)
        except ValueError:
            support = None
    if not isinstance(support, dict) or not _flag(support.get("reviewed")) or not support.get("reference"):
        return "unknown", "Reviewed SST spatial support is unavailable.", support
    kind = support.get("kind")
    if kind not in {"reviewed_regional_context_rectangle", "reviewed_cell_footprint"}:
        return "unknown", "The SST spatial-support kind is unsupported.", support
    coordinates = [ctd_row.get("lat"), ctd_row.get("lon")]
    bounds = [support.get(key) for key in ("west", "east", "south", "north")]
    if not all(_finite(value) for value in [*coordinates, *bounds]):
        return "unknown", "CTD coordinates or SST spatial bounds are unavailable.", support
    lat, lon = map(float, coordinates)
    west, east, south, north = map(float, bounds)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180
            and -180 <= west < east <= 180 and -90 <= south < north <= 90):
        return "unknown", "CTD coordinates or SST spatial bounds are invalid.", support
    if not (west <= lon <= east and south <= lat <= north):
        return "not_applicable", "The CTD cast lies outside the reviewed SST support.", support
    applicability = "regional_context_only" if kind == "reviewed_regional_context_rectangle" else "eligible"
    return applicability, "Spatial support matches; regional means remain regional comparisons.", support


# ─────────────────────────────────────────────
# 1. SST ↔ CTD Surface Temperature Validation
# ─────────────────────────────────────────────
def validate_sst_ctd_surface_temp() -> pd.DataFrame:
    """Compare only date- and spatially-supported CTD/SST observations.

    Regional means establish a labelled regional consistency check, not a
    coastal/sample-point observation. Historical config defaults cannot supply
    missing spatial evidence. Unavailable checks retain their CTD row and do
    not receive an agreement boolean or score.
    """
    ctd_path = config.NORMALIZED_DIR / "ctd_summary.parquet"
    sst_path = config.NORMALIZED_DIR / "sst_daily_summary.parquet"
    if not ctd_path.exists() or not sst_path.exists():
        logger.warning("Missing CTD or SST data for SST-CTD validation")
        return _operation(pd.DataFrame(), SST_METHOD_VERSION, (ctd_path, sst_path),
                          {"agreement_threshold_celsius": config.SST_CTD_AGREEMENT_THRESHOLD},
                          reason="CTD or SST normalized input is missing.")
    (ctd, sst), provenance = _frozen_parquet_inputs((ctd_path, sst_path))
    if ctd.empty or sst.empty:
        return _operation(pd.DataFrame(), SST_METHOD_VERSION, (ctd_path, sst_path),
                          {"agreement_threshold_celsius": config.SST_CTD_AGREEMENT_THRESHOLD},
                          reason="CTD or SST normalized input is empty.", inputs=provenance)
    ctd = ctd.copy()
    ctd["ctd_date"] = pd.to_datetime(ctd["ctd_date"], errors="coerce")
    ctd["date_str"] = ctd["ctd_date"].dt.strftime("%Y-%m-%d")
    ctd["bay"] = ctd["sample_id"].astype(str).str.extract(r"\d{4}-\d{2}-([A-Z])-")
    sst = sst.copy()
    sst["date_str"] = pd.to_datetime(sst["date_jst"], errors="coerce").dt.strftime("%Y-%m-%d")
    threshold = config.SST_CTD_AGREEMENT_THRESHOLD
    rows = []
    for _, cast in ctd.iterrows():
        row = {"sample_id": cast["sample_id"], "ctd_date": cast["ctd_date"], "bay": cast["bay"],
               "ctd_surface_t": cast.get("surface_temperature"), "sst_daily_mean": None,
               "delta_t": None, "abs_delta_t": None, "agrees": None, "reliability_score": None,
               "check_status": "unavailable", "applicability": "unknown",
               "check_reason": "No unique same-date SST observation is available.",
               "comparison_kind": "unavailable", "method_version": SST_METHOD_VERSION,
               "input_provenance": json.dumps(provenance, sort_keys=True),
               "spatial_support": None, "independent_researcher_approval": False}
        candidates = sst[sst["date_str"] == cast["date_str"]] if pd.notna(cast["date_str"]) else sst.iloc[:0]
        if len(candidates) == 1:
            satellite = candidates.iloc[0]
            applicability, reason, support = _spatial_applicability(cast, satellite)
            row.update(applicability=applicability, check_reason=reason,
                       spatial_support=json.dumps(support, sort_keys=True) if isinstance(support, dict) else None)
            if applicability in {"eligible", "regional_context_only"}:
                row["comparison_kind"] = "regional_temperature_consistency" if applicability == "regional_context_only" else "reviewed_cell_temperature_consistency"
                if _finite(cast.get("surface_temperature")) and _finite(satellite.get("mean_sst")):
                    delta = float(cast["surface_temperature"]) - float(satellite["mean_sst"])
                    agrees = abs(delta) <= threshold
                    row.update(sst_daily_mean=float(satellite["mean_sst"]), delta_t=delta,
                               abs_delta_t=abs(delta), agrees=agrees,
                               reliability_score=round(float(np.clip(1.0 - abs(delta) / (threshold * 2), 0, 1)), 4),
                               check_status="pass" if agrees else "fail",
                               check_reason="Temperature consistency is within the reviewed threshold." if agrees else "Temperature disagreement exceeds the reviewed threshold.")
                else:
                    row["check_reason"] = "A finite CTD or SST temperature is unavailable."
        rows.append(row)
    result = pd.DataFrame(rows)
    result.attrs["input_provenance"] = provenance
    result.attrs["method_version"] = SST_METHOD_VERSION
    logger.info("Spatially qualified SST-CTD checks: %s", result["check_status"].value_counts().to_dict())
    return _operation(result, SST_METHOD_VERSION, (ctd_path, sst_path),
                      {"agreement_threshold_celsius": threshold,
                       "spatial_rule": "retained_reviewed_support_contains_cast; regional_context_is_not_point_validation"},
                      inputs=provenance)


# ─────────────────────────────────────────────
# 2. Temporal Gap Interpolation via SST
# ─────────────────────────────────────────────
def interpolate_sst_for_gaps() -> pd.DataFrame:
    """
    Use continuous SST daily coverage to interpolate expected surface
    temperatures during gaps between CTD sampling dates.

    First establishes the SST↔CTD relationship from paired observations,
    then applies it to SST dates without CTD coverage to produce
    predicted CTD-equivalent surface temperatures.

    Returns DataFrame with columns:
        date, sst_daily_mean, interpolated_surface_t, confidence,
        method, nearest_ctd_days, in_ctd_gap
    """
    ctd_path = config.NORMALIZED_DIR / "ctd_summary.parquet"
    sst_path = config.NORMALIZED_DIR / "sst_daily_summary.parquet"

    if not ctd_path.exists() or not sst_path.exists():
        logger.warning("Missing data for gap interpolation")
        return pd.DataFrame()

    ctd = pd.read_parquet(ctd_path)
    sst = pd.read_parquet(sst_path)

    if ctd.empty or sst.empty:
        return pd.DataFrame()

    ctd["ctd_date"] = pd.to_datetime(ctd["ctd_date"], errors="coerce")
    ctd_dates = ctd["ctd_date"].dropna().dt.normalize().unique()
    ctd_dates = pd.DatetimeIndex(ctd_dates).sort_values()

    sst["date"] = pd.to_datetime(sst["date_jst"], errors="coerce")
    sst = sst.dropna(subset=["date", "mean_sst"]).copy()

    if len(ctd_dates) < 2:
        logger.warning("Need at least 2 CTD dates for gap interpolation")
        return pd.DataFrame()

    # Compute SST→CTD offset from paired observations
    ctd_for_offset = ctd[ctd["surface_temperature"].notna()].copy()
    ctd_for_offset["date_key"] = ctd_for_offset["ctd_date"].dt.strftime("%Y-%m-%d")
    sst["date_key"] = sst["date"].dt.strftime("%Y-%m-%d")

    paired = ctd_for_offset.merge(
        sst[["date_key", "mean_sst"]], on="date_key", how="inner"
    )

    if paired.empty:
        # No overlap — use SST directly without offset correction
        offset = 0.0
        offset_std = 1.0
        logger.info("No SST-CTD overlap for offset; using raw SST values")
    else:
        offsets = paired["surface_temperature"] - paired["mean_sst"]
        offset = float(offsets.mean())
        offset_std = float(offsets.std()) if len(offsets) > 1 else 1.0
        logger.info(
            "SST→CTD offset: %.2f ± %.2f°C (from %d paired obs)",
            offset, offset_std, len(paired),
        )

    # For each SST date, compute interpolated value and confidence
    rows = []
    for _, sr in sst.iterrows():
        d = sr["date"]
        sst_val = sr["mean_sst"]

        # Distance to nearest CTD date
        deltas = np.abs((ctd_dates - d).total_seconds()) / 86400
        nearest_days = float(deltas.min()) if len(deltas) > 0 else 999

        # Check if this date is in a CTD gap (between two CTD dates)
        in_gap = bool((d > ctd_dates.min()) and (d < ctd_dates.max()))

        # Interpolated surface T = SST + learned offset
        interp_t = sst_val + offset

        # Confidence decays with distance from nearest CTD observation
        # Full confidence near CTD dates, lower in long gaps
        confidence = float(np.clip(
            1.0 - (nearest_days / 90.0),  # 90 days → confidence 0
            0.1, 1.0,
        ))

        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "sst_daily_mean": round(sst_val, 3),
            "interpolated_surface_t": round(interp_t, 3),
            "confidence": round(confidence, 4),
            "method": "sst_offset_correction",
            "nearest_ctd_days": round(nearest_days, 1),
            "in_ctd_gap": in_gap,
        })

    result = pd.DataFrame(rows)
    n_gaps = result["in_ctd_gap"].sum()
    logger.info(
        "Gap interpolation: %d SST days processed, %d in CTD gaps, "
        "offset=%.2f°C",
        len(result), n_gaps, offset,
    )
    return result


# ─────────────────────────────────────────────
# 3. Diversity Prediction from Environment
# ─────────────────────────────────────────────
def predict_diversity_from_env() -> pd.DataFrame:
    """
    Use taxa-environment correlations and CTD conditions to predict
    expected Shannon diversity, then compare with actual values.

    Uses a simple linear model: for each significantly correlated
    genus-environment pair, predicts genus contribution direction.
    The ensemble of these predictions yields an expected diversity range.

    Returns DataFrame with columns:
        sample_id, bay, predicted_shannon, actual_shannon,
        deviation, deviation_sigma, is_anomaly,
        n_supporting_vars, supporting_env_summary
    """
    div_path = config.ANALYSIS_DIR / "diversity_indices.parquet"
    corr_path = config.ANALYSIS_DIR / "taxa_env_correlations.parquet"
    ctx_path = config.SERVING_DIR / "sample_multisource_context.parquet"

    paths = (div_path, corr_path, ctx_path)
    parameters = {"diversity_anomaly_sigma": config.DIVERSITY_ANOMALY_SIGMA,
                  "applicability": "in_sample_model_consistency; not_independent_validation"}
    if not all(p.exists() for p in paths):
        logger.warning("Missing data for diversity prediction")
        return _operation(pd.DataFrame(), RELIABILITY_METHOD_VERSION, paths, parameters)

    (diversity, correlations, ctx), frozen_inputs = _frozen_parquet_inputs(paths)
    manifest_path = config.ANALYSIS_DIR / "derived_artifacts.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        frozen_inputs[str(manifest_path.resolve())] = hashlib.sha256(manifest_bytes).hexdigest()
        raw_receipt = manifest["artifacts"][corr_path.name]
        if manifest.get("schema_version") != 1 or raw_receipt.get("method_id") != "taxa_env_correlation":
            raise ValueError("Unknown correlation receipt method/schema")
        expected_inputs = current_method_inputs("taxa_env_correlation")
        if str((config.NORMALIZED_DIR / "kraken_genus_abundance.parquet").resolve()) not in expected_inputs:
            raise ValueError("Full normalized abundance provenance is unavailable")
        expected_inputs[str(ctx_path.resolve())] = frozen_inputs[str(ctx_path.resolve())]
        decision = receipt_eligibility(raw_receipt, frozen_inputs[str(corr_path.resolve())],
                                       expected_inputs=expected_inputs, require_review=False)
        parameters["correlation_status"] = decision.status
        if decision.status != "computed_candidate":
            raise ValueError(f"Correlation generation is {decision.status}")
        # Retain transitive full-abundance dependencies so a later source change
        # invalidates this candidate even if its correlation file is unchanged.
        frozen_inputs.update(raw_receipt["inputs"])
        parameters["correlation_generation_sha256"] = decision.generation_sha256
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return _operation(pd.DataFrame(), RELIABILITY_METHOD_VERSION, paths, parameters,
                          reason="A current computed full-abundance correlation is unavailable; its generation or retained provenance cannot be verified.",
                          inputs=frozen_inputs)

    # Use Kraken diversity only
    div_kr = diversity[diversity["source"] == "kraken"].copy()
    if div_kr.empty:
        logger.warning("No Kraken diversity data for prediction")
        return _operation(pd.DataFrame(), RELIABILITY_METHOD_VERSION, paths, parameters, inputs=frozen_inputs)

    # Get significant correlations
    sig_corr = correlations[correlations["significant"]].copy()
    if sig_corr.empty:
        logger.warning("No significant correlations for diversity prediction")
        return _operation(pd.DataFrame(), RELIABILITY_METHOD_VERSION, paths, parameters, inputs=frozen_inputs)

    # Get CTD-linked samples
    paired = ctx[(ctx["has_ctd"]) & (ctx["has_kraken"])].copy()
    if paired.empty:
        return _operation(pd.DataFrame(), RELIABILITY_METHOD_VERSION, paths, parameters, inputs=frozen_inputs)

    # Environmental variables used in correlations
    env_vars = sig_corr["env_variable"].unique().tolist()
    available_env = [v for v in env_vars if v in paired.columns]

    if not available_env:
        return _operation(pd.DataFrame(), RELIABILITY_METHOD_VERSION, paths, parameters, inputs=frozen_inputs)

    # Merge diversity with environmental data
    div_env = div_kr.merge(
        paired[["sample_id"] + available_env],
        on="sample_id",
        how="inner",
    )

    if len(div_env) < 3:
        logger.warning("Too few paired samples (%d) for prediction", len(div_env))
        return _operation(pd.DataFrame(), RELIABILITY_METHOD_VERSION, paths, parameters, inputs=frozen_inputs)

    # Simple prediction: use mean Shannon as baseline, adjust by
    # how many env variables deviate from their means in a direction
    # consistent with positive/negative genus correlations
    mean_shannon = div_env["shannon_h"].mean()
    std_shannon = div_env["shannon_h"].std()
    if std_shannon == 0:
        std_shannon = 0.1

    # Compute z-scores for environmental variables
    env_means = {v: div_env[v].mean() for v in available_env if div_env[v].notna().sum() > 0}
    env_stds = {v: div_env[v].std() for v in available_env if div_env[v].notna().sum() > 0}

    results = []
    anomaly_sigma = config.DIVERSITY_ANOMALY_SIGMA

    for _, row in div_env.iterrows():
        sid = row["sample_id"]
        actual = row["shannon_h"]

        # Count how many env vars suggest higher/lower diversity
        env_signals = []
        supporting_parts = []

        for ev in available_env:
            val = row.get(ev)
            if not _finite(val) or ev not in env_means or not _finite(env_stds.get(ev)) or env_stds[ev] <= 0:
                continue

            z = (val - env_means[ev]) / env_stds[ev]

            # Direction from correlations: positive rho + high env → high diversity
            ev_corrs = sig_corr[sig_corr["env_variable"] == ev]
            mean_rho = ev_corrs["spearman_rho"].mean()

            signal = z * mean_rho  # positive = expect higher diversity
            env_signals.append(signal)
            direction = "↑" if signal > 0 else "↓"
            supporting_parts.append(
                f"{ev.replace('mean_', '')}={val:.1f}(z={z:+.1f}{direction})"
            )

        if not env_signals:
            continue

        # Predicted diversity: baseline ± adjustment
        adjustment = np.mean(env_signals) * std_shannon * 0.5
        predicted = mean_shannon + adjustment

        deviation = actual - predicted
        deviation_sigma = deviation / std_shannon if std_shannon > 0 else 0

        results.append({
            "sample_id": sid,
            "bay": row.get("bay", None),
            "predicted_shannon": round(predicted, 4),
            "actual_shannon": round(actual, 4),
            "deviation": round(deviation, 4),
            "deviation_sigma": round(deviation_sigma, 4),
            "is_anomaly": abs(deviation_sigma) > anomaly_sigma,
            "n_supporting_vars": len(env_signals),
            "supporting_env_summary": "; ".join(supporting_parts),
            "check_status": ("fail" if abs(deviation_sigma) > anomaly_sigma else "pass")
                            if all(_finite(value) for value in (actual, predicted, deviation_sigma)) else "unavailable",
            "applicability": "in_sample_model_consistency",
            "independent": False,
            "check_reason": "An in-sample heuristic consistency check; not independent validation.",
            "method_version": RELIABILITY_METHOD_VERSION,
            "input_provenance": json.dumps(frozen_inputs, sort_keys=True),
            "independent_researcher_approval": False,
        })

    result = pd.DataFrame(results)
    n_anomalies = result["is_anomaly"].sum() if not result.empty else 0
    logger.info(
        "Diversity prediction: %d samples, %d anomalies (>%.1fσ)",
        len(result), n_anomalies, anomaly_sigma,
    )
    return _operation(result, RELIABILITY_METHOD_VERSION, paths, parameters, inputs=frozen_inputs)


# ─────────────────────────────────────────────
# 4. Cross-Source Corroboration Summary
# ─────────────────────────────────────────────
def corroborate_cross_source(
    sst_ctd_validation: pd.DataFrame,
    diversity_prediction: pd.DataFrame,
) -> pd.DataFrame:
    """Retain explicit outcomes; tier counts only passed independent checks.

    Source availability is inventory, not a check. The diversity heuristic is
    in-sample consistency, not independent validation. Regional SST comparisons
    also cannot establish native sample-point corroboration. The legacy tier
    names remain algorithmic labels and never assert researcher approval.
    """
    ctx_path = config.SERVING_DIR / "sample_multisource_context.parquet"
    parameters = {"agreement_threshold_celsius": config.SST_CTD_AGREEMENT_THRESHOLD,
                  "diversity_anomaly_sigma": config.DIVERSITY_ANOMALY_SIGMA,
                  "tier_rule": "distinct_independent_passes; verified_requires_two_and_no_failures"}
    if not ctx_path.exists():
        return _operation(pd.DataFrame(), RELIABILITY_METHOD_VERSION, (ctx_path,), parameters,
                          reason="Sample source inventory is missing.")
    (ctx,), frozen_inputs = _frozen_parquet_inputs((ctx_path,))
    if ctx.empty:
        return _operation(pd.DataFrame(), RELIABILITY_METHOD_VERSION, (ctx_path,), parameters,
                          reason="Sample source inventory is empty.", inputs=frozen_inputs)
    input_frames = {"sst_validation": sst_ctd_validation, "diversity_prediction": diversity_prediction}
    frame_hashes = {name: _frame_hash(frame) for name, frame in input_frames.items()}
    rows = []
    for _, sample in ctx.iterrows():
        sid = sample.get("sample_id")
        if pd.isna(sid):
            continue
        has_ctd = _flag(sample.get("has_ctd"))
        has_kraken, has_metaeuk = _flag(sample.get("has_kraken")), _flag(sample.get("has_metaeuk"))
        source_types = (["ctd"] if has_ctd else []) + (["metagenome"] if has_kraken or has_metaeuk else [])
        checks = []
        scores = []
        for name, frame in input_frames.items():
            applicable = has_ctd if name == "sst_validation" else has_ctd and has_kraken
            candidates = frame[frame["sample_id"] == sid] if not frame.empty and "sample_id" in frame else frame.iloc[:0]
            check = {"check_id": name, "status": "unavailable", "applicability": "unknown" if applicable else "not_applicable",
                     "independent": False, "independence_group": name,
                     "reason": "No unique check result is available." if applicable else "Required source measurements are unavailable.",
                     "provenance": {"result_sha256": frame_hashes[name],
                                    "operation": frame.attrs.get("operation")}}
            if applicable and len(candidates) == 1:
                observed = candidates.iloc[0]
                if name == "sst_validation":
                    delta = observed.get("delta_t")
                    check["applicability"] = observed.get("applicability", "unknown")
                    check["provenance"]["spatial_support"] = observed.get("spatial_support")
                    if observed.get("check_status") == "unavailable":
                        check["reason"] = observed.get("check_reason", "Spatial or measurement support is unavailable.")
                    elif _finite(delta) and abs(float(delta)) > config.SST_CTD_AGREEMENT_THRESHOLD:
                        check.update(status="fail", reason=f"SST disagreement (ΔT={float(delta):+.1f}°C).")
                        scores.append(float(np.clip(1.0 - abs(float(delta)) / (config.SST_CTD_AGREEMENT_THRESHOLD * 2), 0, 1)))
                    elif (_finite(delta) and _flag(observed.get("agrees"))
                          and observed.get("check_status") == "pass"
                          and observed.get("method_version") == SST_METHOD_VERSION
                          and check["applicability"] in {"eligible", "regional_context_only"}):
                        check.update(status="pass", independent=check["applicability"] == "eligible",
                                     reason=f"SST temperature consistency passes (ΔT={float(delta):+.1f}°C); {check['applicability']}.")
                        scores.append(float(np.clip(1.0 - abs(float(delta)) / (config.SST_CTD_AGREEMENT_THRESHOLD * 2), 0, 1)))
                    else:
                        check["reason"] = "A current spatially supported agreement result is unavailable."
                else:
                    sigma = observed.get("deviation_sigma")
                    check["applicability"] = "in_sample_model_consistency"
                    if _finite(sigma):
                        failed = abs(float(sigma)) > config.DIVERSITY_ANOMALY_SIGMA
                        if failed or (observed.get("method_version") == RELIABILITY_METHOD_VERSION
                                      and observed.get("check_status") == "pass"
                                      and _finite(observed.get("n_supporting_vars"))
                                      and float(observed["n_supporting_vars"]) > 0):
                            check.update(status="fail" if failed else "pass",
                                         reason=f"In-sample diversity {'anomaly' if failed else 'consistency'} ({float(sigma):+.1f}σ); not independent validation.")
                            scores.append(max(0.0, 1.0 - abs(float(sigma)) / 4.0))
                        else:
                            check["reason"] = "A current supported diversity-model result is unavailable."
            checks.append(check)
        passed = [check for check in checks if check["status"] == "pass"]
        failed = [check for check in checks if check["status"] == "fail"]
        independent_groups = {check["independence_group"] for check in passed if check["independent"]}
        n_checks = len(independent_groups)
        tier = "verified" if n_checks >= 2 and not failed else "supported" if n_checks else "standalone"
        rows.append({"event_id": f"sample_{sid}", "sample_id": sid, "source_type": ",".join(source_types),
                     "reliability_tier": tier,
                     "corroboration_sources": ",".join(sorted(independent_groups)),
                     "reliability_score": round(float(np.mean(scores)), 4) if scores else None,
                     "n_checks": n_checks, "n_passed_checks": len(passed), "n_failed_checks": len(failed),
                     "n_attempted_checks": len(passed) + len(failed),
                     "n_unavailable_checks": sum(check["status"] == "unavailable" for check in checks),
                     "has_conflicts": bool(failed), "checks": json.dumps(checks, sort_keys=True, default=str),
                     "detail": " | ".join(check["reason"] for check in checks),
                     "method_version": RELIABILITY_METHOD_VERSION, "independent_researcher_approval": False})
    result = pd.DataFrame(rows)
    return _operation(result, RELIABILITY_METHOD_VERSION, (ctx_path,),
                      {**parameters, "check_input_hashes": frame_hashes}, inputs=frozen_inputs)


# ─────────────────────────────────────────────
# 5. Build Reliability Text Documents (for RAG)
# ─────────────────────────────────────────────
def build_reliability_documents(
    sst_ctd_validation: pd.DataFrame,
    gap_interpolation: pd.DataFrame,
    diversity_prediction: pd.DataFrame,
    corroboration: pd.DataFrame,
) -> List[dict]:
    """
    Convert reliability outputs into text documents for RAG injection.
    Same pattern as pre_analysis.build_analysis_documents().
    """
    docs = []
    bay_names = {"O": "Onagawa Bay", "I": "Ishinomaki Bay", "M": "Mutsu Bay"}

    # ── SST-CTD validation summary ──
    if not sst_ctd_validation.empty:
        statuses = (sst_ctd_validation["check_status"] if "check_status" in sst_ctd_validation
                    else sst_ctd_validation["agrees"].map({True: "pass", False: "fail"}))
        evaluated = sst_ctd_validation[statuses.isin({"pass", "fail"})]
        n_total = len(evaluated)
        n_agree = int((statuses == "pass").sum())
        mean_delta = evaluated["abs_delta_t"].mean()
        mean_score = evaluated["reliability_score"].mean()

        text = "Algorithmic SST/CTD temperature consistency; regional means are regional context, not sample-point observations.\n"
        text += f"  Paired observations: {n_total}\n"
        text += f"  Unavailable checks: {len(sst_ctd_validation) - n_total}\n"
        text += f"  Agreement (within ±{config.SST_CTD_AGREEMENT_THRESHOLD}°C): "
        text += f"{n_agree}/{n_total} ({n_agree/n_total*100:.0f}%)\n" if n_total else "unavailable (no applicable comparison)\n"
        text += f"  Mean |ΔT|: {mean_delta:.2f}°C\n" if n_total else "  Mean |ΔT|: unavailable\n"
        text += f"  Mean reliability score: {mean_score:.3f}\n" if n_total else "  Mean reliability score: unavailable\n"

        # Per-bay breakdown
        for bay in sorted(evaluated["bay"].dropna().unique()):
            bd = evaluated[evaluated["bay"] == bay]
            bn = bay_names.get(bay, bay)
            ba = int(bd["agrees"].sum())
            text += f"  {bn}: {ba}/{len(bd)} agree, mean |ΔT|={bd['abs_delta_t'].mean():.2f}°C\n"

        # Individual disagreements
        disagree = sst_ctd_validation[statuses == "fail"]
        if not disagree.empty:
            text += "  Notable disagreements:\n"
            for _, r in disagree.iterrows():
                text += (
                    f"    {r['sample_id']}: CTD={r['ctd_surface_t']:.1f}°C vs "
                    f"SST={r['sst_daily_mean']:.1f}°C (Δ={r['delta_t']:+.1f}°C)\n"
                )

        docs.append({
            "id": "reliability_sst_ctd_validation",
            "source_type": "reliability",
            "title": "Spatially qualified SST/CTD temperature comparison",
            "text": text,
            "analysis_type": "cross_source_validation",
        })

    # ── Gap interpolation summary ──
    if not gap_interpolation.empty:
        gaps = gap_interpolation[gap_interpolation["in_ctd_gap"]]
        text = "Legacy unvalidated SST gap estimate; spatial calibration is unqualified and these are not validated sample-point temperatures.\n"
        text += f"  Total SST days available: {len(gap_interpolation)}\n"
        text += f"  Days in CTD gaps: {len(gaps)}\n"

        if not gaps.empty:
            text += f"  Interpolated T range: {gaps['interpolated_surface_t'].min():.1f}"
            text += f"–{gaps['interpolated_surface_t'].max():.1f}°C\n"
            text += f"  Mean confidence: {gaps['confidence'].mean():.3f}\n"
            text += f"  Legacy heuristic score >0.7 (not validated confidence): {(gaps['confidence'] > 0.7).sum()} days\n"

        docs.append({
            "id": "reliability_gap_interpolation",
            "source_type": "reliability",
            "title": "Legacy unvalidated SST gap estimates",
            "text": text,
            "analysis_type": "gap_interpolation",
        })

    # ── Diversity prediction summary ──
    if not diversity_prediction.empty:
        n_total = len(diversity_prediction)
        n_anomaly = int(diversity_prediction["is_anomaly"].sum())
        mean_dev = diversity_prediction["deviation_sigma"].abs().mean()

        text = "Diversity prediction: CTD environment → expected Shannon diversity.\n"
        text += f"  Samples evaluated: {n_total}\n"
        if "check_status" in diversity_prediction:
            text += f"  Unavailable checks: {(diversity_prediction['check_status'] == 'unavailable').sum()}\n"
        text += "  Applicability: in-sample model consistency, not independent validation.\n"
        text += f"  Anomalies (>{config.DIVERSITY_ANOMALY_SIGMA}σ deviation): {n_anomaly}\n"
        text += f"  Mean |deviation|: {mean_dev:.2f}σ\n"

        # Anomaly details
        anomalies = diversity_prediction[diversity_prediction["is_anomaly"]]
        if not anomalies.empty:
            text += "  Anomalous samples:\n"
            for _, r in anomalies.iterrows():
                bn = bay_names.get(r.get("bay"), r.get("bay", ""))
                text += (
                    f"    {r['sample_id']} ({bn}): predicted H'={r['predicted_shannon']:.3f}, "
                    f"actual={r['actual_shannon']:.3f} ({r['deviation_sigma']:+.1f}σ)\n"
                )

        docs.append({
            "id": "reliability_diversity_prediction",
            "source_type": "reliability",
            "title": "Environment-based diversity prediction and anomalies",
            "text": text,
            "analysis_type": "diversity_prediction",
        })

    # ── Corroboration summary ──
    if not corroboration.empty:
        tier_counts = corroboration["reliability_tier"].value_counts().to_dict()
        mean_score = corroboration["reliability_score"].mean()

        text = "Algorithmic cross-source check summary; not independent scientific approval.\n"
        text += f"  Total observations: {len(corroboration)}\n"
        text += f"  Verified algorithmic tier (passed independent checks): {tier_counts.get('verified', 0)}\n"
        text += f"  Supported (one independent check passed): {tier_counts.get('supported', 0)}\n"
        text += f"  Standalone (no independent check passed): {tier_counts.get('standalone', 0)}\n"
        if "n_failed_checks" in corroboration:
            text += f"  Failed checks retained: {corroboration['n_failed_checks'].sum()}\n"
            text += f"  Unavailable checks retained: {corroboration['n_unavailable_checks'].sum()}\n"
        text += f"  Mean reliability score: {mean_score:.3f}\n" if _finite(mean_score) else "  Mean reliability score: unavailable\n"

        # List verified observations
        verified = corroboration[corroboration["reliability_tier"] == "verified"]
        if not verified.empty:
            text += "  Verified observations:\n"
            for _, r in verified.head(10).iterrows():
                text += f"    {r['sample_id']}: {r['detail']}\n"

        docs.append({
            "id": "reliability_corroboration_summary",
            "source_type": "reliability",
            "title": "Cross-source corroboration summary",
            "text": text,
            "analysis_type": "corroboration",
        })

    frames = {"cross_source_validation": sst_ctd_validation, "gap_interpolation": gap_interpolation,
              "diversity_prediction": diversity_prediction, "corroboration": corroboration}
    methods = {"cross_source_validation": "sst_ctd_validation", "gap_interpolation": "gap_interpolation",
               "diversity_prediction": "diversity_prediction", "corroboration": "corroboration"}
    docs = [stamp_document(doc, methods[doc["analysis_type"]], frames[doc["analysis_type"]].attrs.get("operation", {})) for doc in docs]
    logger.info("Built %d reliability documents", len(docs))
    return docs


# ─────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────
def run_all() -> Dict[str, Any]:
    """Run all reliability checks and save outputs."""
    config.RELIABILITY_DIR.mkdir(parents=True, exist_ok=True)

    retain_artifact_history(config.RELIABILITY_DIR, ["sst_ctd_validation.parquet", "gap_interpolation.parquet",
        "diversity_prediction.parquet", "corroboration.parquet", "reliability_documents.jsonl", "derived_artifacts.json"])
    results: Dict[str, Any] = {}
    regeneration_id = uuid4().hex

    # 1. SST ↔ CTD validation
    logger.info("Running SST ↔ CTD surface temperature validation...")
    sst_ctd = validate_sst_ctd_surface_temp()
    sst_ctd.attrs["operation"]["parameters"]["regeneration_id"] = regeneration_id
    sst_ctd.to_parquet(
        config.RELIABILITY_DIR / "sst_ctd_validation.parquet", index=False
    )
    results["sst_ctd_validation"] = sst_ctd

    # 2. Gap interpolation
    logger.info("Running temporal gap interpolation via SST...")
    gaps = interpolate_sst_for_gaps()
    gaps.to_parquet(
        config.RELIABILITY_DIR / "gap_interpolation.parquet", index=False
    )
    results["gap_interpolation"] = gaps

    # 3. Diversity prediction
    logger.info("Running diversity prediction from environment...")
    div_pred = predict_diversity_from_env()
    div_pred.attrs["operation"]["parameters"]["regeneration_id"] = regeneration_id
    div_pred.to_parquet(
        config.RELIABILITY_DIR / "diversity_prediction.parquet", index=False
    )
    results["diversity_prediction"] = div_pred

    # 4. Cross-source corroboration
    logger.info("Computing cross-source corroboration...")
    corrob = corroborate_cross_source(sst_ctd, div_pred)
    corrob.attrs["operation"]["parameters"]["regeneration_id"] = regeneration_id
    corrob.attrs["operation"]["inputs"].update(sst_ctd.attrs.get("operation", {}).get("inputs", {}))
    corrob.attrs["operation"]["inputs"].update(div_pred.attrs.get("operation", {}).get("inputs", {}))
    corrob.attrs["operation"]["inputs"].update(input_receipts([
        config.RELIABILITY_DIR / "sst_ctd_validation.parquet", config.RELIABILITY_DIR / "diversity_prediction.parquet"]))
    corrob.to_parquet(
        config.RELIABILITY_DIR / "corroboration.parquet", index=False
    )
    results["corroboration"] = corrob

    # 5. Build reliability documents
    logger.info("Building reliability documents for RAG...")
    rel_docs = build_reliability_documents(sst_ctd, gaps, div_pred, corrob)
    doc_path = config.RELIABILITY_DIR / "reliability_documents.jsonl"
    with open(doc_path, "w", encoding="utf-8") as f:
        for d in rel_docs:
            f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
    results["documents"] = rel_docs
    write_artifact_manifest(config.RELIABILITY_DIR, {
        "sst_ctd_validation.parquet": ("sst_ctd_validation", sst_ctd.attrs.get("operation", {})),
        "diversity_prediction.parquet": ("diversity_prediction", div_pred.attrs.get("operation", {})),
        "corroboration.parquet": ("corroboration", corrob.attrs.get("operation", {})),
        "gap_interpolation.parquet": ("gap_interpolation", {"status": "unavailable", "method_version": "legacy-date-only-gap-v1",
            "inputs": input_receipts([config.NORMALIZED_DIR / "ctd_summary.parquet", config.NORMALIZED_DIR / "sst_daily_summary.parquet"]),
            "reason": "Legacy gap interpolation has no reviewed spatial calibration and is not validated evidence."}),
    })

    logger.info("Reliability ensurance complete: %d outputs", len(results))
    return results
