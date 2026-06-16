"""Tests for evaluation/statistical_analysis.py — significance testing."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from evaluation.statistical_analysis import (
    FriedmanResult,
    PairwiseResult,
    cliffs_delta,
    format_significance,
    friedman_test,
    holm_bonferroni_correction,
    pairwise_to_dataframe,
    run_full_statistical_analysis,
    wilcoxon_paired_test,
)


# ─────────────────────────────────────────────
# Cliff's Delta
# ─────────────────────────────────────────────
class TestCliffsDelta:
    """Test non-parametric effect size computation."""

    def test_identical_groups(self):
        x = [1, 2, 3, 4, 5]
        delta, cat = cliffs_delta(x, x)
        assert delta == 0.0
        assert cat == "negligible"

    def test_completely_separated(self):
        x = [1, 2, 3]
        y = [4, 5, 6]
        delta, cat = cliffs_delta(x, y)
        assert delta == pytest.approx(-1.0)
        assert cat == "large"

    def test_reversed_separation(self):
        x = [4, 5, 6]
        y = [1, 2, 3]
        delta, cat = cliffs_delta(x, y)
        assert delta == pytest.approx(1.0)
        assert cat == "large"

    def test_small_effect(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [1.1, 2.1, 3.1, 4.1, 5.1]
        delta, cat = cliffs_delta(x, y)
        assert abs(delta) < 0.33
        assert cat in ("negligible", "small")

    def test_empty_groups(self):
        delta, cat = cliffs_delta([], [1, 2])
        assert delta == 0.0
        assert cat == "negligible"

    def test_effect_categories(self):
        """Verify category thresholds."""
        # negligible: |d| < 0.147 — use large samples for stability
        x = list(range(1, 21))
        y = [v + 0.01 for v in x]
        _, cat = cliffs_delta(x, y)
        assert cat == "negligible"

    def test_medium_effect(self):
        x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        y = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        delta, cat = cliffs_delta(x, y)
        assert cat in ("small", "medium")


# ─────────────────────────────────────────────
# Wilcoxon Signed-Rank Test
# ─────────────────────────────────────────────
class TestWilcoxonPairedTest:
    """Test Wilcoxon signed-rank test."""

    def test_identical_samples(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        stat, p = wilcoxon_paired_test(a, a)
        # All differences are zero → returns default
        assert p == 1.0

    def test_clearly_different(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        b = [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0]
        stat, p = wilcoxon_paired_test(a, b)
        assert p < 0.05

    def test_not_significant(self):
        np.random.seed(42)
        a = list(np.random.normal(5, 1, 15))
        b = [x + np.random.normal(0, 0.01) for x in a]
        stat, p = wilcoxon_paired_test(a, b)
        # Very small perturbation — likely not significant
        assert p > 0.005

    def test_too_few_nonzero_diffs(self):
        a = [1.0, 2.0]
        b = [1.0, 2.0]
        stat, p = wilcoxon_paired_test(a, b)
        assert p == 1.0


# ─────────────────────────────────────────────
# Friedman Test
# ─────────────────────────────────────────────
class TestFriedmanTest:
    """Test Friedman omnibus test."""

    def test_identical_groups(self):
        scores = {
            "A": [1.0, 2.0, 3.0, 4.0, 5.0],
            "B": [1.0, 2.0, 3.0, 4.0, 5.0],
            "C": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
        stat, p = friedman_test(scores)
        # Identical groups → no difference; scipy may return NaN or 1.0
        assert p >= 0.99 or (isinstance(p, float) and np.isnan(p))

    def test_clearly_different_groups(self):
        scores = {
            "A": [1.0, 1.0, 1.0, 1.0, 1.0],
            "B": [5.0, 5.0, 5.0, 5.0, 5.0],
            "C": [9.0, 9.0, 9.0, 9.0, 9.0],
        }
        stat, p = friedman_test(scores)
        assert p < 0.05

    def test_too_few_groups(self):
        scores = {
            "A": [1.0, 2.0, 3.0],
            "B": [4.0, 5.0, 6.0],
        }
        stat, p = friedman_test(scores)
        assert p == 1.0  # Requires ≥3 groups

    def test_too_few_observations(self):
        scores = {
            "A": [1.0, 2.0],
            "B": [3.0, 4.0],
            "C": [5.0, 6.0],
        }
        stat, p = friedman_test(scores)
        assert p == 1.0  # Requires ≥3 observations

    def test_unequal_group_sizes(self):
        scores = {
            "A": [1.0, 2.0, 3.0],
            "B": [4.0, 5.0],
            "C": [6.0, 7.0, 8.0],
        }
        stat, p = friedman_test(scores)
        assert p == 1.0  # Unequal sizes


# ─────────────────────────────────────────────
# Holm-Bonferroni Correction
# ─────────────────────────────────────────────
class TestHolmBonferroni:
    """Test multiple comparison correction."""

    def test_all_significant(self):
        p_values = [0.001, 0.002, 0.003]
        sig = holm_bonferroni_correction(p_values, alpha=0.05)
        assert all(sig)

    def test_none_significant(self):
        p_values = [0.5, 0.6, 0.7]
        sig = holm_bonferroni_correction(p_values, alpha=0.05)
        assert not any(sig)

    def test_partial_significance(self):
        # 3 tests, alpha=0.05
        # Sorted: 0.01, 0.03, 0.1
        # Check: 0.01 < 0.05/3=0.0167 ✓
        # Check: 0.03 < 0.05/2=0.025  ✗ → stop
        p_values = [0.03, 0.01, 0.1]
        sig = holm_bonferroni_correction(p_values, alpha=0.05)
        assert sig[1] is True   # p=0.01
        assert sig[0] is False  # p=0.03 fails step-down
        assert sig[2] is False  # p=0.1

    def test_empty_input(self):
        sig = holm_bonferroni_correction([], alpha=0.05)
        assert sig == []

    def test_single_test(self):
        sig = holm_bonferroni_correction([0.03], alpha=0.05)
        assert sig == [True]

        sig2 = holm_bonferroni_correction([0.06], alpha=0.05)
        assert sig2 == [False]


# ─────────────────────────────────────────────
# Full Statistical Analysis
# ─────────────────────────────────────────────
class TestFullStatisticalAnalysis:
    """Test the complete analysis pipeline."""

    def _make_ablation_df(self) -> pd.DataFrame:
        """Create synthetic ablation results."""
        np.random.seed(123)
        variants = [
            "LLM-only", "Single-source RAG", "Two-source RAG",
            "Multi-source RAG", "Full framework",
        ]
        questions = [f"q_{i}" for i in range(5)]
        rows = []
        for q in questions:
            for vi, v in enumerate(variants):
                # Each variant gets progressively better scores
                base = 0.2 + vi * 0.15
                rows.append({
                    "question_id": q,
                    "category": "test",
                    "question": f"Question {q}?",
                    "mode": v,
                    "retrieval_precision": min(base + np.random.normal(0, 0.05), 1.0),
                    "source_coverage": min(base + np.random.normal(0, 0.05), 1.0),
                    "citation_accuracy": min(base + np.random.normal(0, 0.05), 1.0),
                    "context_utilization": 1.0 if "Full" in v else 0.0,
                    "latency_seconds": 5.0 + vi * 1.0 + np.random.normal(0, 0.5),
                    "citation_count": int(vi * 2 + np.random.randint(0, 3)),
                })
        return pd.DataFrame(rows)

    def test_report_has_friedman(self):
        df = self._make_ablation_df()
        report = run_full_statistical_analysis(df)
        assert len(report.friedman_tests) > 0

    def test_report_has_pairwise(self):
        df = self._make_ablation_df()
        report = run_full_statistical_analysis(df)
        assert len(report.pairwise_tests) > 0

    def test_report_has_significance_matrix(self):
        df = self._make_ablation_df()
        report = run_full_statistical_analysis(df)
        assert len(report.significance_matrix) > 0
        # Each matrix should be n_variants × n_variants
        for metric, matrix in report.significance_matrix.items():
            assert matrix.shape[0] == matrix.shape[1]

    def test_summary_keys(self):
        df = self._make_ablation_df()
        report = run_full_statistical_analysis(df)
        assert "n_variants" in report.summary
        assert "n_questions" in report.summary
        assert "n_pairwise_tests" in report.summary

    def test_pairwise_to_dataframe(self):
        df = self._make_ablation_df()
        report = run_full_statistical_analysis(df)
        pw_df = pairwise_to_dataframe(report.pairwise_tests)
        assert "variant_a" in pw_df.columns
        assert "p_value" in pw_df.columns
        assert "effect_size" in pw_df.columns
        assert len(pw_df) > 0


# ─────────────────────────────────────────────
# Formatting
# ─────────────────────────────────────────────
class TestFormatSignificance:
    """Test p-value formatting with stars."""

    def test_three_stars(self):
        assert "***" in format_significance(0.0005)

    def test_two_stars(self):
        assert "**" in format_significance(0.005)
        assert "***" not in format_significance(0.005)

    def test_one_star(self):
        assert "*" in format_significance(0.03)
        assert "**" not in format_significance(0.03)

    def test_no_stars(self):
        result = format_significance(0.1)
        assert "*" not in result
