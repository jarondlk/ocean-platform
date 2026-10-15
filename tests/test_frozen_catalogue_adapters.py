"""C10 real adapter paths versus independent frozen scientific expectations."""

import hashlib
from io import BytesIO
import time

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ingestion.catalogue_adapter_inputs import (
    AdapterUnavailable,
    dataset_exports,
    frozen_export_requirement,
    parse_table,
)
from ingestion.catalogue_snapshot import (
    LocalCatalogueSnapshotStore,
    SnapshotAccessDenied,
)
from ingestion.catalogue_snapshot_capture import CaptureHeads
from orchestration.frozen_catalogue import (
    AdapterAccess,
    AdapterAccessDenied,
    FrozenCatalogueAdapter,
)
from schema.catalogue_adapter import ADAPTER_VERSION
from schema.catalogue_adapter_fixtures import (
    adapter_scope,
    ctd_fixture,
    metagenome_fixture,
    seal_fixture,
)
from schema.context_catalogue import CatalogueFilters, ListingRequest, OperationRequest
from schema.catalogue_snapshot import manifest_id

CTD = "synthetic:ctd:campaign-a"
META = "synthetic:metagenome:collection-a"


def listing(snapshot, *, families=("ctd", "metagenome"), **changes):
    return ListingRequest.model_validate(
        {
            "snapshot_id": snapshot,
            "scope": adapter_scope(*families).model_dump(mode="json"),
            "access_binding": "user-a",
            "access_revision": "revision-1",
            **changes,
        }
    )


def operation(snapshot, identity=CTD, op="c10.table", *, scope=None, **params):
    return OperationRequest(
        snapshot_id=snapshot,
        scope=scope or adapter_scope("ctd" if identity == CTD else "metagenome"),
        operation_id=op,
        operation_version=ADAPTER_VERSION,
        input_ids=[identity],
        parameters=params,
        access_binding="user-a",
        access_revision="revision-1",
    )


def local(tmp_path, datasets=None, *, allowed=None):
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda m: True
    )
    sid = seal_fixture(store, datasets or [ctd_fixture(4), metagenome_fixture(4)])
    policy = {"denied": set(), "eligible": True}

    def eligible(snapshot, metadata):
        return policy["eligible"] and metadata.dataset_id not in policy["denied"]

    adapter = FrozenCatalogueAdapter(
        store=store, access=AdapterAccess("user-a", "revision-1", allowed or eligible)
    )
    return store, sid, adapter, policy


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    return local(
        tmp_path_factory.mktemp("c10-large"),
        [ctd_fixture(1205), metagenome_fixture(601)],
    )


def test_ctd_counts_casts_and_depth_observations_over_complete_scope(large):
    _, sid, adapter, _ = large
    casts = adapter.query(operation(sid, op="c10.count", table="casts")).result
    depths = adapter.query(
        operation(sid, op="c10.count", table="depth_observations")
    ).result
    assert casts.rows[0]["count"] == 1205
    assert casts.rows[0]["entity"] == "casts"
    assert depths.rows[0]["count"] == 2410
    assert depths.rows[0]["entity"] == "depth_observations"
    assert casts.receipt.authority == "descriptive"
    assert casts.receipt.operation_version == "c10-v1"


@pytest.mark.parametrize("limit", [1, 25, 100, 500])
def test_preview_size_preserves_complete_counts_and_content_identity(large, limit):
    _, sid, adapter, _ = large
    value = adapter.query(operation(sid, table="depth_observations", limit=limit))
    expected = adapter.query(operation(sid, table="depth_observations", limit=500))
    assert len(value.result.rows) == limit
    assert value.result.receipt.total_rows.value == 2410
    assert value.result.receipt.content_sha256 == expected.result.receipt.content_sha256
    assert value.next_offset == limit
    assert value.result.receipt.preview_truncated


def test_all_pages_reach_every_depth_row_once(large):
    _, sid, adapter, _ = large
    identities, offset = [], 0
    while True:
        result = adapter.query(
            operation(sid, table="depth_observations", offset=offset, limit=500)
        )
        identities.extend(row["observation_id"] for row in result.result.rows)
        if result.next_offset is None:
            assert (
                result.result.receipt.preview_truncated
            )  # preceding rows remain omitted from this page
            break
        offset = result.next_offset
    assert len(identities) == len(set(identities)) == 2410
    assert identities == [f"obs-{i:06d}-{j}" for i in range(1205) for j in range(2)]


