"""Tests for evaluation/benchmark.py — citation extraction, metrics, and question definitions."""
from __future__ import annotations

import pandas as pd
import pytest

from evaluation.benchmark import (
    BENCHMARK_QUESTIONS,
    EVAL_MODES,
    EvalResult,
    SYSTEM_VARIANTS,
    SystemVariant,
    _filter_by_source_coverage,
    extract_citations,
    compute_citation_accuracy,
    compute_summary_metrics,
)


# ---------------------------------------------------------------------------
# Benchmark question definitions
# ---------------------------------------------------------------------------
class TestBenchmarkQuestions:
    """Validate the benchmark question set."""

    def test_has_15_questions(self):
        """Benchmark has exactly 15 questions."""
        assert len(BENCHMARK_QUESTIONS) == 15

    def test_five_categories(self):
        """Questions span exactly 5 categories."""
        categories = {q.category for q in BENCHMARK_QUESTIONS}
        assert len(categories) == 5

    def test_three_per_category(self):
        """Each category has exactly 3 questions."""
        from collections import Counter
        counts = Counter(q.category for q in BENCHMARK_QUESTIONS)
        for cat, n in counts.items():
            assert n == 3, f"{cat} has {n} questions, expected 3"

    def test_unique_ids(self):
        """All question IDs are unique."""
        ids = [q.id for q in BENCHMARK_QUESTIONS]
        assert len(ids) == len(set(ids))

    def test_expected_source_types_not_empty(self):
        """Every question has at least one expected source type."""
        for q in BENCHMARK_QUESTIONS:
            assert len(q.expected_source_types) >= 1, f"{q.id} has no expected sources"

    def test_analysis_questions_flagged(self):
        """Analysis-dependent questions have requires_analysis=True."""
        analysis_qs = [q for q in BENCHMARK_QUESTIONS if q.category == "Analysis-dependent"]
        assert len(analysis_qs) == 3
        assert all(q.requires_analysis for q in analysis_qs)

    def test_reliability_questions_flagged(self):
        """Reliability-dependent questions have requires_reliability=True."""
        rel_qs = [q for q in BENCHMARK_QUESTIONS if q.category == "Reliability-dependent"]
        assert len(rel_qs) == 3
        assert all(q.requires_reliability for q in rel_qs)


# ---------------------------------------------------------------------------
# Evaluation modes
# ---------------------------------------------------------------------------
class TestEvalModes:
    """Validate evaluation mode definitions."""

    def test_has_4_modes(self):
        assert len(EVAL_MODES) == 4

    def test_baseline_mode(self):
        baseline = EVAL_MODES[0]
        assert baseline.name == "Baseline"
        assert baseline.inject_analysis is False
        assert baseline.inject_reliability is False

    def test_full_mode(self):
        full = EVAL_MODES[3]
        assert full.name == "Full"
        assert full.inject_analysis is True
        assert full.inject_reliability is True


# ---------------------------------------------------------------------------
# Citation extraction
# ---------------------------------------------------------------------------
class TestExtractCitations:
    """Validate citation regex extraction from LLM responses."""

    def test_doc_citations(self):
        text = "According to [ctd_2024-04-O-s1] and [meta_2024-05-O-s1], the temperature..."
        cited = extract_citations(text)
        assert "ctd_2024-04-O-s1" in cited
        assert "meta_2024-05-O-s1" in cited
        assert len(cited) == 2

    def test_analysis_citations(self):
        text = "Based on [analysis_trends] and [analysis_correlations]..."
        cited = extract_citations(text)
        assert "analysis_trends" in cited
        assert "analysis_correlations" in cited

    def test_reliability_citations(self):
        text = "The [reliability_sst_ctd_validation] shows agreement."
        cited = extract_citations(text)
        assert "reliability_sst_ctd_validation" in cited

    def test_mixed_citations(self):
        text = (
            "Data from [ctd_2024-04-O-s1] shows temperature. "
            "Cross-validation [reliability_corroboration_summary] confirms. "
            "Trends from [analysis_trends] support this."
        )
        cited = extract_citations(text)
        assert len(cited) == 3

    def test_no_citations(self):
        text = "This response has no source citations."
        cited = extract_citations(text)
        assert len(cited) == 0

    def test_sst_citations(self):
        text = "Satellite data [sst_2024-04-10] shows surface temperature."
        cited = extract_citations(text)
        assert "sst_2024-04-10" in cited

    def test_duplicate_citations(self):
        text = "See [ctd_2024-04-O-s1]. Again [ctd_2024-04-O-s1]."
        cited = extract_citations(text)
        assert len(cited) == 2  # Both instances extracted


