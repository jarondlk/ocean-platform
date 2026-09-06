"""Deterministic evidence checks shared by RAG generation entry points."""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional


ABSTENTION_MESSAGES = {
    "no_matching_evidence": (
        "No evidence matched the current filters. The model was not run."
    ),
    "empty_analysis_cohort": (
        "The selected analysis cohort contains no eligible evidence. "
        "The model was not run."
    ),
    "publication_pending": (
        "eDNA evidence publication is pending. The model was not run."
    ),
}


def has_usable_evidence(*groups: Iterable[Mapping[str, Any]]) -> bool:
    """Return whether any evidence row has both an identifier and content."""
    for group in groups:
        for row in group:
            identifier = str(row.get("doc_id") or row.get("id") or "").strip()
            content = str(row.get("text") or "").strip()
            if identifier and content:
                return True
    return False


def resolve_abstention_reason(
    *,
    analysis_id: Optional[str],
    retrieval_diagnostics: Mapping[str, Any],
) -> str:
    """Choose the most specific reason for a no-evidence response."""
    if (
        retrieval_diagnostics.get("edna_scope_applied") is True
        and retrieval_diagnostics.get("edna_publication") == "pending"
    ):
        return "publication_pending"
    if analysis_id:
        return "empty_analysis_cohort"
    return "no_matching_evidence"


def abstention_message(reason: str) -> str:
    """Return a stable user-facing message for a supported reason."""
    try:
        return ABSTENTION_MESSAGES[reason]
    except KeyError as exc:
        raise ValueError(f"Unknown abstention reason: {reason}") from exc
