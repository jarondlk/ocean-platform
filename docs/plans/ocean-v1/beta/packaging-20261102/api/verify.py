"""Local package guard/import checks; never connects, builds or deploys."""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent
PACKAGE = ROOT / 'deploy/gcp/beta/api'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run():
    entry = load('beta_entry_checks', PACKAGE / 'entry.py')
    context = load('beta_context_checks', PACKAGE / 'prepare_context.py')
    base = {'DEPLOYMENT_ENV': 'production', 'OCEAN_V1_PROJECT_ID': entry.PROJECT,
        'OCEAN_V1_SQL_CONNECTION_NAME': entry.PROJECT + ':asia-northeast1:ocean-v1-beta-example',
        'OCEAN_V1_DATABASE_USER': 'ocean_v1_migrator',
        'OCEAN_V1_DATABASE_URL': 'postgresql+psycopg2://ocean_v1_migrator:synthetic@127.0.0.1:6543/ocean_v1_beta'}
    checks = []
    entry.validate_environment(base, migration=True)
    checks.append('explicit beta loopback configuration accepted without connection')
    socket = dict(base, OCEAN_V1_DATABASE_URL='postgresql+psycopg2://ocean_v1_migrator:synthetic@/ocean_v1_beta?host=/cloudsql/'
        + base['OCEAN_V1_SQL_CONNECTION_NAME'])
    entry.validate_environment(socket, migration=True)
    checks.append('exact selected beta Cloud SQL socket accepted without connection')
    invalid = [
        dict(base, OCEAN_V1_PROJECT_ID='data-infra-infobio'),
        dict(base, DATABASE_URL=base['OCEAN_V1_DATABASE_URL']),
        dict(base, DEPLOYMENT_ENV='test'),
        dict(base, ENABLE_V1_EXPERIMENT_DISPATCH='true'),
        dict(base, OCEAN_V1_DATABASE_URL='postgresql+psycopg2://ocean:synthetic@127.0.0.1:6543/ocean_platform'),
        dict(base, OCEAN_V1_DATABASE_URL='postgresql+psycopg2://ocean_v1_migrator:synthetic@8.8.8.8:5432/ocean_v1_beta'),
        dict(base, OCEAN_V1_DATABASE_URL='sqlite:///ocean_v1_beta'),
        dict(base, OCEAN_V1_SQL_CONNECTION_NAME='data-infra-infobio:asia-northeast1:legacy'),
        dict(base, OCEAN_V1_DATABASE_URL=base['OCEAN_V1_DATABASE_URL'] + '?options=-csearch_path%3Dpublic'),
        dict(socket, OCEAN_V1_DATABASE_URL=socket['OCEAN_V1_DATABASE_URL'].replace('beta-example', 'beta-other')),
        dict(base, OCEAN_V1_DATABASE_USER='ocean_v1_serving', OCEAN_V1_DATABASE_URL=base['OCEAN_V1_DATABASE_URL'].replace('migrator', 'serving')),
    ]
    with patch('sqlalchemy.create_engine', side_effect=AssertionError('unexpected database access')):
        for number, env in enumerate(invalid):
            try:
                entry.validate_environment(env, migration=True)
            except entry.EntryError:
                checks.append('invalid target/configuration rejected ' + str(number + 1))
            else:
                raise AssertionError('unsafe operator target accepted')
        output = io.StringIO()
        with redirect_stdout(output):
            entry.migrate(base, confirm_project=entry.PROJECT, confirm_database=entry.DATABASE, check_only=True)
        assert 'no database connection' in output.getvalue()
        checks.append('migration check-only performs no database access')
        try:
            entry.migrate(base, confirm_project='data-infra-infobio', confirm_database=entry.DATABASE)
        except entry.EntryError:
            checks.append('wrong operator confirmation rejected before connection')
        else:
            raise AssertionError('wrong operator confirmation accepted')
    sources = context.selected_sources()
    relative = {p.relative_to(ROOT).as_posix() for p in sources}
    assert 'api/v1_host.py' in relative and 'api/main.py' not in relative
    assert 'migrations/versions/20261027_0021_experiment_execution.py' in relative
    assert not any('fixture' in name or name.startswith(('tests/', 'data/', 'frontend/')) for name in relative)
    checks.append('static source closure excludes main, fixtures, data, tests and frontend')
    with tempfile.TemporaryDirectory(prefix='ocean-beta-api-package-') as temporary:
        directory = Path(temporary)
        manifest = directory / 'source-manifest.json'
        configuration = directory / 'host.json'
        manifest.write_text(json.dumps({'version':'ocean-v1-beta-api-context-v1', 'project_id':entry.PROJECT,
            'revision':'a'*40}))
        configuration.write_text(json.dumps({'project_id':entry.PROJECT, 'database_name':entry.DATABASE,
            'revision':'a'*40}))
        with patch.object(entry, 'ROOT', directory):
            entry.validate_serving_source({'OCEAN_V1_HOST_CONFIG':str(configuration)})
            checks.append('matching packaged source/config accepted')
            configuration.write_text(json.dumps({'project_id':entry.PROJECT, 'database_name':entry.DATABASE,
                'revision':'b'*40}))
            try:
                entry.validate_serving_source({'OCEAN_V1_HOST_CONFIG':str(configuration)})
            except entry.EntryError:
                checks.append('mismatched host revision rejected')
            else:
                raise AssertionError('mismatched source accepted')
        for source in sources:
            target = directory / 'application' / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        probe = '''
import socket, sqlalchemy, psycopg2
def denied(*a, **k):
    raise AssertionError('Import attempted external state access')
socket.socket.connect = denied
socket.create_connection = denied
sqlalchemy.create_engine = denied
psycopg2.connect = denied
import api.v1_host
assert api.v1_host.MIGRATION_HEAD == '20261027_0021'
print('Selected source-only API imports without connection attempts')
'''
        child_env = dict(os.environ, PYTHONPATH=str(directory / 'application'), PYTHONDONTWRITEBYTECODE='1',
            DEPLOYMENT_ENV='production', DATABASE_URL='postgresql://unusable-legacy.invalid/forbidden')
        process = subprocess.run([str(ROOT / '.venv/bin/python'), '-c', probe], cwd=directory / 'application',
            env=child_env, text=True, capture_output=True, timeout=30, check=True)
        assert 'without connection attempts' in process.stdout
        checks.append('selected isolated source import succeeds with external state access blocked')
        try:
            context.prepare(directory, 'a'*40)
        except ValueError:
            checks.append('existing context output refused without overwrite')
        else:
            raise AssertionError('existing output accepted')
    return {'version':'ocean-v1-beta-api-package-check-v1', 'checks':checks, 'passed':len(checks),
        'selected_source_paths':sorted(relative), 'temporary_cleanup':'owned context removed',
        'database_connections_attempted':False, 'image_build_performed':False, 'cloud_calls_performed':False}


if __name__ == '__main__':
    result = run()
    print(json.dumps(result, indent=2))
