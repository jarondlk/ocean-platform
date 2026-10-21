"""C22 synthetic publication decisions over actual sealed C09/C13/C17 services."""
from dataclasses import dataclass
import uuid

from sqlalchemy import select

from db.app_models import ResearchExperimentCapacity
from ingestion.scientific_catalogue_inputs import load_registry
from orchestration.frozen_experiment_export import (
    FrozenExperimentExporter, PinnedSourcePublicationPolicy, SourcePublicationDecision,
)
from orchestration.research_experiments import FakeExperimentExecutor, ResearchExperimentService
from schema.research_experiments import EnvironmentDescriptor
from tests.investigation_support import make_investigation_fixture


@dataclass
class ExperimentFixture:
    retained: object
    service: ResearchExperimentService
    exporter: FrozenExperimentExporter
    executor: FakeExperimentExecutor
    environment: EnvironmentDescriptor
    state: dict

    @property
    def investigations(self):
        return self.retained.service

    @property
    def factory(self):
        return self.retained.factory

    @property
    def user(self):
        return self.retained.user

    @property
    def other(self):
        return self.retained.other

    @property
    def admin(self):
        return self.retained.admin

    def request(self, *, user=None):
        actor = user or self.user
        created = self.investigations.invoke('create', {'name': 'C22 synthetic proposal',
            'snapshot_id': self.retained.snapshots[0], 'scope': self.retained.scope,
            'idempotency_key': str(uuid.uuid4())}, actor)
        conversation = self.investigations.invoke('conversations/create', {
            'investigation_id': created['investigation']['id'], 'name': 'C22 private review',
            'idempotency_key': str(uuid.uuid4())}, actor)['conversation']
        return {'investigation_id': created['investigation']['id'], 'conversation_id': conversation['id'],
            'context_revision_id': created['context']['id'], 'snapshot_id': created['context']['snapshot_id'],
            'context_payload_sha256': created['context']['payload_sha256'], 'idempotency_key': str(uuid.uuid4()),
            'proposal': {'question': 'Explore synthetic CTD casts without claiming a scientific result',
                'cohort': {'selections': [{'kind': 'dataset', 'target_id': self.retained.dataset_ids['ctd'],
                    'table': 'casts', 'columns': ['cast_id']}]},
                'method': 'Review a complete frozen synthetic cast identity table',
                'assumptions': ['Synthetic source only; not an independent scientific approval'],
                'python_code': '# Stored for owner review only; C22 never executes Python.\nprint("synthetic")\n',
                'expected_outputs': [{'name': 'summary.json', 'kind': 'table', 'description': 'Future experimental summary'}],
                'environment_id': self.environment.identity_sha256,
                'limitations': ['Fake dispatch performs no execution and produces no scientific output'], 'seeds': {'numpy': 7}}}

    def create(self, *, user=None):
        return self.service.invoke('create', self.request(user=user), user or self.user)['experiment']

    @staticmethod
    def address(experiment):
        return {'experiment_id': experiment['id']}

    @staticmethod
    def decision(experiment):
        return {**experiment['binding'], 'experiment_id': experiment['id'], 'expected_version': experiment['version'],
            'expected_proposal_revision_id': experiment['proposal_revision_id'], 'expected_hashes': experiment['hashes'],
            'idempotency_key': str(uuid.uuid4())}


def make_experiment_fixture(engine, directory):
    retained = make_investigation_fixture(engine, directory)
    decisions = {}
    for sid in retained.snapshots:
        registry = load_registry(*retained.store.read(sid)).metadata
        for binding in registry.datasets:
            manifest, _ = retained.store.read(binding.snapshot_id)
            capture = next(item for item in manifest.source_captures if item.source_id == binding.source_id and item.source_family == binding.source_family)
            decision = SourcePublicationDecision(child_snapshot_id=binding.snapshot_id,
                dataset_id=binding.dataset_id, source_id=binding.source_id, publication_generation=capture.publication_generation,
                object_sha256={item.object_id: item.sha256 for item in manifest.objects
                    if item.dataset_id == binding.dataset_id and item.source_id == binding.source_id},
                decision_reference='C22 explicitly synthetic local publication-policy fixture; no scientific approval', test_only=True)
            decisions[(binding.snapshot_id, binding.dataset_id, binding.source_id, capture.publication_generation)] = decision
    policy = PinnedSourcePublicationPolicy(policy_id='c22:synthetic:publication', revision='synthetic-policy-1', decisions=decisions.values())
    exporter = FrozenExperimentExporter(store=retained.store, catalogue=retained.service.catalogue,
        registrations=retained.registrations, publication_policy=policy)
    environment = EnvironmentDescriptor(kind='c22-fake', test_only=True, python_version='not-executed',
        description='Explicit C22 synthetic acceptance adapter; no Python runtime')
    executor = FakeExperimentExecutor()
    state = {'enabled': True, 'dispatch_enabled': True}
    service = ResearchExperimentService(session_factory=retained.factory, site_id=retained.service.site_id,
        investigations=retained.service, exporter=exporter, environments={environment.identity_sha256: environment},
        executor=executor, enabled=lambda: state['enabled'], dispatch_enabled=lambda: state['dispatch_enabled'])
    with retained.factory.begin() as session:
        if session.scalar(select(ResearchExperimentCapacity.id).where(ResearchExperimentCapacity.id == 1)) is None:
            session.add(ResearchExperimentCapacity(id=1))
    return ExperimentFixture(retained, service, exporter, executor, environment, state)
