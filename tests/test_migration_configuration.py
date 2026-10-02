"""Cloud SQL's encoded socket URL survives Alembic configuration unchanged."""
import io

from alembic import command
from alembic.config import Config

import config


def test_encoded_database_url_round_trips_without_interpolation_or_credential_output(monkeypatch):
    url = 'postgresql://migration_user:synthetic%25password@localhost/ocean?host=%2Fcloudsql%2Ftest%3Aregion%3Ainstance'
    monkeypatch.setattr(config, 'DATABASE_URL', url)
    output = io.StringIO()
    settings = Config('alembic.ini', output_buffer=output)
    command.upgrade(settings, '20260925_0013:head', sql=True)
    assert settings.get_main_option('sqlalchemy.url') == url
    assert settings.get_section(settings.config_ini_section)['sqlalchemy.url'] == url
    assert 'freshness_unavailable' in output.getvalue()
    assert 'synthetic' not in output.getvalue()
    assert 'postgresql://' not in output.getvalue()
