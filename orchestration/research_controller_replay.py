"""Versioned host-only durable replay port; no database or external dispatch.

The host journals raw outcomes transactionally under a lease. A committed
logical step is replayed without another physical call or budget reservation.
An uncommitted request may repeat and bill again; the host charges uncertainty
before restoration and fences old attempt tokens independently of this port.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import math
from pathlib import Path
from typing import Protocol

from model_runtime import GenerationResult, GenerationUsage
from schema.context_catalogue import canonical_json
from schema.research_controller import canonical_hash

REPLAY_VERSION = "research-controller-replay-v1"


class ReplayIntegrityError(ValueError):
    """Safe mismatch: persisted bytes/configuration are not the expected run."""


class ControllerReplayJournal(Protocol):
    def bind(self, manifest: dict) -> dict: ...
    def lookup_step(self, step_id: str, request_sha256: str) -> dict | None: ...
    def prepare_step(
        self,
        step_id: str,
        kind: str,
        request_sha256: str,
        request: dict,
        budget: dict,
        checkpoint: dict,
    ) -> str: ...
    def commit_step(
        self, token: str, outcome: dict, budget: dict, checkpoint: dict
    ) -> None: ...


def controller_fingerprint() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = (
        "orchestration/research_controller.py",
        "orchestration/research_controller_budget.py",
        "orchestration/research_controller_replay.py",
        "orchestration/research_controller_scope.py",
        "orchestration/research_controller_observations.py",
        "schema/research_controller.py",
        "model_runtime.py",
        "schema/catalogue_service.py",
        "schema/context_catalogue.py",
    )
    return canonical_hash(
        {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}
    )


def generation_payload(result: GenerationResult) -> dict:
    if not isinstance(result, GenerationResult):
        raise ReplayIntegrityError("Invalid generation replay contract")
    # Raw content remains private. Diagnostics alone cannot replay malformed or
    # incomplete outputs, and missing usage must not become invented zeros.
    value = asdict(result)
    restore_generation(value)
    return value


def runtime_fingerprint(runtime, explicit_identity=None):
    values = (
        {
            key: getattr(runtime, key)
            for key in (
                "provider",
                "endpoint",
                "project",
                "location",
                "embedding_dim",
                "max_attempts",
                "retry_initial_seconds",
                "request_timeout_seconds",
            )
            if hasattr(runtime, key)
        }
        if explicit_identity is None
        else explicit_identity
    )
    return {
        "class": type(runtime).__module__ + "." + type(runtime).__qualname__,
        "configuration_sha256": canonical_hash(values),
    }


def restore_generation(value: dict) -> GenerationResult:
    fields = {
        "content",
        "provider",
        "model",
        "status",
        "finish_reason",
        "elapsed_seconds",
        "usage",
        "max_output_tokens",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ReplayIntegrityError("Invalid generation replay fields")
    if not isinstance(value["status"], str) or value["status"] not in {
        "completed",
        "output_limited",
        "refused",
        "failed",
        "unknown",
    }:
        raise ReplayIntegrityError("Invalid generation replay status")
    if not all(isinstance(value[key], str) for key in ("content", "provider", "model")):
        raise ReplayIntegrityError("Invalid generation replay text")
    if (
        type(value["elapsed_seconds"]) not in (int, float)
        or not math.isfinite(value["elapsed_seconds"])
        or value["elapsed_seconds"] < 0
        or value["finish_reason"] is not None
        and not isinstance(value["finish_reason"], str)
        or value["max_output_tokens"] is not None
        and (
            type(value["max_output_tokens"]) is not int
            or value["max_output_tokens"] < 0
        )
    ):
        raise ReplayIntegrityError("Invalid generation replay metadata")
    usage = value["usage"]
    if usage is not None:
        if not isinstance(usage, dict) or set(usage) != {
            "input_tokens",
            "output_tokens",
            "total_tokens",
        }:
            raise ReplayIntegrityError("Invalid generation replay usage")
        if any(
            item is not None and (type(item) is not int or item < 0)
            for item in usage.values()
        ):
            raise ReplayIntegrityError("Invalid generation replay counts")
        usage = GenerationUsage(**usage)
    result = GenerationResult(**{**value, "usage": usage})
    canonical_json(value).encode("utf-8")
    return result


class ReplaySession:
    def __init__(self, journal: ControllerReplayJournal):
        self.journal = journal

    def lookup(self, step_id: str, request: dict) -> dict | None:
        result = self.journal.lookup_step(step_id, canonical_hash(request))
        if result is None:
            return None
        if (
            not isinstance(result, dict)
            or set(result) != {"outcome", "outcome_sha256"}
            or not isinstance(result["outcome"], dict)
            or canonical_hash(result["outcome"]) != result["outcome_sha256"]
        ):
            raise ReplayIntegrityError("Corrupt committed replay outcome")
        value = result["outcome"]
        if value.get("version") != REPLAY_VERSION:
            raise ReplayIntegrityError("Unsupported replay outcome version")
        common = {"version", "kind", "accepted", "projection_sha256"}
        expected = {
            "tool": common | {"status", "body", "reason"},
            "model": common | {"generation", "reason"},
            "repair": common,
        }
        if (
            value.get("kind") not in expected
            or set(value) != expected[value["kind"]]
            or type(value.get("accepted")) is not bool
            or not isinstance(value.get("projection_sha256"), str)
        ):
            raise ReplayIntegrityError("Invalid replay outcome fields")
        if value["kind"] == "tool":
            status = value["status"]
            if (
                status is not None
                and (type(status) is not int or not 100 <= status <= 599)
                or value["body"] is not None
                and not isinstance(value["body"], dict)
                or value["accepted"]
                and (status != 200 or not isinstance(value["body"], dict))
            ):
                raise ReplayIntegrityError("Invalid replay tool response")
        return value

    def prepare(
        self, step_id: str, kind: str, request: dict, budget: dict, checkpoint: dict
    ) -> str:
        token = self.journal.prepare_step(
            step_id, kind, canonical_hash(request), request, budget, checkpoint
        )
        if not isinstance(token, str) or not token:
            raise ReplayIntegrityError("Invalid replay attempt reservation")
        return token

    def commit(self, token: str, outcome: dict, budget: dict, checkpoint: dict):
        value = {"version": REPLAY_VERSION, **outcome}
        canonical_hash(value)
        self.journal.commit_step(token, value, budget, checkpoint)
