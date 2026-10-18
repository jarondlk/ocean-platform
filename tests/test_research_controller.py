"""C19 executes the actual C17/C14 sealed synthetic stack; no live model/DB."""

from __future__ import annotations

from dataclasses import dataclass
import json
import uuid

import pytest
from sqlalchemy import create_engine, event

import config
from db.app_models import AppBase
from model_runtime import GenerationResult
from orchestration.research_controller import (
    ControllerAdmissionError,
    ResearchController,
)
from schema.context_catalogue import canonical_json
from tests.investigation_support import make_investigation_fixture


class FakeRuntime:
    def __init__(self, actions=(), *, status="completed", before=None):
        self.actions, self.status, self.before = list(actions), status, before
        self.calls = []

    def structured_chat_result(self, **request):
        self.calls.append(request)
        if self.before:
            self.before(len(self.calls))
        action = self.actions.pop(0) if self.actions else {"kind": "finish"}
        content = action if isinstance(action, str) else canonical_json(action)
        return GenerationResult(
            content,
            "synthetic",
            "c19-fake",
            self.status,
            "stop" if self.status == "completed" else "length",
            0.0,
        )


def tool(name, **arguments):
    return {"kind": "tool", "tool": name, "arguments": arguments}


@pytest.fixture(scope="module")
def retained(tmp_path_factory):
    directory = tmp_path_factory.mktemp("c19-actual")
    engine = create_engine(
        "sqlite+pysqlite:///" + str(directory / "separate-v1.sqlite")
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    AppBase.metadata.create_all(engine)
    value = make_investigation_fixture(engine, directory)
    yield value
    engine.dispose()


@dataclass
class Harness:
    retained: object
    state: dict

    def request(self, question, *, pins=(), attachments=()):
        service = self.retained.service
        created = service.invoke(
            "create",
            {
                "name": "C19 synthetic exploration",
                "snapshot_id": self.retained.snapshots[0],
                "scope": self.retained.scope,
                "idempotency_key": str(uuid.uuid4()),
            },
            self.retained.user,
        )
        for kind, refs in [("attach", attachments), ("pin", pins)]:
            for ref in refs:
                created = service.invoke(
                    "context/change",
                    {
                        "investigation_id": created["investigation"]["id"],
                        "expected_revision_id": created["context"]["id"],
                        "idempotency_key": str(uuid.uuid4()),
                        "change": {"op": kind, "reference": ref},
                    },
                    self.retained.user,
                )
        chat = service.invoke(
            "conversations/create",
            {
                "investigation_id": created["investigation"]["id"],
                "name": "Independent C19 question",
                "idempotency_key": str(uuid.uuid4()),
            },
            self.retained.user,
        )
        return {
            "investigation_id": created["investigation"]["id"],
            "conversation_id": chat["conversation"]["id"],
            "revision_id": created["context"]["id"],
            "question": question,
        }

    def ref(self, family="ctd"):
        return {
            "kind": "catalogue",
            "id": self.retained.dataset_ids[family],
            "snapshot_id": self.retained.snapshots[0],
        }

    def controller(self, runtime=None, **kwargs):
        return ResearchController(
            investigations=self.retained.service,
            catalogue=self.retained.service.catalogue,
            identity_provider=lambda: self.state["user"],
            runtime=runtime,
            model="c19-fake" if runtime is not None else None,
            **kwargs,
        )


@pytest.fixture
def actual(retained, monkeypatch):
    monkeypatch.setenv("ENABLE_V1_RESEARCH_CONTROLLER", "true")
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "true")
    for denied in retained.policy.values():
        denied.clear()
    return Harness(retained, {"user": retained.user})


def test_actual_full_inventory_count_is_deterministic_and_never_calls_a_model(actual):
    runtime = FakeRuntime(status="output_limited")
    result = actual.controller(runtime).execute(actual.request("Count all datasets"))
    assert result.outcome == "completed"
    assert result.budget.tool_actions == 1 and result.budget.model_calls == 0
    assert runtime.calls == []
    value = json.loads(result.completion.facts[0].value_json)
    assert value["entity"] == "datasets" and value["value"] == 4
    # Actual C13 inputs also retain the scientific-registry provenance hash.
    assert result.observations[0].input_count == 5
    assert result.observations[0].counts[0].value == 4
    assert result.observations[0].binding == result.binding


