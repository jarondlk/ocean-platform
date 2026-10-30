"""C26 actual C17/C20/C21/C22/C25 composition on an explicit disposable PG.

The application journal and owner/site fences are native PostgreSQL. The output
port retains only explicitly seeded synthetic bytes in its own SQLite journal;
this is not physical execution, a production worker, or scientific approval.
"""
import json
import os
import uuid

import pytest

from api.investigation_routes import investigation_response
from api.research_evidence_routes import research_evidence_response
from tests import experiment_execution_postgres_support as pg
from tests.experiment_workspace_support import DurableSyntheticExecutionPort
from tests.system_acceptance_support import make_system_acceptance_fixture

disposable_database, isolated = pg.disposable_database, pg.isolated
pytestmark = pytest.mark.skipif(os.environ.get('RUN_C23_POSTGRES_INTEGRATION') != '1',
    reason='requires explicitly verified owned C23 PostgreSQL; starts no service')


@pytest.fixture
def actual(isolated, tmp_path, monkeypatch):
    for name in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS', 'ENABLE_V1_RESEARCH_CONTROLLER'):
        monkeypatch.setenv(name, 'true')
    monkeypatch.setenv('DEPLOYMENT_ENV', 'test')
    pg.alembic(isolated, 'upgrade', 'head')
    return make_system_acceptance_fixture(isolated['engine'], tmp_path)


def test_native_pg_foreign_attachment_run_answer_revision_and_historical_reopen(actual):
    context = actual.context()
    approved, request, execution, raw = actual.experiment(context, completed=True)
    item = execution['artifacts'][0]
    attach = {'investigation_id': context['investigation']['id'],
        'expected_revision_id': context['context']['id'], 'idempotency_key': str(uuid.uuid4()),
        'change': {'op': 'attach', 'reference': item['attachment_reference']}}
    response = investigation_response(actual.user, actual.retained.service, 'context/change', attach)
    assert response.status_code == 200, response.body
    attached = {**context, **json.loads(response.body)}
    replay = investigation_response(actual.user, actual.retained.service, 'context/change', attach)
    assert replay.status_code == 200 and json.loads(replay.body)['context'] == attached['context']
    assert attached['context']['resolution'][0]['status'] == 'available'

    _, run = actual.finish_run(attached)
    verified = actual.evidence.ensure_retained(run['id'], 1, actual.user)
    assert verified.receipts[0].counts[0].value == 4
    assert not verified.attached_receipts
    assert any('not independently verified scientific evidence' in value for value in verified.unresolved_work)
    answer = actual.answer(run)['answer']
    assert answer['scientific_verification'] == 'not_independently_verified'
    assert answer['model_used'] is False

    native = verified.receipts[0]
    combined_request = {'investigation_id': attached['investigation']['id'],
        'expected_revision_id': attached['context']['id'], 'idempotency_key': str(uuid.uuid4()),
        'change': {'op': 'attach', 'reference': native.attachment_reference.model_dump(mode='json')}}
    combined = investigation_response(actual.user, actual.retained.service,
        'context/change', combined_request)
    assert combined.status_code == 200, combined.body
    attached = {**attached, **json.loads(combined.body)}
    assert len(attached['context']['attachments']) == 2
    assert all(value['status'] == 'available' for value in attached['context']['resolution'])

    # C22 resolves the new frozen context under the same site lock. A nested
    # transaction here would hit the deliberately bounded native lock timeout.
    revision = actual.experiments.service.invoke('revise', {
        **actual.binding(attached), 'experiment_id': approved['id'],
        'expected_version': approved['version'],
        'expected_proposal_revision_id': approved['proposal_revision_id'],
        'proposal': {**approved['proposal'], 'method': 'New context needs fresh review'},
        'idempotency_key': str(uuid.uuid4())}, actual.user)['experiment']
    assert revision['version'] == approved['version'] + 1
    assert revision['approval']['status'] == 'stale'
    history = actual.experiments.service.invoke('get', {'experiment_id': approved['id'],
        'proposal_revision_id': approved['proposal_revision_id']}, actual.user)['experiment']
    assert history['hashes'] == approved['hashes']
    historical_request = actual.experiments.decision(history)
    historical_request.pop('idempotency_key')
    old_execution = actual.workspace.invoke('status', historical_request, actual.user)['execution']
    assert old_execution == execution
    downloaded = actual.workspace.invoke('artifact', {**historical_request,
        'execution_id': execution['id'], 'artifact_id': item['id'],
        'expected_sha256': item['sha256']}, actual.user)
    assert downloaded['artifact']['scientific_approval'] == 'not_independently_verified'
    assert downloaded['artifact']['authority'] == 'experimental'
    assert len(raw) == downloaded['artifact']['size_bytes']

    # Reconstruct the durable external store; historical context still resolves
    # using retained immutable pins rather than in-memory provider state.
    reopened = DurableSyntheticExecutionPort(experiments=actual.experiments.service,
        path=actual.port.path)
    assert reopened.artifact_locator(str(actual.user.id), item['attachment_reference'])
    old_context = actual.retained.service.invoke('context/get', {
        'investigation_id': attached['investigation']['id'],
        'revision_id': attached['context']['id']}, actual.user)['context']
    assert old_context['resolution'][0]['status'] == 'available'
    receipt = verified.receipts[0]
    evidence = actual.evidence.invoke('open', {'receipt_id': receipt.id,
        'expected_sha256': receipt.sha256}, actual.user)['receipt']
    assert evidence['sha256'] == receipt.sha256
    assert actual.workspace.capability(actual.user)['capability']['start_enabled'] is False
    assert not actual.experiments.executor.deliveries


def test_native_pg_native_first_foreign_second_then_new_run_and_answer(actual, monkeypatch):
    monkeypatch.setenv('ENABLE_V1_EVIDENCE', 'true')
    context = actual.context()
    _, _, execution, _ = actual.experiment(context, completed=True)
    _, original_run = actual.finish_run(context)
    original = actual.evidence.ensure_retained(original_run['id'], 1, actual.user).receipts[0]
    for reference in (original.attachment_reference.model_dump(mode='json'),
            execution['artifacts'][0]['attachment_reference']):
        changed = actual.retained.service.invoke('context/change', {
            'investigation_id': context['investigation']['id'],
            'expected_revision_id': context['context']['id'], 'idempotency_key': str(uuid.uuid4()),
            'change': {'op': 'attach', 'reference': reference}}, actual.user)
        context = {**context, **changed}
    _, current_run = actual.finish_run(context)
    listing = research_evidence_response(actual.user, actual.evidence, actual.answers,
        actual.retained.service, 'evidence', 'list', {**actual.runs.address(current_run), 'input_version': 1})
    assert listing.status_code == 200, listing.body
    receipts = json.loads(listing.body)['items']
    assert len(receipts) == 2
    assert next(row for row in receipts if row['id'] == original.id) == original.model_dump(mode='json')
    current = next(row for row in receipts if row['run_id'] == current_run['id'])
    assert current['binding']['revision_id'] == context['context']['id']
    assert current['counts'][0]['value'] == 4
    answer = actual.answer(current_run)['answer']
    assert current['id'] in answer['receipt_ids']
    assert set(answer['receipt_ids']) <= {row['id'] for row in receipts}
    assert answer['scientific_verification'] == 'not_independently_verified'
    assert any('not independently verified scientific evidence' in item for item in answer['qualifications'])
    assert execution['artifacts'][0]['id'] not in answer['receipt_ids']
