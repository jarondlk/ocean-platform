"""Actual job-lock context tests; no runtime, physical proof or reserve occurs.

The private identity below is explicitly a detached synthetic software fixture,
not an acknowledged DB reservation. Typed identity alone grants no admission.
No Linux preflight, runsc process, kernel cgroup or generated analysis runs.
"""
from copy import copy
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
import select
import sqlite3
import threading
from types import MappingProxyType, SimpleNamespace
import uuid
import warnings

import pytest

from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.journal import DurableExecutionJournal, DurableLease, _safe_sqlite_version
from orchestration.experiment_sandbox.linux_runtime import LinuxExecutionAdapter
from orchestration.experiment_sandbox.profile_execution import render_execution_profile
from orchestration.experiment_sandbox.retained_bridge import RetainedExecutionIdentity
from orchestration.experiment_sandbox import retained_context as module
from orchestration.experiment_sandbox.retained_context import HeldRuntimeContext, _hold_runtime_context
from schema.context_catalogue import canonical_json
from tests.test_experiment_sandbox_contracts import approved_envelope as _approved
from tests.test_experiment_sandbox_profile_execution import layout as _layout

approved_envelope, layout = _approved, _layout
BOOT = '11111111-1111-4111-8111-111111111111'
HOST = 'f'*64


def synthetic_identity(envelope, **changes):
    metadata = envelope.metadata
    document = {'version':'c23-retained-reserve-identity-v1','execution_id':str(uuid.uuid4()),
        **{name:metadata[name] for name in ('reservation_id','site_id','owner_user_id','experiment_id',
            'proposal_revision_id','approval_id')},'envelope_sha256':envelope.envelope_sha256,
        'execution_request_sha256':hashlib.sha256(b'synthetic uncommitted identity fixture').hexdigest(),
        'job_id':envelope.job_id,'capacity_reserved_at_commit':True,'capacity_snapshot_only':True,
        'execution_authorized':False,'publication_authorized':False,'reservation_release_authorized':False,
        'scientific_approval':'not_independently_verified',**changes}
    value = object.__new__(RetainedExecutionIdentity)
    object.__setattr__(value,'_json',canonical_json(document))
    return value


@pytest.fixture
def case(layout, tmp_path, monkeypatch):
    if not _safe_sqlite_version(sqlite3.sqlite_version_info):
        pytest.skip('Actual context tests require fixed SQLite WAL library')
    envelope, options, _ = layout
    root = tmp_path / 'private-context-journal'
    root.mkdir(mode=0o700)

    def no_preflight(*_args, **_kwargs):
        pytest.fail('Host-safe context must not run Linux preflight')

    monkeypatch.setattr(LinuxExecutionAdapter,'_preflight',no_preflight)
    with DurableExecutionJournal(root,host_id=HOST,host_boot_id=BOOT) as journal:
        adapter = LinuxExecutionAdapter(options['job_root'].parent,tmp_path/'inert-runtime',
            options['runtime_manifest'],journal,cgroup_root=tmp_path/'NOT-A-KERNEL-CGROUP')
        yield SimpleNamespace(adapter=adapter,journal=journal,envelope=envelope,
            profile=render_execution_profile(envelope,**options),identity=synthetic_identity(envelope),root=root)


def hold(case, **changes):
    args = dict(adapter=case.adapter,envelope=case.envelope,profile=case.profile,execution_identity=case.identity)
    args.update(changes)
    return _hold_runtime_context(**args)


def test_scope_claims_actual_exact_job_and_exposes_registered_readonly_bindings(case):
    assert case.journal.read(case.envelope.job_id,case.envelope.envelope_sha256) is None
    with hold(case) as context:
        assert type(context) is HeldRuntimeContext
        assert type(context.lease) is DurableLease
        assert context.adapter is case.adapter and context.journal is case.journal
        assert context.envelope is case.envelope and context.profile is case.profile
        assert context.execution_identity is case.identity
        snapshot = context.require_current()
        assert snapshot.epoch == context.lease.epoch == 1
        assert snapshot.events[-1].kind == 'claimed'
        assert context.job_id == case.envelope.job_id
        assert context.envelope_sha256 == case.envelope.envelope_sha256
        assert context.profile_sha256 == case.profile.profile_sha256
        assert context.execution_id == case.identity.document['execution_id']
        assert context.reservation_id == case.envelope.metadata['reservation_id']
        assert context.owner_user_id == case.envelope.metadata['owner_user_id']
        assert context.site_id == case.envelope.metadata['site_id']
        assert context.host_id == HOST and context.host_boot_id == BOOT
        assert context.journal_id == case.journal.identity_reference(context.lease).journal_id
        assert context.worker_root == case.adapter.worker_root
        assert context.runtime_directory == case.adapter.runtime_directory
        assert context.cgroup_root == case.adapter.cgroup_root
        assert context.runtime_json == case.adapter._runtime_json
        assert context.helper_sha256 == case.adapter._helper_sha256
        assert context.require_current(snapshot.events[-1].sha256) == snapshot
        with pytest.raises(FrozenInstanceError):
            context._lease = None
        with pytest.raises((FrozenInstanceError,TypeError)):
            context.lease = None
    assert case.journal.read(case.envelope.job_id,case.envelope.envelope_sha256).epoch == 1
    with pytest.raises(SandboxError,match='context_closed'):
        context.require_current()
    for name in ('adapter','journal','lease','envelope','profile','execution_identity','execution_id'):
        with pytest.raises(SandboxError,match='context_closed'):
            getattr(context,name)


