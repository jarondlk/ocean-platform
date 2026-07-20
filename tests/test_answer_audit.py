from orchestration.answer_audit import audit_answer


def test_audit_accepts_valid_citations_across_all_evidence_roles():
    audit = audit_answer(
        query="Compare CTD and SST reliability trends.",
        answer=(
            "CTD and SST agree for the event [ctd_1, sst_1]. "
            "The trend context and reliability check support this [analysis_1] [reliability_1]."
        ),
        primary_sources=[{"doc_id": "ctd_1", "source_type": "ctd", "title": "CTD"}],
        linked_sources=[{"doc_id": "sst_1", "source_type": "remote_sensing", "title": "SST"}],
        analysis_context=[{"id": "analysis_1", "title": "Trend"}],
        reliability_context=[{"id": "reliability_1", "title": "Validation"}],
        retrieval_diagnostics={
            "expected_source_types": ["ctd", "remote_sensing"],
            "retrieved_source_types": ["ctd", "remote_sensing"],
            "missing_source_types": [],
        },
    )

    assert audit["trust_level"] == "strong"
    assert audit["trust_score"] == 1.0
    assert audit["citation_count"] == 4
    assert audit["invalid_citation_count"] == 0
    assert audit["primary_sources_cited"] == 1
    assert audit["linked_sources_cited"] == 1
    assert audit["analysis_context_cited"] == 1
    assert audit["reliability_context_cited"] == 1
    assert audit["warnings"] == []


def test_audit_flags_invalid_and_unused_linked_evidence():
    audit = audit_answer(
        query="Compare CTD and satellite observations.",
        answer="The surface profile supports the answer [ctd_1] [not_in_context].",
        primary_sources=[{"doc_id": "ctd_1", "source_type": "ctd"}],
        linked_sources=[{"doc_id": "sst_1", "source_type": "remote_sensing"}],
        analysis_context=[],
        reliability_context=[],
        retrieval_diagnostics={
            "expected_source_types": ["ctd", "remote_sensing"],
            "retrieved_source_types": ["ctd", "remote_sensing"],
            "missing_source_types": [],
        },
    )

    assert audit["trust_level"] == "weak"
    assert audit["valid_citation_count"] == 1
    assert audit["invalid_citation_count"] == 1
    assert audit["invalid_citations"][0]["citation_id"] == "not_in_context"
    assert audit["missing_expected_citations"] == ["remote_sensing"]
    assert audit["unused_linked_sources"] == ["sst_1"]
    assert "Answer contains citations not present in supplied evidence." in audit["warnings"]
    assert "Linked cross-source evidence was retrieved but not cited." in audit["warnings"]


def test_audit_requires_gap_acknowledgement_when_retrieval_misses_source_type():
    audit = audit_answer(
        query="Compare CTD and satellite observations.",
        answer="CTD evidence is available, but satellite SST evidence is missing for this answer [ctd_1].",
        primary_sources=[{"doc_id": "ctd_1", "source_type": "ctd"}],
        linked_sources=[],
        analysis_context=[],
        reliability_context=[],
        retrieval_diagnostics={
            "expected_source_types": ["ctd", "remote_sensing"],
            "retrieved_source_types": ["ctd"],
            "missing_source_types": ["remote_sensing"],
        },
    )

    assert audit["trust_level"] == "strong"
    assert audit["missing_expected_citations"] == ["remote_sensing"]
    assert "Retrieval diagnostics reported missing source types, but the answer did not acknowledge the gap." not in audit["warnings"]