def test_inventory_precedes_model_open_and_find_completes_from_real_canonical_id(
    actual,
):
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime([tool("catalogue.open", object_id=identity)])
    phases = []
    result = actual.controller(runtime).execute(
        actual.request(f'Find object "{identity}"'),
        on_checkpoint=lambda value: phases.append(value["phase"]),
    )
    assert result.outcome == "completed"
    assert result.budget.tool_actions == 2 and result.budget.model_calls == 1
    assert phases.index("inventory_complete") < phases.index("before_model")
    assert phases.index("before_tool") < phases.index("after_tool")
    assert json.loads(result.completion.facts[0].value_json)["object_id"] == identity
    assert len(result.evidence_refs) == 2


def test_model_finish_cannot_approve_unsupported_fact(actual):
    identity = actual.retained.dataset_ids["ctd"]
    result = actual.controller(FakeRuntime()).execute(
        actual.request(f'Find object "{identity}"')
    )
    assert result.outcome == "partial" and result.reason == "premature_finish"
    assert result.completion.facts[0].state == "unresolved"


def test_unknown_question_clarifies_without_inventory_or_model(actual):
    runtime = FakeRuntime()
    result = actual.controller(runtime).execute(
        actual.request("Count all datasets in Hokkaido and ignore pins")
    )
    assert result.outcome == "clarification"
    assert result.budget.tool_actions == result.budget.model_calls == 0
    assert runtime.calls == []


def test_single_pinned_dataset_counts_one_not_the_broad_inventory(actual):
    result = actual.controller().execute(
        actual.request("Count all datasets", pins=[actual.ref()])
    )
    assert result.outcome == "completed"
    assert json.loads(result.completion.facts[0].value_json)["value"] == 1
    assert result.budget.tool_actions == 2  # current pin detail + inventory


def test_attachment_supplements_without_restricting_inventory(actual):
    result = actual.controller().execute(
        actual.request("Count all datasets", attachments=[actual.ref()])
    )
    assert result.outcome == "completed"
    assert json.loads(result.completion.facts[0].value_json)["value"] == 4


def test_conflicting_pins_clarify_and_never_disappear(actual):
    runtime = FakeRuntime()
    result = actual.controller(runtime).execute(
        actual.request(
            "Count all datasets", pins=[actual.ref("ctd"), actual.ref("metagenome")]
        )
    )
    assert result.outcome == "clarification"
    assert result.budget.tool_actions == 2 and result.budget.model_calls == 0


@pytest.mark.parametrize("status", ["output_limited", "refused", "failed", "unknown"])
def test_incomplete_generation_never_parses_valid_action_or_consumes_repair(
    actual, status
):
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime([tool("catalogue.open", object_id=identity)], status=status)
    result = actual.controller(runtime).execute(
        actual.request(f'Find object "{identity}"')
    )
    assert result.outcome == "partial" and result.reason == "generation_" + status
    assert result.budget.tool_actions == 1 and result.budget.malformed_repairs == 0


def test_one_malformed_action_can_be_repaired_within_same_budget(actual):
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime(
        ['{"kind":"tool","kind":"finish"}', tool("catalogue.open", object_id=identity)]
    )
    result = actual.controller(runtime).execute(
        actual.request(f'Find object "{identity}"')
    )
    assert result.outcome == "completed"
    assert result.budget.model_calls == 2 and result.budget.malformed_repairs == 1
    assert result.budget.tool_actions == 2


def test_second_malformed_action_stops_without_extra_dispatch(actual):
    identity = actual.retained.dataset_ids["ctd"]
    result = actual.controller(FakeRuntime(["[]", "[]"])).execute(
        actual.request(f'Find object "{identity}"')
    )
    assert result.outcome == "partial" and result.reason == "repair_budget"
    assert result.budget.model_calls == 2 and result.budget.tool_actions == 1


def test_model_cannot_supply_frozen_identity_or_scope(actual):
    identity = actual.retained.dataset_ids["ctd"]
    forged = tool("catalogue.open", object_id=identity, snapshot_id="f" * 64)
    result = actual.controller(FakeRuntime([forged, forged])).execute(
        actual.request(f'Find object "{identity}"')
    )
    assert result.outcome == "partial" and result.budget.tool_actions == 1
    assert result.reason == "repair_budget"


def test_current_identity_change_during_generation_hides_prior_observations(actual):
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime(
        [tool("catalogue.open", object_id=identity)],
        before=lambda _: actual.state.update(user=actual.retained.other),
    )
    result = actual.controller(runtime).execute(
        actual.request(f'Find object "{identity}"')
    )
    assert result.outcome == "unavailable"
    assert result.observations == result.evidence_refs == ()


