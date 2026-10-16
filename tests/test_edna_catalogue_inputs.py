"""Adversarial canonical C12 inputs and immutable C09 export registration."""

import hashlib
from io import BytesIO
import json
import time

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ingestion import edna_catalogue_inputs as inputs
from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.catalogue_snapshot_capture import CaptureHeads
from ingestion.immutable_bundle import canonical_bytes
from preprocessing.anemone_classification import build_review_lineage, canonical_sha256
from schema.edna_catalogue import RAW_METHODS, ROLES
from schema.edna_catalogue_fixtures import edna_fixture, seal_edna_fixture


def fixture(count=10):
    metadata, frames = edna_fixture(count)
    return metadata, {name: frame.astype(object) for name, frame in frames.items()}


def spec(metadata, role):
    return next(item for item in metadata.tables if item.name == role)


def frozen(tmp_path, source=None):
    metadata, frames = source or fixture()
    store = LocalCatalogueSnapshotStore(root=tmp_path.resolve(), access_gate=lambda manifest: True)
    identity = seal_edna_fixture(store, [(metadata, frames)])
    manifest, contents = store.read(identity)
    obj = next(item for item in manifest.objects if item.role == "canonical_rows")
    return manifest, dict(contents), obj


def parquet(role, records, *, schema=None, dictionary=False):
    stream = BytesIO()
    pq.write_table(pa.Table.from_pylist(records, schema=schema or inputs.ARROW_SCHEMAS[role]), stream, use_dictionary=dictionary)
    return stream.getvalue()


def unavailable(metadata, frames, role, status="unavailable"):
    table = spec(metadata, role)
    table.object_id = None
    table.row_count = None
    table.availability.status = status
    table.availability.reason = "Synthetic unavailable source input; no empty population implied"
    table.completeness = status
    frames.pop(role)


@pytest.mark.parametrize("count", [0, 1, 10])
def test_complete_relational_roundtrip_preserves_every_source_value(tmp_path, count):
    metadata, frames = fixture(count)
    manifest, contents, obj = frozen(tmp_path, (metadata, frames))
    loaded = inputs.load_dataset(manifest, contents, obj)
    assert loaded.metadata == metadata
    assert {item.object_id for item in loaded.objects} == set(contents)
    assert set(loaded.tables) == set(ROLES)
    for name, original in frames.items():
        key = inputs.KEYS[name]
        before = inputs._frame_records(name, original.sort_values(key))
        after = loaded.tables[name].to_dict("records")
        assert after == before
        assert loaded.tables[name].attrs["decoded_bytes"] >= 0
    if count:
        zeros = loaded.tables["detections"].query("read_count == 0").to_dict("records")
        assert len(zeros) == 4
        assert all(row["copies_per_ml"] == 0.0 for row in zeros)
        assert set(loaded.tables["detections"].assignment_method) == set(RAW_METHODS)


@pytest.mark.parametrize("status", ["unknown", "unavailable"])
def test_absent_tables_use_real_classification_qualification_not_fake_empty_rows(tmp_path, status):
    metadata, frames = fixture(0)
    for role in ROLES:
        unavailable(metadata, frames, role, status)
    manifest, contents, obj = frozen(tmp_path, (metadata, frames))
    loaded = inputs.load_dataset(manifest, contents, obj)
    assert loaded.tables == {}
    assert all(item.row_count is None for item in loaded.metadata.tables)
    classification = next(item for item in loaded.objects if item.role == "classifications")
    assert classification.schema_version == inputs.CLASSIFICATION_STATE_VERSION
    state = json.loads(contents[classification.object_id])
    assert state["table"]["row_count"] is None
    assert state["table"]["availability"]["status"] == status
    assert state["table"]["object_id"] is None


def test_unavailable_detection_table_retains_source_availability_without_known_detection_count(tmp_path):
    metadata, frames = fixture(1)
    unavailable(metadata, frames, "detections")
    manifest, contents, obj = frozen(tmp_path, (metadata, frames))
    loaded = inputs.load_dataset(manifest, contents, obj)
    assert "detections" not in loaded.tables
    assert spec(loaded.metadata, "detections").row_count is None
    assert inputs.parse_community_availability(loaded.tables["assays"].iloc[0].community_availability_json)


