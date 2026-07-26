"""
Publication-quality visualizations for the ablation study.

Generates figures as PDF and PNG for thesis inclusion:

1. Radar/spider chart — all variants on metric axes
2. Grouped bar chart — metrics by variant
3. Significance heatmap — pairwise p-values
4. Box plots — metric distributions per variant
5. Source coverage impact — line plot showing metric progression
6. Latency comparison — bar chart with error bars
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Variant display order and colors
VARIANT_ORDER = [
    "LLM-only",
    "Single-source RAG",
    "Two-source RAG",
    "Multi-source RAG",
    "Multi-source + Analysis",
    "Multi-source + Reliability",
    "Full framework",
]

VARIANT_COLORS = [
    "#95a5a6",  # grey — LLM-only
    "#3498db",  # blue — single
    "#2980b9",  # dark blue — two
    "#2ecc71",  # green — multi
    "#e67e22",  # orange — +analysis
    "#9b59b6",  # purple — +reliability
    "#e74c3c",  # red — full
]

VARIANT_SHORT = {
    "LLM-only": "LLM",
    "Single-source RAG": "1-Src",
    "Two-source RAG": "2-Src",
    "Multi-source RAG": "3-Src",
    "Multi-source + Analysis": "+Ana",
    "Multi-source + Reliability": "+Rel",
    "Full framework": "Full",
}

METRIC_LABELS = {
    "retrieval_precision": "Retrieval\nPrecision",
    "source_coverage": "Source\nCoverage",
    "citation_count": "Citation\nCount",
    "citation_accuracy": "Citation\nAccuracy",
    "context_utilization": "Context\nUtilization",
    "latency_seconds": "Latency (s)",
    "rouge_l": "ROUGE-L",
    "semantic_similarity": "Semantic\nSimilarity",
    "faithfulness": "Faithfulness",
    "answer_completeness": "Answer\nCompleteness",
    "judge_mean": "Judge\nMean",
}


def _setup_style():
    """Configure matplotlib for publication-quality figures."""
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
    })


def _save(fig, output_dir: Path, name: str) -> None:
    """Save figure as both PDF and PNG."""
    import matplotlib.pyplot as plt
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / f"{name}.pdf")
    fig.savefig(output_dir / f"{name}.png")
    plt.close(fig)
    logger.info("Saved figure: %s", name)


def _get_variant_order(variants: List[str]) -> List[str]:
    """Sort variants in canonical order."""
    return [v for v in VARIANT_ORDER if v in variants]


def _get_colors(variants: List[str]) -> List[str]:
    """Get colors matching variant order."""
    order = _get_variant_order(variants)
    return [
        VARIANT_COLORS[VARIANT_ORDER.index(v)]
        for v in order
        if v in VARIANT_ORDER
    ]


# ─────────────────────────────────────────────
# 1. Radar / Spider Chart
# ─────────────────────────────────────────────
def plot_radar_chart(
    summary_df: pd.DataFrame,
    metrics: List[str],
    output_dir: Path,
    filename: str = "radar_chart",
) -> None:
    """
    Radar chart showing all variants across metric dimensions.

    Args:
        summary_df: DataFrame indexed by variant name, columns are metrics.
        metrics: List of metric column names to include.
        output_dir: Directory to save figures.
    """
    import matplotlib.pyplot as plt

    _setup_style()

    variants = _get_variant_order(list(summary_df.index))
    colors = _get_colors(variants)
    metrics = [m for m in metrics if m in summary_df.columns]

    if len(metrics) < 3:
        logger.warning("Need at least 3 metrics for radar chart")
        return

    # Normalize metrics to 0-1 range
    norm_df = summary_df.copy()
    for m in metrics:
        col_min = norm_df[m].min()
        col_max = norm_df[m].max()
        if col_max > col_min:
            # For latency, lower is better — invert
            if "latency" in m:
                norm_df[m] = 1.0 - (norm_df[m] - col_min) / (col_max - col_min)
            else:
                norm_df[m] = (norm_df[m] - col_min) / (col_max - col_min)
        else:
            norm_df[m] = 0.5

    N = len(metrics)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    for variant, color in zip(variants, colors):
        if variant not in norm_df.index:
            continue
        values = [norm_df.loc[variant, m] for m in metrics]
        values += values[:1]
        short = VARIANT_SHORT.get(variant, variant)
        ax.plot(angles, values, "o-", linewidth=1.5, label=short, color=color)
        ax.fill(angles, values, alpha=0.08, color=color)

    ax.set_xticks(angles[:-1])
    labels = [METRIC_LABELS.get(m, m) for m in metrics]
    ax.set_xticklabels(labels, size=8)
    ax.set_ylim(0, 1.05)
    ax.set_title("System Variant Comparison (Normalized)", pad=20, fontweight="bold")
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

    _save(fig, output_dir, filename)


# ─────────────────────────────────────────────
# 2. Grouped Bar Chart
# ─────────────────────────────────────────────
def plot_grouped_bars(
    summary_df: pd.DataFrame,
    metrics: List[str],
    output_dir: Path,
    filename: str = "grouped_bars",
) -> None:
    """Grouped bar chart of metrics per variant."""
    import matplotlib.pyplot as plt

    _setup_style()

    variants = _get_variant_order(list(summary_df.index))
    colors = _get_colors(variants)
    metrics = [m for m in metrics if m in summary_df.columns and "latency" not in m]

    if not metrics:
        return

    x = np.arange(len(metrics))
    width = 0.8 / len(variants)

    fig, ax = plt.subplots(figsize=(12, 5))

    for i, (variant, color) in enumerate(zip(variants, colors)):
        if variant not in summary_df.index:
            continue
        vals = [summary_df.loc[variant, m] for m in metrics]
        short = VARIANT_SHORT.get(variant, variant)
        offset = (i - len(variants) / 2 + 0.5) * width
        ax.bar(x + offset, vals, width * 0.9, label=short, color=color, edgecolor="white")

    ax.set_xticks(x)
    ax.set_xticklabels([METRIC_LABELS.get(m, m).replace("\n", " ") for m in metrics], rotation=25, ha="right")
    ax.set_ylabel("Score")
    ax.set_title("Evaluation Metrics by System Variant", fontweight="bold")
    ax.legend(ncol=4, fontsize=7, loc="upper left")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.15)

    _save(fig, output_dir, filename)


# ─────────────────────────────────────────────
# 3. Significance Heatmap
# ─────────────────────────────────────────────
def plot_significance_heatmap(
    p_matrix: pd.DataFrame,
    metric_name: str,
    output_dir: Path,
    filename: str = "significance_heatmap",
) -> None:
    """Heatmap of pairwise significance p-values."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    _setup_style()

    variants = _get_variant_order(list(p_matrix.index))
    p_matrix = p_matrix.loc[variants, variants]

    # Create annotation matrix with significance stars
    annot = p_matrix.copy().astype(str)
    for i in range(len(variants)):
        for j in range(len(variants)):
            p = p_matrix.iloc[i, j]
            if i == j:
                annot.iloc[i, j] = "—"
            elif p < 0.001:
                annot.iloc[i, j] = f"{p:.3f}***"
            elif p < 0.01:
                annot.iloc[i, j] = f"{p:.3f}**"
            elif p < 0.05:
                annot.iloc[i, j] = f"{p:.3f}*"
            else:
                annot.iloc[i, j] = f"{p:.3f}"

    short_labels = [VARIANT_SHORT.get(v, v) for v in variants]

    fig, ax = plt.subplots(figsize=(8, 6.5))
    sns.heatmap(
        p_matrix.values.astype(float),
        annot=annot.values,
        fmt="",
        xticklabels=short_labels,
        yticklabels=short_labels,
        cmap="RdYlGn_r",
        vmin=0, vmax=0.1,
        ax=ax,
        square=True,
        linewidths=0.5,
        cbar_kws={"label": "p-value (Wilcoxon + Holm)"},
    )
    ax.set_title(
        f"Pairwise Significance — {METRIC_LABELS.get(metric_name, metric_name).replace(chr(10), ' ')}",
        fontweight="bold",
    )
    plt.tight_layout()

    _save(fig, output_dir, filename)


