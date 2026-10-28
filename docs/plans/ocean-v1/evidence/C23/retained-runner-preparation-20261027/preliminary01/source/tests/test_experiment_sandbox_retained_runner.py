"""Host-safe retained lifecycle simulations with actual journal/context guards.

All Linux preflight/runsc/cgroup/watchdog/DB admission and physical observations
are explicitly mocked. No generated analysis, real Linux proof, DB, cloud or
retained end-to-end acceptance occurs. Synthetic signatures authenticate only
these software assertions. Private validated byte retention uses actual helpers.
"""
import base64
from dataclasses import FrozenInstanceError
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from orchestration.experiment_sandbox import linux_runtime as native
from orchestration.experiment_sandbox import physical_termination as physical
from orchestration.experiment_sandbox import retained_admission as admission
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.journal import DurableExecutionJournal
from orchestration.experiment_sandbox.proofs import (
    PinnedTerminationIssuer, TerminationVerifierRegistry, canonical_packet_bytes,
    sign_termination_claims, verify_termination_packet,
)
from orchestration.experiment_sandbox.retained_runner import RetainedRunReport, run_retained
from orchestration.experiment_sandbox.retained_context import _hold_runtime_context
from sandbox.experiment.trusted_init import VERSION as INIT_VERSION, encode_frame
from schema.context_catalogue import canonical_json
from schema.experiment_execution import ClosedExecutionBinding, TerminationClaims, TerminationIssuerScope
from tests.test_experiment_sandbox_retained_context import case as _context_case
from tests.test_experiment_sandbox_retained_context import approved_envelope as _approved, layout as _layout
from tests.test_experiment_sandbox_proofs import _claims

case, approved_envelope, layout = _context_case, _approved, _layout
_REAL_RETAIN = native.LinuxExecutionAdapter._retain_outputs
_REAL_REPLAY = native.LinuxExecutionAdapter._replay_outputs
_REAL_CONSUME = admission.FreshStartPermit.consume
_PRIVATE = 'PRIVATE-RAW-GUEST-CONTENT'


def _hash(raw):
    return hashlib.sha256(raw.encode() if type(raw) is str else raw).hexdigest()


