"""C11 adversarial frozen input/ownership/registration acceptance."""

import hashlib
from io import BytesIO
import json
import time

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ingestion import sst_catalogue_inputs as inputs
from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.catalogue_snapshot_capture import CaptureHeads
from ingestion.immutable_bundle import canonical_bytes
from schema.sst_catalogue_fixtures import seal_sst_fixture, sst_fixture


def frozen(tmp_path, fixture=None):
    metadata, frames = fixture or sst_fixture(5)
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda m: True
    )
    identity = seal_sst_fixture(store, [(metadata, frames)])
    manifest, contents = store.read(identity)
    obj = next(item for item in manifest.objects if item.role == "dataset_metadata")
    return manifest, dict(contents), obj


def parquet(records, *, schema=inputs.ARROW_SCHEMA, dictionary=False):
    stream = BytesIO()
    pq.write_table(
        pa.Table.from_pylist(records, schema=schema), stream, use_dictionary=dictionary
    )
    return stream.getvalue()


def records_for(metadata, frames):
    exported = inputs.dataset_exports(metadata, frames, generation="generation-1")
    return pq.read_table(
        BytesIO(exported.contents[metadata.table.object_id])
    ).to_pylist()


@pytest.mark.parametrize("calendar", ["UTC", "Asia/Tokyo"])
@pytest.mark.parametrize("precision", ["day", "datetime"])
@pytest.mark.parametrize("entity", ["regional_daily_summary", "grid_observation"])
def test_frozen_roundtrip_retains_source_values_hashes_precision_and_calendar(
    tmp_path, calendar, precision, entity
):
    metadata, frames = sst_fixture(
        5, calendar=calendar, precision=precision, entity=entity
    )
    manifest, contents, obj = frozen(tmp_path, (metadata, frames))
    value = inputs.load_dataset(manifest, contents, obj)
    rows = value.tables["observations"].to_dict("records")
    assert value.metadata.model_dump(mode="json") == metadata.model_dump(mode="json")
    assert rows[0]["value"] == 0.0
    assert rows[1]["value"] is None
    assert rows[1]["quality_flag"] is None
    assert rows[0]["valid_fraction"] == 0.9
    assert rows[0]["valid_ocean_pixels"] == 90
    assert type(rows[0]["valid_ocean_pixels"]) is int
    assert rows[0]["ocean_pixels"] == 100
    assert rows[1]["valid_fraction"] is None
    assert rows[1]["valid_ocean_pixels"] is None
    assert rows[1]["ocean_pixels"] is None
    assert rows[2]["status"] == "invalid"
    assert rows[3]["status"] == "excluded"
    assert [row["time"] for row in rows] == frames["observations"].time.tolist()
    assert value.tables["observations"].attrs["decoded_bytes"] > 0
    assert {item.object_id for item in value.objects} == set(contents)


@pytest.mark.parametrize("status", ["unknown", "unavailable"])
def test_unknown_or_unavailable_observations_retain_unknown_count(tmp_path, status):
    metadata, _ = sst_fixture(0)
    metadata.table.object_id = None
    metadata.table.row_count = None
    metadata.table.availability.status = status
    metadata.table.availability.reason = "Synthetic missing input"
    metadata.table.completeness = status
    manifest, contents, obj = frozen(tmp_path, (metadata, {}))
    value = inputs.load_dataset(manifest, contents, obj)
    assert value.tables == {}
    assert len(value.objects) == 1
    assert value.metadata.table.row_count is None


@pytest.mark.parametrize(
    "payload",
    [
        b'{"dataset_id":"a","dataset_id":"b"}',
        b'{"x": NaN}',
        b'{"x": Infinity}',
        b"[]",
        b"{}",
        b"\xff",
    ],
)
def test_metadata_rejects_duplicate_nonfinite_or_invalid_json(payload):
    with pytest.raises(ValueError):
        inputs.dataset_metadata(payload)


