"""Adversarial input, copy and registration checks through actual C10 paths."""

import hashlib
import json
import time

import pytest

from ingestion import catalogue_adapter_inputs as inputs
from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.catalogue_snapshot_capture import CaptureHeads
from ingestion.catalogue_snapshot_transfer import build_transfer, import_quarantined
from ingestion.immutable_bundle import canonical_bytes
from orchestration import frozen_catalogue
from orchestration.frozen_catalogue import FrozenCatalogueAdapter
from schema.catalogue_adapter import FrozenDataset, FrozenTable
from schema.catalogue_adapter_fixtures import (
    adapter_scope,
    ctd_fixture,
    metagenome_fixture,
)
from schema.context_catalogue import OperationRequest
from tests.test_frozen_catalogue_adapters import CTD, META, listing, local, operation


def test_imported_independent_copy_has_parity_and_retains_original_origins(tmp_path):
    store, sid, original, _ = local(tmp_path / "source")
    manifest, contents = store.read(sid)
    transfer = build_transfer(
        manifest,
        contents,
        destination_id="synthetic-v1-copy",
        authorization_ref="synthetic-approval-only",
        origin_system="synthetic-origin",
        qualifications={
            key: ("Synthetic local fixture", "Current injected access")
            for key in contents
        },
        encodings={key: "opaque-bytes-v1" for key in contents},
    )
    destination = LocalCatalogueSnapshotStore(
        root=(tmp_path / "copy").resolve(), access_gate=lambda m: True
    )
    copied = import_quarantined(
        transfer,
        contents,
        destination_id="synthetic-v1-copy",
        store=destination,
        quarantine_root=(tmp_path / "quarantine").resolve(),
        authorize=lambda t: True,
        eligible=lambda o, p: True,
    )
    adapter = FrozenCatalogueAdapter(store=destination, access=original.access)
    for identity, table in [(CTD, "depth_observations"), (META, "kraken_abundance")]:
        before = original.query(operation(sid, identity, "c10.count", table=table))
        after = adapter.query(
            operation(copied.snapshot_id, identity, "c10.count", table=table)
        )
        assert before.result.rows == after.result.rows
        assert (
            before.result.receipt.content_sha256 == after.result.receipt.content_sha256
        )
        details = adapter.inspect(identity, listing(copied.snapshot_id))
        assert all(
            obj["origin"]["source_snapshot_id"] == sid for obj in details["provenance"]
        )
    assert destination.latest() == (None, 0)


@pytest.mark.parametrize(
    "mutation",
    [
        "metadata-extra",
        "metadata-identity",
        "metadata-role",
        "wrong-version",
        "wrong-operation",
        "wrong-role",
        "orphan",
    ],
)
def test_sealed_hash_valid_bytes_still_need_adapter_semantic_validation(
    tmp_path, mutation
):
    store, sid, adapter, _ = local(tmp_path, [ctd_fixture(2)])
    manifest, contents = store.read(sid)
    metadata = next(obj for obj in manifest.objects if obj.role == "dataset_metadata")
    table = next(obj for obj in manifest.objects if obj.role == "casts")
    if mutation in {"metadata-extra", "metadata-identity"}:
        payload = json.loads(contents[metadata.object_id])
        if mutation == "metadata-extra":
            payload["raw_sql"] = "forbidden"
        else:
            payload["dataset_id"] = "different-dataset"
        contents[metadata.object_id] = canonical_bytes(payload)
        metadata.sha256 = hashlib.sha256(contents[metadata.object_id]).hexdigest()
        metadata.size_bytes = len(contents[metadata.object_id])
        metadata.provenance.content_sha256 = metadata.sha256
    elif mutation == "metadata-role":
        metadata.role = "unrecognized_metadata"
    elif mutation == "wrong-version":
        table.operation_version = "unsupported-v2"
        manifest.operation_versions[table.operation_id] = table.operation_version
    elif mutation == "wrong-operation":
        table.operation_id = "unregistered:export"
        manifest.operation_versions[table.operation_id] = table.operation_version
    elif mutation == "wrong-role":
        table.role = "different_table"
    else:
        extra = table.model_copy(deep=True)
        extra.object_id = "synthetic:orphan"
        manifest.objects.append(extra)
        contents[extra.object_id] = contents[table.object_id]
    changed = store.seal(manifest, contents)
    with pytest.raises(ValueError):
        adapter.query(operation(changed, table="casts"))


