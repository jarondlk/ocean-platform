"""Tests for evaluation/questions.py — standalone benchmark questions module."""
from __future__ import annotations


from evaluation.questions import (
    BENCHMARK_QUESTIONS,
    QUESTION_CATEGORIES,
    BenchmarkQuestion,
    get_by_category,
    get_question,
    get_question_index,
    get_quick_subset,
)
from evaluation.reference_answers import REFERENCE_ANSWERS


# ─────────────────────────────────────────────
# Question definitions
# ─────────────────────────────────────────────
class TestBenchmarkQuestions:
    """Validate question definitions."""

    def test_has_15_questions(self):
        assert len(BENCHMARK_QUESTIONS) == 15

    def test_unique_ids(self):
        ids = [q.id for q in BENCHMARK_QUESTIONS]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[i for i in ids if ids.count(i) > 1]}"

    def test_has_5_categories(self):
        categories = {q.category for q in BENCHMARK_QUESTIONS}
        assert len(categories) == 5

    def test_3_questions_per_category(self):
        from collections import Counter
        counts = Counter(q.category for q in BENCHMARK_QUESTIONS)
        for cat, count in counts.items():
            assert count == 3, f"Category '{cat}' has {count} questions, expected 3"

    def test_all_have_expected_source_types(self):
        for q in BENCHMARK_QUESTIONS:
            assert len(q.expected_source_types) > 0, f"{q.id} has no expected source types"

    def test_all_have_positive_min_citations(self):
        for q in BENCHMARK_QUESTIONS:
            assert q.expected_min_citations >= 1, f"{q.id} has min_citations < 1"

    def test_analysis_questions_require_analysis(self):
        for q in BENCHMARK_QUESTIONS:
            if "analysis" in q.id:
                assert q.requires_analysis, f"{q.id} should require analysis"

    def test_reliability_questions_require_reliability(self):
        for q in BENCHMARK_QUESTIONS:
            if "reliability" in q.id:
                assert q.requires_reliability, f"{q.id} should require reliability"

    def test_ctd_questions_expect_ctd(self):
        for q in BENCHMARK_QUESTIONS:
            if q.id.startswith("ctd_"):
                assert "ctd" in q.expected_source_types

    def test_meta_questions_expect_metagenome(self):
        for q in BENCHMARK_QUESTIONS:
            if q.id.startswith("meta_"):
                assert "metagenome" in q.expected_source_types

    def test_dual_questions_expect_both(self):
        for q in BENCHMARK_QUESTIONS:
            if q.id.startswith("dual_"):
                assert "ctd" in q.expected_source_types
                assert "remote_sensing" in q.expected_source_types


# ─────────────────────────────────────────────
# Categories
# ─────────────────────────────────────────────
class TestQuestionCategories:
    """Validate category constant."""

    def test_has_5_categories(self):
        assert len(QUESTION_CATEGORIES) == 5

    def test_matches_questions(self):
        q_cats = {q.category for q in BENCHMARK_QUESTIONS}
        assert q_cats == set(QUESTION_CATEGORIES)


# ─────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────
class TestGetQuestion:
    """Test single question lookup."""

    def test_existing_id(self):
        q = get_question("ctd_01")
        assert q is not None
        assert q.id == "ctd_01"
        assert "temperature" in q.question.lower()

    def test_missing_id(self):
        assert get_question("nonexistent_99") is None

    def test_all_ids_resolvable(self):
        for q in BENCHMARK_QUESTIONS:
            assert get_question(q.id) is q


class TestGetByCategory:
    """Test category filter."""

    def test_ctd_category(self):
        qs = get_by_category("Single-source (CTD)")
        assert len(qs) == 3
        assert all(q.id.startswith("ctd_") for q in qs)

    def test_empty_for_unknown(self):
        assert get_by_category("Nonexistent") == []


class TestGetQuickSubset:
    """Test quick evaluation subset."""

    def test_returns_5_questions(self):
        subset = get_quick_subset()
        assert len(subset) == 5

    def test_one_per_category(self):
        subset = get_quick_subset()
        cats = [q.category for q in subset]
        assert len(cats) == len(set(cats))

    def test_covers_all_categories(self):
        subset = get_quick_subset()
        cats = {q.category for q in subset}
        assert cats == set(QUESTION_CATEGORIES)


class TestGetQuestionIndex:
    """Test index dictionary."""

    def test_returns_dict(self):
        idx = get_question_index()
        assert isinstance(idx, dict)
        assert len(idx) == 15

    def test_keys_are_ids(self):
        idx = get_question_index()
        for q in BENCHMARK_QUESTIONS:
            assert q.id in idx
            assert idx[q.id] is q


# ─────────────────────────────────────────────
# Reference answer coverage
# ─────────────────────────────────────────────
class TestReferenceAnswerCoverage:
    """Every benchmark question should have a matching reference answer."""

    def test_all_questions_have_references(self):
        missing = []
        for q in BENCHMARK_QUESTIONS:
            if q.id not in REFERENCE_ANSWERS:
                missing.append(q.id)
        assert not missing, f"Questions without reference answers: {missing}"

    def test_all_references_have_questions(self):
        q_ids = {q.id for q in BENCHMARK_QUESTIONS}
        orphan = [rid for rid in REFERENCE_ANSWERS if rid not in q_ids]
        assert not orphan, f"Reference answers without questions: {orphan}"


# ─────────────────────────────────────────────
# Backward compatibility
# ─────────────────────────────────────────────
class TestBackwardCompatibility:
    """Verify imports from benchmark.py still work."""

    def test_import_from_benchmark(self):
        from evaluation.benchmark import BenchmarkQuestion as BQ
        from evaluation.benchmark import BENCHMARK_QUESTIONS as BQs
        assert BQ is BenchmarkQuestion
        assert BQs is BENCHMARK_QUESTIONS

    def test_import_helpers_from_benchmark(self):
        from evaluation.benchmark import get_question, get_by_category, get_quick_subset
        assert callable(get_question)
        assert callable(get_by_category)
        assert callable(get_quick_subset)
