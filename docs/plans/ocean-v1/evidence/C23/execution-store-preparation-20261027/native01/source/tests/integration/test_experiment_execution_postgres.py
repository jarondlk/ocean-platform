"""Native C23 storage/role tests, requiring an explicitly supplied owned PG.

Ephemeral synthetic keys authenticate software assertions only. No real issuer,
Linux proof, root bridge admission or physical acceptance is exercised here.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import threading
from types import SimpleNamespace
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError

from db.app_models import ResearchExperiment, ResearchExperimentApproval, ResearchExperimentRevision
from db.experiment_execution_models import EXECUTION_MODELS, IDENTITY_HASH_FIELDS
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.execution_store import (
    C23ExecutionStore, ExecutionReservationBinding, ExecutionStoreConfig,
    execution_job_id, planned_reservation_ids,
)
from orchestration.experiment_sandbox.proofs import (
    PinnedTerminationIssuer, TerminationVerifierRegistry, canonical_packet_bytes, sign_termination_claims,
)
from schema.context_catalogue import canonical_json
from schema.experiment_execution import TerminationClaims, TerminationIssuerScope
from schema.research_experiments import EnvironmentDescriptor
from tests import experiment_execution_postgres_support as pg
from tests.research_experiment_support import make_experiment_fixture
from tests.test_experiment_sandbox_proofs import _claims

pytestmark = pytest.mark.skipif(os.environ.get('RUN_C23_POSTGRES_INTEGRATION') != '1',
    reason='requires explicitly identified owned C23 PostgreSQL; no service is started')
disposable_database, isolated, role_database = pg.disposable_database, pg.isolated, pg.role_database


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def actual(role_database, tmp_path, monkeypatch):
    for name in ('ENABLE_V1_CATALOGUE','ENABLE_V1_INVESTIGATIONS'):
        monkeypatch.setenv(name,'true')
    fixture = make_experiment_fixture(role_database['engine'],tmp_path)
    fixture.environment = EnvironmentDescriptor(kind='linux-gvisor',test_only=False,
        python_version='3.12.15',image_digest='sha256:'+'a'*64,lockfile_sha256='b'*64,
        packages={name:'1.0.0' for name in ('numpy','pandas','pyarrow','scipy','statsmodels','matplotlib')},
        description='C23 native database software fixture only; no runtime acceptance')
    fixture.service.environments[fixture.environment.identity_sha256] = fixture.environment.model_dump(mode='json')
    return SimpleNamespace(database=role_database,fixture=fixture,key=Ed25519PrivateKey.generate())


def prepared(case, *, actor=None, idempotency_key=None):
    f = case.fixture
    actor = actor or f.user
    initial = f.create(user=actor)
    approved = f.service.invoke('approve',f.decision(initial),actor)['experiment']
    request = f.decision(approved)
    if idempotency_key:
        request['idempotency_key'] = idempotency_key
    execution_id, reservation_id = planned_reservation_ids(site_id=f.service.site_id,
        owner_user_id=str(actor.id),idempotency_key=request['idempotency_key'])
    with f.factory() as session:
        head = session.get(ResearchExperiment,uuid.UUID(approved['id']))
        revision = session.get(ResearchExperimentRevision,head.head_revision_id)
        approval = session.scalar(select(ResearchExperimentApproval).where(ResearchExperimentApproval.revision_id==revision.id))
        proposal, environment, exported = f.service._exported(session,revision)
        envelope = f.service._metadata(head,revision,approval,SimpleNamespace(id=uuid.UUID(reservation_id)),proposal,environment,exported)
        source = revision.source_sha256
        approval_hash = approval.request_sha256
    envelope_json = canonical_json(envelope)
    values = {name:_hash(name) for name in IDENTITY_HASH_FIELDS}
    values.update(execution_id=execution_id,reservation_id=reservation_id,owner_user_id=str(actor.id),
        experiment_id=approved['id'],proposal_revision_id=approved['proposal_revision_id'],approval_id=envelope['approval_id'],
        site_id=f.service.site_id,idempotency_key=request['idempotency_key'],request_json=canonical_json(request),
        envelope_json=envelope_json,job_id=execution_job_id(site_id=f.service.site_id,reservation_id=reservation_id,
            envelope_sha256=_hash(envelope_json)),image_digest=environment['image_digest'],
        approval_request_sha256=approval_hash,execution_request_sha256=_hash(canonical_json(request)),
        envelope_sha256=_hash(envelope_json),source_sha256=source,environment_sha256=approved['hashes']['environment_sha256'])
    return ExecutionReservationBinding.model_validate(values)


def store_for(case,binding):
    scope = TerminationIssuerScope.model_validate({name:getattr(binding,name) for name in TerminationIssuerScope.model_fields})
    issuer = PinnedTerminationIssuer(issuer_id='synthetic-db-test',key_id='ephemeral-db-key',
        trust_scope='synthetic-software-test',public_key=case.key.public_key().public_bytes_raw(),scope=scope)
    registry = TerminationVerifierRegistry(issuers=[issuer],trust_scope='synthetic-software-test',enabled=True)
    d = case.database
    return C23ExecutionStore(config=ExecutionStoreConfig(site_id=binding.site_id,database_name=d['url'].database,
        schema=d['schema'],controller_session_factory=d['controller_factory'],recorder_session_factory=d['recorder_factory'],
        roles=d['roles'],verifier_registry=registry,store_scope='isolated-unmounted-operator',enabled=lambda:case.fixture.state['enabled']))


def reserved(case, *, actor=None):
    binding = prepared(case,actor=actor)
    store = store_for(case,binding)
    with store.controller_transaction() as session:
        assert store.reserve_in_transaction(session,binding)==binding.execution_id
    return store,binding


def closed(store,binding, *, publish=False):
    start_id = str(uuid.uuid4())
    args = dict(execution_id=binding.execution_id,start_id=start_id,host_boot_id=str(uuid.uuid4()),
        journal_id=str(uuid.uuid4()),journal_epoch=1,profile_sha256=_hash('prepared-profile'),
        preceding_journal_sha256=_hash('journal-before-start'))
    with store.controller_transaction() as session:
        store.record_event_in_transaction(session,expected_fence=1,event_id=start_id,kind='start_consumed',**args)
    fence = 2
    if publish:
        with store.controller_transaction() as session:
            store.record_event_in_transaction(session,expected_fence=fence,event_id=str(uuid.uuid4()),
                kind='publication_retained',result_sha256=_hash('validated-output'),**args)
        fence += 1
    with store.controller_transaction(cleanup=True) as session:
        store.record_event_in_transaction(session,expected_fence=fence,event_id=str(uuid.uuid4()),kind='closed',**args)
    return store.load_closed_binding(binding.execution_id)


def packet(case,binding):
    synthetic = _claims()
    claims = TerminationClaims.model_validate({'binding':binding.model_dump(),
        'journal':synthetic.journal.model_dump(),
        'kernel':{**synthetic.kernel.model_dump(),'cgroup_path':'/ocean-c23/'+binding.job_id,
            'delete_job_id':binding.job_id,'delete_runtime_sha256':binding.runtime_sha256,
            'delete_host_boot_id':binding.host_boot_id}})
    return canonical_packet_bytes(sign_termination_claims(claims,issuer_id='synthetic-db-test',
        key_id='ephemeral-db-key',trust_scope='synthetic-software-test',private_key=case.key))


def count(case,table):
    with case.database['engine'].connect() as connection:
        return connection.scalar(text('SELECT count(*) FROM '+table))


def test_new_model_schema_exact_and_empty_roundtrip(isolated):
    pg.alembic(isolated,'upgrade','20261027_0021')
    reflected = inspect(isolated['engine'])
    for model in EXECUTION_MODELS:
        table = model.__table__
        assert [(x['name'],x['nullable']) for x in reflected.get_columns(table.name)] == [(x.name,x.nullable) for x in table.columns]
        assert {x['name'] for x in reflected.get_check_constraints(table.name)} == {x.name for x in table.constraints if x.__class__.__name__=='CheckConstraint'}
        assert {(tuple(x['constrained_columns']),x['referred_table'],tuple(x['referred_columns'])) for x in reflected.get_foreign_keys(table.name)} == {
            (tuple(e.parent.name for e in fk.elements),fk.referred_table.name,tuple(e.column.name for e in fk.elements)) for fk in table.foreign_key_constraints}
    pg.alembic(isolated,'downgrade','20261020_0020')
    with isolated['engine'].connect() as c:
        guard = c.scalar(text("SELECT pg_get_functiondef('ocean_research_experiment_reservation_guard()'::regprocedure)"))
        assert "OLD.state IN ('accepted','released') OR NEW.state='released'" in guard
    pg.alembic(isolated,'upgrade','20261027_0021')


def test_exact_reserve_replay_and_changed_request_conflict(actual):
    store,b = reserved(actual)
    with store.controller_transaction() as session:
        assert store.reserve_in_transaction(session,b)==b.execution_id
    p = b.model_dump()
    p['source_policy_sha256'] = 'f'*64
    with pytest.raises(DBAPIError), store.controller_transaction() as session:
        store.reserve_in_transaction(session,ExecutionReservationBinding.model_validate(p))
    assert count(actual,'research_experiment_execution')==count(actual,'research_experiment_reservation')==1
    assert count(actual,'research_experiment_outbox')==0


def test_serving_and_controller_cannot_forge_recorded_proof_or_release(actual):
    store,b = reserved(actual)
    schema = actual.database['schema']
    roles = actual.database['roles']
    for role in (roles.serving_role,roles.controller_role):
        engine = actual.database['role_engines'][role]
        for statement in (
            f"SELECT {schema}.ocean_c23_record_proof('{{}}'::jsonb)",
            f"SELECT {schema}.ocean_c23_release('{b.execution_id}','{uuid.uuid4()}',3,'{uuid.uuid4()}')",
            f"INSERT INTO {schema}.research_experiment_termination_proof(id) VALUES('{uuid.uuid4()}')",
            f"INSERT INTO {schema}.research_experiment_release(id) VALUES('{uuid.uuid4()}')",
            f"UPDATE {schema}.research_experiment_reservation SET state='released'",
        ):
            with pytest.raises(DBAPIError), engine.begin() as connection:
                connection.execute(text(statement))
    with pytest.raises(SandboxError):
        store.record_verified_termination(execution_id=b.execution_id,packet_bytes={'state':'stopped','authenticated':True})
    assert count(actual,'research_experiment_release')==0


def test_closed_proof_release_replay_preserves_frozen_history_after_launch_disable(actual):
    store,b = reserved(actual)
    before = {table:count(actual,table) for table in ('research_experiment_revision','research_experiment_approval',
        'research_experiment_revision_file','research_experiment_input_blob')}
    bound = closed(store,b,publish=True)
    actual.fixture.state['enabled'] = False
    raw = packet(actual,bound)
    proof_id = store.record_verified_termination(execution_id=b.execution_id,packet_bytes=raw)
    assert store.record_verified_termination(execution_id=b.execution_id,packet_bytes=raw)==proof_id
    release_id = store.release_terminated(execution_id=b.execution_id,proof_id=proof_id,expected_fence=bound.closed_fence)
    assert store.release_terminated(execution_id=b.execution_id,proof_id=proof_id,expected_fence=bound.closed_fence)==release_id
    with pytest.raises(DBAPIError):
        store.release_terminated(execution_id=b.execution_id,proof_id=str(uuid.uuid4()),expected_fence=bound.closed_fence)
    with actual.database['engine'].connect() as c:
        assert c.scalar(text('SELECT state FROM research_experiment_reservation'))=='released'
    assert {table:count(actual,table) for table in before}==before


@pytest.mark.parametrize('changed',['execution_id','reservation_id','owner_user_id','approval_id','envelope_sha256',
    'worker_id','host_boot_id','journal_id','journal_epoch','runtime_sha256','profile_sha256','closed_fence'])
def test_mixed_or_stale_signed_tuple_rejected_before_recording(actual,changed):
    store,b = reserved(actual)
    bound = closed(store,b)
    raw = json.loads(packet(actual,bound))
    # Re-sign a well-typed altered claim when its deterministic correlations
    # permit it. Either wire-contract or pinned DB-bound verification must fail.
    changed_binding = raw['claims']['binding']
    old = changed_binding[changed]
    changed_binding[changed] = old+1 if type(old) is int else (str(uuid.uuid4()) if len(old)==36 else 'f'*64)
    with pytest.raises((ValueError,SandboxError)):
        claims = TerminationClaims.model_validate(raw['claims'])
        signed = canonical_packet_bytes(sign_termination_claims(claims,issuer_id='synthetic-db-test',
            key_id='ephemeral-db-key',trust_scope='synthetic-software-test',private_key=actual.key))
        store.record_verified_termination(execution_id=b.execution_id,packet_bytes=signed)
    assert count(actual,'research_experiment_termination_proof')==0


def test_history_immutability_and_populated_downgrade_refusal(actual):
    store,b = reserved(actual)
    bound = closed(store,b)
    proof = store.record_verified_termination(execution_id=b.execution_id,packet_bytes=packet(actual,bound))
    store.release_terminated(execution_id=b.execution_id,proof_id=proof,expected_fence=bound.closed_fence)
    for model in EXECUTION_MODELS:
        table = model.__tablename__
        for statement in (f'DELETE FROM {table}',f'TRUNCATE {table} CASCADE'):
            with pytest.raises(DBAPIError), actual.database['engine'].begin() as c:
                c.execute(text(statement))
        if table!='research_experiment_execution_state':
            column = 'execution_id' if table=='research_experiment_execution' else 'id'
            with pytest.raises(DBAPIError), actual.database['engine'].begin() as c:
                c.execute(text(f'UPDATE {table} SET {column}={column}'))
    pg.alembic(actual.database,'downgrade','20261020_0020',succeeds=False)
    assert count(actual,'research_experiment_release')==1


def test_release_transaction_rollback_keeps_capacity(actual):
    store,b = reserved(actual)
    bound = closed(store,b)
    proof = store.record_verified_termination(execution_id=b.execution_id,packet_bytes=packet(actual,bound))
    with pytest.raises(RuntimeError), actual.database['recorder_factory'].begin() as session:
        session.execute(text(f"SELECT {actual.database['schema']}.ocean_c23_release(CAST(:e AS uuid),CAST(:p AS uuid),:f,CAST(:r AS uuid))"),
            {'e':b.execution_id,'p':proof,'f':bound.closed_fence,'r':str(uuid.uuid4())})
        raise RuntimeError('Synthetic commit acknowledgement lost before commit')
    assert count(actual,'research_experiment_release')==0
    with actual.database['engine'].connect() as c:
        assert c.scalar(text('SELECT state FROM research_experiment_reservation'))=='reserved'


def test_two_real_global_slots_one_owner_limit_and_release_capacity_serialization(actual):
    store,b = reserved(actual)
    other = prepared(actual,actor=actual.fixture.other)
    other_store = store_for(actual,other)
    with other_store.controller_transaction() as s:
        other_store.reserve_in_transaction(s,other)
    third = prepared(actual,actor=actual.fixture.admin)
    third_store = store_for(actual,third)
    with pytest.raises(DBAPIError), third_store.controller_transaction() as s:
        third_store.reserve_in_transaction(s,third)
    bound = closed(store,b)
    proof = store.record_verified_termination(execution_id=b.execution_id,packet_bytes=packet(actual,bound))
    holding = threading.Event()
    release_commit = threading.Event()
    entered = threading.Event()
    finished = threading.Event()

    def release():
        with actual.database['recorder_factory'].begin() as s:
            s.execute(text(f"SELECT {actual.database['schema']}.ocean_c23_release(CAST(:e AS uuid),CAST(:p AS uuid),:f,CAST(:r AS uuid))"),
                {'e':b.execution_id,'p':proof,'f':bound.closed_fence,'r':str(uuid.uuid4())})
            holding.set()
            assert release_commit.wait(5)

    def reserve():
        assert holding.wait(5)
        entered.set()
        with third_store.controller_transaction() as s:
            third_store.reserve_in_transaction(s,third)
        finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        releasing, reserving = pool.submit(release), pool.submit(reserve)
        try:
            assert entered.wait(5)
            assert not finished.wait(0.1), 'Reserve passed uncommitted capacity release'
        finally:
            release_commit.set()
        releasing.result(timeout=10)
        reserving.result(timeout=10)
    assert count(actual,'research_experiment_release')==1
    with actual.database['engine'].connect() as c:
        assert c.scalar(text("SELECT count(*) FROM research_experiment_reservation WHERE state<>'released'"))==2


@pytest.mark.parametrize('first_channel',['real','fake'])
def test_concurrent_fake_and_real_channel_guards_share_reservation_lock(actual,first_channel):
    b = prepared(actual)
    d = actual.database
    with d['engine'].begin() as connection:
        connection.execute(text('INSERT INTO research_experiment_reservation(id,experiment_id,revision_id,approval_id,user_id,slot,state,envelope_sha256) '
            "VALUES(CAST(:r AS uuid),CAST(:e AS uuid),CAST(:v AS uuid),CAST(:a AS uuid),CAST(:u AS uuid),0,'reserved',:h)"),
            {'r':b.reservation_id,'e':b.experiment_id,'v':b.proposal_revision_id,'a':b.approval_id,'u':b.owner_user_id,'h':b.envelope_sha256})
    locked,second_started,commit_first = threading.Event(),threading.Event(),threading.Event()
    second_done = threading.Event()

    def insert(connection,channel):
        if channel=='real':
            connection.execute(text('INSERT INTO research_experiment_execution SELECT rec.* '
                'FROM jsonb_populate_record(NULL::research_experiment_execution,CAST(:p AS jsonb)||jsonb_build_object(\'created_at\',clock_timestamp())) rec'),
                {'p':json.dumps(b.model_dump())})
        else:
            connection.execute(text("INSERT INTO research_experiment_outbox(id,reservation_id,delivery_id,state,attempts) VALUES(CAST(:i AS uuid),CAST(:r AS uuid),CAST(:d AS uuid),'pending',0)"),
                {'i':str(uuid.uuid4()),'r':b.reservation_id,'d':str(uuid.uuid4())})

    def first():
        with d['engine'].begin() as connection:
            insert(connection,first_channel)
            locked.set()
            assert commit_first.wait(5)

    def second():
        assert locked.wait(5)
        second_started.set()
        try:
            with d['engine'].begin() as connection:
                insert(connection,'fake' if first_channel=='real' else 'real')
        finally:
            second_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        winning,losing = pool.submit(first),pool.submit(second)
        try:
            assert second_started.wait(5)
            assert not second_done.wait(0.1), 'Competing channel did not wait on reservation row'
        finally:
            commit_first.set()
        winning.result(timeout=10)
        with pytest.raises(DBAPIError):
            losing.result(timeout=10)
    assert count(actual,'research_experiment_execution')==(first_channel=='real')
    assert count(actual,'research_experiment_outbox')==(first_channel=='fake')


def test_fake_real_same_owner_and_three_owner_capacity_races(actual):
    f = actual.fixture
    fake_environment = next(value for value in f.service.environments.values() if value['kind']=='c22-fake')

    def approved_fake(actor):
        request = f.request(user=actor)
        request['proposal']['environment_id'] = EnvironmentDescriptor.model_validate(fake_environment).identity_sha256
        proposal = f.service.invoke('create',request,actor)['experiment']
        return f.service.invoke('approve',f.decision(proposal),actor)['experiment']

    fake = approved_fake(f.user)
    real = prepared(actual,actor=f.user)
    store = store_for(actual,real)
    barrier = threading.Barrier(2)

    def fake_reserve():
        barrier.wait(5)
        return f.service.invoke('dispatch',f.decision(fake),f.user)

    def real_reserve():
        barrier.wait(5)
        with store.controller_transaction() as s:
            return store.reserve_in_transaction(s,real)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (pool.submit(fake_reserve),pool.submit(real_reserve))
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=10))
            except Exception as error:
                outcomes.append(error)
    assert sum(isinstance(outcome,Exception) for outcome in outcomes)==1
    assert count(actual,'research_experiment_reservation')==1
    # Two additional distinct owners race for the remaining global slot.
    other_fake = approved_fake(f.other)
    third_real = prepared(actual,actor=f.admin)
    third_store = store_for(actual,third_real)
    barrier = threading.Barrier(2)

    def other():
        barrier.wait(5)
        return f.service.invoke('dispatch',f.decision(other_fake),f.other)

    def third():
        barrier.wait(5)
        with third_store.controller_transaction() as s:
            return third_store.reserve_in_transaction(s,third_real)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (pool.submit(other),pool.submit(third))
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=10))
            except Exception as error:
                outcomes.append(error)
    assert sum(isinstance(outcome,Exception) for outcome in outcomes)==1
    with actual.database['engine'].connect() as c:
        assert c.scalar(text("SELECT count(*) FROM research_experiment_reservation WHERE state<>'released'"))==2
        assert c.scalar(text("SELECT count(DISTINCT user_id) FROM research_experiment_reservation WHERE state<>'released'"))==2


def test_start_replay_stale_fence_and_cleanup_after_launch_disable(actual):
    store,b = reserved(actual)
    start_id = str(uuid.uuid4())
    args = dict(execution_id=b.execution_id,start_id=start_id,host_boot_id=str(uuid.uuid4()),
        journal_id=str(uuid.uuid4()),journal_epoch=1,profile_sha256=_hash('profile'),preceding_journal_sha256=_hash('journal'))
    with store.controller_transaction() as s:
        first = store.record_event_in_transaction(s,expected_fence=1,event_id=start_id,kind='start_consumed',**args)
    with store.controller_transaction() as s:
        assert store.record_event_in_transaction(s,expected_fence=1,event_id=start_id,kind='start_consumed',**args)==first
    with pytest.raises(DBAPIError), store.controller_transaction() as s:
        store.record_event_in_transaction(s,expected_fence=1,event_id=str(uuid.uuid4()),kind='start_consumed',**args)
    actual.fixture.state['enabled'] = False
    with pytest.raises(SandboxError):
        with store.controller_transaction():
            pytest.fail('Disabled launch boundary opened')
    with store.controller_transaction(cleanup=True) as s:
        store.record_event_in_transaction(s,expected_fence=2,event_id=str(uuid.uuid4()),kind='closed',**args)
    assert store.load_closed_binding(b.execution_id).closed_fence==3
