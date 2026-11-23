"""Beta read-only workspace configuration and signed-in serving composition."""
import json
from types import MappingProxyType
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from api import v1_beta_experiment_reads as reads
from api.v1_beta_question_services import compose_beta_question_services
from api.v1_host import EXPERIMENT_LEDGER_URL, EXPERIMENT_READ_CONFIG, HostConfigurationError
from api.v1_research_controller_host import create_from_environment as create_controller
from ingestion.artifact_store import BoundedLocalStore
from orchestration.experiment_sandbox.ledger_reader import RetainedLedgerReader, RetainedLedgerReaderConfig
from orchestration.experiment_sandbox.retained_output_store import RetainedOutputReader
from orchestration.research_experiments import ResearchExperimentError
from schema.research_experiments import EnvironmentDescriptor
from tests.test_beta_question_services import context as context, public_app, questions as questions, sealed as sealed
from tests.test_v1_host import headers, independent as independent


@pytest.fixture
def read_configuration(tmp_path):
    descriptor = EnvironmentDescriptor(kind='linux-gvisor', test_only=False,
        python_version='3.12.15', image_digest='sha256:' + 'a' * 64, lockfile_sha256='b' * 64,
        packages=dict.fromkeys(('numpy', 'pandas', 'pyarrow', 'scipy', 'statsmodels', 'matplotlib'), '1.0.0'),
        description='Synthetic descriptor for beta host configuration tests')
    scope = dict.fromkeys(('worker_id', 'source_policy_sha256', 'worker_source_sha256', 'runtime_sha256',
        'profile_policy_sha256', 'trusted_init_sha256', 'adapter_source_sha256'), 'c' * 64)
    scope.update(site_id=reads.SITE_ID, environment_sha256=descriptor.identity_sha256, image_digest=descriptor.image_digest)
    doc = {'version': 'ocean-v1-beta-experiment-reads-v1', 'site_id': reads.SITE_ID,
        'ledger_database': 'ocean_v1_beta_experiments', 'ledger_schema': 'retained',
        'worker_verifiers': [{'issuer_id': 'fixture-worker', 'key_id': 'fixture-key', 'public_key_hex': 'c4' * 32,
                              'scope': scope}],
        'environments': [descriptor.model_dump(mode='json')],
        'publication': {'policy_id': 'fixture', 'revision': '1', 'decisions': [{
            'child_snapshot_id': 'd' * 64, 'dataset_id': 'fixture', 'source_id': 'fixture-source',
            'publication_generation': '1', 'object_sha256': {'fixture': 'e' * 64},
            'decision_reference': 'fixture-review', 'eligible': True}]}}
    path = tmp_path / 'reads.json'
    path.write_text(json.dumps(doc))
    environ = {EXPERIMENT_READ_CONFIG: str(path), 'OCEAN_V1_CATALOGUE_MODE': 'sealed-gcs-research-v1',
        EXPERIMENT_LEDGER_URL: ('postgresql+psycopg2://' + reads.LEDGER_ROLE +
            ':fixture@127.0.0.1:5432/ocean_v1_beta_experiments'),
        'OCEAN_V1_SQL_CONNECTION_NAME': 'ocean-v1-beta-20261101:asia-northeast1:ocean-v1-beta-db',
        'OCEAN_V1_DATABASE_USER': 'ocean_v1_serving'}
    return environ, path, doc


@pytest.mark.parametrize('invalid', ['duplicate', 'wrong-site', 'wrong-image', 'unreviewed', 'test-only'])
def test_rejects_untrusted_read_configuration(read_configuration, invalid):
    environ, path, doc = read_configuration
    reads._configured_reads(environ)
    decision = doc['publication']['decisions'][0]
    if invalid == 'wrong-site':
        doc['worker_verifiers'][0]['scope']['site_id'] = 'v1:other'
    elif invalid == 'wrong-image':
        doc['worker_verifiers'][0]['scope']['image_digest'] = 'sha256:' + 'f' * 64
    elif invalid == 'unreviewed':
        del decision['eligible']
    elif invalid == 'test-only':
        decision['test_only'] = True
    raw = json.dumps(doc)
    if invalid == 'duplicate':
        raw = '{"site_id": "v1:other",' + raw[1:]
    path.write_text(raw)
    with pytest.raises(HostConfigurationError, match='experiment reads unavailable'):
        reads.load_beta_experiment_reads(environ, session_factory=None)