@pytest.fixture
def lifecycle(case, monkeypatch):
    f = SimpleNamespace(**vars(case),calls=[],capture=None,watchdog=None,handle=None,observation=None,
        preflight_error=False,create_error=False,start_error=None,wait_error=None,native_error=False,
        output_error=False,diagnostic_error=False,publication_error=False,publication_extra=False,
        close_error=False,issue_error=False,record_error=False,release_error=False,
        malformed=False,outcome='completed',writers_reaped=True,waited=0,
        key=Ed25519PrivateKey.generate(),packet=None,closed=None,permit=None,start_count=0,
        hooks=object.__new__(admission.RetainedRuntimeHooks),
        issuer=object.__new__(physical.LinuxTerminationIssuer),context=None)

    def current():
        return case.journal.require_current(case.journal._leases[case.envelope.job_id])

    def preflight(adapter,envelope,profile):
        f.calls.append('preflight')
        assert adapter is f.adapter and envelope is f.envelope and profile is f.profile
        if f.preflight_error:
            raise SandboxError('sandbox_rootfs_not_sealed')
        return adapter.worker_root/envelope.job_id,profile.document,_hash(adapter._runtime_json)

    def prepare(adapter,job,requirements):
        current()
        f.calls.append('prepare_cgroup')
        outer,host,sandbox = adapter._paths(job)
        outer.mkdir(parents=True,mode=0o700)
        host.mkdir(mode=0o700)
        sandbox.mkdir(mode=0o700)
        return outer.stat().st_dev,outer.stat().st_ino

    def open_handle(adapter,envelope,profile,lease,identity):
        current()
        f.calls.append('open_original')
        creates = [e for e in lease.snapshot().events if e.kind=='create_intent']
        assert len(creates)==1 and creates[0].payload['cgroup_identity']==list(identity)
        value = object.__new__(physical.OriginalCgroupHandle)
        object.__setattr__(value,'_closed',False)
        f.handle = value
        return value

    def close_handle(handle):
        assert handle is f.handle
        f.calls.append('close_handle')
        object.__setattr__(handle,'_closed',True)

    class Watchdog:
        pid = 123456

        def stop(self,*,proven):
            current()
            self.proven = proven
            f.calls.append('watchdog_stop')

    def watchdog(_outer,_deadline):
        current()
        f.calls.append('watchdog_arm')
        f.watchdog = Watchdog()
        return f.watchdog

    def frame():
        raw = canonical_json({'columns':['value'],'rows':[[_PRIVATE]]}).encode()
        document = {'version':INIT_VERSION,'job_id':f.envelope.job_id,
            'envelope_sha256':f.envelope.envelope_sha256,'outcome':f.outcome,
            'reason':'completed' if f.outcome=='completed' else 'analysis_failed',
            'analysis_exit_code':0 if f.outcome=='completed' else 1,'writers_reaped':f.writers_reaped,
            'files':{'summary.json':base64.b64encode(raw).decode()} if f.outcome=='completed' else {},
            'logs':{'stdout':base64.b64encode(b'private guest log').decode(),'stderr':''}}
        raw = encode_frame(document,max_output_bytes=f.envelope.resources['max_output_bytes'])
        return raw+b'invalid trailing bytes' if f.malformed else raw

    class Capture:
        def __init__(self):
            self.stdout,self.stderr = bytearray(frame()),bytearray()
            self.eof,self.closed = True,False

        def close(self):
            self.closed = True
            f.calls.append('capture_close')

    def spawn(_adapter,argv,_host,**_kwargs):
        current()
        assert argv[-3]=='create'
        f.calls.append('create')
        f.capture = Capture()
        return f.capture

    def wait_create(_adapter,_capture,**_kwargs):
        current()
        f.calls.append('create_ack')
        if f.create_error:
            raise SandboxError('sandbox_create_failed')
        return 0

    def readback(_adapter,*_args,**_kwargs):
        current()
        f.calls.append('readback')
        return {'software_fixture_only':True}

    def command(_adapter,argv,_host,**_kwargs):
        snapshot = current()
        command = argv[-2]
        if command=='start':
            f.calls.append('start')
            f.start_count += 1
            assert snapshot.events[-1].kind=='start_intent'
            assert f.calls[-2]=='consume'
            if f.start_error=='interrupt':
                raise KeyboardInterrupt
            if f.start_error is not None:
                raise SandboxError(f.start_error)
            return 0,b'',b''
        assert command=='wait'
        f.calls.append('wait')
        if f.wait_error is not None:
            raise SandboxError(f.wait_error)
        return 0,canonical_json({'id':f.envelope.job_id,'exitStatus':f.waited}).encode(),b''

    def cleanup(_adapter,_envelope,_profile,lease,handle,_capture=None):
        current()
        assert handle is f.handle and handle._closed is False
        f.calls.append('native_cleanup')
        if f.native_error:
            raise SandboxError('sandbox_physical_delete_uncertain')
        cleanup = lease.append('cleanup_intent',{'software_fixture_only':True})
        raw = canonical_json({'software_fixture_only':True,'native_DELETE_ACK_simulated':True}).encode()
        terminated = lease.append('termination_verified',{'native_observation_sha256':_hash(raw)})
        value = object.__new__(physical.HostTerminationObservation)
        values = {'_handle':handle,'_native_bytes':raw,'_native_path':Path('/NOT-NATIVE-EVIDENCE'),
            '_cleanup_event':cleanup,'_termination_event':terminated,'_token':object(),
            'native_observation_sha256':_hash(raw),'cleanup_intent_sequence':cleanup.sequence,
            'cleanup_intent_sha256':cleanup.sha256,'termination_sequence':terminated.sequence,
            'termination_sha256':terminated.sha256}
        for name,item in values.items():
            object.__setattr__(value,name,item)
        f.observation = value
        return value

    def fallback(_adapter,*_args,**_kwargs):
        current()
        f.calls.append('fallback_containment')
        return {'runtime_delete_acknowledged':True,'populated':0,'caller_json_not_a_proof':True}

    def diagnose(_adapter,*_args):
        current()
        f.calls.append('diagnose')
        if f.diagnostic_error:
            raise OSError('private diagnostic path detail must not be exposed')

    def retain(adapter,*args):
        assert f.observation is not None, 'decode/retention preceded independent physical cleanup'
        f.calls.append('retain_candidate')
        if f.output_error:
            raise SandboxError('sandbox_retention_integrity')
        return _REAL_RETAIN(adapter,*args)

    def preparation(_hooks,context):
        f.context = context
        f.calls.append('preparation')
        context.require_current()

    def admit_start(_hooks,context):
        f.calls.append('admit_start')
        snapshot = context.require_current()
        assert snapshot.events[-1].kind=='enforcement_verified'
        f.permit = make_permit(context)
        return f.permit

    def make_permit(context):
        snapshot = context.require_current()
        start_id = str(uuid.uuid4())
        payload = {'version':physical.START_INTENT_VERSION,'execution_id':context.execution_id,
            'reservation_id':context.reservation_id,'start_id':start_id,'start_event_id':start_id,
            'start_fence':2,'journal_id':context.journal_id,'journal_epoch':snapshot.epoch,
            'worker_id':context.host_id,'host_boot_id':context.host_boot_id,'job_id':context.job_id,
            'envelope_sha256':context.envelope_sha256,'profile_sha256':context.profile_sha256,
            'preceding_journal_sha256':snapshot.events[-1].sha256}
        value = object.__new__(admission.FreshStartPermit)
        object.__setattr__(value,'_pid',os.getpid())
        object.__setattr__(value,'_json',canonical_json(payload))
        with admission._LOCK:
            admission._PERMITS[id(value)] = (value,context)
        return value

    def consume(permit,context):
        f.calls.append('consume')
        return _REAL_CONSUME(permit,context)

    def publication(_hooks,context,terminal,digest):
        f.calls.append('publication')
        snapshot = context.require_current()
        assert snapshot.terminal and snapshot.events[-1].kind=='finished'
        assert f.handle._closed is False
        outputs = _REAL_REPLAY(context.adapter,context.worker_root/context.job_id,context.envelope,snapshot.result['record'])
        assert _hash(outputs.manifest_bytes)==digest
        if f.publication_error:
            raise SandboxError('sandbox_owner_revoked')
        value = object.__new__(admission.PublicationReceipt)
        doc = {'version':'c23-retained-publication-reference-v1','execution_id':context.execution_id,
            'publication_event_id':str(uuid.uuid4()),'publication_fence':3,'outputs_manifest_sha256':digest,
            'terminal_result_sha256':terminal.terminal_result_sha256,'publication_retained':True,
            'scientific_approval':'not_independently_verified','reservation_released':False}
        if f.publication_extra:
            doc['private_outputs'] = _PRIVATE
        object.__setattr__(value,'_json',canonical_json(doc))
        return value

    def close(_hooks,context,terminal):
        f.calls.append('close')
        assert context.require_current().terminal and f.handle._closed is False
        if f.close_error:
            raise SandboxError('sandbox_retained_close_binding')
        data = _claims().binding.model_dump()
        metadata = context.envelope.metadata
        data.update({name:metadata[name] for name in ('site_id','reservation_id','owner_user_id',
            'experiment_id','proposal_revision_id','approval_id')})
        data.update(execution_id=context.execution_id,execution_request_sha256=f.identity.document['execution_request_sha256'],
            envelope_sha256=context.envelope_sha256,job_id=context.job_id,worker_id=context.host_id,
            host_boot_id=context.host_boot_id,journal_id=context.journal_id,journal_epoch=terminal.epoch,
            profile_sha256=context.profile_sha256,closed_fence=4,environment_sha256=metadata['hashes']['environment_sha256'],
            image_digest=context.envelope.environment['image_digest'],runtime_sha256=_hash(context.runtime_json),
            trusted_init_sha256=context.profile.document['trusted_init']['sha256'],adapter_source_sha256=context.helper_sha256)
        f.closed = ClosedExecutionBinding.model_validate(data)
        return f.closed

    def issue(_issuer,execution_id,adapter,envelope,profile,lease,observation):
        f.calls.append('issuer')
        assert lease.require_current().terminal and f.handle._closed is False and observation is f.observation
        assert execution_id==f.closed.execution_id
        if f.issue_error:
            raise SandboxError('sandbox_physical_issuer_unavailable')
        terminal = adapter.journal.terminal_reference(lease)
        creates = [e for e in lease.snapshot().events if e.kind=='create_intent']
        kernel = _claims().kernel.model_dump()
        kernel.update(cgroup_path='/ocean-c23/'+envelope.job_id,delete_job_id=envelope.job_id,
            delete_runtime_sha256=f.closed.runtime_sha256,delete_host_boot_id=f.closed.host_boot_id,
            terminal_recorded_monotonic_ns=terminal.terminal_recorded_monotonic_ns,
            issued_monotonic_ns=terminal.terminal_recorded_monotonic_ns+1,
            raw_observation_sha256=observation.native_observation_sha256)
        journal = {'create_intent_sequence':creates[0].sequence,'create_intent_sha256':creates[0].sha256,
            'cleanup_intent_sequence':observation.cleanup_intent_sequence,'cleanup_intent_sha256':observation.cleanup_intent_sha256,
            'termination_sequence':observation.termination_sequence,'termination_sha256':observation.termination_sha256,
            'terminal_sequence':terminal.terminal_sequence,'terminal_head_sha256':terminal.terminal_head_sha256,
            'terminal_result_sha256':terminal.terminal_result_sha256}
        claims = TerminationClaims.model_validate({'binding':f.closed,'kernel':kernel,'journal':journal})
        signed = sign_termination_claims(claims,issuer_id='synthetic-runner-test',key_id='ephemeral',
            trust_scope='synthetic-software-test',private_key=f.key)
        f.packet = canonical_packet_bytes(signed)
        scope = TerminationIssuerScope.model_validate({n:getattr(f.closed,n) for n in TerminationIssuerScope.model_fields})
        f.registry = TerminationVerifierRegistry(issuers=[PinnedTerminationIssuer(issuer_id='synthetic-runner-test',
            key_id='ephemeral',trust_scope='synthetic-software-test',public_key=f.key.public_key().public_bytes_raw(),scope=scope)],
            trust_scope='synthetic-software-test',enabled=True)
        return signed

    def record(_hooks,context,raw):
        f.calls.append('record')
        assert context.require_current().terminal and raw==f.packet and f.handle._closed is False
        if f.record_error:
            raise SandboxError('sandbox_termination_signature')
        verify_termination_packet(raw,expected=f.closed,registry=f.registry)
        return str(uuid.uuid4())

    def release(_hooks,context,proof_id,closed_fence):
        f.calls.append('release')
        assert context.require_current().terminal and closed_fence==f.closed.closed_fence
        uuid.UUID(proof_id)
        if f.release_error:
            raise SandboxError('sandbox_execution_release_uncertain')
        return str(uuid.uuid4())

    for name,value in {'_preflight':preflight,'_prepare_cgroups':prepare,'_spawn':spawn,'_wait':wait_create,
        '_readback':readback,'_command':command,'_cleanup':fallback,'_diagnose':diagnose,'_retain_outputs':retain}.items():
        monkeypatch.setattr(native.LinuxExecutionAdapter,name,value)
    monkeypatch.setattr(native,'_arm_watchdog',watchdog)
    monkeypatch.setattr(physical,'open_original_cgroup',open_handle)
    monkeypatch.setattr(physical.OriginalCgroupHandle,'close',close_handle)
    monkeypatch.setattr(physical,'cleanup_under_lease',cleanup)
    for name,value in {'admit_preparation':preparation,'admit_start':admit_start,'admit_publication':publication,
        'close_execution':close,'record_termination':record,'release_terminated':release}.items():
        monkeypatch.setattr(admission.RetainedRuntimeHooks,name,value)
    monkeypatch.setattr(admission.FreshStartPermit,'consume',consume)
    monkeypatch.setattr(physical.LinuxTerminationIssuer,'issue_under_lease',issue)
    f.make_permit = make_permit
    yield f
    with admission._LOCK:
        for key,record in list(admission._PERMITS.items()):
            if record[1] is f.context:
                del admission._PERMITS[key]


