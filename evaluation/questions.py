"""
Benchmark questions for the OCEAN Platform RAG evaluation.

15 questions across 5 categories, each with ground truth annotations
for expected source types, minimum citations, and feature requirements.

Categories:
    1. Single-source (CTD)       — 3 questions
    2. Single-source (Metagenome) — 3 questions
    3. Dual-source (CTD+SST)     — 3 questions
    4. Analysis-dependent        — 3 questions
    5. Reliability-dependent     — 3 questions
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class BenchmarkQuestion:
    """One evaluation question with ground truth annotations."""
    id: str
    category: str
    question: str
    expected_source_types: List[str]
    expected_min_citations: int
    requires_analysis: bool = False
    requires_reliability: bool = False


# ─────────────────────────────────────────────
# Question Categories
# ─────────────────────────────────────────────
QUESTION_CATEGORIES: List[str] = [
    "Single-source (CTD)",
    "Single-source (Metagenome)",
    "Dual-source (CTD+SST)",
    "Analysis-dependent",
    "Reliability-dependent",
]


# ─────────────────────────────────────────────
# Benchmark Questions (15)
# ─────────────────────────────────────────────
BENCHMARK_QUESTIONS: List[BenchmarkQuestion] = [
    # ── Single-source: CTD (3) ──
    BenchmarkQuestion(
        id="ctd_01",
        category="Single-source (CTD)",
        question="What is the temperature and salinity profile at Onagawa Bay in April 2024?",
        expected_source_types=["ctd"],
        expected_min_citations=1,
    ),
    BenchmarkQuestion(
        id="ctd_02",
        category="Single-source (CTD)",
        question="How does dissolved oxygen vary with depth at Onagawa Bay?",
        expected_source_types=["ctd"],
        expected_min_citations=1,
    ),
    BenchmarkQuestion(
        id="ctd_03",
        category="Single-source (CTD)",
        question="What is the chlorophyll-a concentration at the surface in Onagawa Bay during summer?",
        expected_source_types=["ctd"],
        expected_min_citations=1,
    ),

    # ── Single-source: Metagenome (3) ──
    BenchmarkQuestion(
        id="meta_01",
        category="Single-source (Metagenome)",
        question="What are the dominant microbial genera found in Ishinomaki Bay?",
        expected_source_types=["metagenome"],
        expected_min_citations=1,
    ),
    BenchmarkQuestion(
        id="meta_02",
        category="Single-source (Metagenome)",
        question="How does microbial community composition differ between Kraken and MetaEuk classifiers?",
        expected_source_types=["metagenome"],
        expected_min_citations=1,
    ),
    BenchmarkQuestion(
        id="meta_03",
        category="Single-source (Metagenome)",
        question="What metagenome samples are available from Mutsu Bay?",
        expected_source_types=["metagenome"],
        expected_min_citations=1,
    ),

    # ── Dual-source: CTD + SST (3) ──
    BenchmarkQuestion(
        id="dual_01",
        category="Dual-source (CTD+SST)",
        question="How does satellite SST compare to CTD surface temperature measurements at Onagawa Bay?",
        expected_source_types=["ctd", "remote_sensing"],
        expected_min_citations=2,
    ),
    BenchmarkQuestion(
        id="dual_02",
        category="Dual-source (CTD+SST)",
        question="What is the seasonal temperature trend from both CTD profiles and satellite observations?",
        expected_source_types=["ctd", "remote_sensing"],
        expected_min_citations=2,
    ),
    BenchmarkQuestion(
        id="dual_03",
        category="Dual-source (CTD+SST)",
        question="Compare the surface water temperature from in-situ CTD measurements and remote sensing SST data.",
        expected_source_types=["ctd", "remote_sensing"],
        expected_min_citations=2,
    ),

    # ── Analysis-dependent (3) ──
    BenchmarkQuestion(
        id="analysis_01",
        category="Analysis-dependent",
        question="What taxa show significant correlation with temperature changes across all bays?",
        expected_source_types=["metagenome", "ctd"],
        expected_min_citations=2,
        requires_analysis=True,
    ),
    BenchmarkQuestion(
        id="analysis_02",
        category="Analysis-dependent",
        question="How does microbial diversity vary seasonally between Onagawa and Ishinomaki bays?",
        expected_source_types=["metagenome"],
        expected_min_citations=2,
        requires_analysis=True,
    ),
    BenchmarkQuestion(
        id="analysis_03",
        category="Analysis-dependent",
        question="Are there co-occurrence patterns between dinoflagellates and diatoms in the ecosystem?",
        expected_source_types=["metagenome"],
        expected_min_citations=1,
        requires_analysis=True,
    ),

    # ── Reliability-dependent (3) ──
    BenchmarkQuestion(
        id="reliability_01",
        category="Reliability-dependent",
        question="How reliable is our SST data when validated against in-situ CTD measurements?",
        expected_source_types=["ctd", "remote_sensing"],
        expected_min_citations=2,
        requires_reliability=True,
    ),
    BenchmarkQuestion(
        id="reliability_02",
        category="Reliability-dependent",
        question="Are there any anomalous diversity measurements that deviate from environmental predictions?",
        expected_source_types=["metagenome"],
        expected_min_citations=1,
        requires_reliability=True,
    ),
    BenchmarkQuestion(
        id="reliability_03",
        category="Reliability-dependent",
        question="What is the confidence level of cross-source corroboration for our observations?",
        expected_source_types=["ctd", "metagenome"],
        expected_min_citations=1,
        requires_reliability=True,
    ),
]


# ─────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────
def get_question(question_id: str) -> Optional[BenchmarkQuestion]:
    """Look up a benchmark question by its ID."""
    for q in BENCHMARK_QUESTIONS:
        if q.id == question_id:
            return q
    return None


def get_by_category(category: str) -> List[BenchmarkQuestion]:
    """Get all questions in a given category."""
    return [q for q in BENCHMARK_QUESTIONS if q.category == category]


def get_quick_subset() -> List[BenchmarkQuestion]:
    """Get 1 question per category for quick evaluation (5 total)."""
    seen: set[str] = set()
    subset: List[BenchmarkQuestion] = []
    for q in BENCHMARK_QUESTIONS:
        if q.category not in seen:
            subset.append(q)
            seen.add(q.category)
    return subset


def get_question_index() -> Dict[str, BenchmarkQuestion]:
    """Return a dict mapping question ID → BenchmarkQuestion."""
    return {q.id: q for q in BENCHMARK_QUESTIONS}
