from __future__ import annotations

import json
import hashlib

import numpy as np
import pandas as pd
import pytest

import preprocessing.pre_analysis as analysis


def _configure_analysis_data(tmp_path, monkeypatch):
    normalized = tmp_path / "normalized"
    serving = tmp_path / "serving"
    output = tmp_path / "analysis"
    normalized.mkdir()
    serving.mkdir()

    sample_ids = [
        "2024-01-O-s1",
        "2024-02-O-s1",
        "2024-03-O-s1",
        "2024-01-I-s1",
        "2024-02-I-s1",
        "2024-03-I-s1",
    ]
    ctd = pd.DataFrame(
        {
            "sample_id": sample_ids,
            "ctd_date": pd.date_range("2024-01-01", periods=6, freq="30D"),
            "mean_temperature": [10, 11, 12, 13, 14, 15],
            "mean_salinity": [33, 33.1, 33.2, 33.3, 33.4, 33.5],
            "mean_do_percent": [90, 91, 92, 93, 94, 95],
            "mean_chl_a": [1, 2, 3, 4, 5, 6],
            "mean_turbidity": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            "surface_temperature": [11, 12, 13, 14, 15, 16],
            "bottom_temperature": [9, 10, 11, 12, 13, 14],
            "surface_salinity": [32.9] * 6,
            "bottom_salinity": [33.6] * 6,
        }
    )
    ctd.to_parquet(normalized / "ctd_summary.parquet", index=False)

    taxa_rows = []
    for sample_index, sample_id in enumerate(sample_ids):
        for genus_index, genus in enumerate(
            ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"]
        ):
            taxa_rows.append(
                {
                    "genus": genus,
                    "sample_id": sample_id,
                    "abundance_value": (
                        sample_index + genus_index + 1
                        if (sample_index + genus_index) % 3
                        else 0
                    ),
                    "method": "kraken",
                }
            )
    abundance = pd.DataFrame(taxa_rows)
    abundance.to_parquet(
        normalized / "kraken_genus_abundance.parquet",
        index=False,
    )
    abundance.assign(method="metaeuk").to_parquet(
        normalized / "metaeuk_genus_abundance.parquet",
        index=False,
    )

    context_rows = []
    for index, sample_id in enumerate(sample_ids):
        context_rows.append(
            {
                "sample_id": sample_id,
                "has_ctd": True,
                "has_kraken": True,
                "mean_temperature": 10 + index,
                "mean_salinity": 33 + index / 10,
                "mean_do_percent": 90 + index,
                "mean_chl_a": 1 + index,
                "mean_turbidity": 0.1 + index / 10,
                "top_genus_10_json_x": json.dumps(
                    [
                        {
                            "genus": "Alpha",
                            "abundance_value": index + 1,
                        },
                        {
                            "genus": "Beta",
                            "abundance_value": 6 - index,
                        },
                    ]
                ),
            }
        )
    pd.DataFrame(context_rows).to_parquet(
        serving / "sample_multisource_context.parquet",
        index=False,
    )

    monkeypatch.setattr(analysis.config, "NORMALIZED_DIR", normalized)
    monkeypatch.setattr(analysis.config, "SERVING_DIR", serving)
    monkeypatch.setattr(analysis.config, "ANALYSIS_DIR", output)
    return output


def test_pre_analysis_computes_and_persists_all_outputs(
    tmp_path,
    monkeypatch,
):
    output = _configure_analysis_data(tmp_path, monkeypatch)

    results = analysis.run_all()

    assert set(results) == {
        "trends",
        "correlations",
        "diversity",
        "bay_comparison",
        "cooccurrence",
        "documents",
    }
    assert not results["trends"].empty
    assert not results["correlations"].empty
    assert not results["diversity"].empty
    assert set(results["bay_comparison"]["bay"]) == {"I", "O"}
    assert not results["cooccurrence"].empty
    assert results["documents"]
    assert (output / "analysis_documents.jsonl").exists()
    assert (output / "ctd_monthly_trends.parquet").exists()


