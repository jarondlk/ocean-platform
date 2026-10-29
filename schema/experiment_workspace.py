"""C25 public execution projections; no launch, physical-proof or release authority."""
from __future__ import annotations

import base64
import hashlib
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from schema.context_catalogue import Identifier, LocalizedText, Sha256
from schema.investigations import ContextReference, InvestigationRequest, PositiveVersion, UUIDString
from schema.research_experiments import ExperimentAddressRequest, ExperimentContextBinding, ExperimentHashes, FileName

EXECUTION_VERSION = 'research-experiment-executions-v1'
MAX_ARTIFACT_CHUNK = 256 * 1024
MAX_OUTPUT_BYTES = 50 * 1024 * 1024
Cursor = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
Source = Literal['synthetic-fixture', 'retained-operator']
ExecutionState = Literal['queued', 'running', 'cancelling', 'completed', 'failed', 'cancelled', 'timed_out']
DisplayCell = Annotated[str, StringConstraints(max_length=4096)] | None


class ExecutionCapabilityRequest(InvestigationRequest):
    pass


class ExecutionCapability(InvestigationRequest):
    transport: Literal['http-v1', 'unavailable']
    source: Literal['unavailable', 'synthetic-fixture', 'retained-operator']
    start_enabled: Literal[False] = False
    cancel_enabled: bool
    artifacts_enabled: bool
    reason: LocalizedText | None

    @field_validator('start_enabled', mode='before')
    @classmethod
    def no_launch_coercion(cls, value):
        if value is not False:
            raise ValueError('This public contract has no start action')
        return value

    @model_validator(mode='after')
    def unavailable_is_explicit(self):
        if self.transport == 'unavailable':
            if self.source != 'unavailable' or self.cancel_enabled or self.artifacts_enabled or self.reason is None:
                raise ValueError('Unavailable execution has no runtime authority')
        elif self.source == 'unavailable' or self.reason is not None:
            raise ValueError('Configured execution must retain its actual source')
        return self


class ExecutionCapabilityResponse(InvestigationRequest):
    version: Literal['research-experiment-executions-v1'] = EXECUTION_VERSION
    capability: ExecutionCapability


class ExecutionBindingRequest(ExperimentAddressRequest, ExperimentContextBinding):
    expected_version: PositiveVersion
    expected_proposal_revision_id: UUIDString
    expected_hashes: ExperimentHashes


class ExecutionStatusRequest(ExecutionBindingRequest):
    execution_id: UUIDString | None = None


class ExecutionEventsRequest(ExecutionBindingRequest):
    execution_id: UUIDString
    after_cursor: Cursor = 0
    limit: Annotated[int, Field(strict=True, ge=1, le=500)] = 100


class ExecutionCancelRequest(ExecutionBindingRequest):
    execution_id: UUIDString
    idempotency_key: UUIDString


class ExecutionArtifactRequest(ExecutionBindingRequest):
    execution_id: UUIDString
    artifact_id: Identifier
    expected_sha256: Sha256
    offset: Annotated[int, Field(strict=True, ge=0, le=MAX_OUTPUT_BYTES)] = 0
    limit: Annotated[int, Field(strict=True, ge=1, le=MAX_ARTIFACT_CHUNK)] = MAX_ARTIFACT_CHUNK


class ExecutionArtifact(InvestigationRequest):
    id: Identifier
    name: FileName
    kind: Literal['table', 'raster']
    media_type: Literal['application/json', 'text/csv', 'image/png']
    sha256: Sha256
    size_bytes: Annotated[int, Field(strict=True, ge=1, le=MAX_OUTPUT_BYTES)]
    attachment_reference: ContextReference | None = None
    authority: Literal['experimental'] = 'experimental'
    scientific_approval: Literal['not_independently_verified'] = 'not_independently_verified'

    @model_validator(mode='after')
    def safe_profile(self):
        profiles = {('table', 'application/json'): '.json', ('table', 'text/csv'): '.csv', ('raster', 'image/png'): '.png'}
        extension = profiles.get((self.kind, self.media_type))
        if extension is None or not self.name.endswith(extension):
            raise ValueError('Only validated table and PNG profiles are public')
        if self.attachment_reference is not None and self.attachment_reference.kind != 'artifact':
            raise ValueError('An output cannot become catalogue authority')
        return self


