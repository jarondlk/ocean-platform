"""Apply C23 offline SQL to an explicitly owned disposable PostgreSQL schema."""
import io
import os

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect, text

import config
from tests import experiment_execution_postgres_support as pg
from tests.integration import test_experiment_execution_postgres as execution_pg

pytestmark = pytest.mark.skipif(os.environ.get('RUN_C23_POSTGRES_INTEGRATION') != '1',
    reason='Requires the explicitly supplied owned disposable C23 database')
disposable_database, isolated, role_database = pg.disposable_database, pg.isolated, pg.role_database
actual = execution_pg.actual


def render(database, monkeypatch, operation, revisions):
    url = database['url'].update_query_dict({'options': database['options']})
    monkeypatch.setattr(config, 'DATABASE_URL', url.render_as_string(hide_password=False))
    output = io.StringIO()
    getattr(command, operation)(Config('alembic.ini', output_buffer=output), revisions, sql=True)
    return output.getvalue()


def apply(database, sql):
    with database['engine'].connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        try:
            connection.exec_driver_sql(sql)
        except Exception:
            connection.exec_driver_sql('ROLLBACK')
            raise


def function_state(database):
    with database['engine'].connect() as connection:
        rows = connection.execute(text('SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p '
            'JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=:schema '
            "AND (p.proname LIKE 'ocean_c23_%' OR p.proname='ocean_research_experiment_reservation_guard') ORDER BY p.proname"),
            {'schema': database['schema']}).all()
    return rows


def test_offline_upgrade_matches_online_objects_and_empty_downgrade(isolated, monkeypatch):
    pg.alembic(isolated, 'upgrade', '20261027_0021')
    online_functions = function_state(isolated)
    online_tables = set(inspect(isolated['engine']).get_table_names())
    pg.alembic(isolated, 'downgrade', '20261020_0020')
    apply(isolated, render(isolated, monkeypatch, 'upgrade', '20261020_0020:20261027_0021'))
    assert function_state(isolated) == online_functions
    assert set(inspect(isolated['engine']).get_table_names()) == online_tables
    apply(isolated, render(isolated, monkeypatch, 'downgrade', '20261027_0021:20261020_0020'))
    assert not any(name.startswith('research_experiment_execution')
                   for name in inspect(isolated['engine']).get_table_names())
    with isolated['engine'].connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '20261020_0020'


def test_offline_populated_downgrade_rolls_back_and_preserves_immutable_history(actual, monkeypatch):
    binding = execution_pg.prepared(actual)
    store = execution_pg.store_for(actual, binding)
    with store.controller_transaction() as session:
        store.reserve_in_transaction(session, binding)
    database = actual.database
    sql = render(database, monkeypatch, 'downgrade', '20261027_0021:20261020_0020')
    from sqlalchemy.exc import DBAPIError
    with pytest.raises(DBAPIError):
        apply(database, sql)
    with database['engine'].connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '20261027_0021'
        assert connection.scalar(text('SELECT count(*) FROM research_experiment_execution')) > 0
