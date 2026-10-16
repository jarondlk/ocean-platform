"""C13 cross-source acceptance using actual sealed C10, C11, and C12 adapters."""

import pytest

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from orchestration.frozen_catalogue import (
    AdapterAccess,
    AdapterAccessDenied,
    FrozenCatalogueAdapter,
)
from orchestration.frozen_edna_catalogue import EDNAAccess, FrozenEDNACatalogueAdapter
from orchestration.frozen_scientific_catalogue import (
    FrozenScientificCatalogueAdapter,
    ScientificAccess,
)
from orchestration.frozen_sst_catalogue import FrozenSSTCatalogueAdapter, SSTAccess
from retrieval.source_scope import EvidenceScope, FAMILIES
from schema.catalogue_adapter_fixtures import (
    ctd_fixture,
    metagenome_fixture,
    seal_fixture,
)
from schema.context_catalogue import CatalogueFilters, ListingRequest, OperationRequest
from schema.edna_catalogue_fixtures import edna_fixture, seal_edna_fixture
from schema.scientific_catalogue import ScientificRegistry
from schema.scientific_catalogue_fixtures import (
    scientific_fixture,
    scientific_scope,
    seal_scientific_fixture,
)
from schema.sst_catalogue_fixtures import seal_sst_fixture, sst_fixture
from tests.test_scientific_catalogue_relationships import (
    physical_relationship_fixture,
    relationship_fixture,
)

ANALYSIS = "synthetic:analysis:published"
WORKFLOW = "synthetic:workflow:available"
PHYSICAL = "synthetic:relationship:physical"
PROXIMITY = "synthetic:relationship:proximity"


def scope(*enabled, **filters):
    value = scientific_scope()
    if enabled:
        for family in FAMILIES:
            value["sources"][family]["enabled"] = family in enabled
    for family, values in filters.items():
        value["sources"][family]["filters"] = values
    return EvidenceScope.model_validate(value)


def listing(sid, *, selected=None, **changes):
    return ListingRequest(
        snapshot_id=sid,
        scope=selected or scope(),
        access_binding="user-a",
        access_revision="revision-1",
        **changes,
    )


def operation(sid, identity, op, *, selected=None, **params):
    return OperationRequest(
        snapshot_id=sid,
        scope=selected or scope(),
        operation_id=op,
        operation_version="c13-v1",
        input_ids=[identity],
        parameters=params,
        access_binding="user-a",
        access_revision="revision-1",
    )


def source_local(tmp_path, *, with_relationships=True, families=FAMILIES):
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda manifest: True
    )
    fixtures = {
        "ctd": ctd_fixture(4),
        "metagenome": metagenome_fixture(4),
        "remote_sensing": sst_fixture(8),
        "edna_metabarcoding": edna_fixture(12),
    }
    common = seal_fixture(store, [fixtures["ctd"], fixtures["metagenome"]])
    snapshots = {
        "ctd": common,
        "metagenome": common,
        "remote_sensing": seal_sst_fixture(store, [fixtures["remote_sensing"]]),
        "edna_metabarcoding": seal_edna_fixture(
            store, [fixtures["edna_metabarcoding"]]
        ),
    }
    bindings = [
        dict(
            dataset_id=fixtures[family][0].dataset_id,
            source_family=family,
            source_id=fixtures[family][0].source_id,
            snapshot_id=snapshots[family],
        )
        for family in families
    ]
    registry, tables = scientific_fixture(12, bindings=bindings)
    payload = registry.model_dump(mode="json")
    label = dict(en="Explicit retained source definition", ja="保持されたソース定義")
    payload["definitions"] = [
        dict(
            id="synthetic:definition:" + family,
            title=label,
            purpose=label,
            category="source_documentation",
            values=dict(source_family=family, source_reference="fixture://" + family),
            input_dataset_ids=[fixtures[family][0].dataset_id],
            provenance=dict(references=["Synthetic fixture only"]),
        )
        for family in families
    ]
    if with_relationships:
        physical, _ = physical_relationship_fixture()
        physical["id"] = PHYSICAL
        proximity, _ = relationship_fixture("proximity")
        proximity["id"] = PROXIMITY
        payload["relationships"] = [physical, proximity]
    registry = ScientificRegistry.model_validate(payload)
    sid = seal_scientific_fixture(store, registry, tables)
    policy = {"datasets": set(), "objects": set(), "sources": set()}

    def source_access(snapshot, metadata):
        return (
            metadata.dataset_id not in policy["datasets"]
            and metadata.family not in policy["sources"]
        )

    common_adapter = FrozenCatalogueAdapter(
        store=store, access=AdapterAccess("user-a", "revision-1", source_access)
    )
    adapters = dict(
        ctd=common_adapter,
        metagenome=common_adapter,
        remote_sensing=FrozenSSTCatalogueAdapter(
            store=store, access=SSTAccess("user-a", "revision-1", source_access)
        ),
        edna_metabarcoding=FrozenEDNACatalogueAdapter(
            store=store, access=EDNAAccess("user-a", "revision-1", source_access)
        ),
    )

    def scientific_access(snapshot, item):
        return (
            getattr(item, "dataset_id", getattr(item, "id", None))
            not in policy["objects"]
        )

    adapter = FrozenScientificCatalogueAdapter(
        store=store,
        adapters=adapters,
        access=ScientificAccess("user-a", "revision-1", scientific_access),
    )
    return store, sid, adapter, adapters, fixtures, snapshots, policy


