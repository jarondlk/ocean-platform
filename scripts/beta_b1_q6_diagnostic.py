"""Fixed Q6 job/task binding and bounded generation metadata; SELECT only.

The existing observer execution supplies its unchanged identity and secret.
The launcher embeds this source and the original diagnostic helpers by hash.
No account, request, answer prose or scientific table payload is selected.
"""
from scripts import beta_b1_diagnostic as base

VERSION = 'ocean-beta-b1-q6-diagnostic-v1'
RUN_ID = 'f7e35a7a-4196-4431-9f3f-d5edbca66bc8'
JOB_ID = '3d707667-ef41-4b6a-b790-a77a9c91ae9c'
DELIVERY_ID = 'd0b4619b-3108-4c4b-9c32-c3bd7979ec57'
PARAMS = (DELIVERY_ID, RUN_ID, JOB_ID, '86c7fe5b-3485-4a61-ab97-32c4f1628cdc',
    '72a52508-2123-42c4-951f-da54eea16a64', '401844d5-80b8-41a5-83ab-2a1b22093775',
    '50bfdf551337e0b2ff1db4f1df83fe075c6a6b980cb8659f36d614d4d8bca459',
    'cb28a278770a8de9a56de7721e2ad2fea91538cbb0ce8bc11d755df3c5bae2b4')
HEAD = """SELECT j.status,
 CASE WHEN j.reason_code IN ('generation_incomplete','invalid_selection','evidence_pack_unavailable',
 'evidence_unavailable','integrity_error','budget_exhausted','invalid_clock','runtime_unavailable')
 THEN j.reason_code ELSE 'other' END,
 j.active_elapsed_ms,j.tool_actions,j.model_calls,j.malformed_repairs,
 j.lease_until IS NULL AND j.active_started_at IS NULL,
 r.status,r.lease_until IS NULL AND r.active_started_at IS NULL,
 o.state,j.input_version=r.input_version AND j.input_version=1,
 r.tool_actions,r.model_calls,r.malformed_repairs
 FROM research_answer_job j JOIN research_run r ON r.id=j.run_id AND r.user_id=j.user_id
 AND r.investigation_id=j.investigation_id AND r.conversation_id=j.conversation_id
 AND r.revision_id=j.revision_id AND r.snapshot_id=j.snapshot_id
 AND r.payload_sha256=j.payload_sha256 AND r.input_version=j.input_version
 JOIN research_answer_outbox o ON o.job_id=j.id AND o.delivery_id=%s::uuid
 WHERE r.id=%s::uuid AND j.id=%s::uuid AND r.investigation_id=%s::uuid
 AND r.conversation_id=%s::uuid AND r.revision_id=%s::uuid
 AND r.snapshot_id=%s AND r.payload_sha256=%s"""


def collect(connection):
    with connection.cursor() as cursor:
        cursor.execute(base.IDENTITY)
        if cursor.fetchone() != ('ocean_v1_research_controller', 'ocean_v1_beta', 'on', 'repeatable read'):
            raise ValueError('Wrong read-only identity')
        cursor.execute(HEAD, PARAMS)
        rows = cursor.fetchall()
        if len(rows) != 1:
            raise ValueError('Expected one exact bound Q6 job and delivery')
        status, reason, elapsed, tools, calls, repairs, closed, run_status, run_closed, outbox, version, rt, rc, rr = rows[0]
        if (status not in {'queued', 'completed', 'partial', 'unavailable', 'failed', 'cancelled'}
                or closed is not True or run_status != 'completed' or run_closed is not True
                or outbox != 'sent' or version is not True or (rt, rc, rr) != (2, 1, 0)):
            raise ValueError('Active, unbound or undispatched Q6 state')
        head = {'status': status, 'reason_code': reason, 'active_elapsed_ms': base.integer(elapsed, 180000),
            'tool_actions': base.integer(tools, 12), 'model_calls': base.integer(calls, 14),
            'malformed_repairs': base.integer(repairs, 1), 'lease_closed': True,
            'run_status': run_status, 'run_lease_closed': True, 'outbox_state': outbox,
            'exact_frozen_context_and_task_binding_verified': True}
        if tools < rt or calls < rc or repairs < rr:
            raise ValueError('Shared budget regressed')
        groups = {}
        for table, key, identity in (('research_run', 'run_id', RUN_ID), ('research_answer', 'job_id', JOB_ID)):
            cursor.execute(base.generations(table, key), (identity,))
            rows = cursor.fetchall()
            if len(rows) >= 15 or table == 'research_run' and len(rows) != 1:
                raise ValueError('Unbounded or missing model steps')
            values = []
            for state, outcome, finish, inputs, outputs, total, maximum, valid_hash, attempts in rows:
                if state != 'committed' or valid_hash is not True:
                    raise ValueError('Uncertain or corrupt model step')
                usage = {k: None if v is None else base.integer(v, 10000000)
                    for k, v in (('input_tokens', inputs), ('output_tokens', outputs), ('total_tokens', total))}
                values.append({'state': state, 'status': outcome, 'finish_reason': finish, 'usage': usage,
                    'max_output_tokens': None if maximum is None else base.integer(maximum, 4096),
                    'payload_hash_verified': True, 'physical_attempts': base.integer(attempts, 14)})
            groups[table] = values
        if groups['research_run'][0]['physical_attempts'] != 1:
            raise ValueError('Q6 lookup must retain its one physical attempt')
        if sum(step['physical_attempts'] for values in groups.values() for step in values) != calls:
            raise ValueError('Shared model count does not match retained attempts')
        if status == 'queued' and (calls != 1 or groups['research_answer']):
            raise ValueError('Queued answer already has a model attempt')
    return {'version': VERSION, 'state': 'read_only_diagnostic_verified', 'project': base.PROJECT,
        'run_id': RUN_ID, 'answer_job_id': JOB_ID, 'delivery_id': DELIVERY_ID, 'head': head,
        'generations': groups, 'transaction_read_only_verified': True,
        'raw_content_selected_or_emitted': False, 'model_queue_or_sql_write': False}


if __name__ == '__main__':
    original_configuration = base.configuration
    def configuration(env):
        result = original_configuration(env)
        result['application_name'] = 'ocean-b1-q6-read-only-diagnostic'
        return result
    base.configuration = configuration
    base.VERSION, base.collect = VERSION, collect
    raise SystemExit(base.main())
