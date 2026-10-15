"""Explicit C11 synthetic inputs; these fixtures are never a runtime fallback."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import hashlib
from zoneinfo import ZoneInfo

import pandas as pd

from retrieval.source_scope import EvidenceScope, FAMILIES
from schema.catalogue_snapshot import SnapshotManifest, SourceCapture
from schema.sst_catalogue import SSTDataset, TABLE_COLUMNS, sst_product_node_id


def sst_scope(**filters):
    return EvidenceScope.model_validate(
        {
            "version": 1,
            "sources": {
                family: {
                    "enabled": family == "remote_sensing",
                    "filters": filters if family == "remote_sensing" else {},
                }
                for family in FAMILIES
            },
        }
    )


def sst_fixture(
    count=1205,
    *,
    dataset_id="synthetic:sst:mur-final",
    source_id="synthetic-sst",
    generation="final",
    entity="regional_daily_summary",
    calendar="UTC",
    sampling=True,
    precision="day",
):
    """Retain one leap-day gap, zero, missing value, invalid and excluded rows.

    For count >= 4: raw rows=count, accepted nonnull rows=count-3, and the
    inclusive declared calendar contains count+1 days. No source is opened.
    """
    if type(count) is not int or not 0 <= count <= 36_598:
        raise ValueError("Synthetic SST count must fit the bounded daily calendar")
    if generation not in {"final", "interim"}:
        raise ValueError("Synthetic MUR fixtures require final or interim generation")
    first = date(2024, 2, 27)
    rows = []
    for index in range(count):
        day = first + timedelta(days=index + (index >= 2))
        retained_time = day.isoformat()
        if precision == "datetime":
            retained_time = datetime.combine(
                day, time(12), tzinfo=ZoneInfo(calendar)
            ).isoformat()
        status = "invalid" if index == 2 else "excluded" if index == 3 else "valid"
        rows.append(
            {
                "observation_id": f"observation-{index:06d}",
                "time": retained_time,
                "value": None
                if index == 1
                else 100.0
                if index == 2
                else 999.0
                if index == 3
                else float(index),
                "status": status,
                "lat": None
                if entity == "regional_daily_summary"
                else 38.25 + (index % 2) * 0.5,
                "lon": None
                if entity == "regional_daily_summary"
                else 141.25 + (index % 2) * 0.5,
                "quality_flag": None
                if index == 1
                else "invalid-quality"
                if index == 2
                else "source-excluded"
                if index == 3
                else "accepted",
                "uncertainty": None if index == 1 else 0.25,
                "valid_fraction": None if index == 1 else 0.5 if index == 2 else 0.9,
                "valid_ocean_pixels": None if index == 1 else 50 if index == 2 else 90,
                "ocean_pixels": None if index == 1 else 100,
                "source_sha256": hashlib.sha256(
                    f"synthetic:{dataset_id}:{index}".encode()
                ).hexdigest(),
                "exclusion_reason": "invalid quality"
                if index == 2
                else "source excluded"
                if index == 3
                else None,
            }
        )
    # Nullable integer columns preserve reported pixel counts without casting
    # known values to floats when another source row has an unknown count.
    frame = pd.DataFrame(rows, columns=TABLE_COLUMNS).astype(
        {"valid_ocean_pixels": "Int64", "ocean_pixels": "Int64"}
    )
    version = "04.1" if generation == "final" else "04.1nrt"
    last = first + timedelta(days=max(count - 1, 0) + (count >= 3))
    metadata = SSTDataset.model_validate(
        {
            "dataset_id": dataset_id,
            "source_id": source_id,
            "product_node_id": sst_product_node_id(
                source_id, "mur", version, generation
            ),
            "collection_id": f"{dataset_id}:collection",
            "title": {"en": "Synthetic MUR SST", "ja": "合成MUR海面水温"},
            "purpose": {
                "en": "Frozen SST semantics acceptance",
                "ja": "固定SST意味論の検証",
            },
            "descriptor": {
                "family": "remote_sensing",
                "product_id": "mur",
                "product_version": version,
                "spatial_resolution": 0.05,
                "spatial_resolution_unit": "degree",
                "temporal_resolution": "daily foundation analysis",
                "measurement": "sea_surface_temperature",
                "unit": "degC",
                "spatial_role": "regional_summary"
                if entity == "regional_daily_summary"
                else "coarse_context",
            },
            "processing_generation": generation,
            "measurement_type": "satellite_in_situ_analysis",
            "temporal_statistic": "daily_foundation_analysis",
            "calendar": calendar,
            "observation_precision": precision,
            "support": {"south": 38.0, "north": 39.0, "west": 141.0, "east": 142.0},
            "observation_entity": entity,
            "sampling": {
                "frequency": "daily",
                "start": first.isoformat(),
                "end": last.isoformat(),
                "calendar": calendar,
            }
            if sampling
            else None,
            "spatial_resolution_basis": "Explicit 0.05-degree grid-point subsampling, not a native-grid reconstruction",
            "aggregation_method": "Cosine-latitude weighted mean of retained grid-point subsampling"
            if entity == "regional_daily_summary"
            else "One retained grid-point observation; no spatial aggregation",
            "quality_policy": "Producer valid status is eligible; invalid and explicitly excluded statuses are retained separately",
            "uncertainty_policy": "Reported uncertainty has the same temperature interval unit as value; null means unknown",
            "qualification": "Synthetic local acceptance only; not scientific publication or approval",
            "methods": [
                "Final and interim products remain separate",
                "No inferred grid observations or timestamps",
            ],
            "table": {
                "name": "observations",
                "object_id": f"{dataset_id}:table:observations",
                "row_count": count,
                "availability": {"status": "available"},
                "completeness": "complete",
            },
        }
    )
    return metadata, {"observations": frame}


def seal_sst_fixture(store, datasets, *, publication="publication-1"):
    """Seal only explicit synthetic datasets; do not change a latest pointer."""
    from ingestion.sst_catalogue_inputs import dataset_exports

    objects, contents, sources = [], {}, {}
    for metadata, frames in datasets:
        captured = dataset_exports(metadata, frames, generation=publication)
        objects.extend(captured.objects)
        if set(contents) & set(captured.contents):
            raise ValueError("Duplicate SST synthetic object identity")
        contents.update(captured.contents)
        sources[metadata.source_id] = SourceCapture(
            source_id=metadata.source_id,
            source_family="remote_sensing",
            source_generation=publication,
            publication_generation=publication,
            classification_generation="no-scientific-approval-v1",
            relationship_generation="no-unified-samples-v1",
            operation_generation="c11-v1",
            capture_method="synthetic-c11-frozen-parquet-v1",
            qualifiers=[metadata.qualification],
        )
    manifest = SnapshotManifest(
        scope=sst_scope(),
        source_captures=list(sources.values()),
        objects=objects,
        operation_versions={obj.operation_id: obj.operation_version for obj in objects},
    )
    return store.seal(manifest, contents)