def test_catalogue_membership_revision_change_invalidates_prior_inventory(actual):
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime(
        [tool("catalogue.open", object_id=identity)],
        before=lambda _: actual.retained.policy[actual.retained.snapshots[0]].add(
            identity
        ),
    )
    result = actual.controller(runtime).execute(
        actual.request(f'Find object "{identity}"')
    )
    assert result.outcome == "unavailable"
    assert result.observations == result.evidence_refs == ()


def test_disabled_controller_never_reads_context_or_calls_model(monkeypatch):
    monkeypatch.setenv("ENABLE_V1_RESEARCH_CONTROLLER", "false")

    def forbidden():
        raise AssertionError(
            "No identity/service/model access before feature admission"
        )

    controller = ResearchController(
        investigations=None, catalogue=None, identity_provider=forbidden
    )
    with pytest.raises(ControllerAdmissionError, match="controller_unavailable"):
        controller.execute(
            {
                "investigation_id": str(uuid.uuid4()),
                "conversation_id": str(uuid.uuid4()),
                "revision_id": str(uuid.uuid4()),
                "question": "Count all datasets",
            }
        )
    assert config.v1_research_controller_enabled({}) is False


def test_checkpoint_failure_before_tool_never_dispatches(actual):
    request = actual.request("Count all datasets")

    def checkpoint(value):
        if value["phase"] == "before_tool":
            raise RuntimeError("sensitive persistence failure")

    with pytest.raises(ControllerAdmissionError, match="checkpoint_unavailable"):
        actual.controller().execute(request, on_checkpoint=checkpoint)


def test_final_checkpoint_revocation_cannot_return_stale_success(actual):
    def checkpoint(value):
        if value["phase"] == "finishing":
            actual.state["user"] = actual.retained.other

    result = actual.controller().execute(
        actual.request("Count all datasets"), on_checkpoint=checkpoint
    )
    assert result.outcome == "unavailable"
    assert result.observations == result.evidence_refs == ()


def test_final_checkpoint_cancellation_wins_over_proposed_success(actual):
    state = {"cancelled": False}

    def checkpoint(value):
        if value["phase"] == "finishing":
            state["cancelled"] = True

    result = actual.controller().execute(
        actual.request("Count all datasets"),
        on_checkpoint=checkpoint,
        cancelled=lambda: state["cancelled"],
    )
    assert result.outcome == "cancelled" and result.reason == "cancelled"


def test_cancellation_after_blocking_model_records_after_step_and_keeps_inventory(
    actual,
):
    state = {"cancelled": False}
    phases = []
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime(
        [tool("catalogue.open", object_id=identity)],
        before=lambda _: state.update(cancelled=True),
    )
    result = actual.controller(runtime).execute(
        actual.request(f'Find object "{identity}"'),
        cancelled=lambda: state["cancelled"],
        on_checkpoint=lambda value: phases.append(value),
    )
    assert result.outcome == "cancelled" and result.budget.tool_actions == 1
    assert len(result.observations) == 1
    assert any(
        value["phase"] == "after_model" and value.get("returned_value_discarded")
        for value in phases
    )


def test_revoke_before_provider_admission_does_not_send_private_prompt(actual):
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime()

    def checkpoint(value):
        if value["phase"] == "before_model":
            actual.state["user"] = actual.retained.other

    result = actual.controller(runtime).execute(
        actual.request(f'Find object "{identity}"'), on_checkpoint=checkpoint
    )
    assert result.outcome == "unavailable" and runtime.calls == []
    assert result.observations == ()


def test_blocking_model_overrun_preserves_after_checkpoint_and_cannot_finish(actual):
    clock = [0.0]
    phases = []
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime(
        [tool("catalogue.open", object_id=identity)],
        before=lambda _: clock.__setitem__(0, 181.0),
    )
    result = actual.controller(runtime, clock=lambda: clock[0]).execute(
        actual.request(f'Find object "{identity}"'),
        on_checkpoint=lambda value: phases.append(value),
    )
    assert result.outcome == "partial" and result.reason == "time_budget"
    assert result.budget.active_elapsed_seconds == 181.0
    assert result.budget.tool_actions == 1
    assert any(
        value["phase"] == "after_model" and value.get("reason") == "time_budget"
        for value in phases
    )


def test_tool_budget_does_not_reset_after_failed_attempts(actual):
    identity = actual.retained.dataset_ids["ctd"]
    actions = [tool("catalogue.open", object_id="synthetic:missing")] * 12
    result = actual.controller(FakeRuntime(actions)).execute(
        actual.request(f'Find object "{identity}"')
    )
    assert result.outcome == "partial" and result.reason == "action_budget"
    assert result.budget.tool_actions == 12
    assert len(result.observations) == 1


