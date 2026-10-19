"""Actual sealed C17/C14 execution with a deterministic private replay journal."""

import copy

import pytest

from model_runtime import GenerationResult, GenerationUsage
from orchestration.research_controller import ControllerAdmissionError, _Exploration
from orchestration.research_controller_budget import ExplorationStopped
from orchestration.research_controller_replay import (
    ReplayIntegrityError,
    generation_payload,
    restore_generation,
)
from schema.research_controller import canonical_hash
from tests import test_research_controller as fixtures

FakeRuntime, tool = fixtures.FakeRuntime, fixtures.tool
actual, retained = fixtures.actual, fixtures.retained


class Journal:
    def __init__(self, crash_kind=None, before_commit=False):
        self.manifest = None
        self.steps = {}
        self.attempts = []
        self.budget = {}
        self.checkpoint = {}
        self.crash_kind = crash_kind
        self.before_commit = before_commit

    def bind(self, manifest):
        if self.manifest is None:
            self.manifest = copy.deepcopy(manifest)
        elif manifest != self.manifest:
            raise ValueError("Changed replay manifest")
        return {
            "budget": self.budget,
            "clock_invalid": self.checkpoint.get("clock_invalid", False),
            "actor_binding": self.checkpoint.get("actor_binding"),
            "catalogue_policy_revision": self.checkpoint.get(
                "catalogue_policy_revision"
            ),
            "reserved_repair_steps": [
                attempt["step"]
                for attempt in self.attempts
                if attempt["kind"] == "repair"
            ],
        }

    def lookup_step(self, step_id, request_sha256):
        value = self.steps.get(step_id)
        if value is None:
            return None
        assert value["request_sha256"] == request_sha256
        return copy.deepcopy(
            {"outcome": value["outcome"], "outcome_sha256": value["outcome_sha256"]}
        )

    def prepare_step(self, step_id, kind, request_sha256, request, budget, checkpoint):
        assert step_id not in self.steps
        token = str(len(self.attempts))
        self.attempts.append(
            {
                "step": step_id,
                "kind": kind,
                "request_sha256": request_sha256,
                "request": copy.deepcopy(request),
                "token": token,
            }
        )
        self.budget, self.checkpoint = copy.deepcopy(budget), copy.deepcopy(checkpoint)
        return token

    def commit_step(self, token, outcome, budget, checkpoint):
        attempt = self.attempts[int(token)]
        crash = attempt["kind"] == self.crash_kind
        if crash and self.before_commit:
            self.crash_kind = None
            raise OSError("Synthetic process interruption before commit")
        self.steps[attempt["step"]] = {
            "request_sha256": attempt["request_sha256"],
            "outcome": copy.deepcopy(outcome),
            "outcome_sha256": canonical_hash(outcome),
        }
        self.budget, self.checkpoint = copy.deepcopy(budget), copy.deepcopy(checkpoint)
        if crash:
            self.crash_kind = None
            raise OSError("Synthetic lost committed acknowledgement")


def controller(actual, runtime=None):
    return actual.controller(runtime, clock=lambda: 0.0)


def find(actual):
    identity = actual.retained.dataset_ids["ctd"]
    return actual.request(f'Find object "{identity}"'), tool(
        "catalogue.open", object_id=identity
    )


def test_committed_inventory_replay_has_no_second_dispatch_or_counter_charge(actual):
    journal = Journal()
    request = actual.request("Count all datasets")
    first = controller(actual).execute(request, journal=journal)
    attempts = len(journal.attempts)
    second = controller(actual).execute(request, journal=journal)
    assert first == second and second.outcome == "completed"
    assert second.budget.tool_actions == 1 and len(journal.attempts) == attempts == 1
    assert len(second.observations) == 1


@pytest.mark.parametrize("kind", ["tool", "model", "repair"])
def test_lost_commit_ack_replays_exact_raw_outcomes_without_repeating_effect(
    actual, kind
):
    request, action = find(actual)
    runtime = FakeRuntime(["malformed", action] if kind == "repair" else [action])
    journal = Journal(crash_kind=kind)
    with pytest.raises(ControllerAdmissionError, match="checkpoint_unavailable"):
        controller(actual, runtime).execute(request, journal=journal)
    before = len(runtime.calls)
    result = controller(actual, runtime).execute(request, journal=journal)
    assert result.outcome == "completed"
    assert len(runtime.calls) == (2 if kind == "repair" else 1)
    assert result.budget.tool_actions == 2 and result.budget.malformed_repairs == int(
        kind == "repair"
    )
    if kind == "model":
        assert len(runtime.calls) == before
        raw = journal.steps["turn:0:model:0"]["outcome"]["generation"]
        assert raw["content"] and raw["status"] == "completed" and raw["usage"] is None


