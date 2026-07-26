"""
Statistical significance testing for the ablation study.

Provides non-parametric tests appropriate for small-sample (n=15)
paired evaluation data:

1. Wilcoxon Signed-Rank Test — pairwise comparison between two variants
2. Friedman Test — omnibus comparison across all variants
3. Holm-Bonferroni Correction — post-hoc multiple comparison control
4. Cliff's Delta — non-parametric effect size
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────
@dataclass
class PairwiseResult:
    """Result of a pairwise statistical test."""
    variant_a: str
    variant_b: str
    metric: str
    statistic: float
    p_value: float
    effect_size: float
    effect_category: str   # negligible, small, medium, large
    significant: bool      # after correction
    mean_a: float = 0.0
    mean_b: float = 0.0
    delta: float = 0.0     # mean_b - mean_a


@dataclass
class FriedmanResult:
    """Result of a Friedman omnibus test."""
    metric: str
    statistic: float
    p_value: float
    significant: bool
    n_variants: int
    n_questions: int


@dataclass
class StatisticalReport:
    """Complete statistical analysis results."""
    friedman_tests: List[FriedmanResult]
    pairwise_tests: List[PairwiseResult]
    significance_matrix: Dict[str, pd.DataFrame]  # metric -> n×n p-value matrix
    summary: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────
# Cliff's Delta (non-parametric effect size)
# ─────────────────────────────────────────────
def cliffs_delta(x: List[float], y: List[float]) -> Tuple[float, str]:
    """
    Compute Cliff's delta effect size between two groups.

    Interpretation (Romano et al. 2006):
        |d| < 0.147  → negligible
        |d| < 0.330  → small
        |d| < 0.474  → medium
        |d| >= 0.474 → large

    Returns:
        (delta, category) tuple.
    """
    n_x, n_y = len(x), len(y)
    if n_x == 0 or n_y == 0:
        return 0.0, "negligible"

    # Count concordant and discordant pairs
    more = sum(1 for xi in x for yi in y if xi > yi)
    less = sum(1 for xi in x for yi in y if xi < yi)
    total = n_x * n_y

    delta = (more - less) / total if total > 0 else 0.0

    # Categorize
    abs_d = abs(delta)
    if abs_d < 0.147:
        category = "negligible"
    elif abs_d < 0.330:
        category = "small"
    elif abs_d < 0.474:
        category = "medium"
    else:
        category = "large"

    return round(delta, 4), category


# ─────────────────────────────────────────────
# Wilcoxon Signed-Rank Test
# ─────────────────────────────────────────────
def wilcoxon_paired_test(
    scores_a: List[float],
    scores_b: List[float],
    alternative: str = "two-sided",
) -> Tuple[float, float]:
    """
    Wilcoxon signed-rank test for paired samples.

    Returns (statistic, p_value). If all differences are zero,
    returns (0.0, 1.0).
    """
    a = np.array(scores_a, dtype=float)
    b = np.array(scores_b, dtype=float)
    diff = b - a

    # Remove zero differences
    nonzero = diff[diff != 0]
    if len(nonzero) < 3:
        return 0.0, 1.0

    try:
        stat, p = sp_stats.wilcoxon(
            a, b, alternative=alternative, zero_method="wilcox",
        )
        return float(stat), float(p)
    except ValueError:
        return 0.0, 1.0


# ─────────────────────────────────────────────
# Friedman Test
# ─────────────────────────────────────────────
def friedman_test(
    variant_scores: Dict[str, List[float]],
) -> Tuple[float, float]:
    """
    Friedman test for comparing k related groups.

    Args:
        variant_scores: Dict mapping variant name to list of scores
                       (same length for all variants, one per question).

    Returns (statistic, p_value).
    """
    groups = list(variant_scores.values())

    if len(groups) < 3:
        logger.warning("Friedman test requires at least 3 groups")
        return 0.0, 1.0

    # All groups must have same length
    lengths = {len(g) for g in groups}
    if len(lengths) != 1:
        logger.warning("Friedman test requires equal group sizes")
        return 0.0, 1.0

    n = lengths.pop()
    if n < 3:
        logger.warning("Friedman test requires at least 3 observations")
        return 0.0, 1.0
    reference = np.asarray(groups[0], dtype=float)
    if all(
        np.array_equal(reference, np.asarray(group, dtype=float), equal_nan=True)
        for group in groups[1:]
    ):
        return 0.0, 1.0

    try:
        stat, p = sp_stats.friedmanchisquare(*groups)
        return float(stat), float(p)
    except Exception as e:
        logger.warning("Friedman test failed: %s", e)
        return 0.0, 1.0


# ─────────────────────────────────────────────
# Holm-Bonferroni Correction
# ─────────────────────────────────────────────
def holm_bonferroni_correction(
    p_values: List[float],
    alpha: float = 0.05,
) -> List[bool]:
    """
    Apply Holm-Bonferroni step-down correction for multiple comparisons.

    Returns list of booleans: True if the corresponding test is
    significant after correction.
    """
    n = len(p_values)
    if n == 0:
        return []

    # Sort p-values with original indices
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])

    significant = [False] * n
    for rank, (orig_idx, p) in enumerate(indexed):
        adjusted_alpha = alpha / (n - rank)
        if p <= adjusted_alpha:
            significant[orig_idx] = True
        else:
            # Step-down: once one fails, all remaining fail
            break

    return significant


# ─────────────────────────────────────────────
# Full Statistical Analysis
# ─────────────────────────────────────────────
def run_full_statistical_analysis(
    results_df: pd.DataFrame,
    metrics: Optional[List[str]] = None,
    alpha: float = 0.05,
) -> StatisticalReport:
    """
    Run complete statistical analysis on ablation results.

    Args:
        results_df: DataFrame with columns 'mode' (variant name),
                   'question_id', and metric columns.
        metrics: List of metric column names to analyze.
                 Defaults to standard evaluation metrics.
        alpha: Significance level (default 0.05).

    Returns:
        StatisticalReport with Friedman tests, pairwise comparisons,
        and significance matrices.
    """
    if metrics is None:
        metrics = [
            "retrieval_precision", "source_coverage",
            "citation_count", "citation_accuracy",
            "context_utilization", "latency_seconds",
        ]
        # Add quality metrics if available
        for qm in ["rouge_l", "semantic_similarity", "faithfulness",
                    "answer_completeness", "judge_mean"]:
            if qm in results_df.columns:
                metrics.append(qm)

    variants = sorted(results_df["mode"].unique())
    questions = sorted(results_df["question_id"].unique())

    friedman_results: List[FriedmanResult] = []
    pairwise_results: List[PairwiseResult] = []
    significance_matrices: Dict[str, pd.DataFrame] = {}

    for metric in metrics:
        if metric not in results_df.columns:
            continue

        # Build per-variant score vectors (aligned by question)
        variant_scores: Dict[str, List[float]] = {}
        for variant in variants:
            scores = []
            vdf = results_df[results_df["mode"] == variant]
            for q in questions:
                qrow = vdf[vdf["question_id"] == q]
                if not qrow.empty:
                    scores.append(float(qrow[metric].iloc[0]))
                else:
                    scores.append(0.0)
            variant_scores[variant] = scores

        # Friedman omnibus test (if ≥3 variants)
        if len(variants) >= 3:
            f_stat, f_p = friedman_test(variant_scores)
            friedman_results.append(FriedmanResult(
                metric=metric,
                statistic=round(f_stat, 4),
                p_value=round(f_p, 6),
                significant=f_p < alpha,
                n_variants=len(variants),
                n_questions=len(questions),
            ))

        # Pairwise Wilcoxon tests
        pairs = list(itertools.combinations(variants, 2))
        pair_p_values = []
        pair_results_temp = []

        for va, vb in pairs:
            sa = variant_scores[va]
            sb = variant_scores[vb]

            stat, p = wilcoxon_paired_test(sa, sb)
            delta, delta_cat = cliffs_delta(sa, sb)

            pair_p_values.append(p)
            pair_results_temp.append(PairwiseResult(
                variant_a=va,
                variant_b=vb,
                metric=metric,
                statistic=round(stat, 4),
                p_value=round(p, 6),
                effect_size=delta,
                effect_category=delta_cat,
                significant=False,  # Filled after correction
                mean_a=round(float(np.mean(sa)), 4),
                mean_b=round(float(np.mean(sb)), 4),
                delta=round(float(np.mean(sb)) - float(np.mean(sa)), 4),
            ))

        # Apply Holm-Bonferroni correction
        corrections = holm_bonferroni_correction(pair_p_values, alpha)
        for pr, sig in zip(pair_results_temp, corrections):
            pr.significant = sig
        pairwise_results.extend(pair_results_temp)

        # Build significance matrix
        sig_matrix = pd.DataFrame(
            np.ones((len(variants), len(variants))),
            index=variants, columns=variants,
        )
        for pr in pair_results_temp:
            sig_matrix.loc[pr.variant_a, pr.variant_b] = pr.p_value
            sig_matrix.loc[pr.variant_b, pr.variant_a] = pr.p_value
        significance_matrices[metric] = sig_matrix

    # Summary statistics
    summary = {
        "n_variants": len(variants),
        "n_questions": len(questions),
        "n_metrics": len(metrics),
        "n_pairwise_tests": len(pairwise_results),
        "n_significant_pairwise": sum(1 for pr in pairwise_results if pr.significant),
        "alpha": alpha,
        "variants": variants,
        "metrics": metrics,
    }

    return StatisticalReport(
        friedman_tests=friedman_results,
        pairwise_tests=pairwise_results,
        significance_matrix=significance_matrices,
        summary=summary,
    )


# ─────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────
def format_significance(p: float) -> str:
    """Format p-value with significance stars."""
    if p < 0.001:
        return f"{p:.4f}***"
    elif p < 0.01:
        return f"{p:.4f}**"
    elif p < 0.05:
        return f"{p:.4f}*"
    else:
        return f"{p:.4f}"


def pairwise_to_dataframe(results: List[PairwiseResult]) -> pd.DataFrame:
    """Convert pairwise results to a DataFrame for export."""
    rows = []
    for pr in results:
        rows.append({
            "variant_a": pr.variant_a,
            "variant_b": pr.variant_b,
            "metric": pr.metric,
            "mean_a": pr.mean_a,
            "mean_b": pr.mean_b,
            "delta": pr.delta,
            "statistic": pr.statistic,
            "p_value": pr.p_value,
            "significant": pr.significant,
            "effect_size": pr.effect_size,
            "effect_category": pr.effect_category,
        })
    return pd.DataFrame(rows)