def test_original_submitted_revision_survives_new_shared_head(actual):
    identity = actual.retained.dataset_ids["ctd"]
    request = actual.request(f'Find object "{identity}"')

    def update(_):
        actual.retained.service.invoke(
            "context/change",
            {
                "investigation_id": request["investigation_id"],
                "expected_revision_id": request["revision_id"],
                "idempotency_key": str(uuid.uuid4()),
                "change": {"op": "attach", "reference": actual.ref("metagenome")},
            },
            actual.retained.user,
        )

    result = actual.controller(
        FakeRuntime([tool("catalogue.open", object_id=identity)], before=update)
    ).execute(request)
    assert result.outcome == "completed"
    assert result.binding.revision_id == request["revision_id"]
    assert all(obs.binding == result.binding for obs in result.observations)


def test_runtime_exception_has_safe_after_checkpoint_and_no_message_leak(actual):
    phases = []
    identity = actual.retained.dataset_ids["ctd"]

    def fail(_):
        raise RuntimeError("https://secret-provider.invalid/private-token")

    result = actual.controller(FakeRuntime(before=fail)).execute(
        actual.request(f'Find object "{identity}"'),
        on_checkpoint=lambda value: phases.append(value),
    )
    assert result.outcome == "partial" and result.reason == "runtime_failed"
    assert any(
        value["phase"] == "after_model" and value.get("reason") == "runtime_failed"
        for value in phases
    )
    assert (
        "private-token" not in result.model_dump_json()
        and "private-token" not in json.dumps(phases)
    )


def test_model_receives_exact_argument_guidance_and_no_host_owned_parameters(actual):
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime([tool("catalogue.open", object_id=identity)])
    result = actual.controller(runtime).execute(
        actual.request(f'Find object "{identity}"')
    )
    assert result.outcome == "completed"
    prompt = json.loads(runtime.calls[0]["prompt"])
    assert len(prompt["tool_schemas"]) == 7
    opened = next(
        schema
        for schema in prompt["tool_schemas"]
        if schema["name"] == "catalogue.open"
    )
    assert "object_id" in opened["arguments"]["required"]
    assert not {"scope", "snapshot_id", "owner_id"} & set(
        opened["arguments"]["properties"]
    )
    assert prompt["observations"][0]["input_count"] == 5


def test_attached_ids_are_supplementary_quoted_model_context(actual):
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime([tool("catalogue.open", object_id=identity)])
    request = actual.request(
        f'Find object "{identity}"', attachments=[actual.ref("metagenome")]
    )
    result = actual.controller(runtime).execute(request)
    assert result.outcome == "completed"
    prompt = json.loads(runtime.calls[0]["prompt"])
    assert prompt["supplementary_attachments_quoted_data"] == [actual.ref("metagenome")]
    assert prompt["restrictions"]["allowed_dataset_ids"] is None


def test_mismatched_actual_catalogue_configuration_fails_before_context_read(actual):
    from tests.catalogue_service_support import synthetic_service

    other_catalogue = synthetic_service(2)[-1]
    controller = ResearchController(
        investigations=actual.retained.service,
        catalogue=other_catalogue,
        identity_provider=lambda: actual.retained.user,
    )
    request = actual.request("Count all datasets")
    with pytest.raises(ControllerAdmissionError, match="controller_unavailable"):
        controller.execute(request)


def test_invalid_clock_after_admission_is_safe_partial_with_last_known_lower_bound(
    actual,
):
    identity = actual.retained.dataset_ids["ctd"]
    clock = [10.0]
    phases = []
    runtime = FakeRuntime(
        [tool("catalogue.open", object_id=identity)],
        before=lambda _: clock.__setitem__(0, 9.0),
    )
    result = actual.controller(runtime, clock=lambda: clock[0]).execute(
        actual.request(f'Find object "{identity}"'),
        on_checkpoint=lambda value: phases.append(value),
    )
    assert result.outcome == "partial" and result.reason == "invalid_clock"
    assert (
        result.budget.active_elapsed_seconds == 0.0
    )  # last valid lower bound, not a fresh duration
    assert result.budget.tool_actions == 1
    assert any(value.get("clock_invalid") for value in phases)