@pytest.mark.parametrize("payload", [b'{}', b'[]', b'\xff', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1,"x":2}'])
def test_metadata_rejects_invalid_duplicate_nonfinite_or_incomplete_json(payload):
    with pytest.raises(ValueError):
        inputs.dataset_metadata(payload)


def test_metadata_is_bounded_and_forbids_unregistered_approval_fields(monkeypatch):
    metadata, _ = fixture(1)
    raw = metadata.model_dump(mode="json")
    raw["scientific_approval"] = True
    with pytest.raises(ValueError):
        inputs.dataset_metadata(canonical_bytes(raw))
    monkeypatch.setattr(inputs, "MAX_MANIFEST_BYTES", 1)
    with pytest.raises(ValueError, match="Bounded"):
        inputs.dataset_metadata(b"{}")


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("mutation", ["extra", "missing", "reordered", "wrong-type", "nullable-id"])
def test_parquet_requires_exact_columns_types_order_and_nullability(role, mutation):
    metadata, frames = fixture(1)
    fields = list(inputs.ARROW_SCHEMAS[role])
    records = inputs._frame_records(role, frames[role])
    if mutation == "extra":
        fields.append(pa.field("invented_approval", pa.bool_()))
    elif mutation == "missing":
        fields.pop()
    elif mutation == "reordered":
        fields.reverse()
    elif mutation == "wrong-type":
        fields[0] = pa.field(fields[0].name, pa.large_string(), nullable=False)
    else:
        fields[0] = pa.field(fields[0].name, pa.string(), nullable=True)
    with pytest.raises(ValueError, match="columns/types/nullability"):
        inputs.parse_table(spec(metadata, role), parquet(role, records, schema=pa.schema(fields)))


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("mutation", ["dictionary", "wrong-count", "row-budget", "decoded-budget", "corrupt", "bytes-budget"])
def test_parquet_rejects_corruption_expansion_and_resource_mismatch(monkeypatch, role, mutation):
    metadata, frames = fixture(1)
    data = parquet(role, inputs._frame_records(role, frames[role]), dictionary=mutation == "dictionary")
    if mutation == "wrong-count":
        spec(metadata, role).row_count += 1
    elif mutation == "row-budget":
        monkeypatch.setattr(inputs, "MAX_ROWS", 0)
    elif mutation == "decoded-budget":
        monkeypatch.setattr(inputs, "MAX_DECODED_BYTES", 0)
    elif mutation == "corrupt":
        data = b"not a parquet file"
    elif mutation == "bytes-budget":
        monkeypatch.setattr(inputs, "MAX_BYTES", 1)
    with pytest.raises(ValueError):
        inputs.parse_table(spec(metadata, role), data)


@pytest.mark.parametrize("role,column,value", [
    ("occurrences", "sample_id", 42), ("occurrences", "active", 1),
    ("occurrences", "lat", True), ("occurrences", "lat", float("inf")),
    ("classifications", "is_control", 0), ("classifications", "sample_kind", " "),
    ("assays", "active", "true"), ("assays", "sample_id", None),
    ("detections", "read_count", True), ("detections", "read_count", 1.5),
    ("detections", "read_count", -1), ("detections", "copies_per_ml", "0"),
    ("detections", "copies_per_ml", float("inf")),
])
def test_writer_rejects_primitive_coercion_and_nonfinite_values(role, column, value):
    metadata, frames = fixture(1)
    frames[role].at[0, column] = value
    with pytest.raises(ValueError):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize("role,column", [("occurrences", "lat"), ("occurrences", "lon"), ("detections", "copies_per_ml")])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_opaque_parquet_nonfinite_payloads_do_not_become_nullable_unknowns(role, column, value):
    metadata, frames = fixture(1)
    records = inputs._frame_records(role, frames[role])
    records[0][column] = value
    with pytest.raises(ValueError, match="finite"):
        inputs.parse_table(spec(metadata, role), parquet(role, records))


@pytest.mark.parametrize("role,column,value", [
    ("occurrences", "sample_id", "root:invented"),
    ("occurrences", "source_occurrence_id", "not-a-hash"),
    ("occurrences", "source_snapshot_id", "A" * 64),
    ("occurrences", "scientific_content_sha256", "bad"),
    ("occurrences", "provider", "another-provider"),
    ("occurrences", "provider_locus", "another-locus"),
    ("occurrences", "provider_team", "another-team"),
    ("occurrences", "provider_project_id", "another-project"),
    ("occurrences", "collection_date_utc", "2024-02-30"),
    ("occurrences", "temporal_precision", "datetime"),
    ("occurrences", "lat", 91.0), ("occurrences", "lon", -181.0),
    ("occurrences", "lat", None),
    ("occurrences", "identity_status", "inferred_sample"),
    ("occurrences", "physical_sample_id", "inferred-physical-sample"),
    ("classifications", "sample_kind", "invented"),
    ("classifications", "sample_kind", "unknown"),
    ("classifications", "source_snapshot_id", "b" * 64),
    ("classifications", "provider_sample_id", "another-provider-sample"),
    ("classifications", "classification_basis", "review:invented"),
    ("classifications", "classification_review_json", "{}"),
    ("assays", "sample_id", "b" * 64),
    ("assays", "assay_id", "arbitrary-assay"),
    ("detections", "assay_id", "b" * 64),
    ("detections", "detection_id", "arbitrary-detection"),
    ("detections", "assignment_method", "unregistered_method"),
    ("detections", "target_status", "nontarget"),
    ("detections", "sequence_sha256", "bad"),
    ("detections", "concentration_status", "missing"),
    ("detections", "copies_per_ml", -1.0),
    ("detections", "assigned_taxon_name", "invented species"),
    ("detections", "assigned_taxon_rank", "isolate"),
    ("detections", "taxonomy_json", '{"invented_rank":"fish"}'),
    ("detections", "taxonomy_json", '{"species":"a","species":"b"}'),
    ("detections", "taxonomy_json", '{"species":NaN}'),
    ("detections", "taxonomy_json", '[]'),
])
def test_source_identity_qualifications_and_relations_cannot_be_reinterpreted(role, column, value):
    metadata, frames = fixture(1)
    frames[role].at[0, column] = value
    with pytest.raises(ValueError):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize("role", ROLES)
def test_duplicate_canonical_keys_are_rejected(role):
    metadata, frames = fixture(2)
    key = inputs.KEYS[role]
    frames[role].at[1, key] = frames[role].at[0, key]
    with pytest.raises(ValueError, match="Duplicate"):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


def test_distinct_detection_ids_cannot_duplicate_assay_method_sequence_evidence():
    metadata, frames = fixture(1)
    frames["detections"].at[1, "assignment_method"] = frames["detections"].at[0, "assignment_method"]
    frames["detections"].at[1, "target_status"] = frames["detections"].at[0, "target_status"]
    with pytest.raises(ValueError, match="Duplicate assay/method/sequence"):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize("value,precision", [
    (None, None), (None, "unknown"), ("2024", "year"),
    ("2024-02", "month"), ("2024-02-29", "date"), ("2024-02-29", "day"),
    ("2024-02-29T11:12:13Z", "datetime"), ("2024-02-29T11:12:13+00:00", "datetime"),
])
def test_coarse_unresolved_and_explicit_utc_dates_are_retained_without_precision_invention(value, precision):
    metadata, frames = fixture(1)
    frames["occurrences"].at[0, "collection_date_utc"] = value
    frames["occurrences"].at[0, "temporal_precision"] = precision
    exported = inputs.dataset_exports(metadata, frames, generation="generation-1")
    table = spec(metadata, "occurrences")
    row = inputs.parse_table(table, exported.contents[table.object_id]).iloc[0]
    assert row.collection_date_utc == value
    assert row.temporal_precision == precision


@pytest.mark.parametrize("value,precision", [
    (None, "date"), ("2024-02-29", None), ("2024-02-29", "unknown"),
    ("2024-2", "month"), ("2024-13", "month"), ("0000", "year"),
    ("2024-02-29T11:12:13", "datetime"),
    ("2024-02-29T20:12:13+09:00", "datetime"),
])
def test_mismatched_dates_naive_instants_and_utc_relabeling_fail(value, precision):
    metadata, frames = fixture(1)
    frames["occurrences"].at[0, "collection_date_utc"] = value
    frames["occurrences"].at[0, "temporal_precision"] = precision
    with pytest.raises(ValueError):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize("mutation", ["unknown-method", "unknown-status", "bad-source", "source-snapshot", "bad-count", "bool-count", "extra-key", "missing-key", "count-mismatch"])
def test_source_backed_method_availability_cannot_be_invented_or_counted_incorrectly(mutation):
    metadata, frames = fixture(1)
    value = json.loads(frames["assays"].at[0, "community_availability_json"])
    method = RAW_METHODS[0]
    if mutation == "unknown-method":
        value["unknown_method"] = value.pop(method)
    elif mutation == "unknown-status":
        value[method]["status"] = "unknown"
    elif mutation == "bad-source":
        value[method]["source_file_id"] = "not-a-hash"
    elif mutation == "source-snapshot":
        value[method]["source_snapshot_id"] = "b" * 64
    elif mutation == "bad-count":
        value[method]["row_count"] = -1
    elif mutation == "bool-count":
        value[method]["row_count"] = True
    elif mutation == "extra-key":
        value[method]["scientific_approval"] = True
    elif mutation == "missing-key":
        value[method].pop("source_file_id")
    elif mutation == "count-mismatch":
        value[method]["row_count"] = 0
    frames["assays"].at[0, "community_availability_json"] = json.dumps(value)
    with pytest.raises(ValueError):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize("value", [None, "{}"])
def test_legacy_canonical_detections_supply_method_evidence_without_inventing_availability(tmp_path, value):
    metadata, frames = fixture(1)
    frames["assays"].at[0, "community_availability_json"] = value
    manifest, contents, obj = frozen(tmp_path, (metadata, frames))
    loaded = inputs.load_dataset(manifest, contents, obj)
    assert loaded.tables["assays"].iloc[0].community_availability_json == value
    assert inputs.parse_community_availability(value) == {}
    assert set(loaded.tables["detections"].assignment_method) == set(RAW_METHODS)
    assert len(loaded.tables["detections"]) == 4


def test_detection_evidence_is_distinct_from_an_explicit_available_empty_method(tmp_path):
    metadata, frames = fixture(1)
    value = json.loads(frames["assays"].at[0, "community_availability_json"])
    value.pop(RAW_METHODS[0])
    frames["assays"].at[0, "community_availability_json"] = json.dumps(value)
    manifest, contents, obj = frozen(tmp_path, (metadata, frames))
    loaded = inputs.load_dataset(manifest, contents, obj)
    retained = inputs.parse_community_availability(loaded.tables["assays"].iloc[0].community_availability_json)
    assert RAW_METHODS[0] not in retained
    assert RAW_METHODS[0] in set(loaded.tables["detections"].assignment_method)


def test_unknown_source_method_row_count_is_not_manufactured_from_detections(tmp_path):
    metadata, frames = fixture(1)
    value = json.loads(frames["assays"].at[0, "community_availability_json"])
    value[RAW_METHODS[0]]["row_count"] = None
    frames["assays"].at[0, "community_availability_json"] = json.dumps(value)
    manifest, contents, obj = frozen(tmp_path, (metadata, frames))
    loaded = inputs.load_dataset(manifest, contents, obj)
    assert inputs.parse_community_availability(loaded.tables["assays"].iloc[0].community_availability_json)[RAW_METHODS[0]]["row_count"] is None


def test_complete_counts_reconcile_but_partial_source_rows_do_not_claim_completeness():
    metadata, frames = fixture(1)
    frames["detections"] = frames["detections"].iloc[1:].copy()
    spec(metadata, "detections").row_count -= 1
    with pytest.raises(ValueError, match="Source method row count"):
        inputs.dataset_exports(metadata, frames, generation="generation-1")
    spec(metadata, "detections").completeness = "partial"
    inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize("field,value", [("assignment_method", "qcauto_target"), ("assignment_method", "unknown"), ("sample_kind", "environmental"), ("sample_kind", "unknown")])
def test_single_population_descriptor_cannot_hide_mixed_raw_inventory(field, value):
    metadata, frames = fixture()
    setattr(metadata.descriptor, field, value)
    if field == "sample_kind":
        metadata.descriptor.is_control = False if value == "environmental" else None
    with pytest.raises(ValueError, match="descriptor"):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


def test_exact_shared_review_lineage_is_retained_and_mismatched_review_is_rejected():
    metadata, frames = fixture(1)
    sample = frames["occurrences"].iloc[0]
    decision = {
        "provider_sample_id": sample.provider_sample_id, "sample_kind": "environmental",
        "reviewer": "Synthetic test reviewer; no independent scientific approval",
        "reviewed_at": "2024-01-01T00:00:00Z", "rationale": "Synthetic lineage validation only",
        "evidence": [{"source_role": "sample_metadata", "source_sha256": "a" * 64, "row_number": 2, "key": "synthetic", "value": "environmental"}],
    }
    review = {"schema_version": 1, "status": "approved", "source_snapshot_id": sample.source_snapshot_id, "decisions": [decision]}
    lineage = build_review_lineage(review, decision, provider_classification_basis="synthetic-provider-only")
    frames["classifications"].at[0, "classification_review_json"] = json.dumps(lineage)
    frames["classifications"].at[0, "classification_basis"] = "review:" + canonical_sha256(lineage)
    inputs.dataset_exports(metadata, frames, generation="generation-1")
    lineage["decision"]["provider_sample_id"] = "another-provider-sample"
    frames["classifications"].at[0, "classification_review_json"] = json.dumps(lineage)
    with pytest.raises(ValueError):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


@pytest.mark.parametrize("mutation", ["wrong-role", "wrong-version", "wrong-operation", "extra-object", "missing-object", "bytes-hash", "metadata-identity", "table-role", "object-membership"])
def test_hash_valid_object_bytes_still_require_exact_frozen_ownership(tmp_path, mutation):
    manifest, contents, obj = frozen(tmp_path)
    table = next(item for item in manifest.objects if item.role == "occurrences")
    if mutation == "wrong-role":
        obj.role = "dataset_metadata"
    elif mutation == "wrong-version":
        obj.schema_version = "invented-v2"
    elif mutation == "wrong-operation":
        table.operation_id = "unregistered:operation"
    elif mutation == "extra-object":
        extra = table.model_copy(deep=True)
        extra.object_id = "synthetic:orphan"
        manifest.objects.append(extra)
        contents[extra.object_id] = contents[table.object_id]
    elif mutation == "missing-object":
        manifest.objects.remove(table)
    elif mutation == "bytes-hash":
        contents[table.object_id] += b"corrupt"
    elif mutation == "metadata-identity":
        raw = json.loads(contents[obj.object_id])
        raw["dataset_id"] = "another-dataset"
        contents[obj.object_id] = canonical_bytes(raw)
        obj.sha256 = hashlib.sha256(contents[obj.object_id]).hexdigest()
        obj.size_bytes = len(contents[obj.object_id])
    elif mutation == "table-role":
        table.role = "assays"
    else:
        manifest.objects.remove(obj)
    with pytest.raises(ValueError):
        inputs.load_dataset(manifest, contents, obj)


def test_cumulative_row_budget_fails_before_any_parquet_decode(tmp_path, monkeypatch):
    manifest, contents, obj = frozen(tmp_path, fixture(1))
    monkeypatch.setattr(inputs, "MAX_ROWS", 1)
    def unexpected(*args, **kwargs):
        pytest.fail("Cumulative row count must fail before parsing table bytes")
    monkeypatch.setattr(inputs, "parse_table", unexpected)
    with pytest.raises(ValueError, match="Cumulative"):
        inputs.load_dataset(manifest, contents, obj)


def test_cumulative_decoded_budget_is_passed_as_remaining_capacity(tmp_path, monkeypatch):
    manifest, contents, obj = frozen(tmp_path, fixture(1))
    actual = inputs.parse_table
    seen = []
    def observe(specification, data, **kwargs):
        seen.append(kwargs["decoded_budget"])
        return actual(specification, data, **kwargs)
    monkeypatch.setattr(inputs, "parse_table", observe)
    inputs.load_dataset(manifest, contents, obj)
    assert seen[0] == inputs.MAX_DECODED_BYTES
    assert all(left > right for left, right in zip(seen, seen[1:]))


@pytest.mark.parametrize("budget", [0, 1])
def test_caller_remaining_decoded_budget_bounds_dataset_before_decode(tmp_path, budget):
    manifest, contents, obj = frozen(tmp_path, fixture(1))
    with pytest.raises(ValueError, match="decoded budget"):
        inputs.load_dataset(manifest, contents, obj, decoded_budget=budget)


@pytest.mark.parametrize("budget", [True, -1, "1", 1.0])
def test_caller_decoded_budgets_are_strict_primitive_integers(tmp_path, budget):
    manifest, contents, obj = frozen(tmp_path, fixture(1))
    with pytest.raises(ValueError, match="decoded budget"):
        inputs.load_dataset(manifest, contents, obj, decoded_budget=budget)
    metadata, frames = fixture(1)
    data = parquet("occurrences", inputs._frame_records("occurrences", frames["occurrences"]))
    with pytest.raises(ValueError, match="decoded budget"):
        inputs.parse_table(spec(metadata, "occurrences"), data, decoded_budget=budget)


@pytest.mark.parametrize("mutation", ["frames", "row-count", "source-occurrence", "classification-missing", "assay-orphan", "columns", "rows-budget", "decoded-budget"])
def test_export_requires_exact_frames_relations_and_cumulative_budgets(monkeypatch, mutation):
    metadata, frames = fixture(2)
    if mutation == "frames":
        frames.pop("detections")
    elif mutation == "row-count":
        spec(metadata, "assays").row_count += 1
    elif mutation == "source-occurrence":
        frames["occurrences"].at[1, "source_occurrence_id"] = frames["occurrences"].at[0, "source_occurrence_id"]
    elif mutation == "classification-missing":
        frames["classifications"] = frames["classifications"].iloc[1:]
        spec(metadata, "classifications").row_count -= 1
    elif mutation == "assay-orphan":
        unavailable(metadata, frames, "assays")
    elif mutation == "columns":
        frames["assays"] = frames["assays"][list(reversed(frames["assays"].columns))]
    elif mutation == "rows-budget":
        monkeypatch.setattr(inputs, "MAX_ROWS", 1)
    else:
        monkeypatch.setattr(inputs, "MAX_DECODED_BYTES", 1)
    with pytest.raises(ValueError):
        inputs.dataset_exports(metadata, frames, generation="generation-1")


def test_export_registration_binds_immutable_bytes_and_exact_source_generation():
    metadata, frames = fixture(1)
    registration = inputs.frozen_export_requirement(metadata, frames, source_generation="generation-1")
    heads = CaptureHeads({f"source:{metadata.source_id}": "generation-1"})
    first = registration.exporter(None, heads, time.monotonic() + 10)
    frames["occurrences"].at[0, "provider"] = "mutated-after-registration"
    metadata.qualification = "mutated-after-registration"
    first.objects[0].sha256 = "b" * 64
    second = registration.exporter(None, heads, time.monotonic() + 10)
    assert b"mutated-after-registration" not in second.contents[second.objects[0].object_id]
    assert second.objects[0].sha256 != "b" * 64
    with pytest.raises(TypeError):
        second.contents["new-object"] = b"unregistered"
    with pytest.raises(inputs.AdapterUnavailable, match="generation"):
        registration.exporter(None, CaptureHeads({f"source:{metadata.source_id}": "generation-2"}), time.monotonic() + 10)


@pytest.mark.parametrize("deadline", [0, float("inf"), float("nan"), True, "later"])
def test_export_registration_rejects_expired_nonfinite_or_coerced_deadlines(deadline):
    metadata, frames = fixture(1)
    registration = inputs.frozen_export_requirement(metadata, frames, source_generation="generation-1")
    with pytest.raises(inputs.AdapterUnavailable, match="deadline"):
        registration.exporter(None, CaptureHeads({f"source:{metadata.source_id}": "generation-1"}), deadline)


@pytest.mark.parametrize("mutation", ["empty", "different-source", "duplicate", "objects-budget", "bytes-budget", "cumulative-rows", "mixed-classification-schema"])
def test_source_registration_rejects_ambiguous_identity_or_unbounded_combined_inputs(monkeypatch, mutation):
    first = fixture(1)
    second = edna_fixture(1, dataset_id="synthetic:edna:other", source_id=first[0].source_id)
    items = [first, second]
    if mutation == "empty":
        items = []
    elif mutation == "different-source":
        second[0].source_id = "another-source"
    elif mutation == "duplicate":
        items = [first, first]
    elif mutation == "objects-budget":
        monkeypatch.setattr(inputs, "MAX_OBJECTS", 1)
    elif mutation == "bytes-budget":
        monkeypatch.setattr(inputs, "MAX_BYTES", 1)
    elif mutation == "cumulative-rows":
        monkeypatch.setattr(inputs, "MAX_ROWS", 10)
    else:
        second = fixture(0)
        second[0].dataset_id = "synthetic:edna:unavailable"
        for role in ROLES:
            unavailable(*second, role)
        items = [first, second]
    with pytest.raises(ValueError):
        inputs.frozen_source_requirement(items, source_generation="generation-1")


def test_source_registration_exports_all_explicit_datasets_without_live_discovery():
    first = fixture(1)
    second = edna_fixture(1, dataset_id="synthetic:edna:other", source_id=first[0].source_id)
    registration = inputs.frozen_source_requirement([first, second], source_generation="generation-1")
    captured = registration.exporter(None, CaptureHeads({f"source:{first[0].source_id}": "generation-1"}), time.monotonic() + 10)
    assert {item.dataset_id for item in captured.objects} == {first[0].dataset_id, second[0].dataset_id}
    assert len(captured.objects) == 10
    assert {"canonical_rows", "classifications"} <= set(registration.schema_versions)
