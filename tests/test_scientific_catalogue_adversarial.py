"""Independent C13 counterexamples for shared budgets, access and lineage."""

from io import BytesIO
import json

import pyarrow.parquet as pq
import pytest

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.immutable_bundle import digest
from ingestion.scientific_catalogue_inputs import _decoded_size
from orchestration import frozen_scientific_catalogue as implementation
from orchestration.frozen_catalogue import (
    AdapterAccess,
    AdapterAccessDenied,
    FrozenCatalogueAdapter,
)
from orchestration.frozen_scientific_catalogue import (
    FrozenScientificCatalogueAdapter,
    ScientificAccess,
)
from preprocessing import derived_artifacts
from schema.catalogue_adapter_fixtures import adapter_scope, ctd_fixture, seal_fixture
from schema.context_catalogue import ListingRequest, OperationRequest
from schema.scientific_catalogue_fixtures import (
    scientific_fixture,
    seal_scientific_fixture,
)


def test_receipts_and_workflow_links_do_not_disclose_denied_findings(tmp_path):
    denied = "synthetic:analysis:denied"
    hidden_table = denied + ":results"

    def configure(registry, tables):
        extra = registry.analyses[0].model_copy(deep=True)
        extra.id = denied
        extra.tables[0].object_id = hidden_table
        registry.analyses.append(extra)
        registry.workflows[0].analysis_ids.append(denied)
        tables[hidden_table] = [{**row, "value": 1000.0 + row["value"]} for row in tables[TABLE]]

    store, sid, adapter, _, _, _, _ = build(tmp_path, configure=configure)
    adapter.access = ScientificAccess("adversarial-user", "policy-1", lambda snapshot, item: item.id != denied)
    manifest, _ = store.read(sid)
    forbidden_hash = next(obj.sha256 for obj in manifest.objects if obj.object_id == hidden_table)
    for request in (query(sid), query(sid, identity=DATASET, operation_id="c13.coverage"), query(sid, identity="root:data", operation_id="c13.inventory")):
        result = adapter.query(request)
        wire = json.dumps(result.model_dump(mode="json"))
        assert hidden_table not in wire
        assert forbidden_hash not in wire
    workflow = adapter.inspect("synthetic:workflow:available", listing(sid))
    assert denied not in workflow["record"]["analysis_ids"]


def test_advertised_actions_route_through_scientific_envelope(tmp_path):
    _, sid, adapter, _, _, _, _ = build(tmp_path)
    nodes = adapter.list(listing(sid)).items
    assert all(action.id.startswith("c13.") and action.version == "c13-v1" for node in nodes for action in node.operations)
    statistic = next(node for node in nodes if node.root == "statistics" and node.kind == "statistic")
    assert {action.id for action in statistic.operations} >= {"c13.inventory", "c13.coverage", "c13.operation"}
    assert adapter.query(query(sid, identity=statistic.id, operation_id="c13.coverage")).receipt.availability.status == "available"
    analysis = next(node for node in nodes if node.id == ANALYSIS)
    assert "c13.table" in {action.id for action in analysis.operations}

DATASET = "synthetic:ctd:campaign-a"
ANALYSIS = "synthetic:analysis:published"
TABLE = ANALYSIS + ":results"


def build(tmp_path, *, count=4, configure=None):
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda m: True
    )
    child = seal_fixture(store, [ctd_fixture(4)])
    registry, tables = scientific_fixture(
        count,
        bindings=[
            {
                "dataset_id": DATASET,
                "source_family": "ctd",
                "source_id": "synthetic-ctd",
                "snapshot_id": child,
            }
        ],
    )
    if configure:
        configure(registry, tables)
    sid = seal_scientific_fixture(store, registry, tables)
    source = FrozenCatalogueAdapter(
        store=store,
        access=AdapterAccess("adversarial-user", "policy-1", lambda s, d: True),
    )
    adapter = FrozenScientificCatalogueAdapter(
        store=store,
        adapters={"ctd": source},
        access=ScientificAccess("adversarial-user", "policy-1", lambda s, item: True),
    )
    return store, sid, adapter, child, source, registry, tables


def listing(sid):
    return ListingRequest(
        snapshot_id=sid,
        scope=adapter_scope("ctd"),
        access_binding="adversarial-user",
        access_revision="policy-1",
    )


