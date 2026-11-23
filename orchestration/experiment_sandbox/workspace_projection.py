"""Read-only C25 projection from the isolated C23 execution and release ledger."""

from dataclasses import asdict
import json

from sqlalchemy import text

from orchestration.experiment_sandbox.contracts import ExecutionMetadata, SandboxError
from orchestration.experiment_sandbox.execution_store import C23ExecutionStore, ExecutionReservationBinding
from orchestration.experiment_sandbox.proofs import verify_termination_packet
from orchestration.experiment_sandbox.retained_bridge import RetainedReserveRequest
from orchestration.experiment_sandbox.retained_output_store import RetainedOutputReader
from orchestration.experiment_workspace import ExperimentExecutionPort, ExperimentWorkspaceError
from schema.experiment_execution import ClosedExecutionBinding


_EVENT_TEXT = {
    'reserved': ('Execution capacity reserved.', '実行枠を確保しました。'),
    'start_consumed': ('The worker consumed the start permit.', 'ワーカーが実行許可を使用しました。'),
    'publication_retained': ('The validated output manifest was retained.', '検証済みの出力目録を保存しました。'),
    'closed': ('The worker recorded a terminal observation.', 'ワーカーが終了時の観測を記録しました。'),
    'released': ('Termination proof verified and execution capacity released.',
                 '終了の証明を検証し、実行枠を解放しました。'),
}

_LEDGER_STATES = {
    (): 'reserved',
    ('start_consumed',): 'start_consumed',
    ('start_consumed', 'publication_retained'): 'publication_retained',
    ('start_consumed', 'closed'): 'closed',
    ('start_consumed', 'publication_retained', 'closed'): 'closed',
}


