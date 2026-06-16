"""Tests for evaluation/quality_metrics.py — answer quality scoring."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from evaluation.quality_metrics import (
    JudgeScores,
    QualityScores,
    _parse_judge_json,
    _simple_rouge_l,
    compute_answer_completeness,
    compute_faithfulness,
    compute_rouge_l,
    compute_semantic_similarity,
)


# ─────────────────────────────────────────────
# ROUGE-L
# ─────────────────────────────────────────────
class TestRougeL:
    """Test ROUGE-L computation."""

    def test_identical_texts(self):
        text = "The temperature at Onagawa Bay was 15.5 degrees."
        score = compute_rouge_l(text, text)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_completely_different(self):
        gen = "Alpha beta gamma delta"
        ref = "One two three four five six seven"
        score = compute_rouge_l(gen, ref)
        assert score < 0.1

    def test_partial_overlap(self):
        gen = "Temperature was 15 degrees at Onagawa Bay station s1."
        ref = "Temperature was 14.89 degrees at Onagawa Bay in April 2024."
        score = compute_rouge_l(gen, ref)
        assert 0.2 < score < 0.9

    def test_empty_generated(self):
        score = compute_rouge_l("", "Some reference text")
        assert score == 0.0

    def test_empty_reference(self):
        score = compute_rouge_l("Some generated text", "")
        assert score == 0.0

    def test_both_empty(self):
        score = compute_rouge_l("", "")
        assert score == 0.0


class TestSimpleRougeL:
    """Test fallback LCS-based ROUGE-L."""

    def test_identical(self):
        text = "the quick brown fox"
        score = _simple_rouge_l(text, text)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_no_overlap(self):
        score = _simple_rouge_l("alpha beta", "gamma delta epsilon")
        assert score == 0.0

    def test_partial(self):
        gen = "the quick brown fox jumps"
        ref = "the slow brown fox runs"
        score = _simple_rouge_l(gen, ref)
        assert 0.3 < score < 0.9

    def test_empty(self):
        assert _simple_rouge_l("", "abc") == 0.0
        assert _simple_rouge_l("abc", "") == 0.0


# ─────────────────────────────────────────────
# Semantic Similarity
# ─────────────────────────────────────────────
class TestSemanticSimilarity:
    """Test embedding-based similarity (with mocked Ollama)."""

    def test_empty_input_returns_zero(self):
        score = compute_semantic_similarity("", "some text")
        assert score == 0.0

    def test_empty_reference_returns_zero(self):
        score = compute_semantic_similarity("some text", "")
        assert score == 0.0


# ─────────────────────────────────────────────
# Faithfulness
# ─────────────────────────────────────────────
class TestFaithfulness:
    """Test faithfulness scoring."""

    def test_fully_grounded(self):
        response = (
            "The temperature was 15.5 degrees celsius. "
            "The salinity was 33.89 PSU at Onagawa Bay."
        )
        context = [
            {"text": "Temperature 15.5 degrees celsius measured at the station."},
            {"text": "Salinity reading of 33.89 PSU at Onagawa Bay."},
        ]
        score = compute_faithfulness(response, context)
        assert score > 0.5

    def test_no_context(self):
        response = "Temperature was 15 degrees."
        score = compute_faithfulness(response, [])
        assert score == 0.0

    def test_empty_response(self):
        score = compute_faithfulness("", [{"text": "some context"}])
        assert score == 0.0

    def test_hallucinated_content(self):
        response = (
            "Xenomorphic crystalline formations were detected. "
            "Quantum flux variations exceeded the baseline parameters."
        )
        context = [
            {"text": "Temperature was 15 degrees at station s1."},
        ]
        score = compute_faithfulness(response, context)
        # Hallucinated content should have low overlap
        assert score < 0.5

    def test_partially_grounded(self):
        response = (
            "The temperature was 15 degrees at Onagawa Bay. "
            "This indicates quantum crystallographic anomalies in the sediment."
        )
        context = [
            {"text": "Temperature measured 15 degrees at Onagawa Bay station s1."},
        ]
        score = compute_faithfulness(response, context)
        assert 0.2 <= score <= 0.8


# ─────────────────────────────────────────────
# Answer Completeness
# ─────────────────────────────────────────────
class TestAnswerCompleteness:
    """Test key-fact completeness checking."""

    def test_all_facts_present(self):
        response = "Temperature was 15°C, salinity was 33 PSU at Onagawa Bay."
        facts = ["temperature", "salinity", "Onagawa"]
        score = compute_answer_completeness(response, facts)
        assert score == pytest.approx(1.0)

    def test_no_facts_present(self):
        response = "The weather was nice today."
        facts = ["temperature", "salinity", "Onagawa"]
        score = compute_answer_completeness(response, facts)
        assert score == 0.0

    def test_partial_facts(self):
        response = "Temperature was 15°C in the bay."
        facts = ["temperature", "salinity", "Onagawa", "dissolved oxygen"]
        score = compute_answer_completeness(response, facts)
        assert score == pytest.approx(0.25)

    def test_empty_facts(self):
        score = compute_answer_completeness("Any response", [])
        assert score == 1.0

    def test_empty_response(self):
        score = compute_answer_completeness("", ["temperature"])
        assert score == 0.0

    def test_case_insensitive(self):
        response = "TEMPERATURE was measured at ONAGAWA Bay."
        facts = ["temperature", "Onagawa"]
        score = compute_answer_completeness(response, facts)
        assert score == pytest.approx(1.0)


# ─────────────────────────────────────────────
# LLM Judge JSON Parsing
# ─────────────────────────────────────────────
class TestJudgeParsing:
    """Test JSON extraction from LLM judge responses."""

    def test_clean_json(self):
        text = '{"correctness": 4, "completeness": 3, "citation_quality": 5, "coherence": 4}'
        scores = _parse_judge_json(text)
        assert scores.correctness == 4
        assert scores.completeness == 3
        assert scores.citation_quality == 5
        assert scores.coherence == 4

    def test_json_with_surrounding_text(self):
        text = 'Here are the scores:\n{"correctness": 3, "completeness": 2, "citation_quality": 4, "coherence": 3}\nDone.'
        scores = _parse_judge_json(text)
        assert scores.correctness == 3
        assert scores.citation_quality == 4

    def test_invalid_json(self):
        text = "This is not JSON at all."
        scores = _parse_judge_json(text)
        assert scores.correctness == 0
        assert scores.mean == 0.0

    def test_partial_json(self):
        text = '{"correctness": 4, "completeness": 3}'
        scores = _parse_judge_json(text)
        assert scores.correctness == 4
        assert scores.completeness == 3
        assert scores.citation_quality == 0

    def test_out_of_range_clamped(self):
        text = '{"correctness": 10, "completeness": -1, "citation_quality": 3, "coherence": 4}'
        scores = _parse_judge_json(text)
        assert scores.correctness == 5  # clamped to max
        assert scores.completeness == 0  # clamped to min


# ─────────────────────────────────────────────
# JudgeScores
# ─────────────────────────────────────────────
class TestJudgeScores:
    """Test JudgeScores dataclass."""

    def test_mean_calculation(self):
        scores = JudgeScores(correctness=4, completeness=3, citation_quality=5, coherence=4)
        assert scores.mean == pytest.approx(4.0)

    def test_mean_with_zeros(self):
        scores = JudgeScores(correctness=4, completeness=0, citation_quality=0, coherence=4)
        assert scores.mean == pytest.approx(4.0)  # Only non-zero counted

    def test_all_zeros(self):
        scores = JudgeScores()
        assert scores.mean == 0.0
