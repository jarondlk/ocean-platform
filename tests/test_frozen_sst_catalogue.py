"""Independent C11 exact SST semantics over immutable synthetic populations."""

import hashlib
from io import BytesIO

import pandas as pd
import pyarrow.parquet as pq
import pytest

from ingestion.catalogue_snapshot import (
    LocalCatalogueSnapshotStore,
    SnapshotAccessDenied,
)
from ingestion.sst_catalogue_inputs import SSTUnavailable, parse_table
from orchestration.frozen_sst_catalogue import (
    AdapterAccessDenied,
    FrozenSSTCatalogueAdapter,
    SSTAccess,
)
from schema.context_catalogue import CatalogueFilters, ListingRequest, OperationRequest
from schema.sst_catalogue_fixtures import (
    seal_sst_fixture,
    sst_fixture,
    sst_scope,
)

FINAL = "synthetic:sst:mur-final"
INTERIM = "synthetic:sst:mur-interim"


def listing(snapshot, **changes):
    return ListingRequest.model_validate(
        {
            "snapshot_id": snapshot,
            "scope": sst_scope().model_dump(mode="json"),
            "access_binding": "user-a",
            "access_revision": "revision-1",
            **changes,
        }
    )


def operation(snapshot, identity=FINAL, op="c11.table", *, scope=None, **parameters):
    return OperationRequest(
        snapshot_id=snapshot,
        scope=scope or sst_scope(),
        operation_id=op,
        operation_version="c11-v1",
        input_ids=[identity],
        parameters=parameters,
        access_binding="user-a",
        access_revision="revision-1",
    )


def local(tmp_path, datasets=None, *, allowed=None):
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda manifest: True
    )
    sid = seal_sst_fixture(store, datasets or [sst_fixture(8)])
    policy = {"denied": set(), "eligible": True}

    def eligible(snapshot, metadata):
        return policy["eligible"] and metadata.dataset_id not in policy["denied"]

    adapter = FrozenSSTCatalogueAdapter(
        store=store, access=SSTAccess("user-a", "revision-1", allowed or eligible)
    )
    return store, sid, adapter, policy


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    return local(tmp_path_factory.mktemp("c11-large"), [sst_fixture(1205)])


@pytest.mark.parametrize("limit", [1, 25, 100, 500])
def test_preview_does_not_limit_complete_population_or_receipt(large, limit):
    _, sid, adapter, _ = large
    value = adapter.query(operation(sid, limit=limit))
    reference = adapter.query(operation(sid, limit=500))
    assert len(value.result.rows) == limit
    assert value.result.receipt.total_rows.value == 1205
    assert (
        value.result.receipt.content_sha256 == reference.result.receipt.content_sha256
    )
    assert value.next_offset == limit
    assert value.result.receipt.preview_truncated


def test_pages_reach_all_retained_observations_once_including_quality_states(large):
    _, sid, adapter, _ = large
    rows, offset = [], 0
    while True:
        value = adapter.query(operation(sid, offset=offset, limit=500))
        rows.extend(value.result.rows)
        if value.next_offset is None:
            break
        offset = value.next_offset
    assert len(rows) == len({row["observation_id"] for row in rows}) == 1205
    assert {row["status"] for row in rows} == {"valid", "invalid", "excluded"}
    assert sum(row["value"] is None for row in rows) == 1
    assert sum(row["value"] == 0 for row in rows) == 1


def test_exact_counts_name_daily_summary_entity_and_quality_denominator(large):
    _, sid, adapter, _ = large
    result = adapter.query(operation(sid, op="c11.count", limit=1)).result
    row = result.rows[0]
    assert row["count"] == 1202
    assert row["entity"] == "regional_daily_summary"
    assert row["excluded_count"] == row["invalid_count"] == 1
    assert row["missing_value_count"] == 1
    assert row["denominator"]
    assert result.receipt.total_rows.value == 1
    assert result.receipt.authority == "descriptive"
    assert result.receipt.operation_version == "c11-v1"


def test_exact_summary_excludes_quality_failures_and_retains_zero_and_units(large):
    _, sid, adapter, _ = large
    result = adapter.query(operation(sid, op="c11.summary", limit=1)).result
    row = result.rows[0]
    assert row["n_observed"] == 1202
    assert row["n_missing"] == row["n_zero"] == 1
    assert row["minimum"] == 0
    assert row["maximum"] == 1204
    assert row["mean"] == pytest.approx(sum(range(4, 1205)) / 1202)
    assert (
        next(column for column in result.columns if column.key == "mean").unit == "degC"
    )
    assert result.receipt.total_rows.value == 1


