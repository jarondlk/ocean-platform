"""C26 independent actual-service acceptance and honest integration failures."""
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

from db.app_models import AppBase
from schema.system_acceptance import ControllerObservation
from tests.system_acceptance_support import make_system_acceptance_fixture, run_integrated_acceptance


@pytest.fixture(scope='module')
def retained(tmp_path_factory):
    directory = tmp_path_factory.mktemp('c26-shared-actual-services')
    engine = create_engine('sqlite+pysqlite:///' + str(directory / 'independent-app.sqlite'))
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    AppBase.metadata.create_all(engine)
    fixture = make_system_acceptance_fixture(engine, directory)
    yield fixture
    engine.dispose()


@pytest.fixture
def actual(retained, monkeypatch):
    for name in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS', 'ENABLE_V1_RESEARCH_CONTROLLER'):
        monkeypatch.setenv(name, 'true')
    monkeypatch.setenv('DEPLOYMENT_ENV', 'test')
    retained.state['runtime'] = None
    retained.experiments.state.update(enabled=True, dispatch_enabled=True)
    for values in retained.retained.policy.values():
        values.clear()
    return retained


def test_shared_stack_exports_actual_service_evidence_and_attachment_regression(actual):
    report = run_integrated_acceptance(actual)
    output = os.environ.get('C26_INTEGRATED_CAPTURE')
    if output:
        with Path(output).open('x') as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False)
    by_id = {row['id']: row for row in report['checks']}
    assert by_id['shared-context-inventory-answer']['status'] == 'passed'
    assert by_id['experimental-bytes-and-approval']['status'] == 'passed'
    attached = by_id['research-and-experiment-attachment-composition']
    assert attached['status'] == 'passed'
    assert attached['evidence']['resolver_validates'] is True
    assert attached['observed']['available'] is True
    assert attached['evidence']['protection'] == 'ResearchEvidenceService'
    for row in report['checks']:
        assert row['status'] == 'passed', json.dumps(row, ensure_ascii=False)
    assert report['fixture']['live_calls_performed'] is False
    assert ControllerObservation.model_validate(report['comparison_observations'][0]).inventory_state == 'complete'
