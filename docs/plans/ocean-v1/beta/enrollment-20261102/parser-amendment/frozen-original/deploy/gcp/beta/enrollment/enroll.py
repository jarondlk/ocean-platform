"""One explicitly approved first beta account; default is an offline plan.

Google ID tokens and DSNs are private environment inputs, never CLI arguments,
SQL values or output. Approved account metadata can enter protected DB diagnostics.
No legacy account import, invitation bypass endpoint, update or upsert exists.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import http.client
import json
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
import urllib.request
import uuid

from google.oauth2 import id_token
import jwt
from sqlalchemy import Column, DateTime, MetaData, String, Table, Uuid, create_engine, func, insert, select, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parent
PROJECT = 'ocean-v1-beta-20261101'
DATABASE = 'ocean_v1_beta'
CONNECTION = PROJECT + ':asia-northeast1:ocean-v1-beta-sql'
API_REVISION = '7924a28e919b1fb751890c694f7b1f9b26b104ff'
API_IMAGE = ('asia-northeast1-docker.pkg.dev/' + PROJECT + '/ocean-v1-beta/api@sha256:'
    'f2e73ca98ba915e29a4dd7dc429e34a165475faa7f9000bc8cefaa10e5a6ee4f')
HEAD = '20261027_0021'
MIGRATOR = 'ocean_v1_migrator'
CERTS = 'https://www.googleapis.com/oauth2/v1/certs'
FLAGS = ('ENABLE_V1_RESEARCH_CONTROLLER', 'ENABLE_V1_RESEARCH_DISPATCH',
    'ENABLE_V1_SYNTHESIS', 'ENABLE_V1_EXPERIMENT_DISPATCH')
ROLES = {'viewer', 'researcher', 'admin'}
ACCOUNT_TYPES = {'research', 'commercial', 'internal'}
# Fixed AppUser contract only. Importing db.app_models would execute db/__init__
# and import the legacy connection/config modules in this separate operator.
# The offline checks compare these columns/roles with the actual accepted model.
ACCOUNT_TABLE = Table('app_user', MetaData(),
    Column('id', Uuid(as_uuid=True), primary_key=True),
    Column('auth_provider', String(64), nullable=False),
    Column('auth_subject', String(255), nullable=False),
    Column('email', String(320), nullable=False), Column('display_name', String(255)),
    Column('role', String(32), nullable=False), Column('account_type', String(32), nullable=False),
    Column('status', String(32), nullable=False), Column('invited_by_user_id', Uuid(as_uuid=True)),
    Column('created_at', DateTime(timezone=True), server_default=func.now()),
    Column('updated_at', DateTime(timezone=True), server_default=func.now()),
    Column('last_login_at', DateTime(timezone=True)), schema='public')


class EnrollmentError(ValueError):
    """Only fixed, private-input-free messages may be emitted."""


@dataclass(frozen=True, repr=False)
class Configuration:
    dsn: str = field(repr=False)
    token: str = field(repr=False)
    email: str = field(repr=False)
    audience: str
    revision: str
    role: str
    account_type: str


@dataclass(frozen=True, repr=False)
class GoogleIdentity:
    subject: str = field(repr=False)
    email: str = field(repr=False)


def normalized_email(value):
    if not isinstance(value, str):
        raise EnrollmentError('Explicit expected account configuration rejected')
    email = value.strip().lower()
    if (len(email) > 320 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email)
            or email.endswith('.gserviceaccount.com')):
        raise EnrollmentError('Explicit expected account configuration rejected')
    return email


def configuration(env, args):
    try:
        if (args.confirm_project != PROJECT or args.confirm_database != DATABASE
                or args.confirm_source != API_REVISION
                or args.role not in ROLES or args.account_type not in ACCOUNT_TYPES
                or env.get('DEPLOYMENT_ENV') != 'production'
                or env.get('OCEAN_V1_PROJECT_ID') != PROJECT
                or env.get('OCEAN_V1_SQL_CONNECTION_NAME') != CONNECTION
                or 'DATABASE_URL' in env or 'config' in sys.modules
                or any(env.get(name, 'false').strip().lower() != 'false' for name in FLAGS)):
            raise ValueError()
        revision = env['OCEAN_V1_ENROLLMENT_REVISION']
        manifest = json.loads((ROOT / 'enrollment-manifest.json').read_text())
        application = json.loads((ROOT / 'source-manifest.json').read_text())
        if (not re.fullmatch(r'[a-f0-9]{40}', revision)
                or args.confirm_enrollment != revision
                or manifest.get('version') != 'ocean-beta-first-account-package-v1'
                or manifest.get('project_id') != PROJECT or manifest.get('revision') != revision
                or manifest.get('api_revision') != API_REVISION or manifest.get('api_image') != API_IMAGE
                or application.get('version') != 'ocean-v1-beta-api-context-v1'
                or application.get('project_id') != PROJECT or application.get('revision') != API_REVISION):
            raise ValueError()
        dsn = env['OCEAN_V1_ENROLLMENT_DATABASE_URL']
        url = make_url(dsn)
        if (url.drivername != 'postgresql+psycopg2' or url.database != DATABASE
                or url.username != MIGRATOR or not url.password or url.host != '127.0.0.1'
                or url.port != 5432 or dict(url.query) not in ({}, {'sslmode': 'disable'})):
            raise ValueError()
        audience = env['OCEAN_V1_ENROLLMENT_EXPECTED_AUDIENCE']
        if not re.fullmatch(r'[A-Za-z0-9-]+\.apps\.googleusercontent\.com', audience):
            raise ValueError()
        token = env['OCEAN_V1_ENROLLMENT_ID_TOKEN']
        if not isinstance(token, str) or not 100 <= len(token) <= 16384 or re.search(r'\s', token):
            raise ValueError()
        return Configuration(dsn, token, normalized_email(env['OCEAN_V1_ENROLLMENT_EXPECTED_EMAIL']),
            audience, revision, args.role, args.account_type)
    except Exception:
        raise EnrollmentError('Exact first-account target, source and private inputs required') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


class GoogleCertRequest:
    """Google-auth transport: fixed public cert GET, no credential transmitted."""
    def __call__(self, url, method='GET', body=None, headers=None, **kwargs):
        if url != CERTS or method != 'GET' or body is not None:
            raise EnrollmentError('Unexpected certificate destination rejected')
        try:
            opener = urllib.request.build_opener(NoRedirect())
            request = urllib.request.Request(CERTS, headers={'Accept': 'application/json'}, method='GET')
            with opener.open(request, timeout=10) as response:
                data = response.read(262145)
                if response.status != 200 or len(data) > 262144:
                    raise ValueError()
                return SimpleNamespace(status=200, data=data)
        except Exception:
            raise EnrollmentError('Google signing certificates unavailable') from None


def verify_identity(settings, request=None):
    try:
        header = jwt.get_unverified_header(settings.token)
        if (header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,255}', header['kid'])):
            raise ValueError()
        claims = id_token.verify_oauth2_token(settings.token, request or GoogleCertRequest(),
            audience=settings.audience, clock_skew_in_seconds=0)
        now = int(time.time())
        if (claims.get('iss') not in {'accounts.google.com', 'https://accounts.google.com'}
                or claims.get('aud') != settings.audience
                or claims.get('azp', settings.audience) != settings.audience
                or claims.get('email_verified') is not True
                or normalized_email(claims.get('email')) != settings.email
                or type(claims.get('iat')) is not int or type(claims.get('exp')) is not int
                or not 0 < claims['exp'] - claims['iat'] <= 3600
                or not 0 <= now - claims['iat'] <= 3600 or claims['exp'] - now < 60
                or not isinstance(claims.get('sub'), str)
                or not re.fullmatch(r'[\x21-\x7e]{1,255}', claims['sub'])
                or 'google.compute_engine' in claims):
            raise ValueError()
        return GoogleIdentity(claims['sub'], settings.email)
    except Exception:
        raise EnrollmentError('Google user identity verification failed') from None


def database_preflight(connection):
    if connection.dialect.name != 'postgresql':
        raise EnrollmentError('First-account enrollment requires the independent PostgreSQL target')
    if tuple(connection.execute(text('SELECT current_database(),current_user,session_user')).one()) != (
            DATABASE, MIGRATOR, MIGRATOR):
        raise EnrollmentError('Independent enrollment database or principal mismatch')
    version = int(connection.scalar(text("SELECT current_setting('server_version_num')")))
    if not 160000 <= version < 170000:
        raise EnrollmentError('Reviewed Cloud SQL PostgreSQL16 target required')
    if connection.execute(text('SELECT version_num FROM public.alembic_version')).scalars().all() != [HEAD]:
        raise EnrollmentError('Exact reviewed migration head required')
    if connection.scalar(text("SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user")) is not False:
        raise EnrollmentError('Restricted migrator principal required')
    if connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user) OR roleid=(SELECT oid FROM pg_roles WHERE rolname=current_user))')):
        raise EnrollmentError('Enrollment principal must have no memberships or members')
    connection.exec_driver_sql('LOCK TABLE public.app_user, public.user_invitation IN ACCESS EXCLUSIVE MODE')
    if connection.scalar(text("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.app_user'::regclass")) != MIGRATOR:
        raise EnrollmentError('Reviewed independent account-table ownership required')
    columns = set(connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='app_user'")).scalars())
    if columns != set(ACCOUNT_TABLE.columns.keys()):
        raise EnrollmentError('Account-table column inventory drift detected')
    if connection.scalar(text('SELECT EXISTS(SELECT 1 FROM public.user_invitation)')):
        raise EnrollmentError('First-account enrollment refuses existing invitation state')


def insert_first_account(connection, identity, role, account_type):
    if not isinstance(identity, GoogleIdentity) or role not in ROLES or account_type not in ACCOUNT_TYPES:
        raise EnrollmentError('Explicit verified account and selected role required')
    database_preflight(connection)
    if connection.scalar(select(func.count()).select_from(ACCOUNT_TABLE)) != 0:
        raise EnrollmentError('First-account enrollment refuses existing account or subject state')
    account_id = uuid.uuid4()
    connection.execute(insert(ACCOUNT_TABLE).values(id=account_id, auth_provider='google',
        auth_subject=identity.subject, email=identity.email, display_name=None, role=role,
        account_type=account_type, status='active', invited_by_user_id=None, last_login_at=None))
    if connection.scalar(select(func.count()).select_from(ACCOUNT_TABLE)) != 1:
        raise EnrollmentError('Exactly one independent account was not established')
    return account_id


def enroll(settings, identity):
    engine = create_engine(settings.dsn, hide_parameters=True, pool_pre_ping=True,
        connect_args={'connect_timeout': 10, 'options': '-c statement_timeout=30000 -c lock_timeout=10000'})
    try:
        with engine.begin() as connection:
            account_id = insert_first_account(connection, identity, settings.role, settings.account_type)
        engine.dispose()
        with engine.connect() as connection:
            if tuple(connection.execute(text('SELECT current_database(),current_user,session_user')).one()) != (
                    DATABASE, MIGRATOR, MIGRATOR):
                raise EnrollmentError('Committed account readback target mismatch')
            c = ACCOUNT_TABLE.c
            rows = connection.execute(select(c.id, c.auth_provider, c.auth_subject,
                c.email, c.role, c.account_type, c.status)).all()
            if len(rows) != 1 or tuple(rows[0]) != (account_id, 'google', identity.subject,
                    identity.email, settings.role, settings.account_type, 'active'):
                raise EnrollmentError('Committed first-account readback did not match')
        return {'account_count': 1, 'provider': 'google', 'role': settings.role,
            'account_type': settings.account_type, 'status': 'active', 'identity_verified': True,
            'subject_or_token_exported': False}
    finally:
        engine.dispose()


def stop_proxy():
    for attempt in range(3):
        client = http.client.HTTPConnection('127.0.0.1', 9091, timeout=3)
        try:
            client.request('POST', '/quitquitquit', body=b'', headers={'Content-Length': '0'})
            response = client.getresponse()
            response.read(4096)
            if 200 <= response.status < 300:
                return {'shutdown_requested': True, 'actual_process_exit': 'requires execution evidence'}
        except (OSError, http.client.HTTPException):
            pass
        finally:
            client.close()
        if attempt < 2:
            time.sleep(0.5)
    raise EnrollmentError('Private proxy shutdown was not acknowledged')


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise EnrollmentError('Explicit first-account invocation required')

    argv = sys.argv[1:] if argv is None else argv
    applying = '--apply' in argv
    report = {'version': 'beta-first-account-result-v1', 'state': 'failed',
        'project_id': PROJECT, 'database': DATABASE, 'mutation_may_have_committed': False}
    code = 2
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--apply', action='store_true')
        for name in ['project', 'database', 'source', 'enrollment']:
            parser.add_argument('--confirm-' + name)
        parser.add_argument('--role')
        parser.add_argument('--account-type')
        args = parser.parse_args(argv)
        if not args.apply:
            print(json.dumps({'state': 'plan_only', 'project_id': PROJECT, 'database': DATABASE,
                'accounts_to_insert': 1, 'explicit_role_and_account_type_required': True,
                'token_acquisition': False, 'database_or_network_calls': False}))
            return 0
        settings = configuration(os.environ, args)
        identity = verify_identity(settings)
        report['enrollment_revision'] = settings.revision
        report['mutation_may_have_committed'] = True
        report['result'] = enroll(settings, identity)
        report['state'], code = 'first_account_enrolled', 0
    except EnrollmentError as error:
        report['error'] = str(error)
    except Exception:
        report['error'] = 'First-account enrollment failed; inspect protected target metadata before recovery'
    finally:
        if applying:
            try:
                report['proxy'] = stop_proxy()
            except Exception:
                report['state'], code = 'failed_proxy_shutdown', 3
                report['proxy'] = {'shutdown_requested': False}
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
