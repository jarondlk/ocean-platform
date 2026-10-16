"""Independent C13 acceptance over real frozen adapters and explicit fixtures."""

from copy import deepcopy

import pytest

from ingestion.immutable_bundle import digest
from ingestion.catalogue_snapshot import (
    LocalCatalogueSnapshotStore,
    SnapshotAccessDenied,
)
from orchestration.frozen_catalogue import AdapterAccess, FrozenCatalogueAdapter
from orchestration.frozen_scientific_catalogue import (
    AdapterAccessDenied,
    FrozenScientificCatalogueAdapter,
    ScientificAccess,
)
from schema.catalogue_adapter_fixtures import adapter_scope, ctd_fixture, seal_fixture
from schema.context_catalogue import CatalogueFilters, ListingRequest, OperationRequest
from schema.scientific_catalogue import INDEX_OBJECT_ID, ScientificRegistry
from schema.scientific_catalogue_fixtures import (
    scientific_fixture,
    seal_scientific_fixture,
)

CTD = "synthetic:ctd:campaign-a"
ANALYSIS = "synthetic:analysis:published"
TABLE = ANALYSIS + ":results"
WORKFLOW = "synthetic:workflow:available"
DEFINITION = "synthetic:definition:temperature-unit"
RELATIONSHIP = "synthetic:relationship:unresolved"


def listing(snapshot, *, scope=None, **changes):
    return ListingRequest.model_validate(
        {
            "snapshot_id": snapshot,
            "scope": (scope or adapter_scope("ctd")).model_dump(mode="json"),
            "access_binding": "user-a",
            "access_revision": "revision-1",
            **changes,
        }
    )


def operation(snapshot, identity=ANALYSIS, op="c13.table", *, scope=None, **parameters):
    return OperationRequest(
        snapshot_id=snapshot,
        scope=scope or adapter_scope("ctd"),
        operation_id=op,
        operation_version="c13-v1",
        input_ids=[identity],
        parameters=parameters,
        access_binding="user-a",
        access_revision="revision-1",
    )


def local(tmp_path, *, count=12, configure=None):
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda manifest: True
    )
    source_dataset = ctd_fixture(4)
    child = seal_fixture(store, [source_dataset])
    registry, tables = scientific_fixture(
        count,
        bindings=[
            {
                "dataset_id": CTD,
                "source_family": "ctd",
                "source_id": "synthetic-ctd",
                "snapshot_id": child,
            }
        ],
    )
    payload = registry.model_dump(mode="json")
    payload["analyses"][0]["scope"] = adapter_scope("ctd").model_dump(mode="json")
    label = {"en": "Synthetic metadata or relationship", "ja": "合成メタデータ・関連"}
    payload["definitions"] = [{
        "id": DEFINITION, "title": label, "purpose": label, "category": "unit",
        "values": {"variable": "temperature", "unit": "degC"},
        "input_dataset_ids": [CTD], "provenance": {"references": ["Synthetic units only"]},
    }]
    row = source_dataset[1]["casts"].iloc[0].to_dict()
    payload["relationships"] = [{
        "id": RELATIONSHIP, "title": label, "purpose": label, "category": "unresolved",
        "input_dataset_ids": [CTD], "endpoints": [{"dataset_id": CTD, "entity_id": row["cast_id"],
                                                  "scientific_content_sha256": digest(row)}],
        "qualification": "Retained source occurrence; physical identity remains unresolved",
        "evidence": {"reason": "No retained physical identity review"},
        "comparison_authorized": False, "provenance": {"references": ["Synthetic unresolved identity"]},
    }]
    if configure:
        configure(payload, tables)
    registry = ScientificRegistry.model_validate(payload)
    sid = seal_scientific_fixture(store, registry, tables)
    policy = {"objects": set(), "datasets": set()}
    source = FrozenCatalogueAdapter(
        store=store,
        access=AdapterAccess(
            "user-a", "revision-1", lambda snapshot, metadata: metadata.dataset_id not in policy["datasets"]
        ),
    )
    adapter = FrozenScientificCatalogueAdapter(
        store=store,
        adapters={"ctd": source},
        access=ScientificAccess(
            "user-a", "revision-1", lambda snapshot, item: getattr(item, "id", getattr(item, "dataset_id", None)) not in policy["objects"]
        ),
    )
    return store, sid, adapter, policy, registry, tables, child, source


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    return local(tmp_path_factory.mktemp("c13-scientific-large"), count=1205)


