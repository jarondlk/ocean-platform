"""C22 actual frozen exports, owner review and fake-only durable dispatch."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import uuid

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import OperationalError

from db.app_models import (
    AppBase, AppUser, ResearchExperimentApproval, ResearchExperimentOperation,
    ResearchExperimentOutbox, ResearchExperimentReservation, ResearchExperimentRevision,
    ResearchInvestigation,
)
from orchestration.research_experiments import FakeExperimentExecutor, ResearchExperimentError
from tests.research_experiment_support import make_experiment_fixture


@pytest.fixture(scope='module')
def retained(tmp_path_factory):
    directory = tmp_path_factory.mktemp('c22-store')
    engine = create_engine('sqlite+pysqlite:///' + str(directory / 'app.sqlite'))

    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

    AppBase.metadata.create_all(engine)
    actual = make_experiment_fixture(engine, directory)
    yield actual
    engine.dispose()


@pytest.fixture
def actual(retained, monkeypatch):
    for name in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS'):
        monkeypatch.setenv(name, 'true')
    retained.state.update(enabled=True, dispatch_enabled=True)
    for denied in retained.retained.policy.values():
        denied.clear()
    yield retained


def approved(fixture, *, user=None):
    actor = user or fixture.user
    experiment = fixture.create(user=actor)
    return fixture.service.invoke('approve', fixture.decision(experiment), actor)['experiment']


def test_actual_export_review_exact_hashes_private_bytes_and_no_execution(actual, tmp_path):
    request = actual.request()
    sentinel = tmp_path / 'must-not-exist'
    request['proposal']['python_code'] = f'from pathlib import Path\nPath({str(sentinel)!r}).write_text("bad")\n'
    response = actual.service.invoke('create', request, actual.user)
    experiment = response['experiment']
    assert response['operation']['state'] == 'ready'
    assert experiment['binding'] == {key: request[key] for key in experiment['binding']}
    assert experiment['authority'] == 'experimental' and experiment['execution_performed'] is False
    assert experiment['scientific_approval'] == 'not_independently_verified'
    assert experiment['manifest']['sources']['datasets'][0]['publication']['test_only'] is True
    assert not sentinel.exists()
    assert actual.service.invoke('get', actual.address(experiment), actual.user)['experiment'] == experiment
    def contains_private_bytes(value):
        if isinstance(value, dict):
            return any(key in {'content', 'bytes', 'base64'} or contains_private_bytes(item) for key, item in value.items())
        return isinstance(value, list) and any(contains_private_bytes(item) for item in value)
    assert 'files' not in response and not contains_private_bytes(response)


def test_same_key_replays_exact_operation_different_request_or_action_conflicts(actual):
    request = actual.request()
    response = actual.service.invoke('create', request, actual.user)
    assert actual.service.invoke('create', request, actual.user) == response
    changed = deepcopy(request)
    changed['proposal']['question'] += ' changed'
    with pytest.raises(ResearchExperimentError) as failure:
        actual.service.invoke('create', changed, actual.user)
    assert failure.value.code == 'conflict'
    decision = actual.decision(response['experiment'])
    decision['idempotency_key'] = request['idempotency_key']
    with pytest.raises(ResearchExperimentError, match='changed'):
        actual.service.invoke('approve', decision, actual.user)


def test_revision_preserves_history_and_invalidates_exact_old_approval(actual):
    initial = approved(actual)
    request = {**initial['binding'], 'proposal': deepcopy(initial['proposal']),
        'experiment_id': initial['id'], 'expected_version': initial['version'],
        'expected_proposal_revision_id': initial['proposal_revision_id'], 'idempotency_key': str(uuid.uuid4())}
    request['proposal']['python_code'] += '# changed code requires new approval\n'
    updated = actual.service.invoke('revise', request, actual.user)['experiment']
    assert updated['version'] == initial['version'] + 1
    assert updated['proposal_revision_id'] != initial['proposal_revision_id']
    assert updated['approval']['status'] == 'stale' and updated['dispatch']['eligible'] is False
    assert updated['hashes']['code_sha256'] != initial['hashes']['code_sha256']
    old = actual.service.invoke('get', {**actual.address(initial), 'proposal_revision_id': initial['proposal_revision_id']}, actual.user)['experiment']
    assert old['proposal'] == initial['proposal'] and old['hashes'] == initial['hashes']
    with pytest.raises(ResearchExperimentError) as failure:
        actual.service.invoke('dispatch', actual.decision(initial), actual.user)
    assert failure.value.code == 'conflict'


@pytest.mark.parametrize('actor_name', ['other', 'admin'])
def test_admin_and_other_owner_cannot_read_approve_dispatch(actual, actor_name):
    initial = actual.create()
    actor = getattr(actual, actor_name)
    for name, request in [('get', actual.address(initial)), ('approve', actual.decision(initial)), ('dispatch', actual.decision(initial))]:
        with pytest.raises(ResearchExperimentError) as failure:
            actual.service.invoke(name, request, actor)
        assert failure.value.status_code == 404


def test_current_owner_status_and_permission_epoch_rechecked(actual):
    initial = actual.create()
    with actual.factory.begin() as session:
        session.get(AppUser, actual.user.id).status = 'suspended'
    try:
        with pytest.raises(ResearchExperimentError) as failure:
            actual.service.invoke('get', actual.address(initial), actual.user)
        assert failure.value.status_code == 403
    finally:
        with actual.factory.begin() as session:
            session.get(AppUser, actual.user.id).status = 'active'


def test_missing_publication_policy_leaves_conservative_prepared_protection(actual):
    policy, actual.exporter.publication_policy = actual.exporter.publication_policy, None
    try:
        request = actual.request()
        response = actual.service.invoke('create', request, actual.user)
        assert response['experiment'] is None and response['operation']['state'] == 'unavailable'
        with actual.factory() as session:
            operation = session.get(ResearchExperimentOperation, uuid.UUID(response['operation']['id']))
            references = json.loads(operation.references_json)
            assert references and all(actual.retained.store.lifecycle()['references'][item['reference']] == item['snapshot_id'] for item in references)
        actual.exporter.publication_policy = policy
        retry = actual.service.invoke('retry', {'operation_id': response['operation']['id']}, actual.user)
        assert retry['operation']['state'] == 'ready' and retry['experiment'] is not None
    finally:
        actual.exporter.publication_policy = policy


def test_changed_context_requires_new_review_but_old_history_reopens(actual):
    initial = approved(actual)
    actual.investigations.invoke('context/change', {'investigation_id': initial['binding']['investigation_id'],
        'expected_revision_id': initial['binding']['context_revision_id'], 'idempotency_key': str(uuid.uuid4()),
        'change': {'op': 'attach', 'reference': {'kind': 'catalogue', 'snapshot_id': initial['binding']['snapshot_id'],
            'id': actual.retained.dataset_ids['ctd']}}}, actual.user)
    reopened = actual.service.invoke('get', actual.address(initial), actual.user)['experiment']
    assert reopened['proposal'] == initial['proposal'] and not reopened['dispatch']['eligible']
    with pytest.raises(ResearchExperimentError) as failure:
        actual.service.invoke('dispatch', actual.decision(initial), actual.user)
    assert failure.value.code == 'conflict'


def test_paused_flags_preserve_history_and_existing_approval_key(actual):
    initial = actual.create()
    decision = actual.decision(initial)
    saved = actual.service.invoke('approve', decision, actual.user)
    actual.state.update(enabled=False, dispatch_enabled=False)
    assert actual.service.invoke('approve', decision, actual.user)['experiment']['proposal'] == saved['experiment']['proposal']
    assert actual.service.invoke('get', actual.address(initial), actual.user)['experiment']['proposal'] == initial['proposal']
    with pytest.raises(ResearchExperimentError):
        actual.service.invoke('approve', actual.decision(initial), actual.user)


def test_current_publication_withdrawal_or_source_policy_change_denies_new_decision(actual):
    initial = actual.create()
    decision = actual.decision(initial)
    policy = actual.exporter.publication_policy
    actual.exporter.publication_policy = None
    try:
        with pytest.raises(ResearchExperimentError) as failure:
            actual.service.invoke('approve', decision, actual.user)
        assert failure.value.status_code == 403
    finally:
        actual.exporter.publication_policy = policy
    actual.retained.policy[initial['binding']['snapshot_id']].add(actual.retained.dataset_ids['ctd'])
    with pytest.raises(ResearchExperimentError) as failure:
        actual.service.invoke('approve', decision, actual.user)
    assert failure.value.status_code == 403


def test_sql_blob_tamper_rejected_before_approval(actual):
    initial = actual.create()
    with actual.factory() as session:
        file = session.execute(text('SELECT sha256 FROM research_experiment_revision_file WHERE revision_id=:id LIMIT 1'),
            {'id': initial['proposal_revision_id'].replace('-', '')}).scalar_one()
    with actual.factory.begin() as session:
        original = session.execute(text('SELECT content FROM research_experiment_input_blob WHERE sha256=:hash'), {'hash': file}).scalar_one()
        session.execute(text('UPDATE research_experiment_input_blob SET content=:content WHERE sha256=:hash'), {'hash': file, 'content': b'x' * len(original)})
    try:
        with pytest.raises(ResearchExperimentError) as failure:
            actual.service.invoke('approve', actual.decision(initial), actual.user)
        assert failure.value.code == 'integrity_error'
    finally:
        with actual.factory.begin() as session:
            session.execute(text('UPDATE research_experiment_input_blob SET content=:content WHERE sha256=:hash'), {'hash': file, 'content': original})


def test_archive_retirement_retains_experiments_even_flags_disabled(actual):
    initial = actual.create()
    with actual.factory.begin() as session:
        row = session.get(ResearchInvestigation, uuid.UUID(initial['binding']['investigation_id']))
        row.status, row.updated_at = 'archived', datetime.now(timezone.utc) - timedelta(days=400)
    actual.state['enabled'] = False
    result = actual.investigations.retire_expired(retention_days=1, user=actual.admin, dry_run=False)
    assert result['retired_count'] == 0
    assert actual.service.invoke('get', actual.address(initial), actual.user)['experiment']['proposal'] == initial['proposal']


def test_events_and_owner_list_use_real_consecutive_history(actual):
    initial = approved(actual)
    response = actual.service.invoke('events', actual.address(initial), actual.user)
    assert [item['cursor'] for item in response['items']] == list(range(1, response['latest_event_cursor'] + 1))
    listing = actual.service.invoke('list', {'investigation_id': initial['binding']['investigation_id'], 'limit': 1}, actual.user)
    assert [item['id'] for item in listing['items']] == [initial['id']]


def test_commit_ack_loss_reconciles_same_candidate_without_duplicate_revision(actual, monkeypatch):
    original = actual.service._transaction
    failed = {'value': False}

    @contextmanager
    def lose_ack():
        with original() as session:
            yield session
            activated = any(isinstance(item, ResearchExperimentOperation) and item.kind == 'create'
                and item.state == 'committed' for item in session.identity_map.values())
        if activated and not failed['value']:
            failed['value'] = True
            raise OperationalError('synthetic lost acknowledgement', {}, None)

    monkeypatch.setattr(actual.service, '_transaction', lose_ack)
    request = actual.request()
    response = actual.service.invoke('create', request, actual.user)
    assert failed['value']
    assert response['operation']['state'] == 'ready'
    assert actual.service.invoke('create', request, actual.user)['experiment']['proposal_revision_id'] == response['experiment']['proposal_revision_id']


def test_fake_delivery_uncertainty_keeps_capacity_and_stable_identity(actual):
    # Separate owner avoids reservations retained by any previous test.
    initial = approved(actual, user=actual.other)
    request = actual.decision(initial)
    response = actual.service.invoke('dispatch', request, actual.other)
    reservation_id = response['experiment']['dispatch']['reservation_id']

    class LostAck(FakeExperimentExecutor):
        def enqueue(self, **kwargs):
            super().enqueue(**kwargs)
            raise OSError('Synthetic acknowledgement lost after acceptance')

    executor, actual.service.executor = actual.service.executor, LostAck()
    try:
        assert actual.service.dispatch_outbox()['sent'] == 0
        assert len(actual.service.executor.deliveries) == 1
        assert actual.service.invoke('dispatch', request, actual.other)['experiment']['dispatch']['reservation_id'] == reservation_id
        with actual.factory() as session:
            reservation = session.get(ResearchExperimentReservation, uuid.UUID(reservation_id))
            outbox = session.scalar(select(ResearchExperimentOutbox).where(ResearchExperimentOutbox.reservation_id == reservation.id))
            assert reservation.state == outbox.state == 'uncertain'
            stable_delivery = outbox.delivery_id
        actual.service.executor = executor
        assert actual.service.dispatch_outbox(retry_uncertain=True)['sent'] == 1
        with actual.factory() as session:
            assert session.scalar(select(ResearchExperimentOutbox.delivery_id).where(ResearchExperimentOutbox.reservation_id == uuid.UUID(reservation_id))) == stable_delivery
        envelope = actual.service.load_execution_envelope(reservation_id, user=actual.other)
        assert envelope['metadata']['execution_performed'] is False and envelope['files']
    finally:
        actual.service.executor = executor


def test_capacity_counts_accepted_reservation_one_per_owner_two_globally(actual):
    first = approved(actual)
    actual.service.invoke('dispatch', actual.decision(first), actual.user)
    second_same_owner = approved(actual)
    with pytest.raises(ResearchExperimentError) as failure:
        actual.service.invoke('dispatch', actual.decision(second_same_owner), actual.user)
    assert failure.value.code == 'capacity_unavailable'
    admin = approved(actual, user=actual.admin)
    with pytest.raises(ResearchExperimentError) as failure:
        actual.service.invoke('dispatch', actual.decision(admin), actual.admin)
    assert failure.value.code == 'capacity_unavailable'


def test_orm_immutable_approval_and_frozen_revision(actual):
    initial = approved(actual)
    for model, attribute, value in [(ResearchExperimentRevision, 'proposal_json', '{}'), (ResearchExperimentApproval, 'request_json', '{}')]:
        with pytest.raises(ValueError), actual.factory.begin() as session:
            query = select(model).where(model.experiment_id == uuid.UUID(initial['id']))
            setattr(session.scalar(query), attribute, value)


def test_late_failed_duplicate_preserves_its_saved_revision_after_head_advanced(actual, monkeypatch):
    request = actual.request()
    original = actual.exporter.freeze
    observed = {}

    def a_second_worker_finishes_first(**kwargs):
        if observed:
            return original(**kwargs)
        observed['entered'] = True
        with actual.factory() as session:
            operation = session.scalar(select(ResearchExperimentOperation).where(
                ResearchExperimentOperation.idempotency_key == request['idempotency_key']))
            operation_id = str(operation.id)
        initial = actual.service.invoke('retry', {'operation_id': operation_id}, actual.user)['experiment']
        observed['original_revision'] = initial['proposal_revision_id']
        revised_request = {**initial['binding'], 'proposal': deepcopy(initial['proposal']),
            'experiment_id': initial['id'], 'expected_version': initial['version'],
            'expected_proposal_revision_id': initial['proposal_revision_id'], 'idempotency_key': str(uuid.uuid4())}
        revised_request['proposal']['python_code'] += '# A later owner revision must not replace the first operation result\n'
        revised = actual.service.invoke('revise', revised_request, actual.user)['experiment']
        observed['new_revision'] = revised['proposal_revision_id']
        raise OSError('The older duplicate worker failed after another worker committed')

    monkeypatch.setattr(actual.exporter, 'freeze', a_second_worker_finishes_first)
    response = actual.service.invoke('create', request, actual.user)
    assert observed['original_revision'] != observed['new_revision']
    assert response['operation']['result_revision_id'] == observed['original_revision']
    assert response['experiment']['proposal_revision_id'] == observed['original_revision']