def test_daily_coverage_uses_full_calendar_including_leap_day_and_quality_gaps(large):
    _, sid, adapter, _ = large
    row = adapter.query(operation(sid, op="c11.coverage", limit=1)).result.rows[0]
    assert row["calendar"] == "UTC"
    assert row["observation_entity"] == "regional_daily_summary"
    assert row["observed_observations"] == row["observed_days"] == 1202
    assert row["expected_days"] == 1206
    assert row["missing_days"] == 4
    assert row["missing_dates"] == [
        "2024-02-28",
        "2024-02-29",
        "2024-03-01",
        "2024-03-02",
    ]
    assert row["coverage_state"] == "known"


def test_missing_final_day_is_known_gap_while_table_and_count_are_known_zero(tmp_path):
    _, sid, adapter, _ = local(tmp_path)
    scope = sst_scope(time_from="2024-02-29", time_to="2024-02-29")
    table = adapter.query(operation(sid, scope=scope)).result
    assert table.rows == [] and table.receipt.total_rows.value == 0
    count = adapter.query(operation(sid, op="c11.count", scope=scope)).result
    assert count.rows[0]["count"] == 0
    summary = adapter.query(operation(sid, op="c11.summary", scope=scope)).result.rows[
        0
    ]
    assert summary["n_observed"] == summary["n_missing"] == 0
    assert summary["mean"] is summary["minimum"] is summary["maximum"] is None
    coverage = adapter.query(
        operation(sid, op="c11.coverage", scope=scope)
    ).result.rows[0]
    assert coverage["observed_days"] == 0
    assert coverage["expected_days"] == coverage["missing_days"] == 1
    assert coverage["missing_dates"] == ["2024-02-29"]
    assert coverage["coverage_state"] == "known"


def test_unknown_sampling_does_not_infer_expected_dates_from_observed_extent(tmp_path):
    _, sid, adapter, _ = local(tmp_path, [sst_fixture(8, sampling=False)])
    row = adapter.query(operation(sid, op="c11.coverage")).result.rows[0]
    assert row["observed_days"] == 5
    assert row["coverage_state"] == "unknown"
    assert row["expected_days"] is row["missing_days"] is row["missing_dates"] is None
    assert row["reason"]


def test_partial_population_cannot_claim_exact_count_or_fill_sampling_gaps(tmp_path):
    metadata, frames = sst_fixture(8)
    metadata.table.completeness = "partial"
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    table = adapter.query(operation(sid)).result
    assert len(table.rows) == 8
    assert table.receipt.query_completion == "partial"
    assert table.receipt.total_rows.state == "unknown"
    for op in ("c11.count", "c11.summary"):
        result = adapter.query(operation(sid, op=op)).result
        assert result.rows == []
        assert result.receipt.availability.status == "unavailable"
        assert result.receipt.total_rows.value is None
    row = adapter.query(operation(sid, op="c11.coverage")).result.rows[0]
    assert row["observed_days"] == 5
    assert row["coverage_state"] == "unknown"
    assert row["expected_days"] is row["missing_days"] is row["missing_dates"] is None


def test_incomplete_population_cannot_hide_a_dataset_as_known_zero_scoped_inventory(
    tmp_path,
):
    metadata, frames = sst_fixture(8)
    metadata.table.completeness = "partial"
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    # The missing leap-day row is absent from this partial export. That absence
    # cannot establish that the actual dataset has no matching observations.
    scope = sst_scope(time_from="2024-02-29", time_to="2024-02-29")
    request = listing(sid, scope=scope, filters=CatalogueFilters(kinds=["dataset"]))
    try:
        inventory = adapter.list(request)
    except SSTUnavailable:
        return  # Explicitly unavailable scoped inventory is also honest.
    assert inventory.total.value == 1
    assert inventory.items[0].id == FINAL
    assert inventory.items[0].lifecycle.ingestion == "partial"


def test_unavailable_product_is_visible_but_is_not_a_known_empty_table(tmp_path):
    metadata, frames = sst_fixture(0)
    metadata.table.object_id = metadata.table.row_count = None
    metadata.table.completeness = "unavailable"
    metadata.table.availability.status = "unavailable"
    metadata.table.availability.reason = "Product inputs deliberately not supplied"
    frames.clear()
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    assert adapter.dataset_count(listing(sid)).value == 1
    for op in ("c11.table", "c11.count", "c11.summary", "c11.coverage"):
        result = adapter.query(operation(sid, op=op)).result
        assert result.rows == []
        assert result.receipt.total_rows.state == "unknown"
        assert result.receipt.availability.status == "unavailable"