@pytest.fixture(scope="module")
def all_sources(tmp_path_factory):
    return source_local(tmp_path_factory.mktemp("c13-cross-source"))


def native_operation(snapshot, identity, family, op, **parameters):
    prefix = (
        "c10"
        if family in {"ctd", "metagenome"}
        else "c11"
        if family == "remote_sensing"
        else "c12"
    )
    return OperationRequest(
        snapshot_id=snapshot,
        scope=scope(family),
        operation_id=prefix + "." + op,
        operation_version=prefix + "-v1",
        input_ids=[identity],
        parameters=parameters,
        access_binding="user-a",
        access_revision="revision-1",
    )


def result(value):
    return value.result if hasattr(value, "result") else value


def test_four_real_frozen_sources_have_one_canonical_data_membership_each(all_sources):
    _, sid, adapter, _, fixtures, snapshots, _ = all_sources
    assert snapshots["ctd"] == snapshots["metagenome"]
    roots = adapter.list(listing(sid, filters=CatalogueFilters(kinds=["root"])))
    assert {node.root for node in roots.items} == {
        "data",
        "analyses",
        "statistics",
        "metadata",
        "relationships",
    }
    datasets = adapter.list(listing(sid, filters=CatalogueFilters(kinds=["dataset"])))
    assert {node.id for node in datasets.items} == {
        metadata.dataset_id for metadata, _ in fixtures.values()
    }
    assert len(datasets.items) == 4
    assert all(
        node.root == "data" and node.snapshot_id == sid for node in datasets.items
    )
    assert adapter.dataset_count(listing(sid)).value == 4


@pytest.mark.parametrize(
    "root,expected",
    [
        ("data", 4),
        ("analyses", 4),
        ("statistics", 4),
        ("metadata", 4),
        ("relationships", 2),
    ],
)
def test_five_root_inventory_deduplicates_canonical_input_sets(
    all_sources, root, expected
):
    _, sid, adapter, _, _, _, _ = all_sources
    value = adapter.query(operation(sid, "root:" + root, "c13.inventory"))
    assert value.rows[0]["count"] == expected
    assert value.rows[0]["entity"] == "datasets"
    assert (
        adapter.dataset_count(listing(sid, parent_id="root:" + root)).value == expected
    )


