"""C25 artifacts retained as experimental C17 context through explicit ports.

The port's durable locator is only a lookup hint. Every read re-authorizes its
actual C22 owner, immutable proposal/approval and source binding, validates the
C25 output projection and complete safe file bytes, then closes authorization.
No experimental output becomes a C21 receipt or an execution approval.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import json
import uuid

from sqlalchemy import select

from db.app_models import AppUser, ResearchContextOperation, ResearchContextRevision
from orchestration.experiment_workspace import ExperimentWorkspaceService, ExperimentWorkspaceError
from orchestration.investigations import RetainedArtifactBinding
from orchestration.retained_artifacts import RetainedArtifactProvider
from orchestration.research_experiments import HASH_FIELDS
from schema.context_catalogue import canonical_json


@dataclass(frozen=True)
class ExecutionArtifactLocator:
    owner_user_id: str
    site_id: str
    experiment_id: str
    proposal_revision_id: str
    execution_id: str
    artifact_id: str
    snapshot_id: str
    artifact_sha256: str
    access_sha256: str


@dataclass(frozen=True)
class ContextArtifactPin:
    site_id: str
    owner_user_id: str
    investigation_id: str
    operation_id: str
    revision_id: str
    candidate_sha256: str
    reference_json: str
    artifact_sha256: str
    access_sha256: str
    execution_id: str

    @property
    def identity(self):
        return hashlib.sha256(canonical_json([self.site_id, self.owner_user_id,
            self.operation_id, self.reference_json]).encode()).hexdigest()


class RetainedExecutionArtifactPort(ABC):
    """Additional explicit capability; absent on the default execution port.

    Implementations durably bind an exact locator and pin before acknowledging,
    enforce pin immutability and prevent artifact mutation/deletion while any
    prepared or committed pin exists. A failed/uncertain application commit is
    never a reason to release. No automatic release interface is supplied.
    """
    @abstractmethod
    def artifact_locator(self, owner_user_id, reference):
        """Return ExecutionArtifactLocator or None from the owner's durable index."""

    @abstractmethod
    def retain_artifact(self, pin: ContextArtifactPin, *, committed, closing_authorize):
        """Durable exact idempotent pin; close authority immediately before commit."""

    @abstractmethod
    def verify_artifact_retention(self, pin: ContextArtifactPin):
        """True only for the identical committed pin and still retained bytes."""


