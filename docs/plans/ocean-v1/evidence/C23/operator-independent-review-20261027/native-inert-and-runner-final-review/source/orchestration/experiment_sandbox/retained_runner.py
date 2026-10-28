"""Explicit retained lifecycle over reviewed base operations and a held job.

No serving route or synthetic callback is registered. Host-safe tests mock native
boundaries; actual Linux/retained end-to-end acceptance remains separate. A
report exposes authorized publication references, never quarantined output bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import uuid

from orchestration.experiment_sandbox import linux_runtime as native
from orchestration.experiment_sandbox import physical_termination as physical
from orchestration.experiment_sandbox.contracts import SandboxError, VerifiedEnvelope
from orchestration.experiment_sandbox.profile_execution import PreparedExecutionProfile
from orchestration.experiment_sandbox.proofs import canonical_packet_bytes
from orchestration.experiment_sandbox.retained_bridge import RetainedExecutionIdentity
from orchestration.experiment_sandbox.retained_context import _hold_runtime_context
from schema.context_catalogue import canonical_json
from schema.experiment_execution import ClosedExecutionBinding

VERSION = 'c23-retained-run-report-v1'


@dataclass(frozen=True, init=False, slots=True)
class RetainedRunReport:
    """Detached status/reference document; no private output or launch capability."""
    _json: str

    def __init__(self, *args, **kwargs):
        raise TypeError('Use run_retained')

    @property
    def document(self):
        return json.loads(self._json)

    @property
    def state(self):
        return self.document['state']


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _error(reason='sandbox_retained_runner_binding'):
    raise SandboxError(reason)


def _uuid(value):
    if type(value) is not str or str(uuid.UUID(value)) != value:
        _error()
    return value


def _reason(error, fallback='sandbox_retained_runtime_uncertain'):
    if (type(error) is SandboxError and type(error.reason) is str
            and re.fullmatch(r'sandbox_[a-z0-9_]{1,96}',error.reason)):
        return error.reason
    return fallback


@dataclass
class _Run:
    job: Path
    document: dict
    runtime_sha256: str
    argv: list
    outer: Path
    host: Path
    create_argv: list
    identity: tuple | None = None
    handle: object = None
    capture: object = None
    watchdog: object = None
    observation: object = None
    attempted: bool = False
    started: bool | None = False
    waited: int | None = None
    execution_error: str | None = None
    outputs: object = None
    frame: bytes | None = None
    init: dict | None = None
    logs: dict | None = None
    state: str = 'uncertain'
    reason: str = 'reconciliation_required'
    diagnostic_error: str | None = None
    terminal: object = None


def _report(context, run, *, reason=None, publication=None, publication_status='not_attempted',
            closed=None, proof_id=None, release_id=None, release_status='not_attempted',
            errors=None, replayed=False):
    terminal = run.terminal
    document = {'version':VERSION,'execution_id':context.execution_id,'reservation_id':context.reservation_id,
        'job_id':context.job_id,'envelope_sha256':context.envelope_sha256,'profile_sha256':context.profile_sha256,
        'state':run.state,'reason':reason or run.reason,'start_attempted':run.attempted,
        'execution_started':run.started,'analysis_exit_code':run.init['analysis_exit_code'] if run.init else None,
        'host_runtime_exit_status':run.waited,'native_cleanup_recorded':run.observation is not None,
        'durable_terminal':None if terminal is None else {
            'journal_id':terminal.journal_id,'journal_epoch':terminal.epoch,
            'terminal_sequence':terminal.terminal_sequence,'terminal_head_sha256':terminal.terminal_head_sha256,
            'terminal_result_sha256':terminal.terminal_result_sha256},
        'publication_status':publication_status,'publication_reference':publication,
        'closed_fence':None if closed is None else closed.closed_fence,
        'termination_proof_id':proof_id,'release_id':release_id,'capacity_release_status':release_status,
        'reservation_released':True if release_status=='acknowledged' else None,
        'errors':errors or [],'diagnostic_error':run.diagnostic_error,'replayed':replayed,
        'scientific_approval':'not_independently_verified','authority':'experimental'}
    value = object.__new__(RetainedRunReport)
    object.__setattr__(value,'_json',canonical_json(document))
    return value


def _guarded_call(context, callback, *args):
    before = context.require_current()
    value = callback(context,*args)
    context.require_current(before.events[-1].sha256)
    return value


def _start_payload(context, permit):
    from orchestration.experiment_sandbox.retained_admission import FreshStartPermit
    if type(permit) is not FreshStartPermit:
        _error('sandbox_retained_start_permit')
    snapshot = context.require_current()
    head = snapshot.events[-1].sha256
    payload = permit.consume(context)
    context.require_current(head)
    keys = {'version','execution_id','reservation_id','start_id','start_event_id','start_fence',
        'journal_id','journal_epoch','worker_id','host_boot_id','job_id','envelope_sha256',
        'profile_sha256','preceding_journal_sha256'}
    if (type(payload) is not dict or set(payload)!=keys
            or payload['version']!=physical.START_INTENT_VERSION
            or payload['execution_id']!=context.execution_id or payload['reservation_id']!=context.reservation_id
            or payload['job_id']!=context.job_id or payload['envelope_sha256']!=context.envelope_sha256
            or payload['profile_sha256']!=context.profile_sha256 or payload['journal_id']!=context.journal_id
            or payload['journal_epoch']!=snapshot.epoch or type(payload['journal_epoch']) is not int
            or payload['worker_id']!=context.host_id or payload['host_boot_id']!=context.host_boot_id
            or payload['preceding_journal_sha256']!=head or payload['start_id']!=payload['start_event_id']
            or type(payload['start_fence']) is not int or payload['start_fence']<2):
        _error('sandbox_retained_start_permit')
    _uuid(payload['start_id'])
    return payload


def _retained_start(snapshot, context):
    starts = [event for event in snapshot.events if event.kind=='start_intent']
    if len(starts)!=1:
        return False
    p = starts[0].payload
    return (p.get('version')==physical.START_INTENT_VERSION
        and p.get('execution_id')==context.execution_id and p.get('reservation_id')==context.reservation_id
        and p.get('job_id')==context.job_id and p.get('envelope_sha256')==context.envelope_sha256
        and p.get('profile_sha256')==context.profile_sha256
        and p.get('journal_id')==context.journal_id and p.get('host_boot_id')==context.host_boot_id)


def _fresh_execute(context, run, hooks, cancelled):
    adapter, envelope, profile, lease = context.adapter, context.envelope, context.profile, context.lease
    _guarded_call(context,hooks.admit_preparation)
    context.require_current()
    if cancelled() is True:
        _error('sandbox_cancelled')
    context.require_current()
    lease.append('prepared',{'profile_sha256':profile.profile_sha256,'runtime_sha256':run.runtime_sha256})
    native._put(run.job/'config.json',(canonical_json(profile.config)+'\n').encode(),reuse=True)
    state_root = context.worker_root/('runsc-state-'+context.job_id)
    state_root.mkdir(mode=0o700)
    native._sync_directory(context.worker_root)
    lease.append('cgroup_intent',{'path':'/ocean-c23/'+context.job_id})
    context.require_current()
    run.identity = native.LinuxExecutionAdapter._prepare_cgroups(adapter,context.job_id,run.document['requirements'])
    lease.append('create_intent',{'profile_sha256':profile.profile_sha256,'cgroup_identity':list(run.identity)})
    run.handle = physical.open_original_cgroup(adapter,envelope,profile,lease,run.identity)
    if type(run.handle) is not physical.OriginalCgroupHandle:
        _error('sandbox_retained_native_handle')
    deadline = adapter.clock()+envelope.resources['wall_seconds']
    run.watchdog = native._arm_watchdog(run.outer,deadline)
    lease.append('watchdog_armed',{'pid':run.watchdog.pid,'host_boot_id':context.host_boot_id,
                                  'deadline_monotonic':deadline})
    frame_limit = len(native.MAGIC)+40+native.max_payload_bytes(envelope.resources['max_output_bytes'])
    run.capture = native.LinuxExecutionAdapter._spawn(adapter,run.create_argv,run.host,
        deadline=deadline,frame_limit=frame_limit)
    if native.LinuxExecutionAdapter._wait(adapter,run.capture,deadline=deadline,lease=lease,
            cancelled=cancelled,require_eof=False,watchdog=run.watchdog)!=0:
        _error('sandbox_create_failed')
    readback = native.LinuxExecutionAdapter._readback(adapter,envelope,run.document,lease,run.argv,
        deadline=deadline,side=run.capture,cgroup_identity=run.identity,watchdog=run.watchdog)
    lease.append('enforcement_verified',{'readback':readback})
    permit = _guarded_call(context,hooks.admit_start)
    payload = _start_payload(context,permit)
    context.require_current(payload['preceding_journal_sha256'])
    # No owner/source/user callback is made between this durable intent and the
    # one start attempt. An ambiguous acknowledgement is cleaned up, never retried.
    lease.append('start_intent',payload)
    run.attempted, run.started = True,None
    code,_,_ = native.LinuxExecutionAdapter._command(adapter,run.argv+['start',context.job_id],run.host,
        deadline=deadline,lease=lease,side=run.capture,cancelled=cancelled,watchdog=run.watchdog)
    if code!=0:
        _error('sandbox_start_uncertain')
    run.started = True
    lease.append('started',{})
    code,raw,_ = native.LinuxExecutionAdapter._command(adapter,run.argv+['wait',context.job_id],run.host,
        deadline=deadline,lease=lease,side=run.capture,cancelled=cancelled,watchdog=run.watchdog)
    waited = json.loads(raw)
    if (code!=0 or type(waited) is not dict or set(waited)!={'id','exitStatus'}
            or waited['id']!=context.job_id or type(waited['exitStatus']) is not int
            or not 0<=waited['exitStatus']<=255):
        _error('sandbox_wait_uncertain')
    run.waited = waited['exitStatus']


def _native_cleanup(context, run):
    if run.identity is None:
        return
    adapter,envelope,profile,lease = context.adapter,context.envelope,context.profile,context.lease
    context.require_current()
    if run.handle is None:
        run.handle = physical.open_original_cgroup(adapter,envelope,profile,lease,run.identity)
    observation = physical.cleanup_under_lease(adapter,envelope,profile,lease,run.handle,run.capture)
    if type(observation) is not physical.HostTerminationObservation:
        _error('sandbox_retained_native_observation')
    context.require_current()
    run.observation = observation


def _fallback_containment(context, run):
    # The legacy dictionary is deliberately discarded. It is never converted
    # into a native observation, authenticated packet or capacity-release fact.
    if run.identity is not None and run.observation is None:
        try:
            context.require_current()
            native.LinuxExecutionAdapter._cleanup(context.adapter,context.envelope,run.argv,
                run.identity,context.lease,side=run.capture)
        except Exception:
            pass


def _diagnose(context, run):
    if run.capture is None:
        return
    try:
        native.LinuxExecutionAdapter._diagnose(context.adapter,run.create_argv,run.capture,context.lease)
    except Exception as error:
        run.diagnostic_error = _reason(error,'sandbox_retained_diagnostic_unavailable')


def _retain_candidate(context, run):
    if run.execution_error is not None:
        run.reason = run.execution_error
        run.state = {'sandbox_cancelled':'cancelled','sandbox_wall_limit':'timed_out'}.get(run.reason,'uncertain')
        return
    try:
        run.frame = bytes(run.capture.stdout)
        init,decoded = native.decode_frame(run.frame,policy=run.document['trusted_init']['policy'])
        if init['writers_reaped'] is not True or (init['outcome']=='completed' and run.waited!=0):
            _error('sandbox_guest_writers_uncertain')
        run.init,run.logs = init,decoded['logs']
        if init['outcome']=='completed':
            run.outputs = native.LinuxExecutionAdapter._retain_outputs(context.adapter,run.job,context.envelope,decoded)
        else:
            native.LinuxExecutionAdapter._retain_failure_logs(context.adapter,run.job,decoded)
        run.state,run.reason = init['outcome'],init['reason']
    except Exception as error:
        run.outputs = None
        run.state,run.reason = 'failed',_reason(error,'sandbox_retained_invalid_guest_result')


def _finish(context, run):
    if run.observation is None:
        return False
    _retain_candidate(context,run)
    context.require_current()
    record = native.LinuxExecutionAdapter._record(context.adapter,context.envelope,context.profile,run.runtime_sha256,
        state=run.state,reason=run.reason,attempted=run.attempted,started=run.started,
        proof=run.observation.audit_record,outputs=run.outputs,frame=run.frame,init=run.init,
        waited_exit_status=run.waited,logs=run.logs)
    context.lease.finish(record)
    run.terminal = context.journal.terminal_reference(context.lease)
    context.require_current(run.terminal.terminal_head_sha256)
    return True


def _close_and_release(context, run, hooks, issuer):
    from orchestration.experiment_sandbox.retained_admission import PublicationReceipt
    errors = []
    publication = None
    publication_status = 'not_attempted'
    closed = proof_id = release_id = None
    release_status = 'not_attempted'
    if run.outputs is not None and run.state=='completed':
        try:
            receipt = _guarded_call(context,hooks.admit_publication,run.terminal,_sha(run.outputs.manifest_bytes))
            if type(receipt) is not PublicationReceipt:
                _error('sandbox_retained_publication_receipt')
            publication = receipt.document
            if (type(publication) is not dict or set(publication)!={'version','execution_id',
                    'publication_event_id','publication_fence','outputs_manifest_sha256',
                    'terminal_result_sha256','publication_retained','scientific_approval','reservation_released'}
                    or publication.get('version')!='c23-retained-publication-reference-v1'
                    or publication.get('execution_id')!=context.execution_id
                    or publication.get('outputs_manifest_sha256')!=_sha(run.outputs.manifest_bytes)
                    or publication.get('terminal_result_sha256')!=run.terminal.terminal_result_sha256
                    or publication.get('publication_retained') is not True
                    or publication.get('scientific_approval')!='not_independently_verified'
                    or publication.get('reservation_released') is not False
                    or type(publication.get('publication_fence')) is not int or publication['publication_fence']<3):
                _error('sandbox_retained_publication_receipt')
            _uuid(publication['publication_event_id'])
            publication_status = 'acknowledged'
        except Exception as error:
            publication = None
            publication_status = 'denied_or_uncertain'
            errors.append(_reason(error,'sandbox_retained_publication_unavailable'))
    try:
        closed = _guarded_call(context,hooks.close_execution,run.terminal)
        if (type(closed) is not ClosedExecutionBinding or closed.execution_id!=context.execution_id
                or closed.reservation_id!=context.reservation_id or closed.owner_user_id!=context.owner_user_id
                or closed.job_id!=context.job_id or closed.envelope_sha256!=context.envelope_sha256
                or closed.profile_sha256!=context.profile_sha256 or closed.journal_id!=context.journal_id
                or closed.journal_epoch!=run.terminal.epoch or closed.host_boot_id!=context.host_boot_id
                or closed.worker_id!=context.host_id or closed.site_id!=context.site_id
                or closed.execution_request_sha256!=context.execution_identity.document['execution_request_sha256']
                or closed.runtime_sha256!=run.runtime_sha256 or closed.adapter_source_sha256!=context.helper_sha256
                or closed.image_digest!=context.envelope.environment['image_digest']
                or closed.environment_sha256!=context.envelope.metadata['hashes']['environment_sha256']
                or closed.trusted_init_sha256!=context.profile.document['trusted_init']['sha256']
                or any(getattr(closed,name)!=context.envelope.metadata[name] for name in
                       ('experiment_id','proposal_revision_id','approval_id'))):
            _error('sandbox_retained_closed_binding')
        context.require_current(run.terminal.terminal_head_sha256)
        signed = issuer.issue_under_lease(context.execution_id,context.adapter,context.envelope,
            context.profile,context.lease,run.observation)
        context.require_current(run.terminal.terminal_head_sha256)
        proof_id = _uuid(_guarded_call(context,hooks.record_termination,canonical_packet_bytes(signed)))
        release_status = 'uncertain'
        release_id = _uuid(_guarded_call(context,hooks.release_terminated,proof_id,closed.closed_fence))
        release_status = 'acknowledged'
    except Exception as error:
        errors.append(_reason(error,'sandbox_retained_termination_unavailable'))
    return _report(context,run,publication=publication,publication_status=publication_status,
        closed=closed if type(closed) is ClosedExecutionBinding else None,proof_id=proof_id,
        release_id=release_id,release_status=release_status,errors=errors)


def _scope(context, run, hooks, issuer, cancelled):
    snapshot = context.require_current()
    if any(event.host_boot_id!=context.host_boot_id for event in snapshot.events):
        run.state,run.reason = 'uncertain','unsupported_boot_change_capacity_held'
        return _report(context,run,replayed=snapshot.terminal)
    if snapshot.terminal:
        run.state,run.reason = 'uncertain','terminal_reconciliation_required'
        try:
            run.terminal = context.journal.terminal_reference(context.lease)
        except SandboxError:
            pass
        return _report(context,run,replayed=True)
    if snapshot.reconciliation_required:
        creates = [event for event in snapshot.events if event.kind=='create_intent']
        if len(creates)!=1 or creates[0].payload.get('profile_sha256')!=context.profile_sha256:
            run.reason = 'reconciliation_required'
            return _report(context,run)
        identity = creates[0].payload.get('cgroup_identity')
        if type(identity) is not list or len(identity)!=2 or any(type(item) is not int or item<0 for item in identity):
            return _report(context,run)
        run.identity = tuple(identity)
        run.attempted = _retained_start(snapshot,context)
        run.started = None if run.attempted else False
        run.execution_error = 'reconciled_without_reexecution'
    else:
        state_root = context.worker_root/('runsc-state-'+context.job_id)
        if run.outer.exists() or state_root.exists() or state_root.is_symlink():
            run.reason = 'unowned_existing_runtime'
            return _report(context,run)
        try:
            _fresh_execute(context,run,hooks,cancelled)
        except Exception as error:
            run.execution_error = _reason(error)
    try:
        _native_cleanup(context,run)
    except Exception as error:
        run.reason = _reason(error,'sandbox_retained_cleanup_uncertain')
    _diagnose(context,run)
    if run.observation is None:
        run.state = 'uncertain'
        if run.execution_error is not None and run.identity is None:
            run.reason = run.execution_error
        return _report(context,run)
    try:
        _finish(context,run)
    except Exception as error:
        run.state,run.reason = 'uncertain',_reason(error,'sandbox_retained_durable_finish_unavailable')
        return _report(context,run)
    if not _retained_start(context.require_current(),context):
        run.state,run.reason = 'uncertain','retained_start_missing_capacity_held'
        return _report(context,run)
    return _close_and_release(context,run,hooks,issuer)


def run_retained(adapter, execution_identity, envelope, profile, *, hooks, issuer, cancelled=lambda:False):
    """Execute one retained scope; lifecycle/cleanup never borrows a fake lease."""
    from orchestration.experiment_sandbox.retained_admission import RetainedRuntimeHooks
    if (type(adapter) is not native.LinuxExecutionAdapter or type(execution_identity) is not RetainedExecutionIdentity
            or type(envelope) is not VerifiedEnvelope or type(profile) is not PreparedExecutionProfile
            or type(hooks) is not RetainedRuntimeHooks or type(issuer) is not physical.LinuxTerminationIssuer
            or not callable(cancelled)):
        _error()
    # Base preflight precedes every journal mutation. No ordinary-container or
    # host-Python fallback is available, and the caller retains the sealed mount.
    job,document,runtime_sha = native.LinuxExecutionAdapter._preflight(adapter,envelope,profile)
    with _hold_runtime_context(adapter,envelope,profile,execution_identity) as context:
        argv = [str(context.runtime_directory/'runsc'),*profile.runtime_args]
        outer,host,_ = native.LinuxExecutionAdapter._paths(adapter,context.job_id)
        run = _Run(job,document,runtime_sha,argv,outer,host,argv+['create','--bundle='+str(job),context.job_id])
        try:
            return _scope(context,run,hooks,issuer,cancelled)
        finally:
            # Containment is attempted even after an unexpected BaseException.
            # A legacy cleanup result is never promoted to physical evidence.
            _fallback_containment(context,run)
            if run.capture is not None:
                try:
                    run.capture.close()
                except Exception:
                    pass
            if run.watchdog is not None:
                try:
                    run.watchdog.stop(proven=run.observation is not None)
                except Exception:
                    pass
            if run.handle is not None:
                try:
                    run.handle.close()
                except Exception:
                    pass
