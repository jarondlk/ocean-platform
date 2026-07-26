from __future__ import annotations

import json

import pandas as pd

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