def test_ctd_summary_uses_every_scoped_depth_with_correct_units(large):
    _, sid, adapter, _ = large
    scope = adapter_scope("ctd", station="station-1")
    result = adapter.query(
        operation(
            sid,
            op="c10.summary",
            table="depth_observations",
            column="temperature",
            scope=scope,
            limit=1,
        )
    ).result
    expected = [
        -1.5 if i == j == 0 else float(i + j)
        for i in range(0, 1205, 2)
        for j in range(2)
    ]
    assert result.rows == [
        {
            "measurement": "temperature",
            "n_observed": 1206,
            "n_missing": 0,
            "n_zero": 0,
            "minimum": min(expected),
            "maximum": max(expected),
            "mean": sum(expected) / len(expected),
        }
    ]
    assert next(c for c in result.columns if c.key == "mean").unit == "degC"
    assert result.scope == scope
    assert result.receipt.total_rows.value == 1


@pytest.mark.parametrize(
    "table,mean", [("kraken_abundance", 0.05), ("metaeuk_abundance", 0.15)]
)
def test_taxon_omitted_from_ranked_summary_keeps_full_method_abundance(
    large, table, mean
):
    _, sid, adapter, _ = large
    result = adapter.query(
        operation(
            sid,
            META,
            "c10.summary",
            table=table,
            taxon="BeyondTopTen",
            column="abundance",
        )
    ).result
    assert result.rows[0]["n_observed"] == 601
    assert result.rows[0]["n_zero"] == 0
    assert result.rows[0]["mean"] == pytest.approx(mean)
    assert result.rows[0]["minimum"] == mean
    assert (
        adapter.query(
            operation(sid, META, "c10.count", table=table, taxon="BeyondTopTen")
        ).result.rows[0]["count"]
        == 601
    )


@pytest.mark.parametrize(
    "taxon,observed,missing,zeros",
    [
        ("MeasuredZero", 601, 0, 601),
        ("MissingCell", 0, 601, 0),
        ("NeverMeasured", 0, 0, 0),
    ],
)
def test_zero_missing_and_absent_taxon_never_conflate(
    large, taxon, observed, missing, zeros
):
    _, sid, adapter, _ = large
    result = adapter.query(
        operation(
            sid,
            META,
            "c10.summary",
            table="kraken_abundance",
            column="abundance",
            taxon=taxon,
        )
    ).result
    row = result.rows[0]
    assert (row["n_observed"], row["n_missing"], row["n_zero"]) == (
        observed,
        missing,
        zeros,
    )
    assert row["mean"] == (0.0 if observed else None)


def test_ranked_preview_is_partial_and_cannot_supply_exact_aggregate(large):
    _, sid, adapter, _ = large
    preview = adapter.query(
        operation(sid, META, table="ranked_taxa", taxon="BeyondTopTen")
    )
    assert preview.result.rows == []
    assert preview.result.receipt.total_rows.state == "unknown"
    assert preview.result.receipt.query_completion == "partial"
    for op in ["c10.count", "c10.summary"]:
        params = {"column": "abundance"} if op.endswith("summary") else {}
        value = adapter.query(operation(sid, META, op, table="ranked_taxa", **params))
        assert value.result.rows == []
        assert value.result.receipt.availability.status == "unavailable"
        assert value.result.receipt.total_rows.value is None


def test_coverage_uses_collection_month_not_run_date_or_synthetic_days(large):
    _, sid, adapter, _ = large
    coverage = adapter.query(operation(sid, META, "c10.coverage")).result
    assert coverage.rows == [
        {
            "collection_period": "2024-01",
            "precision": "month",
            "count": 301,
            "entity": "libraries",
        },
        {
            "collection_period": "2024-02",
            "precision": "month",
            "count": 300,
            "entity": "libraries",
        },
    ]
    runs = adapter.query(operation(sid, META, table="run_qc", limit=1))
    assert runs.result.rows[0]["run_date"] == "2025-07-01"
    assert runs.result.rows[0]["sequencing_method"] == "synthetic-long-read"
    assert next(c for c in runs.result.columns if c.key == "reads").unit == "reads"
    assert not any("expected" in column.key for column in coverage.columns)