def test_uncertain_uncommitted_model_attempt_is_charged_again_and_may_repeat(actual):
    request, action = find(actual)
    runtime = FakeRuntime([action, action])
    journal = Journal(crash_kind="model", before_commit=True)
    with pytest.raises(ControllerAdmissionError):
        controller(actual, runtime).execute(request, journal=journal)
    result = controller(actual, runtime).execute(request, journal=journal)
    assert result.outcome == "completed" and len(runtime.calls) == 2
    assert result.budget.model_calls == 2 and result.budget.tool_actions == 2
    assert (
        len(
            [
                attempt
                for attempt in journal.attempts
                if attempt["step"] == "turn:0:model:0"
            ]
        )
        == 2
    )


def test_pending_pure_repair_reservation_is_not_spent_a_second_time(actual):
    request, action = find(actual)
    runtime = FakeRuntime(["malformed", action])
    journal = Journal(crash_kind="repair", before_commit=True)
    with pytest.raises(ControllerAdmissionError):
        controller(actual, runtime).execute(request, journal=journal)
    assert journal.budget["malformed_repairs"] == 1
    result = controller(actual, runtime).execute(request, journal=journal)
    assert result.outcome == "completed" and len(runtime.calls) == 2
    assert result.budget.malformed_repairs == 1
    assert (
        len([attempt for attempt in journal.attempts if attempt["kind"] == "repair"])
        == 2
    )


def test_committed_second_malformed_output_never_receives_another_repair(actual):
    request, _ = find(actual)
    runtime = FakeRuntime(["malformed one", "malformed two"])
    journal = Journal()
    first = controller(actual, runtime).execute(request, journal=journal)
    second = controller(actual, runtime).execute(request, journal=journal)
    assert first == second and second.reason == "repair_budget"
    assert len(runtime.calls) == 2 and second.budget.malformed_repairs == 1


def test_corrupt_committed_outcome_cannot_become_fact_support(actual):
    journal = Journal()
    request = actual.request("Count all datasets")
    controller(actual).execute(request, journal=journal)
    journal.steps["inventory:1"]["outcome"]["body"]["rows"][0]["count"] = 999999
    result = controller(actual).execute(request, journal=journal)
    assert result.outcome == "unavailable" and result.reason == "replay_integrity"
    assert (
        not result.observations
        and not result.evidence_refs
        and len(journal.attempts) == 1
    )


def test_restored_invalid_clock_is_sticky_but_committed_inventory_is_recovered(actual):
    request, action = find(actual)
    runtime = FakeRuntime([action])
    journal = Journal(crash_kind="model")
    with pytest.raises(ControllerAdmissionError):
        controller(actual, runtime).execute(request, journal=journal)
    journal.checkpoint["clock_invalid"] = True
    result = controller(actual, runtime).execute(request, journal=journal)
    assert (
        result.outcome == "partial"
        and result.reason == "invalid_clock"
        and result.observations
    )
    assert len(runtime.calls) == 1 and len(journal.attempts) == 2


def test_model_return_after_deadline_is_retained_as_discarded_and_not_accepted_on_replay(
    actual,
):
    request, action = find(actual)
    clock = [0.0]
    runtime = FakeRuntime([action], before=lambda _: clock.__setitem__(0, 181.0))
    journal = Journal()
    first = actual.controller(runtime, clock=lambda: clock[0]).execute(
        request, journal=journal
    )
    assert first.outcome == "partial" and first.reason == "time_budget"
    saved = journal.steps["turn:0:model:0"]["outcome"]
    assert (
        not saved["accepted"]
        and saved["reason"] == "time_budget"
        and saved["generation"]["content"]
    )
    second = controller(actual, runtime).execute(request, journal=journal)
    assert second.outcome == "partial" and second.reason == "time_budget"
    assert len(runtime.calls) == 1 and len(second.observations) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"elapsed_seconds": float("nan")},
        {"elapsed_seconds": -1.0},
        {"elapsed_seconds": True},
        {"max_output_tokens": True},
        {"status": "invented"},
        {"usage": {"input_tokens": True, "output_tokens": None, "total_tokens": None}},
    ],
)
def test_generation_replay_rejects_nonfinite_or_forged_metadata(change):
    value = generation_payload(
        GenerationResult("{}", "synthetic", "fixed", "completed", "stop", 0.0)
    )
    with pytest.raises(ReplayIntegrityError):
        restore_generation({**value, **change})


@pytest.mark.parametrize("status", ["output_limited", "refused", "failed", "unknown"])
def test_incomplete_raw_generation_retained_and_replayed_without_parsing_or_repair(
    actual, status
):
    request, action = find(actual)
    runtime = FakeRuntime([action], status=status)
    journal = Journal()
    first = controller(actual, runtime).execute(request, journal=journal)
    second = controller(actual, runtime).execute(request, journal=journal)
    assert first == second and second.reason == "generation_" + status
    assert len(runtime.calls) == 1 and second.budget.malformed_repairs == 0
    raw = journal.steps["turn:0:model:0"]["outcome"]["generation"]
    assert raw["status"] == status and raw["content"] and raw["usage"] is None


