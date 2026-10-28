"""Current retained admission and cleanup hooks; no runtime or route effects.

Fresh start authority requires a live registered actual-job context, restricted
native transaction/CAS, acknowledged commit, exact post-read and a one-use local
permit. A UUID, replay, detached context or caller assertion is not that permit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
from types import MappingProxyType
import uuid

from sqlalchemy import text

from api.auth import CurrentUser
from db.app_models import ResearchExperimentRevision
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.execution_store import ExecutionReservationBinding
from orchestration.experiment_sandbox.retained_bridge import C23RetainedBridge
from orchestration.research_experiments import ResearchExperimentError
from schema.context_catalogue import canonical_json
from schema.research_experiments import content_sha256

_NAMESPACE = uuid.UUID('60e31c3f-d823-4a10-9f75-54e633f02570')
_LOCK = threading.RLock()
_PERMITS = {}


def _error(reason='sandbox_retained_admission'):
    raise SandboxError(reason)


def _after_fork():
    global _LOCK
    _LOCK = threading.RLock()
    _PERMITS.clear()


os.register_at_fork(after_in_child=_after_fork)


@dataclass(frozen=True, init=False)
class RetainedAdmissionSourcePolicy:
    """Pinned readonly source data only; no key, Linux fact or effect permit."""
    source_root: Path
    trust_scope: str
    _worker_files: object
    _profile_files: object
    _policy_bytes: bytes
    _binding_json: str

    def __init__(self, source_root, worker_source_files, profile_source_files,
                 source_policy_bytes, trust_scope):
        from orchestration.experiment_sandbox import physical_termination as physical
        from schema.experiment_execution import TerminationIssuerScope
        if trust_scope not in {'synthetic-software-test','retained-operator'}:
            raise ValueError('Explicit source trust scope required')
        worker,worker_hash = physical._manifest(worker_source_files,
            required=physical.WORKER_FILES|{'orchestration/experiment_sandbox/retained_admission.py'},
            version=physical.WORKER_POLICY_VERSION)
        profile,profile_hash = physical._manifest(profile_source_files,
            required=physical.PROFILE_FILES,version=physical.PROFILE_POLICY_VERSION)
        if (set(profile)!=physical.PROFILE_FILES
                or any(worker.get(name)!=digest for name,digest in profile.items())
                or type(source_policy_bytes) is not bytes or not 1<=len(source_policy_bytes)<=4096):
            raise ValueError('Exact complete worker/profile source policy required')
        try:
            policy=json.loads(source_policy_bytes)
            if (type(policy) is not dict or physical._canonical(policy)!=source_policy_bytes
                    or policy.get('version')!=physical.SOURCE_POLICY_VERSION
                    or policy.get('trust_scope')!=trust_scope):
                raise ValueError
            fields={name:value for name,value in policy.items() if name not in {'version','trust_scope'}}
            if set(fields)!=set(TerminationIssuerScope.model_fields)-{'site_id','source_policy_sha256'}:
                raise ValueError
            parsed=TerminationIssuerScope.model_validate({'site_id':'v1:policy-shape-only',
                'source_policy_sha256':hashlib.sha256(source_policy_bytes).hexdigest(),**fields})
            if (parsed.worker_source_sha256!=worker_hash or parsed.profile_policy_sha256!=profile_hash
                    or parsed.adapter_source_sha256!=worker['orchestration/experiment_sandbox/linux_runtime.py']
                    or parsed.trusted_init_sha256!=profile['sandbox/experiment/trusted_init.py']):
                raise ValueError
        except (ValueError,TypeError,UnicodeError):
            raise ValueError('Canonical source policy identity mismatch') from None
        root=Path(source_root)
        if not root.is_absolute():
            raise ValueError('Explicit absolute readonly source root required')
        binding={**fields,'source_policy_sha256':parsed.source_policy_sha256}
        for name,value in {'source_root':root,'trust_scope':trust_scope,
                '_worker_files':MappingProxyType(dict(worker)),
                '_profile_files':MappingProxyType(dict(profile)),
                '_policy_bytes':bytes(source_policy_bytes),'_binding_json':canonical_json(binding)}.items():
            object.__setattr__(self,name,value)

    def verify_current(self, context):
        from orchestration.experiment_sandbox import physical_termination as physical
        context.require_current()
        root=self.source_root
        before_root=root.lstat()
        if (root!=root.resolve(strict=True) or not stat.S_ISDIR(before_root.st_mode)
                or before_root.st_uid!=os.geteuid() or stat.S_IMODE(before_root.st_mode)!=0o700):
            _error('sandbox_retained_source_policy')
        total=0
        for name,digest in self._worker_files.items():
            context.require_current()
            path=root/name
            if path!=path.resolve(strict=True):
                _error('sandbox_retained_source_policy')
            before=path.lstat()
            if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
                    or before.st_mode&0o222 or before.st_nlink!=1
                    or not 1<=before.st_size<=physical.MAX_SOURCE_FILE_BYTES):
                _error('sandbox_retained_source_policy')
            descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
            try:
                raw=os.read(descriptor,physical.MAX_SOURCE_FILE_BYTES+1)
                if (len(raw)!=before.st_size or hashlib.sha256(raw).hexdigest()!=digest
                        or physical._stamp(before)!=physical._stamp(os.fstat(descriptor))
                        or physical._stamp(before)!=physical._stamp(path.lstat())):
                    _error('sandbox_retained_source_policy')
            finally:
                os.close(descriptor)
            total+=len(raw)
            if total>physical.MAX_SOURCE_BYTES:
                _error('sandbox_retained_source_policy')
        if physical._file_id(root.lstat())!=physical._file_id(before_root):
            _error('sandbox_retained_source_policy')
        if self.trust_scope=='retained-operator':
            physical.require_loaded_source_provenance(root,self._worker_files,
                check=context.require_current)
        context.require_current()


@dataclass(frozen=True, slots=True, init=False)
class FreshStartPermit:
    _pid: int
    _json: str

    def __init__(self, *args, **kwargs):
        raise TypeError('Use RetainedRuntimeHooks.admit_start')

    def consume(self, context):
        # Burn the matching permit BEFORE any journal append or runtime command.
        # A failed append, lost fence or changed head cannot reuse this authority.
        if type(self) is not FreshStartPermit or getattr(self,'_pid',None) != os.getpid():
            _error('sandbox_retained_start_permit')
        with _LOCK:
            record = _PERMITS.get(id(self))
            if record is None or record[0] is not self or record[1] is not context:
                _error('sandbox_retained_start_permit')
            del _PERMITS[id(self)]
        payload = json.loads(self._json)
        context.require_current(payload['preceding_journal_sha256'])
        return payload


@dataclass(frozen=True, slots=True, init=False)
class PublicationReceipt:
    _json: str

    def __init__(self, *args, **kwargs):
        raise TypeError('Use RetainedRuntimeHooks.admit_publication')

    @property
    def document(self):
        return json.loads(self._json)


class RetainedRuntimeHooks:
    def __init__(self, bridge, current_owner, source_policy):
        if (type(bridge) is not C23RetainedBridge or type(current_owner) is not CurrentUser
                or type(source_policy) is not RetainedAdmissionSourcePolicy):
            raise ValueError('Exact retained bridge and authenticated application owner required')
        bridge._binding()
        self.bridge, self.current_owner = bridge, current_owner
        self._store, self._config = bridge.store, bridge.store.config
        self._policy_json = bridge._material_json
        self.source_policy=self._source_policy=source_policy
        binding=json.loads(source_policy._binding_json)
        if (any(json.loads(self._policy_json).get(name)!=value for name,value in binding.items())
                or source_policy.trust_scope!=self._config.verifier_registry.trust_scope):
            raise ValueError('Retained bridge and source policy must be identical')
        self._started_contexts = {}

    def _context(self, context, head=None):
        # Local import preserves the context->identity dependency without cycles.
        from orchestration.experiment_sandbox.retained_context import HeldRuntimeContext
        if type(context) is not HeldRuntimeContext:
            _error('sandbox_retained_context_closed')
        snapshot = context.require_current(head)
        if (self.bridge.store is not self._store or self._store.config is not self._config
                or self.source_policy is not self._source_policy
                or context.site_id != self._config.site_id
                or context.owner_user_id != str(self.current_owner.id)):
            _error('sandbox_retained_store_binding')
        return snapshot

    def _execution(self, session, context):
        raw = session.scalar(text(f"SELECT to_jsonb(e)-'created_at' FROM {self._config.schema}."
            'research_experiment_execution e WHERE execution_id=CAST(:id AS uuid) AND site_id=:site'),
            {'id': context.execution_id, 'site': context.site_id})
        try:
            binding = ExecutionReservationBinding.model_validate(raw)
        except (ValueError, TypeError):
            _error('sandbox_retained_execution_binding')
        row, identity = binding.model_dump(mode='json'), context.execution_identity.document
        if (row['envelope_json'] != context.envelope._metadata_json
                or any(row[name] != identity[name] for name in (
                    'execution_id','reservation_id','owner_user_id','experiment_id','proposal_revision_id',
                    'approval_id','site_id','envelope_sha256','execution_request_sha256','job_id'))
                or any(row[name] != value for name,value in json.loads(self._policy_json).items())
                or row['source_sha256'] != content_sha256(context.envelope.metadata['manifest']['sources'])
                or row['runtime_sha256'] != content_sha256(json.loads(context.runtime_json))
                or row['trusted_init_sha256'] != context.profile.document['trusted_init']['sha256']
                or row['adapter_source_sha256'] != context.helper_sha256
                or row['worker_id'] != context.host_id
                or row['environment_sha256'] != context.envelope.metadata['hashes']['environment_sha256']):
            _error('sandbox_retained_execution_binding')
        return row

    def _sources(self,context):
        self._context(context)
        self._source_policy.verify_current(context)
        self._context(context)

    def _state(self, session, context):
        value = session.scalar(text(f'SELECT to_jsonb(s) FROM {self._config.schema}.'
            'research_experiment_execution_state s WHERE execution_id=CAST(:id AS uuid)'),
            {'id': context.execution_id})
        if type(value) is not dict:
            _error('sandbox_retained_execution_state')
        if value.get('execution_id')!=context.execution_id:
            _error('sandbox_retained_execution_state')
        return value

    def _event(self, session, identity):
        value = session.scalar(text(f'SELECT to_jsonb(e) FROM {self._config.schema}.'
            'research_experiment_execution_event e WHERE id=CAST(:id AS uuid)'), {'id': identity})
        if type(value) is not dict:
            _error('sandbox_retained_execution_event')
        return value

    def _candidate(self, context, row):
        self.bridge._enabled()
        request = json.loads(row['request_json'])
        address = {key:value for key,value in request.items() if key != 'idempotency_key'}
        candidate = self.bridge.inspection.inspect_approved(address, current_owner=self.current_owner)
        if (candidate.approval_id != row['approval_id']
                or candidate.approval_request_sha256 != row['approval_request_sha256']
                or candidate.source_sha256 != row['source_sha256']):
            _error('sandbox_retained_current_approval')
        self.bridge._material(candidate)
        self._sources(context)
        self._context(context)
        return address, candidate

    def _prepare_fence(self, session, context, row, address, candidate, head):
        service = self.bridge._service
        actor = service._actor(session, user=self.current_owner)
        item = service._owned(session, actor, row['experiment_id'])
        revision,frozen = service._revision(session, actor, item, active=True)
        current,proposal,exported = self.bridge.inspection._candidate(session,item,revision,address)
        if current != candidate:
            raise ResearchExperimentError('integrity_error',409)
        def closing():
            self._context(context,head)
            self.bridge._enabled()
            service._verify(frozen=frozen,proposal=proposal,actor=actor,exported=exported,access_only=True)
            self.bridge._binding()
            self._sources(context)
            session.expire_all()
            current_actor = service._closing_gate(session,user=self.current_owner,
                head_id=row['experiment_id'],revision_id=row['proposal_revision_id'],active=True)
            current_head = service._owned(session,current_actor,row['experiment_id'])
            current_revision = session.get(ResearchExperimentRevision,current_head.head_revision_id)
            actual,_,_ = self.bridge.inspection._candidate(session,current_head,current_revision,address)
            if actual != candidate:
                raise ResearchExperimentError('integrity_error',409)
            self._execution(session,context)
            self._context(context,head)
        return closing

    def admit_preparation(self, context):
        snapshot = self._context(context)
        self._sources(context)
        if snapshot.terminal or snapshot.reconciliation_required:
            _error('sandbox_retained_preparation_state')
        head = snapshot.events[-1].sha256
        with self._store.controller_transaction() as session:
            row = self._execution(session,context)
        address,candidate = self._candidate(context,row)
        with self._store.controller_transaction() as session:
            self._execution(session,context)
            state = self._state(session,context)
            if state['state'] != 'reserved' or state['fence'] != 1:
                _error('sandbox_retained_preparation_state')
            # No mutation here; still run the same last-current check ordering.
            self._store._controller(session)
            self._prepare_fence(session,context,row,address,candidate,head)()
        self._context(context,head)

    def admit_start(self, context):
        snapshot = self._context(context)
        self._sources(context)
        if snapshot.terminal or snapshot.reconciliation_required:
            _error('sandbox_retained_start_reconciliation')
        head = snapshot.events[-1].sha256
        with _LOCK:
            if id(context) in self._started_contexts:
                _error('sandbox_retained_start_reconciliation')
            self._started_contexts[id(context)] = context
        start_id = str(uuid.uuid4())  # Fresh internal identity, never caller input/retry.
        with self._store.controller_transaction() as session:
            row = self._execution(session,context)
        address,candidate = self._candidate(context,row)
        payload = {'version':'c23-retained-start-intent-v1','execution_id':context.execution_id,
            'reservation_id':context.reservation_id,'start_id':start_id,'start_event_id':start_id,
            'start_fence':2,'journal_id':context.journal_id,'journal_epoch':snapshot.epoch,
            'worker_id':row['worker_id'],'host_boot_id':context.host_boot_id,'job_id':context.job_id,
            'envelope_sha256':context.envelope_sha256,'profile_sha256':context.profile_sha256,
            'preceding_journal_sha256':head}
        with self._store.controller_transaction() as session:
            self._execution(session,context)
            state = self._state(session,context)
            exists = session.scalar(text(f'SELECT EXISTS(SELECT 1 FROM {self._config.schema}.'
                'research_experiment_execution_event WHERE id=CAST(:id AS uuid))'), {'id':start_id})
            if state['state'] != 'reserved' or state['fence'] != 1 or exists is not False:
                _error('sandbox_retained_start_reconciliation')
            closing = self._prepare_fence(session,context,row,address,candidate,head)
            result = self._store.event_after_fence_in_transaction(session,
                execution_id=context.execution_id,expected_fence=1,event_id=start_id,kind='start_consumed',
                start_id=start_id,host_boot_id=context.host_boot_id,journal_id=context.journal_id,
                journal_epoch=snapshot.epoch,profile_sha256=context.profile_sha256,
                preceding_journal_sha256=head,final_fence=closing)
            if result != start_id:
                _error('sandbox_retained_start_reconciliation')
        # Commit acknowledgement precedes minting. Unknown acknowledgement exits
        # with no permit; this context's latch prevents an automatic UUID retry.
        self._context(context,head)
        self._sources(context)
        with self._store.controller_transaction(cleanup=True) as session:
            self._execution(session,context)
            state = self._state(session,context)
            event = self._event(session,start_id)
            if (state['state'] != 'start_consumed' or state['fence'] != 2
                    or state['start_event_id'] != start_id or state['current_event_id'] != start_id
                    or event['kind'] != 'start_consumed' or event['start_id'] != start_id
                    or event['execution_id'] != context.execution_id
                    or event['reservation_id'] != context.reservation_id
                    or event['owner_user_id'] != context.owner_user_id
                    or event['envelope_sha256'] != context.envelope_sha256
                    or event['host_boot_id'] != context.host_boot_id
                    or event['journal_id'] != context.journal_id or event['fence'] != 2
                    or event['journal_epoch'] != snapshot.epoch or event['preceding_journal_sha256'] != head
                    or event['profile_sha256'] != context.profile_sha256):
                _error('sandbox_retained_start_reconciliation')
        self._context(context,head)
        value = object.__new__(FreshStartPermit)
        object.__setattr__(value,'_pid',os.getpid())
        object.__setattr__(value,'_json',canonical_json(payload))
        with _LOCK:
            _PERMITS[id(value)] = (value,context)
        return value

    def _terminal(self, context, terminal):
        from orchestration.experiment_sandbox.journal import DurableTerminalReference
        snapshot = self._context(context)
        actual = context.journal.terminal_reference(context.lease)
        if type(terminal) is not DurableTerminalReference or actual != terminal or not snapshot.terminal:
            _error('sandbox_retained_terminal_binding')
        return snapshot

    def _start(self, session, context, snapshot):
        state = self._state(session,context)
        if state['start_event_id'] is None:
            _error('sandbox_retained_missing_start')
        start = self._event(session,state['start_event_id'])
        if (start['kind'] != 'start_consumed' or start['id'] != start['start_id']
                or start['execution_id'] != context.execution_id
                or start['reservation_id'] != context.reservation_id
                or start['owner_user_id'] != context.owner_user_id
                or start['envelope_sha256'] != context.envelope_sha256
                or start['fence'] != 2 or start['host_boot_id'] != context.host_boot_id
                or start['journal_id'] != context.journal_id or start['profile_sha256'] != context.profile_sha256
                or not 1 <= start['journal_epoch'] <= snapshot.epoch):
            _error('sandbox_retained_start_binding')
        expected = {'version':'c23-retained-start-intent-v1','execution_id':context.execution_id,
            'reservation_id':context.reservation_id,'start_id':start['id'],'start_event_id':start['id'],
            'start_fence':2,'journal_id':context.journal_id,'journal_epoch':start['journal_epoch'],
            'worker_id':json.loads(self._policy_json)['worker_id'],'host_boot_id':context.host_boot_id,
            'job_id':context.job_id,'envelope_sha256':context.envelope_sha256,
            'profile_sha256':context.profile_sha256,'preceding_journal_sha256':start['preceding_journal_sha256']}
        intents = [event for event in snapshot.events if event.kind == 'start_intent']
        if (len(intents) != 1 or intents[0].payload != expected
                or intents[0].previous_sha256 != start['preceding_journal_sha256']
                or intents[0].epoch != start['journal_epoch']):
            _error('sandbox_retained_start_binding')
        return state,start

    def admit_publication(self, context, terminal, outputs_manifest_sha256):
        snapshot = self._terminal(context,terminal)
        self._sources(context)
        head = snapshot.events[-1].sha256
        record = snapshot.result['record']
        outputs = context.adapter._replay_outputs(context.worker_root/context.job_id,context.envelope,record)
        if (outputs is None or type(outputs_manifest_sha256) is not str
                or hashlib.sha256(outputs.manifest_bytes).hexdigest() != outputs_manifest_sha256
                or record.get('outputs_manifest_sha256') != outputs_manifest_sha256):
            _error('sandbox_retained_publication_bytes')
        with self._store.controller_transaction() as session:
            row = self._execution(session,context)
        address,candidate = self._candidate(context,row)
        event_id = str(uuid.uuid5(_NAMESPACE,'publication:'+context.execution_id+':'+terminal.terminal_result_sha256+':'+outputs_manifest_sha256))
        with self._store.controller_transaction() as session:
            self._execution(session,context)
            state,start = self._start(session,context,snapshot)
            if state['state'] not in {'start_consumed','publication_retained'}:
                _error('sandbox_retained_publication_state')
            if state['state']=='publication_retained' and state['current_event_id'] != event_id:
                _error('sandbox_retained_publication_state')
            closing = self._prepare_fence(session,context,row,address,candidate,head)
            result = self._store.event_after_fence_in_transaction(session,
                execution_id=context.execution_id,expected_fence=2,event_id=event_id,kind='publication_retained',
                start_id=start['start_id'],host_boot_id=start['host_boot_id'],journal_id=start['journal_id'],
                journal_epoch=terminal.epoch,profile_sha256=start['profile_sha256'],
                preceding_journal_sha256=start['preceding_journal_sha256'],result_sha256=outputs_manifest_sha256,
                final_fence=closing)
            if result != event_id:
                _error('sandbox_retained_publication_state')
        self._terminal(context,terminal)
        value = object.__new__(PublicationReceipt)
        object.__setattr__(value,'_json',canonical_json({'version':'c23-retained-publication-reference-v1',
            'execution_id':context.execution_id,'publication_event_id':event_id,'publication_fence':3,
            'outputs_manifest_sha256':outputs_manifest_sha256,'terminal_result_sha256':terminal.terminal_result_sha256,
            'publication_retained':True,'scientific_approval':'not_independently_verified','reservation_released':False}))
        return value

    def close_execution(self, context, terminal):
        snapshot = self._terminal(context,terminal)
        head = snapshot.events[-1].sha256
        event_id = str(uuid.uuid5(_NAMESPACE,'closed:'+context.execution_id+':'+terminal.terminal_result_sha256))
        with self._store.controller_transaction(cleanup=True) as session:
            self._execution(session,context)
            state,start = self._start(session,context,snapshot)
            if state['state']=='closed':
                old = self._event(session,state['current_event_id'])
                if old['id'] != event_id:
                    _error('sandbox_retained_close_binding')
                expected_fence = old['fence']-1
            else:
                expected_fence = state['fence']
            result = self._store.event_after_fence_in_transaction(session,
                execution_id=context.execution_id,expected_fence=expected_fence,event_id=event_id,kind='closed',
                start_id=start['start_id'],host_boot_id=start['host_boot_id'],journal_id=start['journal_id'],
                journal_epoch=terminal.epoch,profile_sha256=start['profile_sha256'],
                preceding_journal_sha256=start['preceding_journal_sha256'],result_sha256=terminal.terminal_result_sha256,
                terminal_sequence=terminal.terminal_sequence,terminal_head_sha256=terminal.terminal_head_sha256,
                final_fence=lambda:self._terminal(context,terminal))
            if result != event_id:
                _error('sandbox_retained_close_binding')
        self._context(context,head)
        return self._closed(context,terminal)

    def _closed(self, context, terminal):
        from schema.experiment_execution import ClosedExecutionBinding
        snapshot=self._terminal(context,terminal)
        with self._store.controller_transaction(cleanup=True) as session:
            row=self._execution(session,context)
            state,_=self._start(session,context,snapshot)
            event=self._event(session,state['current_event_id'])
            if (state['state']!='closed' or event['kind']!='closed' or event['fence']!=state['fence']
                    or event['journal_epoch']!=terminal.epoch
                    or event['terminal_sequence']!=terminal.terminal_sequence
                    or event['terminal_head_sha256']!=terminal.terminal_head_sha256
                    or event['result_sha256']!=terminal.terminal_result_sha256):
                _error('sandbox_retained_close_binding')
        binding = self._store.load_closed_binding(context.execution_id)
        expected={name:row[name] for name in ClosedExecutionBinding.model_fields if name in row}
        expected.update(closed_fence=state['fence'],host_boot_id=context.host_boot_id,
            journal_id=context.journal_id,journal_epoch=terminal.epoch,profile_sha256=context.profile_sha256)
        if binding.model_dump(mode='json')!=expected:
            _error('sandbox_retained_close_binding')
        self._terminal(context,terminal)
        return binding

    def record_termination(self, context, packet_bytes):
        self._context(context)
        terminal = context.journal.terminal_reference(context.lease)
        self._closed(context,terminal)
        result = self._store.record_verified_termination(execution_id=context.execution_id,packet_bytes=packet_bytes)
        self._terminal(context,terminal)
        return result

    def release_terminated(self, context, proof_id, closed_fence):
        self._context(context)
        terminal = context.journal.terminal_reference(context.lease)
        binding = self._closed(context,terminal)
        if type(closed_fence) is not int or closed_fence != binding.closed_fence:
            _error('sandbox_retained_close_binding')
        result = self._store.release_terminated(execution_id=context.execution_id,
            proof_id=proof_id,expected_fence=closed_fence)
        self._terminal(context,terminal)
        return result