@pytest.mark.parametrize(
    "start,end,count",
    [
        ("2024-01-01", "2024-01-31", 301),
        ("2024-02-01", "2024-02-29", 300),
        ("2026-01-01", "2026-01-31", 0),
    ],
)
def test_month_scope_matches_only_supported_complete_collection_periods(
    large, start, end, count
):
    _, sid, adapter, _ = large
    scope = adapter_scope("metagenome", time_from=start, time_to=end)
    value = adapter.query(
        operation(sid, META, "c10.count", table="collections", scope=scope)
    )
    assert value.result.rows[0]["count"] == count


def test_partial_month_filter_is_unavailable_instead_of_fabricating_a_day(large):
    _, sid, adapter, _ = large
    scope = adapter_scope("metagenome", time_from="2024-01-15", time_to="2024-01-20")
    result = adapter.query(
        operation(sid, META, "c10.count", table="collections", scope=scope)
    ).result
    assert (
        result.receipt.availability.status == "unavailable"
        and result.receipt.total_rows.value is None
    )
    assert result.rows == []


def test_ctd_day_scope_matches_existing_shared_interval_semantics(large):
    _, sid, adapter, _ = large
    scope = adapter_scope(
        "ctd", time_from="2024-01-01T12:00:00Z", time_to="2024-01-01T18:00:00Z"
    )
    result = adapter.query(operation(sid, op="c10.count", table="casts", scope=scope))
    assert result.result.rows[0]["count"] == 603


def test_all_six_sections_and_source_identities_do_not_unify_shared_labels(large):
    _, sid, adapter, _ = large
    req = listing(sid)
    ctd = adapter.inspect(CTD, req)
    meta = adapter.inspect(META, req)
    assert set(ctd) == {
        "node",
        "overview",
        "tables",
        "coverage",
        "methods",
        "provenance",
        "related",
    }
    assert ctd["node"].sections == [
        "overview",
        "tables",
        "coverage",
        "methods",
        "provenance",
        "related",
    ]
    assert ctd["node"].id != meta["node"].id
    assert ctd["node"].lifecycle.embedding_readiness == "unknown"
    assert ctd["node"].lifecycle.scientific_approval == "not_reviewed"
    assert adapter.dataset_count(req).value == 2
    assert (
        next(
            op for op in meta["node"].operations if op.id == "c10.contigs"
        ).availability.status
        == "unavailable"
    )
    for identity, table in [(CTD, "casts"), (META, "collections")]:
        result = adapter.query(
            operation(
                sid,
                identity,
                "c10.count",
                table=table,
                scope=adapter_scope(
                    "ctd" if identity == CTD else "metagenome", sample_id="shared-label"
                ),
            )
        )
        assert result.result.rows[0]["count"] == 1


def test_inventory_reaches_late_rank_and_crosslinks_do_not_add_membership(tmp_path):
    datasets = []
    for i in range(32):
        data, frames = ctd_fixture(1, dataset_id=f"synthetic:ctd:dataset-{i:03d}")
        data.related_ids = [f"synthetic:ctd:dataset-{(i + 1) % 32:03d}"]
        datasets.append((data, frames))
    _, sid, adapter, policy = local(tmp_path, datasets)
    req = listing(
        sid, families=("ctd",), filters=CatalogueFilters(kinds=["dataset"]), limit=25
    )
    first = adapter.list(req)
    second = adapter.list(req.model_copy(update={"cursor": first.next_cursor}))
    assert first.total.value == second.total.value == 32
    assert len(first.items) == 25 and len(second.items) == 7
    assert second.items[-1].id == "synthetic:ctd:dataset-031"
    assert adapter.dataset_count(req).value == 32
    policy["denied"].add("synthetic:ctd:dataset-031")
    assert adapter.dataset_count(req).value == 31
    node = adapter.open("synthetic:ctd:dataset-030", req)
    assert node.related_ids == []


