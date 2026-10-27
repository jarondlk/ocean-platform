"""Explicitly gated C23 disposable PostgreSQL with real restricted LOGIN roles.

Never starts a service, installs PostgreSQL, creates a database, discovers an
application URL or connects without RUN_C23_POSTGRES_INTEGRATION=1. An operator
must supply an already owned ocean_c23_* loopback database and admin test login.
"""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker

from orchestration.experiment_sandbox.execution_store import ExecutionRolePolicy, bootstrap_execution_roles

ROOT = Path(__file__).resolve().parents[1]


def configured_disposable_url():
    raw = os.environ.get('C23_TEST_DATABASE_URL')
    if not raw:
        raise ValueError('Explicit C23_TEST_DATABASE_URL required; DATABASE_URL is never used')
    try:
        url = make_url(raw)
    except ArgumentError as error:
        raise ValueError('C23 target must be a dedicated PostgreSQL URL') from error
    if (url.get_backend_name() != 'postgresql' or url.host not in {'localhost','127.0.0.1','::1'}
            or not re.fullmatch(r'ocean_c23_[a-z0-9_]+', url.database or '') or url.query):
        raise ValueError('C23 target must be a dedicated ocean_c23_* loopback database without overrides')
    return url


def alembic(database, action, target, *, succeeds=True):
    child = dict(os.environ)
    child.update(DATABASE_URL=database['url'].update_query_dict({'options': database['options']}).render_as_string(hide_password=False),
        AUTH_MODE='disabled', DEPLOYMENT_ENV='test', ENABLE_MOCK_LOGIN='false', PERSIST_LOCAL_CHAT='false')
    result = subprocess.run([sys.executable,'-m','alembic',action,target], cwd=ROOT, env=child,
        capture_output=True, text=True, timeout=90, check=False)
    assert (result.returncode == 0) == succeeds, 'C23 migration outcome mismatch: ' + result.stderr
    return result


@pytest.fixture(scope='module')
def disposable_database():
    if os.environ.get('RUN_C23_POSTGRES_INTEGRATION') != '1':
        pytest.skip('Explicit owned C23 PostgreSQL acceptance not enabled')
    try:
        url = configured_disposable_url()
    except ValueError as error:
        pytest.fail(str(error))
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            identity = connection.execute(text('SELECT current_database(),host(inet_server_addr()),'
                "current_setting('transaction_isolation'),(SELECT rolsuper FROM pg_roles WHERE rolname=current_user)")).one()
            assert identity[0] == url.database and ipaddress.ip_address(identity[1]).is_loopback
            assert identity[2] == 'read committed'
            assert identity[3] is True, 'Disposable role fixtures require an explicitly supplied test admin'
        yield engine, url
    finally:
        engine.dispose()


@pytest.fixture
def isolated(disposable_database):
    observer, url = disposable_database
    schema = 'c23_' + uuid.uuid4().hex
    with observer.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA {schema}')
    options = f'-csearch_path={schema} -clock_timeout=8000 -cstatement_timeout=20000'
    engine = create_engine(url, pool_pre_ping=True, connect_args={'options': options})
    case = {'engine': engine, 'observer': observer, 'url': url, 'schema': schema, 'options': options}
    try:
        yield case
    finally:
        engine.dispose()
        with observer.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
            assert not connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:s)'), {'s':schema})


@pytest.fixture
def role_database(isolated):
    alembic(isolated,'upgrade','20261027_0021')
    suffix = uuid.uuid4().hex[:16]
    policy = ExecutionRolePolicy(*(f'c23_{kind}_{suffix}' for kind in ('serving','controller','verifier','owner')))
    names = [getattr(policy, field) for field in policy.__dataclass_fields__]
    passwords = {name: secrets.token_hex(32) for name in names[:-1]}
    engines = {}
    try:
        with isolated['engine'].begin() as connection:
            for name in names:
                # All identifiers are generated lowercase/hex; secrets are hex.
                login = "LOGIN PASSWORD '" + passwords[name] + "'" if name in passwords else 'NOLOGIN'
                connection.exec_driver_sql(f'CREATE ROLE {name} {login} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
            bootstrap_execution_roles(connection, schema=isolated['schema'], policy=policy)
        for name in names[:-1]:
            engines[name] = create_engine(isolated['url'].set(username=name,password=passwords[name]),
                connect_args={'options': isolated['options']}, pool_pre_ping=True)
            # These are actual separate LOGIN connections, not SET ROLE on a
            # schema-owner connection. No test claims owner forgery resistance.
            with engines[name].connect() as connection:
                assert connection.execute(text('SELECT current_user,session_user')).one() == (name,name)
        yield {**isolated, 'roles':policy, 'role_engines':engines,
            'controller_factory':sessionmaker(bind=engines[policy.controller_role],expire_on_commit=False),
            'recorder_factory':sessionmaker(bind=engines[policy.verifier_role],expire_on_commit=False)}
    finally:
        for engine in engines.values():
            engine.dispose()
        with isolated['engine'].begin() as connection:
            # Functions are retained while tests run, but no random role may
            # survive fixture cleanup even after a populated-downgrade refusal.
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS {isolated["schema"]} CASCADE')
            for name in reversed(names):
                connection.exec_driver_sql(f'DROP OWNED BY {name}')
                connection.exec_driver_sql(f'DROP ROLE {name}')
