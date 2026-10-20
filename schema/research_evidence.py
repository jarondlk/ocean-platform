"""C21 independent evidence and structured-answer wire and trusted worker ports.

Only host-projected facts and retained bytes may populate answers. C20's terminal
wire and rows remain unchanged. Raw payloads, prompts and model journals stay private.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from retrieval.source_scope import EvidenceScope
from schema.context_catalogue import Identifier, LocalizedText, ResultColumn, Sha256
from schema.investigations import ContextReference, InvestigationRequest, PositiveVersion, UUIDString
from schema.research_controller import (
    BudgetSnapshot, CompletionAssessment, ControllerBinding, ControllerLimits, ControllerResult, SemanticCount,
)
from schema.research_runs import PageLimit, SafeCursor

EVIDENCE_VERSION = 'research-evidence-v1'
ANSWER_VERSION = 'research-answers-v1'
Text = Annotated[str, StringConstraints(min_length=1, max_length=10000)]
Locale = Literal['en', 'ja']
ReceiptId = Annotated[str, StringConstraints(pattern=r'^c21:receipt:[a-f0-9]{64}$', min_length=76, max_length=76)]
AccessRevision = Sha256


class RunEvidenceRequest(InvestigationRequest):
    investigation_id: UUIDString
    conversation_id: UUIDString
    run_id: UUIDString
    input_version: PositiveVersion


class EvidenceListRequest(RunEvidenceRequest):
    offset: SafeCursor = 0
    limit: PageLimit = 100


class EvidenceAddressRequest(InvestigationRequest):
    receipt_id: ReceiptId
    expected_sha256: Sha256

    @model_validator(mode='after')
    def identity(self):
        if self.receipt_id != 'c21:receipt:' + self.expected_sha256:
            raise ValueError('Expected hash must bind the selected receipt')
        return self


class EvidencePageRequest(EvidenceAddressRequest):
    section: Literal['rows', 'inputs'] = 'rows'
    offset: SafeCursor = 0
    limit: PageLimit = 100


class EvidenceExportRequest(EvidencePageRequest):
    format: Literal['csv', 'json'] = 'csv'


class AnswerSubmitRequest(RunEvidenceRequest):
    locale: Locale = 'en'
    idempotency_key: UUIDString


class AnswerRunRequest(InvestigationRequest):
    investigation_id: UUIDString
    conversation_id: UUIDString
    run_id: UUIDString


class AnswerAddressRequest(AnswerRunRequest):
    job_id: UUIDString


class AnswerCancelRequest(AnswerAddressRequest):
    idempotency_key: UUIDString


class AnswerEventsRequest(AnswerAddressRequest):
    after_cursor: SafeCursor = 0
    limit: PageLimit = 100


class AnswerListRequest(AnswerRunRequest):
    limit: PageLimit = 25
    cursor: Annotated[str, StringConstraints(min_length=1, max_length=4096)] | None = None


class EvidenceTotal(InvestigationRequest):
    state: Literal['known', 'unknown']
    value: SafeCursor | None
    reason: Text | None

    @model_validator(mode='after')
    def meaning(self):
        if self.state == 'known' and (self.value is None or self.reason is not None):
            raise ValueError('Known total requires its actual value and no unknown reason')
        if self.state == 'unknown' and (self.value is not None or self.reason is None):
            raise ValueError('Unknown total must retain its reason and no invented value')
        return self


class EvidenceReceipt(InvestigationRequest):
    id: ReceiptId
    sha256: Sha256
    run_id: UUIDString
    input_version: PositiveVersion
    binding: ControllerBinding
    observation_id: Identifier
    kind: Literal['catalogue', 'scientific', 'documentary']
    authority: Literal['descriptive', 'published', 'experimental', 'documentary']
    operation_id: Identifier | None
    operation_version: Identifier | None
    parameters: dict
    parameters_sha256: Sha256 | None
    scope: EvidenceScope
    input_count: SafeCursor
    input_sha256: Sha256
    payload_sha256: Sha256
    result_content_sha256: Sha256 | None
    availability: Literal['available', 'unknown', 'unavailable']
    source_completeness: Literal['complete', 'partial', 'unknown', 'unavailable']
    query_completion: Literal['not_started', 'complete', 'partial', 'failed']
    counts: Annotated[list[SemanticCount], Field(max_length=256)]
    total_rows: EvidenceTotal
    returned_count: SafeCursor
    offset: SafeCursor
    next_offset: SafeCursor | None
    preview_rows: Annotated[list[dict], Field(max_length=20)]
    preview_truncated: bool
    columns: Annotated[list[ResultColumn], Field(max_length=256)]
    qualifications: Annotated[list[Text], Field(max_length=2048)]
    origin_receipt_ids: Annotated[list[ReceiptId], Field(max_length=256)]
    attachment_reference: ContextReference

    @model_validator(mode='after')
    def identity(self):
        if self.id != 'c21:receipt:' + self.sha256:
            raise ValueError('Retained receipt identity must bind its content hash')
        reference = self.attachment_reference
        if reference.kind != 'artifact' or reference.id != self.id or reference.snapshot_id != self.binding.snapshot_id:
            raise ValueError('Attachment reference must bind this original retained receipt')
        if self.next_offset is not None and self.next_offset <= self.offset:
            raise ValueError('Retained page cursor must advance')
        if self.authority == 'documentary' and self.kind != 'documentary':
            raise ValueError('Documentary authority cannot become an exact result')
        return self


class EvidenceResponse(InvestigationRequest):
    version: Literal['research-evidence-v1'] = EVIDENCE_VERSION
    access_revision: AccessRevision
    receipt: EvidenceReceipt


class EvidenceListResponse(InvestigationRequest):
    version: Literal['research-evidence-v1'] = EVIDENCE_VERSION
    access_revision: AccessRevision
    run_id: UUIDString
    input_version: PositiveVersion
    offset: SafeCursor
    items: Annotated[list[EvidenceReceipt], Field(max_length=500)]
    next_offset: SafeCursor | None
    total: SafeCursor


class EvidencePageResponse(EvidenceResponse):
    section: Literal['rows', 'inputs']
    offset: SafeCursor
    rows: Annotated[list[dict], Field(max_length=500)]
    next_offset: SafeCursor | None
    section_total: EvidenceTotal


class EvidenceExportResponse(EvidenceResponse):
    section: Literal['rows', 'inputs']
    offset: SafeCursor
    returned_count: SafeCursor
    section_total: EvidenceTotal
    next_offset: SafeCursor | None
    format: Literal['csv', 'json']
    filename: Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r'^[A-Za-z0-9_.-]+$')]
    mime_type: Literal['text/csv; charset=utf-8', 'application/json; charset=utf-8']
    content_text: str
    content_sha256: Sha256
    provenance: dict


class AnswerBlock(InvestigationRequest):
    id: Identifier
    kind: Literal['fact', 'table', 'relationship', 'documentary', 'limitation']
    text: Text
    receipt_ids: Annotated[list[ReceiptId], Field(max_length=256)]
    fact_id: Identifier | None = None
    data: dict | None = None


class RenderedAnswer(InvestigationRequest):
    id: UUIDString
    locale: Locale
    completion: Literal['complete', 'partial']
    blocks: Annotated[list[AnswerBlock], Field(max_length=512)]
    receipt_ids: Annotated[list[ReceiptId], Field(max_length=1024)]
    qualifications: Annotated[list[Text], Field(max_length=2048)]
    pack_sha256: Sha256
    model_used: bool
    scientific_verification: Literal['not_independently_verified'] = 'not_independently_verified'


AnswerStatus = Literal['queued', 'running', 'completed', 'partial', 'cancelled', 'failed', 'unavailable']


class AnswerJob(InvestigationRequest):
    id: UUIDString
    run_id: UUIDString
    input_version: PositiveVersion
    binding: ControllerBinding
    locale: Locale
    status: AnswerStatus
    active_elapsed_ms: SafeCursor
    budget: BudgetSnapshot
    event_cursor: Literal[0]
    latest_event_cursor: SafeCursor
    activity: Annotated[list[dict], Field(max_length=0)]
    answer: RenderedAnswer | None
    error: LocalizedText | None
    synthetic: Literal[False]

    @field_validator('event_cursor', mode='before')
    @classmethod
    def snapshot_cursor(cls, value):
        if type(value) is not int or value != 0:
            raise ValueError('Snapshot cursor must be integer zero')
        return value

    @field_validator('synthetic', mode='before')
    @classmethod
    def production_flag(cls, value):
        if value is not False:
            raise ValueError('Production answer requires explicit false fixture flag')
        return value

    @model_validator(mode='after')
    def publication(self):
        if (self.status in {'completed', 'partial'}) != (self.answer is not None):
            raise ValueError('Only successful structured synthesis can publish an answer')
        if self.answer and (self.answer.locale != self.locale or self.answer.completion != ('complete' if self.status == 'completed' else 'partial')):
            raise ValueError('Answer locale and completion must match its immutable publication')
        if type(self.event_cursor) is not int or self.event_cursor != 0 or self.synthetic is not False:
            raise ValueError('Production answer snapshots have integer cursor zero and explicit false fixture flag')
        return self


class AnswerResponse(InvestigationRequest):
    version: Literal['research-answers-v1'] = ANSWER_VERSION
    access_revision: AccessRevision
    job: AnswerJob


class AnswerListResponse(InvestigationRequest):
    version: Literal['research-answers-v1'] = ANSWER_VERSION
    access_revision: AccessRevision
    run_id: UUIDString
    input_version: PositiveVersion
    binding: ControllerBinding
    eligible: bool
    reason: LocalizedText | None
    items: Annotated[list[AnswerJob], Field(max_length=500)]
    next_cursor: str | None


class AnswerEvent(InvestigationRequest):
    cursor: PositiveVersion
    job_id: UUIDString
    elapsed_ms: SafeCursor
    kind: Literal['accepted', 'started', 'progress', 'completed', 'partial', 'cancelled', 'failed', 'unavailable']
    summary: LocalizedText


class AnswerEventsResponse(InvestigationRequest):
    version: Literal['research-answers-v1'] = ANSWER_VERSION
    access_revision: AccessRevision
    job_id: UUIDString
    binding: ControllerBinding
    after_cursor: SafeCursor
    next_cursor: SafeCursor
    latest_event_cursor: SafeCursor
    has_more: bool
    events: Annotated[list[AnswerEvent], Field(max_length=500)]

    @model_validator(mode='after')
    def consecutive(self):
        if self.next_cursor - self.after_cursor != len(self.events) or any(
            event.cursor != self.after_cursor + index + 1 or event.job_id != self.job_id
            for index, event in enumerate(self.events)
        ):
            raise ValueError('Answer event pages must be consecutive and job-bound')
        if self.next_cursor > self.latest_event_cursor or self.has_more != (self.next_cursor < self.latest_event_cursor):
            raise ValueError('Answer event high water is inconsistent')
        return self


EVIDENCE_REQUEST_MODELS = {'list': EvidenceListRequest, 'open': EvidenceAddressRequest,
                           'page': EvidencePageRequest, 'export': EvidenceExportRequest}
EVIDENCE_RESPONSE_MODELS = {'list': EvidenceListResponse, 'open': EvidenceResponse,
                            'page': EvidencePageResponse, 'export': EvidenceExportResponse}
ANSWER_REQUEST_MODELS = {'submit': AnswerSubmitRequest, 'status': AnswerAddressRequest,
                         'events': AnswerEventsRequest, 'cancel': AnswerCancelRequest, 'list': AnswerListRequest}
ANSWER_RESPONSE_MODELS = {'submit': AnswerResponse, 'status': AnswerResponse,
                          'events': AnswerEventsResponse, 'cancel': AnswerResponse, 'list': AnswerListResponse}


@dataclass(frozen=True)
class RunEvidenceAnchor:
    run_id: str
    input_version: int
    owner_id: str
    binding: ControllerBinding
    effective_question: str
    effective_question_sha256: str
    controller_result: ControllerResult
    controller_result_sha256: str
    execution_manifest_sha256: str
    effective_scope: EvidenceScope
    scope_witness_sha256: str
    limits: ControllerLimits
    run_budget_high_water: BudgetSnapshot
    actor_binding: str
    catalogue_policy_revision: str
    clock_invalid: bool
    frozen_context: dict = field(repr=False)
    execution_manifest: dict = field(repr=False)
    allowed_dataset_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class VerifiedEvidenceSet:
    anchor: RunEvidenceAnchor
    receipts: tuple[EvidenceReceipt, ...]
    full_payloads_by_receipt: dict[str, dict] = field(repr=False)
    input_manifests_by_receipt: dict[str, list[dict]] = field(repr=False)
    attached_receipts: tuple[EvidenceReceipt, ...] = ()
    unresolved_work: tuple[str, ...] = ()
    attached_full_payloads_by_receipt: dict[str, dict] = field(default_factory=dict, repr=False)

    @property
    def completion(self) -> CompletionAssessment:
        return self.anchor.controller_result.completion
