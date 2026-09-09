"""Pure environmental eDNA analysis-eligibility policy."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any


PROTOCOL_FIELDS = ("target_gene", "primer_set", "sequencing_method")
REASON_ORDER = (
    "no_active_assay",
    "control_or_unknown",
    "protocol_incomplete",
    "method_unavailable",
)


def _present(value: Any) -> bool:
    return value is not None and bool(str(value).strip())


def evaluate_analysis_eligibility(
    sample: Mapping[str, Any],
    assays: Sequence[Mapping[str, Any]],
    method_availability: Mapping[str, Iterable[str]],
    assignment_methods: Sequence[str],
) -> dict[str, Any]:
    """Evaluate the exact sample/assay/method inputs consumed by analysis."""
    methods = tuple(sorted(set(assignment_methods)))
    if not methods:
        raise ValueError("At least one assignment method is required")
    active_assays = sorted(
        (assay for assay in assays if assay.get("active", True) is True),
        key=lambda assay: str(assay.get("assay_id") or ""),
    )
    environmental = (
        sample.get("sample_kind") == "environmental"
        and sample.get("is_control") is False
    )
    method_rows: list[dict[str, Any]] = []

    if not active_assays:
        for method in methods:
            reasons = ["no_active_assay"]
            if not environmental:
                reasons.append("control_or_unknown")
            method_rows.append(
                {
                    "sample_id": sample.get("sample_id"),
                    "assay_id": None,
                    "assignment_method": method,
                    "analysis_eligibility": "excluded",
                    "exclusion_reasons": reasons,
                }
            )
    else:
        for assay in active_assays:
            assay_id = str(assay.get("assay_id") or "")
            available = set(method_availability.get(assay_id, ()))
            protocol_complete = all(_present(assay.get(field)) for field in PROTOCOL_FIELDS)
            for method in methods:
                reasons = []
                if not environmental:
                    reasons.append("control_or_unknown")
                if not protocol_complete:
                    reasons.append("protocol_incomplete")
                if method not in available:
                    reasons.append("method_unavailable")
                method_rows.append(
                    {
                        "sample_id": sample.get("sample_id"),
                        "assay_id": assay_id,
                        "assignment_method": method,
                        "analysis_eligibility": "included" if not reasons else "excluded",
                        "exclusion_reasons": reasons,
                    }
                )

    included = any(row["analysis_eligibility"] == "included" for row in method_rows)
    top_reasons = []
    if not included:
        observed = {
            reason
            for row in method_rows
            for reason in row["exclusion_reasons"]
        }
        top_reasons = [reason for reason in REASON_ORDER if reason in observed]
    return {
        "analysis_eligibility": "included" if included else "excluded",
        "exclusion_reasons": top_reasons,
        "method_eligibility": method_rows,
    }