class ExecutionSnapshot(InvestigationRequest):
    id: UUIDString
    state: ExecutionState
    state_revision: PositiveVersion
    source: Source
    execution_performed: bool
    termination_verified: bool
    termination_proof_sha256: Sha256 | None
    cancel_requested: bool
    event_cursor: Cursor = 0
    latest_event_cursor: Cursor
    outputs_manifest_sha256: Sha256 | None
    artifacts: Annotated[list[ExecutionArtifact], Field(max_length=32)]
    authority: Literal['experimental'] = 'experimental'
    scientific_approval: Literal['not_independently_verified'] = 'not_independently_verified'

    @model_validator(mode='after')
    def honest_observations(self):
        terminal = self.state in {'completed', 'failed', 'cancelled', 'timed_out'}
        if self.event_cursor > self.latest_event_cursor or self.event_cursor != 0:
            raise ValueError('Status does not consume event pages')
        if self.source == 'synthetic-fixture':
            if self.execution_performed or self.termination_verified or self.termination_proof_sha256 is not None:
                raise ValueError('Synthetic execution cannot claim physical observations')
        elif terminal and (not self.termination_verified or self.termination_proof_sha256 is None):
            raise ValueError('Real terminal state requires verified termination evidence')
        if self.source == 'retained-operator' and self.state == 'completed' and not self.execution_performed:
            raise ValueError('Real completed output requires an execution observation')
        if self.termination_verified != (self.termination_proof_sha256 is not None) or (self.termination_verified and not terminal):
            raise ValueError('Termination is a separate verified terminal observation')
        if self.state == 'cancelling' and not self.cancel_requested:
            raise ValueError('Cancelling requires a retained request')
        if self.artifacts and (self.state != 'completed' or self.outputs_manifest_sha256 is None):
            raise ValueError('Only retained completed outputs may be inspected')
        if len({a.id for a in self.artifacts}) != len(self.artifacts) or len({a.name for a in self.artifacts}) != len(self.artifacts):
            raise ValueError('Output identities must be distinct')
        if sum(a.size_bytes for a in self.artifacts) > MAX_OUTPUT_BYTES:
            raise ValueError('Output files exceed their total byte bound')
        return self


class ExecutionResponse(InvestigationRequest):
    version: Literal['research-experiment-executions-v1'] = EXECUTION_VERSION
    experiment_id: UUIDString
    proposal_revision_id: UUIDString
    proposal_version: PositiveVersion
    binding: ExperimentContextBinding
    hashes: ExperimentHashes
    capability: ExecutionCapability
    execution: ExecutionSnapshot | None


class ExecutionEvent(InvestigationRequest):
    cursor: PositiveVersion
    kind: Annotated[str, StringConstraints(pattern=r'^[a-z][a-z0-9_]{0,63}$')]
    summary: LocalizedText


class ExecutionEventsResponse(ExecutionResponse):
    execution_id: UUIDString
    after_cursor: Cursor
    items: Annotated[list[ExecutionEvent], Field(max_length=500)]
    next_cursor: Cursor
    latest_event_cursor: Cursor
    has_more: bool

    @model_validator(mode='after')
    def retained_consecutive_events(self):
        if (self.execution is None or self.execution.id != self.execution_id
                or self.execution.latest_event_cursor != self.latest_event_cursor
                or [item.cursor for item in self.items] != list(range(self.after_cursor + 1, self.after_cursor + len(self.items) + 1))
                or self.next_cursor != self.after_cursor + len(self.items)
                or self.next_cursor > self.latest_event_cursor
                or self.has_more != (self.next_cursor < self.latest_event_cursor)
                or (self.has_more and not self.items)):
            raise ValueError('Execution event pages must advance consecutively')
        return self