def run(f,**changes):
    args = dict(hooks=f.hooks,issuer=f.issuer)
    args.update(changes)
    return run_retained(f.adapter,f.identity,f.envelope,f.profile,**args)


def snapshot(f):
    return f.journal.read(f.envelope.job_id,f.envelope.envelope_sha256)


def test_normal_flow_finishes_before_publication_and_releases_without_exposing_bytes(lifecycle):
    f = lifecycle
    report = run(f)
    doc = report.document
    assert type(report) is RetainedRunReport
    assert doc['state']=='completed' and doc['capacity_release_status']=='acknowledged'
    assert doc['reservation_released'] is True
    assert doc['publication_reference']['publication_retained'] is True
    assert _PRIVATE not in canonical_json(doc) and 'private guest log' not in canonical_json(doc)
    assert not hasattr(report,'outputs')
    assert f.calls.index('native_cleanup')<f.calls.index('retain_candidate')<f.calls.index('publication')
    assert f.calls.index('publication')<f.calls.index('close')<f.calls.index('issuer')<f.calls.index('record')<f.calls.index('release')
    assert f.calls.index('release')<f.calls.index('close_handle') and f.watchdog.proven is True
    assert f.capture.closed and f.handle._closed and f.start_count==1
    record = snapshot(f).result['record']
    assert record['version']==native.VERSION and record['state']=='completed'
    for forbidden in ('packet','closed_fence','publication_reference','termination_proof_id','release_id'):
        assert forbidden not in record
    assert snapshot(f).events[-1].kind=='finished'
    doc['state']='caller-mutated'
    assert report.state=='completed'
    with pytest.raises(TypeError):
        RetainedRunReport()
    with pytest.raises(FrozenInstanceError):
        report._json='{}'


