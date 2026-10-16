"""Explicit, bounded C09 exports of frozen relational canonical eDNA rows.

Only supplied immutable bytes and metadata are consumed. Source availability,
classification and identity assertions are retained, never discovered or approved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
from io import BytesIO
import json
import math
import re
import time

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ingestion.catalogue_snapshot_capture import CapturedSource, SourceExportRequirement
from ingestion.immutable_bundle import canonical_bytes
from preprocessing.anemone_classification import (
    MAX_REVIEW_BYTES,
    validate_sample_classification,
    validate_sample_review_lineage,
)
from preprocessing.edna_taxonomy import SOURCE_RANKS, deepest_resolved_assignment
from schema.catalogue_snapshot import (
    MAX_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_OBJECTS,
    SnapshotManifest,
    SnapshotObject,
)
from schema.context_catalogue import _finite_json
from schema.edna_catalogue import (
    ADAPTER_VERSION,
    DATASET_VERSION,
    RAW_METHODS,
    TABLE_COLUMNS,
    TABLE_VERSION,
    EDNADataset,
    EDNATable,
)

MAX_ROWS = 2_000_000
MAX_DECODED_BYTES = 512 * 1024 * 1024
CLASSIFICATION_STATE_VERSION = "catalogue-edna-classification-state-v1"
KEYS = {
    "occurrences": "sample_id",
    "classifications": "sample_id",
    "assays": "assay_id",
    "detections": "detection_id",
}
_NULLABLE = {
    "occurrences": {
        "provider_locus", "provider_team", "collection_date_utc",
        "temporal_precision", "lat", "lon", "physical_sample_id",
    },
    "classifications": {"is_control", "classification_review_json"},
    "assays": {
        "target_gene", "primer_set", "sequencing_method", "library_layout",
        "instrument_model", "community_availability_json",
    },
    "detections": {"copies_per_ml", "assigned_taxon_name", "assigned_taxon_rank"},
}
_TYPES = {
    "active": pa.bool_(), "is_control": pa.bool_(), "read_count": pa.int64(),
    "lat": pa.float64(), "lon": pa.float64(), "copies_per_ml": pa.float64(),
}
ARROW_SCHEMAS = {
    role: pa.schema([
        pa.field(name, _TYPES.get(name, pa.string()), nullable=name in _NULLABLE[role])
        for name in columns
    ])
    for role, columns in TABLE_COLUMNS.items()
}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_JSON_LIMITS = {
    "classification_review_json": MAX_REVIEW_BYTES,
    "community_availability_json": 64 * 1024,
    "taxonomy_json": 64 * 1024,
}


class AdapterUnavailable(ValueError):
    """A requested complete operation cannot run on the supplied frozen inputs."""


EDNAUnavailable = AdapterUnavailable


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate frozen eDNA JSON key")
        result[key] = value
    return result


def _json_object(value: str, *, label: str, limit: int = 64 * 1024):
    if type(value) is not str or len(value.encode("utf-8")) > limit:
        raise ValueError(f"Bounded frozen eDNA {label} JSON required")
    result = json.loads(value, object_pairs_hook=_unique)
    _finite_json(result)
    if type(result) is not dict:
        raise ValueError(f"Frozen eDNA {label} must be an object")
    return result


def dataset_metadata(data: bytes) -> EDNADataset:
    if type(data) is not bytes or len(data) > MAX_MANIFEST_BYTES:
        raise ValueError("Bounded frozen eDNA metadata bytes required")
    raw = json.loads(data.decode("utf-8"), object_pairs_hook=_unique)
    _finite_json(raw)
    return EDNADataset.model_validate(raw)


def parse_community_availability(value: str | None) -> dict:
    """Retain canonical source-file availability, including available zero rows.

    A missing declaration does not prove an available empty source file. Actual
    retained detections can independently establish method availability through
    the shared canonical policy. A retained null row_count stays unknown.
    """
    if value is None:
        return {}
    result = _json_object(value, label="community availability")
    if not set(result) <= set(RAW_METHODS):
        raise ValueError("Unsupported raw eDNA assignment method availability")
    for item in result.values():
        if type(item) is not dict or set(item) != {
            "status", "source_file_id", "source_snapshot_id", "row_count",
        }:
            raise ValueError("Exact canonical source-backed availability required")
        if item["status"] != "available":
            raise ValueError("Canonical availability entries require retained source files")
        for name in ("source_file_id", "source_snapshot_id"):
            if type(item[name]) is not str or not _SHA256.fullmatch(item[name]):
                raise ValueError("Availability requires exact source identity hashes")
        count = item["row_count"]
        if count is not None and (type(count) is not int or not 0 <= count <= 2**63 - 1):
            raise ValueError("Availability row count must be nonnegative int64 or unknown")
    return result


def _validate_primitives(role, records):
    for row in records:
        for field in ARROW_SCHEMAS[role]:
            value = row[field.name]
            if value is None:
                if not field.nullable:
                    raise ValueError("Null in required frozen eDNA column")
            elif field.type == pa.string():
                limit = _JSON_LIMITS.get(field.name, 4000)
                if type(value) is not str or not value.strip() or len(value.encode("utf-8")) > limit:
                    raise ValueError("Invalid frozen eDNA text value")
            elif field.type == pa.bool_():
                if type(value) is not bool:
                    raise ValueError("Frozen eDNA flags require primitive booleans")
            elif field.type == pa.int64():
                if type(value) is not int or not 0 <= value <= 2**63 - 1:
                    raise ValueError("Frozen eDNA counts require nonnegative primitive int64")
            elif type(value) not in {int, float} or not math.isfinite(value):
                raise ValueError("Frozen eDNA numbers require finite primitive values")


def _frame_records(role, frame):
    records = frame.to_dict("records")
    for row in records:
        for name in _NULLABLE[role]:
            value = row[name]
            if value is pd.NA or (type(value) is float and math.isnan(value)):
                row[name] = None
    return records


def _decoded_budget(value):
    if value is None:
        return MAX_DECODED_BYTES
    if type(value) is not int or value < 0:
        raise ValueError("Frozen eDNA decoded budget must be a nonnegative integer")
    return min(MAX_DECODED_BYTES, value)


def parse_table(spec: EDNATable, data: bytes, *, decoded_budget: int | None = None) -> pd.DataFrame:
    if type(data) is not bytes or len(data) > MAX_BYTES:
        raise ValueError("Bounded frozen eDNA table bytes required")
    budget = _decoded_budget(decoded_budget)
    try:
        parquet = pq.ParquetFile(BytesIO(data))
        metadata = parquet.metadata
        if metadata.num_rows > MAX_ROWS or metadata.num_rows != spec.row_count:
            raise ValueError("Frozen eDNA row count/budget mismatch")
        if sum(metadata.row_group(i).total_byte_size for i in range(metadata.num_row_groups)) > budget:
            raise ValueError("Frozen eDNA decoded budget exceeded")
        for group in range(metadata.num_row_groups):
            for column in range(metadata.num_columns):
                if not set(metadata.row_group(group).column(column).encodings) <= {"PLAIN", "RLE", "BIT_PACKED"}:
                    raise ValueError("Unsupported expanding eDNA Parquet encoding")
        if not parquet.schema_arrow.equals(ARROW_SCHEMAS[spec.name], check_metadata=False):
            raise ValueError("eDNA Parquet columns/types/nullability differ from frozen schema")
        table = parquet.read(use_threads=False)
        if table.nbytes > budget:
            raise ValueError("Frozen eDNA decoded budget exceeded")
        records = table.to_pylist()
    except (pa.ArrowException, OSError) as exc:
        raise ValueError("Invalid frozen eDNA Parquet") from exc
    _validate_primitives(spec.name, records)
    frame = pd.DataFrame(records, columns=TABLE_COLUMNS[spec.name], dtype=object)
    if frame[KEYS[spec.name]].duplicated().any():
        raise ValueError("Frozen eDNA row identities must be unique")
    frame.attrs["decoded_bytes"] = table.nbytes
    return frame


def _collection_time(value, precision):
    if value is None:
        if precision not in {None, "unknown"}:
            raise ValueError("Missing eDNA dates require unknown retained precision")
        return
    patterns = {
        "year": r"[0-9]{4}", "month": r"[0-9]{4}-[0-9]{2}",
        "date": r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
        "day": r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
    }
    if precision in patterns:
        if not re.fullmatch(patterns[precision], value):
            raise ValueError("eDNA date differs from retained temporal precision")
        date.fromisoformat(value + ("-01-01" if precision == "year" else "-01" if precision == "month" else ""))
        return
    if precision != "datetime" or "T" not in value:
        raise ValueError("Unsupported or invented eDNA date precision")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() != timezone.utc.utcoffset(instant):
        raise ValueError("Canonical eDNA UTC instant requires an explicit zero offset")
    instant.astimezone(timezone.utc)


def validate_rows(dataset: EDNADataset, tables: dict[str, pd.DataFrame]):
    specs = {item.name: item for item in dataset.tables}
    expected = {name for name, spec in specs.items() if spec.object_id is not None}
    if set(tables) != expected:
        raise ValueError("Exact declared frozen eDNA table frames required")
    records = {}
    row_total = decoded = 0
    for name, frame in tables.items():
        if list(frame.columns) != list(TABLE_COLUMNS[name]) or len(frame) != specs[name].row_count:
            raise ValueError("Frozen eDNA table columns/count differ from metadata")
        row_total += len(frame)
        if row_total > MAX_ROWS:
            raise ValueError("Cumulative frozen eDNA row budget exceeded")
        rows = _frame_records(name, frame)
        _validate_primitives(name, rows)
        arrow_table = pa.Table.from_pylist(rows, schema=ARROW_SCHEMAS[name])
        decoded += arrow_table.nbytes
        if decoded > MAX_DECODED_BYTES:
            raise ValueError("Cumulative frozen eDNA decoded budget exceeded")
        if len({row[KEYS[name]] for row in rows}) != len(rows):
            raise ValueError("Duplicate frozen eDNA row identity")
        for row in rows:
            for identity in ({KEYS[name], "sample_id", "assay_id", "source_occurrence_id"} & set(row)):
                if not _SHA256.fullmatch(row[identity]):
                    raise ValueError("Frozen eDNA canonical identities require exact SHA-256")
            if "scientific_content_sha256" in row and not _SHA256.fullmatch(row["scientific_content_sha256"]):
                raise ValueError("Frozen eDNA records require exact scientific SHA-256")
        records[name] = rows

    occurrences = {row["sample_id"]: row for row in records.get("occurrences", [])}
    classifications = {row["sample_id"]: row for row in records.get("classifications", [])}
    assays = {row["assay_id"]: row for row in records.get("assays", [])}
    if set(classifications) != set(occurrences):
        raise ValueError("Frozen classifications must identify every occurrence exactly once")
    occurrence_ids = set()
    for sample_id, row in occurrences.items():
        if row["source_occurrence_id"] in occurrence_ids:
            raise ValueError("Duplicate frozen source occurrence identity")
        occurrence_ids.add(row["source_occurrence_id"])
        if (row["provider"], row["provider_locus"], row["provider_team"], row["provider_project_id"]) != (
            dataset.provider, dataset.provider_locus, dataset.provider_team, dataset.provider_project_id,
        ):
            raise ValueError("Occurrence provider/project ownership differs from dataset")
        if not _SHA256.fullmatch(row["source_snapshot_id"]):
            raise ValueError("Occurrence requires exact source snapshot SHA-256")
        _collection_time(row["collection_date_utc"], row["temporal_precision"])
        lat, lon = row["lat"], row["lon"]
        if (lat is None) != (lon is None) or (lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180)):
            raise ValueError("Frozen eDNA coordinates require a valid paired location")
        if row["identity_status"] == "unresolved_physical_sample":
            if row["physical_sample_id"] is not None:
                raise ValueError("Unresolved occurrences cannot assert physical sample identity")
        elif row["identity_status"] != "resolved_physical_sample" or row["physical_sample_id"] is None:
            raise ValueError("Physical sample identity requires an explicit supported status")
        classification = classifications[sample_id]
        if (classification["source_snapshot_id"], classification["provider_sample_id"]) != (
            row["source_snapshot_id"], row["provider_sample_id"],
        ):
            raise ValueError("Classification source identity differs from occurrence")
        validate_sample_classification(classification["sample_kind"], classification["is_control"])
        validate_sample_review_lineage(
            classification["classification_review_json"], sample_kind=classification["sample_kind"],
            is_control=classification["is_control"], classification_basis=classification["classification_basis"],
            source_snapshot_id=row["source_snapshot_id"], provider_sample_id=row["provider_sample_id"],
        )

    availability = {}
    for assay_id, row in assays.items():
        sample = occurrences.get(row["sample_id"])
        if sample is None:
            raise ValueError("Frozen assay refers to an unknown occurrence")
        methods = parse_community_availability(row["community_availability_json"])
        if any(item["source_snapshot_id"] != sample["source_snapshot_id"] for item in methods.values()):
            raise ValueError("Assay availability differs from occurrence source snapshot")
        availability[assay_id] = methods

    retained_kinds = {row["sample_kind"] for row in classifications.values()}
    if dataset.descriptor.sample_kind != "mixed" and not retained_kinds <= {dataset.descriptor.sample_kind}:
        raise ValueError("eDNA descriptor classification contradicts retained raw inventory")
    retained_methods = {method for methods in availability.values() for method in methods} | {
        row["assignment_method"] for row in records.get("detections", [])
    }
    if dataset.descriptor.assignment_method != "mixed" and not retained_methods <= {dataset.descriptor.assignment_method}:
        raise ValueError("eDNA descriptor method contradicts retained source availability")

    counts, sequence_keys = {}, set()
    for row in records.get("detections", []):
        if row["assay_id"] not in assays:
            raise ValueError("Frozen detection refers to an unknown assay")
        method = row["assignment_method"]
        if method not in RAW_METHODS or row["target_status"] != ("nontarget" if method.endswith("_nontarget") else "target"):
            raise ValueError("Frozen detection method/target status mismatch")
        key = (row["assay_id"], method)
        counts[key] = counts.get(key, 0) + 1
        if not _SHA256.fullmatch(row["sequence_sha256"]):
            raise ValueError("Frozen sequence identity requires exact SHA-256")
        sequence_key = (*key, row["sequence_sha256"])
        if sequence_key in sequence_keys:
            raise ValueError("Duplicate assay/method/sequence identity")
        sequence_keys.add(sequence_key)
        copies = row["copies_per_ml"]
        if row["concentration_status"] == "reported":
            if copies is None or copies < 0:
                raise ValueError("Reported concentration requires a nonnegative value")
        elif row["concentration_status"] not in {"missing", "column_absent"} or copies is not None:
            raise ValueError("Missing/absent concentration must retain an unknown value")
        taxonomy = _json_object(row["taxonomy_json"], label="taxonomy")
        if not set(taxonomy) <= set(SOURCE_RANKS) or any(
            value is not None and (type(value) is not str or not value.strip() or len(value) > 4000)
            for value in taxonomy.values()
        ):
            raise ValueError("Frozen taxonomy requires retained source rank labels")
        if deepest_resolved_assignment(taxonomy) != (row["assigned_taxon_name"], row["assigned_taxon_rank"]):
            raise ValueError("Frozen assigned taxonomy contradicts shared source interpretation")
    if "detections" in records and specs["detections"].completeness == "complete":
        for assay_id, methods in availability.items():
            for method, item in methods.items():
                if item["row_count"] is not None and item["row_count"] != counts.get((assay_id, method), 0):
                    raise ValueError("Source method row count differs from complete detections")


@dataclass
class DatasetInputs:
    metadata: EDNADataset
    tables: dict[str, pd.DataFrame]
    objects: tuple[SnapshotObject, ...]


def _verified_bytes(item, contents):
    data = contents.get(item.object_id)
    if type(data) is not bytes or len(data) != item.size_bytes or hashlib.sha256(data).hexdigest() != item.sha256:
        raise ValueError("Frozen eDNA object bytes/hash mismatch")
    return data


def _classification_state(dataset):
    table = next(item for item in dataset.tables if item.name == "classifications")
    return canonical_bytes({
        "schema_version": CLASSIFICATION_STATE_VERSION,
        "dataset_id": dataset.dataset_id, "source_id": dataset.source_id,
        "table": table.model_dump(mode="json"),
        "qualification": dataset.qualification,
    })


def load_dataset(manifest: SnapshotManifest, contents, obj: SnapshotObject, *, decoded_budget: int | None = None) -> DatasetInputs:
    budget = _decoded_budget(decoded_budget)
    if obj not in manifest.objects or (obj.role, obj.schema_version, obj.source_family) != (
        "canonical_rows", DATASET_VERSION, "edna_metabarcoding",
    ):
        raise ValueError("Frozen eDNA metadata role/schema/ownership mismatch")
    dataset = dataset_metadata(_verified_bytes(obj, contents))
    if (dataset.dataset_id, dataset.source_id) != (obj.dataset_id, obj.source_id):
        raise ValueError("Frozen eDNA metadata identity differs from sealed ownership")
    objects = {item.object_id: item for item in manifest.objects if item.dataset_id == dataset.dataset_id}
    expected = {obj.object_id} | {item.object_id for item in dataset.tables if item.object_id is not None}
    classifications = next(item for item in dataset.tables if item.name == "classifications")
    state_id = f"{dataset.dataset_id}:classification-state"
    if classifications.object_id is None:
        expected.add(state_id)
    if set(objects) != expected:
        raise ValueError("Exact frozen eDNA dataset object membership required")
    for item in objects.values():
        if (item.source_id, item.source_family, item.operation_id, item.operation_version) != (
            dataset.source_id, "edna_metabarcoding", f"c12:edna_metabarcoding:{item.role}", ADAPTER_VERSION,
        ):
            raise ValueError("Frozen eDNA source/operation ownership mismatch")
    tables = {}
    if sum(item.row_count or 0 for item in dataset.tables) > MAX_ROWS:
        raise ValueError("Cumulative frozen eDNA row budget exceeded")
    decoded = 0
    for spec in dataset.tables:
        if spec.object_id is None:
            continue
        item = objects[spec.object_id]
        if (item.role, item.schema_version) != (spec.name, TABLE_VERSION):
            raise ValueError("Frozen eDNA table role/schema mismatch")
        tables[spec.name] = parse_table(spec, _verified_bytes(item, contents), decoded_budget=budget - decoded)
        decoded += tables[spec.name].attrs["decoded_bytes"]
    if classifications.object_id is None:
        item = objects[state_id]
        if (item.role, item.schema_version) != ("classifications", CLASSIFICATION_STATE_VERSION) or _verified_bytes(item, contents) != _classification_state(dataset):
            raise ValueError("Absent classifications require exact frozen qualification metadata")
    validate_rows(dataset, tables)
    return DatasetInputs(dataset, tables, tuple(objects.values()))


def encode_table(spec: EDNATable, frame: pd.DataFrame) -> bytes:
    if len(frame) > MAX_ROWS or list(frame.columns) != list(TABLE_COLUMNS[spec.name]):
        raise ValueError("Frozen eDNA row budget/exact columns required")
    records = _frame_records(spec.name, frame)
    _validate_primitives(spec.name, records)
    table = pa.Table.from_pylist(records, schema=ARROW_SCHEMAS[spec.name])
    if table.nbytes > MAX_DECODED_BYTES:
        raise ValueError("Frozen eDNA decoded budget exceeded")
    table = table.sort_by([(KEYS[spec.name], "ascending")])
    stream = BytesIO()
    pq.write_table(table, stream, compression="zstd", version="2.6", use_dictionary=False)
    payload = stream.getvalue()
    parse_table(spec, payload)
    return payload


def dataset_exports(dataset: EDNADataset, frames: dict[str, pd.DataFrame], *, generation: str) -> CapturedSource:
    dataset = EDNADataset.model_validate(dataset.model_dump(mode="json"))
    validate_rows(dataset, frames)
    metadata_id = f"{dataset.dataset_id}:metadata"
    contents = {metadata_id: canonical_bytes(dataset.model_dump(mode="json"))}
    descriptors = [(metadata_id, "canonical_rows", DATASET_VERSION)]
    if len(contents[metadata_id]) > MAX_MANIFEST_BYTES:
        raise ValueError("Frozen eDNA metadata byte budget exceeded")
    for spec in dataset.tables:
        if spec.object_id is None:
            if spec.name == "classifications":
                identity = f"{dataset.dataset_id}:classification-state"
                contents[identity] = _classification_state(dataset)
                descriptors.append((identity, spec.name, CLASSIFICATION_STATE_VERSION))
            continue
        if spec.object_id in contents:
            raise ValueError("Frozen eDNA object identities must be distinct")
        contents[spec.object_id] = encode_table(spec, frames[spec.name])
        descriptors.append((spec.object_id, spec.name, TABLE_VERSION))
    if len(descriptors) != len(contents) or sum(map(len, contents.values())) > MAX_BYTES:
        raise ValueError("Frozen eDNA export identity/byte budget exceeded")
    objects = tuple(SnapshotObject(
        object_id=identity, dataset_id=dataset.dataset_id, source_id=dataset.source_id,
        source_family="edna_metabarcoding", role=role, schema_version=version,
        sha256=hashlib.sha256(contents[identity]).hexdigest(), size_bytes=len(contents[identity]),
        operation_id=f"c12:edna_metabarcoding:{role}", operation_version=ADAPTER_VERSION,
        provenance={"source_generation": generation, "content_sha256": hashlib.sha256(contents[identity]).hexdigest(), "references": [dataset.qualification]},
    ) for identity, role, version in descriptors)
    return CapturedSource(objects, contents)


def frozen_source_requirement(datasets, *, source_generation: str) -> SourceExportRequirement:
    """Freeze explicitly supplied datasets; bind them to their exact source head."""
    items = tuple(datasets)
    if not items or len({dataset.source_id for dataset, _ in items}) != 1:
        raise ValueError("One explicit nonempty eDNA source registration required")
    source_id = items[0][0].source_id
    objects, contents, qualifiers = [], {}, []
    rows = decoded = 0
    for dataset, frames in items:
        captured = dataset_exports(dataset, frames, generation=source_generation)
        registered_versions = {item.role: item.schema_version for item in objects}
        if any(
            item.role in registered_versions and registered_versions[item.role] != item.schema_version
            for item in captured.objects
        ):
            raise ValueError("C09 source registration requires one schema version per role; separate classification states")
        if set(contents) & set(captured.contents):
            raise ValueError("Duplicate frozen eDNA source object identity")
        for spec in dataset.tables:
            if spec.object_id is not None:
                frame = parse_table(spec, captured.contents[spec.object_id])
                rows += len(frame)
                decoded += frame.attrs["decoded_bytes"]
        if rows > MAX_ROWS or decoded > MAX_DECODED_BYTES:
            raise ValueError("Cumulative frozen eDNA source row/decoded budget exceeded")
        objects.extend(captured.objects)
        contents.update(captured.contents)
        qualifiers.append(dataset.qualification)
        if len(objects) > MAX_OBJECTS or sum(map(len, contents.values())) > MAX_BYTES:
            raise ValueError("Frozen eDNA registration exceeds C09 capture bounds")
    captured = CapturedSource(tuple(objects), contents)

    def export(connection, heads, deadline):
        if type(deadline) not in {int, float} or not math.isfinite(deadline) or time.monotonic() >= deadline:
            raise AdapterUnavailable("Frozen eDNA export deadline expired/invalid")
        if heads.source_generation(source_id) != source_generation:
            raise AdapterUnavailable("Frozen eDNA generation differs from source head; rebuild registration")
        return CapturedSource(captured.objects, captured.contents)

    return SourceExportRequirement(
        source_id=source_id, source_family="edna_metabarcoding",
        schema_versions={obj.role: obj.schema_version for obj in captured.objects},
        operation_versions={obj.role: obj.operation_version for obj in captured.objects},
        operation_ids={obj.role: obj.operation_id for obj in captured.objects},
        exporter=export, capture_method="c12-frozen-edna-parquet-v1",
        qualifiers=tuple(dict.fromkeys(qualifiers)),
    )


def frozen_export_requirement(dataset: EDNADataset, frames: dict[str, pd.DataFrame], *, source_generation: str) -> SourceExportRequirement:
    return frozen_source_requirement([(dataset, frames)], source_generation=source_generation)
