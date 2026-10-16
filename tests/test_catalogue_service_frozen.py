"""C14 checks against the actual sealed C09/C10–C13 paths, never live services."""

from dataclasses import replace

import pytest

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore, SnapshotAccessDenied
from ingestion.provenance_snapshot import SnapshotNotFound
from ingestion.scientific_catalogue_inputs import load_registry
from orchestration.catalogue_registration import register_scientific_snapshot
from orchestration.catalogue_service import (
    CataloguePolicy,
    CatalogueService,
    CatalogueServiceError,
    FrozenCatalogueResolver,
)
from retrieval.source_scope import FAMILIES
from schema.catalogue_adapter_fixtures import adapter_scope, ctd_fixture, seal_fixture
from schema.scientific_catalogue import INDEX_OBJECT_ID
from schema.scientific_catalogue_fixtures import scientific_fixture, seal_scientific_fixture
from tests.catalogue_service_support import fixture_user
from tests.test_frozen_scientific_catalogue import local
from tests.test_scientific_catalogue_sources import (
    ANALYSIS,
    operation,
    scope,
    source_local,
)


def register(store, sid):
    return register_scientific_snapshot(
        store=store, snapshot_id=sid, registration_id="synthetic:c14-registration"
    )


def test_registered_index_and_exact_child_are_protected_from_cleanup(tmp_path):
    store, sid, _, _, _, _, child, _ = local(tmp_path)
    registration = register(store, sid)
    assert registration.child_snapshot_ids == (child,)
    assert {identity for _, identity in registration.references} == {sid, child}
    registration.require_current(store)
    assert store.cleanup([sid, child])["retired_count"] == 0
    store.read(sid)
    store.read(child)


def test_registration_retry_is_idempotent_without_reference_or_revision_growth(tmp_path):
    store, sid, *_ = local(tmp_path)
    first = register(store, sid)
    revision = store.lifecycle()["revision"]
    assert register(store, sid) == first
    assert store.lifecycle()["revision"] == revision
    assert len(store.lifecycle()["references"]) == 2


def test_registration_pins_only_explicit_dependencies(tmp_path):
    store, sid, _, _, _, _, child, _ = local(tmp_path)
    unrelated = seal_fixture(store, [ctd_fixture(7)])
    assert unrelated not in {sid, child}
    registration = register(store, sid)
    assert unrelated not in {identity for _, identity in registration.references}
    assert store.cleanup([sid, child, unrelated])["retired_ids"] == [unrelated]


@pytest.mark.parametrize("target", ["index", "child"])
def test_pins_do_not_override_current_withdrawal(tmp_path, target):
    store, sid, _, _, _, _, child, _ = local(tmp_path)
    registration = register(store, sid)
    store.revoke(sid if target == "index" else child)
    with pytest.raises(SnapshotAccessDenied):
        registration.require_current(store)
    assert store.cleanup([sid, child])["retired_count"] == 0


def test_missing_dependency_reference_makes_registration_unavailable(tmp_path):
    store, sid, *_ = local(tmp_path)
    registration = register(store, sid)
    reference, identity = registration.references[-1]
    store.remove_reference(identity, reference)
    with pytest.raises(SnapshotAccessDenied):
        registration.require_current(store)


def test_partial_registration_keeps_conservative_pins_and_can_resume(tmp_path, monkeypatch):
    store, sid, *_ = local(tmp_path)
    original = store.add_reference
    calls = []

    def interrupted(identity, reference):
        calls.append(identity)
        if len(calls) == 2:
            raise OSError("Synthetic dependency registration interrupted")
        return original(identity, reference)

    monkeypatch.setattr(store, "add_reference", interrupted)
    with pytest.raises(OSError):
        register(store, sid)
    assert list(store.lifecycle()["references"].values()) == [sid]
    assert store.cleanup([sid])["retired_count"] == 0
    monkeypatch.setattr(store, "add_reference", original)
    register(store, sid).require_current(store)
    assert len(store.lifecycle()["references"]) == 2


def test_retirement_between_index_validation_and_child_pin_fails_closed(tmp_path, monkeypatch):
    store, sid, _, _, _, _, child, _ = local(tmp_path)
    original = store.add_reference

    def retire_child(identity, reference):
        if identity == child:
            assert store.cleanup([child])["retired_count"] == 1
        return original(identity, reference)

    monkeypatch.setattr(store, "add_reference", retire_child)
    with pytest.raises(SnapshotNotFound):
        register(store, sid)
    assert list(store.lifecycle()["references"].values()) == [sid]


def test_registration_cannot_substitute_a_different_child_identity(tmp_path):
    store, sid, *_ = local(tmp_path)
    registration = register(store, sid)
    with pytest.raises(ValueError):
        replace(registration, child_snapshot_ids=("f" * 64,))