# ---------------------------------------------------------------------------
# Citation accuracy
# ---------------------------------------------------------------------------
class TestComputeCitationAccuracy:
    """Validate citation accuracy computation."""

    def test_all_valid(self):
        accuracy = compute_citation_accuracy(
            cited_ids=["ctd_a", "ctd_b"],
            retrieved_ids=["ctd_a", "ctd_b", "ctd_c"],
            analysis_ids=[],
            reliability_ids=[],
        )
        assert accuracy == 1.0

    def test_none_valid(self):
        accuracy = compute_citation_accuracy(
            cited_ids=["hallucinated_doc"],
            retrieved_ids=["ctd_a"],
            analysis_ids=[],
            reliability_ids=[],
        )
        assert accuracy == 0.0

    def test_partial_valid(self):
        accuracy = compute_citation_accuracy(
            cited_ids=["ctd_a", "fake_doc"],
            retrieved_ids=["ctd_a"],
            analysis_ids=[],
            reliability_ids=[],
        )
        assert accuracy == 0.5

    def test_analysis_ids_counted(self):
        accuracy = compute_citation_accuracy(
            cited_ids=["analysis_trends"],
            retrieved_ids=[],
            analysis_ids=["analysis_trends"],
            reliability_ids=[],
        )
        assert accuracy == 1.0

    def test_reliability_ids_counted(self):
        accuracy = compute_citation_accuracy(
            cited_ids=["reliability_sst_ctd_validation"],
            retrieved_ids=[],
            analysis_ids=[],
            reliability_ids=["reliability_sst_ctd_validation"],
        )
        assert accuracy == 1.0

    def test_empty_citations(self):
        accuracy = compute_citation_accuracy([], ["ctd_a"], [], [])
        assert accuracy == 0.0


# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
class TestComputeSummaryMetrics:
    """Validate metric aggregation from results DataFrame."""

    def _make_results(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"question_id": "q1", "category": "Cat A", "mode": "Baseline",
             "retrieval_precision": 0.8, "source_coverage": 1.0,
             "citation_count": 3, "citation_accuracy": 1.0,
             "context_utilization": 0.0, "latency_seconds": 5.0},
            {"question_id": "q1", "category": "Cat A", "mode": "Full",
             "retrieval_precision": 0.9, "source_coverage": 1.0,
             "citation_count": 5, "citation_accuracy": 0.8,
             "context_utilization": 1.0, "latency_seconds": 7.0},
            {"question_id": "q2", "category": "Cat B", "mode": "Baseline",
             "retrieval_precision": 0.6, "source_coverage": 0.5,
             "citation_count": 2, "citation_accuracy": 1.0,
             "context_utilization": 0.0, "latency_seconds": 4.0},
            {"question_id": "q2", "category": "Cat B", "mode": "Full",
             "retrieval_precision": 0.7, "source_coverage": 1.0,
             "citation_count": 4, "citation_accuracy": 0.75,
             "context_utilization": 0.5, "latency_seconds": 6.0},
        ])

    def test_by_mode_keys(self):
        summaries = compute_summary_metrics(self._make_results())
        assert "by_mode" in summaries
        assert "by_category" in summaries
        assert "by_mode_category" in summaries

    def test_by_mode_values(self):
        summaries = compute_summary_metrics(self._make_results())
        by_mode = summaries["by_mode"]
        assert "Baseline" in by_mode.index
        assert "Full" in by_mode.index
        # Full mode should have higher context utilization than Baseline
        assert by_mode.loc["Full", "context_utilization"] > by_mode.loc["Baseline", "context_utilization"]

    def test_by_category_values(self):
        summaries = compute_summary_metrics(self._make_results())
        by_cat = summaries["by_category"]
        assert "Cat A" in by_cat.index
        assert "Cat B" in by_cat.index