def test_all_five_roots_are_reachable_and_index_carrier_is_not_a_raw_dataset(large):
    _, sid, adapter, _, _, _, _, _ = large
    result = adapter.list(listing(sid, filters=CatalogueFilters(kinds=["root"])))
    assert {node.id for node in result.items} == {
        "root:data", "root:analyses", "root:statistics", "root:metadata", "root:relationships"
    }
    datasets = adapter.list(listing(sid, filters=CatalogueFilters(kinds=["dataset"])))
    assert [node.id for node in datasets.items] == [CTD]
    assert datasets.items[0].root == "data"
    assert datasets.items[0].source_family == "ctd"
    assert datasets.items[0].snapshot_id == sid


def test_published_finding_and_workflow_description_keep_distinct_authority(large):
    _, sid, adapter, _, _, _, _, _ = large
    finding = adapter.open(ANALYSIS, listing(sid))
    workflow = adapter.open(WORKFLOW, listing(sid))
    assert finding.root == workflow.root == "analyses"
    assert finding.kind == "analysis" and finding.authority == "published"
    assert finding.lifecycle.publication == "published"
    assert finding.lifecycle.scientific_approval != "approved"
    assert workflow.kind == "workflow" and workflow.authority == "descriptive"
    assert workflow.lifecycle.publication != "published"
    assert CTD in finding.related_ids and CTD in workflow.related_ids
    unsupported = adapter.query(operation(sid, WORKFLOW))
    assert unsupported.rows == []
    assert unsupported.receipt.authority == "descriptive"
    assert unsupported.receipt.availability.status == "unavailable"
    assert unsupported.receipt.total_rows.value is None


@pytest.mark.parametrize("limit", [1, 10, 25, 100, 500])
def test_preview_cannot_limit_published_table_population_or_content_hash(large, limit):
    _, sid, adapter, _, _, _, _, _ = large
    value = adapter.query(operation(sid, table="results", limit=limit))
    full_page = adapter.query(operation(sid, TABLE, limit=500))
    assert len(value.rows) == limit
    assert value.receipt.total_rows.value == 1205
    assert value.receipt.total_rows.entity == "rows"
    assert value.receipt.content_sha256 == full_page.receipt.content_sha256
    assert value.receipt.authority == "published"
    assert value.receipt.operation_id == "c13.table"
    assert value.receipt.operation_version == "c13-v1"
    assert value.next_offset == limit
    assert value.receipt.preview_truncated
    assert value.qualifications


def test_all_published_pages_preserve_every_exact_row_and_explicit_null(large):
    _, sid, adapter, _, _, tables, _, _ = large
    rows, offset = [], 0
    identities = set()
    while True:
        value = adapter.query(operation(sid, TABLE, limit=500, offset=offset))
        rows.extend(value.rows)
        identities.add(value.receipt.content_sha256)
        if value.next_offset is None:
            break
        offset = value.next_offset
    assert rows == tables[TABLE]
    assert len(rows) == len({row["result_id"] for row in rows}) == 1205
    assert len(identities) == 1
    assert rows[0]["value"] == 0 and all(row["missing"] is None for row in rows)


@pytest.mark.parametrize("root", ["data", "analyses", "statistics", "metadata", "relationships"])
def test_directory_inventory_counts_unique_input_dataset_across_multiple_links(large, root):
    _, sid, adapter, _, _, _, _, _ = large
    value = adapter.query(operation(sid, f"root:{root}", "c13.inventory"))
    assert len(value.rows) == 1
    assert value.rows[0]["entity"] == "datasets"
    assert value.rows[0]["count"] == 1
    assert value.rows[0]["denominator"]
    assert value.receipt.authority == "descriptive"


def test_metadata_and_unresolved_relationship_link_exact_existing_dataset_identity(large):
    _, sid, adapter, _, _, _, _, _ = large
    metadata = adapter.open(DEFINITION, listing(sid))
    relationship = adapter.open(RELATIONSHIP, listing(sid))
    assert metadata.root == "metadata" and metadata.kind == "metadata"
    assert relationship.root == "relationships" and relationship.kind == "relationship"
    assert CTD in metadata.related_ids and CTD in relationship.related_ids
    assert metadata.authority == relationship.authority == "descriptive"
    assert relationship.lifecycle.scientific_approval != "approved"
    unsupported = adapter.query(operation(sid, RELATIONSHIP))
    assert unsupported.rows == []
    assert unsupported.receipt.authority == "descriptive"
    assert unsupported.receipt.availability.status == "unavailable"
    assert unsupported.receipt.total_rows.value is None