@pytest.mark.parametrize("family", FAMILIES)
def test_c13_coverage_matches_exact_native_frozen_source_result(all_sources, family):
    _, sid, adapter, adapters, fixtures, snapshots, _ = all_sources
    identity = fixtures[family][0].dataset_id
    value = adapter.query(operation(sid, identity, "c13.coverage"))
    native = result(
        adapters[family].query(
            native_operation(
                snapshots[family], identity, family, "coverage", limit=100, offset=0
            )
        )
    )
    assert value.rows == native.rows
    assert value.columns == native.columns
    assert value.receipt.content_sha256 == native.receipt.content_sha256
    assert value.receipt.total_rows == native.receipt.total_rows
    assert value.receipt.source_completeness == native.receipt.source_completeness
    assert value.receipt.operation_id == "c13.coverage"
    assert value.receipt.snapshot_id == sid
    assert snapshots[family] in str(value.qualifications)


@pytest.mark.parametrize("family", ["remote_sensing", "edna_metabarcoding"])
def test_quality_delegates_native_source_count_without_redefining_scientific_entities(
    all_sources, family
):
    _, sid, adapter, adapters, fixtures, snapshots, _ = all_sources
    identity = fixtures[family][0].dataset_id
    value = adapter.query(operation(sid, identity, "c13.quality"))
    params = dict(limit=100, offset=0)
    if family == "edna_metabarcoding":
        params["population"] = "raw"
    native = result(
        adapters[family].query(
            native_operation(snapshots[family], identity, family, "count", **params)
        )
    )
    assert value.rows == native.rows
    assert value.receipt.content_sha256 == native.receipt.content_sha256
    assert value.receipt.total_rows.entity == native.receipt.total_rows.entity


@pytest.mark.parametrize("family", ["ctd", "metagenome"])
def test_quality_without_registered_native_operation_is_unavailable(
    all_sources, family
):
    _, sid, adapter, _, fixtures, _, _ = all_sources
    value = adapter.query(operation(sid, fixtures[family][0].dataset_id, "c13.quality"))
    assert value.rows == []
    assert value.receipt.availability.status == "unavailable"
    assert value.receipt.total_rows.state == "unknown"
    assert value.receipt.total_rows.value is None


@pytest.mark.parametrize(
    "family,table,population",
    [
        ("ctd", "depth_observations", None),
        ("metagenome", "run_qc", None),
        ("remote_sensing", None, None),
        ("edna_metabarcoding", "detections", "raw"),
    ],
)
def test_explicit_native_table_operation_preserves_page_and_full_population_hash(
    all_sources, family, table, population
):
    _, sid, adapter, adapters, fixtures, snapshots, _ = all_sources
    identity = fixtures[family][0].dataset_id
    prefix = (
        "c10"
        if family in {"ctd", "metagenome"}
        else "c11"
        if family == "remote_sensing"
        else "c12"
    )
    parameters = {}
    if table:
        parameters["table"] = table
    if population:
        parameters["population"] = population
    value = adapter.query(
        operation(
            sid,
            identity,
            "c13.operation",
            limit=2,
            offset=1,
            operation_id=prefix + ".table",
            operation_version=prefix + "-v1",
            parameters=parameters,
        )
    )
    native = result(
        adapters[family].query(
            native_operation(
                snapshots[family],
                identity,
                family,
                "table",
                limit=2,
                offset=1,
                **parameters,
            )
        )
    )
    assert value.rows == native.rows
    assert value.receipt.total_rows == native.receipt.total_rows
    assert value.receipt.content_sha256 == native.receipt.content_sha256
    assert value.offset == 1


@pytest.mark.parametrize("disabled", FAMILIES)
def test_disabled_family_and_its_dependent_science_do_not_inherit_index_carrier_eligibility(
    all_sources, disabled
):
    _, sid, adapter, _, fixtures, _, _ = all_sources
    selected = scope(*(family for family in FAMILIES if family != disabled))
    value = adapter.list(
        listing(sid, selected=selected, filters=CatalogueFilters(kinds=["dataset"]))
    )
    assert {node.id for node in value.items} == {
        metadata.dataset_id
        for family, (metadata, _) in fixtures.items()
        if family != disabled
    }
    assert adapter.dataset_count(listing(sid, selected=selected)).value == 3
    with pytest.raises(AdapterAccessDenied):
        adapter.open(ANALYSIS, listing(sid, selected=selected))
    with pytest.raises(AdapterAccessDenied):
        adapter.open(WORKFLOW, listing(sid, selected=selected))
    with pytest.raises(AdapterAccessDenied):
        adapter.open(fixtures[disabled][0].dataset_id, listing(sid, selected=selected))


