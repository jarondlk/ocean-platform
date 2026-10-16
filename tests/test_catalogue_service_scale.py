"""Independent C14 service acceptance with an explicit 100,000-dataset backend."""

from copy import deepcopy
from dataclasses import replace

import pytest

from retrieval.source_scope import FAMILIES
from schema.context_catalogue import CatalogueListing, CatalogueNode
from schema.context_catalogue_fixtures import fixture_scope, make_catalogue
from tests.catalogue_service_support import (
    dataset_id,
    fixture_user,
    payload,
    synthetic_service,
)


@pytest.fixture(scope="module")
def scale():
    # Build exactly once; every page below is a real CatalogueService.execute call.
    return synthetic_service(catalogue=make_catalogue(100_000))


def execute(service, name, body, user=None):
    return service.execute(name, body, user or fixture_user())


def test_real_service_visits_100000_datasets_on_200_pages_once(scale):
    catalogue, resolver, service = scale
    body = payload(catalogue, filters={"kinds": ["dataset"]}, limit=500)
    identities = []
    pages = 0
    resolutions_before = resolver.calls
    while True:
        page = CatalogueListing.model_validate(execute(service, "catalogue.list", body))
        pages += 1
        assert page.total.value == 100_000
        assert page.returned_count == 500
        assert page.source_completeness == page.query_completion == "complete"
        assert page.items == sorted(page.items, key=lambda node: node.id)
        identities.extend(node.id for node in page.items)
        if page.next_cursor is None:
            break
        body = {**body, "cursor": page.next_cursor}
    assert pages == 200
    assert identities == [dataset_id(index) for index in range(100_000)]
    assert len(set(identities)) == 100_000
    assert resolver.calls - resolutions_before == 200
    # Explicit current access is resolved even when the immutable view is cached.
    assert sum(backend.view_calls for backend in resolver.backends) < 200


@pytest.mark.parametrize("index", [25, 501, 99_999])
def test_service_identity_and_name_search_reach_late_documentary_rank(scale, index):
    catalogue, _, service = scale
    identity = dataset_id(index)
    assert catalogue.records[identity].documentary_rank == index + 1
    opened = CatalogueNode.model_validate(
        execute(service, "catalogue.open", payload(catalogue, object_id=identity))
    )
    assert opened.id == identity
    for term in (identity, f"Synthetic dataset {index:06d}"):
        page = execute(
            service,
            "catalogue.list",
            payload(catalogue, filters={"kinds": ["dataset"], "search": term}),
        )
        assert [node["id"] for node in page["items"]] == [identity]
        assert page["total"]["value"] == 1


def test_service_path_search_and_source_filters_preserve_all_members(scale):
    catalogue, _, service = scale
    for family in FAMILIES:
        page = execute(
            service,
            "catalogue.list",
            payload(
                catalogue,
                filters={"kinds": ["dataset"], "search": f"synthetic:source:{family}"},
                limit=1,
            ),
        )
        assert page["total"]["value"] == 25_000
        assert page["returned_count"] == 1
        assert page["items"][0]["source_family"] == family
    page = execute(
        service,
        "catalogue.list",
        payload(catalogue, filters={"kinds": ["dataset"], "source_families": ["remote_sensing"]}),
    )
    assert page["total"]["value"] == 25_000
    assert all(node["source_family"] == "remote_sensing" for node in page["items"])


@pytest.mark.parametrize("limit", [1, 25, 100, 500])
def test_aggregate_complete_reference_is_independent_of_listing_preview(limit):
    catalogue, _, service = synthetic_service()
    listing = execute(
        service, "catalogue.list", payload(catalogue, filters={"kinds": ["dataset"]}, limit=limit)
    )
    result = execute(
        service,
        "catalogue.query",
        payload(
            catalogue,
            operation_id="c13.inventory",
            operation_version="c13-v1",
            input_ids=["root:data"],
            parameters={"limit": 1},
        ),
    )
    assert listing["returned_count"] == min(limit, 137)
    assert listing["total"]["value"] == result["rows"][0]["count"] == 137
    assert result["receipt"]["returned_count"] == 1
    assert len(result["receipt"]["inputs"]) == 137
    assert result["receipt"]["query_completion"] == "complete"


