"""
Answer quality metrics for the evaluation benchmark.

Computes metrics that go beyond retrieval/citation to measure the
actual quality of generated answers:

1. ROUGE-L  — n-gram overlap with expert reference answers
2. Semantic Similarity — embedding cosine similarity (via Ollama)
3. Faithfulness — fraction of claims grounded in provided context
4. Answer Completeness — fraction of key facts present in the response
5. LLM-as-Judge — structured 4-dimension scoring (correctness,
   completeness, citation quality, coherence)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, List

import numpy as np
import requests

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────
@dataclass
class JudgeScores:
    """LLM-as-judge evaluation scores (1-5 each)."""
    correctness: int = 0
    completeness: int = 0
    citation_quality: int = 0
    coherence: int = 0

    @property
    def mean(self) -> float:
        scores = [self.correctness, self.completeness,
                  self.citation_quality, self.coherence]
        valid = [s for s in scores if s > 0]
        return float(np.mean(valid)) if valid else 0.0


@dataclass
class QualityScores:
    """All quality metrics for one evaluation."""
    question_id: str
    variant: str
    rouge_l: float = 0.0
    semantic_similarity: float = 0.0
    faithfulness: float = 0.0
    answer_completeness: float = 0.0
    judge_correctness: int = 0
    judge_completeness: int = 0
    judge_citation_quality: int = 0
    judge_coherence: int = 0
    judge_mean: float = 0.0


# ─────────────────────────────────────────────
# 1. ROUGE-L
# ─────────────────────────────────────────────
def compute_rouge_l(generated: str, reference: str) -> float:
    """
    Compute ROUGE-L F-measure between generated and reference text.

    Uses the rouge-score library for LCS-based computation.
    Falls back to a simple implementation if the library is unavailable.
    """
    if not generated.strip() or not reference.strip():
        return 0.0

    try:
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
        scores = scorer.score(reference, generated)
        return round(scores["rougeL"].fmeasure, 4)
    except ImportError:
        logger.warning("rouge-score not installed; using simple LCS ROUGE-L")
        return _simple_rouge_l(generated, reference)


def _simple_rouge_l(generated: str, reference: str) -> float:
    """Fallback ROUGE-L using longest common subsequence."""
    gen_tokens = generated.lower().split()
    ref_tokens = reference.lower().split()

    if not gen_tokens or not ref_tokens:
        return 0.0

    # LCS via dynamic programming
    m, n = len(ref_tokens), len(gen_tokens)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_tokens[i - 1] == gen_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs_len = dp[m][n]
    precision = lcs_len / n if n > 0 else 0.0
    recall = lcs_len / m if m > 0 else 0.0
    if precision + recall == 0:
        return 0.0
    f1 = 2 * precision * recall / (precision + recall)
    return round(f1, 4)


# ─────────────────────────────────────────────
# 2. Semantic Similarity
# ─────────────────────────────────────────────
def compute_semantic_similarity(
    generated: str,
    reference: str,
    *,
    ollama_url: str = "http://localhost:11434",
    model: str = "nomic-embed-text",
) -> float:
    """
    Cosine similarity between embeddings of generated and reference texts.

    Uses Ollama's embedding endpoint with nomic-embed-text.
    """
    if not generated.strip() or not reference.strip():
        return 0.0

    try:
        def _embed(text: str) -> np.ndarray:
            resp = requests.post(
                f"{ollama_url}/api/embed",
                json={"model": model, "input": text},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            emb = data.get("embeddings", [data.get("embedding", [])])[0]
            return np.array(emb, dtype="float32")

        emb_gen = _embed(generated[:2000])  # Truncate for embedding
        emb_ref = _embed(reference[:2000])

        # Cosine similarity
        dot = np.dot(emb_gen, emb_ref)
        norm = np.linalg.norm(emb_gen) * np.linalg.norm(emb_ref)
        if norm == 0:
            return 0.0
        return round(float(dot / norm), 4)

    except Exception as e:
        logger.warning("Semantic similarity failed: %s", e)
        return 0.0


# ─────────────────────────────────────────────
# 3. Faithfulness
# ─────────────────────────────────────────────
def compute_faithfulness(
    response: str,
    context_docs: List[dict],
) -> float:
    """
    Estimate faithfulness: fraction of response sentences that are
    grounded in the provided context.

    Uses simple sentence-level overlap heuristic: a sentence is
    considered grounded if it shares significant keyword overlap
    with the context.
    """
    if not response.strip():
        return 0.0

    # Build context corpus
    context_text = " ".join(
        d.get("text", "") for d in context_docs
    ).lower()
    context_words = set(re.findall(r"[a-z0-9]+", context_text))

    if not context_words:
        return 0.0

    # Split response into sentences
    sentences = re.split(r"[.!?]+", response)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    if not sentences:
        return 0.0

    # Common words to exclude from overlap
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "this", "that", "these", "those", "it", "its", "of", "in",
        "on", "at", "to", "for", "with", "by", "from", "as", "and",
        "or", "but", "not", "no", "if", "than", "then", "so", "also",
        "which", "who", "whom", "what", "where", "when", "how", "all",
        "each", "every", "both", "few", "more", "most", "some", "any",
        "other", "into", "about", "between", "through", "during",
        "before", "after", "above", "below", "such", "their", "there",
    }

    grounded = 0
    for sent in sentences:
        sent_words = set(re.findall(r"[a-z0-9]+", sent.lower()))
        sent_words -= stopwords

        if not sent_words:
            grounded += 1  # Trivial sentence, count as grounded
            continue

        overlap = sent_words & context_words
        overlap_ratio = len(overlap) / len(sent_words)

        # Sentence is grounded if >40% of its content words appear in context
        if overlap_ratio > 0.4:
            grounded += 1

    return round(grounded / len(sentences), 4)


# ─────────────────────────────────────────────
# 4. Answer Completeness
# ─────────────────────────────────────────────
def compute_answer_completeness(
    response: str,
    key_facts: List[str],
) -> float:
    """
    Fraction of expected key facts that appear in the response.

    Key facts are case-insensitive substrings that the response
    should mention for a complete answer.
    """
    if not key_facts:
        return 1.0
    if not response.strip():
        return 0.0

    response_lower = response.lower()
    found = sum(1 for fact in key_facts if fact.lower() in response_lower)
    return round(found / len(key_facts), 4)


# ─────────────────────────────────────────────
# 5. LLM-as-Judge
# ─────────────────────────────────────────────
_JUDGE_PROMPT = """You are an expert evaluator for a marine science RAG system.
Rate the following response on 4 dimensions using a 1-5 scale.