def test_exception_deactivates_scope_and_releases_actual_lock(case):
    with pytest.raises(RuntimeError):
        with hold(case) as context:
            context.require_current()
            raise RuntimeError('synthetic controller exception')
    with pytest.raises(SandboxError,match='context_closed'):
        context.require_current()
    with case.journal.claim(case.envelope.job_id,case.envelope.envelope_sha256) as reclaimed:
        assert reclaimed.epoch == 2
    assert not module._CONTEXTS and not module._HELD_JOBS


def test_nested_same_job_scope_and_external_actual_lease_are_rejected(case):
    with hold(case) as first:
        with pytest.raises(SandboxError,match='context_busy'):
            with hold(case):
                pytest.fail('Nested actual job claim was accepted')
        assert first.require_current().epoch == 1
    with case.journal.claim(case.envelope.job_id,case.envelope.envelope_sha256) as external:
        with pytest.raises(SandboxError,match='worker_busy'):
            with hold(case):
                pytest.fail('An external actual lease was borrowed')
        assert external.require_current().epoch == 2
    assert not module._CONTEXTS and not module._HELD_JOBS


@pytest.mark.parametrize('argument',['adapter','envelope','profile','execution_identity'])
@pytest.mark.parametrize('replacement',['json','duck','subclass'])
def test_exact_types_are_required_before_any_claim(case,argument,replacement):
    original = {'adapter':case.adapter,'envelope':case.envelope,'profile':case.profile,'execution_identity':case.identity}[argument]
    if replacement=='json':
        changed = {'epoch':1,'approved':True}
    elif replacement=='duck':
        changed = SimpleNamespace(**vars(original))
    else:
        class Subclass(type(original)):
            pass
        changed = object.__new__(Subclass)
        for name,value in vars(original).items():
            object.__setattr__(changed,name,value)
    with pytest.raises(SandboxError):
        with hold(case,**{argument:changed}):
            pytest.fail('A nonexact type entered actual claim')
    assert case.journal.read(case.envelope.job_id,case.envelope.envelope_sha256) is None


def test_external_lease_shape_is_not_an_entry_argument(case):
    with pytest.raises(TypeError):
        _hold_runtime_context(case.adapter,case.envelope,case.profile,case.identity,lease={'epoch':1})
    with pytest.raises(TypeError):
        HeldRuntimeContext()


def test_copy_forgery_subclass_and_pid_changes_cannot_borrow_a_scope(case):
    with hold(case) as actual:
        class Subclass(HeldRuntimeContext):
            pass
        for kind in (HeldRuntimeContext,Subclass):
            forged = object.__new__(kind)
            for name in HeldRuntimeContext.__slots__:
                object.__setattr__(forged,name,getattr(actual,name))
            with pytest.raises(SandboxError,match='context_closed'):
                forged.require_current()
        with pytest.raises(SandboxError,match='context_closed'):
            copy(actual).require_current()
        original_pid = actual._pid
        try:
            object.__setattr__(actual,'_pid',original_pid+1)
            with pytest.raises(SandboxError,match='context_closed'):
                actual.require_current()
        finally:
            object.__setattr__(actual,'_pid',original_pid)
        assert actual.require_current().epoch == 1


@pytest.mark.parametrize('field',['worker_root','runtime_directory','cgroup_root','runtime_json','helper','clock','journal'])
def test_adapter_configuration_mutation_invalidates_scope(case,field):
    with hold(case) as context:
        name = {'runtime_json':'_runtime_json','helper':'_helper_sha256'}.get(field,field)
        original = getattr(case.adapter,name)
        if field in {'worker_root','runtime_directory','cgroup_root'}:
            changed = original / 'changed'
        elif field=='runtime_json':
            changed = original+' '
        elif field=='helper':
            changed = '0'*64
        elif field=='clock':
            def changed():
                return 0
        else:
            changed = SimpleNamespace()
        try:
            setattr(case.adapter,name,changed)
            with pytest.raises(SandboxError,match='context_binding'):
                context.require_current()
        finally:
            setattr(case.adapter,name,original)
        assert context.require_current().epoch == 1