def test_known_empty_product_has_zero_observations_without_claiming_unknown(tmp_path):
    _, sid, adapter, _ = local(tmp_path, [sst_fixture(0)])
    result = adapter.query(operation(sid, op="c11.count")).result
    assert result.rows[0]["count"] == 0
    assert result.receipt.availability.status == "available"
    assert result.receipt.query_completion == "complete"


def test_dataset_id_selection_retains_known_empty_dataset_inventory(tmp_path):
    _, sid, adapter, _ = local(tmp_path, [sst_fixture(0)])
    scope = sst_scope(dataset_id=FINAL)
    request = listing(sid, scope=scope, filters=CatalogueFilters(kinds=["dataset"]))
    inventory = adapter.list(request)
    assert inventory.total.value == adapter.dataset_count(request).value == 1
    assert [node.id for node in inventory.items] == [FINAL]
    assert (
        adapter.query(operation(sid, op="c11.count", scope=scope)).result.rows[0][
            "count"
        ]
        == 0
    )


def test_unknown_product_inputs_remain_visible_without_a_false_zero(tmp_path):
    metadata, frames = sst_fixture(0)
    metadata.table.object_id = metadata.table.row_count = None
    metadata.table.completeness = "unknown"
    metadata.table.availability.status = "unknown"
    metadata.table.availability.reason = (
        "Product input availability has not been established"
    )
    frames.clear()
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    scope = sst_scope(dataset_id=FINAL)
    request = listing(sid, scope=scope, filters=CatalogueFilters(kinds=["dataset"]))
    inventory = adapter.list(request)
    assert inventory.total.value == adapter.dataset_count(request).value == 1
    assert inventory.items[0].availability.status == "unknown"
    result = adapter.query(operation(sid, op="c11.count", scope=scope)).result
    assert result.rows == [] and result.receipt.total_rows.value is None


@pytest.mark.parametrize(
    "start,end",
    [
        ("2023-01-01", "2023-01-31"),
        ("2024-02-26", "2024-03-03"),
        ("2024-02-27", "2024-03-07"),
    ],
)
def test_request_outside_sampling_contract_does_not_invent_expected_days(
    tmp_path, start, end
):
    _, sid, adapter, _ = local(tmp_path)
    scope = sst_scope(time_from=start, time_to=end)
    coverage = adapter.query(
        operation(sid, op="c11.coverage", scope=scope)
    ).result.rows[0]
    assert coverage["coverage_state"] == "unknown"
    assert coverage["expected_days"] is coverage["missing_days"] is None
    assert coverage["reason"]


def test_parity_with_legacy_synthetic_regional_daily_rows_and_known_final_gap(tmp_path):
    from ingestion.regional_publication import daily_rows
    from tests.test_provisional_research_demo import fixture

    _, legacy_inputs = fixture()
    period = legacy_inputs["period_preview"]
    retained = [
        row for row in period["observations"] if row["time_utc"][:10] != "2021-02-20"
    ]
    period["observations"] = retained
    legacy_rows = daily_rows({"period": period})
    metadata, frames = sst_fixture(len(retained), precision="datetime")
    metadata.sampling.start, metadata.sampling.end = "2020-01-01", "2023-12-31"
    frames["observations"] = pd.DataFrame(
        [
            {
                "observation_id": row["observation_id"],
                "time": row["time_utc"],
                "value": row["sst_celsius"],
                "status": "valid",
                "lat": None,
                "lon": None,
                "quality_flag": "accepted",
                "uncertainty": None,
                "source_sha256": row["raw_sha256"],
                "exclusion_reason": None,
            }
            for row in retained
        ],
        columns=frames["observations"].columns,
    )
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    result = adapter.query(operation(sid, op="c11.summary")).result.rows[0]
    expected = [row["mean_sst"] for row in legacy_rows]
    assert result["n_observed"] == 1460
    assert result["mean"] == pytest.approx(sum(expected) / 1460)
    assert (result["minimum"], result["maximum"]) == (min(expected), max(expected))
    february = sst_scope(time_from="2021-02-01", time_to="2021-02-28")
    assert (
        adapter.query(operation(sid, op="c11.count", scope=february)).result.rows[0][
            "count"
        ]
        == 27
    )
    row = adapter.query(operation(sid, op="c11.coverage")).result.rows[0]
    assert row["observed_days"] == 1460 and row["expected_days"] == 1461
    assert row["missing_dates"] == ["2021-02-20"]
    assert (
        metadata.calendar == "UTC"
    )  # The old helper's date_jst label copied UTC dates.


def test_regional_summary_cannot_recreate_underlying_grid_points(large):
    _, sid, adapter, _ = large
    result = adapter.query(operation(sid, op="c11.grid_points")).result
    assert result.rows == []
    assert result.receipt.availability.status == "unavailable"
    assert result.receipt.total_rows.value is None
    node = adapter.open(FINAL, listing(sid))
    assert (
        next(
            op for op in node.operations if op.id == "c11.grid_points"
        ).availability.status
        == "unavailable"
    )