# ─────────────────────────────────────────────
# 4. Box Plots
# ─────────────────────────────────────────────
def plot_box_plots(
    results_df: pd.DataFrame,
    metrics: List[str],
    output_dir: Path,
    filename: str = "box_plots",
) -> None:
    """Box plots showing metric distributions per variant."""
    import matplotlib.pyplot as plt

    _setup_style()

    variants = _get_variant_order(list(results_df["mode"].unique()))
    colors = _get_colors(variants)
    metrics = [m for m in metrics if m in results_df.columns]

    if not metrics:
        return

    n_metrics = len(metrics)
    fig, axes = plt.subplots(1, n_metrics, figsize=(3.5 * n_metrics, 5))
    if n_metrics == 1:
        axes = [axes]

    for ax, metric in zip(axes, metrics):
        data = []
        for v in variants:
            vdf = results_df[results_df["mode"] == v]
            data.append(vdf[metric].values)

        short_labels = [VARIANT_SHORT.get(v, v) for v in variants]
        bp = ax.boxplot(data, labels=short_labels, patch_artist=True, widths=0.6)

        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)

        ax.set_title(METRIC_LABELS.get(metric, metric).replace("\n", " "), fontsize=9)
        ax.tick_params(axis="x", rotation=45)

    fig.suptitle("Metric Distributions Across System Variants", fontweight="bold", y=1.02)
    plt.tight_layout()

    _save(fig, output_dir, filename)