def test_preflight_precedes_claim_and_missing_mount_does_not_create_history(lifecycle):
    lifecycle.preflight_error=True
    with pytest.raises(SandboxError,match='rootfs_not_sealed'):
        run(lifecycle)
    assert snapshot(lifecycle) is None and lifecycle.calls==['preflight']


@pytest.mark.parametrize('field',['hooks','issuer'])
def test_boolean_or_duck_authority_is_refused_before_preflight(lifecycle,field):
    with pytest.raises(SandboxError,match='runner_binding'):
        run(lifecycle,**{field:lambda:True})
    assert lifecycle.calls==[] and snapshot(lifecycle) is None


def test_consumed_permit_is_one_use_and_terminal_replay_has_zero_runtime_commands(lifecycle):
    f = lifecycle
    first = run(f)
    assert first.document['reservation_released'] is True
    with pytest.raises(SandboxError,match='start_permit'):
        f.permit.consume(f.context)
    events = snapshot(f).events
    before = len(f.calls)
    second = run(f)
    assert f.calls[before:]==['preflight']
    assert f.start_count==1 and second.document['replayed'] is True
    assert second.document['reason']=='terminal_reconciliation_required'
    assert second.document['publication_reference'] is None
    assert snapshot(f).events==events


@pytest.mark.parametrize('flag',['publication_error','publication_extra'])
def test_publication_denial_or_invalid_reference_cannot_prevent_close_release(lifecycle,flag):
    f=lifecycle
    setattr(f,flag,True)
    doc=run(f).document
    assert snapshot(f).terminal and doc['publication_reference'] is None
    assert doc['capacity_release_status']=='acknowledged' and doc['reservation_released'] is True
    assert f.calls.index('publication')<f.calls.index('close')<f.calls.index('release')
    assert _PRIVATE not in canonical_json(doc)