def test_product_isolation_does_not_fill_final_gap_with_interim_observation(tmp_path):
    final, final_frames = sst_fixture(8)
    interim, interim_frames = sst_fixture(8, dataset_id=INTERIM, generation="interim")
    # The retained final gap is 2024-02-29. An interim value on that day cannot
    # become a final observation even when another product is in the snapshot.
    interim_frames["observations"].loc[0, "time"] = "2024-02-29"
    _, sid, adapter, _ = local(
        tmp_path, [(final, final_frames), (interim, interim_frames)]
    )
    scope = sst_scope(time_from="2024-02-29", time_to="2024-02-29")
    assert (
        adapter.query(operation(sid, op="c11.count", scope=scope)).result.rows[0][
            "count"
        ]
        == 0
    )
    assert (
        adapter.query(operation(sid, INTERIM, "c11.count", scope=scope)).result.rows[0][
            "count"
        ]
        == 1
    )
    assert adapter.dataset_count(listing(sid)).value == 2


def test_dataset_mismatch_is_empty_before_unrelated_geographic_incompatibility(
    tmp_path,
):
    _, sid, adapter, _ = local(tmp_path)
    scope = sst_scope(
        dataset_id=INTERIM, lat_min=30.0, lat_max=45.0, lon_min=130.0, lon_max=150.0
    )
    result = adapter.query(operation(sid, op="c11.count", scope=scope)).result
    assert result.rows[0]["count"] == 0


def test_operations_never_silently_combine_product_inputs(tmp_path):
    _, sid, adapter, _ = local(tmp_path)
    request = operation(sid, op="c11.summary").model_dump(mode="json")
    request["input_ids"] = [FINAL, INTERIM]
    with pytest.raises(ValueError):
        adapter.query(request)


def test_product_units_are_retained_and_never_silently_converted(tmp_path):
    kelvin, frames = sst_fixture(8, dataset_id=INTERIM, generation="interim")
    kelvin.descriptor.unit = "K"
    frames["observations"]["value"] = frames["observations"]["value"] + 273.15
    _, sid, adapter, _ = local(tmp_path, [sst_fixture(8), (kelvin, frames)])
    celsius = adapter.query(operation(sid, op="c11.summary")).result
    retained = adapter.query(operation(sid, INTERIM, "c11.summary")).result
    assert celsius.rows[0]["mean"] == pytest.approx(4.4)
    assert retained.rows[0]["mean"] == pytest.approx(277.55)
    assert retained.rows[0]["minimum"] == 273.15
    assert retained.rows[0]["unit"] == "K"
    assert (
        next(column for column in retained.columns if column.key == "mean").unit == "K"
    )
    assert adapter.open(INTERIM, listing(sid)).descriptor.unit == "K"


def test_all_dataset_sections_and_product_collection_parentage_are_explicit(large):
    _, sid, adapter, _ = large
    req = listing(sid)
    inspection = adapter.inspect(FINAL, req)
    assert set(inspection) == {
        "node",
        "overview",
        "tables",
        "coverage",
        "methods",
        "provenance",
        "related",
    }
    node = inspection["node"]
    assert node.sections == [
        "overview",
        "tables",
        "coverage",
        "methods",
        "provenance",
        "related",
    ]
    assert node.source_family == "remote_sensing"
    assert node.lifecycle.scientific_approval == "not_reviewed"
    assert node.lifecycle.embedding_readiness == "unknown"
    collection = adapter.open(node.parent_id, req)
    product = adapter.open(collection.parent_id, req)
    sst = adapter.open(product.parent_id, req)
    assert collection.kind == product.kind == sst.kind == "directory"
    assert sst.parent_id == "root:data"
    assert adapter.dataset_count(req).value == 1


def test_statistics_and_metadata_links_reference_the_same_canonical_dataset(large):
    _, sid, adapter, _ = large
    references = adapter.list(
        listing(sid, filters=CatalogueFilters(kinds=["reference"]))
    )
    assert {node.root for node in references.items} == {"statistics", "metadata"}
    assert len(references.items) == 2
    assert all(node.related_ids == [FINAL] for node in references.items)
    assert adapter.dataset_count(listing(sid)).value == 1
    assert (
        adapter.dataset_count(
            listing(sid, filters=CatalogueFilters(roots=["statistics"]))
        ).value
        == 0
    )