# ─────────────────────────────────────────────
# 5. Source Coverage Impact
# ─────────────────────────────────────────────
def plot_source_coverage_impact(
    summary_df: pd.DataFrame,
    metrics: List[str],
    output_dir: Path,
    filename: str = "source_coverage_impact",
) -> None:
    """
    Line plot showing metric progression as source coverage increases (0→3).

    Only uses variants with no analysis/reliability injection to isolate
    the effect of source coverage.
    """
    import matplotlib.pyplot as plt

    _setup_style()

    coverage_variants = [
        ("LLM-only", 0),
        ("Single-source RAG", 1),
        ("Two-source RAG", 2),
        ("Multi-source RAG", 3),
    ]

    available = [(name, cov) for name, cov in coverage_variants if name in summary_df.index]
    if len(available) < 2:
        logger.warning("Not enough variants for source coverage impact plot")
        return

    metrics = [m for m in metrics if m in summary_df.columns and "latency" not in m]
    if not metrics:
        return

    fig, ax = plt.subplots(figsize=(8, 5))

    x_vals = [cov for _, cov in available]
    for metric in metrics:
        y_vals = [summary_df.loc[name, metric] for name, _ in available]
        label = METRIC_LABELS.get(metric, metric).replace("\n", " ")
        ax.plot(x_vals, y_vals, "o-", linewidth=2, markersize=6, label=label)

    ax.set_xlabel("Number of Source Types")
    ax.set_ylabel("Score")
    ax.set_xticks([0, 1, 2, 3])
    ax.set_xticklabels(["0\n(LLM-only)", "1\n(Single)", "2\n(Two)", "3\n(Multi)"])
    ax.set_title("Impact of Source Coverage on Evaluation Metrics", fontweight="bold")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)

    _save(fig, output_dir, filename)


