"""Host-safe source/permit/fence checks; no native DB or Linux execution."""
from copy import copy
import hashlib
import json
import os
from types import SimpleNamespace
import uuid

import pytest

from orchestration.experiment_sandbox import retained_admission as module
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.execution_store import C23ExecutionStore
from orchestration.experiment_sandbox.retained_admission import FreshStartPermit, RetainedAdmissionSourcePolicy
from schema.context_catalogue import canonical_json
from tests.retained_admission_support import source_policy
from tests.test_experiment_sandbox_execution_store import configuration
from tests.test_experiment_sandbox_retained_context import case as _case, hold
from tests.test_experiment_sandbox_retained_context import approved_envelope as _approved, layout as _layout

case,approved_envelope,layout=_case,_approved,_layout


@pytest.fixture
def policy(case,tmp_path):
    return source_policy(tmp_path/'source',environment=case.envelope.environment,
        runtime=json.loads(case.adapter._runtime_json))


def test_source_policy_hashes_aggregates_individual_adapter_and_live_actual_context(policy,case):
    with hold(case) as context:
        policy.verify_current(context)
        fields=json.loads(policy._binding_json)
        assert fields['worker_id']==context.host_id
        assert fields['profile_policy_sha256']!=policy._profile_files['orchestration/experiment_sandbox/profile_execution.py']
        assert fields['adapter_source_sha256']==context.helper_sha256
        assert fields['source_policy_sha256']==hashlib.sha256(policy._policy_bytes).hexdigest()
    with pytest.raises(SandboxError):
        policy.verify_current(context)


def test_operator_source_policy_requires_actual_loaded_origin_beyond_copied_bytes(policy,case):
    from orchestration.experiment_sandbox import physical_termination as physical
    fields=json.loads(policy._policy_bytes)
    fields['trust_scope']='retained-operator'
    operator=RetainedAdmissionSourcePolicy(policy.source_root,dict(policy._worker_files),
        dict(policy._profile_files),physical._canonical(fields),'retained-operator')
    with hold(case) as context,pytest.raises(SandboxError,match='source_policy'):
        operator.verify_current(context)


def test_operator_loaded_provenance_helper_receives_actual_live_guard(policy,case,monkeypatch):
    from orchestration.experiment_sandbox import physical_termination as physical
    fields=json.loads(policy._policy_bytes)
    fields['trust_scope']='retained-operator'
    operator=RetainedAdmissionSourcePolicy(policy.source_root,dict(policy._worker_files),
        dict(policy._profile_files),physical._canonical(fields),'retained-operator')
    calls=[]
    def observed(root,files,*,check):
        calls.append((root,dict(files),check()))
    monkeypatch.setattr(physical,'require_loaded_source_provenance',observed)
    with hold(case) as context:
        policy.verify_current(context)
        assert not calls  # Copied software trees grant no loaded-module claim.
        operator.verify_current(context)
        assert calls[0][:2]==(policy.source_root,dict(policy._worker_files))
        assert calls[0][2]==context.require_current()