def test_explicit_rerun_has_a_new_generation_even_when_scientific_rows_are_identical(tmp_path, monkeypatch):
    output = _configure_analysis_data(tmp_path, monkeypatch)
    sample_ids = pd.read_parquet(analysis.config.SERVING_DIR / "sample_multisource_context.parquet")["sample_id"]
    pd.DataFrame({"sample_id": sample_ids, "genus": "SyntheticTrend", "method": "kraken",
                  "abundance_value": range(1, len(sample_ids) + 1)}).to_parquet(
        analysis.config.NORMALIZED_DIR / "kraken_genus_abundance.parquet", index=False,
    )

    first = analysis.run_all()
    second = analysis.run_all()

    identifiers = [run["correlations"].attrs["operation"]["parameters"]["regeneration_id"]
                   for run in (first, second)]
    assert identifiers[0] != identifiers[1]
    assert all(len(value) == 32 and int(value, 16) >= 0 for value in identifiers)
    assert first["correlations"].to_dict("records") == second["correlations"].to_dict("records")
    correlation_documents = [next(document for document in run["documents"]
                                  if document["analysis_type"] == "taxa_env_correlation") for run in (first, second)]
    receipts = [document["derived_artifact"] for document in correlation_documents]
    assert [receipt["parameters"]["regeneration_id"] for receipt in receipts] == identifiers
    assert receipts[0]["generation_sha256"] != receipts[1]["generation_sha256"]
    manifest = json.loads((output / "derived_artifacts.json").read_text())
    assert manifest["artifacts"]["taxa_env_correlations.parquet"]["parameters"]["regeneration_id"] == identifiers[1]
    assert "regeneration_id" not in analysis.compute_taxa_env_correlations().attrs["operation"]["parameters"]


def test_analysis_documents_include_each_supported_summary_type():
    trends = pd.DataFrame(
        [
            {
                "bay": "O",
                "year_month": "2024-01",
                "mean_temperature_mean": 12.3,
                "mean_temperature_std": 0.5,
                "mean_temperature_count": 3,
            }
        ]
    )
    correlations = pd.DataFrame(
        [
            {
                "genus": "Alpha",
                "env_variable": "mean_temperature",
                "spearman_rho": 0.8,
                "p_value": 0.01,
                "n_samples": 8,
                "significant": True,
            }
        ]
    )
    diversity = pd.DataFrame(
        [
            {
                "sample_id": "2024-01-O-s1",
                "source": "kraken",
                "shannon_h": 1.2,
                "simpson_1d": 0.7,
                "richness": 3,
                "evenness": 0.9,
            }
        ]
    )
    bay = pd.DataFrame(
        [
            {
                "bay": "O",
                "mean_temperature_mean": 12.3,
                "mean_temperature_std": 0.5,
                "mean_temperature_count": 3,
            }
        ]
    )

    documents = analysis.build_analysis_documents(
        trends,
        correlations,
        diversity,
        bay,
    )

    assert {document["analysis_type"] for document in documents} == {
        "ctd_temporal_trends",
        "taxa_env_correlation",
        "diversity_indices",
        "bay_comparison",
    }


def _correlation_inputs(tmp_path, monkeypatch, abundance):
    normalized = tmp_path / "normalized"
    serving = tmp_path / "serving"
    normalized.mkdir()
    serving.mkdir()
    sample_ids = [f"synthetic-{index}" for index in range(12)]
    rows = []
    for index, sample_id in enumerate(sample_ids):
        top_ten = [{"genus": f"Competitor-{j}", "abundance_value": 2.0}
                   for j in range(9 if index < 6 else 10)]
        if index < 6:
            top_ten.append({"genus": "ConstantGenus", "abundance_value": 1.0})
        rows.append({
            "sample_id": sample_id, "has_ctd": True, "has_kraken": True,
            "mean_temperature": index + 1.0,
            "top_genus_10_json_x": json.dumps(top_ten),
        })
    context_path = serving / "sample_multisource_context.parquet"
    pd.DataFrame(rows).to_parquet(context_path, index=False)
    abundance_path = normalized / "kraken_genus_abundance.parquet"
    if abundance is not None:
        abundance.to_parquet(abundance_path, index=False)
    monkeypatch.setattr(analysis.config, "NORMALIZED_DIR", normalized)
    monkeypatch.setattr(analysis.config, "SERVING_DIR", serving)
    return context_path, abundance_path