@pytest.mark.parametrize('flag',['malformed','output_error','diagnostic_error'])
def test_guest_or_diagnostic_failure_does_not_erase_native_cleanup_or_durable_finish(lifecycle,flag):
    f=lifecycle
    setattr(f,flag,True)
    doc=run(f).document
    assert snapshot(f).terminal and doc['native_cleanup_recorded'] is True
    assert doc['reservation_released'] is True
    if flag!='diagnostic_error':
        assert doc['state']=='failed' and doc['publication_reference'] is None
    else:
        assert doc['diagnostic_error']=='sandbox_retained_diagnostic_unavailable'


def test_failed_analysis_is_closed_and_released_without_successful_publication(lifecycle):
    f=lifecycle
    f.outcome='failed'
    doc=run(f).document
    assert doc['state']=='failed' and doc['analysis_exit_code']==1
    assert doc['publication_reference'] is None and doc['reservation_released'] is True
    assert 'publication' not in f.calls


@pytest.mark.parametrize('reason',['sandbox_cancelled','sandbox_wall_limit','sandbox_wait_uncertain'])
def test_wait_error_cleanup_finish_and_release_are_independent_of_result_success(lifecycle,reason):
    f=lifecycle
    f.wait_error=reason
    doc=run(f).document
    assert snapshot(f).terminal and doc['reservation_released'] is True
    assert doc['publication_reference'] is None and f.start_count==1
    assert f.calls.index('wait')<f.calls.index('native_cleanup')<f.calls.index('close')


