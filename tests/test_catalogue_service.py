"""C14 strict models, logical paths and independent request boundaries."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from threading import Event

import pytest

from orchestration.catalogue_service import (
    CatalogueService, CatalogueServiceError, ResolvedCatalogue, catalogue_access_binding,
)
from schema.catalogue_service import REQUEST_MODELS
from tests.catalogue_service_support import (
    dataset_id, fixture_user, payload, synthetic_service,
)


def request_for(name, catalogue):
    body = payload(catalogue)
    if name == "catalogue.open" or name == "catalogue.coverage":
        body["object_id"] = dataset_id(0)
    if name == "catalogue.query":
        body.update(operation_id="c13.inventory", operation_version="c13-v1", input_ids=["root:data"])
    if name == "analysis.get_published":
        body["analysis_id"] = "synthetic:analysis"
    return body


@pytest.mark.parametrize("name", list(REQUEST_MODELS))
@pytest.mark.parametrize("field", ["access_binding", "access_revision", "role", "permissions", "store", "resolver"])
def test_public_requests_cannot_supply_server_authorization_or_dependencies(name, field):
    catalogue, _, service = synthetic_service(4)
    body = {**request_for(name, catalogue), field: "forged"}
    with pytest.raises(CatalogueServiceError) as failure:
        service.execute(name, body, fixture_user())
    assert failure.value.code == "invalid_request" and failure.value.status_code == 422


@pytest.mark.parametrize("name", list(REQUEST_MODELS))
def test_constructed_public_models_are_revalidated_before_resolver(name):
    catalogue, resolver, service = synthetic_service(4)
    model = REQUEST_MODELS[name].model_construct(**{**request_for(name, catalogue), "scope": "unvalidated"})
    with pytest.raises(CatalogueServiceError) as failure:
        service.execute(name, model, fixture_user())
    assert failure.value.code == "invalid_request"
    assert resolver.calls == 0


@pytest.mark.parametrize("user,code,status", [
    (None, "authentication_required", 401),
    (fixture_user(role="viewer"), "access_denied", 403),
    (replace(fixture_user(), status="suspended"), "access_denied", 403),
    (replace(fixture_user(), permissions=frozenset()), "access_denied", 403),
])
def test_service_enforces_identity_and_permission_before_policy_resolution(user, code, status):
    catalogue, resolver, service = synthetic_service(4)
    with pytest.raises(CatalogueServiceError) as failure:
        service.list(payload(catalogue), user)
    assert (failure.value.code, failure.value.status_code) == (code, status)
    assert resolver.calls == 0


@pytest.mark.parametrize("which", ["canonical", "english", "japanese"])
def test_multisegment_logical_path_search_keeps_languages_and_ids_separate(which):
    catalogue, _, service = synthetic_service(8)
    identity = dataset_id(5)
    node = catalogue.records[identity].node
    chain = [node]
    while chain[-1].parent_id:
        chain.append(catalogue.records[chain[-1].parent_id].node)
    chain.reverse()
    if which == "canonical":
        term = " / ".join(item.id for item in chain)
    else:
        term = " / ".join(getattr(item.title, "en" if which == "english" else "ja") for item in chain)
    result = service.list(payload(catalogue, filters={"kinds": ["dataset"], "search": term}), fixture_user())
    assert [item["id"] for item in result["items"]] == [identity]


def test_directory_search_reaches_descendants_beyond_immediate_children():
    catalogue, _, service = synthetic_service(137)
    identity = dataset_id(136)
    result = service.list(payload(catalogue, parent_id="root:data", filters={"kinds": ["dataset"], "search": identity}), fixture_user())
    assert [node["id"] for node in result["items"]] == [identity]
    assert service.list(payload(catalogue, parent_id="root:data"), fixture_user())["items"][0]["kind"] == "directory"


def test_identity_binding_changes_with_effective_permissions_and_subject():
    user = fixture_user()
    assert catalogue_access_binding(user) != catalogue_access_binding(fixture_user("another-researcher"))
    assert catalogue_access_binding(user) != catalogue_access_binding(replace(user, permissions=user.permissions | {"synthetic:permission"}))


def test_cached_return_values_cannot_mutate_later_inventory():
    catalogue, _, service = synthetic_service(8)
    body = payload(catalogue, filters={"kinds": ["dataset"]})
    before = deepcopy(service.list(body, fixture_user()))
    result = service.list(body, fixture_user())
    result["items"][0]["title"]["en"] = "corrupt"
    result["items"].clear()
    assert service.list(body, fixture_user()) == before


def test_blocked_backend_view_does_not_serialize_another_authenticated_request():
    catalogue, resolver, _ = synthetic_service(4)
    entered, release = Event(), Event()
    slow, fast = fixture_user("slow"), fixture_user("fast")

    class Resolver:
        def resolve(self, user, snapshot_id):
            result = resolver.resolve(user, snapshot_id)
            if user.id != slow.id:
                return result
            original = result.backend

            class SlowBackend:
                def view(self, request):
                    entered.set()
                    assert release.wait(5)
                    return original.view(request)

            return ResolvedCatalogue(SlowBackend(), result.revision, result.cache_token)

    service = CatalogueService(resolver=Resolver())
    with ThreadPoolExecutor(max_workers=2) as pool:
        blocked = pool.submit(service.list, payload(catalogue), slow)
        try:
            assert entered.wait(2)
            independent = pool.submit(service.list, payload(catalogue), fast)
            assert independent.result(timeout=2)["items"]
            assert not blocked.done()
        finally:
            release.set()
        assert blocked.result(timeout=2)["items"]


def test_resolver_failure_never_exposes_internal_paths_or_reuses_cache():
    catalogue, resolver, service = synthetic_service(4)
    service.list(payload(catalogue), fixture_user())

    def fail(user, snapshot_id):
        raise OSError("secret internal path and credential")

    resolver.resolve = fail
    with pytest.raises(CatalogueServiceError) as failure:
        service.list(payload(catalogue), fixture_user())
    assert failure.value.code == "catalogue_unavailable"
    assert failure.value.message == "Catalogue is unavailable"


def test_open_details_mode_is_explicit_and_missing_backend_details_are_qualified():
    catalogue, _, service = synthetic_service(4)
    base = payload(catalogue, object_id=dataset_id(0))
    node = service.open(base, fixture_user())
    detailed = service.open({**base, "include_details": True}, fixture_user())
    assert detailed["node"] == node
    assert detailed["details"]["availability"]["status"] == "unavailable"
    with pytest.raises(CatalogueServiceError) as failure:
        service.open({**base, "include_details": "true"}, fixture_user())
    assert failure.value.code == "invalid_request"


def test_backend_query_cannot_return_a_malformed_success_contract():
    catalogue, resolver, _ = synthetic_service(4)

    class Resolver:
        def resolve(self, user, snapshot_id):
            result = resolver.resolve(user, snapshot_id)
            result.backend.query = lambda request: {"rows": [{"fabricated": True}]}
            return result

    service = CatalogueService(resolver=Resolver())
    body = payload(catalogue, operation_id="c13.inventory", operation_version="c13-v1", input_ids=["root:data"])
    with pytest.raises(CatalogueServiceError) as failure:
        service.query(body, fixture_user())
    assert failure.value.code == "catalogue_unavailable"


def test_details_prune_denied_related_identities_recursively_in_models_and_lists():
    from pydantic import BaseModel

    class Details(BaseModel):
        related_ids: list[str]

    catalogue, resolver, _ = synthetic_service(4)
    allowed, denied = dataset_id(0), dataset_id(1)
    user = fixture_user()
    resolver.revoke(user, denied)

    class Resolver:
        def resolve(self, user, snapshot_id):
            result = resolver.resolve(user, snapshot_id)
            result.backend.inspect = lambda identity, request: {
                "related_ids": [allowed, denied],
                "nested": [{"metadata": Details(related_ids=[denied, allowed])}],
                "qualification": "Retained source qualification stays unchanged",
            }
            return result

    service = CatalogueService(resolver=Resolver())
    response = service.open(payload(catalogue, object_id=allowed, include_details=True), user)
    assert response["details"] == {
        "related_ids": [allowed], "nested": [{"metadata": {"related_ids": [allowed]}}],
        "qualification": "Retained source qualification stays unchanged",
    }
