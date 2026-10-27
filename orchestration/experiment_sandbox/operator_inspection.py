"""Read retained C22 approval on an explicitly isolated operator store.

This module creates no reservation, execution envelope, start permit or release
authority. Store isolation is a trusted deployment declaration, not something
that a request or an inspection can establish.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Literal

from sqlalchemy import select

from db.app_models import ResearchExperimentApproval, ResearchExperimentRevision
from orchestration.research_experiments import (
    HASH_FIELDS, ResearchExperimentError, ResearchExperimentService,
)
from schema.context_catalogue import canonical_json
from schema.investigations import PositiveVersion, UUIDString
from schema.research_experiments import (
    EnvironmentDescriptor, ExperimentAddressRequest, ExperimentApprovalRequest,
    ExperimentContextBinding, ExperimentHashes,
)


def _disabled():
    return False


class ApprovedInspectionRequest(ExperimentAddressRequest, ExperimentContextBinding):
    """Select exact retained review; callers cannot submit approval or bytes."""
    expected_version: PositiveVersion
    expected_proposal_revision_id: UUIDString
    expected_hashes: ExperimentHashes


@dataclass(frozen=True, init=False)
class OperatorInspectionConfig:
    """Explicit trusted configuration; no environment or store discovery.

    ``store_scope`` declares operator-only storage with C22 routes unmounted.
    The caller configuring the process must actually enforce that declaration.
    This read-only component cannot prove deployment isolation or image/runtime
    acceptance. ``enabled`` is independent of the C22 fake-dispatch flag.
    """
    site_id: str
    session_factory: object
    enabled: Callable[[], bool]
    store_scope: Literal['isolated-unmounted-operator']
    _environments_json: Mapping[str, str]

    def __init__(self, *, site_id, session_factory, environments, store_scope,
                 enabled=_disabled):
        if (type(site_id) is not str or not site_id.startswith('v1:')
                or not callable(session_factory) or not callable(enabled)
                or store_scope != 'isolated-unmounted-operator'):
            raise ValueError('Explicit isolated unmounted operator store required')
        parsed = {}
        for identity, value in dict(environments).items():
            descriptor = EnvironmentDescriptor.model_validate(value).model_dump(mode='json')
            if (identity != hashlib.sha256(canonical_json(descriptor).encode()).hexdigest()
                    or descriptor['kind'] != 'linux-gvisor' or descriptor['test_only'] is not False):
                raise ValueError('Exact trusted Linux inspection environments required')
            parsed[identity] = canonical_json(descriptor)
        if not parsed:
            raise ValueError('Exact trusted Linux inspection environments required')
        for name, value in {'site_id': site_id, 'session_factory': session_factory,
                'enabled': enabled, 'store_scope': store_scope,
                '_environments_json': MappingProxyType(parsed)}.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class ApprovedHashes:
    proposal_sha256: str
    code_sha256: str
    input_manifest_sha256: str
    environment_sha256: str
    resources_sha256: str


@dataclass(frozen=True, init=False)
class ApprovedCandidate:
    """Detached inspection evidence. It carries no retained envelope authority."""
    site_id: str
    owner_user_id: str
    experiment_id: str
    proposal_revision_id: str
    proposal_version: int
    approval_id: str
    approval_request_sha256: str
    approval_created_at: str
    hashes: ApprovedHashes
    source_sha256: str
    binding_bytes: bytes
    context_bytes: bytes
    proposal_bytes: bytes
    environment_bytes: bytes
    manifest_bytes: bytes
    approval_request_bytes: bytes
    files: Mapping[str, bytes]

    def __init__(self, *args, **kwargs):
        raise TypeError('Use inspect_approved')

    @property
    def inspection_only(self) -> Literal[True]:
        return True

    @property
    def execution_authorized(self) -> Literal[False]:
        return False

    @property
    def capacity_reserved(self) -> Literal[False]:
        return False

    @property
    def execution_performed(self) -> Literal[False]:
        return False

    @property
    def authority(self) -> Literal['experimental']:
        return 'experimental'

    @property
    def scientific_approval(self) -> Literal['not_independently_verified']:
        return 'not_independently_verified'

    @property
    def environment(self):
        return json.loads(self.environment_bytes)

    @property
    def proposal(self):
        return json.loads(self.proposal_bytes)

    @property
    def manifest(self):
        return json.loads(self.manifest_bytes)


class C23OperatorInspection:
    """Compose accepted C22 checks without registering or changing its APIs."""
    def __init__(self, *, service: ResearchExperimentService, config: OperatorInspectionConfig):
        if not isinstance(service, ResearchExperimentService) or not isinstance(config, OperatorInspectionConfig):
            raise ValueError('Explicit C22 service and operator inspection configuration required')
        self.service, self.config = service, config
        self._investigations, self._exporter = service.investigations, service.exporter
        self._store, self._catalogue = service.investigations.store, service.investigations.catalogue
        self._binding()

    def _binding(self):
        service, config = self.service, self.config
        if (service.site_id != config.site_id or service.session_factory is not config.session_factory
                or service.investigations is not self._investigations or service.exporter is not self._exporter
                or self._investigations.session_factory is not config.session_factory
                or self._investigations.site_id != config.site_id
                or self._exporter.store is not self._store or self._investigations.store is not self._store
                or self._exporter.catalogue is not self._catalogue or self._investigations.catalogue is not self._catalogue):
            raise ValueError('Inspection requires the exact configured C22 store and sources')

    def _enabled(self):
        self._binding()
        try:
            if self.config.enabled() is not True:
                raise ResearchExperimentError('operator_inspection_unavailable')
        except ResearchExperimentError:
            raise
        except Exception:
            raise ResearchExperimentError('operator_inspection_unavailable') from None
        self.service._require_enabled()

    def _environment(self, proposal, environment):
        configured = self.service._environment(proposal, dispatch=False)
        trusted = self.config._environments_json.get(proposal['environment_id'])
        if (configured != environment or trusted != canonical_json(environment)
                or environment['kind'] != 'linux-gvisor' or environment['test_only'] is not False):
            raise ResearchExperimentError('environment_unavailable')

    def _approval(self, session, head, revision):
        approval = session.scalar(select(ResearchExperimentApproval).where(
            ResearchExperimentApproval.revision_id == revision.id).execution_options(populate_existing=True))
        if approval is None:
            raise ResearchExperimentError('conflict', 409)
        try:
            request = ExperimentApprovalRequest.model_validate(json.loads(approval.request_json)).model_dump(mode='json')
            if (approval.experiment_id != head.id or approval.user_id != revision.user_id
                    or canonical_json(request) != approval.request_json
                    or hashlib.sha256(approval.request_json.encode()).hexdigest() != approval.request_sha256
                    or request['experiment_id'] != str(head.id)):
                raise ValueError
            self.service._expected(head, revision, request)
        except (ValueError, TypeError, KeyError):
            raise ResearchExperimentError('integrity_error', 409) from None
        return approval

    def _candidate(self, session, head, revision, data):
        self.service._expected(head, revision, data)
        proposal, environment, exported = self.service._exported(session, revision)
        self._environment(proposal, environment)
        approval = self._approval(session, head, revision)
        value = object.__new__(ApprovedCandidate)
        fields = {'site_id': self.config.site_id, 'owner_user_id': str(revision.user_id),
            'experiment_id': str(head.id), 'proposal_revision_id': str(revision.id),
            'proposal_version': head.version, 'approval_id': str(approval.id),
            'approval_request_sha256': approval.request_sha256, 'approval_created_at': approval.created_at.isoformat(),
            'hashes': ApprovedHashes(**{name: getattr(revision, name) for name in HASH_FIELDS}),
            'source_sha256': revision.source_sha256,
            'binding_bytes': canonical_json(self.service._binding(revision)).encode(),
            'context_bytes': revision.context_json.encode(), 'proposal_bytes': revision.proposal_json.encode(),
            'environment_bytes': revision.environment_json.encode(), 'manifest_bytes': revision.manifest_json.encode(),
            'approval_request_bytes': approval.request_json.encode(),
            'files': MappingProxyType({name: bytes(raw) for name, raw in exported.files.items()})}
        for name, item in fields.items():
            object.__setattr__(value, name, item)
        return value, proposal, exported

    def inspect_approved(self, request, *, current_owner) -> ApprovedCandidate:
        """Check current approval and frozen bytes; perform no DB mutation.

        Full source verification runs between read transactions. Access/flag
        callbacks run again under the final transaction, followed by a fresh
        retained-byte comparison and C22's closing DB authority fence. This is
        an inspection snapshot, never admission for a future effect.
        """
        try:
            data = ApprovedInspectionRequest.model_validate(request).model_dump(mode='json')
        except (ValueError, TypeError):
            raise ResearchExperimentError('invalid_request', 422) from None
        self._enabled()
        service = self.service
        with service._transaction() as session:
            actor = service._actor(session, user=current_owner)
            head = service._owned(session, actor, data['experiment_id'])
            revision, frozen = service._revision(session, actor, head, active=True)
            candidate, proposal, exported = self._candidate(session, head, revision, data)
        service._verify(frozen=frozen, proposal=proposal, actor=actor, exported=exported)
        self._enabled()
        with service._transaction() as session:
            actor = service._actor(session, user=current_owner)
            head = service._owned(session, actor, data['experiment_id'])
            revision, frozen = service._revision(session, actor, head, active=True)
            current, proposal, exported = self._candidate(session, head, revision, data)
            if current != candidate:
                raise ResearchExperimentError('integrity_error', 409)
            service._verify(frozen=frozen, proposal=proposal, actor=actor, exported=exported, access_only=True)
            self._enabled()
            self._binding()
            # Expire cached rows so callback-time SQL changes cannot hide in
            # the identity map. No source/flag callbacks follow this fence.
            session.expire_all()
            actor = service._closing_gate(session, user=current_owner, head_id=data['experiment_id'],
                revision_id=data['expected_proposal_revision_id'], active=True)
            head = service._owned(session, actor, data['experiment_id'])
            revision = session.get(ResearchExperimentRevision, head.head_revision_id)
            current, _, _ = self._candidate(session, head, revision, data)
            if current != candidate:
                raise ResearchExperimentError('integrity_error', 409)
            return current