class CancellationAcknowledgement(InvestigationRequest):
    idempotency_key: UUIDString
    status: Literal['requested', 'already_terminal']
    termination_confirmed: Literal[False] = False

    @field_validator('termination_confirmed', mode='before')
    @classmethod
    def request_is_not_termination(cls, value):
        if value is not False:
            raise ValueError('Cancellation acknowledgement is not termination')
        return value


class ExecutionCancelResponse(ExecutionResponse):
    cancellation: CancellationAcknowledgement

    @model_validator(mode='after')
    def acknowledged_intent_is_retained(self):
        if self.execution is None:
            raise ValueError('Cancellation must identify a retained execution')
        if self.cancellation.status == 'requested' and not self.execution.cancel_requested:
            raise ValueError('Cancellation request must be durably retained')
        if self.cancellation.status == 'already_terminal' and self.execution.state not in {'completed', 'failed', 'cancelled', 'timed_out'}:
            raise ValueError('A cancellation acknowledgement cannot invent termination')
        return self


class TablePreview(InvestigationRequest):
    columns: Annotated[list[Annotated[str, StringConstraints(max_length=4096)]], Field(min_length=1, max_length=128)]
    rows: Annotated[list[list[DisplayCell]], Field(max_length=100)]
    total_rows: Cursor
    truncated: bool
    cells_are_display_strings: Literal[True] = True

    @field_validator('cells_are_display_strings', mode='before')
    @classmethod
    def display_marker_is_exact(cls, value):
        if value is not True:
            raise ValueError('Display strings require an exact marker')
        return value

    @model_validator(mode='after')
    def rectangular(self):
        if (any(len(row) != len(self.columns) for row in self.rows) or len(self.rows) > self.total_rows
                or self.truncated != (len(self.rows) < self.total_rows)):
            raise ValueError('Table preview retains its exact displayed shape')
        return self


class ExecutionArtifactResponse(ExecutionResponse):
    artifact: ExecutionArtifact
    offset: Annotated[int, Field(strict=True, ge=0, le=MAX_OUTPUT_BYTES)]
    next_offset: Annotated[int, Field(strict=True, ge=0, le=MAX_OUTPUT_BYTES)]
    eof: bool
    content_base64: Annotated[str, StringConstraints(max_length=(MAX_ARTIFACT_CHUNK + 2) // 3 * 4)]
    preview: TablePreview | None

    @model_validator(mode='after')
    def bound_chunk(self):
        try:
            raw = base64.b64decode(self.content_base64, validate=True)
        except ValueError:
            raise ValueError('Artifact chunks require canonical base64') from None
        if (base64.b64encode(raw).decode() != self.content_base64
                or self.next_offset != self.offset + len(raw)
                or self.next_offset > self.artifact.size_bytes
                or self.eof != (self.next_offset == self.artifact.size_bytes)
                or (not raw and not self.eof) or len(raw) > MAX_ARTIFACT_CHUNK
                or self.execution is None
                or self.artifact.model_dump(mode='json') not in [item.model_dump(mode='json') for item in self.execution.artifacts]
                or (self.preview is not None and (self.offset != 0 or self.artifact.kind != 'table'))):
            raise ValueError('Artifact chunk is outside its retained manifest')
        if self.offset == 0 and self.eof and hashlib.sha256(raw).hexdigest() != self.artifact.sha256:
            raise ValueError('Complete artifact bytes disagree with their hash')
        return self


EXECUTION_REQUEST_MODELS = {
    'capability': ExecutionCapabilityRequest, 'status': ExecutionStatusRequest,
    'events': ExecutionEventsRequest, 'cancel': ExecutionCancelRequest, 'artifact': ExecutionArtifactRequest,
}
EXECUTION_RESPONSE_MODELS = {
    'capability': ExecutionCapabilityResponse, 'status': ExecutionResponse,
    'events': ExecutionEventsResponse, 'cancel': ExecutionCancelResponse, 'artifact': ExecutionArtifactResponse,
}
