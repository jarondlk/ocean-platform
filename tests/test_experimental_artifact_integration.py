"""Actual C17/C21/C22/C25 composition; synthetic bytes, no execution authority."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import uuid

import pytest
from sqlalchemy import create_engine, event, select

from api.investigation_routes import investigation_response
from db.app_models import AppBase, ResearchEvidenceContextDependency, ResearchInvestigation
from orchestration.experiment_artifacts import ExperimentArtifactProvider
from orchestration.experiment_workspace import ExperimentWorkspaceService
from orchestration.investigations import InvestigationError
from orchestration.research_evidence import ResearchEvidenceError, ResearchEvidenceService
from tests.experiment_workspace_support import DurableSyntheticExecutionPort
from tests.system_acceptance_support import make_system_acceptance_fixture


@pytest.fixture(scope='module')
def retained(tmp_path_factory):
    directory = tmp_path_factory.mktemp('retained-experimental-context')
    engine = create_engine('sqlite+pysqlite:///' + str(directory / 'app.sqlite'))
    @event.listens_for(engine, 'connect')
    def keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    AppBase.metadata.create_all(engine)
    fixture = make_system_acceptance_fixture(engine, directory)
    yield fixture
    engine.dispose()


@pytest.fixture
def actual(retained, monkeypatch):
    for name in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS', 'ENABLE_V1_RESEARCH_CONTROLLER'):
        monkeypatch.setenv(name, 'true')
    monkeypatch.setenv('DEPLOYMENT_ENV', 'test')
    retained.experiments.state.update(enabled=True, dispatch_enabled=True)
    for values in retained.retained.policy.values():
        values.clear()
    return retained


def seeded(fixture):
    context = fixture.context()
    experiment, request, execution, raw = fixture.experiment(context, completed=True)
    return context, experiment, request, execution, raw


def change(fixture, context, reference, *, op='attach', key=None):
    request = {'investigation_id': context['investigation']['id'],
        'expected_revision_id': context['context']['id'], 'idempotency_key': key or str(uuid.uuid4()),
        'change': {'op': op, 'reference': reference}}
    response = investigation_response(fixture.user, fixture.retained.service, 'context/change', request)
    assert response.status_code == 200, response.body
    value = json.loads(response.body)
    return {**context, **value}, request


def pins(port, artifact_id):
    with port._connection() as connection:
        return [dict(row) for row in connection.execute(
            'SELECT * FROM artifact_context_pins WHERE artifact_id=? ORDER BY id', (artifact_id,))]


def test_foreign_attachment_actual_run_evidence_native_dependency_and_exact_retry(actual):
    context, _, _, execution, _ = seeded(actual)
    item = execution['artifacts'][0]
    attached, request = change(actual, context, item['attachment_reference'])
    replay = investigation_response(actual.user, actual.retained.service, 'context/change', request)
    assert replay.status_code == 200 and json.loads(replay.body)['context'] == attached['context']
    assert len(pins(actual.port, item['id'])) == 1
    assert pins(actual.port, item['id'])[0]['state'] == 'committed'
    assert attached['context']['resolution'][0]['status'] == 'available'
    _, run = actual.finish_run(attached)
    verified = actual.evidence.ensure_retained(run['id'], 1, actual.user)
    assert verified.receipts[0].counts[0].value == 4
    assert not verified.attached_receipts  # Experimental bytes never become scientific C21 receipts.
    assert any('not independently verified scientific evidence' in value for value in verified.unresolved_work)
    assert item['attachment_reference'] in verified.anchor.frozen_context['context']['attachments']
    receipt = verified.receipts[0]
    native, _ = change(actual, attached, receipt.attachment_reference.model_dump(mode='json'))
    with actual.retained.factory() as session:
        dependencies = session.scalars(select(ResearchEvidenceContextDependency).where(
            ResearchEvidenceContextDependency.investigation_id == uuid.UUID(native['investigation']['id']))).all()
        assert any(row.receipt_id == receipt.id and row.state == 'committed' for row in dependencies)
    assert actual.workspace.capability(actual.user)['capability']['start_enabled'] is False
    assert not actual.experiments.executor.deliveries


def test_detach_reopen_and_unwired_retirement_keep_historical_external_pins(actual, monkeypatch):
    source, _, _, execution, _ = seeded(actual)
    item = execution['artifacts'][0]
    # The target owns no experiment or native evidence row; historical context
    # itself must prevent retirement after a detach and provider removal.
    target = actual.context()
    attached, _ = change(actual, target, item['attachment_reference'])
    detached, _ = change(actual, attached, item['attachment_reference'], op='detach')
    assert not detached['context']['attachments']
    reopened = DurableSyntheticExecutionPort(experiments=actual.experiments.service, path=actual.port.path)
    assert pins(reopened, item['id']) == pins(actual.port, item['id'])
    assert pins(reopened, item['id'])[0]['state'] == 'committed'
    for sql in ('DELETE FROM artifacts WHERE id=?', 'UPDATE artifacts SET bytes=X\'00\' WHERE id=?',
            'DELETE FROM artifact_locators WHERE id=?'):
        with pytest.raises(sqlite3.IntegrityError), reopened._connection() as connection:
            connection.execute(sql, (item['id'],))
    with pytest.raises(sqlite3.IntegrityError), reopened._connection() as connection:
        connection.execute('DELETE FROM artifact_context_pins WHERE artifact_id=?', (item['id'],))
    old = actual.retained.service.invoke('context/get', {'investigation_id': target['investigation']['id'],
        'revision_id': attached['context']['id']}, actual.user)
    assert old['context']['resolution'][0]['status'] == 'available'
    with actual.retained.factory.begin() as session:
        row = session.get(ResearchInvestigation, uuid.UUID(target['investigation']['id']))
        row.status, row.updated_at = 'archived', datetime.now(timezone.utc) - timedelta(days=400)
    monkeypatch.setattr(actual.retained.service, 'artifact_resolver', None)
    monkeypatch.setattr(actual.retained.service, 'evidence_protection', None)
    actual.retained.service.retire_expired(retention_days=30, user=actual.retained.admin, dry_run=False)
    with actual.retained.factory() as session:
        assert session.get(ResearchInvestigation, uuid.UUID(target['investigation']['id'])).status == 'archived'
    assert source['investigation']['id'] != target['investigation']['id']


def test_prepared_pin_survives_failed_application_phase_and_retries_exactly(actual, monkeypatch):
    context, _, _, execution, _ = seeded(actual)
    reference = execution['artifacts'][0]['attachment_reference']
    request = {'investigation_id': context['investigation']['id'], 'expected_revision_id': context['context']['id'],
        'idempotency_key': str(uuid.uuid4()), 'change': {'op': 'attach', 'reference': reference}}
    identity = actual.retained.service._prepare('context/change', request, actual.user)
    prepared = pins(actual.port, reference['id'])
    assert len(prepared) == 1 and prepared[0]['state'] == 'prepared'
    original = actual.retained.service.store.add_reference
    def unavailable(*args):
        raise OSError('explicit cross-store failure fixture')
    monkeypatch.setattr(actual.retained.service.store, 'add_reference', unavailable)
    with pytest.raises(InvestigationError):
        actual.retained.service._apply(identity, actual.user)
    assert pins(actual.port, reference['id']) == prepared
    monkeypatch.setattr(actual.retained.service.store, 'add_reference', original)
    result = actual.retained.service._apply(identity, actual.user)
    assert result['operation']['state'] == 'committed'
    assert len(pins(actual.port, reference['id'])) == 1 and pins(actual.port, reference['id'])[0]['state'] == 'committed'


@pytest.mark.parametrize('mutation', ['owner', 'snapshot', 'hash', 'safe_file', 'source_revoked'])
def test_foreign_artifact_owner_snapshot_hash_safety_and_publication_are_current(actual, monkeypatch, mutation):
    context, _, _, execution, _ = seeded(actual)
    item = execution['artifacts'][0]
    reference = dict(item['attachment_reference'])
    if mutation == 'owner':
        provider = actual.evidence.external_artifact_providers[0]
        assert provider.resolve is not None
        with actual.retained.factory() as session:
            assert provider.resolve(session, actual.retained.other, reference) is None
        return
    if mutation == 'snapshot':
        reference['snapshot_id'] = actual.retained.snapshots[1]
    elif mutation == 'hash':
        with actual.port._connection() as connection:
            connection.execute('UPDATE artifacts SET bytes=? WHERE id=?', (b'changed', item['id']))
    elif mutation == 'safe_file':
        # A matching digest cannot make an invalid JSON table safe to retain.
        request = actual.experiments.decision(actual.experiments.service.invoke('get',
            {'experiment_id': actual.port.artifact_locator(str(actual.user.id), reference).experiment_id}, actual.user)['experiment'])
        request.pop('idempotency_key')
        access = actual.workspace._access(request, actual.user)
        bad = actual.port.seed(access, state='completed', files=[('summary.json', 'application/json', b'{}')])
        reference = bad['artifacts'][0]['attachment_reference']
    else:
        actual.retained.policy[reference['snapshot_id']].add(actual.retained.dataset_ids['ctd'])
    try:
        response = investigation_response(actual.user, actual.retained.service, 'context/change', {
            'investigation_id': context['investigation']['id'], 'expected_revision_id': context['context']['id'],
            'idempotency_key': str(uuid.uuid4()), 'change': {'op': 'attach', 'reference': reference}})
        assert response.status_code != 200
        assert not pins(actual.port, reference['id'])
    finally:
        actual.retained.policy[item['attachment_reference']['snapshot_id']].clear()


def test_unknown_ambiguous_unavailable_and_reserved_receipt_identity_fail_closed(actual, monkeypatch):
    context, _, _, execution, _ = seeded(actual)
    reference = execution['artifacts'][0]['attachment_reference']
    service = actual.evidence
    assert service.resolve_attachment(actual.user, {**reference, 'id': 'unknown:artifact'}) is None
    assert service.resolve_attachment(actual.user, {**reference, 'id': 'c21:receipt:' + 'a' * 64}) is None
    with pytest.raises(ValueError):
        ExperimentArtifactProvider(workspace=ExperimentWorkspaceService(experiments=actual.experiments.service))
    ambiguous = ResearchEvidenceService(session_factory=service.session_factory, site_id=service.site_id,
        investigations=service.investigations, runs=service.runs, enabled=lambda: True,
        external_artifact_providers=(ExperimentArtifactProvider(workspace=actual.workspace), ExperimentArtifactProvider(workspace=actual.workspace)))
    assert ambiguous.resolve_attachment(actual.user, reference) is None
    monkeypatch.setattr(actual.workspace, 'enabled', lambda: False)
    assert service.resolve_attachment(actual.user, reference) is None
    # Optional unavailable execution integration leaves plain catalogue context usable.
    assert actual.context()['context']['attachments'] == []


def test_retention_ack_without_closing_authority_cannot_publish_context(actual, monkeypatch):
    context, _, _, execution, _ = seeded(actual)
    reference = execution['artifacts'][0]['attachment_reference']
    monkeypatch.setattr(actual.port, 'retain_artifact', lambda *args, **kwargs: None)
    response = investigation_response(actual.user, actual.retained.service, 'context/change', {
        'investigation_id': context['investigation']['id'], 'expected_revision_id': context['context']['id'],
        'idempotency_key': str(uuid.uuid4()), 'change': {'op': 'attach', 'reference': reference}})
    assert response.status_code != 200 and not pins(actual.port, reference['id'])
    with actual.retained.factory() as session:
        assert session.get(ResearchInvestigation, uuid.UUID(context['investigation']['id'])).head_revision_id == uuid.UUID(context['context']['id'])


def test_retained_receipt_reopen_rechecks_foreign_context_authority(actual, monkeypatch):
    context, _, _, execution, _ = seeded(actual)
    attached, _ = change(actual, context, execution['artifacts'][0]['attachment_reference'])
    _, run = actual.finish_run(attached)
    verified = actual.evidence.ensure_retained(run['id'], 1, actual.user)
    receipt = verified.receipts[0]
    address = {'receipt_id': receipt.id, 'expected_sha256': receipt.sha256}
    for attribute, unavailable in [('enabled', lambda: False),
            ('verify_artifact_retention', lambda pin: False),
            ('artifact_locator', lambda *args: None)]:
        target = actual.workspace if attribute == 'enabled' else actual.port
        with monkeypatch.context() as changed:
            changed.setattr(target, attribute, unavailable)
            for action in ('open', 'page', 'export'):
                with pytest.raises(ResearchEvidenceError) as denied:
                    actual.evidence.invoke(action, address, actual.user)
                assert denied.value.status_code in {403, 503}
        opened = actual.evidence.invoke('open', address, actual.user)['receipt']
        assert opened['sha256'] == receipt.sha256
