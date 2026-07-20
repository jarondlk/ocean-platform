"""Deterministic answer citation and evidence-use audit."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set


CITATION_PATTERN = re.compile(r"\[([^\[\]]+)\]")
GAP_TERMS = {
    "gap", "gaps", "missing", "insufficient", "limited", "limitation",
    "limitations", "unavailable", "not available", "not retrieved",
    "no evidence", "cannot determine", "uncertain", "uncertainty",
}
ANALYSIS_TERMS = {
    "trend", "trends", "seasonal", "correlation", "correlations",
    "relationship", "relationships", "diversity", "richness", "evenness",
    "co-occurrence", "cooccurrence", "community", "composition",
    "pattern", "patterns", "taxa-environment", "taxa environment",
}
RELIABILITY_TERMS = {
    "reliable", "reliability", "validate", "validation", "agreement",
    "agree", "corroborate", "corroboration", "confidence", "trust",
    "verify", "consistent", "consistency", "gap", "gaps", "anomaly",
    "anomalies", "cross-source", "cross source",
}
RAW_MEASUREMENT_TERMS = {
    "what was", "which sample", "specific", "sample", "station",
    "date", "measured", "measurement", "observation", "observed",
    "profile", "cast", "surface temperature", "salinity",
    "dissolved oxygen", "chlorophyll",
}
SOURCE_TYPE_TERMS = {
    "ctd": {
        "ctd", "cast", "profile", "water column", "salinity",
        "oxygen", "dissolved oxygen", "chlorophyll", "chl",
        "depth", "surface temperature", "bottom temperature",
    },
    "remote_sensing": {
        "sst", "satellite", "remote sensing", "himawari",
        "sea surface temperature", "surface temperature",
    },
    "metagenome": {
        "metagenome", "metagenomic", "taxonomy", "taxa", "taxon",
        "microbial", "community", "diversity", "shannon", "kraken",
        "metaeuk", "genus", "genera", "diatom", "dinoflagellate",
    },
}


def _doc_id(document: Dict[str, Any]) -> str:
    return str(document.get("doc_id") or document.get("id") or "")


def _string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return []


def _contains_any(text: str, terms: Set[str]) -> bool:
    text_lower = text.lower()
    return any(term in text_lower for term in terms)


def _source_types_in_text(text: str) -> List[str]:
    text_lower = text.lower()
    return sorted(
        source_type
        for source_type, terms in SOURCE_TYPE_TERMS.items()
        if any(term in text_lower for term in terms)
    )


def _document_text(document: Dict[str, Any]) -> str:
    return " ".join(
        str(document.get(key) or "")
        for key in ("doc_id", "id", "title", "analysis_type", "text")
    )


def _citation_tokens(answer: str) -> List[Dict[str, Any]]:
    tokens: List[Dict[str, Any]] = []
    for match in CITATION_PATTERN.finditer(answer or ""):
        raw = match.group(0)
        inside = match.group(1)
        for part in re.split(r"[,;]", inside):
            citation_id = part.strip().strip(".")
            if citation_id:
                tokens.append({
                    "citation_id": citation_id,
                    "raw": raw,
                    "position": match.start(),
                })
    return tokens


def _evidence_index(
    primary_sources: List[Dict[str, Any]],
    linked_sources: List[Dict[str, Any]],
    analysis_context: List[Dict[str, Any]],
    reliability_context: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}

    for role, rows in (("primary", primary_sources), ("linked", linked_sources)):
        for row in rows:
            doc_id = _doc_id(row)
            if not doc_id:
                continue
            index[doc_id] = {
                "citation_id": doc_id,
                "evidence_role": role,
                "context_type": None,
                "source_type": row.get("source_type"),
                "covered_source_types": [str(row.get("source_type"))] if row.get("source_type") else [],
                "title": row.get("title") or doc_id,
            }

    for context_type, rows in (("analysis", analysis_context), ("reliability", reliability_context)):
        for row in rows:
            doc_id = _doc_id(row)
            if not doc_id:
                continue
            index[doc_id] = {
                "citation_id": doc_id,
                "evidence_role": "context",
                "context_type": context_type,
                "source_type": None,
                "covered_source_types": _source_types_in_text(_document_text(row)),
                "title": row.get("title") or row.get("analysis_type") or doc_id,
            }

    return index


def _answer_acknowledges_gap(answer: str) -> bool:
    answer_lower = (answer or "").lower()
    return any(term in answer_lower for term in GAP_TERMS)


def _audit_record(token: Dict[str, Any], evidence: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    valid = evidence is not None
    return {
        "citation_id": token["citation_id"],
        "raw": token["raw"],
        "valid": valid,
        "evidence_role": evidence.get("evidence_role") if evidence else None,
        "source_type": evidence.get("source_type") if evidence else None,
        "context_type": evidence.get("context_type") if evidence else None,
        "covered_source_types": evidence.get("covered_source_types", []) if evidence else [],
        "title": evidence.get("title") if evidence else None,
        "detail": "Resolved against supplied evidence." if valid else "Citation was not present in supplied evidence.",
    }


def _trust_level(score: float) -> str:
    if score >= 0.85:
        return "strong"
    if score >= 0.55:
        return "caution"
    return "weak"


def _query_requires_raw_sources(query: str) -> bool:
    return (
        _contains_any(query, RAW_MEASUREMENT_TERMS)
        and not _query_requires_analysis(query)
        and not _query_requires_reliability(query)
    )


def _query_requires_analysis(query: str) -> bool:
    return _contains_any(query, ANALYSIS_TERMS)


def _query_requires_reliability(query: str) -> bool:
    return _contains_any(query, RELIABILITY_TERMS)


def _citation_requirements(
    *,
    query: str,
    expected_source_types: List[str],
    retrieved_source_types: List[str],
    analysis_context: List[Dict[str, Any]],
    reliability_context: List[Dict[str, Any]],
    cited_source_types: List[str],
    analysis_cited_ids: Set[str],
    reliability_cited_ids: Set[str],
    valid_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    required_context_types: List[str] = []
    if analysis_context and _query_requires_analysis(query):
        required_context_types.append("analysis")
    if reliability_context and _query_requires_reliability(query):
        required_context_types.append("reliability")

    raw_source_required = _query_requires_raw_sources(query)
    context_satisfied_source_types: Set[str] = set()
    context_satisfaction: Dict[str, List[str]] = {}
    if not raw_source_required:
        for record in valid_records:
            context_type = record.get("context_type")
            if context_type not in required_context_types:
                continue
            covered = set(_string_list(record.get("covered_source_types")))
            relevant = sorted(covered.intersection(expected_source_types))
            if not relevant:
                continue
            context_satisfied_source_types.update(relevant)
            context_satisfaction[record["citation_id"]] = relevant

    directly_cited_source_types = sorted(set(cited_source_types))
    satisfied_context_types = sorted(
        context_type
        for context_type, cited_ids in (
            ("analysis", analysis_cited_ids),
            ("reliability", reliability_cited_ids),
        )
        if cited_ids
    )
    satisfied_source_types = sorted(set(directly_cited_source_types).union(context_satisfied_source_types))
    missing_source_types = sorted(set(expected_source_types).difference(satisfied_source_types))
    missing_context_types = sorted(set(required_context_types).difference(satisfied_context_types))

    requirement_rows: List[Dict[str, Any]] = []
    for source_type in expected_source_types:
        if source_type in directly_cited_source_types:
            satisfied_by = "raw citation"
        elif source_type in context_satisfied_source_types:
            providers = [
                citation_id
                for citation_id, covered in context_satisfaction.items()
                if source_type in covered
            ]
            satisfied_by = ", ".join(providers) or "context citation"
        elif source_type not in retrieved_source_types:
            satisfied_by = "not retrieved"
        else:
            satisfied_by = "missing"
        requirement_rows.append({
            "requirement": f"source:{source_type}",
            "required": True,
            "satisfied_by": satisfied_by,
            "status": "satisfied" if source_type in satisfied_source_types else "missing",
        })

    for context_type in required_context_types:
        requirement_rows.append({
            "requirement": f"context:{context_type}",
            "required": True,
            "satisfied_by": "context citation" if context_type in satisfied_context_types else "missing",
            "status": "satisfied" if context_type in satisfied_context_types else "missing",
        })

    return {
        "required_source_types": expected_source_types,
        "required_context_types": required_context_types,
        "raw_source_required": raw_source_required,
        "directly_cited_source_types": directly_cited_source_types,
        "context_satisfied_source_types": sorted(context_satisfied_source_types),
        "satisfied_source_types": satisfied_source_types,
        "missing_source_types": missing_source_types,
        "satisfied_context_types": satisfied_context_types,
        "missing_context_types": missing_context_types,
        "requirement_rows": requirement_rows,
    }


def audit_answer(
    *,
    query: str = "",
    answer: str,
    primary_sources: List[Dict[str, Any]],
    linked_sources: List[Dict[str, Any]],
    analysis_context: List[Dict[str, Any]],
    reliability_context: List[Dict[str, Any]],
    retrieval_diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    """Audit whether an answer cites and uses the supplied evidence bundle."""
    index = _evidence_index(primary_sources, linked_sources, analysis_context, reliability_context)
    tokens = _citation_tokens(answer)
    records = [_audit_record(token, index.get(token["citation_id"])) for token in tokens]

    valid_records = [record for record in records if record["valid"]]
    invalid_records = [record for record in records if not record["valid"]]
    cited_ids = {record["citation_id"] for record in valid_records}
    cited_source_types = sorted({
        str(record["source_type"])
        for record in valid_records
        if record.get("source_type")
    })
    expected_source_types = _string_list(retrieval_diagnostics.get("expected_source_types"))
    retrieved_source_types = _string_list(retrieval_diagnostics.get("retrieved_source_types"))

    primary_cited_ids = {
        record["citation_id"]
        for record in valid_records
        if record.get("evidence_role") == "primary"
    }
    linked_cited_ids = {
        record["citation_id"]
        for record in valid_records
        if record.get("evidence_role") == "linked"
    }
    analysis_cited_ids = {
        record["citation_id"]
        for record in valid_records
        if record.get("context_type") == "analysis"
    }
    reliability_cited_ids = {
        record["citation_id"]
        for record in valid_records
        if record.get("context_type") == "reliability"
    }
    linked_ids = {_doc_id(row) for row in linked_sources if _doc_id(row)}
    unused_linked_sources = sorted(linked_ids.difference(cited_ids))
    citation_requirements = _citation_requirements(
        query=query,
        expected_source_types=expected_source_types,
        retrieved_source_types=retrieved_source_types,
        analysis_context=analysis_context,
        reliability_context=reliability_context,
        cited_source_types=cited_source_types,
        analysis_cited_ids=analysis_cited_ids,
        reliability_cited_ids=reliability_cited_ids,
        valid_records=valid_records,
    )
    missing_expected_citations = citation_requirements["missing_source_types"]

    warnings: List[str] = []
    score = 1.0

    if not tokens:
        warnings.append("Answer contains no bracket citations.")
        score -= 0.4

    if invalid_records:
        warnings.append("Answer contains citations not present in supplied evidence.")
        score -= min(0.4, 0.15 * len(invalid_records))

    retrieved_source_type_set: Set[str] = set(retrieved_source_types)
    satisfied_source_type_set = set(_string_list(citation_requirements.get("satisfied_source_types")))
    for source_type in citation_requirements["missing_source_types"]:
        if source_type in retrieved_source_type_set:
            warnings.append(f"Expected source type {source_type} was retrieved but not cited or covered by cited context.")
            score -= 0.2

    for context_type in citation_requirements["missing_context_types"]:
        warnings.append(f"{context_type.capitalize()} context is required for this query but was not cited.")
        score -= 0.25

    retrieval_missing = _string_list(retrieval_diagnostics.get("missing_source_types"))
    if retrieval_missing and not _answer_acknowledges_gap(answer):
        warnings.append("Retrieval diagnostics reported missing source types, but the answer did not acknowledge the gap.")
        score -= 0.2

    linked_source_types = {
        str(row.get("source_type"))
        for row in linked_sources
        if row.get("source_type")
    }
    if linked_sources and not linked_cited_ids and not linked_source_types.issubset(satisfied_source_type_set):
        warnings.append("Linked cross-source evidence was retrieved but not cited.")
        score -= 0.15

    score = max(0.0, min(1.0, round(score, 3)))
    return {
        "trust_level": _trust_level(score),
        "trust_score": score,
        "citation_count": len(tokens),
        "valid_citation_count": len(valid_records),
        "invalid_citation_count": len(invalid_records),
        "cited_source_types": cited_source_types,
        "expected_source_types": expected_source_types,
        "retrieved_source_types": retrieved_source_types,
        "missing_expected_citations": missing_expected_citations,
        "primary_sources_cited": len(primary_cited_ids),
        "linked_sources_cited": len(linked_cited_ids),
        "analysis_context_cited": len(analysis_cited_ids),
        "reliability_context_cited": len(reliability_cited_ids),
        "unused_linked_sources": unused_linked_sources,
        "citation_requirements": citation_requirements,
        "invalid_citations": invalid_records,
        "citations": records,
        "warnings": warnings,
    }
