"""Explicit beta serving configuration for retained experiment reads."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from api.v1_beta_research_host import SITE_ID
from api.v1_host import EXPERIMENT_LEDGER_URL, EXPERIMENT_READ_CONFIG, EXPERIMENT_READ_ENV, HostConfigurationError, _unique
from db.app_models import (ResearchExperiment, ResearchExperimentApproval, ResearchExperimentEvent,
    ResearchExperimentInputBlob, ResearchExperimentReservation, ResearchExperimentRevision,
    ResearchExperimentRevisionFile, ResearchInvestigation)
from ingestion.artifact_store import BoundedGcsStore
from orchestration.experiment_sandbox.ledger_reader import RetainedLedgerReader, RetainedLedgerReaderConfig
from orchestration.experiment_sandbox.proofs import PinnedTerminationIssuer, TerminationVerifierRegistry
from orchestration.experiment_sandbox.retained_output_store import RetainedOutputReader
from orchestration.experiment_sandbox.workspace_projection import RetainedExecutionProjection
from orchestration.experiment_workspace import ExperimentWorkspaceService
from orchestration.frozen_experiment_export import (
    FrozenExperimentExporter, PinnedSourcePublicationPolicy, SourcePublicationDecision,
)
from orchestration.research_experiments import ResearchExperimentError, ResearchExperimentService
from schema.experiment_execution import TerminationIssuerScope
from schema.research_experiments import EnvironmentDescriptor


LEDGER_ROLE = 'ocean_v1_beta_experiment_ledger_reader'
RESULTS_BUCKET = 'ocean-v1-beta-20261101-results'


class BetaReadOnlyExperimentService(ResearchExperimentService):
    read_only = True

    def invoke(self, name, payload, user):
        if name not in {'list', 'get', 'status', 'events'}:
            raise ResearchExperimentError('access_denied', 403)
        return super().invoke(name, payload, user)


@dataclass(frozen=True)
class BetaExperimentReadBindings:
    ledger: RetainedLedgerReader
    results: RetainedOutputReader
    environments: MappingProxyType
    publication: PinnedSourcePublicationPolicy


def _configured_reads(environ):
    path = Path(environ[EXPERIMENT_READ_CONFIG])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('Explicit beta experiment read config required')
    with path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Experiment read configuration exceeds its bound')
    document = json.loads(raw, object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite')))
    if (type(document) is not dict or set(document) != {'version', 'site_id', 'ledger_database', 'ledger_schema',
            'worker_verifiers', 'environments', 'publication'}
            or document['version'] != 'ocean-v1-beta-experiment-reads-v1' or document['site_id'] != SITE_ID
            or not re.fullmatch(r'ocean_v1_beta(?:_[a-z0-9_]+)?', document['ledger_database'])
            or not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', document['ledger_schema'])):
        raise ValueError('Exact beta experiment read configuration required')

    environments = {}
    for raw_environment in document['environments']:
        environment = EnvironmentDescriptor.model_validate(raw_environment)
        if environment.kind != 'linux-gvisor' or environment.identity_sha256 in environments:
            raise ValueError('Explicit real environment identities required')
        environments[environment.identity_sha256] = environment.model_dump(mode='json')
    if not environments:
        raise ValueError('Experiment review requires a retained environment')

    issuers = []
    for item in document['worker_verifiers']:
        if set(item) != {'issuer_id', 'key_id', 'public_key_hex', 'scope'} or not re.fullmatch(r'[a-f0-9]{64}', item['public_key_hex']):
            raise ValueError('Exact public worker pins required')
        scope = TerminationIssuerScope.model_validate(item['scope'])
        if (scope.site_id != SITE_ID or scope.environment_sha256 not in environments
                or scope.image_digest != environments[scope.environment_sha256]['image_digest']):
            raise ValueError('Worker pins must match the current beta site and retained image')
        issuers.append(PinnedTerminationIssuer(issuer_id=item['issuer_id'], key_id=item['key_id'],
            public_key=bytes.fromhex(item['public_key_hex']), scope=scope, trust_scope='retained-operator'))
    registry = TerminationVerifierRegistry(issuers=issuers, trust_scope='retained-operator', enabled=True)

    publication = document['publication']
    if set(publication) != {'policy_id', 'revision', 'decisions'} or not publication['decisions']:
        raise ValueError('Explicit retained publication decisions required')
    decisions = [SourcePublicationDecision(**item) for item in publication['decisions']]
    if any(decision.test_only or 'eligible' not in item for decision, item in zip(decisions, publication['decisions'])):
        raise ValueError('Only explicit beta publication decisions are accepted')
    policy = PinnedSourcePublicationPolicy(policy_id=publication['policy_id'], revision=publication['revision'], decisions=decisions)
    return document, environments, registry, policy


def _ledger_url(environ, database):
    url = make_url(environ[EXPERIMENT_LEDGER_URL])
    connection = environ['OCEAN_V1_SQL_CONNECTION_NAME']
    if (re.fullmatch(r'ocean-v1-beta-20261101:asia-northeast1:ocean-v1-beta-[a-z0-9-]+', connection) is None
            or url.drivername != 'postgresql+psycopg2' or url.database != database or url.username != LEDGER_ROLE
            or not url.password or not set(url.query) <= {'host', 'sslmode'}
            or environ.get('OCEAN_V1_DATABASE_USER') != 'ocean_v1_serving'):
        raise ValueError('Independent beta ledger login required')
    socket = url.query.get('host')
    if socket is not None:
        if url.host not in {None, ''} or url.port is not None or socket != '/cloudsql/' + connection:
            raise ValueError('Explicit beta ledger socket required')
    elif url.host not in {'127.0.0.1', 'localhost'} or url.port != 5432:
        raise ValueError('Private beta SQL proxy required')
    return url


def _verify_c22_read_access(factory):
    with factory.begin() as session:
        identity = session.execute(text('SELECT current_database(),current_user,session_user')).one()
        if tuple(identity) != ('ocean_v1_beta', 'ocean_v1_serving', 'ocean_v1_serving'):
            raise ValueError('Exact beta app SQL identity required')
        if session.scalar(text("SELECT has_function_privilege(current_user, "
                "to_regprocedure('public.ocean_v1_beta_research_owner_lock(uuid)'), 'EXECUTE')")) is not True:
            raise ValueError('Explicit owner-lock capability required')
        for model in (ResearchExperiment, ResearchInvestigation):
            session.execute(select(model).limit(0).with_for_update())
        for model in (ResearchExperimentApproval, ResearchExperimentRevision, ResearchExperimentRevisionFile,
                      ResearchExperimentInputBlob, ResearchExperimentReservation, ResearchExperimentEvent):
            session.execute(select(model).limit(0))


def load_beta_experiment_reads(environ, *, session_factory):
    """Validate current read privileges before enabling the private read port."""
    engine = None
    try:
        if environ.get('OCEAN_V1_CATALOGUE_MODE') != 'sealed-gcs-research-v1' or not EXPERIMENT_READ_ENV <= environ.keys():
            raise ValueError('Explicit beta Research read configuration required')
        document, environments, registry, policy = _configured_reads(environ)
        url = _ledger_url(environ, document['ledger_database'])
        schema = document['ledger_schema']
        engine = create_engine(url, pool_pre_ping=True, connect_args={'connect_timeout': 10,
            'options': f'-csearch_path={schema} -cstatement_timeout=10000'})
        ledger = RetainedLedgerReader(config=RetainedLedgerReaderConfig(site_id=SITE_ID,
            database_name=document['ledger_database'], schema=schema, role=LEDGER_ROLE,
            session_factory=sessionmaker(bind=engine, expire_on_commit=False), verifier_registry=registry))
        with ledger.transaction():
            pass
        _verify_c22_read_access(session_factory)
        results = RetainedOutputReader(BoundedGcsStore(bucket=RESULTS_BUCKET))
        return BetaExperimentReadBindings(ledger, results, MappingProxyType(environments), policy), engine
    except Exception:
        if engine is not None:
            engine.dispose()
        raise HostConfigurationError('Explicit beta experiment reads unavailable') from None


def compose_beta_experiment_reads(investigations, bindings):
    from api.v1_beta_question_services import lock_research_owner

    if type(bindings) is not BetaExperimentReadBindings or investigations.site_id != SITE_ID:
        raise HostConfigurationError('Explicit beta experiment read bindings required')
    exporter = FrozenExperimentExporter(store=investigations.store, catalogue=investigations.catalogue,
        registrations=investigations.registrations, publication_policy=bindings.publication)
    experiments = BetaReadOnlyExperimentService(session_factory=investigations.session_factory,
        site_id=SITE_ID, investigations=investigations, exporter=exporter, environments=bindings.environments,
        owner_locker=lock_research_owner, enabled=lambda: True, dispatch_enabled=lambda: False)
    port = RetainedExecutionProjection(experiments=experiments, ledger_reader=bindings.ledger,
        output_reader=bindings.results)
    return experiments, ExperimentWorkspaceService(experiments=experiments, port=port, enabled=lambda: True)
