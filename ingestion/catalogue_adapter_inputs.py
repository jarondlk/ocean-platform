"""Verified C09-bound C10 metadata/Parquet inputs and explicit frozen exporters.

No configuration, mutable source path, database discovery or provider fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
from schema.catalogue_adapter import (
    ADAPTER_VERSION,
    DATASET_VERSION,
    KEYS,
    TABLE_VERSION,
    FrozenDataset,
    FrozenTable,
)
from schema.catalogue_snapshot import SnapshotManifest, SnapshotObject
from schema.context_catalogue import _finite_json
from schema.time_range import utc_time

MAX_ROWS = 2_000_000
MAX_DECODED_BYTES = 512 * 1024 * 1024
ARROW_TYPES = {
    "string": pa.string(),
    "number": pa.float64(),
    "integer": pa.int64(),
    "boolean": pa.bool_(),
}


class AdapterUnavailable(ValueError):
    """A complete scientifically supported operation cannot run on these inputs."""


def period(value, precision):
    """Validate retained precision; return intervals only for filter comparison."""
    if precision not in {"day", "month", "year", "datetime", "unknown"}:
        raise ValueError("Unknown per-record collection precision")
    if value is None:
        return None
    patterns = {"year": r"\d{4}", "month": r"\d{4}-\d{2}", "day": r"\d{4}-\d{2}-\d{2}"}
    if precision in patterns:
        if not isinstance(value, str) or not re.fullmatch(patterns[precision], value):
            raise ValueError("Collection date does not match declared precision")
        begin = utc_time(
            value
            + (
                "-01-01"
                if precision == "year"
                else "-01"
                if precision == "month"
                else ""
            )
        )
        if precision == "year":
            end = begin.replace(year=begin.year + 1)
        elif precision == "month":
            end = begin.replace(
                year=begin.year + (begin.month == 12),
                month=1 if begin.month == 12 else begin.month + 1,
            )
        else:
            from datetime import timedelta

            end = begin + timedelta(days=1)
        return begin, end
    if precision == "datetime":
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if "T" not in value or instant.tzinfo is None:
            raise ValueError("Collection instants require an explicit timezone")
        return utc_time(value), None
    raise ValueError("Unknown temporal precision cannot contain an invented date")


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate frozen metadata key")
        value[key] = item
    return value


def dataset_metadata(data: bytes) -> FrozenDataset:
    value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique)
    _finite_json(value)
    return FrozenDataset.model_validate(value)


def parse_table(spec: FrozenTable, data: bytes) -> pd.DataFrame:
    if type(data) is not bytes:
        raise ValueError("Frozen table bytes required")
    try:
        parquet = pq.ParquetFile(BytesIO(data))
        metadata = parquet.metadata
        if metadata.num_rows > MAX_ROWS or metadata.num_rows != spec.row_count:
            raise ValueError("Frozen table row count/limit mismatch")
        if (
            sum(
                metadata.row_group(i).total_byte_size
                for i in range(metadata.num_row_groups)
            )
            > MAX_DECODED_BYTES
        ):
            raise ValueError("Decoded Parquet budget exceeded")
        # Dictionary/prefix encodings can expand repeated strings far beyond
        # footer uncompressed sizes. The v1 canonical writer uses plain values.
        for group in range(metadata.num_row_groups):
            for column in range(metadata.num_columns):
                if not set(metadata.row_group(group).column(column).encodings) <= {
                    "PLAIN",
                    "RLE",
                    "BIT_PACKED",
                }:
                    raise ValueError("Unsupported expanding Parquet value encoding")
        arrow = parquet.schema_arrow
        if arrow.names != [c.name for c in spec.columns] or any(
            arrow.field(c.name).type != ARROW_TYPES[c.dtype] for c in spec.columns
        ):
            raise ValueError("Parquet columns/types differ from frozen schema")
        table = parquet.read(use_threads=False)
        if table.nbytes > MAX_DECODED_BYTES:
            raise ValueError("Decoded Parquet budget exceeded")
        records = table.to_pylist()
    except (pa.ArrowException, OSError) as exc:
        raise ValueError("Invalid frozen Parquet") from exc
    for row in records:
        _finite_json(row)
        for column in spec.columns:
            value = row[column.name]
            if value is None:
                if not column.nullable:
                    raise ValueError("Null in required frozen column")
            elif column.dtype == "string" and (not value.strip() or len(value) > 4000):
                raise ValueError("Invalid frozen text value")
            elif column.dtype in {"number", "integer"} and not math.isfinite(value):
                raise ValueError("Nonfinite frozen measurement")
    frame = pd.DataFrame.from_records(records, columns=[c.name for c in spec.columns])
    key = KEYS[spec.name]
    if frame[key].isna().any() or frame[key].duplicated().any():
        raise ValueError("Frozen row identities must be nonnull and unique")
    return frame


@dataclass
class DatasetInputs:
    metadata: FrozenDataset
    tables: dict[str, pd.DataFrame]
    objects: tuple[SnapshotObject, ...]


def validate_rows(dataset: FrozenDataset, tables: dict[str, pd.DataFrame]):
    anchor_name = "casts" if dataset.family == "ctd" else "collections"
    anchor = tables.get(anchor_name)
    if anchor is not None:
        if anchor.sample_id.isna().any():
            raise ValueError("Source sample labels must be retained explicitly")
        if (
            dataset.collection_date_precision == "mixed"
            and "date_precision" not in anchor
        ):
            raise ValueError("Mixed collection dates require per-record date_precision")
        for row in anchor.to_dict("records"):
            precision = row.get("date_precision", dataset.collection_date_precision)
            if (
                dataset.collection_date_precision != "mixed"
                and precision != dataset.collection_date_precision
            ):
                raise ValueError(
                    "Per-record precision contradicts the dataset contract"
                )
            value = row["collection_date"]
            period(None if pd.isna(value) else value, precision)
    specs = {t.name: t for t in dataset.tables}
    for name, frame in tables.items():
        if name == anchor_name:
            continue
        foreign_key = "cast_id" if dataset.family == "ctd" else "library_id"
        if frame[foreign_key].isna().any():
            raise ValueError("Missing source anchor identity")
        if anchor is not None and not set(frame[foreign_key]) <= set(
            anchor[KEYS[anchor_name]]
        ):
            raise ValueError("Frozen table refers to an unknown source anchor")
        if name == "depth_observations":
            if frame.depth.isna().any() or (
                dataset.depth_convention == "positive_down" and (frame.depth < 0).any()
            ):
                raise ValueError(
                    "Depth observations violate their declared sign convention"
                )
            depth = next(c for c in specs[name].columns if c.name == "depth")
            measurement = next(
                (
                    c
                    for c in specs[name].columns
                    if c.name == dataset.descriptor.measurement
                ),
                None,
            )
            if (
                measurement is None
                or measurement.dtype not in {"number", "integer"}
                or measurement.unit != dataset.descriptor.unit
            ):
                raise ValueError("CTD measurement/units differ from source descriptor")
            if depth.unit != dataset.descriptor.depth_unit:
                raise ValueError("Depth units differ from the source descriptor")
        if name == "run_qc":
            for value in frame.run_date.dropna():
                if (
                    len(value) != 10
                    and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo
                    is None
                ):
                    raise ValueError("Run timestamps require an explicit timezone")
                utc_time(value)
        if name in {"kraken_abundance", "metaeuk_abundance", "ranked_taxa"}:
            if (
                frame.taxon.isna().any()
                or frame.method.isna().any()
                or (frame.abundance.dropna() < 0).any()
            ):
                raise ValueError(
                    "Taxa/method identities and nonnegative abundance required"
                )
            unit = next(c.unit for c in specs[name].columns if c.name == "abundance")
            if (
                unit in {"fraction", "percent"}
                and (
                    frame.abundance.dropna() > (1 if unit == "fraction" else 100)
                ).any()
            ):
                raise ValueError("Abundance exceeds its declared unit range")
        if name in {"kraken_abundance", "metaeuk_abundance"}:
            spec = specs[name]
            if (
                not frame.method.eq(spec.method).all()
                or not frame.taxonomic_rank.eq(spec.taxonomic_rank).all()
            ):
                raise ValueError("Assignment method/rank differs from frozen semantics")
            if frame.duplicated(["library_id", "taxon", "taxonomic_rank"]).any():
                raise ValueError("Duplicate normalized library/taxon cells")
            if anchor is not None:
                flag = "has_kraken" if name == "kraken_abundance" else "has_metaeuk"
                if flag not in anchor or anchor[flag].isna().any():
                    raise ValueError(
                        "Explicit per-library assignment coverage required"
                    )
                libraries = set(anchor.loc[anchor[flag].eq(True), "library_id"])
                if not set(frame.library_id) <= libraries:
                    raise ValueError("Measurements contradict assignment coverage")
                if (
                    spec.completeness == "complete"
                    and len(frame) != len(libraries) * frame.taxon.nunique()
                ):
                    raise ValueError(
                        "Complete normalized abundance requires all explicit cells"
                    )


def load_dataset(
    manifest: SnapshotManifest, contents, obj: SnapshotObject
) -> DatasetInputs:
    dataset = dataset_metadata(contents[obj.object_id])
    if (dataset.dataset_id, dataset.source_id, dataset.family) != (
        obj.dataset_id,
        obj.source_id,
        obj.source_family,
    ):
        raise ValueError("Dataset metadata identity differs from sealed ownership")
    objects = {
        item.object_id: item
        for item in manifest.objects
        if item.dataset_id == obj.dataset_id
    }
    expected = {obj.object_id} | {
        t.object_id for t in dataset.tables if t.object_id is not None
    }
    if set(objects) != expected:
        raise ValueError("Exact frozen dataset object membership required")
    tables = {}
    for item in objects.values():
        if (
            item.operation_version != ADAPTER_VERSION
            or item.operation_id != f"c10:{dataset.family}:{item.role}"
        ):
            raise ValueError("Unsupported source export operation version")
    for spec in dataset.tables:
        if spec.object_id is None:
            continue
        item = objects[spec.object_id]
        if (item.source_id, item.source_family, item.role, item.schema_version) != (
            dataset.source_id,
            dataset.family,
            spec.name,
            TABLE_VERSION,
        ):
            raise ValueError("Frozen table ownership/role/schema mismatch")
        tables[spec.name] = parse_table(spec, contents[item.object_id])
    validate_rows(dataset, tables)
    return DatasetInputs(dataset, tables, tuple(objects.values()))


def encode_table(spec: FrozenTable, frame: pd.DataFrame) -> bytes:
    if len(frame) > MAX_ROWS:
        raise ValueError("Frozen input row budget exceeded")
    if set(frame.columns) != {c.name for c in spec.columns}:
        raise ValueError("Exact input frame columns required")
    arrow_schema = pa.schema(
        [
            pa.field(c.name, ARROW_TYPES[c.dtype], nullable=c.nullable)
            for c in spec.columns
        ]
    )
    table = pa.Table.from_pandas(
        frame[[c.name for c in spec.columns]].sort_values(KEYS[spec.name]),
        schema=arrow_schema,
        preserve_index=False,
        safe=True,
    )
    stream = BytesIO()
    pq.write_table(
        table.replace_schema_metadata(None),
        stream,
        compression="zstd",
        version="2.6",
        use_dictionary=False,
    )
    payload = stream.getvalue()
    parse_table(spec, payload)
    return payload


def dataset_exports(
    dataset: FrozenDataset, frames: dict[str, pd.DataFrame], *, generation: str
) -> CapturedSource:
    dataset = FrozenDataset.model_validate(dataset.model_dump(mode="json"))
    if set(frames) != {t.name for t in dataset.tables if t.object_id is not None}:
        raise ValueError("Exact declared retained table frames required")
    validate_rows(dataset, frames)
    metadata_id = f"{dataset.dataset_id}:metadata"
    contents = {metadata_id: canonical_bytes(dataset.model_dump(mode="json"))}
    descriptors = [(metadata_id, "dataset_metadata", DATASET_VERSION)]
    for table in dataset.tables:
        if table.object_id is not None:
            if table.object_id == metadata_id:
                raise ValueError("Metadata and table identities must differ")
            contents[table.object_id] = encode_table(table, frames[table.name])
            descriptors.append((table.object_id, table.name, TABLE_VERSION))
    objects = tuple(
        SnapshotObject(
            object_id=identity,
            dataset_id=dataset.dataset_id,
            source_id=dataset.source_id,
            source_family=dataset.family,
            role=role,
            schema_version=version,
            sha256=hashlib.sha256(contents[identity]).hexdigest(),
            size_bytes=len(contents[identity]),
            operation_id=f"c10:{dataset.family}:{role}",
            operation_version=ADAPTER_VERSION,
            provenance={
                "source_generation": generation,
                "content_sha256": hashlib.sha256(contents[identity]).hexdigest(),
                "references": [dataset.qualification],
            },
        )
        for identity, role, version in descriptors
    )
    return CapturedSource(objects, contents)


def frozen_export_requirement(
    dataset: FrozenDataset, frames: dict[str, pd.DataFrame], *, source_generation: str
) -> SourceExportRequirement:
    """Register one already frozen dataset without SQL/source discovery."""
    return frozen_source_requirement(
        [(dataset, frames)], source_generation=source_generation
    )


def frozen_source_requirement(
    datasets, *, source_generation: str
) -> SourceExportRequirement:
    """Register all explicit datasets of one source/family as one bounded export."""
    items = tuple(datasets)
    if not items:
        raise ValueError("At least one frozen dataset is required")
    source_ids = {(d.source_id, d.family) for d, _ in items}
    if len(source_ids) != 1:
        raise ValueError("One registration must retain one source identity/family")
    source_id, family = next(iter(source_ids))
    objects, contents, qualifiers = [], {}, []
    for dataset, frames in items:
        captured = dataset_exports(dataset, frames, generation=source_generation)
        if set(contents) & set(captured.contents):
            raise ValueError("Duplicate frozen source object identity")
        objects.extend(captured.objects)
        contents.update(captured.contents)
        qualifiers.append(dataset.qualification)
    if len(objects) > 4000 or sum(map(len, contents.values())) > 512 * 1024 * 1024:
        raise ValueError("Frozen registration exceeds snapshot capture bounds")
    captured = CapturedSource(tuple(objects), contents)

    def export(connection, heads, deadline):
        if time.monotonic() >= deadline:
            raise AdapterUnavailable("Frozen export deadline expired")
        if heads.source_generation(source_id) != source_generation:
            raise AdapterUnavailable(
                "Frozen generation differs from source head; rebuild the registration"
            )
        return CapturedSource(captured.objects, captured.contents)

    return SourceExportRequirement(
        source_id=source_id,
        source_family=family,
        schema_versions={obj.role: obj.schema_version for obj in captured.objects},
        operation_versions={
            obj.role: obj.operation_version for obj in captured.objects
        },
        operation_ids={obj.role: obj.operation_id for obj in captured.objects},
        exporter=export,
        capture_method="c10-frozen-parquet-v1",
        qualifiers=tuple(dict.fromkeys(qualifiers)),
    )
