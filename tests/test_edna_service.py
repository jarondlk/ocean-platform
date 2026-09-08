from api.edna_service import environmental_analysis_eligibility


def test_environmental_analysis_eligibility_matches_analysis_control_policy():
    assert environmental_analysis_eligibility(
        {"sample_kind": "environmental", "is_control": False}, 1
    ) == {"analysis_eligibility": "included", "exclusion_reasons": []}

    for sample in (
        {"sample_kind": "unknown", "is_control": None},
        {"sample_kind": "negative_control", "is_control": True},
        {"sample_kind": "environmental", "is_control": None},
    ):
        assert environmental_analysis_eligibility(sample, 1) == {
            "analysis_eligibility": "excluded",
            "exclusion_reasons": ["control_or_unknown"],
        }


def test_environmental_analysis_eligibility_reports_missing_active_assay_first():
    assert environmental_analysis_eligibility(
        {"sample_kind": "unknown", "is_control": None}, 0
    ) == {
        "analysis_eligibility": "excluded",
        "exclusion_reasons": ["no_active_assay"],
    }
