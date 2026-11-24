"""Render the beta-only storage grants and inspect the retained SQL boundary.

No cloud client, credential handling, SQL grants, or role creation runs here.
"""
from copy import deepcopy
import hashlib

from sqlalchemy import text

from api.v1_beta_experiment_reads import LEDGER_ROLE, RESULTS_BUCKET
from orchestration.experiment_sandbox.ledger_reader import _EXPECTED_READS, _READ_COLUMNS, _read_privileges


PROJECT = 'ocean-v1-beta-20261101'
DATABASE = 'ocean_v1_beta'
SERVING = 'ocean_v1_serving'
MIGRATOR = 'ocean_v1_migrator'
PREFIX = 'c23/outputs-v1/'
SCHEMA = 'public'
BUCKET_RESOURCE = f'projects/_/buckets/{RESULTS_BUCKET}'
CONDITION = f"resource.type == 'storage.googleapis.com/Object' && resource.name.startsWith('{BUCKET_RESOURCE}/objects/{PREFIX}')"
STORAGE_GRANTS = (
    ('oceanBetaExperimentResultRead', 'ocean-v1-beta-serving', ('storage.objects.get',)),
    ('oceanBetaExperimentResultPublish', 'ocean-v1-beta-supervisor', ('storage.objects.create', 'storage.objects.get')),
)
SERVING_READ_TABLES = (
    'research_experiment', 'research_experiment_approval', 'research_experiment_revision',
    'research_experiment_revision_file', 'research_experiment_input_blob',
    'research_experiment_reservation', 'research_experiment_event',
)
HEAD_GUARD_SHA256 = 'f33cc0301a59b93a16eaa11b49d9b2da687860b5f8acf20b247897a652dc2f2c'
OWNER_LOCK_BODY = 'BEGIN\n  PERFORM 1 FROM public.app_user WHERE id = owner_id FOR SHARE;\nEND'


def sql_grant_plan():
    """Split the proposed grants between the database and table owners."""
    return {
        'postgres': (
            f'GRANT CONNECT ON DATABASE {DATABASE} TO {LEDGER_ROLE}',
            f'GRANT USAGE ON SCHEMA {SCHEMA} TO {LEDGER_ROLE}',
        ),
        MIGRATOR: (
            *(f'GRANT SELECT ({", ".join(columns)}) ON {SCHEMA}.{table} TO {LEDGER_ROLE}'
                for table, columns in _READ_COLUMNS.items()),
            *(f'GRANT SELECT ON {SCHEMA}.{table} TO {SERVING}' for table in SERVING_READ_TABLES),
            f'GRANT UPDATE (id) ON {SCHEMA}.research_experiment TO {SERVING}',
        ),
    }


def storage_grant_plan(bucket, policy):
    """Preserve the provider etag and every unrelated binding in the proposal."""
    if (bucket.get('name') != RESULTS_BUCKET or str(bucket.get('projectNumber')) != '534831104543'
            or bucket.get('location') != 'ASIA-NORTHEAST1'):
        raise ValueError('Exact Tokyo beta results bucket required')
    iam = bucket.get('iamConfiguration', {})
    if (iam.get('uniformBucketLevelAccess', {}).get('enabled') is not True
            or iam.get('publicAccessPrevention') != 'enforced'):
        raise ValueError('Protected bucket policy required')
    if (type(policy.get('etag')) is not str or not policy['etag'] or policy.get('version') not in (1, 3)
            or type(policy.get('bindings')) is not list):
        raise ValueError('Fresh IAM policy and etag required')
    proposal = deepcopy(policy)
    proposal['version'] = 3
    roles = {}
    for role_id, identity, permissions in STORAGE_GRANTS:
        role = f'projects/{PROJECT}/roles/{role_id}'
        member = f'serviceAccount:{identity}@{PROJECT}.iam.gserviceaccount.com'
        expected = {'role': role, 'members': [member],
            'condition': {'title': 'betaExperimentOutputsV1Only', 'expression': CONDITION}}
        current = [binding for binding in policy['bindings'] if binding['role'] == role]
        if current and current != [expected]:
            raise ValueError('Existing experiment result role binding differs from the exact plan')
        if any(member in binding['members'] and binding != expected for binding in policy['bindings']):
            raise ValueError('Existing direct access for the experiment runtime requires review')
        if not current:
            proposal['bindings'].append(expected)
        roles[role] = permissions
    return {'project': PROJECT, 'bucket': BUCKET_RESOURCE, 'role_permissions': roles, 'proposed_policy': proposal}


