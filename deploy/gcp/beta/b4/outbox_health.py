"""Read the two current Research outboxes using one counts-only SQL snapshot."""

from contextlib import closing
from datetime import datetime, timezone
import json
import os
import sys
from urllib.request import Request, urlopen

from scripts import beta_b1_diagnostic as observer


VERSION = 'ocean-beta-b4-outbox-health-v1'
PENDING_SECONDS = 600
SENT_SECONDS = 3900
FIELDS = ('active', 'aged_pending', 'aged_sent', 'missing_outbox', 'inconsistent_outbox')
TABLES = {
    'explorations': ('research_run', 'research_run_outbox',
                     'o.run_id = h.id AND o.input_version = h.input_version'),
    'answers': ('research_answer_job', 'research_answer_outbox', 'o.job_id = h.id'),
}


def collect(connection):
    groups = {}
    with connection, connection.cursor() as cursor:
        cursor.execute(observer.IDENTITY)
        if cursor.fetchone() != ('ocean_v1_research_controller', 'ocean_v1_beta', 'on', 'repeatable read'):
            raise ValueError('Wrong read-only observer identity')
        for group, (head, outbox, binding) in TABLES.items():
            cursor.execute(f"""SELECT count(*),
                count(*) FILTER (WHERE o.state = 'pending' AND o.sent_at IS NULL
                  AND o.created_at <= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                  AND (h.lease_until IS NULL OR h.lease_until <= CURRENT_TIMESTAMP)),
                count(*) FILTER (WHERE o.state = 'sent' AND o.sent_at >= o.created_at
                  AND o.sent_at <= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                  AND (h.lease_until IS NULL OR h.lease_until <= CURRENT_TIMESTAMP)),
                count(*) FILTER (WHERE o.id IS NULL),
                count(*) FILTER (WHERE o.id IS NOT NULL AND (
                  o.state IS NULL OR o.state NOT IN ('pending', 'sent') OR o.created_at > CURRENT_TIMESTAMP
                  OR (o.state = 'pending' AND o.sent_at IS NOT NULL)
                  OR (o.state = 'sent' AND (o.sent_at IS NULL OR o.sent_at < o.created_at
                                          OR o.sent_at > CURRENT_TIMESTAMP))))
                FROM public.{head} h LEFT JOIN public.{outbox} o ON {binding}
                WHERE h.status IN ('queued', 'running')""", (PENDING_SECONDS, SENT_SECONDS))
            row, = cursor.fetchall()
            counts = dict(zip(FIELDS, row, strict=True))
            for value in counts.values():
                observer.integer(value, 2**53 - 1)
            if sum(counts[field] for field in FIELDS[1:]) > counts['active']:
                raise ValueError('Inconsistent outbox aggregate')
            groups[group] = counts
    state = 'review_required' if any(group[field] for group in groups.values() for field in FIELDS[1:]) else 'clear'
    return {'state': state, 'counts': groups, 'transaction_read_only_verified': True}


def stop_proxy():
    request = Request('http://127.0.0.1:9091/quitquitquit', data=b'', method='POST')
    with urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise ValueError('Proxy shutdown failed')


def main():
    result = {'state': 'read_failed'}
    try:
        import psycopg2

        if len(sys.argv) != 1:
            raise ValueError('The observer takes no arguments')
        settings = observer.configuration(os.environ)
        settings['application_name'] = 'ocean-beta-b4-outbox-health'
        with closing(psycopg2.connect(**settings)) as connection:
            connection.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
            result = collect(connection)
    except Exception:
        pass  # A SQL/provider exception can contain credentials or work identifiers.
    try:
        stop_proxy()
    except Exception:
        result = {'state': 'read_failed', 'proxy_shutdown_verified': False}
    else:
        result['proxy_shutdown_verified'] = True
    result.update(version=VERSION, project=observer.PROJECT, counts_only=True,
                  pending_threshold_seconds=PENDING_SECONDS, sent_threshold_seconds=SENT_SECONDS,
                  captured_utc=datetime.now(timezone.utc).isoformat())
    print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    return 2 if result['state'] == 'read_failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
