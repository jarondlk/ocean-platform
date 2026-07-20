"""
Unified query orchestrator.

Auto-detects whether PostgreSQL is available and falls back to the
local retriever if not.  Either way, the same provenance-aware prompt
is built for the LLM.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger(__name__)

ANALYSIS_CONTEXT_HEADER = "\n=== PRE-COMPUTED ANALYSES ===\n"
RELIABILITY_CONTEXT_HEADER = "\n=== RELIABILITY ENSURANCE ===\n"

ANALYSIS_KEYWORDS = {
    "trend", "trends", "seasonal", "monthly", "correlation", "correlate",
    "relationship", "diversity", "richness", "evenness", "compare",
    "comparison", "between", "across", "pattern", "change", "over time",
    "stratification", "co-occurrence", "cooccurrence", "community",
    "structure", "composition", "temperature", "salinity", "chlorophyll",
    "bloom", "dinoflagellate", "diatom", "ecosystem", "bay",
}

RELIABILITY_KEYWORDS = {
    "reliable", "reliability", "confidence", "trust", "validate",
    "validation", "corroborate", "corroboration", "agree", "agreement",
    "consistent", "consistency", "gap", "gaps", "anomaly", "anomalies",
    "outlier", "outliers", "interpolate", "predict", "verify",
    "cross-source", "cross", "support", "confirm", "temperature",
    "sst", "ctd", "diversity", "shannon", "compare", "comparison",
    "trend", "seasonal",
}


def _pg_available() -> bool:
    """Check if PostgreSQL is reachable."""
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def retrieve(
    query: str,
    *,
    k: int = 8,
    source_type: Optional[str] = None,
    bay: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    vector_weight: float = 0.6,
    fts_weight: float = 0.4,
    rrf_k: int = 60,
) -> List[dict]:
    """
    Retrieve relevant documents using the best available backend.
    """
    if _pg_available():
        logger.info("Using PostgreSQL hybrid retriever")
        from retrieval.hybrid_retriever import hybrid_search
        results = hybrid_search(
            query, k=k, source_type=source_type, bay=bay,
            time_from=time_from, time_to=time_to,
            vector_weight=vector_weight, fts_weight=fts_weight,
            rrf_k=rrf_k,
        )
        return [
            {
                "doc_id": r.doc_id,
                "source_type": r.source_type,
                "sample_id": r.sample_id,
                "event_id": r.event_id,
                "time": r.time,
                "bay": r.bay,
                "station": r.station,
                "title": r.title,
                "text": r.text,
                "score": r.score,
                "rank_sources": dict(r.rank_sources),
            }
            for r in results
        ]
    else:
        logger.info("PostgreSQL not available – using local retriever")
        from retrieval.local_retriever import get_local_retriever
        retriever = get_local_retriever()
        return retriever.search(
            query, k=k, source_type=source_type, bay=bay,
            time_from=time_from, time_to=time_to,
        )


def _query_matches_context(query: str, keywords: set[str]) -> bool:
    query_lower = query.lower()
    query_terms = set(query_lower.split())
    return bool(query_terms.intersection(keywords) or any(" " in keyword and keyword in query_lower for keyword in keywords))


def _read_context_documents(path) -> List[dict]:
    if not path.exists():
        return []
    documents: List[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                documents.append(json.loads(line))
    return documents


def analysis_context_documents(query: str) -> List[dict]:
    """Return analysis context documents that will be injected for a query."""
    if not _query_matches_context(query, ANALYSIS_KEYWORDS):
        return []
    return _read_context_documents(config.ANALYSIS_DIR / "analysis_documents.jsonl")


def reliability_context_documents(query: str) -> List[dict]:
    """Return reliability context documents that will be injected for a query."""
    if not _query_matches_context(query, RELIABILITY_KEYWORDS):
        return []
    return _read_context_documents(config.RELIABILITY_DIR / "reliability_documents.jsonl")


def _format_analysis_context(documents: List[dict]) -> str:
    if not documents:
        return ""
    text = ANALYSIS_CONTEXT_HEADER
    text += "(These are precomputed ecological relationships for supplementary context.)\n"
    for doc in documents:
        text += f"\n[{doc['id']}] ({doc.get('analysis_type', 'analysis')})\n{doc['text']}\n"
    return text


def _format_reliability_context(documents: List[dict]) -> str:
    if not documents:
        return ""
    text = RELIABILITY_CONTEXT_HEADER
    text += "(Cross-source validation and corroboration results.)\n"
    for doc in documents:
        text += f"\n[{doc['id']}] ({doc.get('analysis_type', 'reliability')})\n{doc['text']}\n"
    return text


def _load_analysis_context(query: str) -> str:
    """
    Load precomputed analysis documents relevant to the query.
    These are injected as supplementary context in addition to retrieved evidence.
    """
    return _format_analysis_context(analysis_context_documents(query))


def _load_reliability_context(query: str) -> str:
    """
    Load reliability ensurance documents relevant to the query.
    These provide cross-source validation and corroboration context.
    """
    return _format_reliability_context(reliability_context_documents(query))


def build_prompt_with_context(
    query: str,
    results: List[dict],
    *,
    inject_analysis: bool = True,
    inject_reliability: bool = True,
) -> tuple[str, Dict[str, List[dict]]]:
    """
    Build the prompt and return the structured supplementary context used.
    """
    context = {
        "analysis": analysis_context_documents(query) if inject_analysis else [],
        "reliability": reliability_context_documents(query) if inject_reliability else [],
    }
    return _build_prompt_from_context(query, results, context), context


def _build_prompt_from_context(
    query: str,
    results: List[dict],
    context: Dict[str, List[dict]],
) -> str:
    """
    Build the provenance-aware system prompt with evidence, analysis,
    and reliability context.
    """
    system = """You are an expert marine science assistant for the Onagawa Bay monitoring programme (Japan).