def test_listing_reaches_late_dataset_and_count_ignores_paging(tmp_path):
    datasets = [
        sst_fixture(1, dataset_id=f"synthetic:sst:dataset-{i:03d}") for i in range(32)
    ]
    _, sid, adapter, policy = local(tmp_path, datasets)
    req = listing(sid, filters=CatalogueFilters(kinds=["dataset"]), limit=25)
    first = adapter.list(req)
    second = adapter.list(req.model_copy(update={"cursor": first.next_cursor}))
    assert (
        first.total.value
        == second.total.value
        == adapter.dataset_count(req).value
        == 32
    )
    assert len(first.items) == 25 and len(second.items) == 7
    assert second.items[-1].id == "synthetic:sst:dataset-031"
    policy["denied"].add("synthetic:sst:dataset-031")
    assert adapter.dataset_count(req).value == 31


def test_revoked_related_dataset_is_not_disclosed_as_a_crosslink(tmp_path):
    first, frames = sst_fixture(8)
    second = sst_fixture(8, dataset_id=INTERIM, generation="interim")
    first.related_ids = [INTERIM]
    _, sid, adapter, policy = local(tmp_path, [(first, frames), second])
    assert INTERIM in adapter.open(FINAL, listing(sid)).related_ids
    policy["denied"].add(INTERIM)
    assert INTERIM not in adapter.open(FINAL, listing(sid)).related_ids
    with pytest.raises(AdapterAccessDenied):
        adapter.open(INTERIM, listing(sid))


def test_retained_snapshot_reopens_identically_after_publication_rollover(tmp_path):
    store, original, adapter, _ = local(tmp_path)
    before = adapter.query(operation(original, op="c11.summary"))
    metadata, frames = sst_fixture(8)
    mask = frames["observations"].status.eq("valid")
    frames["observations"].loc[mask, "value"] = 77.0
    newer = seal_sst_fixture(store, [(metadata, frames)], publication="publication-2")
    reopened = FrozenSSTCatalogueAdapter(
        store=LocalCatalogueSnapshotStore(
            root=tmp_path.resolve(), access_gate=lambda manifest: True
        ),
        access=adapter.access,
    )
    assert newer != original
    assert reopened.query(operation(original, op="c11.summary")) == before
    assert (
        reopened.query(operation(newer, op="c11.summary")).result.rows[0]["mean"]
        == 77.0
    )
    manifest, contents = store.read(original)
    assert all(
        hashlib.sha256(contents[item.object_id]).hexdigest() == item.content_sha256
        for item in before.result.receipt.inputs
    )
    assert all(obj.source_family == "remote_sensing" for obj in manifest.objects)
    assert store.latest() == (None, 0)


@pytest.mark.parametrize("action", ["store-revoke", "current-gate", "dataset-policy"])
def test_current_access_overrides_previously_read_historical_bytes(tmp_path, action):
    store, sid, adapter, policy = local(tmp_path)
    assert adapter.query(operation(sid)).result.rows
    if action == "store-revoke":
        store.revoke(sid)
    elif action == "current-gate":
        store.access_gate = lambda manifest: False
    else:
        policy["denied"].add(FINAL)
    error = AdapterAccessDenied if action == "dataset-policy" else SnapshotAccessDenied
    with pytest.raises(error):
        adapter.query(operation(sid))


@pytest.mark.parametrize(
    "field,value", [("access_binding", "other-user"), ("access_revision", "revision-2")]
)
def test_access_context_is_current_and_exact(tmp_path, field, value):
    _, sid, adapter, _ = local(tmp_path)
    request = operation(sid).model_copy(update={field: value})
    with pytest.raises(AdapterAccessDenied):
        adapter.query(request)


def test_policy_mutation_cannot_change_frozen_science_and_truthy_is_denied(tmp_path):
    def mutate(snapshot, metadata):
        metadata.table.row_count = 0
        return True

    _, sid, adapter, _ = local(tmp_path, allowed=mutate)
    assert adapter.query(operation(sid)).result.receipt.total_rows.value == 8
    adapter.access = SSTAccess("user-a", "revision-1", lambda snapshot, metadata: 1)
    assert adapter.dataset_count(listing(sid)).value == 0


@pytest.mark.parametrize(
    "parameters",
    [
        {"unexpected": True},
        {"table": "observations"},
        {"limit": 0},
        {"limit": 501},
        {"offset": -1},
        {"limit": "5"},
        {"offset": True},
    ],
)
def test_table_parameters_reject_ambiguous_or_unbounded_inputs(tmp_path, parameters):
    _, sid, adapter, _ = local(tmp_path)
    with pytest.raises(ValueError):
        adapter.query(operation(sid, **parameters))


