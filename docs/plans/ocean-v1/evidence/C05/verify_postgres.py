"""Replay C05 acceptance on a newly owned disposable loopback cluster only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import uuid

from sqlalchemy import create_engine, text


def main():
    output = Path(__file__).resolve().parent
    binaries = Path('/opt/homebrew/opt/postgresql@18/bin')
    cluster = Path(tempfile.mkdtemp(prefix='ocean-c05-readiness-', dir='/private/tmp'))
    data = cluster / 'data'
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    role = 'ocean_c05'
    database = 'ocean_c05_readiness_' + uuid.uuid4().hex[:12]
    url = f'postgresql://{role}@127.0.0.1:{port}/{database}'
    result = {
        'cluster_root': str(cluster), 'data_directory': str(data),
        'host': '127.0.0.1', 'port': port, 'role': role, 'database': database,
        'existing_database_urls_used': False,
    }
    code = 1
    with (output / 'postgres-lifecycle.txt').open('w') as lifecycle:
        def run(arguments):
            subprocess.run([str(item) for item in arguments], stdout=lifecycle,
                           stderr=subprocess.STDOUT, check=True)

        try:
            run([binaries / 'initdb', '-D', data, '-U', role, '--auth=trust',
                 '--no-locale', '--encoding=UTF8'])
            run([binaries / 'pg_ctl', '-D', data, '-l', cluster / 'server.log',
                 '-o', f'-h 127.0.0.1 -p {port} -k {cluster}', '-w', 'start'])
            run([binaries / 'createdb', '-h', '127.0.0.1', '-p', port, '-U', role, database])
            engine = create_engine(url)
            try:
                with engine.connect() as connection:
                    connection.execute(text('CREATE EXTENSION vector'))
                    connection.commit()
                    row = connection.execute(text(
                        "SELECT current_database(), current_user, host(inet_server_addr()), "
                        "inet_server_port(), version(), current_setting('transaction_isolation'), "
                        "current_setting('data_directory')"
                    )).one()
                    assert row[0] == database and row[1] == role
                    assert row[2] == '127.0.0.1' and row[3] == port
                    assert row[5] == 'read committed' and Path(row[6]) == data
                    result['identity'] = dict(zip(
                        ['database', 'role', 'host', 'port', 'version', 'isolation', 'data_directory'], row
                    ))
            finally:
                engine.dispose()
            environment = dict(
                os.environ, RUN_POSTGRES_INTEGRATION='1', C05_TEST_DATABASE_URL=url,
                AUTH_MODE='disabled', DEPLOYMENT_ENV='test', PERSIST_LOCAL_CHAT='false',
                DATABASE_URL='postgresql://unused:unused@127.0.0.1:1/ocean_c04_readiness_unused',
            )
            command = [sys.executable, '-m', 'pytest',
                       'tests/integration/test_retrieval_identity_postgres.py',
                       '-q', '-s', '--tb=short']
            with (output / 'postgres-tests.txt').open('w') as test_log:
                code = subprocess.run(command, env=environment, stdout=test_log,
                                      stderr=subprocess.STDOUT).returncode
            result['test_command'] = command
            result['test_exit_code'] = code
            engine = create_engine(url)
            try:
                with engine.connect() as connection:
                    result['pgvector_version'] = connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
                    result['test_schemas_remaining'] = connection.scalar(text(
                        "SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'c05_%'"
                    ))
                    assert result['test_schemas_remaining'] == 0
            finally:
                engine.dispose()
        except BaseException as error:
            result['error'] = str(error)
            code = 1
        finally:
            if (data / 'postmaster.pid').exists():
                stop = subprocess.run(
                    [str(binaries / 'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', 'stop'],
                    stdout=lifecycle, stderr=subprocess.STDOUT,
                )
                result['stop_exit_code'] = stop.returncode
            result['server_stopped'] = not (data / 'postmaster.pid').exists()
            if not result['server_stopped']:
                code = 1
            (output / 'postgres-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result.get(key) for key in
                      ['test_exit_code', 'test_schemas_remaining', 'server_stopped', 'error']}))
    log = output / ('postgres-tests.txt' if (output / 'postgres-tests.txt').exists()
                    else 'postgres-lifecycle.txt')
    print('\n'.join(log.read_text().splitlines()[-5:]))
    return code


if __name__ == '__main__':
    sys.exit(main())