def test_cross_root_links_never_duplicate_complete_aggregate_inputs():
    catalogue, _, service = synthetic_service(12)
    result = execute(
        service,
        "catalogue.query",
        payload(catalogue, operation_id="c13.inventory", operation_version="c13-v1",
                input_ids=["root:metadata"], parameters={"limit": 1}),
    )
    assert catalogue.edges["root:metadata"].count(dataset_id(0)) == 2
    assert result["rows"] == [{"count": 1}]
    assert [item["object_id"] for item in result["receipt"]["inputs"]] == [dataset_id(0)]


def test_service_default_page_is_100_and_title_ties_keep_canonical_id_order():
    catalogue, _, service = synthetic_service(137)
    default = execute(service, "catalogue.list", payload(catalogue, filters={"kinds": ["dataset"]}))
    assert default["request"]["limit"] == default["returned_count"] == 100
    assert default["total"]["value"] == 137 and default["next_cursor"] is not None
    tied = make_catalogue(12)
    for identity, record in tuple(tied.records.items()):
        if record.node.kind == "dataset":
            renamed = record.node.model_dump(mode="json")
            renamed["title"] = {"en": "Equal title", "ja": "同じ名称"}
            tied.records[identity] = replace(record, node=CatalogueNode.model_validate(renamed))
    tied, _, tied_service = synthetic_service(catalogue=tied)
    body = payload(tied, filters={"kinds": ["dataset"]}, limit=5,
                   ordering=[{"field": "title", "direction": "asc"}, {"field": "id", "direction": "asc"}])
    identities = []
    while True:
        page = execute(tied_service, "catalogue.list", body)
        identities.extend(node["id"] for node in page["items"])
        if page["next_cursor"] is None:
            break
        body = {**body, "cursor": page["next_cursor"]}
    assert identities == [dataset_id(index) for index in range(12)]


def test_forbidden_objects_are_absent_from_search_counts_and_open():
    from orchestration.catalogue_service import CatalogueServiceError

    catalogue, resolver, service = synthetic_service(12)
    user = fixture_user()
    resolver.revoke(user, "synthetic:source:ctd")
    result = execute(service, "catalogue.list", payload(catalogue, filters={"kinds": ["dataset"]}), user)
    assert result["total"]["value"] == 9
    assert all(item["source_family"] != "ctd" for item in result["items"])
    for identity in (dataset_id(0), "synthetic:hidden", "synthetic:revoked", "synthetic:private-experiment"):
        page = execute(service, "catalogue.list", payload(catalogue, filters={"search": identity}), user)
        assert page["total"]["value"] == 0 and page["items"] == []
        with pytest.raises(CatalogueServiceError):
            execute(service, "catalogue.open", payload(catalogue, object_id=identity), user)
    path = execute(service, "catalogue.list", payload(catalogue, filters={"search": "synthetic:source:ctd"}), user)
    assert path["items"] == [] and path["total"]["value"] == 0
    aggregate = execute(
        service,
        "catalogue.query",
        payload(catalogue, operation_id="c13.inventory", operation_version="c13-v1",
                input_ids=["root:data"], parameters={"limit": 1}),
        user,
    )
    assert aggregate["rows"] == [{"count": 9}]
    assert len(aggregate["receipt"]["inputs"]) == 9
    assert all(item["object_id"] not in {dataset_id(0), dataset_id(4), dataset_id(8)}
               for item in aggregate["receipt"]["inputs"])


