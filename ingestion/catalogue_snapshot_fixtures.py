"""Small source-owned frozen examples for C09/C10–C13, never real data adapters."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import time

from ingestion.immutable_bundle import canonical_bytes
from schema.catalogue_snapshot import SnapshotManifest, SnapshotObject, SourceCapture
from schema.context_catalogue_fixtures import fixture_scope

FIXTURE_ROWS = {
    "ctd": {
        "casts": [
            {
                "cast_id": "synthetic-cast-1",
                "station": "synthetic-station",
                "date": "2024-01-01",
            }
        ],
        "depth_observations": [
            {"cast_id": "synthetic-cast-1", "depth_m": 0, "temperature_degC": -1.5},
            {"cast_id": "synthetic-cast-1", "depth_m": 10, "temperature_degC": 2.0},
        ],
    },
    "metagenome": {
        "kraken_measurements": [
            {
                "library_id": "synthetic-library-1",
                "method": "Kraken",
                "taxon": "synthetic-taxon",
                "relative_abundance": 0.25,
                "denominator": "classified reads",
            }
        ],
        "metaeuk_measurements": [
            {
                "library_id": "synthetic-library-1",
                "method": "MetaEuk",
                "taxon": "synthetic-taxon",
                "relative_abundance": 0.5,
                "denominator": "classified reads",
            }
        ],
    },
    "remote_sensing": {
        "observations": [
            {
                "date": "2024-01-01",
                "product_id": "synthetic-regional-grid",
                "sst_degC": 8.0,
            },
            {
                "date": "2024-01-03",
                "product_id": "synthetic-regional-grid",
                "sst_degC": 9.0,
            },
        ],
        "coverage": [
            {
                "expected_days": 3,
                "observed_days": 2,
                "missing_dates": ["2024-01-02"],
                "spatial_role": "regional_summary",
                "resolution_degrees": 0.01,
            }
        ],
    },
    "edna_metabarcoding": {
        "canonical_rows": [
            {
                "occurrence_id": "synthetic-occurrence-1",
                "assay_id": "synthetic-assay-1",
                "assignment_method": "qcauto_target",
                "sample_kind": "environmental",
                "is_control": False,
            },
            {
                "occurrence_id": "synthetic-control-1",
                "assay_id": "synthetic-assay-1",
                "assignment_method": "qcauto_target",
                "sample_kind": "negative_control",
                "is_control": True,
            },
        ],
        "classifications": [
            {
                "occurrence_id": "synthetic-occurrence-1",
                "classification_generation": "classification-1",
                "sample_kind": "environmental",
                "review_state": "synthetic-reviewed",
            },
            {
                "occurrence_id": "synthetic-control-1",
                "classification_generation": "classification-1",
                "sample_kind": "negative_control",
                "review_state": "synthetic-reviewed",
            },
        ],
    },
}


def fixture_snapshot(*, generation="generation-1", rows=None):
    """Return validated immutable descriptors and exact bytes for all four sources."""
    rows = deepcopy(FIXTURE_ROWS if rows is None else rows)
    objects = []
    sources = []
    contents = {}
    versions = {}
    for family, tables in sorted(rows.items()):
        sources.append(
            SourceCapture(
                source_id=family,
                source_family=family,
                source_generation=generation,
                publication_generation="publication-1",
                classification_generation="classification-1",
                relationship_generation="relationship-1",
                operation_generation="operation-1",
                capture_method="synthetic-frozen-example-v1",
                qualifiers=[
                    "Synthetic local fixture; no scientific publication approval"
                ],
            )
        )
        for role, records in sorted(tables.items()):
            payload = canonical_bytes(records)
            identity = f"synthetic:{family}:{role}"
            operation = f"{family}:{role}"
            digest = hashlib.sha256(payload).hexdigest()
            objects.append(
                SnapshotObject(
                    object_id=identity,
                    dataset_id=f"synthetic:{family}:dataset",
                    source_id=family,
                    source_family=family,
                    role=role,
                    sha256=digest,
                    size_bytes=len(payload),
                    schema_version="synthetic-rows-v1",
                    operation_id=operation,
                    operation_version="v1",
                    provenance={
                        "source_generation": generation,
                        "content_sha256": digest,
                        "references": ["Synthetic local acceptance fixture only"],
                    },
                )
            )
            contents[identity] = payload
            versions[operation] = "v1"
    manifest = SnapshotManifest(
        scope=fixture_scope(),
        source_captures=sources,
        objects=objects,
        operation_versions=versions,
    )
    return manifest, contents


def fixture_registry(*, rows=None):
    """Register four frozen source exporters; ignore the injected DB connection.

    C10–C13 replace these callbacks with canonical SQL exports using the supplied
    connection and deadline. Bytes are copied now, so later fixture edits cannot
    change an existing registration.
    """
    from ingestion.catalogue_snapshot_capture import (
        CaptureError,
        CapturedSource,
        SourceExportRegistry,
        SourceExportRequirement,
    )

    manifest, contents = fixture_snapshot(rows=rows)
    requirements = []
    for source in manifest.source_captures:
        descriptors = tuple(
            obj.model_dump(mode="json")
            for obj in manifest.objects
            if obj.source_id == source.source_id
        )
        payloads = {obj["object_id"]: contents[obj["object_id"]] for obj in descriptors}

        def export(connection, heads, deadline, *, source_id=source.source_id,
                   descriptors=descriptors, payloads=payloads):
            if time.monotonic() >= deadline:
                raise CaptureError("Synthetic export deadline expired")
            objects = []
            for descriptor in descriptors:
                value = deepcopy(descriptor)
                value["provenance"]["source_generation"] = heads.source_generation(source_id)
                objects.append(SnapshotObject.model_validate(value))
            return CapturedSource(tuple(objects), payloads)

        requirements.append(SourceExportRequirement(
            source_id=source.source_id,
            source_family=source.source_family,
            schema_versions={obj["role"]: obj["schema_version"] for obj in descriptors},
            operation_versions={obj["role"]: obj["operation_version"] for obj in descriptors},
            exporter=export,
            capture_method=source.capture_method,
            qualifiers=tuple(source.qualifiers),
        ))
    return SourceExportRegistry(tuple(requirements))