class RetainedExecutionProjection(ExperimentExecutionPort):
    """Expose confirmed metadata and output bytes from an isolated controller.

    The existing C22 service authorizes each request and repeats its authority
    check after the read. This port uses a separate read-only SQL transaction
    and can read validated outputs from explicitly configured private storage.
    """

    def __init__(self, *, experiments, store, output_reader=None):
        super().__init__(experiments=experiments, source='retained-operator',
                         cancel_available=False, artifacts_available=output_reader is not None)
        if (type(store) is not C23ExecutionStore or store.config.site_id != self.site_id
                or store.config.controller_session_factory is self.session_factory
                or (output_reader is not None and type(output_reader) is not RetainedOutputReader)):
            raise ValueError('An exact, separate C23 store is required for the execution projection')
        self._store, self._config = store, store.config
        self._output_reader = output_reader

    @staticmethod
    def _verify_identity(row, access):
        try:
            binding = ExecutionReservationBinding.model_validate(row.identity)
            envelope = ExecutionMetadata.model_validate_json(binding.envelope_json).model_dump(mode='json')
            request = RetainedReserveRequest.model_validate_json(binding.request_json).model_dump(mode='json')
        except (TypeError, ValueError):
            raise ExperimentWorkspaceError('integrity_error', 409) from None
        # A historical proposal can retain this approval even after the current
        # head's concurrency token changes. The frozen address and hashes still
        # have to match both the retained request and envelope.
        context, hashes = json.loads(access.binding_json), json.loads(access.hashes_json)
        if (any(envelope[field] != getattr(binding, field) for field in (
                'site_id', 'owner_user_id', 'experiment_id', 'proposal_revision_id', 'reservation_id', 'approval_id'))
                or envelope['binding'] != context or envelope['hashes'] != hashes
                or request['expected_hashes'] != hashes
                or request['experiment_id'] != access.experiment_id
                or request['expected_proposal_revision_id'] != access.proposal_revision_id
                or request['idempotency_key'] != binding.idempotency_key
                or any(request[key] != value for key, value in context.items())):
            raise ExperimentWorkspaceError('integrity_error', 409)
        return binding

    @staticmethod
    def _verified_release(row, binding, closed, registry):
        if (closed is None or closed.kind != 'closed' or row.packet is None
                or registry.trust_scope != 'retained-operator'):
            raise ExperimentWorkspaceError('integrity_error', 409)
        try:
            expected = ClosedExecutionBinding.model_validate({
                **binding.model_dump(include=set(ClosedExecutionBinding.model_fields)),
                'closed_fence': closed.fence,
                'host_boot_id': str(closed.host_boot_id), 'journal_id': str(closed.journal_id),
                'journal_epoch': closed.journal_epoch, 'profile_sha256': closed.profile_sha256,
            })
            verified = verify_termination_packet(bytes(row.packet), expected=expected, registry=registry)
        except (TypeError, ValueError, SandboxError):
            raise ExperimentWorkspaceError('integrity_error', 409) from None
        witness = verified.claims.journal
        if (verified.packet_sha256 != row.packet_sha256
                or (witness.terminal_sequence, witness.terminal_head_sha256, witness.terminal_result_sha256)
                != (closed.terminal_sequence, closed.terminal_head_sha256, closed.result_sha256)):
            raise ExperimentWorkspaceError('integrity_error', 409)
        return verified.packet_sha256

    def _read(self, access, execution_id, *, artifact_id=None):
        if access.site_id != self.site_id or self._store.config is not self._config:
            raise ExperimentWorkspaceError('integrity_error', 409)
        if access.approval_id is None:
            return None, [], None
        schema = self._config.schema
        parameters = {'site': access.site_id, 'owner': access.owner_user_id, 'experiment': access.experiment_id,
                      'revision': access.proposal_revision_id, 'approval': access.approval_id,
                      'approval_sha256': access.approval_request_sha256}
        id_filter = ''
        if execution_id is not None:
            id_filter = ' AND e.execution_id=CAST(:execution AS uuid)'
            parameters['execution'] = execution_id
        with self._config.controller_session_factory.begin() as session:
            session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            self._store._check_session(session, self._config.roles.controller_role)
            row = session.execute(text(
                f"SELECT to_jsonb(e)-'created_at' AS identity,s.state,s.fence,s.start_event_id,s.current_event_id,"
                'r.id IS NOT NULL AS released,p.packet_bytes AS packet,p.packet_sha256 '
                f'FROM {schema}.research_experiment_execution e '
                f'LEFT JOIN {schema}.research_experiment_execution_state s USING (execution_id) '
                f'LEFT JOIN {schema}.research_experiment_release r USING (execution_id) '
                f'LEFT JOIN {schema}.research_experiment_termination_proof p '
                'ON p.id=r.proof_id AND p.closed_event_id=s.current_event_id AND p.closed_fence=s.fence '
                'WHERE e.site_id=:site AND e.owner_user_id=CAST(:owner AS uuid) '
                'AND e.experiment_id=CAST(:experiment AS uuid) AND e.proposal_revision_id=CAST(:revision AS uuid) '
                'AND e.approval_id=CAST(:approval AS uuid) AND e.approval_request_sha256=:approval_sha256'
                + id_filter), parameters).one_or_none()
            if row is None:
                return None, [], None
            binding = self._verify_identity(row, access)
            ledger = session.execute(text(
                'SELECT id,fence,kind,host_boot_id,journal_id,journal_epoch,profile_sha256,'
                f'result_sha256,terminal_sequence,terminal_head_sha256 FROM {schema}.research_experiment_execution_event '
                'WHERE execution_id=CAST(:execution AS uuid) ORDER BY fence LIMIT 4'),
                {'execution': binding.execution_id}).all()

        kinds = tuple(event.kind for event in ledger)
        first = ledger[0] if ledger else None
        last = ledger[-1] if ledger else None
        if (row.state is None or _LEDGER_STATES.get(kinds) != row.state
                or [event.fence for event in ledger] != list(range(2, len(ledger) + 2))
                or (row.fence, row.start_event_id, row.current_event_id)
                != (len(ledger) + 1, first.id if first else None, last.id if last else None)):
            raise ExperimentWorkspaceError('integrity_error', 409)

        proof = self._verified_release(row, binding, last, self._config.verifier_registry) if row.released else None
        output_hash = next((event.result_sha256 for event in ledger if event.kind == 'publication_retained'), None)
        state = 'queued' if not ledger else 'verifying'
        if proof is not None:
            state = 'completed' if output_hash is not None else 'outcome_unavailable'
        files, artifact_bytes = (), None
        try:
            if state == 'completed' and self._output_reader is not None:
                files = self._output_reader.describe(binding, output_hash,
                    expected_outputs=json.loads(access.expected_outputs_json), max_bytes=access.output_limit)
            if artifact_id is not None:
                file = next((item for item in files if item.id == artifact_id), None)
                if file is None:
                    raise ExperimentWorkspaceError('not_found', 404)
                artifact_bytes = self._output_reader.read_file(binding, output_hash, file)
        except SandboxError as exc:
            if exc.reason == 'sandbox_output_store_integrity':
                raise ExperimentWorkspaceError('integrity_error', 409) from None
            raise ExperimentWorkspaceError() from None

        event_kinds = ['reserved', *kinds]
        if proof is not None:
            event_kinds.append('released')
        items = []
        for cursor, kind in enumerate(event_kinds, 1):
            en, ja = _EVENT_TEXT[kind]
            items.append({'cursor': cursor, 'kind': kind, 'summary': {'en': en, 'ja': ja}})
        snapshot = {'id': binding.execution_id, 'source': self.source, 'state': state,
                    'state_revision': len(items), 'latest_event_cursor': len(items),
                    'execution_performed': state == 'completed', 'cancel_requested': False,
                    'termination_verified': proof is not None, 'termination_proof_sha256': proof,
                    'outputs_manifest_sha256': output_hash if state == 'completed' else None,
                    'artifacts': [asdict(file) for file in files]}
        return {'access_sha256': access.sha256, 'execution': snapshot}, items, artifact_bytes

    def status(self, access, execution_id=None):
        status, _, _ = self._read(access, execution_id)
        return status

    def status_and_events(self, access, execution_id, after_cursor, limit):
        status, items, _ = self._read(access, execution_id)
        if status is None:
            raise ExperimentWorkspaceError('not_found', 404)
        if after_cursor > len(items):
            raise ExperimentWorkspaceError('conflict', 409)
        page = items[after_cursor:after_cursor + limit]
        next_cursor = after_cursor + len(page)
        return status, {'items': page, 'next_cursor': next_cursor, 'latest_event_cursor': len(items),
                        'has_more': next_cursor < len(items)}

    def events(self, access, execution_id, after_cursor, limit):
        _, page = self.status_and_events(access, execution_id, after_cursor, limit)
        return page

    def cancel(self, access, execution_id, idempotency_key, *, closing_authorize):
        raise ExperimentWorkspaceError()

    def artifact(self, access, execution_id, artifact_id):
        if self._output_reader is None:
            raise ExperimentWorkspaceError()
        status, _, raw = self._read(access, execution_id, artifact_id=artifact_id)
        if status is None:
            raise ExperimentWorkspaceError('not_found', 404)
        return raw