def test_start_ack_loss_is_never_reexecuted_but_proven_cleanup_can_release(lifecycle):
    f=lifecycle
    f.start_error='sandbox_start_uncertain'
    doc=run(f).document
    assert doc['execution_started'] is None and doc['start_attempted'] is True
    assert doc['reservation_released'] is True and f.start_count==1
    assert 'wait' not in f.calls and doc['publication_reference'] is None


def test_native_observation_failure_never_promotes_legacy_cleanup_json(lifecycle):
    f=lifecycle
    f.native_error=True
    doc=run(f).document
    assert not snapshot(f).terminal
    assert doc['native_cleanup_recorded'] is False and doc['reservation_released'] is False
    assert 'fallback_containment' in f.calls
    assert not any(name in f.calls for name in ('publication','close','issuer','record','release'))
    assert f.watchdog.proven is False


def test_cancel_before_effect_does_not_invent_start_or_release(lifecycle):
    f=lifecycle
    doc=run(f,cancelled=lambda:True).document
    assert doc['state']=='uncertain' and doc['reservation_released'] is False
    assert f.start_count==0 and not snapshot(f).terminal
    assert not any(name in f.calls for name in ('prepare_cgroup','create','native_cleanup','close','issuer'))


@pytest.mark.parametrize('flag,missing',[('close_error','issuer'),('issue_error','record'),('record_error','release')])
def test_independent_postfinish_failure_keeps_terminal_history_and_capacity_uncertain(lifecycle,flag,missing):
    f=lifecycle
    setattr(f,flag,True)
    doc=run(f).document
    assert snapshot(f).terminal and doc['native_cleanup_recorded'] is True
    assert doc['reservation_released'] is False and missing not in f.calls
    assert f.handle._closed and f.watchdog.proven is True


def test_release_ack_loss_is_reported_unknown_instead_of_false_or_reexecuted(lifecycle):
    f=lifecycle
    f.release_error=True
    doc=run(f).document
    assert doc['capacity_release_status']=='uncertain' and doc['reservation_released'] is None
    assert snapshot(f).terminal and f.start_count==1


def test_durable_finish_failure_retains_capacity_even_after_native_cleanup(lifecycle,monkeypatch):
    f=lifecycle

    def fail_finish(*_args):
        raise SandboxError('sandbox_journal_busy')

    monkeypatch.setattr(DurableExecutionJournal,'finish',fail_finish)
    doc=run(f).document
    assert not snapshot(f).terminal and doc['reservation_released'] is False
    assert doc['native_cleanup_recorded'] is True and 'close' not in f.calls


def test_unexpected_base_exception_still_attempts_containment_and_keeps_capacity(lifecycle):
    f=lifecycle
    f.start_error='interrupt'
    with pytest.raises(KeyboardInterrupt):
        run(f)
    assert 'fallback_containment' in f.calls and f.watchdog.proven is False
    assert 'close' not in f.calls and f.handle._closed



