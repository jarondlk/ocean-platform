"""Additional real restricted-PG edge cases; no Linux/runtime/generated Python.

Accepted positive lifecycle/ACK cases remain in the separate original module.
Only missing race, callback, collision and publication-integrity gates run here.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from orchestration.experiment_sandbox import retained_admission as module
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.research_experiments import ResearchExperimentError
from tests import experiment_execution_postgres_support as pg
from tests.integration import test_retained_admission_postgres as accepted
from tests.integration import test_retained_reserve_postgres as reserve_tests

pytestmark=pytest.mark.skipif(os.environ.get('RUN_C23_POSTGRES_INTEGRATION')!='1',
    reason='Explicit new owned C23 PostgreSQL required; starts no service')
disposable_database,isolated,role_database=pg.disposable_database,pg.isolated,pg.role_database
retained,case=reserve_tests.retained,accepted.case


def execution_state(case):
    with case.native.database['controller_factory']() as session:
        return session.execute(text('SELECT state,fence FROM research_experiment_execution_state '
            'WHERE execution_id=CAST(:id AS uuid)'),{'id':case.identity.document['execution_id']}).one()


def native_start(case,context,identity,event_id):
    with case.store.controller_transaction() as session:
        return case.store.event_after_fence_in_transaction(session,execution_id=identity,
            expected_fence=1,event_id=event_id,kind='start_consumed',start_id=event_id,
            host_boot_id=context.host_boot_id,journal_id=context.journal_id,journal_epoch=1,
            profile_sha256=context.profile_sha256,
            preceding_journal_sha256=context.require_current().events[-1].sha256,
            final_fence=lambda:context.require_current())


def test_fresh_internal_uuid_collision_cannot_mint_replay_permission(case,monkeypatch):
    other=case.bridge.reserve(case.native.approved(actor=case.native.fixture.other),
        current_owner=case.native.fixture.other)
    used=str(uuid.uuid4())
    with case.hold() as context:
        assert native_start(case,context,other.document['execution_id'],used)==used
        monkeypatch.setattr(module.uuid,'uuid4',lambda:uuid.UUID(used))
        with pytest.raises(SandboxError,match='start_reconciliation'):
            case.hooks.admit_start(context)
        assert execution_state(case)==('reserved',1)
        assert not any(event.kind=='start_intent' for event in context.require_current().events)


def test_two_concurrent_distinct_native_start_ids_have_exactly_one_cas_winner(case):
    with case.hold() as context:
        identities=[str(uuid.uuid4()),str(uuid.uuid4())]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(native_start,case,context,context.execution_id,identity) for identity in identities]
            winners,losers=[],[]
            for future in futures:
                try:
                    winners.append(future.result(timeout=20))
                except DBAPIError as error:
                    losers.append(error)
        assert len(winners)==len(losers)==1 and winners[0] in identities
        assert execution_state(case)==('start_consumed',2)
        with pytest.raises(SandboxError,match='start_reconciliation'):
            case.hooks.admit_start(context)
        assert not any(event.kind=='start_intent' for event in context.require_current().events)


@pytest.mark.parametrize('gate',['source','flag','factory'])
def test_last_controller_callback_mutation_cannot_cross_final_current_fence(case,gate):
    calls=[]
    def enabled():
        calls.append(1)
        if len(calls)==3:  # Initial row read, mutation transaction, final controller guard.
            if gate=='source':
                path=case.policy.source_root/'orchestration/experiment_sandbox/profile.py'
                path.chmod(0o600)
                path.write_bytes(path.read_bytes()+b'\n')
                path.chmod(0o400)
            elif gate=='flag':
                case.native.fixture.state['enabled']=False
            else:
                case.bridge._service.session_factory=lambda:None
        return True
    object.__setattr__(case.store.config,'enabled',enabled)
    with case.hold() as context,pytest.raises((SandboxError,ResearchExperimentError,ValueError)):
        case.hooks.admit_start(context)
    assert len(calls)>=3 and execution_state(case)==('reserved',1)


def test_acknowledged_start_postread_does_not_reinvoke_external_launch_flags(case,monkeypatch):
    original=case.store.controller_transaction
    calls,acknowledged=[],[]
    def enabled():
        assert not acknowledged,'External launch callback ran after acknowledged start commit'
        return True
    object.__setattr__(case.store.config,'enabled',enabled)
    @contextmanager
    def manager(**kwargs):
        calls.append(kwargs)
        number=len(calls)
        with original(**kwargs) as session:
            yield session
        if number==2:
            acknowledged.append(True)
    monkeypatch.setattr(case.store,'controller_transaction',manager)
    with case.hold() as context:
        permit=case.hooks.admit_start(context)
        assert permit.consume(context)['start_fence']==2
    assert acknowledged and calls[-1]=={'cleanup':True}


@pytest.mark.parametrize('gate',['hash','retained','terminal'])
def test_publication_revalidates_actual_terminal_and_private_retained_output_bytes(case,gate):
    from dataclasses import replace
    with case.hold() as context:
        accepted.start(case,context)
        terminal,outputs,_,_=accepted.finish(case,context)
        digest=hashlib.sha256(outputs.manifest_bytes).hexdigest()
        if gate=='hash':
            digest='0'*64
        elif gate=='retained':
            path=case.job/'retained/files/summary.json'
            path.chmod(0o600)
            path.write_bytes(b'{"columns":["value"],"rows":[[999]]}')
            path.chmod(0o400)
        else:
            terminal=replace(terminal,terminal_result_sha256='0'*64)
        with pytest.raises(SandboxError):
            case.hooks.admit_publication(context,terminal,digest)
        assert execution_state(case)==('start_consumed',2)
        actual=context.journal.terminal_reference(context.lease)
        assert case.hooks.close_execution(context,actual).closed_fence==3


def test_queued_terminal_and_consumed_start_without_journal_intent_keep_capacity(case):
    with case.hold() as context:
        case.hooks.admit_start(context).consume(context)
        terminal,_,_,_=accepted.finish(case,context)
        with pytest.raises(SandboxError,match='start_binding'):
            case.hooks.close_execution(context,terminal)
        assert execution_state(case)==('start_consumed',2)
