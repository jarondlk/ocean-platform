"""C20 strict public wire contract; authority and private replay stay server-owned."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from retrieval.source_scope import EvidenceScope
from schema.context_catalogue import Sha256
from schema.investigations import ContextReference, InvestigationRequest, UUIDString

VERSION = "research-runs-v1"
SafeCursor = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=500)]
Question = Annotated[str, StringConstraints(min_length=1, max_length=8000)]


class RunRequest(InvestigationRequest):
    @field_validator("question", "answer", check_fields=False)
    @classmethod
    def visible_input(cls, value):
        if not value.strip() or len(value.encode("utf-8")) > 32000:
            raise ValueError("A bounded visible question is required")
        if any(ord(char) < 32 and char not in "\n\r\t" or ord(char) == 127 for char in value):
            raise ValueError("Input contains invalid controls")
        return value


class RunConversationRequest(RunRequest):
    investigation_id: UUIDString
    conversation_id: UUIDString


class RunSubmitRequest(RunConversationRequest):
    revision_id: UUIDString
    expected_snapshot_id: Sha256
    expected_payload_sha256: Sha256
    question: Question
    idempotency_key: UUIDString


class RunAddressRequest(RunConversationRequest):
    run_id: UUIDString


class RunMutationRequest(RunAddressRequest):
    idempotency_key: UUIDString


class RunClarifyRequest(RunMutationRequest):
    clarification_id: UUIDString
    answer: Question


class RunEventsRequest(RunAddressRequest):
    after_cursor: SafeCursor = 0
    limit: PageLimit = 100


class RunListRequest(RunConversationRequest):
    limit: PageLimit = 25
    cursor: Annotated[str, StringConstraints(min_length=1, max_length=4096)] | None = None


RUN_REQUEST_MODELS: dict[str, type[RunRequest]] = {
    "submit": RunSubmitRequest,
    "status": RunAddressRequest,
    "events": RunEventsRequest,
    "cancel": RunMutationRequest,
    "clarify": RunClarifyRequest,
    "continue": RunMutationRequest,
    "list": RunListRequest,
}


class RunBinding(InvestigationRequest):
    investigation_id: UUIDString
    conversation_id: UUIDString
    revision_id: UUIDString
    snapshot_id: Sha256
    payload_sha256: Sha256


class RunContext(InvestigationRequest):
    binding: RunBinding
    scope: EvidenceScope
    attachments: Annotated[list[ContextReference], Field(max_length=256)]
    pins: Annotated[list[ContextReference], Field(max_length=256)]


class RunText(InvestigationRequest):
    en: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    ja: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


RunStatus = Literal[
    "queued", "running", "awaiting_clarification", "awaiting_approval",
    "completed", "partial", "failed", "cancelled",
]
EventKind = Literal[
    "accepted", "started", "progress", "clarification", "approval", "resumed",
    "completed", "partial", "failed", "cancelled",
]


class RunPublicEvent(InvestigationRequest):
    cursor: Annotated[int, Field(strict=True, ge=1, le=9007199254740991)]
    run_id: UUIDString
    elapsed_ms: SafeCursor
    kind: EventKind
    summary: RunText


class ResearchRun(InvestigationRequest):
    id: UUIDString
    context: RunContext
    question: Question
    status: RunStatus
    active_elapsed_ms: SafeCursor
    event_cursor: Literal[0]
    latest_event_cursor: SafeCursor
    activity: Annotated[list[RunPublicEvent], Field(max_length=0)]
    continuation_of: UUIDString | None
    clarification: RunText | None
    clarification_id: UUIDString | None
    result: None
    error: RunText | None
    synthetic: Literal[False]

    @field_validator("event_cursor", mode="before")
    @classmethod
    def zero_cursor(cls, value):
        if type(value) is not int or value != 0:
            raise ValueError("Snapshot cursor must be integer zero")
        return value

    @field_validator("synthetic", mode="before")
    @classmethod
    def production_run(cls, value):
        if value is not False:
            raise ValueError("Production runs must have an explicit false fixture flag")
        return value

    @model_validator(mode="after")
    def clarification_consistent(self):
        waiting = self.status == "awaiting_clarification"
        if waiting != (self.clarification_id is not None and self.clarification is not None):
            raise ValueError("Clarification wait must have a current token and prompt")
        if not waiting and (self.clarification_id is not None or self.clarification is not None):
            raise ValueError("Only a clarification wait exposes a current prompt")
        return self


class RunResponse(InvestigationRequest):
    version: Literal["research-runs-v1"]
    run: ResearchRun


class RunListResponse(InvestigationRequest):
    version: Literal["research-runs-v1"]
    items: Annotated[list[ResearchRun], Field(max_length=500)]
    next_cursor: Annotated[str, StringConstraints(min_length=1, max_length=4096)] | None


class RunEventsResponse(InvestigationRequest):
    version: Literal["research-runs-v1"]
    run_id: UUIDString
    binding: RunBinding
    after_cursor: SafeCursor
    next_cursor: SafeCursor
    latest_event_cursor: SafeCursor
    has_more: bool
    events: Annotated[list[RunPublicEvent], Field(max_length=500)]

    @model_validator(mode="after")
    def consecutive_events(self):
        expected = self.after_cursor
        for item in self.events:
            expected += 1
            if item.cursor != expected or item.run_id != self.run_id:
                raise ValueError("Events must be consecutive and belong to one run")
        if self.next_cursor != expected or expected > self.latest_event_cursor:
            raise ValueError("Event cursor is invalid")
        if self.has_more != (expected < self.latest_event_cursor):
            raise ValueError("Event high water is inconsistent")
        return self


def validate_run_response(name: str, result: dict, request: RunRequest) -> dict:
    """Encode only the public shape and verify its binding against the request."""
    model = RunListResponse if name == "list" else RunEventsResponse if name == "events" else RunResponse
    parsed = model.model_validate(result)
    if isinstance(parsed, RunEventsResponse):
        bindings = [parsed.binding]
        if parsed.run_id != request.run_id or parsed.after_cursor != request.after_cursor:
            raise ValueError("Event address differs from the request")
        if len(parsed.events) > request.limit:
            raise ValueError("Event page exceeds the request")
    else:
        runs = parsed.items if isinstance(parsed, RunListResponse) else [parsed.run]
        bindings = [run.context.binding for run in runs]
        if isinstance(parsed, RunListResponse) and len(runs) > request.limit:
            raise ValueError("Run page exceeds the request")
        if name in {"status", "cancel", "clarify"} and parsed.run.id != request.run_id:
            raise ValueError("Run address differs from the request")
        if name == "continue" and parsed.run.continuation_of != request.run_id:
            raise ValueError("Continuation differs from its parent")
    for binding in bindings:
        if (binding.investigation_id, binding.conversation_id) != (request.investigation_id, request.conversation_id):
            raise ValueError("Run context differs from the request")
        if name == "submit" and (
            binding.revision_id, binding.snapshot_id, binding.payload_sha256
        ) != (request.revision_id, request.expected_snapshot_id, request.expected_payload_sha256):
            raise ValueError("Submitted run differs from its frozen revision")
    encoded = parsed.model_dump(mode="json")
    # EvidenceScope's public canonical form omits unset filters. Expanding them
    # to null while encoding a run would differ from the frozen C17 payload.
    if not isinstance(parsed, RunEventsResponse):
        encoded_runs = encoded["items"] if isinstance(parsed, RunListResponse) else [encoded["run"]]
        for item, run in zip(encoded_runs, runs):
            item["context"]["scope"] = run.context.scope.canonical()
    return encoded
