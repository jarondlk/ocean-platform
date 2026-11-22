"""Default-off retained C22 reservation on the exact restricted C23 store.

This module reserves capacity only. It registers no route, executes no Python,
creates no fake outbox and grants no start/publication/termination/release
authority. A detached inspection snapshot is always rechecked at mutation.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from types import SimpleNamespace
import uuid

from pydantic import BaseModel, ConfigDict, TypeAdapter
from sqlalchemy import text

from api.auth import CurrentUser
from db.app_models import ResearchExperimentApproval, ResearchExperimentRevision
from orchestration.experiment_sandbox.contracts import ExecutionMetadata, SandboxError, verify_execution_envelope
from orchestration.experiment_sandbox.execution_store import (
    C23ExecutionStore, ExecutionReservationBinding, execution_job_id, planned_reservation_ids,
)
from orchestration.experiment_sandbox.operator_inspection import (
    ApprovedInspectionRequest, C23OperatorInspection,
)
from orchestration.research_experiments import ResearchExperimentError
from schema.context_catalogue import canonical_json
from schema.experiment_execution import Digest, Hash, Site
from schema.investigations import UUIDString
from schema.research_experiments import content_sha256

_execution_id = TypeAdapter(UUIDString)


def _disabled():
    return False


class RetainedReserveRequest(ApprovedInspectionRequest):
    idempotency_key: UUIDString


class RetainedMaterialPolicy(BaseModel):
    """Trusted fixed identities; no acceptance or approval bit is accepted."""
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    site_id: Site
    worker_id: Hash
    source_policy_sha256: Hash
    worker_source_sha256: Hash
    environment_sha256: Hash
    image_digest: Digest
    runtime_sha256: Hash
    profile_policy_sha256: Hash
    trusted_init_sha256: Hash
    adapter_source_sha256: Hash


@dataclass(frozen=True, init=False)
class RetainedExecutionIdentity:
    """Private detached commit receipt, never a current or future launch permit."""
    _json: str

    def __init__(self, *args, **kwargs):
        raise TypeError('Use C23RetainedBridge.reserve')

    @property
    def document(self):
        return json.loads(self._json)

    @property
    def execution_authorized(self):
        return False

    @property
    def reservation_release_authorized(self):
        return False

    @property
    def scientific_approval(self):
        return 'not_independently_verified'


class C23RetainedBridge:
    """Compose unchanged C22 authority with one short C23 mutation transaction."""
    def __init__(self, *, inspection, store, material_policy, enabled: Callable = _disabled):
        if (type(inspection) is not C23OperatorInspection or type(store) is not C23ExecutionStore
                or type(material_policy) is not RetainedMaterialPolicy or not callable(enabled)):
            raise ValueError('Explicit isolated retained bridge configuration required')
        self.inspection, self.store, self.enabled = inspection, store, enabled
        self._inspection_config, self._store_config = inspection.config, store.config
        self._service = inspection.service
        self._material_json = canonical_json(RetainedMaterialPolicy.model_validate(
            material_policy.model_dump(mode='python')).model_dump(mode='json'))
        self._binding()

    def _binding(self):
        inspection, store, service = self.inspection, self.store, self._service
        inspection._binding()
        policy = json.loads(self._material_json)
        if (inspection.config is not self._inspection_config or store.config is not self._store_config
                or inspection.service is not service
                or service.session_factory is not store.config.controller_session_factory
                or inspection.config.session_factory is not store.config.controller_session_factory
                or service.site_id != store.config.site_id or service.site_id != policy['site_id']
                or store.config.store_scope != 'isolated-unmounted-operator'):
            raise ValueError('Retained bridge requires the exact restricted controller factory/site/sources')

    def _enabled(self):
        self._binding()
        try:
            if self.enabled() is not True:
                raise SandboxError('sandbox_retained_bridge_disabled')
        except SandboxError:
            raise
        except Exception:
            raise SandboxError('sandbox_retained_bridge_disabled') from None
        self.inspection._enabled()
        self._binding()

    def _material(self, candidate):
        policy, environment = json.loads(self._material_json), candidate.environment
        if (candidate.site_id != policy['site_id']
                or hashlib.sha256(candidate.environment_bytes).hexdigest() != policy['environment_sha256']
                or environment['kind'] != 'linux-gvisor' or environment['test_only'] is not False
                or environment['image_digest'] != policy['image_digest']):
            raise SandboxError('sandbox_retained_material_identity')
        return policy

    def _compose_reservation(self, session, data, candidate, policy, current_owner):
        service = self._service
        actor = service._actor(session, user=current_owner)
        head = service._owned(session, actor, data['experiment_id'])
        revision, frozen = service._revision(session, actor, head, active=True)
        address = {key: value for key, value in data.items() if key != 'idempotency_key'}
        current, proposal, exported = self.inspection._candidate(session, head, revision, address)
        if current != candidate:
            raise ResearchExperimentError('integrity_error', 409)
        execution_id, reservation_id = planned_reservation_ids(site_id=candidate.site_id,
            owner_user_id=candidate.owner_user_id, idempotency_key=data['idempotency_key'])
        approval = session.get(ResearchExperimentApproval, uuid.UUID(candidate.approval_id))
        metadata = service._metadata(head, revision, approval,
            SimpleNamespace(id=uuid.UUID(reservation_id)), proposal, candidate.environment, exported)
        metadata = ExecutionMetadata.model_validate(metadata).model_dump(mode='json')
        envelope_json, request_json = canonical_json(metadata), canonical_json(data)
        envelope_sha = content_sha256(metadata)
        binding = ExecutionReservationBinding.model_validate({
            **policy, 'execution_id': execution_id, 'reservation_id': reservation_id,
            'owner_user_id': candidate.owner_user_id, 'experiment_id': candidate.experiment_id,
            'proposal_revision_id': candidate.proposal_revision_id, 'approval_id': candidate.approval_id,
            'idempotency_key': data['idempotency_key'], 'request_json': request_json,
            'envelope_json': envelope_json, 'envelope_sha256': envelope_sha,
            'execution_request_sha256': hashlib.sha256(request_json.encode()).hexdigest(),
            'approval_request_sha256': candidate.approval_request_sha256,
            'source_sha256': candidate.source_sha256,
            'job_id': execution_job_id(site_id=candidate.site_id, reservation_id=reservation_id,
                                        envelope_sha256=envelope_sha)})

        def final_fence():
            # External access and feature callbacks precede the closing DB fence.
            self._enabled()
            service._verify(frozen=frozen, proposal=proposal, actor=actor, exported=exported, access_only=True)
            self._binding()
            session.expire_all()
            final_actor = service._closing_gate(session, user=current_owner,
                head_id=data['experiment_id'], revision_id=data['expected_proposal_revision_id'], active=True)
            final_head = service._owned(session, final_actor, data['experiment_id'])
            final_revision = session.get(ResearchExperimentRevision, final_head.head_revision_id)
            final_candidate, _, _ = self.inspection._candidate(session, final_head, final_revision, address)
            if final_candidate != candidate:
                raise ResearchExperimentError('integrity_error', 409)

        return binding, final_fence

    @staticmethod
    def _receipt(binding, *, released):
        value = object.__new__(RetainedExecutionIdentity)
        document = {'version': 'c23-retained-reserve-identity-v1',
            **{name: getattr(binding, name) for name in (
                'execution_id', 'reservation_id', 'site_id', 'owner_user_id', 'experiment_id',
                'proposal_revision_id', 'approval_id', 'envelope_sha256', 'execution_request_sha256', 'job_id')},
            'capacity_reserved_at_commit': not released, 'capacity_snapshot_only': True,
            'execution_authorized': False, 'publication_authorized': False,
            'reservation_release_authorized': False, 'scientific_approval': 'not_independently_verified'}
        object.__setattr__(value, '_json', canonical_json(document))
        return value

    def reserve(self, request, *, current_owner):
        """Retain exact current application approval and capacity, never execute.

        Full source verification is outside the final mutation transaction.
        Final access/flag callbacks precede a fresh C22 closing authority fence
        inside the same transaction as the named native reserve operation.
        """
        try:
            data = RetainedReserveRequest.model_validate(request).model_dump(mode='json')
        except (ValueError, TypeError):
            raise ResearchExperimentError('invalid_request', 422) from None
        self._enabled()
        address = {key: value for key, value in data.items() if key != 'idempotency_key'}
        candidate = self.inspection.inspect_approved(address, current_owner=current_owner)
        policy = self._material(candidate)
        with self.store.controller_transaction() as session:
            binding, final_fence = self._compose_reservation(session, data, candidate, policy, current_owner)
            retained = self.store.reserve_after_fence_in_transaction(session, binding, final_fence=final_fence)
            if retained != binding.execution_id:
                raise SandboxError('sandbox_retained_reservation_identity')
            # Capacity is a commit snapshot, not future action authority. A
            # historical idempotent retry may already have a release ledger.
            released = session.scalar(text(f'SELECT EXISTS(SELECT 1 FROM {self._store_config.schema}.'
                'research_experiment_release WHERE execution_id=CAST(:id AS uuid))'), {'id': binding.execution_id})
            if type(released) is not bool:
                raise SandboxError('sandbox_retained_reservation_identity')
        return self._receipt(binding, released=released)

    def _pending_binding(self, session, execution_id, actor):
        schema = self._store_config.schema
        row = session.execute(text(f"SELECT to_jsonb(e)-'created_at', s.state, s.fence FROM {schema}."
            f'research_experiment_execution e JOIN {schema}.research_experiment_execution_state s USING (execution_id) '
            'WHERE e.execution_id=CAST(:id AS uuid) AND e.site_id=:site AND e.owner_user_id=:owner'),
            {'id': execution_id, 'site': self._store_config.site_id, 'owner': actor.id}).one_or_none()
        if row is None:
            raise ResearchExperimentError('not_found', 404)
        if (row.state, row.fence) != ('reserved', 1):
            raise ResearchExperimentError('conflict', 409)
        try:
            return ExecutionReservationBinding.model_validate(row[0])
        except (ValueError, TypeError):
            raise SandboxError('sandbox_retained_execution_binding') from None

    def reopen_pending(self, execution_id, *, current_owner):
        """Reload the verified worker inputs from an unstarted durable reservation.

        The caller supplies an authenticated owner. The reservation is only a
        snapshot; preparation and start still need the separate runtime fences.
        No queued data or Python is accepted from the caller.
        """
        if not isinstance(current_owner, CurrentUser):
            raise ResearchExperimentError('authentication_required', 401)
        try:
            execution_id = _execution_id.validate_python(execution_id, strict=True)
        except (ValueError, TypeError):
            raise ResearchExperimentError('invalid_request', 422) from None
        self._enabled()
        with self.store.controller_transaction() as session:
            actor = self._service._actor(session, user=current_owner)
            stored = self._pending_binding(session, execution_id, actor)
        try:
            data = RetainedReserveRequest.model_validate_json(stored.request_json).model_dump(mode='json')
        except ValueError:
            raise SandboxError('sandbox_retained_execution_binding') from None
        address = {key: value for key, value in data.items() if key != 'idempotency_key'}
        candidate = self.inspection.inspect_approved(address, current_owner=current_owner)
        policy = self._material(candidate)
        envelope = verify_execution_envelope({'metadata': json.loads(stored.envelope_json),
            'files': candidate.files}, expected_envelope_sha256=stored.envelope_sha256,
            environments={policy['environment_sha256']: candidate.environment})
        with self.store.controller_transaction() as session:
            binding, final_fence = self._compose_reservation(session, data, candidate, policy, current_owner)
            if binding != stored:
                raise SandboxError('sandbox_retained_execution_binding')
            final_fence()
            if self._pending_binding(session, execution_id, current_owner) != binding:
                raise SandboxError('sandbox_retained_execution_binding')
        return self._receipt(binding, released=False), envelope
