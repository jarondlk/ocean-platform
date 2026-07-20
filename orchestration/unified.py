"""
Unified query orchestrator.

Auto-detects whether PostgreSQL is available and falls back to the
local retriever if not.  Either way, the same provenance-aware prompt
is built for the LLM.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set

import config

logger = logging.getLogger(__name__)

ANALYSIS_CONTEXT_HEADER = "\n=== PRE-COMPUTED ANALYSES ===\n"
RELIABILITY_CONTEXT_HEADER = "\n=== RELIABILITY ENSURANCE ===\n"
LINKED_EVIDENCE_HEADER = "\n=== LINKED CROSS-SOURCE EVIDENCE ===\n"

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

SOURCE_TYPE_KEYWORDS = {
    "ctd": {
        "ctd", "cast", "casts", "profile", "profiles", "water column",
        "salinity", "oxygen", "dissolved oxygen", "chlorophyll", "chl",
        "depth", "surface temperature", "bottom temperature",
    },
    "metagenome": {
        "metagenome", "metagenomic", "taxonomy", "taxa", "taxon",
        "microbial", "microbe", "community", "diversity", "shannon",
        "kraken", "metaeuk", "genus", "genera", "diatom",
        "dinoflagellate",
    },
    "remote_sensing": {
        "sst", "satellite", "remote sensing", "himawari",
        "sea surface temperature", "surface temperature",
    },
}

RELIABILITY_COMPARISON_KEYWORDS = {
    "reliable", "reliability", "validate", "validation", "compare",
    "comparison", "agreement", "agree", "corroborate", "corroboration",
    "consistent", "consistency", "verify", "cross-source", "cross source",
}

ENVIRONMENT_KEYWORDS = {
    "temperature", "salinity", "oxygen", "dissolved oxygen", "chlorophyll",
    "chl", "environment", "environmental", "profile", "ctd",
}

SOURCE_TYPE_ALIASES = {
    "ctd": "ctd",
    "metagenome": "metagenome",
    "meta": "metagenome",
    "taxonomy": "metagenome",
    "taxa": "metagenome",
    "remote": "remote_sensing",
    "remote_sensing": "remote_sensing",
    "satellite": "remote_sensing",
    "sst": "remote_sensing",
    "satellite_sst": "remote_sensing",
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


def _normalize_source_type(source_type: Optional[str]) -> str:
    if not source_type:
        return "unknown"
    key = str(source_type).strip().lower()
    return SOURCE_TYPE_ALIASES.get(key, key)


def _contains_keyword(query_lower: str, keywords: Set[str]) -> bool:
    return any(keyword in query_lower for keyword in keywords)


def infer_expected_source_types(query: str) -> List[str]:
    """
    Infer which source families a high-quality answer should consult.

    This intentionally stays heuristic and transparent: it drives diagnostics
    and UI warnings, not hard retrieval filtering.
    """
    query_lower = query.lower()
    expected: Set[str] = set()

    for source_type, keywords in SOURCE_TYPE_KEYWORDS.items():
        if _contains_keyword(query_lower, keywords):
            expected.add(source_type)

    is_reliability_comparison = _contains_keyword(query_lower, RELIABILITY_COMPARISON_KEYWORDS)
    mentions_temperature = "temperature" in query_lower or "sst" in query_lower
    if is_reliability_comparison and mentions_temperature and (
        "sst" in query_lower
        or "satellite" in query_lower
        or "remote sensing" in query_lower
        or "surface temperature" in query_lower
    ):
        expected.update({"ctd", "remote_sensing"})

    if "metagenome" in expected and _contains_keyword(query_lower, ENVIRONMENT_KEYWORDS):
        expected.add("ctd")

    return sorted(expected)


def source_coverage_diagnostics(
    query: str,
    primary_results: List[dict],
    linked_results: Optional[List[dict]] = None,
    *,
    expanded: bool = False,
    backend: str = "unknown",
    expansion_error: Optional[str] = None,
) -> Dict[str, Any]:
    linked_results = linked_results or []
    expected = infer_expected_source_types(query)
    primary_types = sorted({
        _normalize_source_type(row.get("source_type"))
        for row in primary_results
        if _normalize_source_type(row.get("source_type")) != "unknown"
    })
    linked_types = sorted({
        _normalize_source_type(row.get("source_type"))
        for row in linked_results
        if _normalize_source_type(row.get("source_type")) != "unknown"
    })
    retrieved = sorted(set(primary_types).union(linked_types))
    missing = sorted(set(expected).difference(retrieved))
    coverage_ratio = (
        round((len(expected) - len(missing)) / len(expected), 3)
        if expected
        else None
    )
    source_type_counts: Dict[str, Dict[str, int]] = {
        "primary": {},
        "linked": {},
        "combined": {},
    }
    for role, rows in (("primary", primary_results), ("linked", linked_results)):
        for row in rows:
            source_type = _normalize_source_type(row.get("source_type"))
            if source_type == "unknown":
                continue
            source_type_counts[role][source_type] = source_type_counts[role].get(source_type, 0) + 1
            source_type_counts["combined"][source_type] = source_type_counts["combined"].get(source_type, 0) + 1

    return {
        "backend": backend,
        "expanded": expanded,
        "expansion_error": expansion_error,
        "expected_source_types": expected,
        "primary_source_types": primary_types,
        "linked_source_types": linked_types,
        "retrieved_source_types": retrieved,
        "missing_source_types": missing,
        "source_coverage_ratio": coverage_ratio,
        "primary_count": len(primary_results),
        "linked_count": len(linked_results),
        "total_count": len(primary_results) + len(linked_results),
        "source_type_counts": source_type_counts,
    }


def _primary_event_to_doc(primary_results: List[dict]) -> Dict[str, str]:
    event_to_doc: Dict[str, str] = {}
    for row in primary_results:
        event_id = row.get("event_id")
        doc_id = row.get("doc_id")
        if event_id and doc_id and event_id not in event_to_doc:
            event_to_doc[str(event_id)] = str(doc_id)
    return event_to_doc


def _mark_primary_results(results: List[dict]) -> List[dict]:
    primary = []
    for row in results:
        next_row = dict(row)
        next_row.setdefault("retrieval_role", "primary")
        primary.append(next_row)
    return primary


def _expand_linked_evidence(primary_results: List[dict], max_links: int) -> List[dict]:
    if not primary_results or max_links <= 0:
        return []

    event_to_doc = _primary_event_to_doc(primary_results)
    primary_event_ids = sorted(event_to_doc)
    if not primary_event_ids:
        return []

    primary_doc_ids = {
        str(row.get("doc_id"))
        for row in primary_results
        if row.get("doc_id")
    }
    event_placeholders = ", ".join(f":eid_{idx}" for idx, _event_id in enumerate(primary_event_ids))
    doc_placeholders = ", ".join(f":did_{idx}" for idx, _doc_id in enumerate(primary_doc_ids))
    params: Dict[str, Any] = {
        f"eid_{idx}": event_id
        for idx, event_id in enumerate(primary_event_ids)
    }
    params.update({
        f"did_{idx}": doc_id
        for idx, doc_id in enumerate(primary_doc_ids)
    })
    params["limit"] = max(max_links * 4, max_links)

    from sqlalchemy import text
    from db.connection import get_session

    sql = text(f"""
        SELECT rd.doc_id, rd.source_type, rd.sample_id, rd.event_id,
               rd.time, rd.bay, rd.station, rd.title, rd.text,
               cl.source_event_id, cl.target_event_id, cl.link_type,
               cl.distance_km, cl.time_delta_days
        FROM cross_source_link cl
        JOIN retrieval_document rd ON (
          (cl.source_event_id IN ({event_placeholders}) AND rd.event_id = cl.target_event_id)
          OR
          (cl.target_event_id IN ({event_placeholders}) AND rd.event_id = cl.source_event_id)
        )
        WHERE (cl.source_event_id IN ({event_placeholders})
               OR cl.target_event_id IN ({event_placeholders}))
          AND rd.doc_id NOT IN ({doc_placeholders})
        ORDER BY ABS(COALESCE(cl.time_delta_days, 0)) ASC,
                 COALESCE(cl.distance_km, 999999) ASC,
                 rd.source_type ASC,
                 rd.time ASC
        LIMIT :limit
    """)

    linked: List[dict] = []
    seen_doc_ids: Set[str] = set()
    primary_event_id_set = set(primary_event_ids)
    with get_session() as session:
        rows = session.execute(sql, params).fetchall()

    for row in rows:
        doc_id = str(row.doc_id)
        if doc_id in primary_doc_ids or doc_id in seen_doc_ids:
            continue
        linked_from_event_id = (
            row.source_event_id
            if row.source_event_id in primary_event_id_set
            else row.target_event_id
        )
        linked.append({
            "doc_id": row.doc_id,
            "source_type": row.source_type,
            "sample_id": row.sample_id,
            "event_id": row.event_id,
            "time": row.time,
            "bay": row.bay,
            "station": row.station,
            "title": row.title,
            "text": row.text,
            "score": None,
            "rank_sources": {},
            "retrieval_role": "linked",
            "link_type": row.link_type,
            "linked_from_event_id": linked_from_event_id,
            "linked_from_doc_id": event_to_doc.get(str(linked_from_event_id)),
            "time_delta_days": row.time_delta_days,
            "distance_km": row.distance_km,
        })
        seen_doc_ids.add(doc_id)
        if len(linked) >= max_links:
            break

    return linked


def retrieve_with_expansion(
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
    expand_evidence: bool = True,
    max_linked_sources: int = 5,
) -> Dict[str, Any]:
    primary = _mark_primary_results(retrieve(
        query,
        k=k,
        source_type=source_type,
        bay=bay,
        time_from=time_from,
        time_to=time_to,
        vector_weight=vector_weight,
        fts_weight=fts_weight,
        rrf_k=rrf_k,
    ))
    linked: List[dict] = []
    expansion_error: Optional[str] = None
    pg_available = _pg_available()

    if expand_evidence and max_linked_sources > 0 and pg_available:
        try:
            linked = _expand_linked_evidence(primary, max_linked_sources)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            expansion_error = str(exc)
            logger.warning("Linked evidence expansion failed: %s", exc)

    diagnostics = source_coverage_diagnostics(
        query,
        primary,
        linked,
        expanded=bool(expand_evidence and pg_available),
        backend="postgres" if pg_available else "local",
        expansion_error=expansion_error,
    )
    return {
        "primary": primary,
        "linked": linked,
        "diagnostics": diagnostics,
    }


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
    linked_results: Optional[List[dict]] = None,
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
    return _build_prompt_from_context(query, results, context, linked_results=linked_results), context


def _build_prompt_from_context(
    query: str,
    results: List[dict],
    context: Dict[str, List[dict]],
    *,
    linked_results: Optional[List[dict]] = None,
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
8. Treat linked cross-source evidence as corroborating context. Cite it directly
   when it supports or challenges the primary retrieval, and state when expected
   source types are missing.

STUDY SITES:
• Onagawa Bay (O) ≈ 38.44°N 141.45°E
• Ishinomaki Bay (I) ≈ 38.41°N 141.30°E
• Mutsu Bay (M): coordinate from source metadata"""

    evidence_text = "\n=== PRIMARY EVIDENCE ===\n"
    for r in results:
        doc_id = r.get("doc_id") or r.get("id", "unknown")
        src = r.get("source_type", "unknown")
        t = r.get("time") or r.get("date", "")
        text = r.get("text", "")
        evidence_text += f"\n[{doc_id}] ({src}, {t})\n{text}\n"

    if linked_results:
        evidence_text += LINKED_EVIDENCE_HEADER
        for r in linked_results:
            doc_id = r.get("doc_id") or r.get("id", "unknown")
            src = r.get("source_type", "unknown")
            t = r.get("time") or r.get("date", "")
            link_type = r.get("link_type") or "cross_source"
            linked_from = r.get("linked_from_doc_id") or r.get("linked_from_event_id") or "primary evidence"
            text = r.get("text", "")
            evidence_text += f"\n[{doc_id}] ({src}, {t}; linked via {link_type} from {linked_from})\n{text}\n"

    analysis_text = _format_analysis_context(context.get("analysis", []))
    reliability_text = _format_reliability_context(context.get("reliability", []))

    return f"{system}\n{evidence_text}{analysis_text}{reliability_text}\n\nUSER QUESTION: {query}"


def build_prompt(
    query: str,
    results: List[dict],
    *,
    linked_results: Optional[List[dict]] = None,
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
        linked_results=linked_results,
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
