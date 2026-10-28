"""Explicit software-only admission fixtures; no generated code or Linux effects."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from orchestration.experiment_sandbox import physical_termination as physical
from orchestration.experiment_sandbox.contracts import verify_execution_envelope
from orchestration.experiment_sandbox.execution_store import C23ExecutionStore
from orchestration.experiment_sandbox.journal import DurableExecutionJournal
from orchestration.experiment_sandbox.linux_runtime import LinuxExecutionAdapter
from orchestration.experiment_sandbox.profile import rootfs_inventory_sha256
from orchestration.experiment_sandbox.profile_execution import render_execution_profile
from orchestration.experiment_sandbox.proofs import PinnedTerminationIssuer, TerminationVerifierRegistry
from orchestration.experiment_sandbox.retained_admission import RetainedAdmissionSourcePolicy, RetainedRuntimeHooks
from orchestration.experiment_sandbox.retained_bridge import C23RetainedBridge, RetainedMaterialPolicy
from orchestration.experiment_sandbox.retained_context import _hold_runtime_context
from schema.experiment_execution import TerminationIssuerScope
from schema.research_experiments import content_sha256
from tests.test_experiment_sandbox_profile import _layout
from tests.test_experiment_sandbox_retained_context import BOOT, HOST

ROOT=Path(__file__).resolve().parents[1]


def runtime_preparation():
    def digest(label):
        return hashlib.sha256(label.encode()).hexdigest()
    return {'version':'c23-runtime-preparation-v1','evidence_class':'configuration-only',
        'release':'release-20000101.0','architecture':'arm64','files':{
            'runsc':digest('synthetic runsc'),'containerd-shim-runsc-v1':digest('synthetic shim'),
            'gvisor-bin/synthetic-sidecar':digest('synthetic sidecar')},
        'input_host_uid':os.geteuid(),'input_host_gid':os.getegid()}


def source_policy(directory, *, environment, runtime, worker_id=HOST):
    directory.mkdir(mode=0o700)
    worker={}
    for name in sorted(physical.WORKER_FILES|{'orchestration/experiment_sandbox/retained_admission.py'}):
        raw=(ROOT/name).read_bytes()
        destination=directory/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(raw)
        destination.chmod(0o400)
        worker[name]=hashlib.sha256(raw).hexdigest()
    profile={name:worker[name] for name in physical.PROFILE_FILES}
    _,worker_hash=physical._manifest(worker,required=set(worker),version=physical.WORKER_POLICY_VERSION)
    _,profile_hash=physical._manifest(profile,required=set(profile),version=physical.PROFILE_POLICY_VERSION)
    fields={'worker_id':worker_id,'worker_source_sha256':worker_hash,
        'environment_sha256':content_sha256(environment),'image_digest':environment['image_digest'],
        'runtime_sha256':content_sha256(runtime),'profile_policy_sha256':profile_hash,
        'trusted_init_sha256':profile['sandbox/experiment/trusted_init.py'],
        'adapter_source_sha256':worker['orchestration/experiment_sandbox/linux_runtime.py']}
    raw=physical._canonical({'version':physical.SOURCE_POLICY_VERSION,
        'trust_scope':'synthetic-software-test',**fields})
    return RetainedAdmissionSourcePolicy(directory,worker,profile,raw,'synthetic-software-test')


def configured_native(retained,directory,monkeypatch):
    """Real approved C22/reservation/PG roles + inert profile/journal fixture."""
    native=retained
    runtime=runtime_preparation()
    policy=source_policy(directory/'protected-source',environment=native.fixture.environment.model_dump(mode='json'),
        runtime=runtime)
    scope=TerminationIssuerScope.model_validate({'site_id':native.fixture.service.site_id,
        **json.loads(policy._binding_json)})
    key=Ed25519PrivateKey.generate()
    issuer=PinnedTerminationIssuer(issuer_id='synthetic-admission',key_id='ephemeral-admission',
        trust_scope='synthetic-software-test',public_key=key.public_key().public_bytes_raw(),scope=scope)
    registry=TerminationVerifierRegistry(issuers=[issuer],trust_scope='synthetic-software-test',enabled=True)
    config=replace(native.bridge.store.config,verifier_registry=registry)
    store=C23ExecutionStore(config=config)
    material=RetainedMaterialPolicy(site_id=config.site_id,**json.loads(policy._binding_json))
    bridge=C23RetainedBridge(inspection=native.bridge.inspection,store=store,material_policy=material,enabled=lambda:True)
    request=native.approved()
    identity=bridge.reserve(request,current_owner=native.fixture.user)
    address={name:value for name,value in request.items() if name!='idempotency_key'}
    candidate=bridge.inspection.inspect_approved(address,current_owner=native.fixture.user)
    with config.controller_session_factory() as session:
        from sqlalchemy import text
        metadata=json.loads(session.scalar(text('SELECT envelope_json FROM research_experiment_execution')))
    envelope=verify_execution_envelope({'metadata':metadata,'files':dict(candidate.files)},
        expected_envelope_sha256=identity.document['envelope_sha256'],
        environments={native.fixture.environment.identity_sha256:native.fixture.environment.model_dump(mode='json')})
    worker=directory/'inert-worker'
    worker.mkdir(mode=0o700)
    envelope,job,image,actual_runtime=_layout(worker,envelope)
    assert runtime==actual_runtime
    wrapper=job/'rootfs/opt/c23/trusted_init.py'
    wrapper.parent.mkdir(parents=True)
    wrapper.write_bytes((ROOT/'sandbox/experiment/trusted_init.py').read_bytes())
    wrapper.chmod(0o444)
    image['rootfs_inventory_sha256']=rootfs_inventory_sha256(job/'rootfs')
    profile=render_execution_profile(envelope,job_root=job,image_receipt=image,runtime_manifest=runtime,
        control_host_uid=os.geteuid()+1,control_host_gid=os.getegid()+1,
        trusted_init_sha256=scope.trusted_init_sha256)
    journal_root=directory/'actual-private-journal'
    journal_root.mkdir(mode=0o700)
    journal=DurableExecutionJournal(journal_root,host_id=HOST,host_boot_id=BOOT)
    adapter=LinuxExecutionAdapter(worker,directory/'NOT-A-RUNTIME',runtime,journal,
        cgroup_root=directory/'NOT-A-KERNEL-CGROUP')
    def forbidden(*args,**kwargs):
        raise AssertionError('Software admission tests must not perform Linux effects')
    monkeypatch.setattr(LinuxExecutionAdapter,'_preflight',forbidden)
    monkeypatch.setattr(LinuxExecutionAdapter,'_spawn',forbidden)
    hooks=RetainedRuntimeHooks(bridge,native.fixture.user,policy)
    return SimpleNamespace(native=native,bridge=bridge,store=store,policy=policy,hooks=hooks,
        adapter=adapter,journal=journal,envelope=envelope,profile=profile,identity=identity,
        key=key,scope=scope,request=request,job=job,
        hold=lambda:_hold_runtime_context(adapter,envelope,profile,identity))


def retain_terminal(case,context,*,completed=True):
    """Retain fixed literal fixture bytes, never execute approved Python."""
    context.lease.append('create_intent',{'synthetic_software_only':True})
    context.lease.append('cleanup_intent',{'synthetic_software_only':True})
    context.lease.append('termination_observed',{'synthetic_software_only':True})
    outputs=None
    if completed:
        expected=context.envelope.proposal['expected_outputs']
        assert len(expected)==1 and expected[0]['name']=='summary.json'
        outputs=context.adapter._retain_outputs(case.job,context.envelope,{
            'files':{'summary.json':b'{"columns":["value"],"rows":[[42]]}'},
            'logs':{'stdout':b'literal synthetic fixture','stderr':b''}})
    record=context.adapter._record(context.envelope,context.profile,content_sha256(json.loads(context.runtime_json)),
        state='completed' if completed else 'failed',reason='synthetic_software_only',
        attempted=True,started=True,outputs=outputs,init={'analysis_exit_code':0 if completed else 1},
        waited_exit_status=0 if completed else 1)
    context.lease.finish(record)
    return context.journal.terminal_reference(context.lease),outputs