@pytest.mark.parametrize('target',['identity','profile_json','profile_hash','metadata','envelope_hash','job','files','boot','host'])
def test_identity_envelope_profile_and_host_pins_cannot_change_with_live_lease(case,target):
    with hold(case) as context:
        obj,name = {'identity':(case.identity,'_json'),'profile_json':(case.profile,'_json'),
            'profile_hash':(case.profile,'profile_sha256'),'metadata':(case.envelope,'_metadata_json'),
            'envelope_hash':(case.envelope,'envelope_sha256'),'job':(case.envelope,'job_id'),
            'files':(case.envelope,'_files'),'boot':(case.journal,'host_boot_id'),'host':(case.journal,'host_id')}[target]
        original = getattr(obj,name)
        if target in {'identity','profile_json','metadata'}:
            changed = original+' '
        elif target=='job':
            changed = 'c23-'+'0'*48
        elif target=='files':
            changed = MappingProxyType({**original,next(iter(original)):b'changed'})
        elif target=='boot':
            changed = str(uuid.uuid4())
        else:
            changed = '0'*64
        try:
            object.__setattr__(obj,name,changed)
            with pytest.raises(SandboxError,match='context_binding'):
                context.require_current()
        finally:
            object.__setattr__(obj,name,original)
        assert context.require_current().epoch == 1


@pytest.mark.parametrize('field',['owner_user_id','reservation_id','experiment_id','proposal_revision_id','approval_id','site_id','job_id','envelope_sha256'])
def test_mixed_retained_identity_cannot_enter_a_claim(case,field):
    original = case.identity.document[field]
    if field=='site_id':
        changed = 'v1:other-context-site'
    elif field=='job_id':
        changed = 'c23-'+'0'*48
    elif field=='envelope_sha256':
        changed = '0'*64
    else:
        changed = str(uuid.uuid4())
    assert changed != original
    with pytest.raises(SandboxError):
        with hold(case,execution_identity=synthetic_identity(case.envelope,**{field:changed})):
            pytest.fail('Mixed retained identity claimed a job')
    assert case.journal.read(case.envelope.job_id,case.envelope.envelope_sha256) is None


def test_historical_capacity_snapshot_grants_no_admission_but_keeps_identity_bindings(case):
    identity = synthetic_identity(case.envelope,capacity_reserved_at_commit=False)
    with hold(case,execution_identity=identity) as context:
        assert context.execution_identity.document['capacity_reserved_at_commit'] is False
        assert context.execution_identity.execution_authorized is False
        assert context.execution_identity.reservation_release_authorized is False
        context.require_current()


def test_expected_head_is_strict_and_current_after_actual_append(case):
    with hold(case) as context:
        initial = context.require_current().events[-1].sha256
        for wrong in ('0'*64,True,{'head':initial},'bad'):
            with pytest.raises(SandboxError,match='context_head'):
                context.require_current(wrong)
        current = context.lease.append('read_context_test',{'synthetic_control_history':True})
        with pytest.raises(SandboxError,match='context_head'):
            context.require_current(initial)
        assert context.require_current(current.sha256).events[-1] == current


def test_terminal_reacquisition_has_new_valid_context_and_old_stays_invalid(case):
    with hold(case) as first:
        first.lease.finish({'state':'synthetic control result only'})
        terminal = first.journal.terminal_reference(first.lease)
    with hold(case) as second:
        assert second is not first and second.require_current().terminal
        assert second.lease.epoch == terminal.epoch
        assert second.journal.terminal_reference(second.lease) == terminal
        with pytest.raises(SandboxError,match='context_closed'):
            first.require_current()


def test_closed_lease_and_lost_lock_descriptor_are_not_current_context(case):
    with hold(case) as first:
        first.lease.close()
        with pytest.raises(SandboxError,match='fence_lost'):
            first.require_current()
    with hold(case) as second:
        os.close(second.lease._fd)
        with pytest.raises(SandboxError,match='fence_lost'):
            second.require_current()


def test_original_lock_replacement_is_not_a_current_context(case):
    with hold(case) as context:
        lock = case.root/'locks'/(case.envelope.job_id+'.lock')
        lock.rename(case.root/'locks'/'old.lock')
        lock.touch(mode=0o600)
        with pytest.raises(SandboxError,match='fence_lost'):
            context.require_current()