def test_scientific_receipt_binds_frozen_index_and_all_input_snapshot_origins(large):
    store, sid, adapter, _, _, _, child, _ = large
    value = adapter.query(operation(sid))
    manifest, _ = store.read(sid)
    inputs = {item.object_id: item for item in value.receipt.inputs}
    assert INDEX_OBJECT_ID in inputs
    assert inputs[INDEX_OBJECT_ID].content_sha256 == next(
        item.sha256 for item in manifest.objects if item.object_id == INDEX_OBJECT_ID
    )
    assert child in str(value.receipt.model_dump(mode="json"))
    assert sid == value.snapshot_id == value.receipt.snapshot_id
    assert value.scope == adapter_scope("ctd")


@pytest.mark.parametrize("state", ["unpublished", "historical", "experimental"])
def test_noncurrent_and_private_results_never_join_global_analyses(tmp_path, state):
    def configure(payload, tables):
        payload["analyses"][0]["publication_status"] = state

    _, sid, adapter, _, _, _, _, _ = local(tmp_path, configure=configure)
    result = adapter.list(listing(sid, parent_id="root:analyses"))
    assert ANALYSIS not in {node.id for node in result.items}
    with pytest.raises(AdapterAccessDenied):
        adapter.open(ANALYSIS, listing(sid))
    with pytest.raises(AdapterAccessDenied):
        adapter.query(operation(sid))


@pytest.mark.parametrize("scope", [adapter_scope("ctd", station="station-1"), adapter_scope("ctd", bay="O")])
def test_narrowed_or_incompatible_scope_cannot_inherit_fixed_publication_rows(large, scope):
    _, sid, adapter, _, _, _, _, _ = large
    value = adapter.query(operation(sid, scope=scope))
    assert value.rows == []
    assert value.receipt.availability.status == "unavailable"
    assert value.receipt.total_rows.value is None
    assert value.receipt.query_completion != "complete"
    assert value.receipt.availability.reason


def test_scope_with_no_permitted_input_dataset_cannot_disclose_publication_rows(large):
    _, sid, adapter, _, _, _, _, _ = large
    with pytest.raises(AdapterAccessDenied):
        adapter.query(operation(sid, scope=adapter_scope("ctd", bay="M")))


def test_current_child_dataset_policy_removes_dependent_scientific_objects(tmp_path):
    _, sid, adapter, policy, _, _, _, _ = local(tmp_path)
    assert adapter.query(operation(sid)).rows
    policy["datasets"].add(CTD)
    items = adapter.list(listing(sid)).items
    assert not {CTD, ANALYSIS, TABLE, WORKFLOW, DEFINITION, RELATIONSHIP} & {item.id for item in items}
    for identity in (CTD, ANALYSIS, TABLE, WORKFLOW, DEFINITION, RELATIONSHIP):
        with pytest.raises(AdapterAccessDenied):
            adapter.open(identity, listing(sid))
    inventory = adapter.query(operation(sid, "root:data", "c13.inventory"))
    assert inventory.rows[0]["count"] == 0


def test_scientific_policy_does_not_revoke_underlying_raw_dataset(tmp_path):
    _, sid, adapter, policy, _, _, _, _ = local(tmp_path)
    policy["objects"].add(ANALYSIS)
    with pytest.raises(AdapterAccessDenied):
        adapter.query(operation(sid))
    assert adapter.open(CTD, listing(sid)).id == CTD


@pytest.mark.parametrize("target", ["index", "child"])
def test_current_store_revocation_overrides_previous_archived_success(tmp_path, target):
    store, sid, adapter, _, _, _, child, _ = local(tmp_path)
    assert adapter.query(operation(sid)).rows
    store.revoke(sid if target == "index" else child)
    with pytest.raises((AdapterAccessDenied, SnapshotAccessDenied)):
        adapter.query(operation(sid))


def test_corrupted_index_after_success_cannot_use_cached_scientific_rows(tmp_path):
    store, sid, adapter, _, _, _, _, _ = local(tmp_path)
    assert adapter.query(operation(sid)).rows
    manifest, _ = store.read(sid)
    metadata = next(o for o in manifest.objects if o.object_id == INDEX_OBJECT_ID)
    (tmp_path / "v1/catalogue/objects" / metadata.sha256).write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        adapter.query(operation(sid))


@pytest.mark.parametrize("field,value", [("access_binding", "user-b"), ("access_revision", "revision-2")])
@pytest.mark.parametrize("entry", ["list", "open", "query"])
def test_current_access_context_is_enforced_at_every_entry(tmp_path, field, value, entry):
    _, sid, adapter, _, _, _, _, _ = local(tmp_path)
    if entry == "query":
        request = operation(sid).model_copy(update={field: value})
        def call():
            return adapter.query(request)
    else:
        request = listing(sid, **{field: value})
        def call():
            return adapter.list(request) if entry == "list" else adapter.open(ANALYSIS, request)
    with pytest.raises(AdapterAccessDenied):
        call()


