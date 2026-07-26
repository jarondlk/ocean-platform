from __future__ import annotations

import pandas as pd

import evaluation.visualization as visualization


def test_variant_helpers_follow_canonical_order_and_colors():
    variants = ["Full framework", "LLM-only", "unknown"]

    assert visualization._get_variant_order(variants) == [
        "LLM-only",
        "Full framework",
    ]
    assert visualization._get_colors(variants) == [
        visualization.VARIANT_COLORS[0],
        visualization.VARIANT_COLORS[-1],
    ]


def test_generate_all_figures_routes_supported_plots(
    tmp_path,
    monkeypatch,
):
    calls = []

    def record(name):
        def callback(*_args, **_kwargs):
            calls.append(name)

        return callback

    monkeypatch.setattr(visualization, "plot_radar_chart", record("radar"))
    monkeypatch.setattr(visualization, "plot_grouped_bars", record("bars"))
    monkeypatch.setattr(visualization, "plot_box_plots", record("boxes"))
    monkeypatch.setattr(
        visualization,
        "plot_source_coverage_impact",
        record("coverage"),
    )
    monkeypatch.setattr(
        visualization,
        "plot_latency_comparison",
        record("latency"),
    )
    monkeypatch.setattr(
        visualization,
        "plot_significance_heatmap",
        record("significance"),
    )
    results = pd.DataFrame(
        {
            "mode": ["LLM-only", "Full framework"],
            "retrieval_precision": [0.2, 0.9],
            "source_coverage": [0.0, 1.0],
            "citation_accuracy": [0.0, 0.9],
            "context_utilization": [0.0, 0.8],
            "latency_seconds": [1.0, 2.0],
            "citation_count": [0, 3],
        }
    )
    significance = pd.DataFrame(
        [[1.0, 0.01], [0.01, 1.0]],
        index=["LLM-only", "Full framework"],
        columns=["LLM-only", "Full framework"],
    )

    generated = visualization.generate_all_figures(
        results,
        tmp_path,
        significance_matrices={"retrieval_precision": significance},
    )

    assert calls == [
        "radar",
        "bars",
        "boxes",
        "coverage",
        "latency",
        "significance",
    ]
    assert "significance_retrieval_precision" in generated