def test_metadata_is_bounded_and_forbids_undeclared_fields(monkeypatch):
    metadata, _ = sst_fixture(1)
    raw = metadata.model_dump(mode="json")
    raw["scientific_approval"] = True
    with pytest.raises(ValueError):
        inputs.dataset_metadata(canonical_bytes(raw))
    monkeypatch.setattr(inputs, "MAX_MANIFEST_BYTES", 1)
    with pytest.raises(ValueError, match="Bounded"):
        inputs.dataset_metadata(b"{}")


@pytest.mark.parametrize(
    "mutation", ["extra", "missing", "reordered", "wrong-type", "nullable-id"]
)
def test_parquet_requires_exact_columns_types_and_nullability(mutation):
    metadata, frames = sst_fixture(1)
    records = records_for(metadata, frames)
    fields = list(inputs.ARROW_SCHEMA)
    if mutation == "extra":
        fields.append(pa.field("invented_generation", pa.string()))
    elif mutation == "missing":
        fields = fields[:-1]
    elif mutation == "reordered":
        fields = list(reversed(fields))
    elif mutation == "wrong-type":
        fields[2] = pa.field("value", pa.int64())
    else:
        fields[0] = pa.field("observation_id", pa.string(), nullable=True)
    with pytest.raises(ValueError, match="columns/types/nullability"):
        inputs.parse_table(metadata.table, parquet(records, schema=pa.schema(fields)))


@pytest.mark.parametrize(
    "mutation",
    [
        "dictionary",
        "wrong-count",
        "row-budget",
        "decoded-budget",
        "corrupt",
        "bytes-budget",
    ],
)
def test_parquet_rejects_corruption_expansion_or_resource_mismatch(
    monkeypatch, mutation
):
    metadata, frames = sst_fixture(2)
    records = records_for(metadata, frames)
    data = parquet(records, dictionary=mutation == "dictionary")
    if mutation == "wrong-count":
        metadata.table.row_count = 3
    elif mutation == "row-budget":
        monkeypatch.setattr(inputs, "MAX_ROWS", 1)
    elif mutation == "decoded-budget":
        monkeypatch.setattr(inputs, "MAX_DECODED_BYTES", 1)
    elif mutation == "corrupt":
        data = b"not parquet"
    elif mutation == "bytes-budget":
        monkeypatch.setattr(inputs, "MAX_BYTES", 1)
    with pytest.raises(ValueError):
        inputs.parse_table(metadata.table, data)


@pytest.mark.parametrize(
    "column,value",
    [
        ("value", float("nan")),
        ("value", float("inf")),
        ("uncertainty", float("-inf")),
        ("lat", float("nan")),
        ("observation_id", None),
        ("observation_id", " "),
        ("observation_id", "x" * 4001),
    ],
)
def test_opaque_parquet_never_turns_nonfinite_or_invalid_values_into_nulls(
    column, value
):
    metadata, frames = sst_fixture(1)
    records = records_for(metadata, frames)
    records[0][column] = value
    # Arrow correctly rejects an actual null in a nonnullable field on read;
    # either its writer or the adapter must reject that malformed record.
    with pytest.raises((ValueError, pa.ArrowException)):
        inputs.parse_table(metadata.table, parquet(records))


@pytest.mark.parametrize(
    "column,value",
    [
        ("value", True),
        ("uncertainty", "0.25"),
        ("observation_id", 42),
        ("value", float("inf")),
        ("source_sha256", False),
    ],
)
def test_writer_rejects_primitive_type_coercion_before_arrow(column, value):
    metadata, frames = sst_fixture(1)
    frames["observations"] = frames["observations"].astype(object)
    frames["observations"].at[0, column] = value
    with pytest.raises(ValueError):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize(
    "column,value",
    [
        ("status", "invented"),
        ("source_sha256", "bad-hash"),
        ("source_sha256", "A" * 64),
        ("uncertainty", -0.1),
        ("value", -274.0),
        ("time", "2024-02-30"),
        ("time", "2024-02-27T12:00:00Z"),
        ("time", "2024-02-26"),
        ("exclusion_reason", "source excluded"),
        ("lat", 38.5),
        ("lon", 141.5),
    ],
)
def test_rows_reject_incompatible_source_semantics(column, value):
    metadata, frames = sst_fixture(1)
    frames["observations"] = frames["observations"].astype(object)
    frames["observations"].at[0, column] = value
    with pytest.raises(ValueError):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize("status", ["invalid", "excluded"])
