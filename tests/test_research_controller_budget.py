"""C19 active budgets survive host restoration and stop between actual effects."""

import math

import pytest

from orchestration.research_controller_budget import (
    ActiveBudget,
    BudgetState,
    ExplorationStopped,
)


class Clock:
    value = 0.0

    def __call__(self):
        return self.value


def test_defaults_allow_exactly_twelve_attempts_and_one_repair():
    clock = Clock()
    budget = ActiveBudget(clock=clock)
    for count in range(1, 13):
        assert budget.reserve_tool().tool_actions == count
    with pytest.raises(ExplorationStopped, match="action_budget"):
        budget.reserve_tool()
    assert budget.reserve_repair().repairs == 1
    with pytest.raises(ExplorationStopped, match="repair_budget"):
        budget.reserve_repair()


def test_elapsed_admission_and_blocking_overrun_do_not_authorize_a_next_effect():
    clock = Clock()
    budget = ActiveBudget(clock=clock)
    clock.value = 179.999
    budget.reserve_tool()
    clock.value = 180.001
    with pytest.raises(ExplorationStopped, match="time_budget"):
        budget.check()
    assert budget.close().active_seconds == 180.001
    assert budget.snapshot().tool_actions == 1


def test_resume_never_resets_tool_time_or_repair_counters():
    clock = Clock()
    clock.value = 500
    budget = ActiveBudget(clock=clock, restored=BudgetState(179, 11, 1))
    assert budget.reserve_tool().tool_actions == 12
    clock.value = 501
    with pytest.raises(ExplorationStopped, match="time_budget"):
        budget.check()
    assert budget.close() == BudgetState(180, 12, 1)
    clock.value = 9999
    assert budget.snapshot() == BudgetState(180, 12, 1)


def test_cancel_hook_blocks_before_effect_and_after_blocking_return():
    state = {"cancelled": False}
    budget = ActiveBudget(clock=lambda: 0, cancelled=lambda: state["cancelled"])
    budget.reserve_tool()
    state["cancelled"] = True
    with pytest.raises(ExplorationStopped, match="cancelled"):
        budget.check()
    assert budget.close().tool_actions == 1
    denied = ActiveBudget(clock=lambda: 0, cancelled=lambda: True)
    with pytest.raises(ExplorationStopped, match="cancelled"):
        denied.reserve_tool()
    assert denied.snapshot().tool_actions == 0


@pytest.mark.parametrize("value", [True, 0, -1, 181, math.inf, math.nan, "180"])
def test_no_implicit_budget_expansion_or_invalid_duration(value):
    with pytest.raises(ValueError):
        ActiveBudget(active_seconds=value)


@pytest.mark.parametrize("value", [True, 0, -1, 13, 1.5])
def test_invalid_tool_limits(value):
    with pytest.raises(ValueError):
        ActiveBudget(tool_actions=value)


@pytest.mark.parametrize(
    "state",
    [
        BudgetState(-1, 0, 0),
        BudgetState(0, True, 0),
        BudgetState(0, 13, 0),
        BudgetState(0, 0, 2),
    ],
)
def test_invalid_restored_counters(state):
    with pytest.raises(ValueError):
        ActiveBudget(restored=state)


def test_backward_and_nonfinite_clock_fail_closed():
    clock = Clock()
    budget = ActiveBudget(clock=clock)
    clock.value = -1
    with pytest.raises(ExplorationStopped, match="invalid_clock"):
        budget.check()
    with pytest.raises(ExplorationStopped, match="invalid_clock"):
        ActiveBudget(clock=lambda: math.nan)


def test_invalid_cancel_result_cannot_be_treated_as_authorization():
    budget = ActiveBudget(clock=lambda: 0, cancelled=lambda: "false")
    with pytest.raises(TypeError):
        budget.reserve_tool()


def test_closed_budget_cannot_authorize_another_effect():
    budget = ActiveBudget(clock=lambda: 0)
    assert budget.close() == BudgetState(0, 0, 0)
    with pytest.raises(ExplorationStopped, match="budget_closed"):
        budget.reserve_tool()
    assert budget.close() == BudgetState(0, 0, 0)