def test_requires_separate_beta_ledger_url_and_sql_boundary(read_configuration):
    environ, _, doc = read_configuration
    original = environ[EXPERIMENT_LEDGER_URL]
    assert reads._ledger_url(environ, doc['ledger_database']).username == reads.LEDGER_ROLE
    for candidate in (original.replace(reads.LEDGER_ROLE, 'ocean_v1_serving'),
                      original.replace('127.0.0.1', 'example.invalid'),
                      original + '?host=/cloudsql/unrelated:asia-northeast1:db'):
        environ[EXPERIMENT_LEDGER_URL] = candidate
        with pytest.raises(ValueError):
            reads._ledger_url(environ, doc['ledger_database'])


def test_failed_ledger_startup_disposes_pool_and_hides_details(read_configuration, monkeypatch):
    environ, _, _ = read_configuration
    engine = Mock()
    monkeypatch.setattr(reads, 'create_engine', lambda *a, **kw: engine)
    monkeypatch.setattr(RetainedLedgerReader, 'transaction', Mock(side_effect=RuntimeError('fixture credential')))
    with pytest.raises(HostConfigurationError, match='^Explicit beta experiment reads unavailable$'):
        reads.load_beta_experiment_reads(environ, session_factory=None)
    engine.dispose.assert_called_once_with()


def test_controller_rejects_serving_read_configuration(read_configuration, monkeypatch):
    environ, _, _ = read_configuration
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(HostConfigurationError, match='Explicit private beta research mode required'):
        create_controller()


def test_signed_in_beta_discovery_only_enables_reads(questions, read_configuration, tmp_path):
    existing, actor, factory, sealed_fixture = questions
    doc, environments, verifier, policy = reads._configured_reads(read_configuration[0])
    ledger = RetainedLedgerReader(config=RetainedLedgerReaderConfig(site_id=reads.SITE_ID,
        database_name=doc['ledger_database'], schema=doc['ledger_schema'], role=reads.LEDGER_ROLE,
        session_factory=lambda: pytest.fail('Discovery must not query the ledger'), verifier_registry=verifier))
    output = tmp_path / 'output'
    output.mkdir()
    bindings = reads.BetaExperimentReadBindings(ledger, RetainedOutputReader(BoundedLocalStore(output)),
        MappingProxyType(environments), policy)
    bundle = compose_beta_question_services(session_factory=factory, catalogue_service=existing.catalogue_service,
        catalogue_browser=existing.catalogue_browser, cloud_settings=existing.cloud_settings,
        model_settings=existing.model_settings, experiment_reads=bindings)
    auth = headers(actor, sub='subject-1')
    with TestClient(public_app((bundle, actor, factory, sealed_fixture)), base_url='http://127.0.0.1:8000') as client:
        response = client.get('/v1/runtime', headers=auth)
        assert response.status_code == 200, response.text
        value = response.json()
        assert value['research_runs']['submit_enabled'] is True
        experiment = value['research_experiments']
        assert experiment['proposal_transport'] == experiment['execution_transport'] == 'http-v1'
        assert experiment['execution_source'] == 'retained-operator'
        assert experiment['artifacts_enabled'] is True
        assert experiment['approval_enabled'] is experiment['start_enabled'] is experiment['cancel_enabled'] is False
        response = client.post('/research/experiment-executions/capability', json={}, headers=auth)
        assert response.status_code == 200, response.text
        assert response.json()['capability']['cancel_enabled'] is False
        for path in ('/research/experiments/create', '/research/experiments/approve', '/internal/experiments/start'):
            assert client.post(path, json={}, headers=auth).status_code == 403
    with pytest.raises(ResearchExperimentError) as denied:
        bundle.research_experiment_service.invoke('create', {}, actor)
    assert denied.value.code == 'access_denied'
