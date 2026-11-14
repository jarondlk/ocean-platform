"""Fixed Q5 read-only diagnostic; emits bounded execution metadata only.

Run inside the existing beta observer Job, with its unchanged identity, proxy,
network and numeric secret version. No SQL write or model/queue call exists.
"""

import datetime
import json
import os
import sys
import urllib.request

PROJECT = 'ocean-v1-beta-20261101'
RUN_ID = '6e09ea49-b2bd-40ac-a457-b16709912f1d'
JOB_ID = 'bb9994e4-c678-4fc3-a59c-97adf0563e13'
VERSION = 'ocean-beta-b1-q5-diagnostic-v1'
IDENTITY = "SELECT current_user, current_database(), current_setting('transaction_read_only'), current_setting('transaction_isolation')"
HEAD = """SELECT j.status,
 CASE WHEN j.reason_code IN ('generation_incomplete','invalid_selection','evidence_pack_unavailable',
 'evidence_unavailable','integrity_error','budget_exhausted','invalid_clock','runtime_unavailable')
 THEN j.reason_code ELSE 'other' END,
 j.active_elapsed_ms,j.tool_actions,j.model_calls,j.malformed_repairs,
 j.lease_until IS NULL AND j.active_started_at IS NULL,
 r.status,r.lease_until IS NULL AND r.active_started_at IS NULL
 FROM research_answer_job j JOIN research_run r ON r.id=j.run_id AND r.user_id=j.user_id
 AND r.investigation_id=j.investigation_id AND r.conversation_id=j.conversation_id
 AND r.revision_id=j.revision_id AND r.snapshot_id=j.snapshot_id
 AND r.payload_sha256=j.payload_sha256 AND r.input_version=j.input_version
 WHERE r.id=%s::uuid AND j.id=%s::uuid AND j.input_version=1"""


def generations(table, key):
    # Identifiers are fixed constants, never operator input. Never select raw
    # content, requests, prompts, manifests, identities or scientific table rows.
    return f"""SELECT s.state,
 CASE WHEN p.payload_json::jsonb->>'status' IN ('completed','output_limited','refused','failed','unknown')
 THEN p.payload_json::jsonb->>'status' ELSE 'unrecognized' END,
 CASE WHEN p.payload_json::jsonb->>'finish_reason' IN
 ('STOP','MAX_TOKENS','SAFETY','RECITATION','OTHER','BLOCKLIST','PROHIBITED_CONTENT',
 'SPII','MALFORMED_FUNCTION_CALL','UNEXPECTED_TOOL_CALL','ClientError','ServerError',
 'ReadTimeout','TimeoutError','ConnectTimeout','ConnectionError','ValueError')
 THEN p.payload_json::jsonb->>'finish_reason'
 WHEN p.payload_json::jsonb->>'finish_reason' IS NULL THEN NULL ELSE 'unrecognized' END,
 p.payload_json::jsonb#>'{{usage,input_tokens}}',
 p.payload_json::jsonb#>'{{usage,output_tokens}}',
 p.payload_json::jsonb#>'{{usage,total_tokens}}',
 p.payload_json::jsonb->'max_output_tokens',
 encode(sha256(convert_to(p.payload_json,'UTF8')),'hex')=p.sha256,
 (SELECT count(*) FROM {table}_attempt a WHERE a.{key}=s.{key} AND a.step_id=s.step_id)
 FROM {table}_step s LEFT JOIN {table}_payload p ON p.{key}=s.{key} AND p.sha256=s.outcome_sha256
 WHERE s.{key}=%s::uuid AND s.kind='model' ORDER BY s.step_id LIMIT 15"""


def integer(value, cap):
    if type(value) is not int or not 0 <= value <= cap:
        raise ValueError('Invalid bounded count')
    return value