def sql_boundary(connection, ledger_config):
    """Inspect only target, migration, owner/guard and exact ledger access metadata."""
    if (connection.dialect.name != 'postgresql' or ledger_config.database_name != DATABASE
            or ledger_config.schema != SCHEMA or ledger_config.role != LEDGER_ROLE):
        raise ValueError('Exact beta SQL boundary required')
    row = connection.execute(text('''
        SELECT current_database(), current_schema(), current_user, session_user,
            current_setting('transaction_read_only'),
            pg_get_userbyid(d.datdba), pg_get_userbyid(n.nspowner)
        FROM pg_database d JOIN pg_namespace n ON n.nspname = 'public'
        WHERE d.datname = current_database()
    ''')).one()
    if tuple(row) != (DATABASE, SCHEMA, MIGRATOR, MIGRATOR, 'on', 'postgres', 'pg_database_owner'):
        raise ValueError('Exact beta migrator, owners and read-only transaction required')
    if connection.scalars(text('SELECT version_num FROM public.alembic_version')).all() != ['20261027_0021']:
        raise ValueError('Exact C23 migration head required')
    tables = {*SERVING_READ_TABLES, *_READ_COLUMNS}
    owners = connection.execute(text('''
        SELECT c.relname, pg_get_userbyid(c.relowner) FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = ANY(:tables)
    '''), {'tables': sorted(tables)}).all()
    if set(owners) != {(table, MIGRATOR) for table in tables}:
        raise ValueError('Exact experiment table owners required')
    guard = connection.execute(text('''
        SELECT t.tgenabled, t.tgtype, pg_get_userbyid(p.proowner),
            p.oid = to_regprocedure('public.ocean_research_experiment_guard()'), p.prosrc
        FROM pg_trigger t JOIN pg_class c ON t.tgrelid = c.oid JOIN pg_proc p ON t.tgfoid = p.oid
        WHERE c.oid = 'public.research_experiment'::regclass AND t.tgname = 'research_experiment_immutable'
          AND NOT t.tgisinternal AND t.tgqual IS NULL
    ''')).one_or_none()
    if (guard is None or tuple(guard[:4]) != ('O', 27, MIGRATOR, True)
            or hashlib.sha256(guard[4].strip().encode()).hexdigest() != HEAD_GUARD_SHA256):
        raise ValueError('Existing experiment identity trigger required')
    owner_lock = connection.execute(text('''
        SELECT p.prosecdef, pg_get_userbyid(p.proowner), p.proconfig,
            has_function_privilege(:serving, p.oid, 'EXECUTE'), p.prosrc
        FROM pg_proc p WHERE p.oid = to_regprocedure('public.ocean_v1_beta_research_owner_lock(uuid)')
    '''), {'serving': SERVING}).one_or_none()
    if (owner_lock is None or tuple(owner_lock[:4]) != (True, MIGRATOR, ['search_path=pg_catalog'], True)
            or owner_lock[4].strip() != OWNER_LOCK_BODY):
        raise ValueError('Existing account-write-free owner lock required')
    present = connection.scalar(text('SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=:role)'), {'role': LEDGER_ROLE})
    state = 'absent'
    if present:
        observed = _read_privileges(connection, ledger_config)
        if not observed <= _EXPECTED_READS:
            raise ValueError('Existing ledger login has unexpected access')
        state = 'exact' if observed == _EXPECTED_READS else 'partial'
    return {'ledger_login': state, 'schema': SCHEMA, 'migration': '20261027_0021',
        'head_guard_present': True, 'serving_owner_lock_present': True}
