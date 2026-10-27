"""Local C23 storage contracts; these tests supply no PostgreSQL/Linux evidence."""
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from db.experiment_execution_models import EXECUTION_MODELS, IDENTITY_HASH_FIELDS
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.execution_store import (
    C23ExecutionStore, ExecutionReservationBinding, ExecutionRolePolicy,
    ExecutionStoreConfig, bootstrap_execution_roles, execution_job_id,
    planned_reservation_ids,
)
from orchestration.experiment_sandbox.proofs import TerminationVerifierRegistry
from tests.test_experiment_sandbox_proofs import _claims, _issuer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]


def migration():
    spec = importlib.util.spec_from_file_location('c23_migration', ROOT / 'migrations/versions/20261027_0021_experiment_execution.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configuration(**changes):
    claims = _claims()
    key = Ed25519PrivateKey.generate()
    registry = TerminationVerifierRegistry(issuers=[_issuer(key, claims)], trust_scope='synthetic-software-test')
    values = dict(site_id=claims.binding.site_id, database_name='ocean_c23_unit', schema='c23_unit',
        controller_session_factory=lambda: None, recorder_session_factory=lambda: None,
        roles=ExecutionRolePolicy('c23_serving','c23_controller','c23_verifier','c23_owner'),
        verifier_registry=registry, store_scope='isolated-unmounted-operator')
    values.update(changes)
    return ExecutionStoreConfig(**values)


def binding():
    data = _claims().binding.model_dump(exclude={'closed_fence','host_boot_id','journal_id','journal_epoch','profile_sha256'})
    data.update(idempotency_key='one-operation', request_json='{}', envelope_json='{}')
    data['execution_request_sha256'] = data['envelope_sha256'] = hashlib.sha256(b'{}').hexdigest()
    data['execution_id'], data['reservation_id'] = planned_reservation_ids(site_id=data['site_id'],
        owner_user_id=data['owner_user_id'], idempotency_key=data['idempotency_key'])
    data['job_id'] = execution_job_id(site_id=data['site_id'], reservation_id=data['reservation_id'],
                                     envelope_sha256=data['envelope_sha256'])
    return ExecutionReservationBinding.model_validate(data)


def test_explicit_default_off_configuration_never_discovers_database(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://production/must_not_connect')
    config = configuration()
    assert config.enabled() is False
    with pytest.raises(SandboxError, match='sandbox_execution_store_disabled'):
        with C23ExecutionStore(config=config).controller_transaction():
            pytest.fail('Disabled store yielded a transaction')
    with pytest.raises(ValueError):
        replace(config, store_scope='shared-serving')
    with pytest.raises(ValueError):
        replace(config, recorder_session_factory=config.controller_session_factory)
    with pytest.raises(ValueError):
        ExecutionRolePolicy('same','same','verifier','owner')
    with pytest.raises(ValueError):
        replace(config, schema='public; SELECT 1')


def test_binding_preserves_canonical_bytes_and_stable_operation_identity():
    value = binding()
    assert set(IDENTITY_HASH_FIELDS) <= set(ExecutionReservationBinding.model_fields)
    assert value == ExecutionReservationBinding.model_validate(value.model_dump())
    for changes in ({'execution_id': str(uuid.uuid4())}, {'reservation_id': str(uuid.uuid4())},
                    {'job_id': 'c23-' + 'f' * 48}, {'request_json': '{ }'},
                    {'envelope_sha256': '0' * 64}, {'authenticated': True}):
        with pytest.raises(ValidationError):
            ExecutionReservationBinding.model_validate({**value.model_dump(), **changes})


def test_supplied_controller_session_cannot_bypass_explicit_factory_token():
    store = C23ExecutionStore(config=configuration(enabled=lambda: True))
    session = SimpleNamespace(info={}, in_transaction=lambda: True)
    with pytest.raises(SandboxError, match='sandbox_execution_controller_transaction'):
        store.reserve_in_transaction(session, binding())
    with pytest.raises(SandboxError, match='sandbox_termination_unverified'):
        store.record_verified_termination(execution_id=binding().execution_id, packet_bytes={'authenticated': True})


def test_store_rejects_sqlite_as_native_security_boundary():
    store = C23ExecutionStore(config=configuration())
    session = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name='sqlite')))
    with pytest.raises(SandboxError, match='sandbox_execution_postgresql_required'):
        store._check_session(session, 'c23_controller')
    with pytest.raises(ValueError):
        bootstrap_execution_roles(SimpleNamespace(dialect=SimpleNamespace(name='sqlite')),
                                  schema='c23_unit', policy=configuration().roles)


def test_static_migration_ddl_matches_new_models_without_importing_them_at_migration_time():
    module = migration()
    assert module.revision == '20261027_0021' and module.down_revision == '20261020_0020'
    assert module.TABLE_DDL == tuple(str(CreateTable(model.__table__).compile(dialect=postgresql.dialect())).strip() for model in EXECUTION_MODELS)
    source = (ROOT / 'migrations/versions/20261027_0021_experiment_execution.py').read_text()
    assert 'from db.' not in source and 'CREATE ROLE' not in source
    for model in EXECUTION_MODELS:
        assert all(fk.ondelete == 'RESTRICT' for fk in model.__table__.foreign_key_constraints)
    assert all(column.name != 'released_at' for model in EXECUTION_MODELS for column in model.__table__.columns)


def test_0020_reservation_guard_restoration_is_exact():
    import ast
    old_source = (ROOT / 'migrations/versions/20261020_0020_research_experiments.py').read_text()
    old_guard = next(node.args[0].value for node in ast.walk(ast.parse(old_source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'execute'
        and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
        and node.args[0].value.startswith('CREATE FUNCTION ocean_research_experiment_reservation_guard()'))
    assert migration().OLD_RESERVATION_GUARD == old_guard.replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1)


def test_downgrade_checks_all_tables_before_drop_and_restores_guard(monkeypatch):
    module = migration()
    calls = []
    bind = SimpleNamespace(dialect=SimpleNamespace(identifier_preparer=SimpleNamespace(quote_schema=lambda x: '"' + x + '"')),
        exec_driver_sql=lambda sql: SimpleNamespace(scalar_one=lambda: 'c23_test' if 'current_schema' in sql else False))
    monkeypatch.setattr(module, 'op', SimpleNamespace(get_bind=lambda: bind,
        execute=lambda sql: calls.append(sql), drop_table=lambda table: calls.append('DROP ' + table)))
    module.downgrade()
    assert sum('ACCESS EXCLUSIVE' in call for call in calls) == 5
    assert calls[5].startswith('CREATE OR REPLACE FUNCTION "c23_test".ocean_research_experiment_reservation_guard')
    assert calls[6].startswith('DROP TRIGGER c23_outbox_insert_guard')


def test_populated_downgrade_refuses_without_dropping(monkeypatch):
    module = migration()
    calls = []
    bind = SimpleNamespace(dialect=SimpleNamespace(identifier_preparer=SimpleNamespace(quote_schema=lambda x: x)),
        exec_driver_sql=lambda sql: SimpleNamespace(scalar_one=lambda: 'c23_test' if 'current_schema' in sql else True))
    monkeypatch.setattr(module, 'op', SimpleNamespace(get_bind=lambda: bind,
        execute=lambda sql: calls.append(sql), drop_table=lambda table: calls.append('DROP ' + table)))
    with pytest.raises(RuntimeError, match='populated C23'):
        module.downgrade()
    assert len(calls) == 5 and all('ACCESS EXCLUSIVE' in call for call in calls)