def collect(connection):
    with connection.cursor() as cursor:
        cursor.execute(IDENTITY)
        if cursor.fetchone() != ('ocean_v1_research_controller', 'ocean_v1_beta', 'on', 'repeatable read'):
            raise ValueError('Wrong read-only identity')
        cursor.execute(HEAD, (RUN_ID, JOB_ID))
        heads = cursor.fetchall()
        if len(heads) != 1:
            raise ValueError('Expected one bound head')
        status, reason, elapsed, tools, calls, repairs, closed, run_status, run_closed = heads[0]
        if status != 'unavailable' or run_status != 'completed' or closed is not True or run_closed is not True:
            raise ValueError('Expected terminal closed heads')
        head = {'status': status, 'reason_code': reason, 'active_elapsed_ms': integer(elapsed, 180000),
                'tool_actions': integer(tools, 12), 'model_calls': integer(calls, 14),
                'malformed_repairs': integer(repairs, 1), 'lease_closed': closed,
                'run_status': run_status, 'run_lease_closed': run_closed}
        groups = {}
        for table, key, identity in (('research_run', 'run_id', RUN_ID), ('research_answer', 'job_id', JOB_ID)):
            cursor.execute(generations(table, key), (identity,))
            rows = cursor.fetchall()
            if len(rows) >= 15:
                raise ValueError('Model step bound exceeded')
            values = []
            for state, outcome, finish, inputs, outputs, total, maximum, valid_hash, attempts in rows:
                if state != 'committed' or valid_hash is not True:
                    raise ValueError('Uncertain or corrupt model step')
                usage = {k: None if v is None else integer(v, 10000000)
                         for k, v in (('input_tokens', inputs), ('output_tokens', outputs), ('total_tokens', total))}
                values.append({'state': state, 'status': outcome, 'finish_reason': finish, 'usage': usage,
                               'max_output_tokens': None if maximum is None else integer(maximum, 4096),
                               'payload_hash_verified': True, 'physical_attempts': integer(attempts, 14)})
            groups[table] = values
    return {'version': VERSION, 'state': 'read_only_diagnostic_verified', 'project': PROJECT,
            'run_id': RUN_ID, 'answer_job_id': JOB_ID, 'head': head, 'generations': groups,
            'transaction_read_only_verified': True, 'raw_content_selected_or_emitted': False,
            'model_queue_or_sql_write': False}


def configuration(env):
    from sqlalchemy.engine import make_url
    user = 'ocean_v1_research_controller'
    if (env.get('OCEAN_V1_PROJECT_ID') != PROJECT or env.get('DEPLOYMENT_ENV') != 'production'
            or env.get('OCEAN_V1_SQL_CONNECTION_NAME') != PROJECT + ':asia-northeast1:ocean-v1-beta-sql'
            or env.get('OCEAN_V1_DATABASE_USER') != user or 'DATABASE_URL' in env
            or any(v.strip().lower() != 'false' for k, v in env.items() if k.startswith('ENABLE_V1_'))):
        raise ValueError('Wrong diagnostic target')
    url = make_url(env['OCEAN_V1_DATABASE_URL'])
    if (url.drivername != 'postgresql+psycopg2' or url.username != user or not url.password
            or url.database != 'ocean_v1_beta' or url.host != '127.0.0.1' or url.port != 5432
            or dict(url.query) not in ({}, {'sslmode': 'disable'})):
        raise ValueError('Wrong diagnostic database identity')
    return {'host': url.host, 'port': url.port, 'user': url.username, 'password': url.password,
            'dbname': url.database, 'sslmode': 'disable', 'connect_timeout': 5,
            'application_name': 'ocean-b1-q5-read-only-diagnostic',
            'options': '-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=15000'}


def main():
    connection = None
    result = {'version': VERSION, 'state': 'diagnostic_failed'}
    code = 2
    try:
        if len(sys.argv) != 1:
            raise ValueError('No arguments supported')
        import psycopg2
        connection = psycopg2.connect(**configuration(os.environ))
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
        result = collect(connection)
        code = 0
    except Exception:
        # Never stringify a DB/provider exception, URL, connection or row.
        pass
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                code = 2
            try:
                connection.close()
            except Exception:
                code = 2
        try:
            request = urllib.request.Request('http://127.0.0.1:9091/quitquitquit', data=b'', method='POST')
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status != 200:
                    raise ValueError('Proxy shutdown failed')
            result['proxy_shutdown_verified'] = True
        except Exception:
            code = 2
            result['proxy_shutdown_verified'] = False
        if code:
            result['state'] = 'diagnostic_failed'
        result['captured_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        print(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