def test_registration_requires_scientific_index_instead_of_raw_source_snapshot(tmp_path):
    store, _, _, _, _, _, child, _ = local(tmp_path)
    with pytest.raises(ValueError):
        register(store, child)
    assert store.lifecycle()["references"] == {}


def frozen_service(store, snapshots, policy):
    registrations = {sid: register(store, sid) for sid in snapshots}

    def current(user, sid):
        return CataloguePolicy(
            revision=policy.get("revision", "current-policy-1"),
            dataset_eligible=lambda snapshot, metadata: (
                metadata.dataset_id not in policy["datasets"]
                and metadata.family not in policy["sources"]
            ),
            scientific_eligible=lambda snapshot, item: getattr(
                item, "id", getattr(item, "dataset_id", None)
            ) not in policy["objects"],
        )

    resolver = FrozenCatalogueResolver(
        store=store, policy_resolver=current, registrations=registrations
    )
    return CatalogueService(resolver=resolver)


def request(sid, **updates):
    return {"snapshot_id": sid, "scope": scope().model_dump(mode="json"), **updates}


@pytest.fixture(scope="module")
def frozen(tmp_path_factory):
    data = source_local(tmp_path_factory.mktemp("c14-actual-frozen-adapters"))
    store, sid, _, _, _, _, policy = data
    return (*data, frozen_service(store, [sid], policy), fixture_user())


def test_actual_frozen_service_has_five_roots_four_canonical_datasets_and_no_carrier(frozen):
    _, sid, _, _, fixtures, _, _, service, user = frozen
    roots = service.overview(request(sid), user)
    assert {node["root"] for node in roots["items"]} == {
        "data", "analyses", "statistics", "metadata", "relationships"
    }
    listed = service.list(request(sid, filters={"kinds": ["dataset"]}), user)
    assert {node["id"] for node in listed["items"]} == {
        metadata.dataset_id for metadata, _ in fixtures.values()
    }
    assert listed["total"]["value"] == 4
    assert all(node["snapshot_id"] == sid for node in listed["items"])


@pytest.mark.parametrize("family", FAMILIES)
def test_service_open_matches_actual_frozen_node_without_relabeling_source(frozen, family):
    _, sid, adapter, _, fixtures, _, _, service, user = frozen
    identity = fixtures[family][0].dataset_id
    from tests.test_scientific_catalogue_sources import listing
    assert service.open(request(sid, object_id=identity), user) == adapter.open(
        identity, listing(sid)
    ).model_dump(mode="json")


@pytest.mark.parametrize("family", FAMILIES)
def test_service_coverage_preserves_exact_native_units_counts_and_qualifications(frozen, family):
    _, sid, adapter, _, fixtures, _, _, service, user = frozen
    identity = fixtures[family][0].dataset_id
    expected = adapter.query(
        operation(sid, identity, "c13.coverage", limit=1)
    ).model_dump(mode="json")
    actual = service.coverage(request(sid, object_id=identity, limit=1), user)
    assert actual == expected


@pytest.mark.parametrize("family", FAMILIES)
def test_service_scientific_operation_delegates_exact_frozen_source_receipt(frozen, family):
    _, sid, adapter, _, fixtures, _, _, service, user = frozen
    identity = fixtures[family][0].dataset_id
    parameters = {
        "operation_id": "c10.count" if family in {"ctd", "metagenome"}
        else "c11.count" if family == "remote_sensing" else "c12.count",
        "operation_version": "c10-v1" if family in {"ctd", "metagenome"}
        else "c11-v1" if family == "remote_sensing" else "c12-v1",
        "limit": 1,
    }
    if family in {"ctd", "metagenome"}:
        parameters["parameters"] = {
            "table": "casts" if family == "ctd" else "collections"
        }
    expected = adapter.query(operation(
        sid, identity, "c13.operation", **parameters
    )).model_dump(mode="json")
    actual = service.query(request(
        sid, operation_id="c13.operation", operation_version="c13-v1",
        input_ids=[identity], parameters=parameters,
    ), user)
    assert actual == expected


def test_service_published_table_pages_bind_complete_rows_and_original_scope(frozen):
    _, sid, adapter, _, _, _, _, service, user = frozen
    expected = adapter.query(operation(sid, ANALYSIS, "c13.table", limit=2)).model_dump(mode="json")
    first = service.get_published(request(sid, analysis_id=ANALYSIS, limit=2), user)
    assert first == expected
    rows = list(first["rows"])
    next_offset = first["next_offset"]
    while next_offset is not None:
        page = service.get_published(request(
            sid, analysis_id=ANALYSIS, limit=2, offset=next_offset
        ), user)
        assert page["receipt"]["content_sha256"] == first["receipt"]["content_sha256"]
        assert page["receipt"]["total_rows"]["value"] == 12
        rows.extend(page["rows"])
        next_offset = page["next_offset"]
    assert len(rows) == len({row["result_id"] for row in rows}) == 12


