"""C12 raw inventory contracts preserve the distinct C01 scientific boundary."""

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from retrieval.source_scope import EvidenceScope
from schema.context_catalogue import EDNADescriptor
from schema.edna_catalogue import EDNADataset, RAW_METHODS, TABLE_COLUMNS
from schema.edna_catalogue_fixtures import edna_fixture, edna_scope
from scripts.export_edna_catalogue import generated_files

ROOT = Path(__file__).resolve().parents[1]


def test_generated_schema_and_examples_are_current():
    for path, expected in generated_files().items():
        assert path.read_text() == expected


def _descriptor(**changes):
    return {
        "family": "edna_metabarcoding",
        "protocol_id": "synthetic-mifish",
        "protocol": "Synthetic MiFish",
        "assignment_method": "qcauto_target",
        "sample_kind": "environmental",
        "is_control": False,
        "measurement": "assigned_reads",
        "unit": "reads",
        **changes,
    }


def test_prior_scientific_descriptor_remains_accepted_with_scientific_default():
    value = _descriptor()
    before = copy.deepcopy(value)
    parsed = EDNADescriptor.model_validate(value)
    assert parsed.population == "scientific"
    assert value == before


@pytest.mark.parametrize("method", [*RAW_METHODS, "mixed", "unknown"])
def test_explicit_raw_population_retains_all_method_labels_without_coercion(method):
    parsed = EDNADescriptor.model_validate(
        _descriptor(
            population="raw_inventory",
            assignment_method=method,
            sample_kind="mixed",
            is_control=None,
        )
    )
    assert parsed.assignment_method == method
    assert parsed.population == "raw_inventory"


@pytest.mark.parametrize(
    "method", ["qcauto_nontarget", "qcauto_95pct_3nn_nontarget", "mixed", "unknown"]
)
@pytest.mark.parametrize("explicit", [False, True])
def test_raw_method_enum_extension_does_not_grant_scientific_execution(
    method, explicit
):
    descriptor = _descriptor(assignment_method=method)
    if explicit:
        descriptor["population"] = "scientific"
    with pytest.raises(ValueError, match="Scientific descriptors"):
        EDNADescriptor.model_validate(descriptor)
    scope = edna_scope().model_dump(mode="json")
    scope["sources"]["edna_metabarcoding"]["filters"]["assignment_method"] = method
    with pytest.raises(ValueError):
        EvidenceScope.model_validate(scope)


@pytest.mark.parametrize(
    "value",
    [
        _descriptor(sample_kind="mixed", is_control=None),
        _descriptor(population="raw_inventory", sample_kind="mixed", is_control=False),
        _descriptor(population="raw_inventory", sample_kind="unknown", is_control=True),
        _descriptor(
            population="raw_inventory", sample_kind="negative_control", is_control=False
        ),
        _descriptor(
            population="raw_inventory", sample_kind="environmental", is_control=None
        ),
        _descriptor(population="new_population"),
        _descriptor(population="raw_inventory", assignment_method="new_method"),
    ],
)
def test_raw_descriptor_cannot_invent_method_population_or_control_status(value):
    with pytest.raises(ValueError):
        EDNADescriptor.model_validate(value)


def _metadata():
    return edna_fixture(10)[0].model_dump(mode="json")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda x: x.update(schema_version="catalogue-edna-dataset-v2"),
        lambda x: x.update(family="metagenome"),
        lambda x: x.update(extra="reject"),
        lambda x: x["descriptor"].update(
            population="scientific",
            assignment_method="qcauto_target",
            sample_kind="environmental",
            is_control=False,
        ),
        lambda x: x.update(collection_id=x["dataset_id"]),
        lambda x: x.update(dataset_id="root:data"),
        lambda x: x.update(collection_id="c12:provider:shadow"),
        lambda x: x.update(tables=x["tables"][:-1]),
        lambda x: x["tables"][0].update(name="assays"),
        lambda x: x["tables"][0].update(object_id=x["tables"][1]["object_id"]),
        lambda x: x["tables"][0].update(row_count=True),
        lambda x: x["tables"][0].update(row_count=-1),
        lambda x: x["tables"][0].update(object_id=None),
        lambda x: x["tables"][0].update(completeness="unavailable"),
        lambda x: x.update(related_ids=[x["dataset_id"]]),
        lambda x: x.update(related_ids=["other:link", "other:link"]),
    ],
)
def test_dataset_contract_rejects_ambiguous_or_contradictory_frozen_bindings(mutate):
    value = _metadata()
    mutate(value)
    with pytest.raises(ValueError):
        EDNADataset.model_validate(value)


