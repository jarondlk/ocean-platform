"""Explicit C09 exports of frozen SST metadata and complete observation tables.

Inputs are caller-supplied immutable bytes. This module neither discovers a
publication nor grants scientific eligibility to its own metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as clock_time, timedelta, timezone
import hashlib
from io import BytesIO
import json
import math
import re
import time
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ingestion.catalogue_snapshot_capture import CapturedSource, SourceExportRequirement
from ingestion.immutable_bundle import canonical_bytes
from schema.catalogue_snapshot import MAX_BYTES, MAX_MANIFEST_BYTES, MAX_OBJECTS
from schema.catalogue_snapshot import SnapshotManifest, SnapshotObject
from schema.context_catalogue import _finite_json
from schema.sst_catalogue import (
    ADAPTER_VERSION,
    DATASET_VERSION,
    TABLE_VERSION,
    SSTDataset,
    SSTTable,
)

MAX_ROWS = 2_000_000
MAX_DECODED_BYTES = 512 * 1024 * 1024
COLUMNS = (
    ("observation_id", pa.string(), False),
    ("time", pa.string(), False),
    ("value", pa.float64(), True),
    ("status", pa.string(), False),
    ("lat", pa.float64(), True),
    ("lon", pa.float64(), True),
    ("quality_flag", pa.string(), True),
    ("uncertainty", pa.float64(), True),
    ("valid_fraction", pa.float64(), True),
    ("valid_ocean_pixels", pa.int64(), True),
    ("ocean_pixels", pa.int64(), True),
    ("source_sha256", pa.string(), False),
    ("exclusion_reason", pa.string(), True),
)
ARROW_SCHEMA = pa.schema(
    [pa.field(name, dtype, nullable=nullable) for name, dtype, nullable in COLUMNS]
)


class AdapterUnavailable(ValueError):
    """A supported complete operation cannot run on these frozen inputs."""


SSTUnavailable = AdapterUnavailable


def observation_time(value: str, precision: str, calendar: str) -> datetime:
    """Validate retained precision and resolve instants in the declared calendar.

    The returned timestamp is for comparison only; source text stays intact.
    A day value is a calendar-day interval, not a measured midnight instant.
    Day labels are interpreted in their declared calendar, never relabeled UTC.
    """
    if type(value) is not str or calendar not in {"UTC", "Asia/Tokyo"}:
        raise ValueError("Explicit supported SST time/calendar required")
    zone = ZoneInfo(calendar)
    if precision == "day":
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("SST day does not match declared precision")
        try:
            begin = datetime.combine(date.fromisoformat(value), clock_time(), zone)
            begin.astimezone(timezone.utc)
            (begin + timedelta(days=1)).astimezone(timezone.utc)
        except OverflowError as exc:
            raise ValueError(
                "SST day requires representable UTC interval boundaries"
            ) from exc
        return begin
    if precision != "datetime" or "T" not in value:
        raise ValueError("SST instant does not match declared precision")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("SST instants require an explicit timezone")
    try:
        instant.astimezone(timezone.utc)
        return instant.astimezone(zone)
    except OverflowError as exc:
        raise ValueError(
            "SST instant is outside representable UTC/calendar range"
        ) from exc


def observation_day(value: str, precision: str, calendar: str) -> str:
    return observation_time(value, precision, calendar).date().isoformat()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate frozen SST metadata key")
        result[key] = value
    return result


def dataset_metadata(data: bytes) -> SSTDataset:
    if type(data) is not bytes or len(data) > MAX_MANIFEST_BYTES:
        raise ValueError("Bounded frozen SST metadata bytes required")
    raw = json.loads(data.decode("utf-8"), object_pairs_hook=_unique)
    _finite_json(raw)
    return SSTDataset.model_validate(raw)


def _validate_primitives(records):
    for row in records:
        for name, dtype, nullable in COLUMNS:
            value = row[name]
            if value is None:
                if not nullable:
                    raise ValueError("Null in required SST column")
            elif dtype == pa.string():
                if type(value) is not str or not value.strip() or len(value) > 4000:
                    raise ValueError("Invalid frozen SST text value")
            elif dtype == pa.int64():
                if type(value) is not int or not 0 <= value <= 2**63 - 1:
                    raise ValueError(
                        "SST pixel counts require nonnegative int64 primitive values"
                    )
            elif type(value) not in {int, float} or not math.isfinite(value):
                raise ValueError("SST numbers must be finite primitive values")


def _frame_records(frame):
    """Resolve pandas nullable sentinels only in nullable source columns.

    Parquet NaN payloads remain invalid. An explicitly supplied dataframe uses
    pandas' native missing-value representation before its canonical encoding.
    """
    records = frame.to_dict("records")
    for row in records:
        for name, _, nullable in COLUMNS:
            value = row[name]
            if nullable and (
                value is pd.NA or (type(value) is float and math.isnan(value))
            ):
                row[name] = None
    return records


def parse_table(spec: SSTTable, data: bytes) -> pd.DataFrame:
    if type(data) is not bytes or len(data) > MAX_BYTES:
        raise ValueError("Bounded frozen SST table bytes required")
    try:
        parquet = pq.ParquetFile(BytesIO(data))
        metadata = parquet.metadata
        if metadata.num_rows > MAX_ROWS or metadata.num_rows != spec.row_count:
            raise ValueError("Frozen SST row count/budget mismatch")
        if (
            sum(
                metadata.row_group(i).total_byte_size
                for i in range(metadata.num_row_groups)
            )
            > MAX_DECODED_BYTES
        ):
            raise ValueError("Frozen SST decoded budget exceeded")
        # Dictionary/prefix encodings can expand beyond footer byte accounting.
        # The canonical writer deliberately emits only plain values.
        for group in range(metadata.num_row_groups):
            for column in range(metadata.num_columns):
                if not set(metadata.row_group(group).column(column).encodings) <= {
                    "PLAIN",
                    "RLE",
                    "BIT_PACKED",
                }:
                    raise ValueError("Unsupported expanding SST Parquet encoding")
        if not parquet.schema_arrow.equals(ARROW_SCHEMA, check_metadata=False):
            raise ValueError(
                "SST Parquet columns/types/nullability differ from frozen schema"
            )
        table = parquet.read(use_threads=False)
        if table.nbytes > MAX_DECODED_BYTES:
            raise ValueError("Frozen SST decoded budget exceeded")
        records = table.to_pylist()
    except (pa.ArrowException, OSError) as exc:
        raise ValueError("Invalid frozen SST Parquet") from exc
    _validate_primitives(records)
    # Object dtype retains explicit None rather than manufacturing numeric NaN.
    frame = pd.DataFrame(records, columns=ARROW_SCHEMA.names, dtype=object)
    if frame.observation_id.duplicated().any():
        raise ValueError("Frozen SST observation identities must be unique")
    frame.attrs["decoded_bytes"] = table.nbytes
    return frame


@dataclass
class DatasetInputs:
    metadata: SSTDataset
    tables: dict[str, pd.DataFrame]
    objects: tuple[SnapshotObject, ...]


def validate_rows(dataset: SSTDataset, tables: dict[str, pd.DataFrame]):
    expected = {"observations"} if dataset.table.object_id is not None else set()
    if set(tables) != expected:
        raise ValueError("Exact declared SST table frames required")
    if not expected:
        return
    frame = tables["observations"]
    if len(frame) > MAX_ROWS:
        raise ValueError("Frozen SST row budget exceeded")
    if (
        list(frame.columns) != ARROW_SCHEMA.names
        or len(frame) != dataset.table.row_count
    ):
        raise ValueError("SST table columns/count differ from metadata")
    records = _frame_records(frame)
    _validate_primitives(records)
    identities, cells = set(), set()
    for row in records:
        if row["observation_id"] in identities:
            raise ValueError("Duplicate SST observation identity")
        identities.add(row["observation_id"])
        instant = observation_time(
            row["time"], dataset.observation_precision, dataset.calendar
        )
        if (
            dataset.sampling is not None
            and not dataset.sampling.start
            <= instant.date().isoformat()
            <= dataset.sampling.end
        ):
            raise ValueError("SST observation lies outside declared sampling calendar")
        if row["status"] not in {"valid", "invalid", "excluded"}:
            raise ValueError("Unknown SST observation status")
        if row["status"] == "valid":
            if row["exclusion_reason"] is not None:
                raise ValueError("Valid SST quality status cannot carry an exclusion")
        elif row["exclusion_reason"] is None:
            raise ValueError(
                "Invalid/excluded SST observations require explicit reasons"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"]):
            raise ValueError("SST observations require exact source SHA-256 values")
        if row["uncertainty"] is not None and row["uncertainty"] < 0:
            raise ValueError("SST uncertainty cannot be negative")
        fraction, valid_pixels, ocean_pixels = (
            row["valid_fraction"],
            row["valid_ocean_pixels"],
            row["ocean_pixels"],
        )
        if fraction is not None and not 0 <= fraction <= 1:
            raise ValueError("SST valid fraction must lie within zero and one")
        if (
            valid_pixels is not None
            and ocean_pixels is not None
            and valid_pixels > ocean_pixels
        ):
            raise ValueError("SST valid pixel count exceeds ocean pixel count")
        if ocean_pixels == 0 and fraction is not None:
            raise ValueError("Zero ocean pixels require unknown valid fraction")
        if (
            ocean_pixels is not None
            and ocean_pixels > 0
            and valid_pixels is not None
            and fraction is not None
            and not math.isclose(
                fraction, valid_pixels / ocean_pixels, rel_tol=1e-6, abs_tol=1e-8
            )
        ):
            raise ValueError("SST valid fraction contradicts retained pixel counts")
        absolute_zero = 0 if dataset.descriptor.unit == "K" else -273.15
        if row["value"] is not None and row["value"] < absolute_zero:
            raise ValueError("SST measurement is below absolute zero in declared units")
        if dataset.observation_entity == "regional_daily_summary":
            if row["lat"] is not None or row["lon"] is not None:
                raise ValueError(
                    "Regional SST summaries cannot invent point coordinates"
                )
            cell = instant.date()
        else:
            lat, lon = row["lat"], row["lon"]
            support = dataset.support
            if (
                lat is None
                or lon is None
                or not (-90 <= lat <= 90 and -180 <= lon <= 180)
            ):
                raise ValueError("Grid SST observations require valid coordinates")
            if not (
                support.south <= lat <= support.north
                and support.west <= lon <= support.east
            ):
                raise ValueError("SST grid coordinate lies outside retained support")
            cell = (instant, lat, lon)
        if cell in cells:
            raise ValueError("Duplicate SST regional day/grid coordinate-time cell")
        cells.add(cell)


def _verified_bytes(item: SnapshotObject, contents) -> bytes:
    data = contents.get(item.object_id)
    if (
        type(data) is not bytes
        or len(data) != item.size_bytes
        or hashlib.sha256(data).hexdigest() != item.sha256
    ):
        raise ValueError("Frozen SST object bytes/hash mismatch")
    return data


def load_dataset(
    manifest: SnapshotManifest, contents, obj: SnapshotObject
) -> DatasetInputs:
    if obj not in manifest.objects or (
        obj.role,
        obj.schema_version,
        obj.source_family,
    ) != ("dataset_metadata", DATASET_VERSION, "remote_sensing"):
        raise ValueError("Frozen SST metadata role/schema/ownership mismatch")
    dataset = dataset_metadata(_verified_bytes(obj, contents))
    if (dataset.dataset_id, dataset.source_id) != (obj.dataset_id, obj.source_id):
        raise ValueError("SST metadata identity differs from sealed ownership")
    objects = {
        item.object_id: item
        for item in manifest.objects
        if item.dataset_id == dataset.dataset_id
    }
    expected = {obj.object_id} | (
        {dataset.table.object_id} if dataset.table.object_id is not None else set()
    )
    if set(objects) != expected:
        raise ValueError("Exact frozen SST dataset object membership required")
    for item in objects.values():
        if (
            item.source_id,
            item.source_family,
            item.operation_id,
            item.operation_version,
        ) != (
            dataset.source_id,
            "remote_sensing",
            f"c11:remote_sensing:{item.role}",
            ADAPTER_VERSION,
        ):
            raise ValueError("Frozen SST source/operation ownership mismatch")
    tables = {}
    if dataset.table.object_id is not None:
        item = objects[dataset.table.object_id]
        if (item.role, item.schema_version) != ("observations", TABLE_VERSION):
            raise ValueError("Frozen SST table role/schema mismatch")
        tables["observations"] = parse_table(
            dataset.table, _verified_bytes(item, contents)
        )
    validate_rows(dataset, tables)
    return DatasetInputs(dataset, tables, tuple(objects.values()))


def encode_table(spec: SSTTable, frame: pd.DataFrame) -> bytes:
    if len(frame) > MAX_ROWS or list(frame.columns) != ARROW_SCHEMA.names:
        raise ValueError("Frozen SST row budget/exact columns required")
    records = _frame_records(frame)
    _validate_primitives(records)
    table = pa.Table.from_pylist(records, schema=ARROW_SCHEMA)
    if table.nbytes > MAX_DECODED_BYTES:
        raise ValueError("Frozen SST decoded budget exceeded")
    table = table.sort_by([("observation_id", "ascending")])
    stream = BytesIO()
    pq.write_table(
        table, stream, compression="zstd", version="2.6", use_dictionary=False
    )
    payload = stream.getvalue()
    parse_table(spec, payload)
    return payload


def dataset_exports(
    dataset: SSTDataset, frames: dict[str, pd.DataFrame], *, generation: str
) -> CapturedSource:
    dataset = SSTDataset.model_validate(dataset.model_dump(mode="json"))
    validate_rows(dataset, frames)
    metadata_id = f"{dataset.dataset_id}:metadata"
    contents = {metadata_id: canonical_bytes(dataset.model_dump(mode="json"))}
    descriptors = [(metadata_id, "dataset_metadata", DATASET_VERSION)]
    if len(contents[metadata_id]) > MAX_MANIFEST_BYTES:
        raise ValueError("Frozen SST metadata byte budget exceeded")
    if dataset.table.object_id is not None:
        if dataset.table.object_id == metadata_id:
            raise ValueError("SST metadata and observations identities must differ")
        contents[dataset.table.object_id] = encode_table(
            dataset.table, frames["observations"]
        )
        descriptors.append((dataset.table.object_id, "observations", TABLE_VERSION))
    if sum(map(len, contents.values())) > MAX_BYTES:
        raise ValueError("Frozen SST export byte budget exceeded")
    objects = tuple(
        SnapshotObject(
            object_id=identity,
            dataset_id=dataset.dataset_id,
            source_id=dataset.source_id,
            source_family="remote_sensing",
            role=role,
            schema_version=version,
            sha256=hashlib.sha256(contents[identity]).hexdigest(),
            size_bytes=len(contents[identity]),
            operation_id=f"c11:remote_sensing:{role}",
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


def frozen_source_requirement(
    datasets, *, source_generation: str
) -> SourceExportRequirement:
    """Freeze all explicitly supplied datasets of one source; never discover it."""
    items = tuple(datasets)
    if not items or len({dataset.source_id for dataset, _ in items}) != 1:
        raise ValueError("One explicit nonempty SST source registration required")
    source_id = items[0][0].source_id
    objects, contents, qualifiers = [], {}, []
    rows = decoded = 0
    for dataset, frames in items:
        captured = dataset_exports(dataset, frames, generation=source_generation)
        if set(contents) & set(captured.contents):
            raise ValueError("Duplicate frozen SST source object identity")
        if dataset.table.object_id is not None:
            frame = parse_table(
                dataset.table, captured.contents[dataset.table.object_id]
            )
            rows += len(frame)
            decoded += frame.attrs["decoded_bytes"]
        if rows > MAX_ROWS or decoded > MAX_DECODED_BYTES:
            raise ValueError("Cumulative frozen SST source row/decoded budget exceeded")
        objects.extend(captured.objects)
        contents.update(captured.contents)
        qualifiers.append(dataset.qualification)
        if len(objects) > MAX_OBJECTS or sum(map(len, contents.values())) > MAX_BYTES:
            raise ValueError("Frozen SST registration exceeds C09 capture bounds")
    captured = CapturedSource(tuple(objects), contents)

    def export(connection, heads, deadline):
        if (
            type(deadline) not in {int, float}
            or not math.isfinite(deadline)
            or time.monotonic() >= deadline
        ):
            raise AdapterUnavailable("Frozen SST export deadline expired/invalid")
        if heads.source_generation(source_id) != source_generation:
            raise AdapterUnavailable(
                "Frozen SST generation differs from source head; rebuild registration"
            )
        return CapturedSource(captured.objects, captured.contents)

    return SourceExportRequirement(
        source_id=source_id,
        source_family="remote_sensing",
        schema_versions={obj.role: obj.schema_version for obj in captured.objects},
        operation_versions={
            obj.role: obj.operation_version for obj in captured.objects
        },
        operation_ids={obj.role: obj.operation_id for obj in captured.objects},
        exporter=export,
        capture_method="c11-frozen-sst-parquet-v1",
        qualifiers=tuple(dict.fromkeys(qualifiers)),
    )


def frozen_export_requirement(
    dataset: SSTDataset, frames: dict[str, pd.DataFrame], *, source_generation: str
) -> SourceExportRequirement:
    return frozen_source_requirement(
        [(dataset, frames)], source_generation=source_generation
    )