def test_fork_clears_context_registry_without_waiting_or_unlocking_parent(case):
    with hold(case) as context:
        held, release = threading.Event(),threading.Event()

        def hold_registry_mutex():
            with module._MUTEX:
                held.set()
                release.wait(10)

        thread = threading.Thread(target=hold_registry_mutex)
        thread.start()
        assert held.wait(3)
        read_fd,write_fd = os.pipe()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',DeprecationWarning)
            pid = os.fork()
        if pid==0:
            os.close(read_fd)
            try:
                for action in (context.require_current,lambda:context.lease):
                    try:
                        action()
                    except SandboxError as error:
                        if error.reason!='sandbox_retained_context_closed':
                            os.write(write_fd,b'wrong_error')
                            break
                    else:
                        os.write(write_fd,b'inherited_context')
                        break
                else:
                    os.write(write_fd,b'child_context_denied')
            finally:
                os.close(write_fd)
                os._exit(0)
        os.close(write_fd)
        waited = False
        try:
            assert select.select([read_fd],[],[],3)[0], 'child waited on inherited registry mutex'
            assert os.read(read_fd,256)==b'child_context_denied'
            assert os.waitpid(pid,0)[1]==0
            waited = True
        finally:
            if not waited:
                try:
                    os.kill(pid,9)
                except ProcessLookupError:
                    pass
                os.waitpid(pid,0)
            os.close(read_fd)
            release.set()
            thread.join(5)
        assert not thread.is_alive()
        assert context.require_current().epoch==1
        # The child's at-fork cleanup did not LOCK_UN the parent's job.
        with DurableExecutionJournal(case.root,host_id=HOST,host_boot_id=BOOT) as other:
            with pytest.raises(SandboxError,match='worker_busy'):
                other.claim(case.envelope.job_id,case.envelope.envelope_sha256)


def test_approved_inspection_candidate_is_not_a_retained_identity(case):
    from orchestration.experiment_sandbox.operator_inspection import ApprovedCandidate
    candidate = object.__new__(ApprovedCandidate)
    with pytest.raises(SandboxError):
        with hold(case,execution_identity=candidate):
            pytest.fail('An inspection candidate created an actual context')
    assert case.journal.read(case.envelope.job_id,case.envelope.envelope_sha256) is None


def test_stale_epoch_and_foreign_actual_lease_cannot_borrow_registration(case):
    with hold(case) as context:
        lease = context.lease
        epoch = lease._epoch
        try:
            lease._epoch = epoch+1
            with pytest.raises(SandboxError,match='fence_lost'):
                context.require_current()
        finally:
            lease._epoch = epoch
        with case.journal.claim('c23-'+'e'*48,'d'*64) as other:
            try:
                object.__setattr__(context,'_lease',other)
                with pytest.raises(SandboxError,match='context_binding'):
                    context.require_current()
            finally:
                object.__setattr__(context,'_lease',lease)
        assert context.require_current().epoch == epoch


@pytest.mark.parametrize('target',['marker','event_chain'])
def test_context_checks_real_journal_again_instead_of_cached_snapshot(case,target):
    with hold(case) as context:
        context.require_current()
        if target=='marker':
            path = case.root/'identity.json'
            marker = json.loads(path.read_text())
            marker['journal_id'] = str(uuid.uuid4())
            path.write_text(canonical_json(marker))
        else:
            from orchestration.experiment_sandbox import journal as journal_module
            with sqlite3.connect(case.root/'journal.sqlite3') as connection:
                connection.execute('DROP TRIGGER events_no_update')
                connection.execute("UPDATE events SET payload_json='{}'")
                connection.execute(journal_module._TRIGGERS['events_no_update'])
        with pytest.raises(SandboxError,match='journal_integrity'):
            context.require_current()


def test_base_claim_cannot_be_replaced_by_instance_external_lease_callback(case,monkeypatch):
    calls = []

    def fake_claim(*_args):
        calls.append('instance fake must not be called')
        raise AssertionError('Context delegated actual claim to an instance callback')

    monkeypatch.setattr(case.journal,'claim',fake_claim)
    with hold(case) as context:
        assert context.require_current().epoch == 1
    assert calls == []


def test_mutable_or_duck_typed_nested_file_mapping_is_not_accepted(case):
    original = case.envelope._files
    try:
        object.__setattr__(case.envelope,'_files',dict(original))
        with pytest.raises(SandboxError,match='context_binding'):
            with hold(case):
                pytest.fail('Mutable file mapping entered actual context')
    finally:
        object.__setattr__(case.envelope,'_files',original)
    assert case.journal.read(case.envelope.job_id,case.envelope.envelope_sha256) is None
