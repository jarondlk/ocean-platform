"""C22 disposable PostgreSQL reservation, immutability and retention gates."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
import threading
import uuid

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, OperationalError

from db import app_models as models
from orchestration.research_experiments import FakeExperimentExecutor, ResearchExperimentError
from tests import research_experiment_postgres_support as pg
from tests.research_experiment_support import make_experiment_fixture


disposable_database, isolated = pg.disposable_database, pg.isolated
pytestmark = pytest.mark.skipif(os.environ.get('RUN_POSTGRES_INTEGRATION') != '1',
    reason='requires explicitly verified disposable C22 PostgreSQL')
NEW_MODELS = tuple(model for model in vars(models).values() if isinstance(model, type)
    and hasattr(model, '__tablename__') and model.__tablename__.startswith('research_experiment'))


@pytest.fixture
def actual(isolated, tmp_path, monkeypatch):
    for name in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS'):
        monkeypatch.setenv(name, 'true')
    pg.alembic(isolated, 'upgrade', 'head')
    return make_experiment_fixture(isolated['engine'], tmp_path)


def approved(actual, *, user=None):
    actor = user or actual.user
    experiment = actual.create(user=actor)
    return actual.service.invoke('approve', actual.decision(experiment), actor)['experiment']


def dispatch(actual, *, user=None):
    actor = user or actual.user
    experiment = approved(actual, user=actor)
    return actual.service.invoke('dispatch', actual.decision(experiment), actor)['experiment']


def concurrently(functions):
    barrier = threading.Barrier(len(functions))

    def perform(function):
        barrier.wait(timeout=10)
        try:
            return function()
        except ResearchExperimentError as error:
            return error
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return list(pool.map(perform, functions))


def test_migration_exact_model_schema_and_empty_roundtrip(isolated):
    pg.alembic(isolated, 'upgrade', 'head')
    assert pg.revision(isolated) == '20261027_0021'
    reflected = inspect(isolated['engine'])
    for model in NEW_MODELS:
        table = model.__table__
        assert [(entry['name'], entry['nullable']) for entry in reflected.get_columns(table.name)] == [(column.name, column.nullable) for column in table.columns]
        assert {entry['name'] for entry in reflected.get_check_constraints(table.name)} == {constraint.name for constraint in table.constraints if constraint.__class__.__name__ == 'CheckConstraint'}
        assert {(tuple(entry['constrained_columns']), entry['referred_table'], tuple(entry['referred_columns'])) for entry in reflected.get_foreign_keys(table.name)} == {
            (tuple(element.parent.name for element in constraint.elements), constraint.referred_table.name, tuple(element.column.name for element in constraint.elements))
            for constraint in table.foreign_key_constraints}
    pg.alembic(isolated, 'upgrade', 'head')
    pg.alembic(isolated, 'downgrade', '20261019_0019')
    assert not {model.__tablename__ for model in NEW_MODELS} & set(inspect(isolated['engine']).get_table_names())
    pg.alembic(isolated, 'upgrade', 'head')


def test_real_pg_freeze_last_file_before_head_and_approval_revision_history(actual):
    first = approved(actual)
    assert len(first['manifest']['files']) >= 3
    request = {**first['binding'], 'proposal': first['proposal'], 'experiment_id': first['id'],
        'expected_version': first['version'], 'expected_proposal_revision_id': first['proposal_revision_id'],
        'idempotency_key': str(uuid.uuid4())}
    request['proposal']['python_code'] += '# review changed\n'
    second = actual.service.invoke('revise', request, actual.user)['experiment']
    assert second['version'] == 2 and second['approval']['status'] == 'stale'
    with actual.factory() as session:
        assert len(list(session.scalars(select(models.ResearchExperimentRevisionFile).where(
            models.ResearchExperimentRevisionFile.revision_id == uuid.UUID(second['proposal_revision_id']))))) == len(second['manifest']['files'])


@pytest.mark.parametrize('statement', [
    "UPDATE research_experiment_revision SET proposal_json='{}'",
    "UPDATE research_experiment_input_blob SET content=decode('00','hex')",
    "DELETE FROM research_experiment_revision_file",
    "TRUNCATE research_experiment_revision CASCADE",
    "UPDATE research_experiment_approval SET request_json='{}'",
    "UPDATE research_experiment SET version=0",
    "UPDATE research_experiment_capacity SET id=1",
])
def test_native_sql_cannot_rewrite_delete_or_truncate_private_records(actual, statement):
    approved(actual)
    with pytest.raises(DBAPIError), actual.factory.begin() as session:
        session.execute(text(statement))


def test_native_postactivation_file_append_and_head_rollback_rejected(actual):
    experiment = actual.create()
    with pytest.raises(DBAPIError), actual.factory.begin() as session:
        session.execute(text("INSERT INTO research_experiment_revision_file(revision_id,name,experiment_id,user_id,sha256,size_bytes) SELECT revision_id,'extra.json',experiment_id,user_id,sha256,size_bytes FROM research_experiment_revision_file LIMIT 1"))
    with pytest.raises(DBAPIError), actual.factory.begin() as session:
        session.execute(text("UPDATE research_experiment SET head_revision_id=NULL"))
    assert actual.service.invoke('get', actual.address(experiment), actual.user)['experiment']['proposal_revision_id'] == experiment['proposal_revision_id']


def test_same_key_concurrent_dispatch_is_one_reservation_and_outbox(actual):
    experiment = approved(actual)
    request = actual.decision(experiment)
    results = concurrently([lambda: actual.service.invoke('dispatch', request, actual.user)] * 2)
    assert not any(isinstance(result, Exception) for result in results)
    assert len({result['experiment']['dispatch']['reservation_id'] for result in results}) == 1
    with actual.factory() as session:
        assert len(list(session.scalars(select(models.ResearchExperimentReservation)))) == 1
        assert len(list(session.scalars(select(models.ResearchExperimentOutbox)))) == 1


def test_different_keys_same_revision_reuse_dispatch_identity(actual):
    experiment = approved(actual)
    requests = [actual.decision(experiment) for _ in range(2)]
    results = concurrently([lambda request=request: actual.service.invoke('dispatch', request, actual.user) for request in requests])
    assert not any(isinstance(result, Exception) for result in results)
    assert len({result['experiment']['dispatch']['reservation_id'] for result in results}) == 1
    with actual.factory() as session:
        assert len(list(session.scalars(select(models.ResearchExperimentOutbox)))) == 1


def test_one_owner_capacity_serializes_two_proposals(actual):
    proposals = [approved(actual), approved(actual)]
    results = concurrently([lambda proposal=proposal: actual.service.invoke('dispatch', actual.decision(proposal), actual.user) for proposal in proposals])
    assert sum(isinstance(result, ResearchExperimentError) and result.code == 'capacity_unavailable' for result in results) == 1
    with actual.factory() as session:
        assert len(list(session.scalars(select(models.ResearchExperimentReservation)))) == 1


def test_two_global_capacity_serializes_three_owners(actual):
    actors = (actual.user, actual.other, actual.admin)
    proposals = [approved(actual, user=actor) for actor in actors]
    results = concurrently([lambda proposal=proposal, actor=actor: actual.service.invoke('dispatch', actual.decision(proposal), actor)
        for proposal, actor in zip(proposals, actors, strict=True)])
    assert sum(isinstance(result, ResearchExperimentError) and result.code == 'capacity_unavailable' for result in results) == 1
    with actual.factory() as session:
        reservations = list(session.scalars(select(models.ResearchExperimentReservation)))
        assert len(reservations) == 2 and {item.slot for item in reservations} == {0, 1}


def test_native_reservation_cannot_release_or_clone_active_owner_and_slot(actual):
    dispatch(actual)
    with pytest.raises(DBAPIError), actual.factory.begin() as session:
        session.execute(text("UPDATE research_experiment_reservation SET state='released'"))
    with pytest.raises(DBAPIError), actual.factory.begin() as session:
        session.execute(text("UPDATE research_experiment_reservation SET slot=1"))


def test_missing_ack_retry_deduplicates_effect_and_never_releases_capacity(actual):
    experiment = dispatch(actual)
    reservation_id = experiment['dispatch']['reservation_id']

    class LostAck(FakeExperimentExecutor):
        fail = True

        def enqueue(self, **kwargs):
            result = super().enqueue(**kwargs)
            if self.fail:
                raise OSError('Synthetic lost acknowledgement')
            return result

    executor = LostAck()
    actual.service.executor = executor
    assert actual.service.dispatch_outbox()['sent'] == 0
    assert len(executor.deliveries) == 1
    with actual.factory() as session:
        row = session.get(models.ResearchExperimentReservation, uuid.UUID(reservation_id))
        assert row.state == 'uncertain'
        delivery = session.scalar(select(models.ResearchExperimentOutbox.delivery_id))
    executor.fail = False
    assert actual.service.dispatch_outbox(retry_uncertain=True)['sent'] == 1
    assert len(executor.deliveries) == 1
    with actual.factory() as session:
        assert session.scalar(select(models.ResearchExperimentOutbox.delivery_id)) == delivery
        assert session.get(models.ResearchExperimentReservation, uuid.UUID(reservation_id)).state == 'accepted'


def test_flags_rechecked_per_outbox_row_after_first_acceptance(actual):
    for actor in (actual.user, actual.other):
        dispatch(actual, user=actor)

    class Pause(FakeExperimentExecutor):
        def enqueue(self, **kwargs):
            result = super().enqueue(**kwargs)
            actual.state['dispatch_enabled'] = False
            return result

    actual.service.executor = Pause()
    with pytest.raises(ResearchExperimentError):
        actual.service.dispatch_outbox()
    assert len(actual.service.executor.deliveries) == 1
    with actual.factory() as session:
        assert sorted(session.scalars(select(models.ResearchExperimentOutbox.state))) == ['pending', 'sent']


def test_closing_gate_refuses_revocation_from_final_source_callback(actual, monkeypatch):
    experiment = dispatch(actual)
    original = actual.service._verify
    changed = {'value': False}

    def revoke(**kwargs):
        original(**kwargs)
        if not changed['value']:
            changed['value'] = True
            with actual.factory.begin() as session:
                session.get(models.AppUser, actual.user.id).status = 'suspended'

    monkeypatch.setattr(actual.service, '_verify', revoke)
    assert actual.service.dispatch_outbox()['sent'] == 0
    assert changed['value'] and not actual.service.executor.deliveries
    with actual.factory() as session:
        assert session.get(models.ResearchExperimentReservation, uuid.UUID(experiment['dispatch']['reservation_id'])).state == 'uncertain'


def test_lost_activation_commit_ack_replays_immutable_candidate(actual, monkeypatch):
    original = actual.service._transaction
    changed = {'value': False}

    @contextmanager
    def lose_ack():
        with original() as session:
            yield session
            activated = any(isinstance(item, models.ResearchExperimentOperation) and item.kind == 'create'
                and item.state == 'committed' for item in session.identity_map.values())
        if activated and not changed['value']:
            changed['value'] = True
            raise OperationalError('Synthetic COMMIT acknowledgement lost', {}, None)

    monkeypatch.setattr(actual.service, '_transaction', lose_ack)
    request = actual.request()
    first = actual.service.invoke('create', request, actual.user)
    assert changed['value'] and first['operation']['state'] == 'ready'
    second = actual.service.invoke('create', request, actual.user)
    assert second['experiment']['proposal_revision_id'] == first['experiment']['proposal_revision_id']
    with actual.factory() as session:
        assert len(list(session.scalars(select(models.ResearchExperimentRevision)))) == 1


def test_prepared_source_and_native_retirement_guard_are_serialized(actual, monkeypatch):
    original = actual.exporter.freeze
    ready, release = threading.Event(), threading.Event()

    def wait(**kwargs):
        ready.set()
        assert release.wait(timeout=15)
        return original(**kwargs)

    monkeypatch.setattr(actual.exporter, 'freeze', wait)
    request = actual.request()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(actual.service.invoke, 'create', request, actual.user)
        assert ready.wait(timeout=15)
        with actual.factory.begin() as session:
            row = session.get(models.ResearchInvestigation, uuid.UUID(request['investigation_id']))
            row.status, row.updated_at = 'archived', datetime.now(timezone.utc) - timedelta(days=400)
        try:
            assert actual.investigations.retire_expired(retention_days=1, user=actual.admin, dry_run=False)['retired_count'] == 0
            with pytest.raises(DBAPIError), actual.factory.begin() as session:
                session.execute(text("UPDATE research_investigation SET status='retired' WHERE id=:id"), {'id': request['investigation_id']})
        finally:
            release.set()
        with pytest.raises(ResearchExperimentError):
            future.result(timeout=20)
    with actual.factory() as session:
        assert session.scalar(select(models.ResearchExperimentOperation.state)) in {'prepared', 'unavailable', 'uncertain'}


def test_populated_downgrade_is_rejected_without_data_loss(actual, isolated):
    experiment = actual.create()
    pg.alembic(isolated, 'downgrade', '20261019_0019', succeeds=False)
    assert actual.service.invoke('get', actual.address(experiment), actual.user)['experiment']['proposal'] == experiment['proposal']