def test_reliability_context_can_satisfy_ctd_sst_source_requirements():
    audit = audit_answer(
        query="How reliable is satellite SST compared with CTD surface temperature?",
        answer="The SST-CTD reliability summary supports agreement [reliability_sst_ctd].",
        primary_sources=[{"doc_id": "sst_1", "source_type": "remote_sensing"}],
        linked_sources=[{"doc_id": "ctd_1", "source_type": "ctd"}],
        analysis_context=[],
        reliability_context=[
            {
                "id": "reliability_sst_ctd",
                "analysis_type": "cross_source_validation",
                "title": "SST CTD validation",
                "text": "Satellite SST and CTD surface temperature agree within expected uncertainty.",
            }
        ],
        retrieval_diagnostics={
            "expected_source_types": ["ctd", "remote_sensing"],
            "retrieved_source_types": ["ctd", "remote_sensing"],
            "missing_source_types": [],
        },
    )

    requirements = audit["citation_requirements"]
    assert audit["trust_level"] == "strong"
    assert audit["missing_expected_citations"] == []
    assert requirements["context_satisfied_source_types"] == ["ctd", "remote_sensing"]
    assert requirements["missing_source_types"] == []
    assert requirements["required_context_types"] == ["reliability"]
    assert "Expected source type ctd was retrieved but not cited or covered by cited context." not in audit["warnings"]
    assert "Linked cross-source evidence was retrieved but not cited." not in audit["warnings"]


def test_analysis_context_can_satisfy_trend_source_requirements():
    audit = audit_answer(
        query="What seasonal CTD temperature trend is visible?",
        answer="The seasonal CTD trend is summarized by the analysis context [analysis_trends].",
        primary_sources=[{"doc_id": "ctd_1", "source_type": "ctd"}],
        linked_sources=[],
        analysis_context=[
            {
                "id": "analysis_trends",
                "analysis_type": "trend",
                "title": "CTD seasonal trend",
                "text": "CTD temperature and salinity show seasonal structure.",
            }
        ],
        reliability_context=[],
        retrieval_diagnostics={
            "expected_source_types": ["ctd"],
            "retrieved_source_types": ["ctd"],
            "missing_source_types": [],
        },
    )

    assert audit["trust_level"] == "strong"
    assert audit["missing_expected_citations"] == []
    assert audit["citation_requirements"]["required_context_types"] == ["analysis"]
    assert audit["citation_requirements"]["context_satisfied_source_types"] == ["ctd"]


def test_raw_measurement_question_still_requires_raw_source_citation():
    audit = audit_answer(
        query="What was the CTD surface temperature for sample 2024-01-O-s1?",
        answer="The analysis summary mentions the sample [analysis_trends].",
        primary_sources=[{"doc_id": "ctd_1", "source_type": "ctd"}],
        linked_sources=[],
        analysis_context=[
            {
                "id": "analysis_trends",
                "analysis_type": "trend",
                "title": "CTD trend",
                "text": "CTD temperature trend summary.",
            }
        ],
        reliability_context=[],
        retrieval_diagnostics={
            "expected_source_types": ["ctd"],
            "retrieved_source_types": ["ctd"],
            "missing_source_types": [],
        },
    )

    assert audit["trust_level"] == "caution"
    assert audit["missing_expected_citations"] == ["ctd"]
    assert audit["citation_requirements"]["raw_source_required"] is True
    assert audit["citation_requirements"]["context_satisfied_source_types"] == []
    assert "Expected source type ctd was retrieved but not cited or covered by cited context." in audit["warnings"]


def test_required_reliability_context_warns_when_not_cited():
    audit = audit_answer(
        query="How reliable is CTD surface temperature compared with satellite SST?",
        answer="The raw observations agree [ctd_1] [sst_1].",
        primary_sources=[{"doc_id": "sst_1", "source_type": "remote_sensing"}],
        linked_sources=[{"doc_id": "ctd_1", "source_type": "ctd"}],
        analysis_context=[],
        reliability_context=[
            {
                "id": "reliability_sst_ctd",
                "analysis_type": "cross_source_validation",
                "title": "SST CTD validation",
                "text": "Satellite SST and CTD surface temperature agreement summary.",
            }
        ],
        retrieval_diagnostics={
            "expected_source_types": ["ctd", "remote_sensing"],
            "retrieved_source_types": ["ctd", "remote_sensing"],
            "missing_source_types": [],
        },
    )

    assert audit["trust_level"] == "caution"
    assert audit["citation_requirements"]["missing_context_types"] == ["reliability"]
    assert "Reliability context is required for this query but was not cited." in audit["warnings"]