# ─────────────────────────────────────────────
# 6. Latency Comparison
# ─────────────────────────────────────────────
def plot_latency_comparison(
    results_df: pd.DataFrame,
    output_dir: Path,
    filename: str = "latency_comparison",
) -> None:
    """Bar chart of mean ± std latency per variant."""
    import matplotlib.pyplot as plt

    _setup_style()

    if "latency_seconds" not in results_df.columns:
        return

    variants = _get_variant_order(list(results_df["mode"].unique()))
    colors = _get_colors(variants)

    means = []
    stds = []
    for v in variants:
        vdf = results_df[results_df["mode"] == v]
        means.append(vdf["latency_seconds"].mean())
        stds.append(vdf["latency_seconds"].std())

    short_labels = [VARIANT_SHORT.get(v, v) for v in variants]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(
        short_labels, means, yerr=stds,
        color=colors, edgecolor="white",
        capsize=4, alpha=0.85,
    )

    ax.set_ylabel("Latency (seconds)")
    ax.set_title("Response Latency by System Variant", fontweight="bold")
    ax.grid(axis="y", alpha=0.3)

    # Value labels on bars
    for bar, mean in zip(bars, means):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
            f"{mean:.1f}s", ha="center", va="bottom", fontsize=8,
        )

    _save(fig, output_dir, filename)


# ─────────────────────────────────────────────
# Master function
# ─────────────────────────────────────────────
def generate_all_figures(
    results_df: pd.DataFrame,
    output_dir: Path,
    significance_matrices: Optional[Dict[str, pd.DataFrame]] = None,
    metrics: Optional[List[str]] = None,
) -> List[str]:
    """
    Generate all publication-quality figures.

    Args:
        results_df: Full evaluation results DataFrame.
        output_dir: Directory to save figures.
        significance_matrices: Optional pairwise p-value matrices.
        metrics: Optional list of metrics to plot.

    Returns:
        List of generated figure filenames.
    """
    if metrics is None:
        metrics = [
            "retrieval_precision", "source_coverage",
            "citation_accuracy", "context_utilization",
        ]
        for qm in ["rouge_l", "semantic_similarity",
                    "faithfulness", "answer_completeness", "judge_mean"]:
            if qm in results_df.columns:
                metrics.append(qm)

    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Summary by mode
    metric_cols = [m for m in metrics + ["latency_seconds", "citation_count"]
                   if m in results_df.columns]
    summary = results_df.groupby("mode")[metric_cols].mean()

    generated = []

    try:
        plot_radar_chart(summary, metrics, figures_dir)
        generated.append("radar_chart")
    except Exception as e:
        logger.warning("Radar chart failed: %s", e)

    try:
        plot_grouped_bars(summary, metrics, figures_dir)
        generated.append("grouped_bars")
    except Exception as e:
        logger.warning("Grouped bars failed: %s", e)

    try:
        plot_box_plots(results_df, metrics, figures_dir)
        generated.append("box_plots")
    except Exception as e:
        logger.warning("Box plots failed: %s", e)

    try:
        plot_source_coverage_impact(summary, metrics, figures_dir)
        generated.append("source_coverage_impact")
    except Exception as e:
        logger.warning("Source coverage impact plot failed: %s", e)

    try:
        plot_latency_comparison(results_df, figures_dir)
        generated.append("latency_comparison")
    except Exception as e:
        logger.warning("Latency comparison failed: %s", e)

    # Significance heatmaps (one per key metric)
    if significance_matrices:
        for metric_name, matrix in significance_matrices.items():
            if metric_name in ["retrieval_precision", "citation_accuracy",
                               "rouge_l", "faithfulness", "judge_mean"]:
                try:
                    plot_significance_heatmap(
                        matrix, metric_name, figures_dir,
                        f"significance_{metric_name}",
                    )
                    generated.append(f"significance_{metric_name}")
                except Exception as e:
                    logger.warning("Significance heatmap for %s failed: %s", metric_name, e)

    logger.info("Generated %d figures in %s", len(generated), figures_dir)
    return generated