You analyze CTD water profiles, metagenome taxonomic data, and satellite SST observations.

RULES:
1. ONLY use the evidence provided below. Do not hallucinate.
2. ALWAYS cite sources using [doc_id] notation.
3. Distinguish data types: CTD measurements, metagenome taxonomy, satellite SST.
4. State data gaps explicitly. Report values with units.
5. When comparing across time/space, note the resolution.
6. If pre-computed analyses are provided, use them to support your answer about
   trends, correlations, diversity patterns, or cross-source relationships.
   Cite analysis docs with [analysis_*] notation.
7. If reliability ensurance data is provided, mention cross-source validation
   results when relevant (e.g., SST-CTD agreement, data confidence levels).
   Cite reliability docs with [reliability_*] notation.

STUDY SITES:
• Onagawa Bay (O) ≈ 38.44°N 141.45°E
• Ishinomaki Bay (I) ≈ 38.41°N 141.30°E
• Mutsu Bay (M): coordinate from source metadata"""

    evidence_text = "\n=== EVIDENCE ===\n"
    for r in results:
        doc_id = r.get("doc_id") or r.get("id", "unknown")
        src = r.get("source_type", "unknown")
        t = r.get("time") or r.get("date", "")
        text = r.get("text", "")
        evidence_text += f"\n[{doc_id}] ({src}, {t})\n{text}\n"

    analysis_text = _format_analysis_context(context.get("analysis", []))
    reliability_text = _format_reliability_context(context.get("reliability", []))

    return f"{system}\n{evidence_text}{analysis_text}{reliability_text}\n\nUSER QUESTION: {query}"


def build_prompt(
    query: str,
    results: List[dict],
    *,
    inject_analysis: bool = True,
    inject_reliability: bool = True,
) -> str:
    """
    Build the provenance-aware system prompt with evidence, analysis,
    and reliability context.
    """
    prompt, _context = build_prompt_with_context(
        query,
        results,
        inject_analysis=inject_analysis,
        inject_reliability=inject_reliability,
    )
    return prompt


def ask(
    query: str,
    *,
    k: int = 8,
    source_type: Optional[str] = None,
    bay: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full RAG pipeline: retrieve → build prompt → call LLM → return answer + sources.
    """
    import requests

    # Retrieve
    results = retrieve(
        query, k=k, source_type=source_type, bay=bay,
        time_from=time_from, time_to=time_to,
    )

    # Build prompt
    prompt = build_prompt(query, results)

    # Call Ollama
    model = model or config.CHAT_MODEL
    try:
        resp = requests.post(
            f"{config.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        answer = resp.json()["message"]["content"]
    except Exception as e:
        answer = f"LLM error: {e}"

    return {
        "query": query,
        "answer": answer,
        "sources": results,
        "model": model,
        "n_sources": len(results),
    }
