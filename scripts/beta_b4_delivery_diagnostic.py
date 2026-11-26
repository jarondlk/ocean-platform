"""Compare one beta Research delivery with Cloud Tasks without changing either.

Run with the existing beta observer database binding and a principal that can
read the exact task in FULL view. A missing task is an observation, not proof
of retry exhaustion, model shutdown, or permission to create a replacement.
"""

import argparse
from hashlib import sha256
import json
import os
import uuid

from orchestration.cloud_research_dispatch import CloudResearchQueue
from orchestration.research_answers import TERMINAL as ANSWER_TERMINAL
from orchestration.research_runs import TERMINAL as RUN_TERMINAL
from scripts import beta_b1_diagnostic as observer
from scripts.beta_b1_dispatch import SETTINGS


KIND = {
    'run': ('research_run', 'research_run_outbox', 'research_run_step', 'run_id',
            'o.input_version = h.input_version', RUN_TERMINAL | {'awaiting_clarification', 'awaiting_approval'}),
    'answer': ('research_answer_job', 'research_answer_outbox', 'research_answer_step', 'job_id',
               'TRUE', ANSWER_TERMINAL),
}
VERSION = 'ocean-beta-b4-delivery-diagnostic-v1'


def snapshot(connection, kind, work_id):
    head, outbox, steps, key, current_input, _ = KIND[kind]
    # Table and column names come only from the two fixed message kinds.
    query = f"""SELECT h.status, h.version, h.input_version, h.lease_epoch,
        h.lease_until, h.active_started_at, h.cancellation_requested,
        o.delivery_id, o.state, o.sent_at, o.attempts,
        (SELECT count(*) FROM public.{steps} s
         WHERE s.{key} = h.id AND s.kind = 'model' AND s.state = 'prepared'),
        transaction_timestamp()
        FROM public.{head} h
        LEFT JOIN public.{outbox} o ON o.{key} = h.id AND ({current_input})
        WHERE h.id = %s::uuid"""
    with connection, connection.cursor() as cursor:
        cursor.execute(observer.IDENTITY)
        if cursor.fetchone() != ('ocean_v1_research_controller', 'ocean_v1_beta', 'on', 'repeatable read'):
            raise ValueError('Wrong read-only database identity')
        cursor.execute(query, (work_id,))
        row, = cursor.fetchall()
    return row[:-1], row[-1]


def task_state(session, task):
    response = session.get('https://cloudtasks.googleapis.com/v2/' + task['name'],
                           params={'responseView': 'FULL'}, timeout=10, allow_redirects=False)
    if response.status_code == 404:
        return 'missing', None
    if response.status_code != 200:
        return 'unverified', None
    observed = response.json()
    expected = task['httpRequest']
    http = observed.get('httpRequest', {})
    if (observed.get('name') != task['name'] or observed.get('dispatchDeadline') != task['dispatchDeadline']
            or any(http.get(k) != expected[k] for k in ('httpMethod', 'url', 'body', 'oidcToken'))
            or {k.lower(): v for k, v in http.get('headers', {}).items()}.get('content-type') != 'application/json'):
        return 'binding_mismatch', None
    return 'present', observer.integer(observed.get('dispatchCount', 0), 2**31 - 1)


def inspect(connection, queue_session, *, kind, work_id):
    if type(work_id) is not str or str(uuid.UUID(work_id)) != work_id:
        raise ValueError('Canonical work UUID required')
    _, _, _, key, _, settled = KIND[kind]
    before, _ = snapshot(connection, kind, work_id)
    status, _, _, _, lease, started, cancelled, delivery, state, sent_at, attempts, prepared = before
    if (status not in settled | {'queued', 'running'} or type(cancelled) is not bool
            or state not in {None, 'pending', 'sent'} or (state == 'sent') != (sent_at is not None)
            or (delivery is None) != (state is None)):
        raise ValueError('Inconsistent delivery state')
    task_digest = None
    provider, provider_dispatches = 'no_outbox', None
    if delivery is not None:
        task = CloudResearchQueue(settings=SETTINGS, kind=kind).task(delivery_id=str(delivery), **{key: work_id})
        task_digest = sha256(task['name'].encode()).hexdigest()
        provider, provider_dispatches = task_state(queue_session, task)
    after, now = snapshot(connection, kind, work_id)
    if before != after:
        disposition = 'snapshot_changed'
    elif provider in {'unverified', 'binding_mismatch'}:
        disposition = 'provider_readback_required'
    elif status in settled and lease is None and started is None:
        disposition = 'durable_outcome_recorded'
    elif lease is not None and lease > now:
        disposition = 'lease_active'
    elif status in settled or cancelled or provider == 'no_outbox':
        disposition = 'operator_reconciliation_required'
    elif provider == 'present':
        disposition = 'canonical_task_present'
    elif state == 'pending':
        disposition = 'pending_outbox_requires_observation'
    else:
        disposition = 'sent_task_missing_requires_reconciliation'
    return {'version': VERSION, 'project': observer.PROJECT, 'kind': kind, 'captured_utc': now.isoformat(),
            'disposition': disposition, 'work_status': status, 'outbox_state': state,
            'outbox_attempts': attempts, 'prepared_model_steps': prepared,
            'canonical_task_sha256': task_digest, 'task_readback': provider, 'provider_dispatches': provider_dispatches,
            'lease_fields_closed': lease is None and started is None,
            'safe_to_automatically_replay': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', required=True, choices=tuple(KIND))
    parser.add_argument('--work-id', required=True, help='Exact owner-visible run or answer job UUID')
    args = parser.parse_args()
    try:
        from google.auth import default
        from google.auth.transport.requests import AuthorizedSession
        import psycopg2

        settings = observer.configuration(os.environ)
        settings['application_name'] = 'ocean-beta-b4-delivery-diagnostic'
        connection = psycopg2.connect(**settings)
        try:
            connection.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
            credentials, _ = default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            with AuthorizedSession(credentials) as queue_session:
                report = inspect(connection, queue_session, kind=args.kind, work_id=args.work_id)
        finally:
            connection.close()
        print(json.dumps(report, sort_keys=True))
        return 0 if report['disposition'] in {'durable_outcome_recorded', 'canonical_task_present'} else 3
    except Exception:
        print(json.dumps({'version': VERSION, 'disposition': 'readback_failed'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