@pytest.mark.parametrize(
    "charge", [{"active_elapsed_seconds": 180.0}, {"tool_actions": 12}]
)
def test_exhausted_restart_reconstructs_committed_inventory_before_stopping_new_effects(
    actual, charge
):
    request, action = find(actual)
    runtime = FakeRuntime([action])
    journal = Journal(crash_kind="model")
    with pytest.raises(ControllerAdmissionError):
        controller(actual, runtime).execute(request, journal=journal)
    journal.budget.update(charge)
    result = controller(actual, runtime).execute(request, journal=journal)
    assert result.outcome == "partial" and result.observations
    assert len(runtime.calls) == 1 and len(journal.attempts) == 2
    assert result.reason in {"time_budget", "action_budget"}


def test_current_authorization_and_configuration_remain_authoritative(actual):
    journal = Journal()
    request = actual.request("Count all datasets")
    controller(actual).execute(request, journal=journal)
    actual.retained.policy[actual.retained.snapshots[0]].add(
        actual.retained.dataset_ids["ctd"]
    )
    with pytest.raises(ControllerAdmissionError):
        controller(actual).execute(request, journal=journal)
    assert len(journal.attempts) == 1


def test_raw_generation_nullable_usage_roundtrips_without_inventing_zero():
    value = GenerationResult(
        "not JSON",
        "synthetic",
        "fixed-model",
        "output_limited",
        "length",
        2.5,
        GenerationUsage(input_tokens=None, output_tokens=0, total_tokens=None),
        4096,
    )
    restored = restore_generation(generation_payload(value))
    assert (
        restored == value
        and restored.usage.input_tokens is None
        and restored.usage.output_tokens == 0
    )


def test_changed_question_or_limits_cannot_reuse_an_existing_input_manifest(actual):
    journal = Journal()
    request = actual.request("Count all datasets")
    controller(actual).execute(request, journal=journal)
    with pytest.raises(ControllerAdmissionError):
        actual.controller(clock=lambda: 0.0, limits={"tool_actions": 11}).execute(
            request, journal=journal
        )
    with pytest.raises(ControllerAdmissionError):
        controller(actual).execute(
            {**request, "question": "How many datasets are available"}, journal=journal
        )
    assert len(journal.attempts) == 1


def test_nonzero_budget_without_replay_journal_cannot_pretend_to_resume(actual):
    with pytest.raises(ControllerAdmissionError, match="checkpoint_unavailable"):
        controller(actual).execute(
            actual.request("Count all datasets"), restored_budget={"tool_actions": 1}
        )


@pytest.mark.parametrize(
    "code,exception",
    [
        ("replay_integrity", ReplayIntegrityError),
        ("access_denied", ControllerAdmissionError),
        ("authentication_required", ControllerAdmissionError),
        ("not_found", ControllerAdmissionError),
        ("budget_exhausted", ExplorationStopped),
        ("lease_lost", ControllerAdmissionError),
        ("unknown_storage_error", ControllerAdmissionError),
    ],
)
def test_journal_machine_errors_map_to_safe_integrity_authorization_or_retry(
    code, exception
):
    class Failure(Exception):
        pass

    def fail():
        error = Failure("private database details must not escape")
        error.code = code
        raise error

    with pytest.raises(exception) as caught:
        _Exploration.replay_call(None, fail)
    assert "private database" not in str(caught.value)
    if code in {"lease_lost", "unknown_storage_error"}:
        assert caught.value.code == "checkpoint_unavailable"


def test_explicit_new_segment_reuses_verified_inventory_but_not_parent_terminal_model_decision(
    actual,
):
    request, action = find(actual)
    parent = Journal()
    parent_runtime = FakeRuntime([{"kind": "finish"}])
    original = controller(actual, parent_runtime).execute(request, journal=parent)
    assert original.outcome == "partial" and original.reason == "premature_finish"
    child = Journal()
    child.steps = {
        key: copy.deepcopy(value)
        for key, value in parent.steps.items()
        if key.startswith(("pin:", "inventory:"))
    }
    child_runtime = FakeRuntime([action])
    continued = controller(actual, child_runtime).execute(request, journal=child)
    assert continued.outcome == "completed" and len(child_runtime.calls) == 1
    assert continued.budget.tool_actions == continued.budget.model_calls == 1
    assert len(child.attempts) == 2 and len(parent_runtime.calls) == 1
    assert (
        parent.steps["turn:0:model:0"]["outcome"]["generation"]["content"]
        == '{"kind":"finish"}'
    )