def test_same_user_same_role_revocation_rejects_cursor_and_cached_metadata():
    from orchestration.catalogue_service import CatalogueServiceError

    catalogue, resolver, service = synthetic_service(12)
    user = fixture_user()
    body = payload(catalogue, filters={"kinds": ["dataset"]}, limit=2)
    first = execute(service, "catalogue.list", body, user)
    execute(service, "catalogue.open", payload(catalogue, object_id=dataset_id(0)), user)
    resolver.revoke(user, "synthetic:source:ctd")
    assert user.role == "researcher"
    with pytest.raises(CatalogueServiceError):
        execute(service, "catalogue.list", {**body, "cursor": first["next_cursor"]}, user)
    with pytest.raises(CatalogueServiceError):
        execute(service, "catalogue.open", payload(catalogue, object_id=dataset_id(0)), user)
    fresh = execute(service, "catalogue.list", body, user)
    assert fresh["total"]["value"] == 9
    assert dataset_id(0) not in [node["id"] for node in fresh["items"]]


def test_interleaved_users_cannot_reuse_access_or_cursors():
    from orchestration.catalogue_service import CatalogueServiceError

    catalogue, resolver, service = synthetic_service(12)
    a, b = fixture_user(), fixture_user("researcher-b")
    resolver.revoke(b, "synthetic:source:ctd")
    body = payload(catalogue, filters={"kinds": ["dataset"]}, limit=2)
    page_a = execute(service, "catalogue.list", body, a)
    page_b = execute(service, "catalogue.list", body, b)
    assert page_a["total"]["value"] == 12 and page_b["total"]["value"] == 9
    with pytest.raises(CatalogueServiceError):
        execute(service, "catalogue.list", {**body, "cursor": page_a["next_cursor"]}, b)
    second_a = execute(service, "catalogue.list", {**body, "cursor": page_a["next_cursor"]}, a)
    assert [node["id"] for node in second_a["items"]] == [dataset_id(2), dataset_id(3)]


def test_snapshot_rollover_retains_old_results_without_accepting_new_cursor():
    from orchestration.catalogue_service import CatalogueServiceError

    old, resolver, service = synthetic_service(12)
    current = make_catalogue(13, snapshot_id="synthetic-snapshot-2")
    record = current.records[dataset_id(0)]
    renamed = record.node.model_dump(mode="json")
    renamed["title"] = {"en": "Renamed in new snapshot", "ja": "新しい名称"}
    current.records[dataset_id(0)] = replace(
        record,
        node=CatalogueNode.model_validate(renamed),
    )
    resolver.catalogues[current.snapshot_id] = current
    body = payload(old, filters={"kinds": ["dataset"]}, limit=2)
    before = execute(service, "catalogue.list", body)
    new_body = payload(current, filters={"kinds": ["dataset"]}, limit=2)
    after = execute(service, "catalogue.list", new_body)
    assert before["total"]["value"] == 12 and after["total"]["value"] == 13
    assert before["items"][0]["title"]["en"] == "Synthetic dataset 000000"
    assert after["items"][0]["title"]["en"] == "Renamed in new snapshot"
    assert execute(service, "catalogue.list", body) == before
    with pytest.raises(CatalogueServiceError):
        execute(service, "catalogue.list", {**new_body, "cursor": before["next_cursor"]})


@pytest.mark.parametrize(
    "change",
    [
        {"limit": 3},
        {"parent_id": "root:data"},
        {"filters": {"kinds": ["dataset"], "search": "000"}},
        {"ordering": [{"field": "id", "direction": "desc"}]},
        {"scope": fixture_scope("ctd").model_dump(mode="json")},
        {"cursor": "malformed$$"},
    ],
)
def test_cursor_reuse_requires_identical_scope_filter_order_limit_and_parent(change):
    from orchestration.catalogue_service import CatalogueServiceError

    catalogue, _, service = synthetic_service(12)
    body = payload(catalogue, filters={"kinds": ["dataset"]}, limit=2)
    first = execute(service, "catalogue.list", body)
    with pytest.raises(CatalogueServiceError):
        execute(service, "catalogue.list", {**body, "cursor": first["next_cursor"], **change})