@pytest.mark.parametrize(
    "field,value",
    [("row_count", None), ("completeness", "unavailable"), ("object_id", None)],
)
def test_available_table_cannot_claim_missing_count_or_object(field, value):
    metadata, _ = ctd_fixture(1)
    raw = metadata.tables[0].model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValueError):
        FrozenTable.model_validate(raw)


@pytest.mark.parametrize("field", ["dataset_id", "collection_id"])
def test_reserved_node_identities_are_rejected_before_registration(field):
    metadata, _ = ctd_fixture(1)
    raw = metadata.model_dump(mode="json")
    raw[field] = "root:data"
    with pytest.raises(ValueError):
        FrozenDataset.model_validate(raw)


def test_source_batch_registration_captures_every_dataset_and_detaches_mutable_inputs():
    datasets = [ctd_fixture(2, dataset_id=f"synthetic:ctd:batch-{i}") for i in range(3)]
    requirement = inputs.frozen_source_requirement(
        datasets, source_generation="source-generation-2"
    )
    datasets[0][1]["casts"].drop(index=0, inplace=True)
    value = requirement.exporter(
        None,
        CaptureHeads({"source:synthetic-ctd": "source-generation-2"}),
        time.monotonic() + 10,
    )
    assert len(value.objects) == 9
    assert len({obj.dataset_id for obj in value.objects}) == 3
    assert all(
        obj.provenance.source_generation == "source-generation-2"
        for obj in value.objects
    )
    assert set(value.contents) == {obj.object_id for obj in value.objects}


@pytest.mark.parametrize(
    "datasets",
    [[], [ctd_fixture(1), metagenome_fixture(1)], [ctd_fixture(1), ctd_fixture(1)]],
)
def test_ambiguous_source_registration_is_rejected(datasets):
    with pytest.raises(ValueError):
        inputs.frozen_source_requirement(
            datasets, source_generation="source-generation-2"
        )


@pytest.mark.parametrize("limit", ["row", "decoded"])
def test_complete_snapshot_decode_budgets_fail_without_silent_truncation(
    tmp_path, monkeypatch, limit
):
    _, sid, adapter, _ = local(tmp_path)
    monkeypatch.setattr(
        frozen_catalogue, "MAX_ROWS" if limit == "row" else "MAX_DECODED_BYTES", 1
    )
    with pytest.raises(ValueError, match="budget"):
        adapter.query(operation(sid, table="casts"))


def test_complete_and_incomplete_anchor_states_are_distinct(tmp_path):
    metadata, frames = ctd_fixture(2)
    metadata.tables[0].completeness = "partial"
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    assert adapter.dataset_count(listing(sid, families=("ctd",))).value == 1
    value = adapter.query(
        operation(sid, op="c10.count", table="depth_observations")
    ).result
    assert (
        value.receipt.availability.status == "unavailable"
        and value.receipt.total_rows.value is None
    )
    assert (
        adapter.open(CTD, listing(sid, families=("ctd",))).lifecycle.query_readiness
        == "not_ready"
    )


@pytest.mark.parametrize(
    "precision,date,start,end,expected",
    [
        ("year", "2024", "2024-01-01", "2024-12-31", 1),
        ("year", "2024", "2024-01-01", "2024-06-30", None),
        ("datetime", "2024-01-01T23:30:00-02:00", "2024-01-02", "2024-01-02", 1),
        ("datetime", "2024-01-01T23:30:00-02:00", "2024-01-01", "2024-01-01", 0),
        ("unknown", None, None, None, 1),
    ],
)
def test_retained_temporal_precision_and_offsets_are_not_fabricated(
    tmp_path, precision, date, start, end, expected
):
    metadata, frames = ctd_fixture(1)
    metadata.collection_date_precision = precision
    frames["casts"]["collection_date"] = date
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    value = adapter.query(
        operation(
            sid,
            op="c10.count",
            table="casts",
            scope=adapter_scope("ctd", time_from=start, time_to=end),
        )
    ).result
    if expected is None:
        assert value.receipt.total_rows.value is None
    else:
        assert value.rows[0]["count"] == expected
    if expected is not None and start is None:
        assert (
            adapter.query(operation(sid, table="casts")).result.rows[0][
                "collection_date"
            ]
            == date
        )