@pytest.mark.parametrize('change',['canonical','unknown','site','trust','worker','profile','adapter','init','missing','relative'])
def test_source_policy_rejects_incomplete_noncanonical_or_mixed_material(policy,change):
    worker,profile=dict(policy._worker_files),dict(policy._profile_files)
    raw,root,scope=policy._policy_bytes,policy.source_root,policy.trust_scope
    fields=json.loads(raw)
    if change=='canonical':
        raw+=b'\n'
    elif change in {'unknown','site','trust','worker','profile','adapter','init'}:
        key={'unknown':'approval','site':'site_id','trust':'trust_scope','worker':'worker_source_sha256',
            'profile':'profile_policy_sha256','adapter':'adapter_source_sha256','init':'trusted_init_sha256'}[change]
        fields[key]='0'*64
        raw=module.json.dumps(fields,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()
    elif change=='missing':
        worker.pop('orchestration/experiment_sandbox/retained_admission.py')
    else:
        root='relative-path'
    with pytest.raises(ValueError):
        RetainedAdmissionSourcePolicy(root,worker,profile,raw,scope)


@pytest.mark.parametrize('change',['bytes','writable','symlink','hardlink','missing','rootmode'])
def test_source_policy_rechecks_real_readonly_tree_not_caller_hash_claims(policy,case,change):
    name='orchestration/experiment_sandbox/retained_admission.py'
    path=policy.source_root/name
    if change=='rootmode':
        policy.source_root.chmod(0o750)
    elif change=='bytes':
        path.chmod(0o600)
        path.write_bytes(path.read_bytes()+b'\n')
        path.chmod(0o400)
    elif change=='writable':
        path.chmod(0o600)
    elif change=='symlink':
        raw=path.read_bytes()
        path.unlink()
        alternate=path.with_suffix('.other')
        alternate.write_bytes(raw)
        alternate.chmod(0o400)
        path.symlink_to(alternate.name)
    elif change=='hardlink':
        os.link(path,path.with_suffix('.linked'))
    else:
        path.unlink()
    with hold(case) as context,pytest.raises((SandboxError,OSError)):
        policy.verify_current(context)


def synthetic_permit(context):
    permit=object.__new__(FreshStartPermit)
    object.__setattr__(permit,'_pid',os.getpid())
    object.__setattr__(permit,'_json',canonical_json({'preceding_journal_sha256':context.require_current().events[-1].sha256}))
    module._PERMITS[id(permit)]=(permit,context)
    return permit


def test_private_permit_cannot_construct_forge_copy_or_cross_context(case):
    with pytest.raises(TypeError):
        FreshStartPermit()
    with hold(case) as context:
        with pytest.raises(SandboxError):
            object.__new__(FreshStartPermit).consume(context)
        permit=synthetic_permit(context)
        with pytest.raises(SandboxError):
            copy(permit).consume(context)
        with pytest.raises(SandboxError):
            permit.consume(object())
        assert permit.consume(context)['preceding_journal_sha256']==context.require_current().events[-1].sha256
        with pytest.raises(SandboxError):
            permit.consume(context)


def test_permit_is_burned_before_changed_head_or_closed_scope_can_retry(case):
    with hold(case) as context:
        permit=synthetic_permit(context)
        context.lease.append('synthetic_test',{})
        with pytest.raises(SandboxError):
            permit.consume(context)
        assert id(permit) not in module._PERMITS
        with pytest.raises(SandboxError):
            permit.consume(context)
        expired=synthetic_permit(context)
    with pytest.raises(SandboxError):
        expired.consume(context)
    assert id(expired) not in module._PERMITS


def event_arguments():
    identity=str(uuid.uuid4())
    return dict(execution_id=str(uuid.uuid4()),expected_fence=1,event_id=identity,
        kind='start_consumed',start_id=identity,host_boot_id=str(uuid.uuid4()),
        journal_id=str(uuid.uuid4()),journal_epoch=1,profile_sha256='a'*64,
        preceding_journal_sha256='b'*64)


def test_event_prepares_strict_immutable_parameters_before_last_fence_then_immediate_sql(monkeypatch):
    store=C23ExecutionStore(config=configuration())
    calls=[]
    monkeypatch.setattr(store,'_controller',lambda session,**kw:calls.append('controller'))
    args=event_arguments()
    session=SimpleNamespace(execute=lambda *a,**k:SimpleNamespace(one=lambda:(uuid.uuid4(),uuid.uuid4(),'c'*64)))
    def scalar(statement,parameters):
        assert calls==['controller','fence']
        payload=json.loads(parameters['p'])
        assert payload['fence']==2 and payload['journal_epoch']==1
        calls.append('sql')
        return args['event_id']
    session.scalar=scalar
    def closing():
        calls.append('fence')
        args['journal_epoch']=999  # Prepared payload cannot follow this mutation.
    assert store.event_after_fence_in_transaction(session,**args,final_fence=closing)==args['event_id']
    assert calls==['controller','fence','sql']


@pytest.mark.parametrize('field,value',[('expected_fence',True),('journal_epoch',True),
    ('event_id','NOT-A-UUID'),('host_boot_id','0'*36),('profile_sha256','A'*64),
    ('kind','caller_approved'),('result_sha256','c'*64),('terminal_sequence',1)])
def test_event_invalid_inputs_never_reach_closing_callback_or_sql(monkeypatch,field,value):
    store=C23ExecutionStore(config=configuration())
    monkeypatch.setattr(store,'_controller',lambda *a,**kw:None)
    args=event_arguments()
    args[field]=value
    def forbidden(*args,**kwargs):
        pytest.fail('Invalid event reached a callback or SQL')
    with pytest.raises(SandboxError):
        store.event_after_fence_in_transaction(SimpleNamespace(execute=forbidden),**args,final_fence=forbidden)


def test_event_closing_exception_retains_no_named_operation(monkeypatch):
    store=C23ExecutionStore(config=configuration())
    monkeypatch.setattr(store,'_controller',lambda *a,**kw:None)
    def closing():
        raise RuntimeError('closing gate rejected')
    session=SimpleNamespace(execute=lambda *a,**k:SimpleNamespace(one=lambda:(uuid.uuid4(),uuid.uuid4(),'c'*64)),
        scalar=lambda *a,**k:pytest.fail('Closing rejection reached SQL'))
    with pytest.raises(RuntimeError,match='closing gate'):
        store.event_after_fence_in_transaction(session,**event_arguments(),final_fence=closing)