def test_current_membership_policy_change_rejects_old_cursor_with_same_identity(tmp_path):
    store, sid, _, _, fixtures, _, policy = source_local(tmp_path)
    service, user = frozen_service(store, [sid], policy), fixture_user()
    payload = request(sid, filters={"kinds": ["dataset"]}, limit=1)
    first = service.list(payload, user)
    denied = fixtures["ctd"][0].dataset_id
    policy["datasets"].add(denied)
    policy["revision"] = "current-policy-2"
    with pytest.raises(CatalogueServiceError) as stale:
        service.list({**payload, "cursor": first["next_cursor"]}, user)
    assert stale.value.code == "invalid_cursor"
    current = service.list(request(sid, filters={"kinds": ["dataset"]}), user)
    assert current["total"]["value"] == 3
    assert denied not in str(current)
    with pytest.raises(CatalogueServiceError) as unavailable:
        service.get_published(request(sid, analysis_id=ANALYSIS), user)
    assert unavailable.value.code == "not_found"


@pytest.mark.parametrize("target", ["index", "ctd", "remote_sensing", "edna_metabarcoding"])
def test_current_store_withdrawal_overrides_previous_success_and_dependency_pins(tmp_path, target):
    store, sid, _, _, _, children, policy = source_local(tmp_path)
    service, user = frozen_service(store, [sid], policy), fixture_user()
    assert service.get_published(request(sid, analysis_id=ANALYSIS), user)["rows"]
    store.revoke(sid if target == "index" else children[target])
    with pytest.raises(CatalogueServiceError) as unavailable:
        service.get_published(request(sid, analysis_id=ANALYSIS), user)
    assert unavailable.value.code == "not_found"


def test_unregistered_frozen_index_is_unavailable_without_creating_any_references(tmp_path):
    store, sid, *_ = source_local(tmp_path)
    resolver = FrozenCatalogueResolver(
        store=store, policy_resolver=lambda user, snapshot: None, registrations={}
    )
    with pytest.raises(CatalogueServiceError) as unavailable:
        CatalogueService(resolver=resolver).overview(request(sid), fixture_user())
    assert unavailable.value.code == "not_found"
    assert store.lifecycle()["references"] == {}


@pytest.mark.parametrize("identity", [
    "synthetic:definition:ctd", "synthetic:relationship:physical",
    "synthetic:workflow:available", ANALYSIS, "metadata:synthetic:ctd:campaign-a",
])
def test_detailed_open_exposes_actual_source_and_scientific_content(frozen, identity):
    _, sid, adapter, _, _, _, _, service, user = frozen
    from tests.test_scientific_catalogue_sources import listing
    # C13's qualified dataset metadata identity is discovered from the actual
    # verified view rather than invented by this service acceptance test.
    if identity.startswith("metadata:"):
        nodes = service.list(request(sid, filters={"roots": ["metadata"]}), user)
        identity = next(
            node["id"] for node in nodes["items"]
            if node["id"].startswith("c13:metadata:")
        )
    actual = service.open(request(sid, object_id=identity, include_details=True), user)
    expected = CatalogueService._json(adapter.inspect(identity, listing(sid)))
    assert actual["node"]["id"] == identity
    assert actual["details"] == expected
    if "record" in expected and "comparison_authorized" in expected["record"]:
        assert expected["record"]["comparison_authorized"] is False
    if identity == ANALYSIS:
        assert expected["record"]["independent_researcher_approval"] is False
        assert expected["record"]["provider_endorsement"] is False