@pytest.mark.parametrize("field,value", [("source_id", "another-source"), ("source_family", "metagenome")])
def test_frozen_binding_identity_conflicts_fail_before_visibility_policy(tmp_path, field, value):
    def configure(payload, tables):
        payload["datasets"][0][field] = value
        if field == "source_family":
            payload["analyses"][0]["scope"] = adapter_scope("metagenome").model_dump(mode="json")
            payload["workflows"][0]["required_sources"].append("metagenome")

    _, sid, adapter, policy, _, _, _, _ = local(tmp_path, configure=configure)
    policy["datasets"].add(CTD)
    with pytest.raises((ValueError, AdapterAccessDenied)):
        adapter.list(listing(sid))


def test_changed_new_snapshot_does_not_relabel_or_replace_old_published_rows(tmp_path):
    store, sid, adapter, _, registry, tables, _, _ = local(tmp_path)
    original = adapter.query(operation(sid))
    newer = deepcopy(tables)
    newer[TABLE][0]["value"] = -999.0
    updated = seal_scientific_fixture(store, registry, newer, publication="publication-2")
    changed = adapter.query(operation(updated))
    replay = adapter.query(operation(sid))
    assert changed.rows[0]["value"] == -999
    assert changed.receipt.content_sha256 != original.receipt.content_sha256
    assert replay.rows == original.rows
    assert replay.receipt.model_dump(mode="json") == original.receipt.model_dump(mode="json")


@pytest.mark.parametrize(
    "outer,inner,parameters",
    [
        ("c13.coverage", "c10.coverage", {}),
        ("c13.operation", "c10.summary", {"table": "depth_observations", "column": "temperature"}),
        ("c13.operation", "c10.count", {"table": "casts"}),
    ],
)
def test_source_owned_operations_reconcile_exactly_with_actual_child_adapter(large, outer, inner, parameters):
    _, sid, adapter, _, _, _, child, source = large
    expected = source.query(OperationRequest(
        snapshot_id=child, scope=adapter_scope("ctd"), operation_id=inner,
        operation_version="c10-v1", input_ids=[CTD], parameters=parameters,
        access_binding="user-a", access_revision="revision-1",
    )).result
    outer_parameters = {} if outer == "c13.coverage" else {
        "operation_id": inner, "operation_version": "c10-v1", "parameters": parameters,
    }
    value = adapter.query(operation(sid, CTD, outer, **outer_parameters))
    assert value.rows == expected.rows
    assert value.columns == expected.columns
    assert value.receipt.operation_id == outer
    assert value.receipt.operation_version == "c13-v1"
    assert value.receipt.authority == "descriptive"
    assert value.receipt.total_rows == expected.receipt.total_rows
    assert value.receipt.availability == expected.receipt.availability


@pytest.mark.parametrize(
    "parameters",
    [
        {"limit": 0}, {"limit": 501}, {"offset": -1}, {"offset": True},
        {"table": "not-a-table"}, {"silently_ignored": True},
    ],
)
def test_invalid_or_unknown_table_parameters_cannot_return_apparently_valid_rows(large, parameters):
    _, sid, adapter, _, _, _, _, _ = large
    with pytest.raises((ValueError, AdapterAccessDenied)):
        adapter.query(operation(sid, **parameters))


@pytest.mark.parametrize(
    "changes",
    [
        {"operation_version": "c13-v2"}, {"operation_id": "c13.run_experiment"},
        {"input_ids": []}, {"input_ids": [ANALYSIS, CTD]},
    ],
)
def test_operations_require_one_supported_versioned_input(large, changes):
    _, sid, adapter, _, _, _, _, _ = large
    with pytest.raises(ValueError):
        adapter.query(operation(sid).model_copy(update=changes))


@pytest.mark.parametrize("decision", [None, 1, "approved", []])
def test_truthy_scientific_gate_values_cannot_authorize_published_rows(tmp_path, decision):
    store, sid, _, _, _, _, _, source = local(tmp_path)
    adapter = FrozenScientificCatalogueAdapter(
        store=store, adapters={"ctd": source},
        access=ScientificAccess("user-a", "revision-1", lambda snapshot, item: decision),
    )
    with pytest.raises(AdapterAccessDenied):
        adapter.query(operation(sid))