def query(sid, identity=ANALYSIS, operation_id="c13.table", **parameters):
    return OperationRequest(
        snapshot_id=sid,
        scope=adapter_scope("ctd"),
        operation_id=operation_id,
        operation_version="c13-v1",
        input_ids=[identity],
        parameters=parameters,
        access_binding="adversarial-user",
        access_revision="policy-1",
    )


def footer_totals(store, child):
    manifest, payloads = store.read(child)
    footers = [
        pq.ParquetFile(BytesIO(payloads[obj.object_id])).metadata
        for obj in manifest.objects
        if obj.schema_version == "catalogue-parquet-v1"
    ]
    return sum(f.num_rows for f in footers), sum(
        f.row_group(i).total_byte_size for f in footers for i in range(f.num_row_groups)
    )


def test_c10_footer_budget_is_checked_before_any_native_policy_or_decode(
    tmp_path, monkeypatch
):
    store, sid, adapter, child, source, _, _ = build(tmp_path, count=0)
    native_rows, _ = footer_totals(store, child)
    monkeypatch.setattr(implementation, "MAX_ROWS", native_rows - 1)
    monkeypatch.setattr(
        source,
        "_load",
        lambda request: pytest.fail("Decoded source before cumulative footer budget"),
    )
    with pytest.raises(ValueError, match="budget"):
        adapter.list(listing(sid))


def test_index_and_source_rows_share_one_operation_budget(tmp_path, monkeypatch):
    store, sid, adapter, child, _, _, tables = build(tmp_path, count=4)
    native_rows, _ = footer_totals(store, child)
    index_rows = len(tables[TABLE])
    monkeypatch.setattr(implementation, "MAX_ROWS", native_rows + index_rows - 1)
    with pytest.raises(ValueError, match="budget"):
        adapter.query(query(sid))


def test_index_and_source_decoded_bytes_share_one_operation_budget(
    tmp_path, monkeypatch
):
    store, sid, adapter, child, _, _, tables = build(tmp_path, count=4)
    _, native_bytes = footer_totals(store, child)
    index_bytes = _decoded_size(tables[TABLE])
    monkeypatch.setattr(
        implementation, "MAX_DECODED_BYTES", max(native_bytes, index_bytes) + 1
    )
    with pytest.raises(ValueError, match="budget"):
        adapter.query(query(sid))


def test_denied_raw_source_still_cannot_hide_excessive_frozen_decode_budget(
    tmp_path, monkeypatch
):
    store, sid, adapter, child, source, _, _ = build(tmp_path, count=0)
    native_rows, _ = footer_totals(store, child)
    source.access = AdapterAccess("adversarial-user", "policy-1", lambda s, d: False)
    monkeypatch.setattr(implementation, "MAX_ROWS", native_rows - 1)
    with pytest.raises(ValueError, match="budget"):
        adapter.list(listing(sid))


def test_source_and_registry_policies_receive_their_own_detached_types(tmp_path):
    _, sid, adapter, _, source, _, _ = build(tmp_path)
    seen = []

    def source_policy(snapshot, dataset):
        seen.append(("source", type(dataset).__name__))
        dataset.title.en = "Policy-local mutation"
        return True

    def scientific_policy(snapshot, item):
        seen.append(("scientific", type(item).__name__))
        assert hasattr(item, "id")
        item.title.en = "Policy-local mutation"
        return True

    source.access = AdapterAccess("adversarial-user", "policy-1", source_policy)
    adapter.access = ScientificAccess("adversarial-user", "policy-1", scientific_policy)
    finding = adapter.open(ANALYSIS, listing(sid))
    assert finding.title.en == "Published synthetic finding"
    assert ("source", "FrozenDataset") in seen
    assert ("scientific", "PublishedAnalysis") in seen
    assert all(kind != "DatasetBinding" for _, kind in seen)


def test_final_page_and_empty_tail_keep_full_total_and_c08_truncation_semantics(
    tmp_path,
):
    _, sid, adapter, _, _, _, _ = build(tmp_path, count=1205)
    page = adapter.query(query(sid, limit=500, offset=1000))
    assert len(page.rows) == 205
    assert page.next_offset is None
    assert page.receipt.total_rows.value == 1205
    assert page.receipt.preview_truncated
    tail = adapter.query(query(sid, limit=500, offset=1205))
    assert tail.rows == [] and tail.next_offset is None
    assert tail.receipt.total_rows.value == 1205
    assert tail.receipt.preview_truncated
    assert page.receipt.content_sha256 == tail.receipt.content_sha256