@pytest.mark.parametrize("op", ["c11.count", "c11.summary"])
def test_aggregate_offsets_cannot_hide_result_population(tmp_path, op):
    _, sid, adapter, _ = local(tmp_path)
    with pytest.raises(ValueError):
        adapter.query(operation(sid, op=op, offset=1))


@pytest.mark.parametrize(
    "scope",
    [
        {"lat_min": 37.0, "lat_max": 40.0, "lon_min": 140.0, "lon_max": 143.0},
        {"lat_min": 38.2, "lat_max": 38.8, "lon_min": 141.2, "lon_max": 141.8},
    ],
)
def test_regional_mean_is_neither_extrapolated_nor_recomputed_for_new_region(
    tmp_path, scope
):
    _, sid, adapter, _ = local(tmp_path)
    result = adapter.query(
        operation(sid, op="c11.summary", scope=sst_scope(**scope))
    ).result
    assert result.rows == []
    assert result.receipt.availability.status == "unavailable"
    assert result.receipt.total_rows.value is None


def test_exact_retained_region_can_answer_without_improving_resolution(tmp_path):
    _, sid, adapter, _ = local(tmp_path)
    scope = sst_scope(lat_min=38.0, lat_max=39.0, lon_min=141.0, lon_max=142.0)
    result = adapter.query(operation(sid, op="c11.count", scope=scope)).result
    assert result.rows[0]["count"] == 5
    node = adapter.open(FINAL, listing(sid))
    assert node.descriptor.spatial_resolution == 0.05
    assert node.descriptor.spatial_resolution_unit == "degree"


def test_grid_observations_are_counted_as_points_and_narrow_bbox_is_exact(tmp_path):
    _, sid, adapter, _ = local(tmp_path, [sst_fixture(8, entity="grid_observation")])
    scope = sst_scope(lat_min=38.2, lat_max=38.3, lon_min=141.2, lon_max=141.3)
    rows = adapter.query(operation(sid, op="c11.grid_points", scope=scope)).result.rows
    assert len(rows) == 4
    assert {row["lat"] for row in rows} == {38.25}
    assert {row["lon"] for row in rows} == {141.25}
    row = adapter.query(operation(sid, op="c11.count", scope=scope)).result.rows[0]
    assert (
        row["count"] == 3
    )  # indices 0, 4 and 6; invalid index 2 is retained separately.
    assert row["entity"] == "grid_observation"
    coverage = adapter.query(
        operation(sid, op="c11.coverage", scope=scope)
    ).result.rows[0]
    assert coverage["observed_observations"] == 3
    assert coverage["coverage_state"] == "unknown"
    assert (
        coverage["expected_days"] is None
    )  # Dataset sampling does not describe every subregion.


def test_grid_product_cannot_answer_a_wider_region(tmp_path):
    _, sid, adapter, _ = local(tmp_path, [sst_fixture(8, entity="grid_observation")])
    scope = sst_scope(lat_min=37.9, lat_max=39.0, lon_min=141.0, lon_max=142.0)
    result = adapter.query(operation(sid, op="c11.count", scope=scope)).result
    assert result.rows == []
    assert result.receipt.availability.status == "unavailable"


def test_grid_point_bbox_does_not_infer_a_complete_area_or_calendar(tmp_path):
    _, sid, adapter, _ = local(tmp_path, [sst_fixture(8, entity="grid_observation")])
    scope = sst_scope(lat_min=38.25, lat_max=38.25, lon_min=141.25, lon_max=141.25)
    result = adapter.query(operation(sid, op="c11.grid_points", scope=scope)).result
    assert len(result.rows) == 4
    assert all(row["lat"] == 38.25 and row["lon"] == 141.25 for row in result.rows)
    coverage = adapter.query(
        operation(sid, op="c11.coverage", scope=scope)
    ).result.rows[0]
    assert coverage["expected_days"] is coverage["missing_days"] is None
    assert coverage["coverage_state"] == "unknown"


def test_partial_day_request_cannot_invent_hourly_values_from_tokyo_day_summary(
    tmp_path,
):
    utc = sst_fixture(8)
    tokyo = sst_fixture(
        8, dataset_id=INTERIM, generation="interim", calendar="Asia/Tokyo"
    )
    _, sid, adapter, _ = local(tmp_path, [utc, tokyo])
    scope = sst_scope(time_from="2024-02-26T16:00:00Z", time_to="2024-02-26T17:00:00Z")
    assert (
        adapter.query(operation(sid, op="c11.count", scope=scope)).result.rows[0][
            "count"
        ]
        == 0
    )
    result = adapter.query(operation(sid, INTERIM, scope=scope)).result
    assert result.rows == []
    assert result.receipt.availability.status == "unavailable"


