"""Strict C13 index bytes and complete tables with explicit frozen ownership."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import sys
import time

from ingestion.catalogue_snapshot_capture import CapturedSource, SourceExportRequirement
from ingestion.immutable_bundle import canonical_bytes, digest
from preprocessing.derived_artifacts import (
    CURRENT_METHODS,
    FILE_METHODS,
    ID_METHODS,
    TYPE_METHODS,
    DerivedEligibility,
    receipt_eligibility,
)
from schema.catalogue_snapshot import (
    MAX_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_OBJECTS,
    SnapshotManifest,
    SnapshotObject,
)
from schema.context_catalogue import _finite_json
from schema.scientific_catalogue import (
    ADAPTER_VERSION,
    DATASET_VERSION,
    TABLE_VERSION,
    INDEX_OBJECT_ID,
    INDEX_DATASET_ID,
    INDEX_SOURCE_ID,
    TRANSPORT_QUALIFICATION,
    ScientificRegistry,
    ScientificTable,
)

MAX_ROWS = 2_000_000
MAX_TABLE_BYTES = 32 * 1024 * 1024
MAX_DECODED_BYTES = 512 * 1024 * 1024


class AdapterUnavailable(ValueError):
    """The frozen index cannot establish this supported scientific operation."""


ScientificUnavailable = AdapterUnavailable


@dataclass(frozen=True)
class RegistryInputs:
    metadata: ScientificRegistry
    tables: dict[str, list[dict]]
    objects: tuple[SnapshotObject, ...]
    eligibility: dict[str, DerivedEligibility]


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate frozen scientific JSON key")
        result[key] = value
    return result


def _json(data, maximum):
    if type(data) is not bytes or len(data) > maximum:
        raise ValueError("Bounded frozen scientific bytes required")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique)
    except (RecursionError, UnicodeError) as error:
        raise ValueError("Invalid frozen scientific JSON") from error
    _finite_json(value)
    return value


def registry_metadata(data: bytes) -> ScientificRegistry:
    return ScientificRegistry.model_validate(_json(data, MAX_MANIFEST_BYTES))


def _decoded_size(value):
    total = sys.getsizeof(value)
    if isinstance(value, dict):
        total += sum(sys.getsizeof(k) + _decoded_size(v) for k, v in value.items())
    elif isinstance(value, list):
        total += sum(_decoded_size(v) for v in value)
    if total > MAX_DECODED_BYTES:
        raise ValueError("Frozen scientific decoded byte budget exceeded")
    return total


def parse_table(spec: ScientificTable, data: bytes) -> list[dict]:
    rows = _json(data, MAX_TABLE_BYTES)
    if (
        not isinstance(rows, list)
        or len(rows) > MAX_ROWS
        or len(rows) != spec.row_count
    ):
        raise ValueError("Frozen scientific table row count/budget mismatch")
    keys = {c.key for c in spec.columns}
    if any(type(row) is not dict or set(row) != keys for row in rows):
        raise ValueError("Scientific rows must exactly match their declared columns")
    if "result_id" in keys:
        identities = [r["result_id"] for r in rows]
        if any(
            type(i) is not str or not i.strip() or len(i) > 256 for i in identities
        ) or len(set(identities)) != len(identities):
            raise ValueError(
                "Published result row identities must be unique nonempty text"
            )
    _decoded_size(rows)
    return rows


def _verified_bytes(obj, contents):
    data = contents.get(obj.object_id)
    if (
        type(data) is not bytes
        or len(data) != obj.size_bytes
        or hashlib.sha256(data).hexdigest() != obj.sha256
    ):
        raise ValueError("Frozen scientific object hash/size/content mismatch")
    return data


def _eligibility(registry, tables):
    bindings = {d.dataset_id: d.snapshot_id for d in registry.datasets}
    affected = (
        set(CURRENT_METHODS)
        | set(FILE_METHODS.values())
        | set(TYPE_METHODS.values())
        | set(ID_METHODS.values())
    )
    result = {}
    for analysis in registry.analyses:
        method = ID_METHODS.get(analysis.id, analysis.method_id)
        if analysis.derived_receipt is None:
            blocked = method in affected or method.startswith(
                ("unknown_reliability", "unknown_analysis")
            )
            result[analysis.id] = DerivedEligibility(
                not blocked,
                "legacy_unversioned" if blocked else "unaffected",
                "Affected legacy evidence requires regeneration and bound eligibility review."
                if blocked
                else "This published analysis is outside the affected C02 derived methods.",
            )
            continue
        output = {
            t.name: tables[t.object_id]
            for t in analysis.tables
            if t.object_id is not None
        }
        value = receipt_eligibility(
            analysis.derived_receipt,
            digest(output),
            expected_inputs={i: bindings[i] for i in analysis.input_dataset_ids},
            superseded_generations=set(registry.superseded_generations),
        )
        if analysis.derived_receipt.get("method_id") != method:
            value = DerivedEligibility(
                False,
                "method_mismatch",
                "The derived receipt does not match the analysis method.",
            )
        elif analysis.derived_receipt.get("method_version") != analysis.method_version:
            value = DerivedEligibility(
                False,
                "method_version_mismatch",
                "The derived receipt does not match the declared analysis method version.",
            )
        result[analysis.id] = value
    return result


def load_registry(manifest, contents) -> RegistryInputs:
    manifest = SnapshotManifest.model_validate(
        manifest.model_dump(mode="json")
        if isinstance(manifest, SnapshotManifest)
        else manifest
    )
    objects = {obj.object_id: obj for obj in manifest.objects}
    if len(objects) != len(manifest.objects) or set(objects) != set(contents):
        raise ValueError("Exact scientific index object membership required")
    obj = objects.get(INDEX_OBJECT_ID)
    if obj is None:
        raise ValueError("Scientific registry object is absent")
    if (
        obj.dataset_id,
        obj.source_id,
        obj.source_family,
        obj.role,
        obj.schema_version,
    ) != (
        INDEX_DATASET_ID,
        INDEX_SOURCE_ID,
        "ctd",
        "scientific_registry",
        DATASET_VERSION,
    ):
        raise ValueError("Scientific registry role/schema/ownership mismatch")
    registry = registry_metadata(_verified_bytes(obj, contents))
    specs = {
        t.object_id: t
        for a in registry.analyses
        for t in a.tables
        if t.object_id is not None
    }
    if set(objects) != {INDEX_OBJECT_ID, *specs}:
        raise ValueError("Exact scientific table membership required")
    if sum(t.row_count for t in specs.values()) > MAX_ROWS:
        raise ValueError("Cumulative scientific row budget exceeded")
    tables, decoded = {}, 0
    for item in objects.values():
        role, version = (
            ("scientific_registry", DATASET_VERSION)
            if item.object_id == INDEX_OBJECT_ID
            else ("result_table", TABLE_VERSION)
        )
        if (
            item.dataset_id,
            item.source_id,
            item.source_family,
            item.role,
            item.schema_version,
            item.operation_id,
            item.operation_version,
        ) != (
            INDEX_DATASET_ID,
            INDEX_SOURCE_ID,
            "ctd",
            role,
            version,
            f"c13:scientific:{role}",
            ADAPTER_VERSION,
        ):
            raise ValueError(
                "Scientific object source/schema/operation ownership mismatch"
            )
        data = _verified_bytes(item, contents)
        if item.object_id in specs:
            rows = parse_table(specs[item.object_id], data)
            decoded += _decoded_size(rows)
            if decoded > MAX_DECODED_BYTES:
                raise ValueError("Cumulative scientific decoded byte budget exceeded")
            tables[item.object_id] = rows
    if (
        len(manifest.source_captures) != 1
        or manifest.source_captures[0].source_id != INDEX_SOURCE_ID
    ):
        raise ValueError("Scientific index requires its explicit transport source only")
    return RegistryInputs(
        registry, tables, tuple(objects.values()), _eligibility(registry, tables)
    )


def registry_exports(
    registry: ScientificRegistry, tables: dict, *, generation: str
) -> CapturedSource:
    registry = ScientificRegistry.model_validate(registry.model_dump(mode="json"))
    specs = {
        t.object_id: t
        for a in registry.analyses
        for t in a.tables
        if t.object_id is not None
    }
    if set(tables) != set(specs):
        raise ValueError("Exact declared scientific table contents required")
    contents = {INDEX_OBJECT_ID: canonical_bytes(registry.model_dump(mode="json"))}
    if len(contents[INDEX_OBJECT_ID]) > MAX_MANIFEST_BYTES:
        raise ValueError("Scientific registry metadata budget exceeded")
    decoded = rows_count = 0
    for identity, spec in specs.items():
        payload = canonical_bytes(tables[identity])
        rows = parse_table(spec, payload)
        rows_count += len(rows)
        decoded += _decoded_size(rows)
        if rows_count > MAX_ROWS or decoded > MAX_DECODED_BYTES:
            raise ValueError("Cumulative scientific row/decoded budget exceeded")
        contents[identity] = payload
    if len(contents) > MAX_OBJECTS or sum(map(len, contents.values())) > MAX_BYTES:
        raise ValueError("Scientific export exceeds C09 object/byte bounds")
    objects = []
    for identity, payload in contents.items():
        role, version = (
            ("scientific_registry", DATASET_VERSION)
            if identity == INDEX_OBJECT_ID
            else ("result_table", TABLE_VERSION)
        )
        checksum = hashlib.sha256(payload).hexdigest()
        objects.append(
            SnapshotObject(
                object_id=identity,
                dataset_id=INDEX_DATASET_ID,
                source_id=INDEX_SOURCE_ID,
                source_family="ctd",
                role=role,
                schema_version=version,
                sha256=checksum,
                size_bytes=len(payload),
                operation_id=f"c13:scientific:{role}",
                operation_version=ADAPTER_VERSION,
                provenance={
                    "source_generation": generation,
                    "content_sha256": checksum,
                    "references": [TRANSPORT_QUALIFICATION],
                },
            )
        )
    return CapturedSource(tuple(objects), contents)


def frozen_registry_requirement(
    registry, tables, *, source_generation: str
) -> SourceExportRequirement:
    captured = registry_exports(registry, tables, generation=source_generation)

    def export(connection, heads, deadline):
        if (
            type(deadline) not in {int, float}
            or not math.isfinite(deadline)
            or time.monotonic() >= deadline
        ):
            raise AdapterUnavailable(
                "Frozen scientific export deadline expired/invalid"
            )
        if heads.source_generation(INDEX_SOURCE_ID) != source_generation:
            raise AdapterUnavailable(
                "Frozen scientific generation differs from source head"
            )
        return CapturedSource(captured.objects, captured.contents)

    return SourceExportRequirement(
        source_id=INDEX_SOURCE_ID,
        source_family="ctd",
        schema_versions={o.role: o.schema_version for o in captured.objects},
        operation_versions={o.role: o.operation_version for o in captured.objects},
        operation_ids={o.role: o.operation_id for o in captured.objects},
        exporter=export,
        capture_method="c13-frozen-scientific-index-v1",
        qualifiers=(TRANSPORT_QUALIFICATION,),
    )