def test_scientific_access_revocation_never_changes_raw_dataset_membership(tmp_path):
    _, sid, adapter, _, _, _, _ = build(tmp_path)
    adapter.access = ScientificAccess(
        "adversarial-user", "policy-1", lambda s, item: item.id != ANALYSIS
    )
    with pytest.raises(AdapterAccessDenied):
        adapter.query(query(sid))
    assert adapter.open(DATASET, listing(sid)).id == DATASET


def test_derived_method_metadata_cannot_disagree_with_bound_review(tmp_path):
    def configure(registry, tables):
        analysis = registry.analyses[0]
        analysis.method_id = "taxa_env_correlation"
        analysis.method_version = "contradictory-declared-version"
        receipt = derived_artifacts.make_receipt(
            "taxa_env_correlation",
            digest({"results": tables[TABLE]}),
            {
                "status": "computed",
                "inputs": {d.dataset_id: d.snapshot_id for d in registry.datasets},
                "parameters": {"generation": "synthetic"},
            },
        )
        receipt.update(
            eligibility="eligible",
            review={
                "reviewer": "Synthetic researcher",
                "rationale": "Synthetic review only",
                "references": ["Synthetic acceptance"],
                "evidence_sha256": receipt["generation_sha256"],
            },
        )
        analysis.derived_receipt = receipt

    _, sid, adapter, _, _, _, _ = build(tmp_path, configure=configure)
    with pytest.raises(AdapterAccessDenied):
        adapter.query(query(sid))


@pytest.mark.parametrize("historical", ["invalidated", "superseded"])
def test_historical_derived_receipt_never_recovers_through_registry_rollover(
    tmp_path, historical
):
    def configure(registry, tables):
        analysis = registry.analyses[0]
        analysis.method_id = "taxa_env_correlation"
        analysis.method_version = derived_artifacts.CURRENT_METHODS[analysis.method_id]
        analysis.derived_receipt = derived_artifacts.make_receipt(
            analysis.method_id,
            digest({"results": tables[TABLE]}),
            {
                "status": "computed",
                "inputs": {d.dataset_id: d.snapshot_id for d in registry.datasets},
                "parameters": {},
            },
        )
        analysis.derived_receipt["eligibility"] = historical

    store, sid, adapter, _, _, registry, tables = build(tmp_path, configure=configure)
    newer = seal_scientific_fixture(
        store, registry, tables, publication="publication-2"
    )
    for snapshot in (sid, newer):
        with pytest.raises(AdapterAccessDenied):
            adapter.query(query(snapshot))
        assert adapter.open(DATASET, listing(snapshot)).id == DATASET


def test_cross_root_history_link_cannot_count_same_dataset_twice(tmp_path):
    _, sid, adapter, _, _, _, _ = build(tmp_path)
    for identity in ("root:data", "root:statistics", "root:metadata", "root:analyses"):
        value = adapter.query(query(sid, identity, "c13.inventory"))
        assert value.rows[0]["count"] == 1


def test_unavailable_workflow_description_cannot_be_a_published_finding(tmp_path):
    def configure(registry, tables):
        registry.workflows[0].availability.status = "unavailable"
        registry.workflows[0].availability.reason = "No approved execution service"

    _, sid, adapter, _, _, _, _ = build(tmp_path, configure=configure)
    workflow = adapter.open("synthetic:workflow:available", listing(sid))
    assert workflow.authority == "descriptive"
    assert workflow.availability.status == "unavailable"
    value = adapter.query(query(sid, workflow.id))
    assert value.rows == [] and value.receipt.availability.status == "unavailable"


@pytest.mark.parametrize(
    "operation", ["c13.run_experiment", "c13.approve", "c13.publish"]
)
def test_catalogue_does_not_create_experiments_or_approval_side_effects(
    tmp_path, operation
):
    _, sid, adapter, _, _, _, _ = build(tmp_path)
    with pytest.raises(ValueError):
        adapter.query(query(sid, operation_id=operation))
