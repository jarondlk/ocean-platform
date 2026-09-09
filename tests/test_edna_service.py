import pytest

from api.edna_service import environmental_analysis_eligibility
from preprocessing.edna_eligibility import evaluate_analysis_eligibility


METHODS = ("qcauto_target", "qcauto_95pct_3nn_target")


def _sample(kind="environmental", is_control=False):
    return {"sample_id": "sample", "sample_kind": kind, "is_control": is_control}


def _assay(**updates):
    assay = {
        "assay_id": "assay",
        "target_gene": "12S",
        "primer_set": "MiFish",
        "sequencing_method": "Illumina",
        "active": True,
    }
    assay.update(updates)
    return assay


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
        "exclusion_reasons": ["no_active_assay", "control_or_unknown"],
    }


@pytest.mark.parametrize(
    ("sample", "assays", "availability", "status", "reasons"),
    [
        (_sample(), [_assay()], {"assay": METHODS}, "included", []),
        (_sample("negative_control", True), [_assay()], {"assay": METHODS}, "excluded", ["control_or_unknown"]),
        (_sample("unknown", None), [_assay()], {"assay": METHODS}, "excluded", ["control_or_unknown"]),
        (_sample(), [], {}, "excluded", ["no_active_assay"]),
        (_sample(), [_assay(primer_set=None)], {"assay": METHODS}, "excluded", ["protocol_incomplete"]),
        (_sample(), [_assay()], {}, "excluded", ["method_unavailable"]),
    ],
)
def test_shared_eligibility_policy_matrix(
    sample, assays, availability, status, reasons
):
    result = evaluate_analysis_eligibility(sample, assays, availability, METHODS)

    assert result["analysis_eligibility"] == status
    assert result["exclusion_reasons"] == reasons
    assert all(
        row["analysis_eligibility"] == status
        for row in result["method_eligibility"]
    )


def test_shared_eligibility_reports_mixed_method_availability():
    result = evaluate_analysis_eligibility(
        _sample(), [_assay()], {"assay": {"qcauto_target"}}, METHODS
    )

    assert result["analysis_eligibility"] == "included"
    assert result["exclusion_reasons"] == []
    assert result["method_eligibility"] == [
        {
            "sample_id": "sample",
            "assay_id": "assay",
            "assignment_method": "qcauto_95pct_3nn_target",
            "analysis_eligibility": "excluded",
            "exclusion_reasons": ["method_unavailable"],
        },
        {
            "sample_id": "sample",
            "assay_id": "assay",
            "assignment_method": "qcauto_target",
            "analysis_eligibility": "included",
            "exclusion_reasons": [],
        },
    ]


def test_shared_eligibility_accumulates_stable_reason_codes():
    result = evaluate_analysis_eligibility(
        _sample("unknown", None),
        [_assay(primer_set=None)],
        {},
        ["qcauto_target"],
    )

    assert result["exclusion_reasons"] == [
        "control_or_unknown",
        "protocol_incomplete",
        "method_unavailable",
    ]
    assert result["method_eligibility"][0]["exclusion_reasons"] == [
        "control_or_unknown",
        "protocol_incomplete",
        "method_unavailable",
    ]


def test_shared_eligibility_rejects_an_unexplained_empty_method_scope():
    with pytest.raises(ValueError, match="assignment method"):
        evaluate_analysis_eligibility(_sample(), [_assay()], {}, [])