def test_unusable_observations_require_reason_even_when_measurement_is_null(status):
    metadata, frames = sst_fixture(1)
    frames["observations"].at[0, "status"] = status
    frames["observations"].at[0, "value"] = None
    with pytest.raises(ValueError, match="explicit reasons"):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize(
    "column,value",
    [
        ("valid_fraction", -0.1),
        ("valid_fraction", 1.1),
        ("valid_fraction", 0.8),
        ("valid_ocean_pixels", -1),
        ("valid_ocean_pixels", 101),
        ("valid_ocean_pixels", 90.0),
        ("valid_ocean_pixels", True),
        ("valid_ocean_pixels", 2**63),
        ("ocean_pixels", -1),
        ("ocean_pixels", 89),
        ("ocean_pixels", 100.0),
        ("ocean_pixels", False),
    ],
)
def test_quality_metrics_require_consistent_declared_fraction_and_integer_counts(
    column, value
):
    metadata, frames = sst_fixture(1)
    frames["observations"] = frames["observations"].astype(object)
    frames["observations"].at[0, column] = value
    with pytest.raises(ValueError):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


def test_unknown_quality_and_zero_ocean_denominator_never_become_zero_fraction():
    metadata, frames = sst_fixture(1)
    frame = frames["observations"].astype(object)
    frames["observations"] = frame
    columns = ["valid_fraction", "valid_ocean_pixels", "ocean_pixels"]
    frame.loc[0, columns] = [None, None, None]
    captured = inputs.dataset_exports(metadata, frames, generation="generation-1")
    row = inputs.parse_table(
        metadata.table, captured.contents[metadata.table.object_id]
    ).iloc[0]
    assert all(row[column] is None for column in columns)
    frame.loc[0, columns] = [None, 0, 0]
    inputs.dataset_exports(metadata, frames, generation="generation-1")
    frame.at[0, "valid_fraction"] = 0.0
    with pytest.raises(ValueError, match="Zero ocean pixels"):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


def test_quality_metrics_do_not_automatically_reclassify_source_status():
    metadata, frames = sst_fixture(1)
    frame = frames["observations"].astype(object)
    frames["observations"] = frame
    frame.loc[0, ["valid_fraction", "valid_ocean_pixels", "ocean_pixels"]] = [
        0.5,
        50,
        100,
    ]
    captured = inputs.dataset_exports(metadata, frames, generation="generation-1")
    row = inputs.parse_table(
        metadata.table, captured.contents[metadata.table.object_id]
    ).iloc[0]
    assert row["valid_fraction"] == 0.5
    assert row["status"] == "valid"
    assert row["quality_flag"] == "accepted"


def test_source_float32_fraction_precision_is_retained_without_recomputation():
    metadata, frames = sst_fixture(1)
    frame = frames["observations"].astype(object)
    frames["observations"] = frame
    fraction = 0.800000011920929
    frame.loc[0, ["valid_fraction", "valid_ocean_pixels", "ocean_pixels"]] = [
        fraction,
        80,
        100,
    ]
    captured = inputs.dataset_exports(metadata, frames, generation="generation-1")
    row = inputs.parse_table(
        metadata.table, captured.contents[metadata.table.object_id]
    ).iloc[0]
    assert row["valid_fraction"] == fraction
    assert row["valid_fraction"] != 0.8


