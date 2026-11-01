"""Owned local PostgreSQL entry/limiter rehearsal; no cloud or real data."""
from __future__ import annotations

import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
DIRECTORY = Path(__file__).resolve().parent
BIN = Path('/opt/homebrew/opt/postgresql@18/bin')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-directory', default='native-accepted')
    args = parser.parse_args()
    if not args.run_directory.replace('-', '').isalnum():
        parser.error('Use a new simple run-directory name')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    output = DIRECTORY / args.run_directory
    output.mkdir(exist_ok=False)
    temp = Path(tempfile.mkdtemp(prefix='ocean-v1-host-native-', dir='/private/tmp'))
    cluster, sock = temp/'pg', temp/'socket'
    sock.mkdir()
    receipt = {'version': 'beta-api-host-native-v1', 'scope': 'new disposable local PostgreSQL only',
        'status': 'failed', 'checks': [], 'commands': [], 'cloud_actions': False,
        'scientific_data_or_execution': False, 'server_port': port, 'temp': str(temp)}
    started = False

    def check(name, condition):
        receipt['checks'].append({'id': name, 'passed': bool(condition)})
        assert condition, name

    def command(name, args, *, env=None, expected=0):
        result = subprocess.run(args, cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
        (output/(name+'.stdout')).write_text(result.stdout)
        (output/(name+'.stderr')).write_text(result.stderr)
        receipt['commands'].append({'name': name, 'returncode': result.returncode, 'expected': expected})
        assert result.returncode == expected, name
        return result

    try:
        command('initdb', [str(BIN/'initdb'), '-D', str(cluster), '-A', 'trust', '--no-locale'])
        command('pg-start', [str(BIN/'pg_ctl'), '-D', str(cluster), '-l', str(temp/'postgres.log'),
            '-o', f'-h 127.0.0.1 -p {port} -k {sock}', '-w', 'start'])
        started = True
        command('create-role', [str(BIN/'psql'), '-h', '127.0.0.1', '-p', str(port), '-d', 'postgres',
            '-v', 'ON_ERROR_STOP=1', '-c', 'CREATE ROLE ocean_v1_host LOGIN'])
        command('create-database', [str(BIN/'createdb'), '-h', '127.0.0.1', '-p', str(port),
            '-O', 'ocean_v1_host', 'ocean_v1_host_test'])
        dsn = f'postgresql://ocean_v1_host@127.0.0.1:{port}/ocean_v1_host_test'
        env = {**os.environ, 'DATABASE_URL': dsn, 'DEPLOYMENT_ENV': 'test', 'AUTH_MODE': 'disabled'}
        command('migrations', [str(ROOT/'.venv/bin/python'), '-m', 'alembic', 'upgrade', 'head'], env=env)
        import jwt
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine, inspect, select, text
        from sqlalchemy.orm import sessionmaker
        from api import v1_host
        from db.app_models import AppUser
        for name in v1_host.EXECUTION_FLAGS:
            os.environ[name] = 'false'
        for name in ('SHELL', 'CATALOGUE', 'CATALOGUE_BROWSER', 'INVESTIGATIONS', 'RESEARCH_RUNS', 'EVIDENCE'):
            os.environ['ENABLE_V1_'+name] = 'true'
        os.environ['DEPLOYMENT_ENV'] = 'production'
        config = {'version': 'ocean-v1-api-host-v1', 'project_id': 'ocean-v1-beta-test',
            'site_id': 'v1:ocean-v1-beta-test', 'revision': '1'*40,
            'public_origin': 'https://beta.oceaninfobio.com', 'database_name': 'ocean_v1_host_test',
            'backend_hosts': ['127.0.0.1:8000'], 'allowed_providers': ['oidc'],
            'internal_issuer': 'ocean-v1-frontend', 'internal_audience': 'ocean-v1-api'}
        config_path = temp/'host.json'
        config_path.write_text(json.dumps(config))
        secret = 'synthetic-native-host-secret-'*2
        os.environ.update(OCEAN_V1_HOST_CONFIG=str(config_path), OCEAN_V1_DATABASE_URL=dsn,
            OCEAN_V1_INTERNAL_AUTH_SECRET=secret,
            DATABASE_URL='postgresql://wrong:never-used@127.0.0.1:1/legacy')
        engine = create_engine(dsn)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        actor_id = uuid.uuid4()
        with factory.begin() as session:
            session.add(AppUser(id=actor_id, auth_provider='oidc', auth_subject='native-host-subject',
                email='native-host@example.invalid', display_name='Synthetic native host', role='researcher',
                account_type='internal', status='active'))
        before = inspect(engine).get_table_names()
        now = int(time.time())
        token = jwt.encode({'iss': 'ocean-v1-frontend', 'aud': 'ocean-v1-api', 'iat': now, 'exp': now+60,
            'sub': 'native-host-subject', 'provider': 'oidc', 'email': 'native-host@example.invalid',
            'email_verified': True}, secret, algorithm='HS256')
        headers = {'Authorization': 'Bearer '+token}
        app = v1_host.create_from_environment()
        check('prefixed_factory_ignores_legacy_database_url', app.state.v1_owned_engine.url.database == 'ocean_v1_host_test')
        with TestClient(app, base_url='http://127.0.0.1:8000') as client:
            check('native_authenticated_current_user', client.get('/me', headers=headers).json()['id'] == str(actor_id))
            runtime = client.get('/v1/runtime', headers=headers)
            check('native_unconfigured_catalogue_is_unavailable', runtime.status_code == 200
                and runtime.json()['capabilities']['catalogue']['status'] == 'unavailable')
            check('native_new_execution_rejected', client.post('/research/runs/submit', json={}, headers=headers).status_code == 403)
            with factory.begin() as session:
                session.get(AppUser, actor_id).status = 'suspended'
            check('native_revocation_next_request', client.get('/me', headers=headers).status_code == 403)
            with factory.begin() as session:
                session.get(AppUser, actor_id).status = 'active'
                session.execute(text('UPDATE rate_limit_bucket SET request_count=240'))
            limited = client.get('/me', headers=headers)
            check('native_shared_postgresql_limiter', limited.status_code == 429 and int(limited.headers['retry-after']) >= 1)
        check('native_host_adds_no_schema', before == inspect(engine).get_table_names())
        with factory() as session:
            check('native_migration_head_unchanged', session.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '20261027_0021')
            check('native_user_not_imported_or_duplicated', len(session.scalars(select(AppUser)).all()) == 1)
            receipt['table_count'] = len(before)
        engine.dispose()
        receipt['status'] = 'passed'
    finally:
        if started:
            command('pg-stop', [str(BIN/'pg_ctl'), '-D', str(cluster), '-m', 'immediate', '-w', 'stop'])
            command('pg-stopped', [str(BIN/'pg_ctl'), '-D', str(cluster), 'status'], expected=3)
        with socket.socket() as probe:
            closed = probe.connect_ex(('127.0.0.1', port)) != 0
        receipt['cleanup'] = {'port_closed': closed, 'pid_file_absent': not (cluster/'postmaster.pid').exists()}
        if (temp/'postgres.log').exists():
            shutil.copyfile(temp/'postgres.log', output/'postgres.stdout')
        shutil.rmtree(temp)
        receipt['cleanup']['temporary_directory_removed'] = not temp.exists()
        receipt['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT/'api/v1_host.py', ROOT/'tests/test_v1_host.py', Path(__file__).resolve())}
        receipt['artifact_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in output.iterdir() if p.is_file()}
        (output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    assert all(receipt['cleanup'].values()), receipt['cleanup']
    print(json.dumps({'status': receipt['status'], 'checks': len(receipt['checks']), 'cleanup': receipt['cleanup']}, indent=2))


if __name__ == '__main__':
    main()