def test_unregistered_ctd_quality_is_unknown_instead_of_an_invented_grade(large):
    _, sid, adapter, _, _, _, _, _ = large
    value = adapter.query(operation(sid, CTD, "c13.quality"))
    assert value.rows == []
    assert value.receipt.availability.status == "unavailable"
    assert value.receipt.total_rows.state == "unknown"
    assert value.receipt.total_rows.value is None
    assert value.receipt.availability.reason
    assert value.qualifications


@pytest.fixture(scope="module")
def many_datasets(tmp_path_factory):
    store = LocalCatalogueSnapshotStore(
        root=tmp_path_factory.mktemp("c13-scientific-inventory").resolve(),
        access_gate=lambda manifest: True,
    )
    identities = [f"synthetic:ctd:campaign-{i:04d}" for i in range(1205)]
    child = seal_fixture(store, [ctd_fixture(0, dataset_id=identity) for identity in identities])
    registry, tables = scientific_fixture(0, bindings=[{
        "dataset_id": identity, "source_family": "ctd", "source_id": "synthetic-ctd", "snapshot_id": child,
    } for identity in identities])
    payload = registry.model_dump(mode="json")
    payload["analyses"][0]["scope"] = adapter_scope("ctd").model_dump(mode="json")
    sid = seal_scientific_fixture(store, ScientificRegistry.model_validate(payload), tables)
    policy = {"denied": set()}
    source = FrozenCatalogueAdapter(
        store=store, access=AdapterAccess("user-a", "revision-1", lambda snapshot, metadata: metadata.dataset_id not in policy["denied"]),
    )
    adapter = FrozenScientificCatalogueAdapter(
        store=store, adapters={"ctd": source},
        access=ScientificAccess("user-a", "revision-1", lambda snapshot, item: True),
    )
    return sid, adapter, identities, policy


def test_full_dataset_inventory_exceeds_previews_and_deduplicates_cross_root_links(many_datasets):
    sid, adapter, identities, _ = many_datasets
    page = adapter.list(listing(sid, limit=1, filters=CatalogueFilters(kinds=["dataset"])))
    assert len(page.items) == 1
    assert page.total.value == 1205
    assert page.next_cursor is not None
    for root in ("data", "analyses", "statistics", "metadata"):
        result = adapter.query(operation(sid, f"root:{root}", "c13.inventory"))
        assert result.rows[0]["count"] == len(identities)
        assert result.rows[0]["entity"] == "datasets"


def test_dataset_cursor_pages_reach_all_1205_canonical_objects_once(many_datasets):
    sid, adapter, identities, _ = many_datasets
    found, cursor = [], None
    while True:
        value = adapter.list(listing(sid, limit=500, cursor=cursor, filters=CatalogueFilters(kinds=["dataset"])))
        found.extend(item.id for item in value.items)
        assert value.total.value == 1205
        cursor = value.next_cursor
        if cursor is None:
            break
    assert found == identities
    assert len(found) == len(set(found)) == 1205


@pytest.mark.parametrize("identity", [CTD + ":collection", "c10:source:synthetic-ctd"])
@pytest.mark.parametrize("denied", [False, True])
def test_scientific_identity_cannot_collide_with_hidden_source_directories(tmp_path, identity, denied):
    def configure(payload, tables):
        payload["workflows"][0]["id"] = identity

    _, sid, adapter, policy, _, _, _, _ = local(tmp_path, configure=configure)
    if denied:
        policy["objects"].add(identity)
    with pytest.raises(ValueError, match="collid|identit"):
        adapter.list(listing(sid))


def test_statistics_exposes_named_operations_routable_through_its_index_snapshot(large):
    _, sid, adapter, _, _, _, _, _ = large
    result = adapter.list(listing(sid, parent_id="root:statistics"))
    assert len(result.items) == 1
    node = result.items[0]
    advertised = {op.id: op for op in node.operations}
    assert {"c13.coverage", "c13.operation"} <= set(advertised)
    assert all(op.version == "c13-v1" for op in advertised.values())
    delegated = adapter.query(operation(sid, node.id, "c13.coverage"))
    assert delegated.rows
    assert delegated.receipt.operation_id == "c13.coverage"


def test_copied_raw_nodes_do_not_advertise_native_operation_ids_against_index_snapshot(large):
    _, sid, adapter, _, _, _, _, _ = large
    nodes = adapter.list(listing(sid, filters=CatalogueFilters(roots=["data"]))).items
    assert nodes
    for node in nodes:
        assert all(op.id.startswith("c13.") and op.version == "c13-v1" for op in node.operations)
    analysis = adapter.open(ANALYSIS, listing(sid))
    table = adapter.open(TABLE, listing(sid))
    assert "c13.table" in {op.id for op in analysis.operations}
    assert "c13.table" in {op.id for op in table.operations}