def test_reopen_old_snapshot_after_update_has_original_results_and_receipt_inputs(
    tmp_path,
):
    store, sid, adapter, _ = local(tmp_path)
    before = adapter.query(
        operation(
            sid, op="c10.summary", table="depth_observations", column="temperature"
        )
    )
    dataset, frames = ctd_fixture(4)
    frames["depth_observations"]["temperature"] = 100.0
    new = seal_fixture(
        store,
        [(dataset, frames), metagenome_fixture(4)],
        generation="synthetic-generation-2",
    )
    reopened = FrozenCatalogueAdapter(
        store=LocalCatalogueSnapshotStore(
            root=tmp_path.resolve(), access_gate=lambda m: True
        ),
        access=adapter.access,
    )
    assert (
        reopened.query(
            operation(
                sid, op="c10.summary", table="depth_observations", column="temperature"
            )
        )
        == before
    )
    assert (
        reopened.query(
            operation(
                new, op="c10.summary", table="depth_observations", column="temperature"
            )
        ).result.rows[0]["mean"]
        == 100
    )
    manifest, contents = store.read(sid)
    assert manifest_id(manifest) == sid
    assert all(
        hashlib.sha256(contents[item.object_id]).hexdigest() == item.content_sha256
        for item in before.result.receipt.inputs
    )
    assert store.latest() == (None, 0)


@pytest.mark.parametrize("action", ["store-revoke", "current-gate", "dataset-policy"])
def test_current_access_overrides_cached_historical_results(tmp_path, action):
    store, sid, adapter, policy = local(tmp_path)
    assert adapter.query(operation(sid, table="casts")).result.rows
    if action == "store-revoke":
        store.revoke(sid)
    elif action == "current-gate":
        store.access_gate = lambda m: False
    else:
        policy["denied"].add(CTD)
    error = AdapterAccessDenied if action == "dataset-policy" else SnapshotAccessDenied
    with pytest.raises(error):
        adapter.query(operation(sid, table="casts"))
    if action == "dataset-policy":
        assert adapter.dataset_count(listing(sid)).value == 1
        with pytest.raises(AdapterAccessDenied):
            adapter.inspect(CTD, listing(sid))


def test_policy_callback_cannot_mutate_frozen_semantics_and_truthy_is_denied(tmp_path):
    def mutate(snapshot, metadata):
        metadata.tables.clear()
        return True

    _, sid, adapter, _ = local(tmp_path, allowed=mutate)
    assert (
        adapter.query(operation(sid, table="casts")).result.receipt.total_rows.value
        == 4
    )
    adapter.access = AdapterAccess("user-a", "revision-1", lambda sid, d: 1)
    assert adapter.dataset_count(listing(sid)).value == 0


@pytest.mark.parametrize(
    "field,value", [("access_binding", "other-user"), ("access_revision", "revision-2")]
)
def test_stale_or_different_current_access_context_is_denied(tmp_path, field, value):
    _, sid, adapter, _ = local(tmp_path)
    req = operation(sid, table="casts").model_copy(update={field: value})
    with pytest.raises(AdapterAccessDenied):
        adapter.query(req)


@pytest.mark.parametrize(
    "changes",
    [
        {"unexpected": True},
        {"limit": 0},
        {"limit": 501},
        {"offset": -1},
        {"limit": "5"},
        {"offset": True},
        {"table": "contigs"},
        {"column": "temperature"},
        {"taxon": "Missing"},
    ],
)
def test_invalid_table_query_parameters_fail_explicitly(tmp_path, changes):
    _, sid, adapter, _ = local(tmp_path)
    params = {"table": "casts", **changes}
    with pytest.raises(ValueError):
        adapter.query(operation(sid, **params))


@pytest.mark.parametrize(
    "mutation",
    ["extra-filter", "bad-bay", "bad-date", "wrong-enabled", "unknown-source"],
)
def test_malformed_scope_fails_before_frozen_query(tmp_path, mutation):
    _, sid, adapter, _ = local(tmp_path)
    req = operation(sid, table="casts").model_dump(mode="json")
    source = req["scope"]["sources"]["ctd"]
    if mutation == "extra-filter":
        source["filters"]["raw_sql"] = "SELECT anything"
    elif mutation == "bad-bay":
        source["filters"]["bay"] = "invented"
    elif mutation == "bad-date":
        source["filters"]["time_from"] = "2024-13-20"
    elif mutation == "wrong-enabled":
        source["enabled"] = "true"
    else:
        req["scope"]["sources"]["future"] = {"enabled": True, "filters": {}}
    with pytest.raises(ValueError):
        adapter.query(req)