def test_denied_dataset_is_not_reachable_through_hidden_related_id_or_parent(tmp_path):
    a, frames = ctd_fixture(1)
    b, bframes = ctd_fixture(1, dataset_id="synthetic:ctd:secret")
    a.related_ids = [b.dataset_id]
    _, sid, adapter, policy = local(tmp_path, [(a, frames), (b, bframes)])
    policy["denied"].add(b.dataset_id)
    req = listing(sid, families=("ctd",))
    assert adapter.inspect(CTD, req)["related"] == []
    assert all("secret" not in node.id for node in adapter.list(req).items)
    assert (
        adapter.dataset_count(
            req.model_copy(update={"parent_id": a.collection_id})
        ).value
        == 1
    )


def test_inventory_cursor_binds_snapshot_scope_page_size_and_current_access(tmp_path):
    _, sid, adapter, _ = local(tmp_path)
    req = listing(sid, limit=1)
    cursor = adapter.list(req).next_cursor
    for changes in [
        {"limit": 2},
        {"access_revision": "next"},
        {"scope": adapter_scope("ctd")},
    ]:
        changed = req.model_copy(update={"cursor": cursor, **changes})
        with pytest.raises(ValueError):
            adapter.list(changed)


@pytest.mark.parametrize(
    "operation_id,parameters",
    [
        ("c10.summary", {"table": "casts"}),
        ("c10.coverage", {"table": "run_qc"}),
        ("c10.count", {"table": "casts", "offset": 1}),
        ("c10.table", {"table": "casts", "offset": 999}),
        ("unrestricted.sql", {"table": "casts"}),
    ],
)
def test_operations_do_not_execute_unsupported_or_misbound_parameters(
    tmp_path, operation_id, parameters
):
    _, sid, adapter, _ = local(tmp_path)
    req = OperationRequest(
        snapshot_id=sid,
        scope=adapter_scope("ctd"),
        operation_id=operation_id,
        operation_version="c10-v1",
        input_ids=[CTD],
        parameters=parameters,
        access_binding="user-a",
        access_revision="revision-1",
    )
    with pytest.raises(ValueError):
        adapter.query(req)


def test_frozen_registration_never_relabels_old_bytes_under_new_heads():
    metadata, frames = ctd_fixture(2)
    registration = inputs.frozen_export_requirement(
        metadata, frames, source_generation="frozen-g1"
    )
    assert registration.exporter(
        None, CaptureHeads({"source:synthetic-ctd": "frozen-g1"}), time.monotonic() + 10
    )
    with pytest.raises(inputs.AdapterUnavailable, match="generation|Generation"):
        registration.exporter(
            None,
            CaptureHeads({"source:synthetic-ctd": "newer-g2"}),
            time.monotonic() + 10,
        )


def test_signed_depth_convention_preserves_source_negative_depth(tmp_path):
    metadata, frames = ctd_fixture(1)
    metadata.depth_convention = "signed_source"
    frames["depth_observations"].loc[0, "depth"] = -0.25
    _, snapshot, adapter, _ = local(tmp_path, [(metadata, frames)])
    value = adapter.query(operation(snapshot, table="depth_observations"))
    assert value.result.rows[0]["depth"] == -0.25
    assert next(c for c in value.result.columns if c.key == "depth").unit == "m"


def test_mixed_collection_precision_is_retained_per_record(tmp_path):
    from schema.catalogue_adapter import FrozenColumn

    metadata, frames = metagenome_fixture(2)
    metadata.collection_date_precision = "mixed"
    frames["collections"]["collection_date"] = ["2024-01", "2024-02-10"]
    frames["collections"]["date_precision"] = ["month", "day"]
    metadata.tables[0].columns.append(
        FrozenColumn(
            name="date_precision",
            dtype="string",
            nullable=False,
            description="Retained source precision",
        )
    )
    _, snapshot, adapter, _ = local(tmp_path, [(metadata, frames)])
    value = adapter.query(operation(snapshot, META, "c10.coverage"))
    assert [
        (row["collection_period"], row["precision"]) for row in value.result.rows
    ] == [("2024-01", "month"), ("2024-02-10", "day")]
    request = operation(
        snapshot,
        META,
        "c10.count",
        table="collections",
        scope=adapter_scope("metagenome", time_from="2024-02-10", time_to="2024-02-10"),
    )
    assert adapter.query(request).result.rows[0]["count"] == 1


