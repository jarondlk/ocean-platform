"""Separate beta API entry and explicitly selected migration operator.

Never receives a DSN in argv or emits it. Configuration checks do not attest
live connector routing or IAM: those remain deployment acceptance gates.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

PROJECT = 'ocean-v1-beta-20261101'
DATABASE = 'ocean_v1_beta'
HEAD = '20261027_0021'
ROOT = Path(__file__).resolve().parent
EXECUTION_FLAGS = (
    'ENABLE_V1_RESEARCH_CONTROLLER', 'ENABLE_V1_RESEARCH_DISPATCH',
    'ENABLE_V1_SYNTHESIS', 'ENABLE_V1_EXPERIMENT_DISPATCH',
)


class EntryError(ValueError):
    """A diagnostic that must never embed credentials or untrusted input."""


def validate_environment(env, *, migration=False):
    """Validate explicit beta identity before importing application config."""
    from sqlalchemy.engine import make_url

    if env.get('DEPLOYMENT_ENV') != 'production' or env.get('OCEAN_V1_PROJECT_ID') != PROJECT:
        raise EntryError('Explicit production beta project required')
    if any(env.get(name, 'false').strip().lower() != 'false' for name in EXECUTION_FLAGS):
        raise EntryError('Execution flags must remain false')
    if 'DATABASE_URL' in env:
        raise EntryError('Ambient database configuration must be absent')
    if migration and 'config' in sys.modules:
        raise EntryError('Migration operator requires a fresh process')
    try:
        dsn = env['OCEAN_V1_DATABASE_URL']
        url = make_url(dsn)
        connection_name = env['OCEAN_V1_SQL_CONNECTION_NAME']
        if not re.fullmatch(re.escape(PROJECT) + r':asia-northeast1:ocean-v1-beta-[a-z0-9-]+', connection_name):
            raise ValueError()
        if url.drivername != 'postgresql+psycopg2' or url.database != DATABASE:
            raise ValueError()
        expected_user = env['OCEAN_V1_DATABASE_USER']
        if (not re.fullmatch(r'ocean_v1_[a-z0-9_]+', expected_user)
                or url.username != expected_user or not url.password):
            raise ValueError()
        if migration and expected_user != 'ocean_v1_migrator':
            raise ValueError()
        if not set(url.query) <= {'host', 'sslmode'}:
            raise ValueError()
        socket = url.query.get('host')
        if socket is not None:
            if url.host not in {None, ''} or socket != '/cloudsql/' + connection_name or url.port is not None:
                raise ValueError()
        elif url.host not in {'127.0.0.1', 'localhost'} or url.port is None or not 1 <= url.port <= 65535:
            raise ValueError()
    except Exception:
        raise EntryError('Explicit independent PostgreSQL target required') from None
    return dsn, expected_user


def validate_serving_source(env):
    try:
        path = Path(env['OCEAN_V1_HOST_CONFIG'])
        if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            raise ValueError()
        configuration = json.loads(path.read_text())
        manifest = json.loads((ROOT / 'source-manifest.json').read_text())
        if (manifest['version'] != 'ocean-v1-beta-api-context-v1'
                or manifest['project_id'] != PROJECT
                or not re.fullmatch(r'[a-f0-9]{40}', manifest['revision'])
                or configuration['revision'] != manifest['revision']
                or configuration['project_id'] != PROJECT
                or configuration['database_name'] != DATABASE):
            raise ValueError()
    except Exception:
        raise EntryError('Host configuration must match the packaged beta source identity') from None


def migrate(env, *, confirm_project, confirm_database, check_only=False):
    if confirm_project != PROJECT or confirm_database != DATABASE:
        raise EntryError('Exact beta migration confirmations required')
    dsn, expected_user = validate_environment(env, migration=True)
    if check_only:
        print('Beta migration configuration validated; no database connection or migration attempted')
        return
    # Read the actual identity using the same immutable URL before any DDL.
    from sqlalchemy import create_engine, text
    engine = create_engine(dsn, connect_args={'connect_timeout': 10})
    try:
        with engine.connect() as connection:
            actual = connection.execute(text('SELECT current_database(), current_user')).one()
            if tuple(actual) != (DATABASE, expected_user):
                raise EntryError('Live migration database identity mismatch')
    except EntryError:
        raise
    except Exception:
        raise EntryError('Independent migration database preflight failed') from None
    finally:
        engine.dispose()
    # Existing migrations/env.py intentionally reads config.DATABASE_URL.
    # Set it only in this explicitly selected, validated operator process.
    os.environ['DATABASE_URL'] = dsn
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    configuration = Config(str(ROOT / 'alembic.ini'))
    configuration.set_main_option('script_location', str(ROOT / 'migrations'))
    if ScriptDirectory.from_config(configuration).get_heads() != [HEAD]:
        raise EntryError('Packaged migration head does not match the reviewed target')
    try:
        command.upgrade(configuration, HEAD)
    except Exception:
        raise EntryError('Beta migration failed; retain operator logs and inspect the unchanged target') from None
    print('Beta migration completed to the reviewed head; record live schema and history acceptance separately')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('serve')
    operator = commands.add_parser('migrate')
    operator.add_argument('--confirm-project', required=True)
    operator.add_argument('--confirm-database', required=True)
    operator.add_argument('--check-only', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.operation == 'serve':
            validate_environment(os.environ)
            validate_serving_source(os.environ)
            # exec preserves signals, has no shell and runs only the separate factory.
            os.execv(sys.executable, [sys.executable, '-m', 'uvicorn',
                'api.v1_host:create_from_environment', '--factory', '--host', '127.0.0.1',
                '--port', '8000', '--workers', '1', '--no-proxy-headers', '--no-access-log'])
        else:
            migrate(os.environ, confirm_project=args.confirm_project,
                confirm_database=args.confirm_database, check_only=args.check_only)
    except EntryError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