def test_whole_tokyo_day_retains_date_label_and_explicit_calendar(tmp_path):
    _, sid, adapter, _ = local(tmp_path, [sst_fixture(8, calendar="Asia/Tokyo")])
    scope = sst_scope(
        time_from="2024-02-26T15:00:00Z", time_to="2024-02-27T14:59:59.999999Z"
    )
    result = adapter.query(operation(sid, scope=scope)).result
    assert result.rows[0]["time"] == "2024-02-27"
    assert "T" not in result.rows[0]["time"]
    coverage = adapter.query(
        operation(sid, op="c11.coverage", scope=scope)
    ).result.rows[0]
    assert coverage["calendar"] == "Asia/Tokyo"
    assert coverage["expected_days"] == coverage["observed_days"] == 1
    assert coverage["missing_days"] == 0


def test_datetime_precision_compares_real_instants_and_retains_offset(tmp_path):
    metadata, frames = sst_fixture(8, calendar="Asia/Tokyo", precision="datetime")
    frames["observations"].loc[0, "time"] = "2024-02-27T00:30:00+09:00"
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    scope = sst_scope(time_from="2024-02-26T15:00:00Z", time_to="2024-02-26T16:00:00Z")
    row = adapter.query(operation(sid, scope=scope)).result.rows[0]
    assert row["time"] == "2024-02-27T00:30:00+09:00"
    assert row["value"] == 0
    assert (
        adapter.query(operation(sid, op="c11.count", scope=scope)).result.rows[0][
            "count"
        ]
        == 1
    )