def test_kelvin_units_are_not_coerced_to_celsius():
    metadata, frames = sst_fixture(1)
    metadata.descriptor.unit = "K"
    frames["observations"].at[0, "value"] = 280.0
    captured = inputs.dataset_exports(metadata, frames, generation="generation-1")
    assert inputs.parse_table(
        metadata.table, captured.contents[metadata.table.object_id]
    ).value.tolist() == [280.0]
    frames["observations"].at[0, "value"] = -1.0
    with pytest.raises(ValueError, match="absolute zero"):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize("mutation", ["identity", "regional-day", "grid-cell"])
def test_duplicate_source_identity_or_observation_cell_is_rejected(mutation):
    metadata, frames = sst_fixture(
        2,
        entity="grid_observation"
        if mutation == "grid-cell"
        else "regional_daily_summary",
    )
    frame = frames["observations"]
    if mutation == "identity":
        frame.at[1, "observation_id"] = frame.at[0, "observation_id"]
    else:
        frame.at[1, "time"] = frame.at[0, "time"]
        if mutation == "grid-cell":
            frame.loc[1, ["lat", "lon"]] = frame.loc[0, ["lat", "lon"]]
    with pytest.raises(ValueError, match="Duplicate"):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize(
    "column,value",
    [
        ("lat", None),
        ("lon", None),
        ("lat", 91.0),
        ("lon", 181.0),
        ("lat", 37.9),
        ("lon", 142.1),
    ],
)
def test_grid_rows_require_coordinates_inside_declared_support(column, value):
    metadata, frames = sst_fixture(1, entity="grid_observation")
    frames["observations"].at[0, column] = value
    with pytest.raises(ValueError):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


def test_grid_same_time_different_cells_are_retained_and_offsets_resolve_duplicate_instants():
    metadata, frames = sst_fixture(2, entity="grid_observation", precision="datetime")
    frame = frames["observations"]
    frame.at[0, "time"] = "2024-02-27T23:30:00Z"
    frame.at[1, "time"] = "2024-02-28T08:30:00+09:00"
    inputs.dataset_exports(metadata, frames, generation="generation-1")
    frame.loc[1, ["lat", "lon"]] = frame.loc[0, ["lat", "lon"]]
    with pytest.raises(ValueError, match="Duplicate"):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize(
    "value,precision",
    [
        ("2024-02-27", "datetime"),
        ("2024-02-27T12:00:00", "datetime"),
        ("2024-02-27 12:00:00Z", "datetime"),
        ("2024-02", "day"),
        ("2024-02-30", "day"),
    ],
)
def test_temporal_precision_is_never_invented(value, precision):
    with pytest.raises(ValueError):
        inputs.observation_time(value, precision, "UTC")


def test_calendar_day_resolves_declared_zone_without_relabeling_source():
    assert (
        inputs.observation_day("2024-02-27T23:30:00Z", "datetime", "Asia/Tokyo")
        == "2024-02-28"
    )
    assert (
        inputs.observation_day("2024-02-27T23:30:00Z", "datetime", "UTC")
        == "2024-02-27"
    )
    assert inputs.observation_day("2024-02-27", "day", "Asia/Tokyo") == "2024-02-27"


@pytest.mark.parametrize(
    "value,precision,calendar",
    [
        ("0001-01-01T00:00:00+09:00", "datetime", "UTC"),
        ("0001-01-01T00:00:00+09:00", "datetime", "Asia/Tokyo"),
        ("9999-12-31T23:59:59-12:00", "datetime", "UTC"),
        ("9999-12-31T15:00:00Z", "datetime", "Asia/Tokyo"),
        ("0001-01-01", "day", "Asia/Tokyo"),
        ("9999-12-31", "day", "UTC"),
    ],
)
def test_unrepresentable_calendar_or_utc_boundaries_raise_value_error(
    value, precision, calendar
):
    with pytest.raises(ValueError, match="representable"):
        inputs.observation_time(value, precision, calendar)


