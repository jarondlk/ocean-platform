"""C23 SQL rendering without a connection; no database or runtime is started."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = 'migrations/versions/20261027_0021_experiment_execution.py'
ORIGINAL = ROOT / 'docs/plans/ocean-v1/evidence/C23/execution-store-preparation-20261027/native03-final/source' / MIGRATION


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def online_statements(module, schema, operation):
    statements = []
    bind = SimpleNamespace(dialect=postgresql.dialect(), exec_driver_sql=lambda sql:
        SimpleNamespace(scalar_one=lambda: schema if sql == 'SELECT current_schema()' else False))
    module.op = SimpleNamespace(get_bind=lambda: bind,
        get_context=lambda: SimpleNamespace(as_sql=False), execute=statements.append,
        drop_table=lambda name: statements.append(('drop_table', name)))
    getattr(module, operation)()
    return statements


@pytest.mark.parametrize('schema', ['c23_operator', 'Mixed schema"quote'])
@pytest.mark.parametrize('operation', ['upgrade', 'downgrade'])
def test_online_sql_is_exactly_the_accepted_original(schema, operation):
    original = load(ORIGINAL, 'accepted_c23_migration')
    current = load(ROOT / MIGRATION, 'current_c23_migration')
    assert online_statements(current, schema, operation) == online_statements(original, schema, operation)


@pytest.mark.parametrize('operation', ['upgrade', 'downgrade'])
def test_offline_rendering_never_queries_or_guesses_a_schema(operation):
    module = load(ROOT / MIGRATION, 'offline_c23_migration')
    statements = []
    module.op = SimpleNamespace(get_context=lambda: SimpleNamespace(as_sql=True),
        get_bind=lambda: pytest.fail('Offline generation contacted a database'), execute=statements.append)
    module._schema = lambda: pytest.fail('Offline generation queried a schema')
    getattr(module, operation)()
    assert len(statements) == 1
    sql = statements[0]
    assert sql.startswith('DO $c23_offline$')
    assert 'target_schema text := current_schema()' in sql
    assert "quote_ident(target_schema)" in sql
    assert "'public'" not in sql
    if operation == 'downgrade':
        assert sql.count('ACCESS EXCLUSIVE MODE') == 5
        assert sql.index('ACCESS EXCLUSIVE MODE') < sql.index('INTO has_rows') < sql.index('DROP TABLE')
        assert 'Cannot downgrade populated C23 execution history' in sql


def test_fixed_sql_delimiters_cannot_be_injected():
    module = load(ROOT / MIGRATION, 'delimiter_c23_migration')
    for delimiter in ('$c23_ddl$', '$c23_offline$'):
        with pytest.raises(ValueError):
            module._offline_block(['SELECT ' + delimiter])