def _abundance_rows(values, *, genus="MeasuredGenus", method="kraken"):
    return pd.DataFrame([
        {"sample_id": f"synthetic-{index}", "genus": genus,
         "abundance_value": value, "method": method}
        for index, value in enumerate(values)
    ])


def test_full_constant_abundance_is_not_changed_by_top_ten_displacement(tmp_path, monkeypatch):
    abundance = pd.concat([
        _abundance_rows([1.0] * 12, genus="ConstantGenus"),
        _abundance_rows(range(1, 13), genus="ChangingGenus"),
    ], ignore_index=True)
    context_path, abundance_path = _correlation_inputs(tmp_path, monkeypatch, abundance)

    correlations = analysis.compute_taxa_env_correlations()

    assert correlations.attrs["operation"]["status"] == "computed"
    assert set(correlations["genus"]) == {"ChangingGenus"}
    row = correlations.iloc[0]
    assert row["spearman_rho"] == 1.0 and row["n_samples"] == 12
    assert row["n_observed_zero"] == 0
    for path in (context_path, abundance_path):
        assert correlations.attrs["operation"]["inputs"][str(path.resolve())] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert correlations.attrs["operation"]["method_version"] == "taxa-env-full-abundance-v2"
    documents = analysis.build_analysis_documents(pd.DataFrame(), correlations, pd.DataFrame(), pd.DataFrame())
    assert "ConstantGenus" not in documents[0]["text"]


def test_explicit_missing_measurements_stay_missing_and_measured_zero_is_used(tmp_path, monkeypatch):
    abundance = _abundance_rows([0, 1, 2, 3, 4, 5, *([np.nan] * 6)])
    _correlation_inputs(tmp_path, monkeypatch, abundance)

    correlations = analysis.compute_taxa_env_correlations()

    row = correlations.iloc[0]
    assert row["n_samples"] == 6 and row["n_missing_abundance"] == 6
    assert row["n_observed_zero"] == 1 and row["spearman_rho"] == 1.0
    assert correlations.attrs["operation"]["parameters"]["min_samples"] == 5


def test_assignment_methods_are_correlated_separately_and_labelled(tmp_path, monkeypatch):
    abundance = pd.concat([
        _abundance_rows(range(1, 13), method="kraken"),
        _abundance_rows(range(12, 0, -1), method="alternate_assignment"),
    ], ignore_index=True)
    _correlation_inputs(tmp_path, monkeypatch, abundance)

    correlations = analysis.compute_taxa_env_correlations()

    assert correlations.set_index("method")["spearman_rho"].to_dict() == {
        "kraken": 1.0, "alternate_assignment": -1.0,
    }
    assert correlations["n_samples"].tolist() == [12, 12]
    documents = analysis.build_analysis_documents(pd.DataFrame(), correlations, pd.DataFrame(), pd.DataFrame())
    assert "(kraken)" in documents[0]["text"] and "(alternate_assignment)" in documents[0]["text"]


def test_complete_wide_input_preserves_explicit_zero_and_missingness(tmp_path, monkeypatch):
    values = [0, 1, 2, 3, 4, 5, *([np.nan] * 6)]
    abundance = pd.DataFrame([{"genus": "MeasuredGenus", **{
        f"synthetic-{index}": value for index, value in enumerate(values)
    }}])
    _correlation_inputs(tmp_path, monkeypatch, abundance)

    correlations = analysis.compute_taxa_env_correlations()

    row = correlations.iloc[0]
    assert row["method"] == "kraken" and row["n_samples"] == 6
    assert row["n_observed_zero"] == 1 and row["n_missing_abundance"] == 6