def test_missing_source_and_disabled_source_are_not_known_empty(tmp_path):
    _, sid, adapter, _ = local(tmp_path, [ctd_fixture(2)])
    with pytest.raises(AdapterUnavailable):
        adapter.list(listing(sid))
    result = adapter.query(operation(sid, scope=adapter_scope(), table="casts")).result
    assert (
        result.receipt.availability.status == "unavailable"
        and result.receipt.total_rows.value is None
    )


def test_missing_table_is_visible_and_unavailable_and_empty_table_is_known_zero(
    tmp_path,
):
    metadata, frames = ctd_fixture(0)
    table = metadata.tables[1]
    table.object_id = None
    table.row_count = None
    table.completeness = "unavailable"
    table.availability.status = "unavailable"
    table.availability.reason = "Depth inputs not supplied"
    del frames["depth_observations"]
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    result = adapter.query(operation(sid, table="depth_observations")).result
    assert (
        result.receipt.availability.status == "unavailable"
        and result.receipt.total_rows.value is None
    )
    assert (
        adapter.query(operation(sid, op="c10.count", table="casts")).result.rows[0][
            "count"
        ]
        == 0
    )
    node = adapter.open(
        f"{CTD}:unavailable:depth_observations", listing(sid, families=("ctd",))
    )
    assert (
        node.availability.status == "unavailable"
        and node.lifecycle.query_readiness == "not_ready"
    )


def test_undated_collection_is_retained_but_temporal_count_is_unavailable(tmp_path):
    metadata, frames = metagenome_fixture(2)
    frames["collections"].loc[0, "collection_date"] = None
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    coverage = adapter.query(operation(sid, META, "c10.coverage")).result
    assert (
        coverage.rows[-1]["collection_period"] is None
        and coverage.rows[-1]["count"] == 1
    )
    scoped = adapter.query(
        operation(
            sid,
            META,
            "c10.count",
            table="collections",
            scope=adapter_scope("metagenome", time_from="2024-01-01"),
        )
    ).result
    assert scoped.receipt.total_rows.value is None