@pytest.mark.parametrize("method,route,extra", [
    ("overview", "/overview", {}),
    ("list", "/list", {"filters": {"kinds": ["dataset"]}, "limit": 2}),
    ("open", "/open", {"object_id": "synthetic:definition:ctd", "include_details": True}),
    ("coverage", "/coverage", {"object_id": "synthetic:ctd:campaign-a", "limit": 1}),
    ("relationships", "/relationships", {"object_id": "synthetic:ctd:campaign-a"}),
    ("query", "/query", {"operation_id": "c13.inventory", "operation_version": "c13-v1", "input_ids": ["root:data"], "parameters": {"limit": 1}}),
    ("get_published", "/analysis/get-published", {"analysis_id": ANALYSIS, "limit": 2}),
])
def test_authenticated_api_and_tools_match_actual_frozen_service(frozen, monkeypatch, method, route, extra):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import auth
    from api.catalogue_routes import router
    from orchestration.catalogue_tools import CatalogueTools

    _, sid, _, _, _, _, _, service, user = frozen
    monkeypatch.setenv("ENABLE_V1_CATALOGUE", "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setattr(auth, "authenticate_request", lambda incoming: user)
    app = FastAPI()
    app.state.catalogue_service = service
    app.middleware("http")(auth.authorization_middleware)
    app.include_router(router)
    payload = request(sid, **extra)
    expected = getattr(service, method)(payload, user)
    tools = CatalogueTools(service=service, identity_provider=lambda: user)
    assert getattr(tools, method)(payload) == expected
    with TestClient(app) as client:
        response = client.post("/catalogue" + route, json=payload)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json() == expected


@pytest.mark.parametrize("target", ["index", "child"])
@pytest.mark.parametrize("method", ["list", "get_published", "query", "coverage", "open"])
def test_corrupt_frozen_bytes_are_unavailable_consistently_across_service_entries(tmp_path, target, method):
    store, sid, _, _, fixtures, children, policy = source_local(tmp_path)
    service, user = frozen_service(store, [sid], policy), fixture_user()
    identity = fixtures["ctd"][0].dataset_id
    choices = {
        "list": {},
        "get_published": {"analysis_id": ANALYSIS},
        "query": {"operation_id": "c13.inventory", "operation_version": "c13-v1", "input_ids": ["root:data"]},
        "coverage": {"object_id": identity},
        "open": {"object_id": identity, "include_details": True},
    }
    payload = request(sid, **choices[method])
    getattr(service, method)(payload, user)
    manifest, _ = store.read(sid if target == "index" else children["ctd"])
    obj = next(item for item in manifest.objects if item.object_id == INDEX_OBJECT_ID) if target == "index" else manifest.objects[0]
    (tmp_path / "v1/catalogue/objects" / obj.sha256).write_bytes(b"synthetic corruption")
    with pytest.raises(CatalogueServiceError) as unavailable:
        getattr(service, method)(payload, user)
    assert unavailable.value.code == "catalogue_unavailable"
    assert unavailable.value.status_code == 503


def test_new_registered_index_preserves_original_published_rows_receipt_and_dependencies(tmp_path):
    store, old, _, _, _, _, policy = source_local(tmp_path)
    old_service, user = frozen_service(store, [old], policy), fixture_user()
    expected = old_service.get_published(request(old, analysis_id=ANALYSIS), user)
    manifest, contents = store.read(old)
    retained = load_registry(manifest, contents).metadata
    new_registry, new_tables = scientific_fixture(13, bindings=retained.datasets)
    new = seal_scientific_fixture(store, new_registry, new_tables)
    assert old != new
    service = frozen_service(store, [old, new], policy)
    assert service.get_published(request(old, analysis_id=ANALYSIS), user) == expected
    newer = service.get_published(request(new, analysis_id=ANALYSIS), user)
    assert newer["receipt"]["total_rows"]["value"] == 13
    assert expected["receipt"]["total_rows"]["value"] == 12
    assert newer["receipt"]["content_sha256"] != expected["receipt"]["content_sha256"]
    protected = set(store.lifecycle()["references"].values())
    assert old in protected and new in protected
    assert set(retained_dataset.snapshot_id for retained_dataset in retained.datasets) <= protected
    assert store.cleanup(sorted(protected))["retired_count"] == 0


@pytest.mark.parametrize("root", ["data", "metadata", "statistics"])
def test_detailed_open_never_discloses_denied_source_metadata_links(tmp_path, root):
    import json

    allowed, denied = "synthetic:ctd:visible", "synthetic:ctd:denied-link"
    store = LocalCatalogueSnapshotStore(root=tmp_path.resolve(), access_gate=lambda _: True)
    metadata, frames = ctd_fixture(2, dataset_id=allowed)
    metadata = metadata.model_copy(update={"related_ids": [denied]})
    child = seal_fixture(store, [(metadata, frames), ctd_fixture(1, dataset_id=denied)])
    registry, tables = scientific_fixture(2, bindings=[{
        "dataset_id": identity, "source_family": "ctd",
        "source_id": "synthetic-ctd", "snapshot_id": child,
    } for identity in (allowed, denied)])
    sid = seal_scientific_fixture(store, registry, tables)
    policy = {"sources": set(), "objects": set(), "datasets": {denied}}
    service, user = frozen_service(store, [sid], policy), fixture_user()
    base = {"snapshot_id": sid, "scope": adapter_scope("ctd").model_dump(mode="json")}
    if root == "data":
        identity = allowed
    else:
        page = service.list({**base, "filters": {"roots": [root]}}, user)
        identity = next(
            node["id"] for node in page["items"]
            if node["id"].startswith("c13:" + root + ":")
        )
    detailed = service.open({**base, "object_id": identity, "include_details": True}, user)
    assert detailed["node"]["id"] == identity
    assert denied not in json.dumps(detailed)
    permitted = service.list(base, user)
    permitted_ids = {node["id"] for node in permitted["items"]}
    assert detailed["node"]["related_ids"]
    assert set(detailed["node"]["related_ids"]) <= permitted_ids