@pytest.mark.parametrize("case", ["missing_file", "absent_cell", "missing_sample", "duplicate_cell",
                                  "invalid_number", "negative", "infinite", "missing_method"])
def test_incomplete_or_ambiguous_abundance_is_an_unavailable_operation(tmp_path, monkeypatch, case):
    abundance = pd.concat([
        _abundance_rows(range(1, 13)),
        _abundance_rows(range(12, 0, -1), genus="OtherGenus"),
    ], ignore_index=True)
    if case == "missing_file":
        abundance = None
    elif case == "absent_cell":
        abundance = abundance.drop(index=0)
    elif case == "missing_sample":
        abundance = abundance[abundance["sample_id"] != "synthetic-0"]
    elif case == "duplicate_cell":
        abundance = pd.concat([abundance, abundance.iloc[[0]]], ignore_index=True)
    elif case == "missing_method":
        abundance = abundance.drop(columns="method")
    else:
        abundance["abundance_value"] = abundance["abundance_value"].astype(str if case == "invalid_number" else float)
        abundance.loc[0, "abundance_value"] = {"invalid_number": "not measured", "negative": -1, "infinite": np.inf}[case]
    context_path, abundance_path = _correlation_inputs(tmp_path, monkeypatch, abundance)

    correlations = analysis.compute_taxa_env_correlations()

    operation = correlations.attrs["operation"]
    assert correlations.empty and operation["status"] == "unavailable" and operation["reason"]
    assert str(context_path.resolve()) in operation["inputs"]
    if abundance_path.exists():
        assert str(abundance_path.resolve()) in operation["inputs"]
    assert analysis.build_analysis_documents(pd.DataFrame(), correlations, pd.DataFrame(), pd.DataFrame()) == []


def test_insufficient_observations_are_not_zero_filled_to_meet_threshold(tmp_path, monkeypatch):
    _correlation_inputs(tmp_path, monkeypatch, _abundance_rows([1, 2, 3, 4, *([np.nan] * 8)]))

    correlations = analysis.compute_taxa_env_correlations()

    assert correlations.empty
    operation = correlations.attrs["operation"]
    assert operation["status"] == "unavailable" and operation["reason"] == "no_estimable_correlations"
    assert operation["unavailable_pairs"][0]["reason"] == "insufficient_paired_measurements"


@pytest.mark.parametrize("changed_input", ["abundance", "context"])
def test_correlation_hashes_and_values_use_the_same_snapshot_during_file_replacement(
    tmp_path, monkeypatch, changed_input,
):
    context_path, abundance_path = _correlation_inputs(tmp_path, monkeypatch, _abundance_rows(range(1, 13)))
    original_hashes = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in (context_path, abundance_path)}
    read_parquet = pd.read_parquet
    changed_path = abundance_path if changed_input == "abundance" else context_path
    replacement = read_parquet(changed_path)
    field = "abundance_value" if changed_input == "abundance" else "mean_temperature"
    replacement[field] = list(range(12, 0, -1))
    calls = []

    def replace_before_parse(source, *args, **kwargs):
        if not calls:
            # Both input receipts are captured before the first parser call.
            # Reopening this path would now read an opposite scientific trend.
            replacement.to_parquet(changed_path, index=False)
        calls.append(source)
        return read_parquet(source, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", replace_before_parse)

    correlations = analysis.compute_taxa_env_correlations()

    assert correlations.iloc[0]["spearman_rho"] == 1.0
    assert correlations.attrs["operation"]["inputs"] == original_hashes
    assert hashlib.sha256(changed_path.read_bytes()).hexdigest() != original_hashes[str(changed_path.resolve())]
    assert len(calls) == 2
    assert [hashlib.sha256(source.getvalue()).hexdigest() for source in calls] == [
        original_hashes[str(context_path.resolve())], original_hashes[str(abundance_path.resolve())],
    ]