def test_representable_extreme_instants_remain_valid():
    assert inputs.observation_time("0001-01-01T00:00:00Z", "datetime", "UTC").year == 1
    assert (
        inputs.observation_time("9999-12-31T14:59:59Z", "datetime", "Asia/Tokyo").year
        == 9999
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-metadata-role",
        "wrong-metadata-schema",
        "metadata-identity",
        "wrong-table-role",
        "wrong-table-schema",
        "wrong-operation",
        "wrong-version",
        "wrong-source",
        "orphan",
        "missing-object",
        "corrupt-bytes",
    ],
)
def test_sealed_object_ownership_hash_or_roles_cannot_be_bypassed(tmp_path, mutation):
    manifest, contents, metadata = frozen(tmp_path)
    table = next(item for item in manifest.objects if item.role == "observations")
    if mutation == "wrong-metadata-role":
        metadata.role = "unrecognized"
    elif mutation == "wrong-metadata-schema":
        metadata.schema_version = "unrecognized"
    elif mutation == "metadata-identity":
        raw = json.loads(contents[metadata.object_id])
        raw["dataset_id"] = "synthetic:different-dataset"
        contents[metadata.object_id] = canonical_bytes(raw)
        metadata.sha256 = hashlib.sha256(contents[metadata.object_id]).hexdigest()
        metadata.size_bytes = len(contents[metadata.object_id])
        metadata.provenance.content_sha256 = metadata.sha256
    elif mutation == "wrong-table-role":
        table.role = "unrecognized"
    elif mutation == "wrong-table-schema":
        table.schema_version = "unrecognized"
    elif mutation == "wrong-operation":
        table.operation_id = "unregistered:export"
    elif mutation == "wrong-version":
        table.operation_version = "unrecognized"
    elif mutation == "wrong-source":
        table.source_id = "synthetic:different-source"
    elif mutation == "orphan":
        extra = table.model_copy(deep=True)
        extra.object_id = "synthetic:orphan"
        manifest.objects.append(extra)
    elif mutation == "missing-object":
        contents.pop(table.object_id)
    else:
        contents[table.object_id] += b"corrupt"
    with pytest.raises(ValueError):
        inputs.load_dataset(manifest, contents, metadata)


def test_registration_detaches_mutable_inputs_and_every_returned_object():
    metadata, frames = sst_fixture(2)
    requirement = inputs.frozen_export_requirement(
        metadata, frames, source_generation="generation-1"
    )
    frames["observations"].drop(index=0, inplace=True)
    metadata.qualification = "mutated after freezing"
    heads = CaptureHeads({"source:synthetic-sst": "generation-1"})
    first = requirement.exporter(None, heads, time.monotonic() + 10)
    first.objects[0].source_id = "mutated by consumer"
    second = requirement.exporter(None, heads, time.monotonic() + 10)
    assert all(item.source_id == "synthetic-sst" for item in second.objects)
    retained = next(item for item in second.objects if item.role == "observations")
    metadata.table.row_count = 2
    assert (
        len(inputs.parse_table(metadata.table, second.contents[retained.object_id]))
        == 2
    )
    assert requirement.capture_method == "c11-frozen-sst-parquet-v1"
    assert requirement.operation_ids == {
        "dataset_metadata": "c11:remote_sensing:dataset_metadata",
        "observations": "c11:remote_sensing:observations",
    }


@pytest.mark.parametrize("deadline", [0, float("inf"), float("nan"), True])
def test_registration_enforces_deadline(deadline):
    metadata, frames = sst_fixture(1)
    requirement = inputs.frozen_export_requirement(
        metadata, frames, source_generation="generation-1"
    )
    with pytest.raises(inputs.AdapterUnavailable, match="deadline"):
        requirement.exporter(
            None, CaptureHeads({"source:synthetic-sst": "generation-1"}), deadline
        )


