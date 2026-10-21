"""C22 private proposal, approval and fake-dispatch contracts.

Public requests select data and an explicitly configured environment identity.
They cannot provide source eligibility, execution authority or runtime objects.
"""
from __future__ import annotations

import ast
import hashlib
import re
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator
from packaging.version import InvalidVersion, Version

from schema.context_catalogue import Identifier, LocalizedText, Sha256, canonical_json
from schema.investigations import InvestigationRequest, PositiveVersion, UUIDString

EXPERIMENT_VERSION = 'research-experiments-v1'
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_OUTPUT_BYTES = 50 * 1024 * 1024
Text = Annotated[str, StringConstraints(min_length=1, max_length=4000, pattern=r'\S')]
Cursor = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
FileName = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')]


def content_sha256(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


class ExportSelection(InvestigationRequest):
    kind: Literal['dataset', 'published_analysis'] = 'dataset'
    target_id: Identifier
    table: Identifier
    columns: Annotated[list[Identifier], Field(min_length=1, max_length=128)]

    @model_validator(mode='after')
    def unique_columns(self):
        if len(set(self.columns)) != len(self.columns):
            raise ValueError('Export columns must be distinct')
        return self


class PairingSpec(InvestigationRequest):
    mode: Literal['independent', 'physical_identity'] = 'independent'
    relationship_ids: Annotated[list[Identifier], Field(max_length=128)] = Field(default_factory=list)

    @model_validator(mode='after')
    def meaningful_pairing(self):
        if len(set(self.relationship_ids)) != len(self.relationship_ids):
            raise ValueError('Pairing relationships must be distinct')
        if (self.mode == 'independent') != (not self.relationship_ids):
            raise ValueError('Only explicit physical identity may name pairing relationships')
        return self


class ExplicitExclusion(InvestigationRequest):
    dataset_id: Identifier
    entity: Literal['cast', 'library', 'sst_observation', 'source_occurrence']
    ids: Annotated[list[Identifier], Field(min_length=1, max_length=256)]
    reason: Text

    @model_validator(mode='after')
    def unique_ids(self):
        if len(set(self.ids)) != len(self.ids):
            raise ValueError('Excluded identities must be distinct')
        return self


class FrozenCohortSpec(InvestigationRequest):
    version: Literal['c22-cohort-v1'] = 'c22-cohort-v1'
    selections: Annotated[list[ExportSelection], Field(min_length=1, max_length=32)]
    pairing: PairingSpec = Field(default_factory=PairingSpec)
    exclusions: Annotated[list[ExplicitExclusion], Field(max_length=128)] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_selections(self):
        identities = [(item.kind, item.target_id, item.table) for item in self.selections]
        if len(set(identities)) != len(identities):
            raise ValueError('Select each source table once')
        exclusions = [(item.dataset_id, item.entity, identity) for item in self.exclusions for identity in item.ids]
        if len(set(exclusions)) != len(exclusions):
            raise ValueError('Declare each excluded source entity once')
        return self


class ExperimentResources(InvestigationRequest):
    cpus: Annotated[int, Field(strict=True, ge=1, le=2)] = 2
    memory_bytes: Annotated[int, Field(strict=True, ge=64 * 1024 * 1024, le=4 * 1024**3)] = 4 * 1024**3
    wall_seconds: Annotated[int, Field(strict=True, ge=1, le=600)] = 600
    max_input_bytes: Annotated[int, Field(strict=True, ge=1, le=MAX_INPUT_BYTES)] = MAX_INPUT_BYTES
    max_output_bytes: Annotated[int, Field(strict=True, ge=1, le=MAX_OUTPUT_BYTES)] = MAX_OUTPUT_BYTES


class ExpectedOutput(InvestigationRequest):
    name: FileName
    kind: Literal['table', 'raster']
    description: Text


class EnvironmentDescriptor(InvestigationRequest):
    """Trusted host registry entry; never an approval authority from a request."""
    kind: Literal['c22-fake', 'linux-gvisor']
    test_only: bool
    python_version: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    image_digest: Annotated[str, StringConstraints(pattern=r'^sha256:[a-f0-9]{64}$')] | None = None
    lockfile_sha256: Sha256 | None = None
    packages: dict[Identifier, Annotated[str, StringConstraints(min_length=1, max_length=128)]] = Field(default_factory=dict)
    description: Text

    @model_validator(mode='after')
    def concrete_identity(self):
        if self.kind == 'c22-fake':
            if not self.test_only or self.image_digest is not None or self.lockfile_sha256 is not None or self.packages:
                raise ValueError('Fake descriptors cannot claim an execution environment')
            if self.python_version != 'not-executed':
                raise ValueError('Fake descriptors must disclose that Python is not executed')
        elif (self.test_only or self.image_digest is None or self.lockfile_sha256 is None
              or not {'numpy', 'pandas', 'pyarrow', 'scipy', 'statsmodels', 'matplotlib'} <= self.packages.keys()
              or not re.fullmatch(r'3\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', self.python_version)):
            raise ValueError('A real environment requires exact image, lockfile, Python and scientific package identities')
        try:
            for value in self.packages.values():
                Version(value)
        except InvalidVersion:
            raise ValueError('Environment packages require exact versions') from None
        if len(self.packages) > 256:
            raise ValueError('Environment package manifest exceeds its bound')
        return self

    @property
    def identity_sha256(self):
        return content_sha256(self.model_dump(mode='json'))


class ExperimentProposal(InvestigationRequest):
    question: Annotated[str, StringConstraints(min_length=1, max_length=8000, pattern=r'\S')]
    cohort: FrozenCohortSpec
    method: Text
    assumptions: Annotated[list[Text], Field(max_length=64)]
    python_code: Annotated[str, StringConstraints(min_length=1, max_length=32768, pattern=r'\S')]
    expected_outputs: Annotated[list[ExpectedOutput], Field(min_length=1, max_length=32)]
    environment_id: Sha256
    limitations: Annotated[list[Text], Field(max_length=128)]
    seeds: dict[Identifier, Annotated[int, Field(strict=True, ge=0, le=4294967295)]] = Field(default_factory=dict)
    resources: ExperimentResources = Field(default_factory=ExperimentResources)

    @model_validator(mode='after')
    def reviewable(self):
        if len(self.python_code.encode('utf-8')) > 32768:
            raise ValueError('Python source exceeds its UTF-8 byte bound')
        try:
            ast.parse(self.python_code, mode='exec')
        except (SyntaxError, ValueError, RecursionError):
            raise ValueError('Python source must be syntactically reviewable') from None
        names = [item.name for item in self.expected_outputs]
        if len(set(names)) != len(names) or len(self.seeds) > 32:
            raise ValueError('Distinct bounded outputs and seed declarations required')
        if len(canonical_json(self.model_dump(mode='json')).encode('utf-8')) > 60000:
            raise ValueError('Proposal exceeds its review byte bound')
        return self


class ExperimentContextBinding(InvestigationRequest):
    investigation_id: UUIDString
    conversation_id: UUIDString
    context_revision_id: UUIDString
    snapshot_id: Sha256
    context_payload_sha256: Sha256


class ExperimentCreateRequest(ExperimentContextBinding):
    proposal: ExperimentProposal
    idempotency_key: UUIDString


class ExperimentAddressRequest(InvestigationRequest):
    experiment_id: UUIDString


class ExperimentGetRequest(ExperimentAddressRequest):
    proposal_revision_id: UUIDString | None = None


class ExperimentReviseRequest(ExperimentCreateRequest):
    experiment_id: UUIDString
    expected_version: PositiveVersion
    expected_proposal_revision_id: UUIDString


class ExperimentHashes(InvestigationRequest):
    proposal_sha256: Sha256
    code_sha256: Sha256
    input_manifest_sha256: Sha256
    environment_sha256: Sha256
    resources_sha256: Sha256


class ExperimentApprovalRequest(ExperimentAddressRequest, ExperimentContextBinding):
    expected_version: PositiveVersion
    expected_proposal_revision_id: UUIDString
    expected_hashes: ExperimentHashes
    idempotency_key: UUIDString


class ExperimentDispatchRequest(ExperimentApprovalRequest):
    pass


class ExperimentRetryRequest(InvestigationRequest):
    operation_id: UUIDString


class ExperimentListRequest(InvestigationRequest):
    investigation_id: UUIDString
    conversation_id: UUIDString | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 25
    after_id: UUIDString | None = None


class ExperimentEventsRequest(ExperimentAddressRequest):
    after_cursor: Cursor = 0
    limit: Annotated[int, Field(strict=True, ge=1, le=500)] = 100


class ExperimentApprovalSnapshot(InvestigationRequest):
    status: Literal['none', 'current', 'stale']
    proposal_revision_id: UUIDString | None
    approved_at: Text | None

    @model_validator(mode='after')
    def retained_decision(self):
        if self.status == 'none':
            if self.proposal_revision_id is not None or self.approved_at is not None:
                raise ValueError('Absent approval has no decision identity')
        elif self.proposal_revision_id is None or self.approved_at is None:
            raise ValueError('Retained approval requires its original revision and time')
        return self


class ExperimentDispatchSnapshot(InvestigationRequest):
    eligible: bool
    reason: Text | None
    reservation_id: UUIDString | None
    status: Literal['unavailable', 'ready', 'reserved', 'accepted', 'uncertain']

    @model_validator(mode='after')
    def capacity_state(self):
        if self.status == 'ready':
            if not self.eligible or self.reservation_id is not None or self.reason is not None:
                raise ValueError('Ready dispatch must describe an eligible unreserved proposal')
        elif self.eligible:
            raise ValueError('Unavailable or reserved dispatch cannot offer a new reservation')
        if self.status == 'unavailable':
            if self.reason is None or self.reservation_id is not None:
                raise ValueError('Unavailable dispatch requires its actual reason')
        elif self.status != 'ready' and self.reservation_id is None:
            raise ValueError('Retained dispatch requires its stable reservation identity')
        return self


class ExperimentSnapshot(InvestigationRequest):
    id: UUIDString
    binding: ExperimentContextBinding
    version: PositiveVersion
    proposal_revision_id: UUIDString
    proposal: ExperimentProposal
    hashes: ExperimentHashes
    manifest: dict
    environment: EnvironmentDescriptor
    approval: ExperimentApprovalSnapshot | None
    dispatch: ExperimentDispatchSnapshot | None
    event_cursor: Cursor = 0
    latest_event_cursor: Cursor
    authority: Literal['experimental'] = 'experimental'
    scientific_approval: Literal['not_independently_verified'] = 'not_independently_verified'
    execution_performed: Literal[False] = False

    @field_validator('execution_performed', mode='before')
    @classmethod
    def fake_did_not_execute(cls, value):
        if value is not False:
            raise ValueError('C22 does not execute Python')
        return value

    @model_validator(mode='after')
    def exact_proposal(self):
        proposal = self.proposal.model_dump(mode='json')
        if (self.hashes.proposal_sha256 != content_sha256(proposal)
                or self.hashes.code_sha256 != hashlib.sha256(self.proposal.python_code.encode('utf-8')).hexdigest()
                or self.hashes.input_manifest_sha256 != content_sha256(self.manifest)
                or self.hashes.resources_sha256 != content_sha256(proposal['resources'])
                or self.hashes.environment_sha256 != self.environment.identity_sha256
                or self.proposal.environment_id != self.environment.identity_sha256):
            raise ValueError('Experiment review must retain the exact approved identities')
        if self.approval and self.approval.status == 'current' and self.approval.proposal_revision_id != self.proposal_revision_id:
            raise ValueError('Approval cannot transfer to a different proposal revision')
        if self.dispatch and self.dispatch.eligible and (self.approval is None or self.approval.status != 'current'):
            raise ValueError('Dispatch eligibility requires a current exact approval')
        if self.event_cursor > self.latest_event_cursor:
            raise ValueError('Event cursor exceeds retained history')
        return self


class ExperimentOperationSnapshot(InvestigationRequest):
    id: UUIDString
    state: Literal['prepared', 'ready', 'uncertain', 'unavailable']
    result_revision_id: UUIDString | None
    error_code: Identifier | None = None
    reason: LocalizedText | None = None


class ExperimentResponse(InvestigationRequest):
    version: Literal['research-experiments-v1'] = EXPERIMENT_VERSION
    experiment: ExperimentSnapshot | None
    operation: ExperimentOperationSnapshot | None

    @model_validator(mode='after')
    def nonempty(self):
        if self.experiment is None and self.operation is None:
            raise ValueError('Experiment response requires retained state')
        return self


class ExperimentListResponse(InvestigationRequest):
    version: Literal['research-experiments-v1'] = EXPERIMENT_VERSION
    items: Annotated[list[ExperimentSnapshot], Field(max_length=100)]
    next_cursor: UUIDString | None


class ExperimentEvent(InvestigationRequest):
    cursor: PositiveVersion
    kind: Identifier
    summary: LocalizedText


class ExperimentEventsResponse(InvestigationRequest):
    version: Literal['research-experiments-v1'] = EXPERIMENT_VERSION
    experiment_id: UUIDString
    after_cursor: Cursor
    items: Annotated[list[ExperimentEvent], Field(max_length=500)]
    next_cursor: Cursor
    latest_event_cursor: Cursor
    has_more: bool

    @model_validator(mode='after')
    def consecutive(self):
        expected = list(range(self.after_cursor + 1, self.after_cursor + 1 + len(self.items)))
        if ([item.cursor for item in self.items] != expected
                or self.next_cursor != self.after_cursor + len(self.items)
                or self.next_cursor > self.latest_event_cursor
                or self.has_more != (self.next_cursor < self.latest_event_cursor)
                or (self.has_more and not self.items)):
            raise ValueError('Experiment events must retain consecutive real cursors')
        return self


EXPERIMENT_REQUEST_MODELS = {
    'create': ExperimentCreateRequest, 'revise': ExperimentReviseRequest,
    'get': ExperimentGetRequest, 'status': ExperimentAddressRequest,
    'list': ExperimentListRequest, 'approve': ExperimentApprovalRequest,
    'dispatch': ExperimentDispatchRequest, 'events': ExperimentEventsRequest,
    'retry': ExperimentRetryRequest,
}
EXPERIMENT_RESPONSE_MODELS = {
    name: ExperimentListResponse if name == 'list' else ExperimentEventsResponse if name == 'events' else ExperimentResponse
    for name in EXPERIMENT_REQUEST_MODELS
}