@pytest.mark.parametrize("family", FAMILIES)
def test_native_current_dataset_access_denial_removes_dependent_objects(
    tmp_path, family
):
    _, sid, adapter, _, fixtures, _, policy = source_local(tmp_path)
    denied = fixtures[family][0].dataset_id
    policy["datasets"].add(denied)
    listed = adapter.list(listing(sid))
    assert denied not in {node.id for node in listed.items}
    assert ANALYSIS not in {node.id for node in listed.items}
    assert WORKFLOW not in {node.id for node in listed.items}
    assert adapter.dataset_count(listing(sid)).value == 3
    with pytest.raises(AdapterAccessDenied):
        adapter.open(denied, listing(sid))


def test_reviewed_physical_identity_is_retained_without_reclassifying_control_or_authorizing_comparison(
    all_sources,
):
    _, sid, adapter, _, _, _, _ = all_sources
    value = adapter.inspect(PHYSICAL, listing(sid))
    qualification = value["qualification"]
    assert qualification["validation_status"] == "verified_retained_registry"
    assert qualification["source_occurrences"] == 2
    assert qualification["classification_approval"] == "independent_not_granted"
    assert qualification["comparison_authorized"] is False
    assert value["node"].authority == "descriptive"
    assert value["node"].lifecycle.scientific_approval != "approved"


def test_proximity_remains_candidate_context_on_exact_retained_endpoints(all_sources):
    _, sid, adapter, _, _, _, _ = all_sources
    value = adapter.inspect(PROXIMITY, listing(sid))
    assert value["qualification"]["context_status"] == "candidate"
    assert value["qualification"]["physical_identity"] == "not_established"
    assert value["qualification"]["comparison_authorized"] is False


def test_denying_either_proximity_endpoint_removes_relationship_and_its_count(tmp_path):
    _, sid, adapter, _, fixtures, _, policy = source_local(tmp_path)
    policy["datasets"].add(fixtures["ctd"][0].dataset_id)
    with pytest.raises(AdapterAccessDenied):
        adapter.open(PROXIMITY, listing(sid))
    value = adapter.query(operation(sid, "root:relationships", "c13.inventory"))
    assert value.rows[0]["count"] == 1
    assert adapter.open(PHYSICAL, listing(sid)).id == PHYSICAL


def test_source_specific_filters_do_not_rewrite_other_source_scopes(all_sources):
    _, sid, adapter, adapters, fixtures, snapshots, _ = all_sources
    identity = fixtures["ctd"][0].dataset_id
    selected = scope(ctd=dict(station="station-1"))
    value = adapter.query(operation(sid, identity, "c13.coverage", selected=selected))
    request = native_operation(
        snapshots["ctd"], identity, "ctd", "coverage", limit=100, offset=0
    )
    request.scope.sources.ctd.filters.station = "station-1"
    native = result(adapters["ctd"].query(request))
    assert value.rows == native.rows
    assert value.receipt.content_sha256 == native.receipt.content_sha256
    assert adapter.dataset_count(listing(sid, selected=selected)).value == 4


def test_child_access_revision_cannot_be_accepted_under_current_index_context(tmp_path):
    _, sid, adapter, adapters, _, _, _ = source_local(tmp_path)
    adapters["remote_sensing"].access = SSTAccess(
        "user-a", "revision-2", lambda snapshot, metadata: True
    )
    with pytest.raises(AdapterAccessDenied, match="source access context"):
        adapter.list(listing(sid))


def test_c10_source_rows_participate_in_cross_source_preflight_budget(
    tmp_path, monkeypatch
):
    import orchestration.frozen_scientific_catalogue as scientific

    _, sid, adapter, _, _, _, _ = source_local(
        tmp_path, with_relationships=False, families=("ctd", "metagenome")
    )
    monkeypatch.setattr(scientific, "MAX_ROWS", 1)
    with pytest.raises(ValueError, match="complete source decode budget"):
        adapter.list(listing(sid))
