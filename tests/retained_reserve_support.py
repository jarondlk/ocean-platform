"""Synthetic C22 approvals and explicit reader configuration, never runtime proof."""
import hashlib

from orchestration.experiment_sandbox.execution_store import C23ExecutionStore, ExecutionStoreConfig
from orchestration.experiment_sandbox.operator_inspection import C23OperatorInspection, OperatorInspectionConfig
from orchestration.experiment_sandbox.retained_bridge import C23RetainedBridge, RetainedMaterialPolicy
from orchestration.investigations import InvestigationService
from orchestration.research_experiments import ResearchExperimentService
from tests.test_experiment_sandbox_execution_store import configuration


def reader(fixture, factory):
    investigations = InvestigationService(session_factory=factory, site_id=fixture.service.site_id,
        catalogue_service=fixture.investigations.catalogue, snapshot_store=fixture.retained.store,
        registrations=fixture.retained.registrations)
    return ResearchExperimentService(session_factory=factory, site_id=fixture.service.site_id,
        investigations=investigations, exporter=fixture.exporter,
        environments={fixture.environment.identity_sha256: fixture.environment},
        enabled=lambda: fixture.state['enabled'], dispatch_enabled=lambda: False)


def material(fixture):
    names = ('worker_id', 'source_policy_sha256', 'worker_source_sha256', 'runtime_sha256',
             'profile_policy_sha256', 'trusted_init_sha256', 'adapter_source_sha256')
    return RetainedMaterialPolicy(site_id=fixture.service.site_id,
        environment_sha256=fixture.environment.identity_sha256, image_digest=fixture.environment.image_digest,
        **{name: hashlib.sha256(('synthetic-software-only:' + name).encode()).hexdigest() for name in names})


def bridge(fixture, *, factory=None, config=None, enabled=lambda: True):
    factory = fixture.factory if factory is None else factory
    service = reader(fixture, factory)
    inspection = C23OperatorInspection(service=service, config=OperatorInspectionConfig(
        site_id=service.site_id, session_factory=factory,
        environments={fixture.environment.identity_sha256: fixture.environment},
        store_scope='isolated-unmounted-operator', enabled=lambda: True))
    if config is None:
        old = configuration()
        config = ExecutionStoreConfig(site_id=service.site_id, database_name=old.database_name,
            schema='main', controller_session_factory=factory,
            recorder_session_factory=lambda: None, roles=old.roles,
            verifier_registry=old.verifier_registry, store_scope='isolated-unmounted-operator',
            enabled=lambda: True)
    store = C23ExecutionStore(config=config)
    return C23RetainedBridge(inspection=inspection, store=store, material_policy=material(fixture), enabled=enabled)