def test_no_legacy_c09_fixture_or_live_config_fallback(tmp_path, monkeypatch):
    from ingestion.catalogue_snapshot_fixtures import fixture_snapshot

    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda m: True
    )
    manifest, contents = fixture_snapshot()
    sid = store.seal(manifest, contents)
    adapter = FrozenCatalogueAdapter(
        store=store, access=AdapterAccess("user-a", "revision-1", lambda sid, d: True)
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://forbidden/never")
    monkeypatch.setenv("MODEL_PROVIDER", "forbidden")
    with pytest.raises(AdapterUnavailable):
        adapter.query(operation(sid, table="casts"))


def test_corrupted_snapshot_bytes_fail_instead_of_serving_previous_preview(tmp_path):
    store, sid, adapter, _ = local(tmp_path)
    adapter.query(operation(sid, table="casts"))
    manifest, _ = store.read(sid)
    target = next(obj for obj in manifest.objects if obj.role == "casts")
    path = tmp_path / "v1/catalogue/objects" / target.sha256
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity|bound|size"):
        adapter.query(operation(sid, table="casts"))


@pytest.mark.parametrize(
    "change",
    [
        "duplicate-anchor",
        "orphan",
        "negative-depth",
        "wrong-unit",
        "duplicate-cell",
        "incomplete-grid",
        "mixed-method",
        "coverage-contradiction",
        "infinite",
        "unsafe-integer",
        "wrong-month",
    ],
)
def test_frozen_source_validation_rejects_ambiguous_or_unsafe_inputs(change):
    metadata, frames = (
        ctd_fixture(2)
        if change
        in {
            "duplicate-anchor",
            "orphan",
            "negative-depth",
            "wrong-unit",
            "infinite",
            "unsafe-integer",
        }
        else metagenome_fixture(2)
    )
    if change == "duplicate-anchor":
        frames["casts"].loc[1, "cast_id"] = frames["casts"].loc[0, "cast_id"]
    elif change == "orphan":
        frames["depth_observations"].loc[0, "cast_id"] = "missing-cast"
    elif change == "negative-depth":
        frames["depth_observations"].loc[0, "depth"] = -1
    elif change == "wrong-unit":
        metadata.tables[1].columns[2].unit = "dbar"
    elif change == "duplicate-cell":
        frames["kraken_abundance"].loc[1, "taxon"] = frames["kraken_abundance"].loc[
            0, "taxon"
        ]
    elif change == "incomplete-grid":
        frames["kraken_abundance"] = frames["kraken_abundance"].iloc[1:]
        next(t for t in metadata.tables if t.name == "kraken_abundance").row_count -= 1
    elif change == "mixed-method":
        frames["kraken_abundance"].loc[0, "method"] = "MetaEuk"
    elif change == "coverage-contradiction":
        frames["collections"].loc[0, "has_kraken"] = False
    elif change == "infinite":
        frames["depth_observations"].loc[0, "temperature"] = float("inf")
    elif change == "unsafe-integer":
        frames["depth_observations"].loc[0, "temperature"] = float(2**54)
    elif change == "wrong-month":
        frames["collections"].loc[0, "collection_date"] = "2024-01-01"
    with pytest.raises(ValueError):
        dataset_exports(metadata, frames, generation="g1")


def test_registered_exports_are_frozen_and_use_supplied_source_generation():
    metadata, frames = ctd_fixture(3)
    requirement = frozen_export_requirement(metadata, frames, source_generation="g2")
    frames["casts"].drop(frames["casts"].index, inplace=True)
    metadata.title.en = "changed"
    value = requirement.exporter(
        None, CaptureHeads({"source:synthetic-ctd": "g2"}), time.monotonic() + 10
    )
    assert all(obj.provenance.source_generation == "g2" for obj in value.objects)
    assert all(obj.operation_version == "c10-v1" for obj in value.objects)
    source = next(obj for obj in value.objects if obj.role == "casts")
    spec = next(t for t in ctd_fixture(3)[0].tables if t.name == "casts")
    assert len(parse_table(spec, value.contents[source.object_id])) == 3
    with pytest.raises(AdapterUnavailable):
        requirement.exporter(
            None, CaptureHeads({"source:synthetic-ctd": "g2"}), time.monotonic() - 1
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "row-count",
        "column-order",
        "column-type",
        "duplicate-key",
        "null-key",
        "malformed",
    ],
)
def test_actual_parquet_bytes_are_validated_against_declared_schema(mutation):
    metadata, frames = ctd_fixture(2)
    captured = dataset_exports(metadata, frames, generation="g1")
    spec = metadata.tables[0].model_copy(deep=True)
    payload = captured.contents[spec.object_id]
    if mutation == "row-count":
        spec.row_count = 999
    elif mutation == "column-order":
        spec.columns = list(reversed(spec.columns))
    elif mutation == "column-type":
        spec.columns[0].dtype = "boolean"
    elif mutation in {"duplicate-key", "null-key"}:
        table = pq.read_table(BytesIO(payload))
        values = table.column("cast_id").to_pylist()
        values[1] = values[0] if mutation == "duplicate-key" else None
        table = table.set_column(0, "cast_id", pa.array(values, type=pa.string()))
        out = BytesIO()
        pq.write_table(table, out, use_dictionary=False)
        payload = out.getvalue()
    else:
        payload = b"not-parquet"
    with pytest.raises(ValueError):
        parse_table(spec, payload)


def test_unknown_units_or_denominators_block_scientific_summary(tmp_path):
    metadata, frames = metagenome_fixture(2)
    next(
        t for t in metadata.tables if t.name == "kraken_abundance"
    ).abundance_denominator = "unknown"
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    value = adapter.query(
        operation(
            sid, META, "c10.summary", table="kraken_abundance", column="abundance"
        )
    ).result
    assert value.receipt.availability.status == "unavailable" and value.rows == []
