"""C19 cooperative active-time accounting; no queue, worker or provider lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Callable


class ExplorationStopped(Exception):
    """A bounded machine reason; never carries model/source/private text."""

    def __init__(self, reason: str):
        if reason not in {
            "cancelled",
            "time_budget",
            "action_budget",
            "repair_budget",
            "invalid_clock",
            "budget_closed",
        }:
            raise ValueError("Unknown stop reason")
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class BudgetState:
    active_seconds: float
    tool_actions: int
    repairs: int


class ActiveBudget:
    """Charge wall time, including preflight and blocking operations, to one run.

    Restored counters are trusted host checkpoints, never model arguments. The
    clock starts on construction; close freezes elapsed time while waiting for
    clarification or continuation outside this active invocation. Cancellation
    is cooperative at admission/return boundaries, not preemptive termination.
    """

    def __init__(
        self,
        *,
        active_seconds: float = 180,
        tool_actions: int = 12,
        repairs: int = 1,
        clock: Callable[[], float] = time.monotonic,
        cancelled: Callable[[], bool] = lambda: False,
        restored: BudgetState | None = None,
    ):
        if (
            type(active_seconds) not in (int, float)
            or not math.isfinite(active_seconds)
            or not 0 < active_seconds <= 180
        ):
            raise ValueError("Active budget must be positive and at most180 seconds")
        if type(tool_actions) is not int or not 1 <= tool_actions <= 12:
            raise ValueError("Tool budget must be between1 and12")
        if type(repairs) is not int or not 0 <= repairs <= 1:
            raise ValueError("Repair budget must be zero or one")
        if not callable(clock) or not callable(cancelled):
            raise TypeError("Explicit clock and cancellation callbacks required")
        initial = restored or BudgetState(0.0, 0, 0)
        if (
            type(initial.active_seconds) not in (int, float)
            or not math.isfinite(initial.active_seconds)
            or initial.active_seconds < 0
            or type(initial.tool_actions) is not int
            or not 0 <= initial.tool_actions <= tool_actions
            or type(initial.repairs) is not int
            or not 0 <= initial.repairs <= repairs
        ):
            raise ValueError("Restored budget is invalid")
        self.max_seconds, self.max_tools, self.max_repairs = (
            float(active_seconds),
            tool_actions,
            repairs,
        )
        self.clock, self.cancelled = clock, cancelled
        self.initial_seconds = float(initial.active_seconds)
        self.tools, self.repairs = initial.tool_actions, initial.repairs
        self.started = self._time()
        self.last_time = self.started
        self.closed: BudgetState | None = None

    def _time(self):
        value = self.clock()
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ExplorationStopped("invalid_clock")
        return float(value)

    def snapshot(self):
        if self.closed is not None:
            return self.closed
        now = self._time()
        if now < self.last_time:
            raise ExplorationStopped("invalid_clock")
        self.last_time = now
        return BudgetState(
            self.initial_seconds + now - self.started, self.tools, self.repairs
        )

    def last_known_state(self):
        """A lower bound only when an invalid clock prevents fresh measurement."""
        return self.closed or BudgetState(
            self.initial_seconds + self.last_time - self.started,
            self.tools,
            self.repairs,
        )

    def check(self):
        if self.closed is not None:
            raise ExplorationStopped("budget_closed")
        state = self.snapshot()
        cancellation = self.cancelled()
        if type(cancellation) is not bool:
            raise TypeError("Cancellation callback must return a boolean")
        if cancellation:
            raise ExplorationStopped("cancelled")
        if state.active_seconds >= self.max_seconds:
            raise ExplorationStopped("time_budget")
        return state

    def reserve_tool(self):
        self.check()
        if self.tools >= self.max_tools:
            raise ExplorationStopped("action_budget")
        self.tools += 1
        return self.snapshot()

    def reserve_repair(self):
        self.check()
        if self.repairs >= self.max_repairs:
            raise ExplorationStopped("repair_budget")
        self.repairs += 1
        return self.snapshot()

    def close(self, *, clock_failed=False):
        self.closed = self.last_known_state() if clock_failed else self.snapshot()
        return self.closed
