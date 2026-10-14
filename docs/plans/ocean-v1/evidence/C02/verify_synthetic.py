"""Reproduce C02 findings against Git baseline and regenerate disposable fixtures.

Run with .venv/bin/python docs/plans/ocean-v1/evidence/C02/verify_synthetic.py.
Only synthetic temp files are written outside this evidence directory. No data
provider, production dataset, database, model or publication is accessed.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
import config  # noqa: E402
from preprocessing import derived_artifacts as derived  # noqa: E402
from preprocessing import pre_analysis, reliability_ensurance as reliability  # noqa: E402

import pandas as pd  # noqa: E402

BASELINE = "c7ea5f4c4243d1c1a0657a0a01c075f5f738219d"
DEST = Path(__file__).resolve().parent


def legacy_module(path):
    payload = subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT)
    module = types.ModuleType("c02_legacy_" + Path(path).stem)
    exec(compile(payload, f"{BASELINE}:{path}", "exec"), module.__dict__)
    return module


def fixtures(root):
    for setting, folder in (("NORMALIZED_DIR", "normalized"), ("SERVING_DIR", "serving"),
                            ("ANALYSIS_DIR", "analysis"), ("RELIABILITY_DIR", "reliability")):
        path = root / folder
        path.mkdir()
        setattr(config, setting, path)
    ids = [f"2024-{index + 1:02d}-O-s1" for index in range(12)]
    dates = [f"2024-{index + 1:02d}-15" for index in range(12)]
    projections = []
    for index in range(12):
        entries = [{"genus": f"Competitor-{j}", "abundance_value": 2.0}
                   for j in range(9 if index < 6 else 10)]
        if index < 6:
            entries.append({"genus": "ConstantGenus", "abundance_value": 1.0})
        projections.append(json.dumps(entries))
    pd.DataFrame({"sample_id": ids, "has_ctd": True, "has_kraken": True, "has_metaeuk": False,
                  "mean_temperature": list(range(12)), "top_genus_10_json_x": projections}).to_parquet(
        config.SERVING_DIR / "sample_multisource_context.parquet", index=False)
    ctd = pd.DataFrame({"sample_id": ids, "ctd_date": dates, "mean_temperature": list(range(12)),
                        "surface_temperature": [20.] * 12, "lat": [38.5] * 11 + [40.9], "lon": [141.5] * 12})
    ctd.to_parquet(config.NORMALIZED_DIR / "ctd_summary.parquet", index=False)
    support = {"kind": "reviewed_regional_context_rectangle", "west": 141., "east": 142., "south": 38., "north": 39.,
               "reviewed": True, "reference": "fixture://synthetic-spatial-review"}
    pd.DataFrame({"date_jst": dates, "mean_sst": [20.] * 12, "min_sst": [19.] * 12, "max_sst": [21.] * 12,
                  "spatial_support": [json.dumps(support)] * 12}).to_parquet(config.NORMALIZED_DIR / "sst_daily_summary.parquet", index=False)
    abundance = pd.DataFrame([{"sample_id": sample, "genus": genus, "method": "kraken", "abundance_value": value}
        for index, sample in enumerate(ids) for genus, value in (("ConstantGenus", 1.), ("ChangingGenus", float(index)))])
    abundance.to_parquet(config.NORMALIZED_DIR / "kraken_genus_abundance.parquet", index=False)
    return ids


def inventory():
    names = {"analysis": ["taxa_env_correlations.parquet", "analysis_documents.jsonl"],
             "reliability": ["sst_ctd_validation.parquet", "diversity_prediction.parquet", "corroboration.parquet",
                             "gap_interpolation.parquet", "reliability_documents.jsonl"]}
    result = {}
    for folder, files in names.items():
        for name in files:
            path = ROOT / "data" / folder / name
            if path.is_file():
                result[str(path.relative_to(ROOT))] = {"bytes": path.stat().st_size, "sha256": derived.file_hash(path),
                    "current_eligibility": "legacy_unversioned", "action": "Later authorized regeneration and eligibility review required."}
    return result


def run():
    before = inventory()
    original_config = {name: getattr(config, name) for name in ("NORMALIZED_DIR", "SERVING_DIR", "ANALYSIS_DIR", "RELIABILITY_DIR")}
    baseline_reliability = legacy_module("preprocessing/reliability_ensurance.py")
    baseline_analysis = legacy_module("preprocessing/pre_analysis.py")
    report = {"component": "C02", "scope": "Synthetic local fixtures only; no scientific approval or publication.", "baseline_revision": BASELINE}
    try:
        with tempfile.TemporaryDirectory(prefix="ocean-c02-") as temp:
            root = Path(temp).resolve()
            ids = fixtures(root)
            failed_sst = pd.DataFrame({"sample_id": [ids[0]], "agrees": [False], "delta_t": [8.], "reliability_score": [0.]})
            anomaly = pd.DataFrame({"sample_id": [ids[0]], "is_anomaly": [True], "deviation_sigma": [5.]})
            legacy_corrob = baseline_reliability.corroborate_cross_source(failed_sst, anomaly)
            corrected_corrob = reliability.corroborate_cross_source(failed_sst, anomaly)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                legacy_correlation = baseline_analysis.compute_taxa_env_correlations()
            false = legacy_correlation.loc[legacy_correlation.genus.eq("ConstantGenus")].iloc[0]
            corrected = pre_analysis.compute_taxa_env_correlations()
            legacy_sst = baseline_reliability.validate_sst_ctd_surface_temp()
            corrected_sst = reliability.validate_sst_ctd_surface_temp()
            report["finding_probes"] = {
                "F02": {"legacy_tier": legacy_corrob.iloc[0].reliability_tier, "legacy_n_checks": int(legacy_corrob.iloc[0].n_checks),
                         "corrected_tier": corrected_corrob.iloc[0].reliability_tier, "corrected_passed_independent": int(corrected_corrob.iloc[0].n_checks),
                         "corrected_failed": int(corrected_corrob.iloc[0].n_failed_checks)},
                "F04": {"legacy_constant_genus_rho": float(false.spearman_rho), "legacy_p_value": float(false.p_value),
                         "legacy_significant": bool(false.significant), "corrected_constant_genus_correlations": int(corrected.genus.eq("ConstantGenus").sum()),
                         "corrected_measured_zero_count": int(corrected.iloc[0].n_observed_zero)},
                "F05": {"legacy_40_9N_agrees": bool(legacy_sst.loc[legacy_sst.sample_id.eq(ids[-1])].iloc[0].agrees),
                         "corrected_40_9N_status": corrected_sst.iloc[-1].check_status, "corrected_40_9N_applicability": corrected_sst.iloc[-1].applicability},
            }
            assert report["finding_probes"]["F02"]["legacy_tier"] == "verified"
            assert report["finding_probes"]["F02"]["corrected_tier"] != "verified"
            assert bool(false.significant) and not corrected.genus.eq("ConstantGenus").any()
            assert corrected_sst.iloc[-1].check_status == "unavailable"
            # Retain a synthetic prior generation, then run actual producers.
            legacy_correlation.to_parquet(config.ANALYSIS_DIR / "taxa_env_correlations.parquet", index=False)
            legacy_corrob.to_parquet(config.RELIABILITY_DIR / "corroboration.parquet", index=False)
            analysis = pre_analysis.run_all()
            checks = reliability.run_all()
            operations = {}
            for folder in ("analysis", "reliability"):
                manifest = json.loads((root / folder / "derived_artifacts.json").read_text())
                for name, receipt in manifest["artifacts"].items():
                    path = root / folder / name
                    actual_inputs = {str(Path(source).relative_to(root)): checksum for source, checksum in receipt["inputs"].items()}
                    operations[f"{folder}/{name}"] = {**receipt, "input_archive_paths": actual_inputs,
                        "eligibility_check": derived.file_eligibility(path, expected_inputs=derived.current_method_inputs(receipt["method_id"])).as_dict()}
                    for source, checksum in receipt["inputs"].items():
                        assert derived.file_hash(source) == checksum
            report["regenerated_artifacts"] = operations
            report["document_counts"] = {"analysis": len(analysis["documents"]), "reliability": len(checks["documents"])}
            report["history"] = [str(path.relative_to(root)) for path in sorted(root.glob("*/derived_history/*/history.json"))]
            assert all(not row["eligibility_check"]["eligible"] for row in operations.values())
            with zipfile.ZipFile(DEST / "synthetic-regeneration.zip", "w", zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        archive.write(path, str(path.relative_to(root)))
    finally:
        for name, value in original_config.items():
            setattr(config, name, value)
    after = inventory()
    assert before == after, "Real local artifacts changed during synthetic verification."
    report["real_artifact_inventory"] = after
    report["real_artifacts_unchanged"] = True
    report["archive_sha256"] = derived.file_hash(DEST / "synthetic-regeneration.zip")
    (DEST / "synthetic-regeneration.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"finding_probes": report["finding_probes"], "artifact_count": len(report["regenerated_artifacts"]),
                      "real_artifacts_unchanged": True}, indent=2))


if __name__ == "__main__":
    run()