def test_legacy_c09_sst_fixture_is_not_silently_reinterpreted_as_product_contract(
    tmp_path, monkeypatch
):
    from ingestion.catalogue_snapshot_fixtures import fixture_snapshot

    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda manifest: True
    )
    manifest, contents = fixture_snapshot()
    sid = store.seal(manifest, contents)
    adapter = FrozenSSTCatalogueAdapter(
        store=store,
        access=SSTAccess("user-a", "revision-1", lambda snapshot, metadata: True),
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://forbidden/never")
    monkeypatch.setenv("MODEL_PROVIDER", "forbidden")
    with pytest.raises(SSTUnavailable):
        adapter.query(operation(sid))


def test_whole_population_requirement_rejects_a_previously_scoped_capture(tmp_path):
    store, sid, adapter, _ = local(tmp_path)
    manifest, contents = store.read(sid)
    manifest.scope = sst_scope(time_from="2024-02-27")
    subset = store.seal(manifest, contents)
    with pytest.raises(SSTUnavailable, match="whole-source"):
        adapter.query(operation(subset))


def test_explicit_local_c09_copy_preserves_sst_values_and_independent_access(tmp_path):
    from ingestion.catalogue_snapshot_transfer import build_transfer, import_quarantined

    source, sid, adapter, _ = local(tmp_path / "source")
    before = adapter.query(operation(sid, op="c11.summary")).result
    manifest, contents = source.read(sid)
    transfer = build_transfer(
        manifest,
        contents,
        destination_id="synthetic-c11-copy",
        authorization_ref="synthetic-local-c11-acceptance",
        origin_system="synthetic-source",
        qualifications={
            identity: (
                "Synthetic descriptive SST fixture",
                "Current destination eligibility required",
            )
            for identity in contents
        },
        encodings={identity: "opaque-bytes-v1" for identity in contents},
    )
    destination = LocalCatalogueSnapshotStore(
        root=(tmp_path / "destination").resolve(), access_gate=lambda snapshot: True
    )
    imported = import_quarantined(
        transfer,
        contents,
        destination_id="synthetic-c11-copy",
        store=destination,
        quarantine_root=(tmp_path / "quarantine").resolve(),
        authorize=lambda transfer: True,
        eligible=lambda obj, origin: True,
    )
    copied = FrozenSSTCatalogueAdapter(store=destination, access=adapter.access)
    assert imported.snapshot_id != sid and imported.latest_promoted is False
    source.revoke(sid)
    after = copied.query(operation(imported.snapshot_id, op="c11.summary")).result
    assert after.rows == before.rows
    assert after.receipt.content_sha256 == before.receipt.content_sha256
    assert (
        copied.inspect(FINAL, listing(imported.snapshot_id))["provenance"][0]["origin"][
            "live_dependency"
        ]
        is False
    )
    destination.revoke(imported.snapshot_id)
    with pytest.raises(SnapshotAccessDenied):
        copied.query(operation(imported.snapshot_id))


@pytest.mark.parametrize(
    "mutation", ["extra-filter", "bad-date", "wrong-enabled", "unknown-source"]
)
def test_malformed_scope_fails_before_any_frozen_computation(tmp_path, mutation):
    _, sid, adapter, _ = local(tmp_path)
    request = operation(sid).model_dump(mode="json")
    source = request["scope"]["sources"]["remote_sensing"]
    if mutation == "extra-filter":
        source["filters"]["raw_sql"] = "select forbidden"
    elif mutation == "bad-date":
        source["filters"]["time_from"] = "2024-13-20"
    elif mutation == "wrong-enabled":
        source["enabled"] = "true"
    else:
        request["scope"]["sources"]["future"] = {"enabled": True, "filters": {}}
    with pytest.raises(ValueError):
        adapter.query(request)


def test_corrupt_snapshot_fails_after_previous_success_instead_of_using_cache(tmp_path):
    store, sid, adapter, _ = local(tmp_path)
    adapter.query(operation(sid))
    manifest, _ = store.read(sid)
    target = next(obj for obj in manifest.objects if obj.role == "observations")
    path = tmp_path / "v1/catalogue/objects" / target.sha256
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integrity|bound|size"):
        adapter.query(operation(sid))


@pytest.mark.parametrize("mutation", ["table-dataset", "cross-product-collection"])
@pytest.mark.parametrize("entry", ["query", "list"])
@pytest.mark.parametrize("deny_second", [False, True])
def test_canonical_identity_collisions_fail_at_every_entry_before_policy_filtering(
    tmp_path, mutation, entry, deny_second
):
    first, first_frames = sst_fixture(1)
    second, second_frames = sst_fixture(1, dataset_id=INTERIM, generation="interim")
    if mutation == "table-dataset":
        first.table.object_id = second.dataset_id
    else:
        first.collection_id = second.collection_id

    def allowed(snapshot, metadata):
        return not deny_second or metadata.dataset_id != INTERIM

    _, sid, adapter, _ = local(
        tmp_path, [(first, first_frames), (second, second_frames)], allowed=allowed
    )
    with pytest.raises(ValueError, match="identities collide"):
        if entry == "query":
            adapter.query(operation(sid, op="c11.count"))
        else:
            adapter.list(listing(sid))


@pytest.mark.parametrize("budget", ["rows", "decoded"])
def test_adapter_applies_cumulative_snapshot_budgets_before_loading_datasets(
    tmp_path, monkeypatch, budget
):
    import orchestration.frozen_sst_catalogue as adapter_module

    store, sid, adapter, _ = local(
        tmp_path,
        [sst_fixture(1), sst_fixture(1, dataset_id=INTERIM, generation="interim")],
    )
    if budget == "rows":
        monkeypatch.setattr(adapter_module, "MAX_ROWS", 1)
    else:
        manifest, contents = store.read(sid)
        sizes = []
        for obj in manifest.objects:
            if obj.role == "observations":
                footer = pq.ParquetFile(BytesIO(contents[obj.object_id])).metadata
                sizes.append(
                    sum(
                        footer.row_group(i).total_byte_size
                        for i in range(footer.num_row_groups)
                    )
                )
        limit = max(sizes) + 1
        assert limit < sum(sizes)
        monkeypatch.setattr(adapter_module, "MAX_DECODED_BYTES", limit)

    def forbidden_load(*args):
        pytest.fail(
            "Snapshot preflight must reject the budget before scientific table decoding"
        )

    monkeypatch.setattr(adapter_module, "load_dataset", forbidden_load)
    with pytest.raises(ValueError, match="complete snapshot decode budget"):
        adapter.query(operation(sid))


def test_adapter_checks_cumulative_actual_arrow_bytes_after_footer_preflight(
    tmp_path, monkeypatch
):
    import orchestration.frozen_sst_catalogue as adapter_module

    datasets = [
        sst_fixture(100),
        sst_fixture(100, dataset_id=INTERIM, generation="interim"),
    ]
    store, sid, adapter, _ = local(tmp_path, datasets)
    manifest, contents = store.read(sid)
    actual, footer_bytes = [], []
    for metadata, _ in datasets:
        payload = contents[metadata.table.object_id]
        actual.append(parse_table(metadata.table, payload).attrs["decoded_bytes"])
        footer = pq.ParquetFile(BytesIO(payload)).metadata
        footer_bytes.append(
            sum(
                footer.row_group(i).total_byte_size
                for i in range(footer.num_row_groups)
            )
        )
    # Arrow string offsets/validity overhead can exceed Parquet's uncompressed
    # footer accounting even when plain values are used. Test the genuine sizes.
    limit = max(sum(footer_bytes), max(actual)) + 1
    assert limit < sum(actual)
    monkeypatch.setattr(adapter_module, "MAX_DECODED_BYTES", limit)
    with pytest.raises(ValueError, match="actual snapshot decode budget"):
        adapter.query(operation(sid))
