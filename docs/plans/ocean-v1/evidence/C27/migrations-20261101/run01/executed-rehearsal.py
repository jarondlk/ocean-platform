"""C27 owned, synthetic, loopback PostgreSQL migration rehearsal.

Starts a fresh temporary cluster; accepts no database URL or existing cluster.
Writes new evidence only. No cloud, provider, scientific execution or real data.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT))

from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

PG = Path('/opt/homebrew/opt/postgresql@18/bin')
BASELINE = '20261005_0016'
CONTEXT = '20261018_0017'
HEAD = '20261027_0021'
OWNER = 'c27_owned_synthetic'
DATABASES = ('ocean_c27_fresh', 'ocean_c27_upgrade', 'ocean_c27_offline')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + '\n')


def sanitized_environment():
    child = dict(os.environ)
    for name in list(child):
        if name.startswith(('PG', 'ENABLE_V1_')) or name in ('DATABASE_URL', 'COVERAGE_CORE'):
            child.pop(name)
    child.update(AUTH_MODE='disabled', DEPLOYMENT_ENV='test', ENABLE_MOCK_LOGIN='false',
        PERSIST_LOCAL_CHAT='false', PYTHONPATH=str(ROOT))
    return child


class Rehearsal:
    def __init__(self, output):
        if output.exists():
            raise ValueError('Evidence directory must be new; original receipts are immutable')
        output.mkdir(parents=True)
        shutil.copyfile(__file__, output/'executed-rehearsal.py')
        self.output = output
        self.commands = []
        self.checks = []
        self.temp = Path(tempfile.mkdtemp(prefix='ocean-c27-native-', dir='/private/tmp'))
        self.data = self.temp / 'data'
        self.socket = self.temp / 'socket'
        self.socket.mkdir()
        self.marker = self.temp / 'C27_OWNED_SYNTHETIC'
        self.marker.write_text(str(output))
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            self.port = probe.getsockname()[1]
        self.started = False
        self.engines = []
        self.receipt = {'version': 'c27-disposable-migration-rehearsal-v1',
            'started_at': datetime.now(timezone.utc).isoformat(),
            'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'baseline_revision': BASELINE, 'head_revision': HEAD,
            'scope': 'New owned PostgreSQL18 loopback cluster and synthetic databases only',
            'production_backup_tested': False, 'live_runtime_tested': False,
            'scientific_execution_performed': False, 'prior_binary_compatibility_tested': False,
            'rollback_strategy': 'Disable independent v1 entry/dispatch; preserve schema and all retained records',
            'checks': self.checks, 'commands': self.commands}

    def run(self, label, command, *, env=None, expected=0, timeout=180):
        result = subprocess.run([str(item) for item in command], cwd=ROOT,
            env=env or sanitized_environment(), capture_output=True, timeout=timeout)
        stdout, stderr = self.output / (label + '.stdout'), self.output / (label + '.stderr')
        stdout.write_bytes(result.stdout)
        stderr.write_bytes(result.stderr)
        self.commands.append({'label': label, 'argv': [str(item) for item in command],
            'returncode': result.returncode, 'expected': expected,
            'stdout': stdout.name, 'stderr': stderr.name})
        assert (result.returncode == 0) == (expected == 0), (label, result.stderr.decode()[-3500:])
        return result

    def check(self, identity, observed, expected=True):
        row = {'id': identity, 'status': 'passed' if observed == expected else 'failed',
            'expected': expected, 'observed': observed}
        self.checks.append(row)
        assert row['status'] == 'passed', row

    def url(self, database):
        assert database in DATABASES + ('postgres',)
        return f'postgresql://{OWNER}@127.0.0.1:{self.port}/{database}'

    def engine(self, database):
        engine = create_engine(self.url(database), connect_args={
            'options': '-cstatement_timeout=30000 -clock_timeout=5000'}, pool_pre_ping=True)
        self.engines.append(engine)
        with engine.connect() as connection:
            observed = connection.execute(text('SELECT current_database(),host(inet_server_addr()),'
                'inet_server_port(),current_user,current_setting(\'data_directory\')')).one()
            assert tuple(observed) == (database, '127.0.0.1', self.port, OWNER, str(self.data))
        return engine

    def migrate(self, label, database, target, *, action='upgrade', expected=0):
        child = sanitized_environment()
        child['DATABASE_URL'] = self.url(database)
        return self.run(label, [sys.executable, '-m', 'alembic', action, target],
            env=child, expected=expected)

    @staticmethod
    def revision(engine):
        with engine.connect() as connection:
            return connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()

    def snapshot(self, label, engine):
        with engine.connect() as connection:
            tables = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
            rows = {}
            for table in tables:
                assert table.replace('_', '').isalnum()
                values = connection.execute(text(f'SELECT row_to_json(t)::text FROM "{table}" t')).scalars().all()
                rows[table] = {'count': len(values), 'sha256': digest(canonical(sorted(values)).encode())}
            columns = connection.execute(text("SELECT table_name,column_name,ordinal_position,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position")).all()
            constraints = connection.execute(text("SELECT c.relname,n.conname,pg_get_constraintdef(n.oid) FROM pg_constraint n JOIN pg_class c ON c.oid=n.conrelid JOIN pg_namespace s ON s.oid=c.relnamespace WHERE s.nspname='public' ORDER BY c.relname,n.conname")).all()
            triggers = connection.execute(text("SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace s ON s.oid=c.relnamespace WHERE s.nspname='public' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname")).all()
            functions = connection.execute(text("SELECT p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace s ON s.oid=p.pronamespace WHERE s.nspname='public' ORDER BY p.proname,pg_get_function_identity_arguments(p.oid)")).all()
        schema = {'tables': tables, 'columns': [list(row) for row in columns],
            'constraints': [list(row) for row in constraints], 'triggers': [list(row) for row in triggers],
            'functions': [list(row) for row in functions]}
        result = {'revision': self.revision(engine), 'rows': rows, 'schema': schema,
            'schema_sha256': digest(canonical(schema).encode())}
        write_json(self.output / (label + '.json'), result)
        return result

    def seed_legacy(self, engine):
        owner, chat = str(uuid.uuid4()), str(uuid.uuid4())
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO app_user(id,auth_provider,auth_subject,email,role,account_type,status) VALUES(:id,'c27-synthetic',:id,'synthetic-c27@example.invalid','researcher','research','active')"), {'id': owner})
            connection.execute(text("INSERT INTO chat_interaction(id,user_id,status,query,answer,request_options,evidence_snapshot,legal_hold) VALUES(:id,:owner,'completed','Synthetic C27 retained question','Synthetic C27 retained answer','{}','{}',true)"), {'id': chat, 'owner': owner})
        return {'owner_id': owner, 'chat_id': chat}

    def seed_context(self, engine, owner):
        investigation, revision, conversation = (str(uuid.uuid4()) for _ in range(3))
        payload = canonical({'version': 'c27-synthetic-history', 'authority': 'not_independently_verified'})
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO research_investigation(id,user_id,name,metadata_version,status,legal_hold) VALUES(:id,:owner,'C27 retained synthetic context',1,'active',true)"), {'id': investigation, 'owner': owner})
            connection.execute(text("INSERT INTO research_context_revision(id,investigation_id,sequence,snapshot_id,payload_json,payload_sha256,created_by_user_id) VALUES(:id,:investigation,1,:snapshot,:payload,:hash,:owner)"), {'id': revision, 'investigation': investigation, 'snapshot': 'a'*64, 'payload': payload, 'hash': digest(payload.encode()), 'owner': owner})
            connection.execute(text('UPDATE research_investigation SET head_revision_id=:revision WHERE id=:id'), {'revision': revision, 'id': investigation})
            connection.execute(text("INSERT INTO research_conversation(id,investigation_id,name,metadata_version) VALUES(:id,:investigation,'C27 retained synthetic conversation',1)"), {'id': conversation, 'investigation': investigation})
        return {'investigation_id': investigation, 'revision_id': revision, 'conversation_id': conversation}

    def offline(self):
        scripts = ScriptDirectory.from_config(Config(str(ROOT/'alembic.ini')))
        graph = [{'revision': revision.revision, 'down_revision': revision.down_revision,
            'path': str(Path(revision.path).relative_to(ROOT))} for revision in reversed(list(scripts.walk_revisions()))]
        self.check('single_actual_migration_head', scripts.get_heads(), [HEAD])
        self.check('actual_migration_count', len(graph), 21)
        write_json(self.output/'migration-graph.json', graph)
        review = []
        for row in graph:
            module = ast.parse((ROOT/row['path']).read_text())
            upgrade = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name=='upgrade')
            operations = sorted({node.func.attr for node in ast.walk(upgrade)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id=='op'})
            review.append({**row, 'upgrade_operations': operations,
                'sha256': digest((ROOT/row['path']).read_bytes())})
        write_json(self.output/'migration-review.json', review)
        child = sanitized_environment()
        child['DATABASE_URL'] = 'postgresql://c27_offline:synthetic-sentinel@127.0.0.1:1/ocean_c27_offline'
        for label, span in (('offline-base-to-head', 'base:head'),
                ('offline-0016-to-head', BASELINE+':head')):
            result = self.run(label, [sys.executable, '-m', 'alembic', 'upgrade', span, '--sql'], env=child)
            sql = result.stdout
            self.check(label+'-no-target-or-credential', not any(token in sql for token in
                (b'synthetic-sentinel', b'postgresql://', b'127.0.0.1')))
            self.check(label+'-transactional', b'BEGIN;' in sql and sql.rstrip().endswith(b'COMMIT;'))
            (self.output/(label+'.sql')).write_bytes(sql)

    def start(self):
        self.run('initdb', [PG/'initdb', '-D', self.data, '-U', OWNER, '-A', 'trust', '--no-locale', '-E', 'UTF8'])
        self.run('pg-start', [PG/'pg_ctl', '-D', self.data, '-l', self.temp/'postgres.log', '-o',
            f'-h 127.0.0.1 -p {self.port} -k {self.socket} -c max_connections=20', '-w', 'start'])
        self.started = True
        admin = self.engine('postgres')
        with admin.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            for database in DATABASES:
                connection.exec_driver_sql(f'CREATE DATABASE {database}')
        self.receipt['owned_target'] = {'temp_directory': str(self.temp),
            'listen_address': '127.0.0.1', 'port': self.port, 'databases': list(DATABASES),
            'database_identity_checked': True, 'runtime': self.run('pg-version', [PG/'postgres', '--version']).stdout.decode().strip()}

    def native(self):
        fresh, upgrade, offline = (self.engine(name) for name in DATABASES)
        self.migrate('fresh-upgrade-head', DATABASES[0], 'head')
        first = self.snapshot('fresh-head', fresh)
        self.check('fresh_current_revision', first['revision'], HEAD)
        self.migrate('baseline-upgrade-0016', DATABASES[1], BASELINE)
        legacy = self.seed_legacy(upgrade)
        baseline = self.snapshot('baseline-seeded-0016', upgrade)
        with upgrade.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE research_conversation(c27_failure_marker integer)')
        blocker = self.snapshot('before-controlled-failure', upgrade)
        self.migrate('controlled-duplicate-table-upgrade-failure', DATABASES[1], 'head', expected=1)
        failed = self.snapshot('after-controlled-failure', upgrade)
        self.check('partial_migration_transaction_restored', digest(canonical(failed).encode()), digest(canonical(blocker).encode()))
        with upgrade.begin() as connection:
            connection.exec_driver_sql('DROP TABLE research_conversation')
        self.migrate('retry-upgrade-0017', DATABASES[1], CONTEXT)
        context = self.seed_context(upgrade, legacy['owner_id'])
        context_before = self.snapshot('seeded-context-0017', upgrade)
        self.migrate('retry-upgrade-head', DATABASES[1], 'head')
        after = self.snapshot('upgraded-head', upgrade)
        self.check('baseline_chat_rows_preserved', after['rows']['chat_interaction'], baseline['rows']['chat_interaction'])
        for table in ('research_investigation','research_context_revision','research_conversation'):
            self.check(table+'-preserved-across-upgrade', after['rows'][table], context_before['rows'][table])
        self.check('fresh_and_upgrade_schema_equal', after['schema_sha256'], first['schema_sha256'])
        # Apply the actual generated SQL to a third empty database; do not infer
        # its executability solely from compilation or string checks.
        self.run('apply-offline-sql', [PG/'psql', '-h', '127.0.0.1', '-p', self.port, '-U', OWNER,
            '-d', DATABASES[2], '-v', 'ON_ERROR_STOP=1', '-f', self.output/'offline-base-to-head.sql'])
        applied = self.snapshot('offline-applied-head', offline)
        self.check('offline_and_online_schema_equal', applied['schema_sha256'], first['schema_sha256'])
        # Existing synthetic application services populate actual current
        # journals/evidence/proposals. The explicit synthetic execution adapter
        # never executes code and is not a C23 physical-runtime substitute.
        os.environ.update(sanitized_environment())
        for name in ('ENABLE_V1_CATALOGUE','ENABLE_V1_INVESTIGATIONS','ENABLE_V1_RESEARCH_CONTROLLER'):
            os.environ[name]='true'
        from tests.system_acceptance_support import make_system_acceptance_fixture, seed_integrated_browser
        fixtures = self.temp/'fixtures'
        fixtures.mkdir()
        actual = make_system_acceptance_fixture(upgrade, fixtures)
        seed = seed_integrated_browser(actual)
        populated = self.snapshot('populated-current-history', upgrade)
        required = ('research_investigation','research_context_revision','research_run',
            'research_evidence_receipt','research_answer','research_experiment','research_experiment_revision',
            'research_experiment_approval')
        self.check('current_history_populated', all(populated['rows'][name]['count'] > 0 for name in required))
        self.migrate('repeat-head-with-history', DATABASES[1], 'head')
        repeated = self.snapshot('reapplied-current-history', upgrade)
        self.check('repeat_head_preserves_all_rows_and_schema', digest(canonical(repeated).encode()), digest(canonical(populated).encode()))
        self.migrate('populated-downgrade-refused', DATABASES[1], BASELINE, action='downgrade', expected=1)
        retained = self.snapshot('after-refused-downgrade', upgrade)
        self.check('populated_downgrade_transaction_preserves_head_schema_history', digest(canonical(retained).encode()), digest(canonical(populated).encode()))
        self.check('physical_execution_not_inferred', seed['execution']['execution_performed'], False)
        self.receipt['synthetic_history_ids'] = {'legacy': legacy,'context_at0017': context,
            'current_investigation': seed['binding']['investigation_id'], 'current_run': seed['run']['id'],
            'current_answer': seed['answer_job']['answer']['id'], 'experiment': seed['experiment']['id'],
            'synthetic_artifacts': [{'id': row['id'], 'sha256': row['sha256']} for row in seed['execution']['artifacts']]}
        self.receipt['schema_summary'] = {name: len(first['schema'][name]) for name in first['schema']}
        self.receipt['schema_sha256'] = first['schema_sha256']

    def cleanup(self):
        for engine in self.engines:
            engine.dispose()
        if self.started:
            # Only the freshly initialized path bearing this run's ownership
            # marker is accepted. No discovery of existing local servers.
            assert self.marker.read_text() == str(self.output)
            self.run('pg-stop', [PG/'pg_ctl','-D',self.data,'-m','fast','-w','stop'])
            self.started = False
            self.run('pg-stopped-status', [PG/'pg_ctl','-D',self.data,'status'], expected=1)
            with socket.socket() as probe:
                probe.settimeout(1)
                closed = probe.connect_ex(('127.0.0.1',self.port)) != 0
            self.check('owned_server_stopped_and_port_closed', closed and not (self.data/'postmaster.pid').exists())
            if (self.temp/'postgres.log').is_file():
                shutil.copyfile(self.temp/'postgres.log',self.output/'owned-postgres.log')
        self.receipt['cleanup']={'cluster_stopped': not self.started,
            'temporary_directory': str(self.temp), 'temporary_files_removed': False}
        if not self.started and self.marker.is_file():
            shutil.rmtree(self.temp)
            self.receipt['cleanup']['temporary_files_removed']=not self.temp.exists()

    def finish(self):
        self.receipt['finished_at']=datetime.now(timezone.utc).isoformat()
        self.receipt['status']='passed' if self.checks and all(x['status']=='passed' for x in self.checks) and 'error' not in self.receipt else 'failed'
        files={str(path.relative_to(self.output)):digest(path.read_bytes()) for path in sorted(self.output.iterdir()) if path.is_file() and path.name!='receipt.json'}
        self.receipt['artifact_sha256']=files
        self.receipt['source_sha256']={str(path.relative_to(ROOT)):digest(path.read_bytes()) for path in [Path(__file__),ROOT/'migrations/env.py',ROOT/'config.py',ROOT/'alembic.ini']+sorted((ROOT/'migrations/versions').glob('*.py'))}
        write_json(self.output/'receipt.json',self.receipt)
        print(json.dumps({'status':self.receipt['status'],'checks':len(self.checks),'output':str(self.output),'cleanup':self.receipt['cleanup']}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.resolve()==Path(__file__).resolve().parent:
        raise ValueError('Use a new child run directory to preserve the script and existing evidence')
    work=Rehearsal(args.output.resolve())
    try:
        work.offline()
        work.start()
        work.native()
    except BaseException as error:
        work.receipt['error']={'type':type(error).__name__,'message':str(error)}
        raise
    finally:
        try:
            work.cleanup()
        finally:
            work.finish()


if __name__=='__main__':
    main()
