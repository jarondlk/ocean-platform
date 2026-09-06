import pytest

from orchestration.evidence_availability import (
    abstention_message,
    has_usable_evidence,
    resolve_abstention_reason,
)


def test_usable_evidence_requires_identifier_and_text():
    assert not has_usable_evidence([], [{"doc_id": "x", "text": ""}])
    assert not has_usable_evidence([{"text": "content"}])
    assert has_usable_evidence([], [{"id": "analysis", "text": "content"}])


def test_abstention_reason_precedence():
    assert resolve_abstention_reason(
        analysis_id="analysis",
        retrieval_diagnostics={
            "edna_publication": "pending",
            "edna_scope_applied": True,
        },
    ) == "publication_pending"
    assert resolve_abstention_reason(
        analysis_id=None,
        retrieval_diagnostics={
            "edna_publication": "pending",
            "edna_scope_applied": False,
        },
    ) == "no_matching_evidence"
    assert resolve_abstention_reason(
        analysis_id="analysis", retrieval_diagnostics={"edna_publication": "ready"}
    ) == "empty_analysis_cohort"
    assert resolve_abstention_reason(
        analysis_id=None, retrieval_diagnostics={}
    ) == "no_matching_evidence"


def test_unknown_abstention_reason_is_rejected():
    with pytest.raises(ValueError, match="Unknown abstention reason"):
        abstention_message("unknown")
