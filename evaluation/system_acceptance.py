"""Independent deterministic C26 metrics. Never runs a model or rewrites a gate."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json

from schema.system_acceptance import (
    AcceptanceGateResult,
    AcceptanceRequirement,
    ControllerComparison,
    ControllerMetrics,
    ControllerObservation,
    ExpectedOutcome,
    MetricAssessment,
    SystemAcceptanceReport,
    json_value,
)


def content_sha256(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python")
    raw = json.dumps(
        json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_acceptance_json(raw, *, maximum_bytes=8 * 1024 * 1024):
    """Read bounded acceptance JSON without duplicate-key or nonfinite repair."""
    if type(raw) is str:
        raw = raw.encode("utf-8")
    if (
        type(raw) is not bytes
        or type(maximum_bytes) is not int
        or not 1 <= maximum_bytes <= 8 * 1024 * 1024
        or len(raw) > maximum_bytes
    ):
        raise ValueError("Acceptance JSON exceeds its fixed byte bound")

    def distinct_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate acceptance JSON key")
            result[key] = value
        return result

    return json_value(json.loads(raw.decode("utf-8"), object_pairs_hook=distinct_keys))


def _assessment(status, details, reason=None):
    return MetricAssessment(status=status, details=details, reason=reason)


def _status(values):
    return (
        "failed"
        if "failed" in values
        else "blocked"
        if "blocked" in values
        else "not_run"
        if not values or "not_run" in values
        else "passed"
    )


def derive_metrics(expected, observation):
    """Compare retained structured observations against a separately built oracle.

    A complete structured claim audit is explicitly required. This routine does
    not pretend to evaluate arbitrary prose or establish scientific approval.
    """
    expected = ExpectedOutcome.model_validate(expected)
    observed = ControllerObservation.model_validate(observation)
    wanted, actual = set(expected.inventory_ids), set(observed.inventory_ids)
    missing, unexpected = wanted - actual, actual - wanted
    details = {
        "expected_count": len(wanted),
        "observed_count": len(actual),
        "matched_count": len(wanted & actual),
        "missing_count": len(missing),
        "unexpected_count": len(unexpected),
        "state": observed.inventory_state,
        "missing_preview": sorted(missing)[:25],
        "unexpected_preview": sorted(unexpected)[:25],
        "diagnostics_truncated": len(missing) > 25 or len(unexpected) > 25,
    }
    if unexpected or missing and observed.inventory_state == "complete":
        inventory = _assessment(
            "failed",
            details,
            "Whole-scope inventory membership differs from the independent oracle",
        )
    elif observed.inventory_state != "complete":
        inventory = _assessment(
            "blocked",
            details,
            "Inventory is partial, unknown or unavailable; preview rows cannot establish completeness",
        )
    else:
        inventory = _assessment("passed", details)
    mismatches, unknown, absent = [], [], []
    for key, number in expected.numbers.items():
        if key not in observed.numbers:
            absent.append(key)
        elif number is None:
            unknown.append(key)
        elif observed.numbers[key] is None or Decimal(number) != Decimal(
            observed.numbers[key]
        ):
            mismatches.append(key)
    extra = sorted(observed.numbers.keys() - expected.numbers.keys())
    details = {
        "expected_count": len(expected.numbers),
        "mismatched_keys": mismatches,
        "missing_keys": absent,
        "unexpected_keys": extra,
        "unknown_reference_keys": unknown,
    }
    if mismatches or absent or extra:
        numerical = _assessment(
            "failed",
            details,
            "Structured numerical answers differ from the independent exact-decimal oracle",
        )
    elif unknown or not expected.numbers:
        numerical = _assessment(
            "blocked",
            details,
            "No complete independently known numerical reference is available",
        )
    else:
        numerical = _assessment("passed", details)
    unsupported = sorted(set(observed.claims) - set(expected.supported_claims))
    details = {
        "unsupported_count": len(unsupported),
        "unsupported_claim_ids": unsupported,
        "structured_claim_audit_complete": observed.claims_complete,
        "scientific_approval_established": False,
    }
    claims = (
        _assessment(
            "failed", details, "Observed structured claims lack independent support"
        )
        if unsupported
        else (
            _assessment("passed", details)
            if observed.claims_complete
            else _assessment(
                "blocked", details, "Structured claim review was not completed"
            )
        )
    )
    missing_tasks = sorted(set(expected.required_tasks) - set(observed.completed_tasks))
    details = {
        "expected_outcome": expected.outcome,
        "observed_outcome": observed.outcome,
        "missing_tasks": missing_tasks,
    }
    completion = (
        _assessment("passed", details)
        if not missing_tasks and observed.outcome == expected.outcome
        else _assessment(
            "failed",
            details,
            "Required task completion or expected refusal/clarification differs",
        )
    )
    invalid = sorted(set(observed.cited_ids) - set(expected.valid_citation_ids))
    details = {
        "cited_count": len(observed.cited_ids),
        "valid_count": len(observed.cited_ids) - len(invalid),
        "invalid_ids": invalid,
        "validity_fraction": (len(observed.cited_ids) - len(invalid))
        / len(observed.cited_ids)
        if observed.cited_ids
        else None,
    }
    citations = (
        _assessment(
            "failed",
            details,
            "Citations include identifiers outside the retained evidence",
        )
        if invalid
        else (
            _assessment("passed", details)
            if observed.cited_ids
            else _assessment(
                "not_run",
                details,
                "No citations were observed; absence is not perfect citation validity",
            )
        )
    )
    return ControllerMetrics(
        controller=observed.controller,
        inventory=inventory,
        numerical=numerical,
        unsupported_claims=claims,
        completion=completion,
        citations=citations,
        telemetry=observed.telemetry,
    )


def compare_controllers(expected, legacy, v1):
    """Exact input mismatch blocks comparison instead of rewriting either run."""
    expected = ExpectedOutcome.model_validate(expected)
    legacy, v1 = (
        ControllerObservation.model_validate(legacy),
        ControllerObservation.model_validate(v1),
    )
    if legacy.controller != "legacy" or v1.controller != "v1":
        raise ValueError("Comparison requires one distinct legacy and v1 observation")
    common = {
        "oracle_sha256": content_sha256(expected),
        "legacy_observation_sha256": content_sha256(legacy),
        "v1_observation_sha256": content_sha256(v1),
        "live_quality_established": False,
    }
    if content_sha256(legacy.input) != content_sha256(v1.input):
        return ControllerComparison(
            status="blocked",
            reason="Question, permissions, scope, snapshot, source, provider or fixture inputs are not exactly matched",
            input_sha256=None,
            legacy=None,
            v1=None,
            **common,
        )
    left, right = derive_metrics(expected, legacy), derive_metrics(expected, v1)
    status = _status(
        [
            getattr(metrics, key).status
            for metrics in (left, right)
            for key in (
                "inventory",
                "numerical",
                "unsupported_claims",
                "completion",
                "citations",
            )
        ]
    )
    return ControllerComparison(
        status=status,
        reason=None
        if status == "passed"
        else "One or more independent controller acceptance metrics did not pass",
        input_sha256=content_sha256(legacy.input),
        legacy=left,
        v1=right,
        **common,
    )


def build_acceptance_report(*, source_revision, requirements, results, comparisons=()):
    requirements = [
        AcceptanceRequirement.model_validate(value) for value in requirements
    ]
    results = [AcceptanceGateResult.model_validate(value) for value in results]
    ids = [item.id for item in requirements]
    if len(ids) != len(set(ids)) or len(results) != len(
        {item.requirement_id for item in results}
    ):
        raise ValueError("Acceptance requirements/results must be distinct")
    by_id = {item.requirement_id: item for item in results}
    if by_id.keys() - set(ids):
        raise ValueError("Acceptance result names an unknown requirement")
    complete = [
        by_id.get(item.id)
        or AcceptanceGateResult(
            requirement_id=item.id,
            status="not_run",
            reason="No attributable result was supplied for this requirement",
            evidence=[],
        )
        for item in requirements
    ]
    phases = {item.id: item.phase for item in requirements}
    local = [
        item.status for item in complete if phases[item.requirement_id] == "preparation"
    ]
    release = [
        item.status for item in complete if phases[item.requirement_id] == "release"
    ]
    preparation_status, release_status = (
        _status(local),
        _status([*local, *release] if release else []),
    )
    return SystemAcceptanceReport(
        source_revision=source_revision,
        requirements=[item.model_dump(mode="json") for item in requirements],
        results=[item.model_dump(mode="json") for item in complete],
        comparisons=[
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in comparisons
        ],
        preparation_status=preparation_status,
        release_status=release_status,
        preparation_complete=preparation_status == "passed",
        release_accepted=release_status == "passed",
    )
