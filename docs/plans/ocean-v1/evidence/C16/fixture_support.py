"""Explicit C16 synthetic integration dependencies; never a runtime import.

Only owned temporary directories are written. No real data, provider, database
or legacy resource is opened. Current test policy is supplied by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass

from ingestion.scientific_catalogue_inputs import load_registry
from orchestration.catalogue_browser import CatalogueBrowser
from orchestration.catalogue_registration import register_scientific_snapshot
from orchestration.catalogue_service import CataloguePolicy, CatalogueService, FrozenCatalogueResolver
from schema.catalogue_browser import CatalogueSnapshotDescriptor
from schema.context_catalogue_fixtures import fixture_scope, make_catalogue
from schema.scientific_catalogue_fixtures import seal_scientific_fixture
from tests.catalogue_service_support import MutableFixtureResolver, fixture_user
from tests.test_scientific_catalogue_sources import scope, source_local


@dataclass
class BrowserFixture:
    service: object
    browser: object
    scope: object
    snapshots: tuple[str, ...]
    user: object
    dataset_ids: tuple[str, ...]
    store: object = None


def build_fixture(directory, *, state, count=None):
    user = fixture_user("C16 local test researcher")
    if count is not None:
        catalogue = make_catalogue(count, snapshot_id="a" * 64)
        resolver = MutableFixtureResolver({catalogue.snapshot_id: catalogue})
        service = CatalogueService(resolver=resolver)
        snapshots = (catalogue.snapshot_id,)
        selected_scope = fixture_scope()
        datasets = tuple(sorted(k for k, v in catalogue.records.items() if v.node.kind == "dataset"))
        store = None
    else:
        store, first, _, _, fixtures, _, _ = source_local(directory / "frozen")
        loaded = load_registry(*store.read(first))
        second = seal_scientific_fixture(
            store, loaded.metadata, loaded.tables, publication="synthetic-c16-publication-2"
        )
        snapshots = (second, first)  # Explicit host order; never C09's global latest.
        registrations = {
            sid: register_scientific_snapshot(
                store=store, snapshot_id=sid, registration_id="synthetic:c16:" + sid
            ) for sid in snapshots
        }

        def current(actor, sid):
            current_state = state()
            return CataloguePolicy(
                revision=current_state["revision"],
                dataset_eligible=lambda snapshot, metadata: (
                    metadata.family not in current_state.get("denied_sources", [])
                    and metadata.dataset_id not in current_state.get("denied_ids", [])
                ),
                scientific_eligible=lambda snapshot, item: getattr(
                    item, "id", getattr(item, "dataset_id", None)
                ) not in current_state.get("denied_ids", []),
            )

        service = CatalogueService(resolver=FrozenCatalogueResolver(
            store=store, policy_resolver=current, registrations=registrations,
        ))
        selected_scope = scope()
        datasets = tuple(sorted(meta.dataset_id for meta, _ in fixtures.values()))
    descriptors = tuple(CatalogueSnapshotDescriptor(
        snapshot_id=sid,
        label={"en": f"Synthetic frozen catalogue {len(snapshots) - index}",
               "ja": f"合成・固定カタログ {len(snapshots) - index}"},
    ) for index, sid in enumerate(snapshots))
    browser = CatalogueBrowser(
        service=service, snapshots=descriptors,
        permitted=lambda actor, descriptor: (
            state().get("allow_browser", True) is True
            and descriptor.snapshot_id not in state().get("denied_snapshots", [])
        ),
        revision=lambda actor: state()["revision"],
    )
    return BrowserFixture(service, browser, selected_scope, snapshots, user, datasets, store)