def test_start_denial_after_create_still_cleans_and_finishes_but_retains_capacity(lifecycle,monkeypatch):
    f=lifecycle

    def deny(_hooks,context):
        context.require_current()
        f.calls.append('start_denied')
        raise SandboxError('sandbox_owner_revoked')

    monkeypatch.setattr(admission.RetainedRuntimeHooks,'admit_start',deny)
    doc=run(f).document
    assert snapshot(f).terminal and doc['native_cleanup_recorded'] is True
    assert doc['reason']=='retained_start_missing_capacity_held'
    assert doc['reservation_released'] is False and f.start_count==0
    assert f.calls.index('start_denied')<f.calls.index('native_cleanup')
    assert not any(name in f.calls for name in ('close','issuer','record','release'))
    assert not any(event.kind=='start_intent' for event in snapshot(f).events)


def test_create_failure_with_known_group_is_cleaned_without_fictitious_start(lifecycle):
    f=lifecycle
    f.create_error=True
    doc=run(f).document
    assert snapshot(f).terminal and doc['native_cleanup_recorded'] is True
    assert doc['start_attempted'] is False and doc['reservation_released'] is False
    assert f.start_count==0 and 'close' not in f.calls


def seed_interrupted(f,*,retained_start):
    with _hold_runtime_context(f.adapter,f.envelope,f.profile,f.identity) as context:
        f.context=context
        identity=native.LinuxExecutionAdapter._prepare_cgroups(f.adapter,context.job_id,f.profile.requirements)
        context.lease.append('create_intent',{'profile_sha256':context.profile_sha256,'cgroup_identity':list(identity)})
        if retained_start:
            context.lease.append('enforcement_verified',{'software_fixture_only':True})
            permit=f.make_permit(context)
            context.lease.append('start_intent',_REAL_CONSUME(permit,context))


@pytest.mark.parametrize('retained_start',[True,False])
def test_nonterminal_reconciliation_never_restarts_and_only_bound_start_can_close(lifecycle,retained_start):
    f=lifecycle
    seed_interrupted(f,retained_start=retained_start)
    f.calls.clear()
    doc=run(f).document
    assert snapshot(f).terminal and doc['native_cleanup_recorded'] is True
    assert f.start_count==0 and not any(name in f.calls for name in ('preparation','admit_start','create','start','wait'))
    assert doc['publication_reference'] is None
    assert snapshot(f).epoch==2
    if retained_start:
        assert doc['reservation_released'] is True and doc['start_attempted'] is True
        assert f.calls.index('native_cleanup')<f.calls.index('close')<f.calls.index('issuer')
    else:
        assert doc['reservation_released'] is False and doc['start_attempted'] is False
        assert doc['reason']=='retained_start_missing_capacity_held' and 'close' not in f.calls


def test_missing_original_create_identity_retains_capacity_without_runtime_commands(lifecycle):
    f=lifecycle
    with _hold_runtime_context(f.adapter,f.envelope,f.profile,f.identity) as context:
        context.lease.append('cgroup_intent',{'path':'/ocean-c23/'+context.job_id})
    f.calls.clear()
    doc=run(f).document
    assert doc['state']=='uncertain' and doc['reservation_released'] is False
    assert not snapshot(f).terminal and f.calls==['preflight']


def test_changed_boot_retains_capacity_and_never_reconstructs_start_or_cleanup(lifecycle):
    f=lifecycle
    seed_interrupted(f,retained_start=True)
    f.calls.clear()
    with DurableExecutionJournal(f.root,host_id=f.journal.host_id,
            host_boot_id='22222222-2222-4222-8222-222222222222') as rebooted:
        original=f.adapter.journal
        try:
            f.adapter.journal=rebooted
            doc=run(f).document
        finally:
            f.adapter.journal=original
    assert doc['reason']=='unsupported_boot_change_capacity_held'
    assert doc['reservation_released'] is False and f.start_count==0
    assert f.calls==['preflight']