@pytest.mark.parametrize(
    "change",
    [
        {"limit": 0}, {"limit": 501}, {"limit": True}, {"limit": "100"},
        {"ordering": [{"field": "title"}]},
        {"ordering": [{"field": "id"}, {"field": "id"}]},
        {"filters": {"source_families": ["unknown"]}},
        {"filters": {"kinds": ["dataset", "dataset"]}},
        {"access_binding": "administrator"}, {"access_revision": "trusted"},
    ],
)
def test_public_payload_rejects_malformed_and_client_authority(change):
    from orchestration.catalogue_service import CatalogueServiceError

    catalogue, _, service = synthetic_service(12)
    with pytest.raises(CatalogueServiceError):
        execute(service, "catalogue.list", {**payload(catalogue), **deepcopy(change)})


def authenticated_client(monkeypatch, service, user):
    """Exercise the real route authorization middleware with an offline identity."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.auth as auth
    import config
    from api.catalogue_routes import router

    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setattr(config, "production_like_environment", lambda: False)
    monkeypatch.setattr(auth, "authenticate_request", lambda request: user)
    app = FastAPI()
    app.state.catalogue_service = service
    app.middleware("http")(auth.authorization_middleware)
    app.include_router(router)
    return TestClient(app)


def test_authenticated_api_and_agent_tools_reach_last_object_in_100000(scale, monkeypatch):
    from orchestration.catalogue_tools import CatalogueTools

    catalogue, resolver, service = scale
    user = fixture_user()
    tools = CatalogueTools(service, lambda: user)
    body = payload(catalogue, filters={"kinds": ["dataset"], "search": "099999"}, limit=1)
    before = resolver.calls
    with authenticated_client(monkeypatch, service, user) as client:
        response = client.post("/catalogue/list", json=body)
        assert response.status_code == 200
        assert response.json() == tools.list(body) == execute(service, "catalogue.list", body, user)
        assert [node["id"] for node in response.json()["items"]] == [dataset_id(99_999)]
        assert response.json()["total"]["value"] == 1
        assert response.headers["cache-control"] == "no-store"
        opened = payload(catalogue, object_id=dataset_id(99_999))
        api_open = client.post("/catalogue/open", json=opened)
        assert api_open.status_code == 200
        assert api_open.json() == tools.open(opened)
    assert resolver.calls - before == 5


def test_api_tools_and_service_share_pages_aggregate_and_revocation_errors(monkeypatch):
    from orchestration.catalogue_tools import CatalogueTools

    catalogue, resolver, service = synthetic_service(137)
    user = fixture_user()
    tools = CatalogueTools(service, lambda: user)
    body = payload(catalogue, filters={"kinds": ["dataset"]}, limit=2)
    with authenticated_client(monkeypatch, service, user) as client:
        first = client.post("/catalogue/list", json=body)
        assert first.status_code == 200
        assert first.json() == tools.list(body) == execute(service, "catalogue.list", body, user)
        next_body = {**body, "cursor": first.json()["next_cursor"]}
        second = client.post("/catalogue/list", json=next_body)
        assert second.status_code == 200
        assert second.json() == tools.list(next_body)
        assert [node["id"] for node in second.json()["items"]] == [dataset_id(2), dataset_id(3)]
        aggregate = payload(catalogue, operation_id="c13.inventory", operation_version="c13-v1",
                            input_ids=["root:data"], parameters={"limit": 1})
        api_query = client.post("/catalogue/query", json=aggregate)
        assert api_query.status_code == 200
        assert api_query.json() == tools.query(aggregate)
        assert api_query.json()["rows"] == [{"count": 137}]
        resolver.revoke(user, "synthetic:source:ctd")
        stale = client.post("/catalogue/list", json=next_body)
        assert stale.status_code == 409
        assert stale.json() == tools.list(next_body)
        denied_body = payload(catalogue, object_id=dataset_id(0))
        denied = client.post("/catalogue/open", json=denied_body)
        assert denied.status_code == 404
        assert denied.json() == tools.open(denied_body)
        fresh = client.post("/catalogue/list", json=body)
        assert fresh.status_code == 200
        assert fresh.json() == tools.list(body)
        assert fresh.json()["total"]["value"] == 102
