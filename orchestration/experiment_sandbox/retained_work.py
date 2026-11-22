"""Private controller polling of the same durable C23 reservation ledger."""
from dataclasses import dataclass, field
import json

from pydantic import TypeAdapter
from sqlalchemy import text

from api.auth import CurrentUser
from orchestration.experiment_sandbox.contracts import SandboxError, VerifiedEnvelope
from orchestration.experiment_sandbox.retained_bridge import C23RetainedBridge, RetainedExecutionIdentity
from orchestration.research_experiments import ResearchExperimentError
from schema.investigations import UUIDString

_execution_id = TypeAdapter(UUIDString)


@dataclass(frozen=True)
class RetainedWorkStatus:
    execution_id: str
    state: str
    exact_material: bool


@dataclass(frozen=True)
class RetainedWork:
    owner: CurrentUser = field(repr=False)
    identity: RetainedExecutionIdentity = field(repr=False)
    envelope: VerifiedEnvelope = field(repr=False)


class RetainedWorkQueue:
    """Reopen committed work without a browser acknowledgement or owner claim.

    Instantiate only in a trusted controller with the explicit C23 owner-read
    grants. Ready-looking rows are observations, never a lease or permission to
    execute. The exact journal/preparation/start fences still own admission.
    """

    def __init__(self, *, bridge):
        if type(bridge) is not C23RetainedBridge:
            raise ValueError('An explicit retained controller is required')
        bridge._binding()
        self._bridge = bridge
        self._store = bridge.store
        self._config = bridge.store.config
        self._policy_json = bridge._material_json

    def _binding(self):
        self._bridge._binding()
        if (self._bridge.store is not self._store or self._store.config is not self._config
                or self._bridge._material_json != self._policy_json):
            raise SandboxError('sandbox_retained_work_binding')

    def _select(self):
        schema = self._config.schema
        return (f'FROM {schema}.research_experiment_execution e '
            f'JOIN {schema}.research_experiment_execution_state s USING (execution_id) '
            'WHERE e.site_id=:site AND e.worker_id=:worker '
            f'AND NOT EXISTS (SELECT 1 FROM {schema}.research_experiment_release r '
            'WHERE r.execution_id=e.execution_id)')

    def _parameters(self):
        return {'site': self._config.site_id, 'worker': json.loads(self._policy_json)['worker_id'],
                'policy': self._policy_json}

    def list_unreleased(self):
        """Observe held work for this worker even while new starts are paused."""
        self._binding()
        with self._store.controller_transaction(cleanup=True) as session:
            rows = session.execute(text(
                'SELECT e.execution_id, s.state, to_jsonb(e) @> CAST(:policy AS jsonb) AS exact_material '
                + self._select() + ' ORDER BY e.created_at, e.execution_id LIMIT 3'), self._parameters()).all()
        self._binding()
        if len(rows) > 2:
            raise SandboxError('sandbox_retained_work_capacity')
        return tuple(RetainedWorkStatus(str(row.execution_id), row.state, row.exact_material) for row in rows)

    def reopen(self, execution_id):
        """Resolve current owner and exact inputs for this worker's pending row."""
        try:
            execution_id = _execution_id.validate_python(execution_id, strict=True)
        except (ValueError, TypeError):
            raise ResearchExperimentError('invalid_request', 422) from None
        self._binding()
        self._bridge._enabled()
        with self._store.controller_transaction() as session:
            row = session.execute(text(
                'SELECT e.owner_user_id, s.state, s.fence, to_jsonb(e) @> CAST(:policy AS jsonb) AS exact_material '
                + self._select() + ' AND e.execution_id=CAST(:id AS uuid)'),
                {**self._parameters(), 'id': execution_id}).one_or_none()
            if row is None:
                raise ResearchExperimentError('not_found', 404)
            if (row.state, row.fence, row.exact_material) != ('reserved', 1, True):
                raise ResearchExperimentError('conflict', 409)
            owner = self._bridge.inspection.service._actor(session, owner_id=row.owner_user_id)
        identity, envelope = self._bridge.reopen_pending(execution_id, current_owner=owner)
        self._binding()
        return RetainedWork(owner, identity, envelope)