# ---------------------------------------------------------------------------
# System Variants (ablation study)
# ---------------------------------------------------------------------------
class TestSystemVariants:
    """Validate the 7 ablation study system variants."""

    def test_has_7_variants(self):
        assert len(SYSTEM_VARIANTS) == 7

    def test_variant_names(self):
        names = [v.name for v in SYSTEM_VARIANTS]
        assert "LLM-only" in names
        assert "Single-source RAG" in names
        assert "Two-source RAG" in names
        assert "Multi-source RAG" in names
        assert "Multi-source + Analysis" in names
        assert "Multi-source + Reliability" in names
        assert "Full framework" in names

    def test_unique_names(self):
        names = [v.name for v in SYSTEM_VARIANTS]
        assert len(names) == len(set(names))

    def test_llm_only_variant(self):
        v = SYSTEM_VARIANTS[0]
        assert v.name == "LLM-only"
        assert v.source_coverage == 0
        assert v.inject_analysis is False
        assert v.inject_reliability is False

    def test_full_variant(self):
        v = SYSTEM_VARIANTS[-1]
        assert v.name == "Full framework"
        assert v.source_coverage == 3
        assert v.inject_analysis is True
        assert v.inject_reliability is True

    def test_source_coverage_progression(self):
        """First 4 variants increase source coverage 0→1→2→3."""
        coverages = [v.source_coverage for v in SYSTEM_VARIANTS[:4]]
        assert coverages == [0, 1, 2, 3]

    def test_injection_variants(self):
        """Variants 4-6 all have source_coverage=3 with different injections."""
        for v in SYSTEM_VARIANTS[3:]:
            assert v.source_coverage == 3

    def test_all_have_descriptions(self):
        for v in SYSTEM_VARIANTS:
            assert v.description, f"{v.name} has no description"

    def test_backward_compatible_eval_modes(self):
        """Original EVAL_MODES still have 4 entries."""
        assert len(EVAL_MODES) == 4


# ---------------------------------------------------------------------------
# Source coverage filtering
# ---------------------------------------------------------------------------
class TestSourceCoverageFiltering:
    """Validate _filter_by_source_coverage logic."""

    def _make_question(self, expected_types):
        from evaluation.benchmark import BenchmarkQuestion
        return BenchmarkQuestion(
            id="test_q",
            question="Test?",
            category="test",
            expected_source_types=expected_types,
            expected_min_citations=1,
            requires_analysis=False,
            requires_reliability=False,
        )

    def _make_docs(self):
        return [
            {"doc_id": "ctd_1", "source_type": "ctd"},
            {"doc_id": "ctd_2", "source_type": "ctd"},
            {"doc_id": "meta_1", "source_type": "metagenome"},
            {"doc_id": "sst_1", "source_type": "remote_sensing"},
            {"doc_id": "sst_2", "source_type": "remote_sensing"},
        ]

    def test_coverage_0_returns_empty(self):
        q = self._make_question(["ctd"])
        result = _filter_by_source_coverage(self._make_docs(), q, 0)
        assert result == []

    def test_coverage_1_single_type(self):
        q = self._make_question(["ctd", "remote_sensing"])
        result = _filter_by_source_coverage(self._make_docs(), q, 1)
        assert all(r["source_type"] == "ctd" for r in result)
        assert len(result) == 2

    def test_coverage_2_two_types(self):
        q = self._make_question(["ctd", "remote_sensing"])
        result = _filter_by_source_coverage(self._make_docs(), q, 2)
        types = {r["source_type"] for r in result}
        assert types == {"ctd", "remote_sensing"}

    def test_coverage_2_with_single_expected(self):
        """If question expects 1 type, coverage=2 adds one more."""
        q = self._make_question(["ctd"])
        result = _filter_by_source_coverage(self._make_docs(), q, 2)
        types = {r["source_type"] for r in result}
        assert len(types) == 2
        assert "ctd" in types

    def test_coverage_3_returns_all(self):
        q = self._make_question(["ctd"])
        docs = self._make_docs()
        result = _filter_by_source_coverage(docs, q, 3)
        assert len(result) == len(docs)

    def test_coverage_above_3_returns_all(self):
        q = self._make_question(["ctd"])
        docs = self._make_docs()
        result = _filter_by_source_coverage(docs, q, 5)
        assert len(result) == len(docs)