def test_registration_never_relabels_frozen_bytes_with_new_source_head():
    metadata, frames = sst_fixture(1)
    requirement = inputs.frozen_export_requirement(
        metadata, frames, source_generation="generation-1"
    )
    with pytest.raises(inputs.AdapterUnavailable, match="generation"):
        requirement.exporter(
            None,
            CaptureHeads({"source:synthetic-sst": "generation-2"}),
            time.monotonic() + 10,
        )


@pytest.mark.parametrize("mutation", ["empty", "mixed-source", "duplicate"])
def test_source_registration_requires_unambiguous_explicit_identity(mutation):
    datasets = (
        []
        if mutation == "empty"
        else [
            sst_fixture(1),
            sst_fixture(1, dataset_id="synthetic:sst:b", source_id="other-source"),
        ]
        if mutation == "mixed-source"
        else [sst_fixture(1), sst_fixture(1)]
    )
    with pytest.raises(ValueError):
        inputs.frozen_source_requirement(datasets, source_generation="generation-1")


@pytest.mark.parametrize("budget", ["rows", "decoded", "objects", "bytes"])
def test_batch_registration_applies_cumulative_bounds(monkeypatch, budget):
    count = 20 if budget == "decoded" else 1
    datasets = [sst_fixture(count), sst_fixture(count, dataset_id="synthetic:sst:b")]
    if budget == "rows":
        monkeypatch.setattr(inputs, "MAX_ROWS", 1)
    elif budget == "objects":
        monkeypatch.setattr(inputs, "MAX_OBJECTS", 3)
    elif budget == "decoded":
        metadata, frames = datasets[0]
        one = inputs.dataset_exports(metadata, frames, generation="generation-1")
        data = one.contents[metadata.table.object_id]
        footer = pq.ParquetFile(BytesIO(data)).metadata
        retained = inputs.parse_table(metadata.table, data).attrs["decoded_bytes"]
        limit = (
            max(
                retained,
                sum(
                    footer.row_group(i).total_byte_size
                    for i in range(footer.num_row_groups)
                ),
            )
            + 1
        )
        assert retained * 2 > limit
        monkeypatch.setattr(inputs, "MAX_DECODED_BYTES", limit)
    else:
        one = inputs.dataset_exports(*datasets[0], generation="generation-1")
        monkeypatch.setattr(
            inputs, "MAX_BYTES", sum(map(len, one.contents.values())) + 100
        )
    with pytest.raises(ValueError, match="budget|bounds"):
        inputs.frozen_source_requirement(datasets, source_generation="generation-1")


def test_batch_registration_includes_every_dataset_without_promoting_publication():
    datasets = [sst_fixture(1, dataset_id=f"synthetic:sst:batch-{i}") for i in range(3)]
    requirement = inputs.frozen_source_requirement(
        datasets, source_generation="generation-1"
    )
    captured = requirement.exporter(
        None,
        CaptureHeads({"source:synthetic-sst": "generation-1"}),
        time.monotonic() + 10,
    )
    assert len(captured.objects) == 6
    assert len({item.dataset_id for item in captured.objects}) == 3
    assert set(captured.contents) == {item.object_id for item in captured.objects}


def test_canonical_export_order_is_stable_and_parser_rejects_duplicate_ids():
    metadata, frames = sst_fixture(3)
    before = inputs.dataset_exports(metadata, frames, generation="generation-1")
    frames["observations"] = frames["observations"].iloc[::-1]
    after = inputs.dataset_exports(metadata, frames, generation="generation-1")
    assert dict(before.contents) == dict(after.contents)
    rows = records_for(metadata, frames)
    rows[1]["observation_id"] = rows[0]["observation_id"]
    with pytest.raises(ValueError, match="identities must be unique"):
        inputs.parse_table(metadata.table, parquet(rows))