class ExperimentArtifactProvider(RetainedArtifactProvider):
    def __init__(self, *, workspace):
        if (not isinstance(workspace, ExperimentWorkspaceService)
                or not isinstance(workspace.port, RetainedExecutionArtifactPort)):
            raise ValueError('Explicit retention-capable C25 execution port required')
        super().__init__(investigations=workspace.investigations)
        self.workspace, self.port = workspace, workspace.port

    def _ready(self):
        self.workspace._binding()
        if self.workspace.port is not self.port or not self.workspace._capability()['artifacts_enabled']:
            raise ExperimentWorkspaceError()

    def authorize_owner(self, session, user):
        # C17 catalogue-only contexts retain their own read permission contract.
        # Acquire the common owner fence before site/target locks; C22's stricter
        # experiment permissions are checked only when resolving its artifacts.
        session.scalar(select(AppUser).where(AppUser.id == user.id)
            .with_for_update(key_share=True).execution_options(populate_existing=True))
        self.investigations._actor(session, user)

    def _access(self, session, user, locator):
        service = self.workspace.experiments
        actor = service._actor(session, user=user)
        if (locator.owner_user_id != str(actor.id) or locator.site_id != self.site_id
                or self.investigations.site_id != self.site_id
                or self.investigations.session_factory is not self.session_factory):
            raise ExperimentWorkspaceError('access_denied', 403)
        head = service._owned(session, actor, locator.experiment_id)
        revision, _ = service._revision(session, actor, head, locator.proposal_revision_id)
        request = {**service._binding(revision), 'experiment_id': str(head.id),
            'expected_version': head.version, 'expected_proposal_revision_id': str(revision.id),
            'expected_hashes': {key: getattr(revision, key) for key in HASH_FIELDS}}
        access = self.workspace._authorized(session, request, user)
        if (access.approval_id is None or access.sha256 != locator.access_sha256
                or json.loads(access.binding_json)['snapshot_id'] != locator.snapshot_id):
            raise ExperimentWorkspaceError('access_denied', 403)
        return access

    def _close(self, session, user, locator, expected):
        self._ready()
        if self._access(session, user, locator) != expected:
            raise ExperimentWorkspaceError('access_denied', 403)

    def _resolved(self, session, user, reference, *, close=True):
        self._ready()
        locator = self.port.artifact_locator(str(user.id), reference)
        if locator is None:
            return None
        if (not isinstance(locator, ExecutionArtifactLocator)
                or reference != {'kind': 'artifact', 'id': locator.artifact_id, 'snapshot_id': locator.snapshot_id}):
            raise ExperimentWorkspaceError('integrity_error', 409)
        access = self._access(session, user, locator)
        # Internal validation omits recursive attachment availability only. Every
        # projection/output bound and safe-file check is the actual C25 path.
        execution = self.workspace._snapshot(access, user, locator.execution_id, resolve_attachments=False)
        if execution is None:
            raise ExperimentWorkspaceError('not_found', 404)
        result = self.workspace._artifact(access, execution, {'artifact_id': locator.artifact_id,
            'expected_sha256': locator.artifact_sha256, 'offset': 0, 'limit': 1})
        if result['artifact']['attachment_reference'] != reference:
            raise ExperimentWorkspaceError('integrity_error', 409)
        if close:
            self._close(session, user, locator, access)
        return locator, access, RetainedArtifactBinding(id=locator.artifact_id,
            snapshot_id=locator.snapshot_id, sha256=locator.artifact_sha256, owner_user_id=user.id)

    def resolve(self, session, user, reference):
        result = self._resolved(session, user, reference)
        return result[2] if result is not None else None

    def _pin(self, operation, candidate, reference, user, locator):
        if (operation.user_id != user.id or operation.candidate_revision_id is None
                or operation.candidate_json != canonical_json(candidate)
                or reference not in [*candidate['attachments'], *candidate['pins']]
                or candidate.get('artifact_bindings', {}).get(hashlib.sha256(canonical_json(reference).encode()).hexdigest()) != locator.artifact_sha256):
            raise ExperimentWorkspaceError('integrity_error', 409)
        return ContextArtifactPin(site_id=self.site_id, owner_user_id=str(user.id),
            investigation_id=str(operation.investigation_id), operation_id=str(operation.id),
            revision_id=str(operation.candidate_revision_id),
            candidate_sha256=hashlib.sha256(operation.candidate_json.encode()).hexdigest(),
            reference_json=canonical_json(reference), artifact_sha256=locator.artifact_sha256,
            access_sha256=locator.access_sha256, execution_id=locator.execution_id)

    def _retain(self, session, operation, candidate, reference, user, *, committed):
        result = self._resolved(session, user, reference)
        if result is None:
            raise ExperimentWorkspaceError('not_found', 404)
        locator, access, _ = result
        pin = self._pin(operation, candidate, reference, user, locator)
        closed = []
        def closing_authorize():
            self._close(session, user, locator, access)
            closed.append(True)
        self.port.retain_artifact(pin, committed=committed, closing_authorize=closing_authorize)
        if not closed or (committed and self.port.verify_artifact_retention(pin) is not True):
            raise ExperimentWorkspaceError('integrity_error', 409)
        self._close(session, user, locator, access)

    def prepare_context(self, session, operation, candidate, reference, user):
        self._retain(session, operation, candidate, reference, user, committed=False)

    def activate_context(self, session, operation, candidate, reference, user):
        self._retain(session, operation, candidate, reference, user, committed=True)

    def verify_context(self, session, revision_id, reference, expected_sha256, user):
        # One safe lookup serves both resolution and context verification. The
        # closing fence runs after the durable-pin callback below, rather than
        # repeating full authorization and byte validation in a second lookup.
        result = self._resolved(session, user, reference, close=False)
        if result is None:
            return None
        if result[2].sha256 != expected_sha256:
            raise ExperimentWorkspaceError('access_denied', 403)
        locator, access, _ = result
        revision = session.get(ResearchContextRevision, uuid.UUID(str(revision_id)))
        operation = session.scalar(select(ResearchContextOperation).where(
            ResearchContextOperation.candidate_revision_id == uuid.UUID(str(revision_id)),
            ResearchContextOperation.user_id == user.id))
        if (revision is None or operation is None or operation.state != 'committed'
                or revision.investigation_id != operation.investigation_id
                or revision.payload_json != operation.candidate_json
                or revision.payload_sha256 != hashlib.sha256(revision.payload_json.encode()).hexdigest()):
            raise ExperimentWorkspaceError('integrity_error', 409)
        pin = self._pin(operation, json.loads(revision.payload_json), reference, user, locator)
        if self.port.verify_artifact_retention(pin) is not True:
            raise ExperimentWorkspaceError('integrity_error', 409)
        self._close(session, user, locator, access)
        return result[2]
