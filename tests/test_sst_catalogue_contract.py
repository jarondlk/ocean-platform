"""C11 product/calendar contracts and portable byte-bound logical examples."""

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.sst_catalogue_inputs import load_dataset
from schema.sst_catalogue import (
    SSTDataset,
    SSTSampling,
    SSTSupport,
    TABLE_COLUMNS,
    sst_product_node_id,
)
from schema.sst_catalogue_fixtures import seal_sst_fixture, sst_fixture
from scripts.export_sst_catalogue import generated_files

ROOT = Path(__file__).resolve().parents[1]


def test_generated_schema_and_logical_examples_are_current():
    for path, expected in generated_files().items():
        assert path.read_text() == expected


def test_portable_examples_round_trip_explicit_parquet_and_c09(tmp_path):
    examples = json.loads((ROOT / "schema/sst_catalogue_examples.json").read_text())
    datasets = []
    for example in examples["datasets"]:
        metadata = SSTDataset.model_validate(example["metadata"])
        frames = {
            role: pd.DataFrame(rows) for role, rows in example["table_rows"].items()
        }
        # JSON object ordering is irrelevant; restore the source-owned column order.
        frames = {
            role: frame[list(TABLE_COLUMNS)].astype(
                {"valid_ocean_pixels": "Int64", "ocean_pixels": "Int64"}
            )
            for role, frame in frames.items()
        }
        datasets.append((metadata, frames))
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda manifest: True
    )
    snapshot = seal_sst_fixture(store, datasets)
    manifest, contents = store.read(snapshot)
    observed = {}
    for obj in manifest.objects:
        if obj.role != "dataset_metadata":
            continue
        loaded = load_dataset(manifest, contents, obj)
        metadata = loaded.metadata
        if metadata.table.object_id is None:
            assert metadata.table.row_count is None
            assert metadata.table.availability.status == "unavailable"
            assert loaded.tables == {}
            continue
        rows = loaded.tables["observations"]
        accepted = rows[(rows.status == "valid") & rows.value.notna()]
        observed[metadata.dataset_id] = metadata.processing_generation
        expected = examples["expected"]
        assert len(rows) == expected["raw_rows_per_retained_dataset"]
        assert len(accepted) == expected["eligible_nonnull_observations"]
        assert accepted.value.sum() == expected["eligible_sum"]
        assert accepted.value.mean() == expected["eligible_mean"]
        assert (accepted.value == 0).sum() == expected["measured_zero_observations"]
        assert (rows.status == "invalid").sum() == expected["invalid_observations"]
        assert (rows.status == "excluded").sum() == expected["excluded_observations"]
        assert rows.value.isna().sum() == expected["missing_value_observations"]
        quality = ["valid_fraction", "valid_ocean_pixels", "ocean_pixels"]
        assert rows.loc[0, quality].tolist() == [0.9, 90, 100]
        assert rows.loc[2, quality].tolist() == [0.5, 50, 100]
        assert all(rows.loc[1, name] is None for name in quality)
    assert set(observed.values()) == {"final", "interim"}
    assert len(observed) == 4
    assert store.latest() == (None, 0)


@pytest.mark.parametrize(
    "changes",
    [
        {"north": 38.0},
        {"south": -91.0},
        {"east": 181.0},
        {"west": 170.0, "east": -170.0},
        {"north": float("nan")},
        {"east": True},
    ],
)
def test_geographic_support_rejects_invalid_or_wrapping_scope(changes):
    with pytest.raises(ValueError):
        SSTSupport.model_validate(
            {"south": 38.0, "north": 39.0, "west": 141.0, "east": 142.0, **changes}
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"start": "2023-02-29"},
        {"end": "2024-02-26"},
        {"start": "2024-02-27T00:00:00Z"},
        {"frequency": "hourly"},
        {"start": "1900-01-01", "end": "2100-01-01"},
    ],
)
def test_sampling_is_bounded_real_calendar_with_actual_day_precision(changes):
    with pytest.raises(ValueError):
        SSTSampling.model_validate(
            {"start": "2024-02-27", "end": "2024-03-01", "calendar": "UTC", **changes}
        )


