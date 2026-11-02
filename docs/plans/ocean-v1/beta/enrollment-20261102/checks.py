"""Offline crypto/guard and synthetic SQLite transaction checks, not Google/PG proof."""
from __future__ import annotations

import argparse
import ast
from contextlib import redirect_stdout
from dataclasses import replace
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from sqlalchemy import create_engine, func, select

ROOT = Path(__file__).resolve().parents[5]
SOURCE = ROOT / 'deploy/gcp/beta/enrollment/enroll.py'


def run():
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location('enrollment_checks_source', SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    checks = []

    def check(name, condition):
        assert condition, name
        checks.append(name)

    model = ast.parse((ROOT / 'db/app_models.py').read_text())
    user = next(node for node in model.body if isinstance(node, ast.ClassDef) and node.name == 'AppUser')
    columns = {node.targets[0].id for node in user.body if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
        and node.value.func.id == 'Column'}
    check('fixed typed insertion columns match actual AppUser without legacy package import',
        columns == set(module.ACCOUNT_TABLE.c.keys()) and 'config' not in sys.modules)
    auth = ast.parse((ROOT / 'api/auth.py').read_text())
    permissions = next(node.value for node in auth.body if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name) and node.target.id == 'ROLE_PERMISSIONS')
    check('explicit roles match actual authorization role contract',
        module.ROLES == {node.value for node in permissions.keys})

    # These are ephemeral offline test keys/tokens, never Google/SDK credentials.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    now = int(time.time())
    claims = {'iss': 'https://accounts.google.com', 'aud': 'synthetic-client.apps.googleusercontent.com',
        'iat': now - 2, 'exp': now + 3598, 'sub': 'synthetic-google-public-subject',
        'email': 'first-user@fixture.invalid', 'email_verified': True}

    def token(value):
        return jwt.encode(value, key, algorithm='RS256', headers={'kid': 'synthetic-key'})

    def cert_request(url, method='GET', **kwargs):
        assert url == module.CERTS and method == 'GET'
        assert kwargs.get('body') is None
        return SimpleNamespace(status=200, data=json.dumps({'synthetic-key': public}).encode())

    settings = module.Configuration('postgresql+psycopg2://ocean_v1_migrator:synthetic-private-dsn@127.0.0.1:5432/ocean_v1_beta',
        token(claims), claims['email'], claims['aud'], 'b' * 40, 'researcher', 'research')
    identity = module.verify_identity(settings, cert_request)
    check('actual offline RS256 verification resolves exact public subject and email',
        identity.subject == claims['sub'] and identity.email == claims['email'])
    variants = [dict(claims, iss='https://other-issuer.invalid'),
        dict(claims, aud='wrong-client.apps.googleusercontent.com'), dict(claims, aud=[claims['aud']]),
        dict(claims, azp='wrong-presenter.apps.googleusercontent.com'), dict(claims, email_verified=False),
        dict(claims, email_verified='true'), dict(claims, email='other@fixture.invalid'),
        dict(claims, sub=''), dict(claims, sub='x' * 256), dict(claims, sub='bad\nsubject'),
        dict(claims, exp=now - 1), dict(claims, exp=now + 7200),
        dict(claims, iat=now + 60), dict(claims, exp=now + 30)]
    for index, value in enumerate(variants):
        try:
            module.verify_identity(replace(settings, token=token(value)), cert_request)
        except module.EnrollmentError as error:
            check('unsafe signed claim rejected ' + str(index + 1), str(error) == 'Google user identity verification failed')
        else:
            raise AssertionError('unsafe signed identity accepted')
    damaged = settings.token.rsplit('.', 1)[0] + '.' + 'A' * 342
    try:
        module.verify_identity(replace(settings, token=damaged), cert_request)
    except module.EnrollmentError:
        check('invalid signature rejected by actual verifier', True)
    else:
        raise AssertionError('invalid signature accepted')
    for value in ['http://www.googleapis.com/oauth2/v1/certs', 'https://attacker.invalid/certs']:
        try:
            module.GoogleCertRequest()(value)
        except module.EnrollmentError:
            check('foreign certificate destination rejects without network', True)
        else:
            raise AssertionError('foreign cert destination accepted')
    output = io.StringIO()
    with redirect_stdout(output), patch.object(module, 'create_engine', side_effect=AssertionError('DB forbidden')), \
            patch.object(module, 'verify_identity', side_effect=AssertionError('token IO forbidden')), \
            patch.object(module, 'stop_proxy', side_effect=AssertionError('network forbidden')):
        check('default CLI plan returns zero', module.main([]) == 0)
    check('default plan declares no token or DB/network call',
        json.loads(output.getvalue())['database_or_network_calls'] is False)
    with tempfile.TemporaryDirectory(prefix='ocean-enrollment-guards-') as directory:
        root = Path(directory)
        (root / 'enrollment-manifest.json').write_text(json.dumps({
            'version': 'ocean-beta-first-account-package-v1', 'project_id': module.PROJECT,
            'revision': settings.revision, 'api_revision': module.API_REVISION, 'api_image': module.API_IMAGE}))
        (root / 'source-manifest.json').write_text(json.dumps({'version': 'ocean-v1-beta-api-context-v1',
            'project_id': module.PROJECT, 'revision': module.API_REVISION}))
        env = {'DEPLOYMENT_ENV': 'production', 'OCEAN_V1_PROJECT_ID': module.PROJECT,
            'OCEAN_V1_SQL_CONNECTION_NAME': module.CONNECTION,
            'OCEAN_V1_ENROLLMENT_REVISION': settings.revision,
            'OCEAN_V1_ENROLLMENT_DATABASE_URL': settings.dsn,
            'OCEAN_V1_ENROLLMENT_ID_TOKEN': settings.token,
            'OCEAN_V1_ENROLLMENT_EXPECTED_EMAIL': settings.email,
            'OCEAN_V1_ENROLLMENT_EXPECTED_AUDIENCE': settings.audience}
        args = SimpleNamespace(confirm_project=module.PROJECT, confirm_database=module.DATABASE,
            confirm_source=module.API_REVISION, confirm_enrollment=settings.revision,
            role='researcher', account_type='research')
        with patch.object(module, 'ROOT', root):
            check('exact private configuration accepted without token or DB IO', module.configuration(env, args) == settings)
            variants = [dict(env, DATABASE_URL='legacy'), dict(env, OCEAN_V1_PROJECT_ID='data-infra-infobio'),
                dict(env, DEPLOYMENT_ENV='test'), dict(env, ENABLE_V1_RESEARCH_DISPATCH='true'),
                dict(env, OCEAN_V1_ENROLLMENT_DATABASE_URL=settings.dsn.replace('ocean_v1_migrator:', 'postgres:')),
                dict(env, OCEAN_V1_ENROLLMENT_DATABASE_URL=settings.dsn.replace('127.0.0.1', '8.8.8.8')),
                dict(env, OCEAN_V1_ENROLLMENT_DATABASE_URL=settings.dsn + '?options=unsafe'),
                dict(env, OCEAN_V1_ENROLLMENT_DATABASE_URL=settings.dsn.replace('/ocean_v1_beta', '/ocean_platform')),
                dict(env, OCEAN_V1_ENROLLMENT_EXPECTED_EMAIL='service@project.iam.gserviceaccount.com'),
                dict(env, OCEAN_V1_ENROLLMENT_EXPECTED_AUDIENCE='https://beta.oceaninfobio.com')]
            for index, value in enumerate(variants):
                try:
                    module.configuration(value, args)
                except module.EnrollmentError:
                    check('unsafe target/private configuration rejected ' + str(index + 1), True)
                else:
                    raise AssertionError('unsafe target accepted')
            try:
                module.configuration(env, SimpleNamespace(**dict(vars(args), role=None)))
            except module.EnrollmentError:
                check('role has no default or inferred approval', True)
            else:
                raise AssertionError('role omission accepted')
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
            module.ACCOUNT_TABLE.create(connection)
        with patch.object(module, 'database_preflight'):
            with engine.begin() as connection:
                module.insert_first_account(connection, identity, 'researcher', 'research')
                row = connection.execute(select(module.ACCOUNT_TABLE)).one()
                check('actual synthetic SQL insert matches current AppUser contract',
                    row.auth_provider == 'google' and row.auth_subject == identity.subject
                    and row.email == identity.email and row.role == 'researcher' and row.status == 'active')
            try:
                with engine.begin() as connection:
                    module.insert_first_account(connection, identity, 'admin', 'internal')
            except module.EnrollmentError:
                check('existing first account rejects without upsert or role change', True)
            else:
                raise AssertionError('existing account changed')
            with engine.connect() as connection:
                check('refused retry preserves exactly one original role',
                    connection.scalar(select(func.count()).select_from(module.ACCOUNT_TABLE)) == 1
                    and connection.scalar(select(module.ACCOUNT_TABLE.c.role)) == 'researcher')
    finally:
        engine.dispose()
    for failed_proxy in [False, True]:
        output = io.StringIO()
        with patch.object(module, 'configuration', return_value=settings), \
                patch.object(module, 'verify_identity', return_value=identity), \
                patch.object(module, 'enroll', side_effect=RuntimeError(settings.token)), \
                patch.object(module, 'stop_proxy', side_effect=RuntimeError('synthetic') if failed_proxy else None,
                    return_value={'shutdown_requested': True}) as shutdown, redirect_stdout(output):
            result = module.main(['--apply'])
        report = json.loads(output.getvalue())
        check('apply failure finalizes proxy and remains unaccepted ' + str(failed_proxy),
            result == (3 if failed_proxy else 2) and shutdown.call_count == 1
            and report['mutation_may_have_committed'] is True)
        check('private identity/token/DSN absent from application failure output ' + str(failed_proxy),
            all(value not in output.getvalue() for value in [settings.token, settings.dsn, identity.subject, identity.email]))
    return {'version': 'beta-enrollment-offline-checks-v1', 'passed': len(checks), 'checks': checks,
        'real_google_or_sdk_token_acquired': False, 'offline_rsa_fixture_only': True,
        'database_qualification': 'Synthetic SQLite INSERT/first-account semantics only; PostgreSQL preflight mocked',
        'native_postgresql_or_cloud_calls': False, 'actual_user_enrolled': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run()
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'passed': result['passed'], 'real_identity_or_cloud_calls': False,
        'qualification': result['database_qualification']}))