def test_withdrawn_snapshot_cannot_become_a_known_zero(actual):
    request = actual.request("Count all datasets")
    original = actual.retained.service.load_for_submission

    def unavailable(**_):
        raise RuntimeError("private withdrawn snapshot details")

    actual.retained.service.load_for_submission = unavailable
    try:
        with pytest.raises(ControllerAdmissionError, match="context_unavailable"):
            actual.controller().execute(request)
    finally:
        actual.retained.service.load_for_submission = original


@pytest.mark.parametrize("final_time", [180.0, float("nan")])
def test_final_closed_budget_cannot_complete_after_boundary_or_first_clock_failure(
    actual, final_time
):
    finishing = {"values": None}

    def clock():
        if finishing["values"]:
            return finishing["values"].pop(0)
        return 0.0

    def checkpoint(value):
        if value["phase"] == "finishing":
            finishing["values"] = [179.0, final_time]

    result = actual.controller(clock=clock).execute(
        actual.request("Count all datasets"), on_checkpoint=checkpoint
    )
    assert result.outcome == "partial"
    assert result.reason == (
        "invalid_clock" if final_time != final_time else "time_budget"
    )
    assert result.budget.active_elapsed_seconds == (
        179.0 if final_time != final_time else 180.0
    )


@pytest.mark.parametrize("phase", ["before_tool", "before_model"])
def test_transient_invalid_checkpoint_clock_stops_future_effects(
    actual, monkeypatch, phase
):
    from orchestration.research_controller import _Exploration

    readings = []
    original_checkpoint = _Exploration.checkpoint
    original_execute = actual.retained.service.catalogue.execute
    calls = []

    def checkpoint(exploration, current, **details):
        if current == phase:
            readings.append(float("nan"))
        return original_checkpoint(exploration, current, **details)

    def execute(name, *args, **kwargs):
        calls.append(name)
        return original_execute(name, *args, **kwargs)

    monkeypatch.setattr(_Exploration, "checkpoint", checkpoint)
    monkeypatch.setattr(actual.retained.service.catalogue, "execute", execute)
    identity = actual.retained.dataset_ids["ctd"]
    runtime = FakeRuntime([tool("catalogue.open", object_id=identity)])
    result = actual.controller(
        runtime, clock=lambda: readings.pop(0) if readings else 0.0
    ).execute(
        actual.request(f'Find object "{identity}"'),
        on_checkpoint=lambda _: None,
    )
    assert result.outcome == "partial" and result.reason == "invalid_clock"
    assert runtime.calls == []
    # C17 still rechecks snapshot access through overview on finalization.
    effect_calls = [name for name in calls if name != "catalogue.overview"]
    assert effect_calls == ([] if phase == "before_tool" else ["catalogue.query"])


def test_actual_registered_sst_count_keeps_native_scope_and_receipt(actual):
    identity = actual.retained.dataset_ids["remote_sensing"]
    runtime = FakeRuntime(
        [
            tool(
                "catalogue.query",
                operation_id="c13.operation",
                operation_version="c13-v1",
                input_ids=[identity],
                parameters={"operation_id": "c11.count", "operation_version": "c11-v1"},
            )
        ]
    )
    result = actual.controller(runtime).execute(
        actual.request(
            f'Run operation "c11.count" version "c11-v1" on dataset "{identity}"'
        )
    )
    assert result.outcome == "completed"
    assert result.budget.tool_actions == 2 and result.budget.model_calls == 1
    assert result.observations[-1].operation_id == "c13.operation"
    assert result.observations[-1].query_completion == "complete"
    assert result.observations[-1].input_count >= 1


def test_actual_edna_unknown_coverage_never_completes_from_retained_row_counts(actual):
    identity = actual.retained.dataset_ids["edna_metabarcoding"]
    runtime = FakeRuntime([tool("catalogue.coverage", object_id=identity)])
    result = actual.controller(runtime).execute(
        actual.request(f'Show coverage for dataset "{identity}"')
    )
    assert result.outcome == "partial" and result.reason == "premature_finish"
    assert result.observations[-1].query_completion == "complete"
    assert "coverage_known" not in result.observations[-1].known_fields
    assert not result.completion.complete


def test_actual_known_empty_scope_returns_zero_without_a_model_or_unavailable_claim(
    actual,
):
    runtime = FakeRuntime(status="failed")
    question = (
        'Count datasets where ctd.station="C19-empty-synthetic-station" and '
        "metagenome.enabled=false and remote_sensing.enabled=false and "
        "edna_metabarcoding.enabled=false"
    )
    result = actual.controller(runtime).execute(actual.request(question))
    assert result.outcome == "completed" and result.completion.complete
    assert json.loads(result.completion.facts[0].value_json)["value"] == 0
    assert runtime.calls == []