def test_retained_occurrences_cannot_lose_frozen_classifications():
    value = _metadata()
    table = next(item for item in value["tables"] if item["name"] == "classifications")
    table.update(
        object_id=None,
        row_count=None,
        availability={"status": "unavailable", "reason": "No retained classifications"},
        completeness="unavailable",
    )
    with pytest.raises(ValueError, match="frozen classifications"):
        EDNADataset.model_validate(value)


@pytest.mark.parametrize("state", ["unknown", "unavailable"])
def test_absent_tables_retain_unknown_count_instead_of_fabricated_zero(state):
    value = _metadata()
    for table in value["tables"]:
        table.update(
            object_id=None,
            row_count=None,
            availability={
                "status": state,
                "reason": "No retained canonical source bytes",
            },
            completeness=state,
        )
    parsed = EDNADataset.model_validate(value)
    assert all(table.row_count is None for table in parsed.tables)
    value["tables"][0]["row_count"] = 0
    with pytest.raises(ValueError):
        EDNADataset.model_validate(value)


def test_available_empty_tables_are_explicit_known_zero_not_missing():
    metadata, frames = edna_fixture(0)
    assert all(
        table.row_count == 0 and table.availability.status == "available"
        for table in metadata.tables
    )
    assert set(frames) == set(TABLE_COLUMNS)
    assert all(frame.empty for frame in frames.values())


def test_logical_inputs_retain_zero_missing_source_methods_and_classifications():
    metadata, frames = edna_fixture(10)
    assert metadata.descriptor.population == "raw_inventory"
    assert {role: len(frame) for role, frame in frames.items()} == {
        "occurrences": 10,
        "assays": 10,
        "classifications": 10,
        "detections": 35,
    }
    classes = frames["classifications"]
    assert classes.loc[1, ["sample_kind", "is_control"]].tolist() == [
        "negative_control",
        True,
    ]
    assert classes.loc[2, ["sample_kind", "is_control"]].tolist() == ["unknown", None]
    detections = frames["detections"]
    first = detections.iloc[0]
    assert first.read_count == first.copies_per_ml == 0
    assert first.concentration_status == "reported"
    assert set(detections.concentration_status) == {
        "reported",
        "missing",
        "column_absent",
    }
    assert (
        len(set(detections[detections.assay_id == first.assay_id].sequence_sha256)) == 1
    )
    empty = json.loads(frames["assays"].iloc[6].community_availability_json)
    assert set(empty) == set(RAW_METHODS)
    assert all(item["row_count"] == 0 for item in empty.values())
    assert "qcauto_95pct_3nn_target" not in json.loads(
        frames["assays"].iloc[7].community_availability_json
    )


def test_portable_logical_examples_preserve_source_column_order_and_metadata():
    examples = json.loads((ROOT / "schema/edna_catalogue_examples.json").read_text())
    assert examples["expected"]["unavailable_count"] is None
    for example in examples["datasets"]:
        metadata = EDNADataset.model_validate(example["metadata"])
        for role, records in example["table_rows"].items():
            frame = pd.DataFrame(records, columns=TABLE_COLUMNS[role])
            table = next(table for table in metadata.tables if table.name == role)
            assert len(frame) == table.row_count


def test_portable_examples_round_trip_explicit_parquet_and_c09(tmp_path):
    from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
    from ingestion.edna_catalogue_inputs import load_dataset
    from schema.edna_catalogue_fixtures import seal_edna_fixture

    examples = json.loads((ROOT / "schema/edna_catalogue_examples.json").read_text())
    datasets = []
    for example in examples["datasets"]:
        metadata = EDNADataset.model_validate(example["metadata"])
        frames = {
            role: pd.DataFrame(records, columns=TABLE_COLUMNS[role], dtype=object)
            for role, records in example["table_rows"].items()
        }
        datasets.append((metadata, frames))
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda manifest: True
    )
    snapshot = seal_edna_fixture(store, datasets)
    manifest, contents = store.read(snapshot)
    observed = []
    for obj in manifest.objects:
        if obj.role != "canonical_rows":
            continue
        loaded = load_dataset(manifest, contents, obj)
        observed.append(loaded.metadata.dataset_id)
        for table in loaded.metadata.tables:
            if table.object_id is None:
                assert table.row_count is None
                assert table.name not in loaded.tables
            else:
                assert len(loaded.tables[table.name]) == table.row_count
    assert len(observed) == 3
    assert store.latest() == (None, 0)
