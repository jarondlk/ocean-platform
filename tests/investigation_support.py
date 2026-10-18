"""C17 explicit synthetic frozen sources and independent application database."""
from dataclasses import dataclass
import hashlib
import json

from sqlalchemy.orm import sessionmaker

from db.app_models import AppUser
from ingestion.scientific_catalogue_inputs import load_registry
from orchestration.catalogue_registration import register_scientific_snapshot
from orchestration.catalogue_service import CataloguePolicy, CatalogueService, FrozenCatalogueResolver
from orchestration.investigations import InvestigationService
from schema.scientific_catalogue_fixtures import seal_scientific_fixture
from tests.catalogue_service_support import fixture_user
from tests.test_scientific_catalogue_sources import scope, source_local


@dataclass
class InvestigationFixture:
    service: object
    factory: object
    user: object
    other: object
    admin: object
    scope: dict
    snapshots: tuple
    store: object
    registrations: dict
    policy: dict
    dataset_ids: dict
    source_dataset_ids: dict


def make_investigation_fixture(engine, directory):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    user, other, admin = (fixture_user("c17-owner"), fixture_user("c17-other"), fixture_user("c17-admin", role="admin"))
    with factory.begin() as session:
        for actor in (user, other, admin):
            session.add(AppUser(
                id=actor.id, auth_provider=actor.auth_provider, auth_subject=str(actor.id),
                email=actor.email, display_name=actor.display_name, role=actor.role,
                account_type=actor.account_type, status="active",
            ))
    store, first, _, _, fixtures, _, _ = source_local(directory / "frozen")
    registry = load_registry(*store.read(first))
    second = seal_scientific_fixture(store, registry.metadata, registry.tables, publication="c17-newer-synthetic-index")
    snapshots = (first, second)
    registrations = {sid: register_scientific_snapshot(store=store, snapshot_id=sid, registration_id="synthetic:c17:" + sid) for sid in snapshots}
    policy = {sid: set() for sid in snapshots}

    def current(actor, sid):
        return CataloguePolicy(
            revision="c17:" + hashlib.sha256(json.dumps(sorted(policy[sid])).encode()).hexdigest(),
            dataset_eligible=lambda snapshot, metadata: metadata.dataset_id not in policy[sid],
            scientific_eligible=lambda snapshot, item: getattr(item, "id", getattr(item, "dataset_id", None)) not in policy[sid],
        )

    catalogue = CatalogueService(resolver=FrozenCatalogueResolver(store=store, policy_resolver=current, registrations=registrations))
    selected_scope = scope().model_dump(mode="json")
    datasets = catalogue.list({"snapshot_id": first, "scope": selected_scope, "filters": {"kinds": ["dataset"]}, "limit": 500}, user)["items"]
    service = InvestigationService(session_factory=factory, site_id="v1:c17-synthetic", catalogue_service=catalogue, snapshot_store=store, registrations=registrations)
    return InvestigationFixture(service, factory, user, other, admin, selected_scope, snapshots, store, registrations, policy, {node["source_family"]: node["id"] for node in datasets}, {family: metadata.dataset_id for family, (metadata, _) in fixtures.items()})