QUESTION:
{question}

REFERENCE ANSWER:
{reference}

CONTEXT PROVIDED TO THE SYSTEM:
{context}

SYSTEM RESPONSE:
{response}

Rate each dimension (1=very poor, 2=poor, 3=acceptable, 4=good, 5=excellent):

1. CORRECTNESS: Are the factual claims in the response accurate based on the context and reference?
2. COMPLETENESS: Does the response address all aspects of the question?
3. CITATION_QUALITY: Are citations present, accurate (matching provided context IDs), and well-integrated?
4. COHERENCE: Is the response well-organized, clear, and logically structured?

Respond ONLY with a JSON object in this exact format (no other text):
{{"correctness": N, "completeness": N, "citation_quality": N, "coherence": N}}
"""


def llm_judge_score(
    question: str,
    response: str,
    reference: str,
    context: str,
    *,
    model: str = "qwen2.5:14b-instruct",
    ollama_url: str = "http://localhost:11434",
    temperature: float = 0.0,
    num_ctx: int = 8192,
) -> JudgeScores:
    """
    Use an LLM to rate a response on 4 quality dimensions.

    Returns JudgeScores with integer ratings 1-5 for each dimension.
    """
    prompt = _JUDGE_PROMPT.format(
        question=question,
        reference=reference[:1500],
        context=context[:3000],
        response=response[:2000],
    )

    try:
        resp = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_ctx": num_ctx,
                },
            },
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]

        # Parse JSON from response
        scores = _parse_judge_json(content)
        return scores

    except Exception as e:
        logger.warning("LLM judge failed: %s", e)
        return JudgeScores()


def _parse_judge_json(text: str) -> JudgeScores:
    """Extract judge scores from LLM response text."""
    # Try direct JSON parse
    try:
        data = json.loads(text.strip())
        return JudgeScores(
            correctness=_clamp(data.get("correctness", 0)),
            completeness=_clamp(data.get("completeness", 0)),
            citation_quality=_clamp(data.get("citation_quality", 0)),
            coherence=_clamp(data.get("coherence", 0)),
        )
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from surrounding text
    json_match = re.search(r"\{[^{}]+\}", text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return JudgeScores(
                correctness=_clamp(data.get("correctness", 0)),
                completeness=_clamp(data.get("completeness", 0)),
                citation_quality=_clamp(data.get("citation_quality", 0)),
                coherence=_clamp(data.get("coherence", 0)),
            )
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse judge response: %s", text[:200])
    return JudgeScores()


def _clamp(val: Any, lo: int = 0, hi: int = 5) -> int:
    """Clamp a value to an integer in [lo, hi]."""
    try:
        return max(lo, min(hi, int(val)))
    except (ValueError, TypeError):
        return 0


# ─────────────────────────────────────────────
# Batch scoring
# ─────────────────────────────────────────────
def score_single_response(
    question_id: str,
    variant_name: str,
    question_text: str,
    response: str,
    context_docs: List[dict],
    reference_text: str,
    key_facts: List[str],
    *,
    ollama_url: str = "http://localhost:11434",
    embedding_model: str = "nomic-embed-text",
    run_judge: bool = False,
    judge_model: str = "qwen2.5:14b-instruct",
) -> QualityScores:
    """
    Compute all quality metrics for a single response.

    Args:
        question_id: Benchmark question ID.
        variant_name: System variant name.
        question_text: The original question.
        response: The generated response.
        context_docs: Retrieved documents provided as context.
        reference_text: Expert reference answer.
        key_facts: Key facts for completeness checking.
        ollama_url: Ollama API URL.
        embedding_model: Model for semantic similarity.
        run_judge: Whether to run LLM-as-judge scoring.
        judge_model: Model for LLM-as-judge.

    Returns:
        QualityScores with all computed metrics.
    """
    scores = QualityScores(
        question_id=question_id,
        variant=variant_name,
    )

    # ROUGE-L
    scores.rouge_l = compute_rouge_l(response, reference_text)

    # Semantic similarity
    scores.semantic_similarity = compute_semantic_similarity(
        response, reference_text,
        ollama_url=ollama_url, model=embedding_model,
    )

    # Faithfulness
    scores.faithfulness = compute_faithfulness(response, context_docs)

    # Answer completeness
    scores.answer_completeness = compute_answer_completeness(
        response, key_facts,
    )

    # LLM-as-judge (optional, expensive)
    if run_judge:
        context_text = "\n".join(
            f"[{d.get('doc_id', 'unknown')}] {d.get('text', '')}"
            for d in context_docs
        )
        judge = llm_judge_score(
            question=question_text,
            response=response,
            reference=reference_text,
            context=context_text,
            model=judge_model,
            ollama_url=ollama_url,
        )
        scores.judge_correctness = judge.correctness
        scores.judge_completeness = judge.completeness
        scores.judge_citation_quality = judge.citation_quality
        scores.judge_coherence = judge.coherence
        scores.judge_mean = judge.mean

    return scores
