"""C26 independent metric accounting; fixtures never establish live acceptance."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from evaluation.system_acceptance import (
    build_acceptance_report,
    compare_controllers,
    content_sha256,
    derive_metrics,
    parse_acceptance_json,
)
from schema.system_acceptance import (
    AcceptanceRequirement,
    ControllerComparison,
    ControllerObservation,
    SystemAcceptanceReport,
)

SOURCE = "sha256:" + "a" * 64


def observation(controller="v1"):
    unknown = {"basis": "unknown", "value": None}
    return {
        "version": "system-controller-observation-v1",
        "controller": controller,
        "input": {
            "question_id": "count-all",
            "question": "Count all datasets",
            "permissions": ["chat:use", "data:read"],
            "scope": {"sources": ["synthetic"]},
            "snapshot_id": "b" * 64,
            "source_revision": SOURCE,
            "fixture_id": "synthetic:independent",
            "fixture_sha256": "c" * 64,
            "provider": {
                "mode": "not_invoked",
                "provider": None,
                "model": None,
                "configuration": {},
            },
        },
        "evidence_kind": "actual-service-synthetic",
        "inventory_state": "complete",
        "inventory_ids": ["dataset:a", "dataset:b"],
        "numbers": {"datasets": "2"},
        "claims": ["count:datasets:2"],
        "claims_complete": True,
        "completed_tasks": ["count"],
        "cited_ids": ["evidence:count"],
        "outcome": "completed",
        "telemetry": {
            "timing": {"basis": "measured", "value": 0.001},
            "tool_calls": {"basis": "measured", "value": 1},
            "input_tokens": deepcopy(unknown),
            "output_tokens": deepcopy(unknown),
            "cost": deepcopy(unknown),
        },
        "evidence": [
            {
                "id": "capture:" + controller,
                "sha256": "d" * 64,
                "source_revision": SOURCE,
                "kind": "actual-service-synthetic",
            }
        ],
    }


def oracle():
    return {
        "inventory_ids": ["dataset:a", "dataset:b"],
        "numbers": {"datasets": "2"},
        "supported_claims": ["count:datasets:2"],
        "required_tasks": ["count"],
        "valid_citation_ids": ["evidence:count"],
        "outcome": "completed",
    }


def requirements():
    return [
        {
            "id": "R01",
            "phase": "preparation",
            "owner": "C26",
            "evidence_kind": "actual-service-synthetic",
        },
        {
            "id": "live.hosting",
            "phase": "release",
            "owner": "C24",
            "evidence_kind": "live-service",
        },
    ]


def passed():
    return {
        "requirement_id": "R01",
        "status": "passed",
        "reason": None,
        "evidence": observation()["evidence"],
    }


def test_matched_inputs_have_independent_metrics_without_invented_live_billing():
    result = compare_controllers(oracle(), observation("legacy"), observation())
    assert result.status == "passed" and result.input_sha256 == content_sha256(
        observation()["input"]
    )
    assert result.legacy.controller == "legacy" and result.v1.controller == "v1"
    assert result.v1.inventory.details["matched_count"] == 2
    assert (
        result.v1.telemetry.cost.value is None
        and result.live_quality_established is False
    )
    assert (
        result.v1.unsupported_claims.details["scientific_approval_established"] is False
    )


@pytest.mark.parametrize("left,right", [(False, 0), (True, 1), (1, 1.0)])
def test_exact_manifest_matching_never_uses_python_bool_integer_or_float_equality(
    left, right
):
    legacy, new = observation("legacy"), observation()
    legacy["input"]["scope"]["typed_value"] = left
    new["input"]["scope"]["typed_value"] = right
    assert compare_controllers(oracle(), legacy, new).status == "blocked"


@pytest.mark.parametrize(
    "field,value",
    [
        ("question_id", "other"),
        ("question", "Different question"),
        ("permissions", ["data:read"]),
        ("scope", {"sources": ["different"]}),
        ("snapshot_id", "e" * 64),
        ("source_revision", "git:" + "f" * 40),
        ("fixture_id", "another-fixture"),
        ("fixture_sha256", "0" * 64),
        (
            "provider",
            {
                "mode": "fixture",
                "provider": "scripted",
                "model": "fixture-v1",
                "configuration": {"seed": 1},
            },
        ),
    ],
)
def test_each_input_mismatch_blocks_instead_of_rebinding_either_controller(
    field, value
):
    new = observation()
    new["input"][field] = value
    if field == "source_revision":
        new["evidence"][0]["source_revision"] = value
    result = compare_controllers(oracle(), observation("legacy"), new)
    assert result.status == "blocked" and result.input_sha256 is None
    assert result.legacy is None and result.v1 is None


def test_citation_validity_cannot_hide_inventory_numerical_unsupported_or_completion_failures():
    observed = observation()
    observed.update(
        inventory_ids=["dataset:a"],
        numbers={"datasets": "1"},
        claims=["independent_scientific_approval"],
        completed_tasks=[],
    )
    metrics = derive_metrics(oracle(), observed)
    assert metrics.citations.status == "passed"
    assert [
        getattr(metrics, name).status
        for name in ("inventory", "numerical", "unsupported_claims", "completion")
    ] == ["failed"] * 4
    assert (
        compare_controllers(oracle(), observation("legacy"), observed).status
        == "failed"
    )


def test_100000_inventory_accounts_for_rank26_and_later_pages_without_preview_denominators():
    ids = ["object:" + str(index).zfill(6) for index in range(100000)]
    expected = oracle()
    expected["inventory_ids"] = ids
    expected["numbers"] = {"datasets": "100000"}
    observed = observation()
    observed["inventory_ids"] = ids
    observed["numbers"] = {"datasets": "100000"}
    assert derive_metrics(expected, observed).inventory.status == "passed"
    observed["inventory_ids"] = ids[:25]
    failed = derive_metrics(expected, observed).inventory
    assert failed.status == "failed" and failed.details["missing_count"] == 99975
    assert failed.details["diagnostics_truncated"] is True
    observed["inventory_state"] = "partial"
    assert derive_metrics(expected, observed).inventory.status == "blocked"


@pytest.mark.parametrize("state", ["unknown", "unavailable", "partial"])
def test_zero_is_distinct_from_unknown_unavailable_and_incomplete_inventory(state):
    expected = oracle()
    expected.update(inventory_ids=[], numbers={"datasets": "0"})
    observed = observation()
    observed.update(inventory_ids=[], numbers={"datasets": "0"}, inventory_state=state)
    assert derive_metrics(expected, observed).inventory.status == "blocked"
    observed["inventory_state"] = "complete"
    assert derive_metrics(expected, observed).inventory.status == "passed"


def test_exact_machine_int64_decimal_answers_do_not_round_and_unknown_is_not_zero():
    expected = oracle()
    expected["numbers"] = {
        "count": "9223372036854775807",
        "ratio": "0.10000000000000000001",
    }
    observed = observation()
    observed["numbers"] = dict(expected["numbers"])
    assert derive_metrics(expected, observed).numerical.status == "passed"
    observed["numbers"]["count"] = "9223372036854775808"
    assert derive_metrics(expected, observed).numerical.status == "failed"
    observed["numbers"] = {"count": None, "ratio": "0.10000000000000000001"}
    assert derive_metrics(expected, observed).numerical.status == "failed"
    expected["numbers"]["count"] = None
    observed["numbers"]["count"] = "0"
    assert derive_metrics(expected, observed).numerical.status == "blocked"


def test_unsupported_audit_and_citation_absence_remain_explicit():
    observed = observation()
    observed["claims_complete"] = False
    observed["cited_ids"] = []
    metrics = derive_metrics(oracle(), observed)
    assert metrics.unsupported_claims.status == "blocked"
    assert (
        metrics.citations.status == "not_run"
        and metrics.citations.details["validity_fraction"] is None
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda x: x["inventory_ids"].append(x["inventory_ids"][0]),
        lambda x: x["cited_ids"].append(x["cited_ids"][0]),
        lambda x: x["evidence"].append(x["evidence"][0]),
        lambda x: x["evidence"][0].update(source_revision="sha256:" + "f" * 64),
        lambda x: x["telemetry"]["timing"].update(value=float("nan")),
        lambda x: x["telemetry"]["cost"].update(basis="measured", value=float("inf")),
        lambda x: x["telemetry"]["tool_calls"].update(value=True),
        lambda x: x["telemetry"]["tool_calls"].update(value=1.5),
        lambda x: x["telemetry"]["input_tokens"].update(
            basis="fixture", value=9007199254740992
        ),
        lambda x: x["telemetry"]["cost"].update(basis="fixture", value=-1),
        lambda x: x["telemetry"]["cost"].update(value=0),
        lambda x: x["telemetry"]["cost"].update(basis="measured", value=0),
        lambda x: x["numbers"].update(datasets=2),
        lambda x: x["numbers"].update(datasets="NaN"),
        lambda x: x["numbers"].update(datasets="1e999999999"),
        lambda x: x["input"]["scope"].update(unsafe=float("nan")),
        lambda x: x["input"].update(question="\ud800"),
        lambda x: x.update(evidence_kind="unrun-live"),
        lambda x: x.update(unknown_result=True),
    ],
)
def test_unknown_malformed_duplicate_unsafe_and_nonfinite_observations_fail_closed(
    mutate,
):
    observed = observation()
    mutate(observed)
    with pytest.raises((ValueError, TypeError, UnicodeError)):
        ControllerObservation.model_validate(observed)


def test_fixture_usage_is_explicit_and_real_provider_mode_cannot_be_forged():
    observed = observation()
    observed["input"]["provider"] = {
        "mode": "fixture",
        "provider": "script",
        "model": "c26-fixture-v1",
        "configuration": {"temperature": 0},
    }
    observed["telemetry"]["input_tokens"] = {"basis": "fixture", "value": 17}
    assert (
        ControllerObservation.model_validate(observed).telemetry.input_tokens.basis
        == "fixture"
    )
    observed["input"]["provider"]["mode"] = "live"
    with pytest.raises(ValidationError):
        ControllerObservation.model_validate(observed)


def test_missing_gate_is_not_run_and_local_preparation_does_not_promote_release():
    report = build_acceptance_report(
        source_revision=SOURCE, requirements=requirements(), results=[passed()]
    )
    assert report.preparation_complete and report.preparation_status == "passed"
    assert report.release_status == "not_run" and not report.release_accepted
    assert report.results[1].status == "not_run"
    blocked = {
        "requirement_id": "live.hosting",
        "status": "blocked",
        "reason": "Concrete isolated host/auth targets are absent",
        "evidence": [],
    }
    report = build_acceptance_report(
        source_revision=SOURCE, requirements=requirements(), results=[passed(), blocked]
    )
    assert (
        report.preparation_complete
        and report.release_status == "blocked"
        and not report.release_accepted
    )
    altered = report.model_dump(mode="json")
    altered["release_accepted"] = True
    with pytest.raises(ValidationError):
        SystemAcceptanceReport.model_validate(altered)


def test_failed_predecessor_integration_prevents_preparation_complete():
    result = passed()
    result.update(
        status="failed",
        reason="Owner-bound experiment attachment rejected by an actual service",
    )
    report = build_acceptance_report(
        source_revision=SOURCE, requirements=requirements(), results=[result]
    )
    assert report.preparation_status == "failed" and not report.preparation_complete
    assert report.release_status == "failed" and not report.release_accepted


@pytest.mark.parametrize(
    "kind", ["duplicate", "unknown", "source", "evidence", "no-evidence"]
)
def test_gate_accounting_rejects_duplicates_unknown_ids_changed_source_and_invented_passes(
    kind,
):
    results = [passed()]
    if kind == "duplicate":
        results.append(passed())
    elif kind == "unknown":
        results[0]["requirement_id"] = "not-in-matrix"
    elif kind == "source":
        results[0]["evidence"][0]["source_revision"] = "git:" + "1" * 40
    elif kind == "evidence":
        results[0]["evidence"].append(results[0]["evidence"][0])
    else:
        results[0]["evidence"] = []
    with pytest.raises(ValueError):
        build_acceptance_report(
            source_revision=SOURCE, requirements=requirements(), results=results
        )


def test_original_physical_receipt_is_historical_and_cannot_satisfy_current_release():
    historical = {
        "id": "C23.original",
        "phase": "preparation",
        "owner": "C23",
        "evidence_kind": "original-physical",
    }
    result = {
        "requirement_id": historical["id"],
        "status": "passed",
        "reason": None,
        "evidence": [
            {
                "id": "C23.immutable",
                "source_revision": "git:" + "1" * 40,
                "sha256": "9" * 64,
                "kind": "original-physical",
            }
        ],
    }
    report = build_acceptance_report(
        source_revision=SOURCE,
        requirements=[historical, requirements()[1]],
        results=[result],
    )
    assert report.preparation_complete and not report.release_accepted
    with pytest.raises(ValueError):
        AcceptanceRequirement.model_validate({**historical, "phase": "release"})


def test_comparison_status_cannot_be_rewritten_to_pass_after_a_metric_failure():
    observed = observation()
    observed["numbers"] = {"datasets": "1"}
    result = compare_controllers(oracle(), observation("legacy"), observed).model_dump(
        mode="json"
    )
    result["status"] = "passed"
    result["reason"] = None
    with pytest.raises(ValidationError):
        ControllerComparison.model_validate(result)


def test_parsed_models_are_revalidated_after_nested_mutation():
    observed = ControllerObservation.model_validate(observation())
    observed.input.scope["unsafe"] = float("nan")
    with pytest.raises(ValueError):
        derive_metrics(oracle(), observed)


def test_actual_legacy_and_v1_share_published_source_rows_with_native_wrappers_explicit(
    tmp_path,
):
    from tests.system_acceptance_comparison_support import run_publication_comparison

    result = run_publication_comparison(tmp_path, source_revision=SOURCE)
    assert result["comparison"]["status"] == "passed"
    assert result["comparison"]["live_quality_established"] is False
    assert result["observations"][0]["input"] == result["observations"][1]["input"]
    assert (
        result["observations"][0]["numbers"]
        == result["observations"][1]["numbers"]
        == result["expected"]["numbers"]
    )
    native = result["native_bindings"]
    assert native["legacy_analysis_id"] == native["shared_source_snapshot_id"]
    assert native["v1_controller_snapshot_id"] == native["v1_registry_snapshot_id"]
    assert native["identical_native_wrapper_ids_claimed"] is False
    assert (
        result["model_calls"]["legacy"] == 0
        and result["model_calls"]["v1_scripted_fixture"] > 0
    )
    assert result["legacy_count_probe"]["status"] == "blocked"
    assert result["legacy_count_probe"]["model_invoked"] is False
    altered = deepcopy(result["observations"][1])
    altered["numbers"]["ranking:A"] = "999"
    assert (
        compare_controllers(
            result["expected"], result["observations"][0], altered
        ).v1.numerical.status
        == "failed"
    )


@pytest.mark.parametrize(
    "raw",
    [
        '{"status":"failed","status":"passed"}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":9007199254740992}',
        b"\xff",
    ],
)
def test_acceptance_json_never_silently_repairs_duplicate_nonfinite_unsafe_or_invalid_utf8(
    raw,
):
    with pytest.raises(ValueError):
        parse_acceptance_json(raw)


def test_acceptance_json_is_bounded_and_preserves_int64_strings():
    assert parse_acceptance_json('{"count":"9223372036854775807"}') == {
        "count": "9223372036854775807"
    }
    with pytest.raises(ValueError):
        parse_acceptance_json('{"large":"xxxxxxxx"}', maximum_bytes=4)