def test_leap_day_sampling_retains_declared_calendar_without_inventing_instants():
    sampling = SSTSampling(start="2024-02-28", end="2024-03-01", calendar="Asia/Tokyo")
    assert sampling.model_dump()["start"] == "2024-02-28"
    assert sampling.calendar == "Asia/Tokyo"


def _metadata():
    return sst_fixture(6)[0].model_dump(mode="json")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda x: x.update(unrecognized="not accepted"),
        lambda x: x.update(product_node_id="wrong-product"),
        lambda x: x.update(collection_id=x["dataset_id"]),
        lambda x: x.update(dataset_id="root:data"),
        lambda x: x.update(collection_id="c11:source:synthetic-sst"),
        lambda x: x.update(dataset_id=x["product_node_id"]),
        lambda x: x.update(related_ids=[x["dataset_id"]]),
        lambda x: x["descriptor"].update(spatial_resolution=None),
        lambda x: x["descriptor"].update(spatial_resolution=True),
        lambda x: x["descriptor"].update(spatial_role="native_grid"),
        lambda x: x["sampling"].update(calendar="Asia/Tokyo"),
        lambda x: x.update(temporal_statistic="instant_retrieval"),
        lambda x: x.update(measurement_type="satellite_retrieval"),
        lambda x: x["table"].update(row_count=True),
        lambda x: x["table"].update(object_id=None),
        lambda x: x["table"].update(completeness="unavailable"),
    ],
)
def test_products_do_not_acquire_fabricated_identity_resolution_sampling_or_counts(
    mutation,
):
    value = _metadata()
    mutation(value)
    with pytest.raises(ValueError):
        SSTDataset.model_validate(value)


def test_mur_version_cannot_be_relabelled_even_with_new_canonical_identity():
    value = _metadata()
    value["processing_generation"] = "interim"
    value["product_node_id"] = sst_product_node_id(
        value["source_id"], "mur", "04.1", "interim"
    )
    with pytest.raises(ValueError, match="MUR version"):
        SSTDataset.model_validate(value)


def test_same_product_version_from_different_source_or_generation_has_distinct_identity():
    base = sst_product_node_id("source-a", "mur", "04.1", "final")
    assert base == sst_product_node_id("source-a", "mur", "04.1", "final")
    assert (
        len(
            {
                base,
                sst_product_node_id("source-b", "mur", "04.1", "final"),
                sst_product_node_id("source-a", "mur", "04.1nrt", "interim"),
            }
        )
        == 3
    )


@pytest.mark.parametrize("status", ["unknown", "unavailable"])
def test_missing_table_keeps_unknown_count_distinct_from_measured_zero(status):
    value = _metadata()
    value["table"].update(
        object_id=None,
        row_count=None,
        availability={"status": status, "reason": "No retained observation bytes"},
        completeness=status,
    )
    parsed = SSTDataset.model_validate(value)
    assert parsed.table.row_count is None
    assert parsed.table.availability.status == status
    contradictory = copy.deepcopy(value)
    contradictory["table"]["row_count"] = 0
    with pytest.raises(ValueError):
        SSTDataset.model_validate(contradictory)


def test_empty_retained_table_is_known_zero_and_instant_observations_need_no_daily_contract():
    zero, _ = sst_fixture(0)
    assert zero.table.row_count == 0 and zero.table.availability.status == "available"
    value = _metadata()
    value["descriptor"]["product_id"] = "synthetic-instant"
    value["descriptor"]["spatial_role"] = "coarse_context"
    value["observation_entity"] = "grid_observation"
    value["temporal_statistic"] = "instant_retrieval"
    value["measurement_type"] = "satellite_retrieval"
    value["observation_precision"] = "datetime"
    value["sampling"] = None
    value["product_node_id"] = sst_product_node_id(
        value["source_id"], "synthetic-instant", "04.1", "final"
    )
    assert SSTDataset.model_validate(value).sampling is None


