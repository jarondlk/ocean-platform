"""C14 full validation and private retained graphs across cache boundaries."""
from copy import deepcopy

import pytest

from orchestration.catalogue_service import CatalogueService, CatalogueServiceError
from tests.catalogue_service_support import dataset_id, fixture_user, payload, synthetic_service


def test_backend_and_wire_mutations_cannot_alias_retained_scope_or_scientific_metadata():
    catalogue, resolver, _ = synthetic_service(8)
    source_requests, source_nodes = [], []

    class Resolver:
        def resolve(self, user, snapshot_id):
            result = resolver.resolve(user, snapshot_id)
            original = result.backend.view
            def observed(request):
                values = original(request)
                source_requests.append(request)
                source_nodes.extend(values.values())
                return values
            result.backend.view = observed
            return result

    service = CatalogueService(resolver=Resolver(), maximum_cached_views=1)
    body, user = payload(catalogue, filters={"kinds": ["dataset"]}), fixture_user()
    expected = deepcopy(service.list(body, user))
    # The backend received the request and supplied mutable validated models.
    # Retained metadata must remain independent of both external object graphs.
    source_requests[0].scope.sources.ctd.filters.station = "backend-mutated"
    selected = next(node for node in source_nodes if node.id == dataset_id(0))
    selected.title.en = "backend-mutated"
    selected.lifecycle.scientific_approval = "approved"
    changed = service.list(body, user)
    changed["items"][0]["scope"]["sources"]["ctd"]["filters"]["station"] = "wire-mutated"
    changed["items"][0]["descriptor"]["measurement"] = "wire-mutated"
    changed["items"][0]["operations"][0]["availability"]["status"] = "wire-mutated"
    changed["items"][1]["purpose"]["en"] = "wire-mutated"
    assert service.list(body, user) == expected
    # Cache eviction and rematerialization still apply fresh current permission.
    resolver.revoke(user, dataset_id(0))
    current = service.list(body, user)
    assert current["total"]["value"] == 7
    assert dataset_id(0) not in {item["id"] for item in current["items"]}


@pytest.mark.parametrize("mutation", ["scope", "membership", "descriptor"])
def test_unvalidated_backend_model_updates_still_fail_closed(mutation):
    catalogue, resolver, _ = synthetic_service(4)

    class Resolver:
        def resolve(self, user, snapshot_id):
            result = resolver.resolve(user, snapshot_id)
            original = result.backend.view
            def malformed(request):
                values = original(request)
                node = values[dataset_id(0)].model_copy(deep=True)
                if mutation == "scope":
                    node.scope.version = 2
                elif mutation == "membership":
                    node.membership, node.owner_id = "private", None
                else:
                    node.descriptor.depth_unit = "invalid-unit"
                values[node.id] = node
                return values
            result.backend.view = malformed
            return result

    service = CatalogueService(resolver=Resolver())
    with pytest.raises(CatalogueServiceError) as error:
        service.list(payload(catalogue), fixture_user())
    assert error.value.code == "catalogue_unavailable"