def test_mixed_collection_precision_requires_source_owned_per_record_metadata():
    metadata, frames = metagenome_fixture(1)
    metadata.collection_date_precision = "mixed"
    with pytest.raises(ValueError, match="precision"):
        inputs.dataset_exports(metadata, frames, generation="g1")


def test_dictionary_encoded_parquet_is_rejected_before_value_expansion():
    from io import BytesIO
    import pyarrow.parquet as pq

    metadata, frames = ctd_fixture(3)
    captured = inputs.dataset_exports(metadata, frames, generation="g1")
    spec = metadata.tables[0]
    table = pq.read_table(BytesIO(captured.contents[spec.object_id]))
    stream = BytesIO()
    pq.write_table(table, stream, use_dictionary=True)
    with pytest.raises(ValueError, match="encoding"):
        inputs.parse_table(spec, stream.getvalue())


def test_scoped_capture_cannot_be_mistaken_for_complete_source_inventory(tmp_path):
    store, sid, adapter, _ = local(tmp_path, [ctd_fixture(2)])
    manifest, contents = store.read(sid)
    manifest.scope.sources.ctd.filters.station = "station-1"
    changed = store.seal(manifest, contents)
    with pytest.raises(inputs.AdapterUnavailable, match="whole-source"):
        adapter.dataset_count(listing(changed, families=("ctd",)))


def test_valid_frozen_queries_do_not_require_models_or_live_data_paths(
    tmp_path, monkeypatch
):
    import config
    from db import connection

    def forbidden(*args, **kwargs):
        raise AssertionError("Live database access is outside the frozen adapter")

    _, snapshot, adapter, _ = local(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://forbidden/never")
    monkeypatch.setenv("MODEL_PROVIDER", "not-a-provider")
    monkeypatch.setattr(config, "NORMALIZED_DIR", tmp_path / "absent-normalized")
    monkeypatch.setattr(config, "SERVING_DIR", tmp_path / "absent-serving")
    monkeypatch.setattr(connection, "get_engine", forbidden)
    assert (
        adapter.query(operation(snapshot, op="c10.count", table="casts")).result.rows[
            0
        ]["count"]
        == 4
    )
    assert not config.NORMALIZED_DIR.exists() and not config.SERVING_DIR.exists()


def test_missing_normalized_abundance_stays_visible_and_cannot_use_ranked_rows(
    tmp_path,
):
    metadata, frames = metagenome_fixture(2)
    for spec in metadata.tables:
        if spec.name.endswith("abundance"):
            spec.object_id = None
            spec.row_count = None
            spec.completeness = "unavailable"
            spec.availability.status = "unavailable"
            spec.availability.reason = "Complete normalized source inputs not supplied"
            del frames[spec.name]
    _, snapshot, adapter, _ = local(tmp_path, [(metadata, frames)])
    details = adapter.inspect(META, listing(snapshot, families=("metagenome",)))
    assert len(details["tables"]) == 5
    value = adapter.query(
        operation(
            snapshot, META, "c10.summary", table="kraken_abundance", column="abundance"
        )
    )
    assert (
        value.result.receipt.availability.status == "unavailable"
        and value.result.rows == []
    )
    assert value.result.receipt.total_rows.value is None
    assert adapter.query(operation(snapshot, META, table="ranked_taxa")).result.rows


def test_omitting_a_source_role_requires_explicit_unavailable_descriptor():
    metadata, _ = metagenome_fixture(1)
    value = metadata.model_dump(mode="json")
    value["tables"] = value["tables"][:-1]
    with pytest.raises(ValueError, match="roles"):
        FrozenDataset.model_validate(value)


def test_enabled_scope_flag_without_captured_source_is_not_an_empty_population(
    tmp_path,
):
    store, snapshot, adapter, _ = local(tmp_path, [ctd_fixture(2)])
    manifest, contents = store.read(snapshot)
    manifest.scope.sources.metagenome.enabled = True
    changed = store.seal(manifest, contents)
    with pytest.raises(inputs.AdapterUnavailable, match="absent"):
        adapter.dataset_count(listing(changed))