@pytest.mark.parametrize("role", ["dataset_id", "collection_id", "table"])
@pytest.mark.parametrize(
    "identity", ["c11:sst", "c11:sst:shadow", "c11:reference:metadata:shadow"]
)
def test_source_records_cannot_shadow_generated_hierarchy_or_crosslinks(role, identity):
    value = _metadata()
    if role == "table":
        value["table"]["object_id"] = identity
    else:
        value[role] = identity
    with pytest.raises(ValueError, match="nonreserved"):
        SSTDataset.model_validate(value)


@pytest.mark.parametrize(
    "statistic,measurement",
    [
        ("instant_retrieval", "satellite_retrieval"),
        ("model_instant", "model_assimilation"),
    ],
)
def test_daily_summary_cannot_be_relabeled_instant_even_without_sampling(
    statistic, measurement
):
    value = _metadata()
    value.update(
        temporal_statistic=statistic, measurement_type=measurement, sampling=None
    )
    with pytest.raises(ValueError, match="daily temporal statistic"):
        SSTDataset.model_validate(value)


@pytest.mark.parametrize(
    "statistic,measurement",
    [
        ("instant_retrieval", "model_assimilation"),
        ("model_instant", "satellite_retrieval"),
    ],
)
def test_grid_instant_products_preserve_retrieval_versus_assimilated_measurement(
    statistic, measurement
):
    metadata, _ = sst_fixture(
        1, entity="grid_observation", sampling=False, precision="datetime"
    )
    value = metadata.model_dump(mode="json")
    value.update(temporal_statistic=statistic, measurement_type=measurement)
    with pytest.raises(ValueError, match="source measurement type"):
        SSTDataset.model_validate(value)


@pytest.mark.parametrize(
    "start,end,calendar",
    [
        ("9999-12-31", "9999-12-31", "UTC"),
        ("9999-12-31", "9999-12-31", "Asia/Tokyo"),
        ("0001-01-01", "0001-01-02", "Asia/Tokyo"),
    ],
)
def test_sampling_rejects_unrepresentable_utc_day_boundaries(start, end, calendar):
    with pytest.raises(ValueError, match="representable UTC"):
        SSTSampling(start=start, end=end, calendar=calendar)


def test_sampling_retains_extreme_but_representable_boundaries_and_related_crosslinks():
    assert (
        SSTSampling(start="0001-01-01", end="0001-01-02", calendar="UTC").start
        == "0001-01-01"
    )
    assert (
        SSTSampling(start="9999-12-30", end="9999-12-30", calendar="UTC").end
        == "9999-12-30"
    )
    value = _metadata()
    value["related_ids"] = ["c11:reference:metadata:valid-crosslink"]
    assert SSTDataset.model_validate(value).related_ids == value["related_ids"]


@pytest.mark.parametrize("generation", ["final", "interim"])
@pytest.mark.parametrize(
    "statistic,measurement",
    [
        ("instant_retrieval", "satellite_retrieval"),
        ("model_instant", "model_assimilation"),
        ("daily_mean", "satellite_in_situ_analysis"),
    ],
)
def test_known_mur_product_cannot_be_reinterpreted_as_retrieval_model_or_daily_mean(
    generation, statistic, measurement
):
    metadata, _ = sst_fixture(
        1, generation=generation, entity="grid_observation", sampling=False
    )
    value = metadata.model_dump(mode="json")
    value.update(temporal_statistic=statistic, measurement_type=measurement)
    with pytest.raises(ValueError, match="Known MUR products"):
        SSTDataset.model_validate(value)


def test_named_mur_foundation_alias_keeps_the_same_product_meaning():
    value = _metadata()
    value["descriptor"]["product_id"] = "mur_l4_foundation_sst"
    value["product_node_id"] = sst_product_node_id(
        value["source_id"], "mur_l4_foundation_sst", "04.1", "final"
    )
    assert (
        SSTDataset.model_validate(value).temporal_statistic
        == "daily_foundation_analysis"
    )
    value.update(temporal_statistic="daily_mean")
    with pytest.raises(ValueError, match="Known MUR products"):
        SSTDataset.model_validate(value)
