from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest

from orchestration.cloud_research_dispatch import CloudResearchQueue
from scripts import beta_b4_delivery_diagnostic as diagnostic


NOW = datetime(2026, 11, 26, tzinfo=timezone.utc)
WORK = str(uuid.uuid4())
DELIVERY = uuid.uuid4()


@pytest.mark.parametrize('kind', ['run', 'answer'])
@pytest.mark.parametrize('http, head, outbox, lease, disposition', [
    (404, 'queued', 'sent', None, 'sent_task_missing_requires_reconciliation'),
    (404, 'running', 'sent', -1, 'sent_task_missing_requires_reconciliation'),
    (404, 'queued', 'pending', None, 'pending_outbox_requires_observation'),
    (404, 'running', 'sent', 10, 'lease_active'),
    (404, 'completed', 'sent', None, 'durable_outcome_recorded'),
    (200, 'queued', 'sent', None, 'canonical_task_present'),
    (403, 'queued', 'sent', None, 'provider_readback_required'),
    (503, 'queued', 'sent', None, 'provider_readback_required'),
])
def test_readback_holds_unresolved_work(monkeypatch, kind, http, head, outbox, lease, disposition):
    key = 'run_id' if kind == 'run' else 'job_id'
    task = CloudResearchQueue(settings=diagnostic.SETTINGS, kind=kind).task(delivery_id=str(DELIVERY), **{key: WORK})
    expiry = None if lease is None else NOW + timedelta(seconds=lease)
    head_row = (head, 2, 1, 1, expiry, NOW if lease is not None else None, False, DELIVERY,
                outbox, NOW if outbox == 'sent' else None, 1, 1)
    monkeypatch.setattr(diagnostic, 'snapshot', lambda *_: (head_row, NOW))

    def read(url, **kwargs):
        assert url == 'https://cloudtasks.googleapis.com/v2/' + task['name']
        assert kwargs == {'params': {'responseView': 'FULL'}, 'timeout': 10, 'allow_redirects': False}
        return SimpleNamespace(status_code=http, json=lambda: {**task, 'dispatchCount': 2})

    report = diagnostic.inspect(None, SimpleNamespace(get=read), kind=kind, work_id=WORK)
    assert report['disposition'] == disposition
    assert report['safe_to_automatically_replay'] is False
    assert report['prepared_model_steps'] == 1
    assert report['lease_fields_closed'] == (lease is None)
    assert report['provider_dispatches'] == (2 if http == 200 else None)
    assert str(DELIVERY) not in repr(report) and WORK not in repr(report)


def test_changed_snapshot_takes_precedence_over_missing_task(monkeypatch):
    head = ('queued', 1, 1, 0, None, None, False, DELIVERY, 'sent', NOW, 1, 0)
    states = iter((head, ('completed', 2, *head[2:])))
    monkeypatch.setattr(diagnostic, 'snapshot', lambda *_: (next(states), NOW))
    queue = SimpleNamespace(get=lambda *_, **__: SimpleNamespace(status_code=404))
    assert diagnostic.inspect(None, queue, kind='run', work_id=WORK)['disposition'] == 'snapshot_changed'


def test_successful_but_incomplete_task_readback_is_unverified():
    task = CloudResearchQueue(settings=diagnostic.SETTINGS, kind='answer').task(delivery_id=str(DELIVERY), job_id=WORK)
    altered = {**task, 'httpRequest': {**task['httpRequest'], 'body': 'unexpected'}}
    queue = SimpleNamespace(get=lambda *_, **__: SimpleNamespace(status_code=200, json=lambda: altered))
    assert diagnostic.task_state(queue, task) == ('binding_mismatch', None)
