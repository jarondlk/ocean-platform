"""Explicit synthetic C12 relational inputs; never a runtime fallback."""

from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json

import pandas as pd

from retrieval.source_scope import EvidenceScope, FAMILIES
from schema.catalogue_snapshot import SnapshotManifest, SourceCapture
from schema.edna_catalogue import EDNADataset, RAW_METHODS, TABLE_COLUMNS


def edna_scope(**filters):
    return EvidenceScope.model_validate(
        {
            "version": 1,
            "sources": {
                family: {
                    "enabled": family == "edna_metabarcoding",
                    "filters": filters if family == "edna_metabarcoding" else {},
                }
                for family in FAMILIES
            },
        }
    )


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def edna_fixture(
    count=1205,
    *,
    dataset_id="synthetic:edna:project-a",
    source_id="synthetic-edna",
    provider_project_id="ProjectA",
):
    """One occurrence/assay and four alternative method rows per occurrence.

    Deliberate exceptions: 1 control, 2 unknown, 3 inactive occurrence,
    4 inactive assay, 5 incomplete protocol, 6 available empty methods,
    7 unavailable 3nn target, 8 different assay protocol. Index zero preserves
    measured zero concentration/reads. These alternatives share sequence
    evidence and must never be summed as independent biological observations.
    """
    if type(count) is not int or not 0 <= count <= 20_000:
        raise ValueError("Synthetic eDNA count must fit explicit fixture bounds")
    rows = {role: [] for role in TABLE_COLUMNS}
    source_snapshot = _hash([source_id, provider_project_id, "source-snapshot"])
    for index in range(count):
        sample = _hash([dataset_id, "occurrence", index])
        assay = _hash([dataset_id, "assay", index])
        provider_sample = f"synthetic-sample-{index:06d}"
        occurrence = {
            "sample_id": sample,
            "source_occurrence_id": sample,
            "provider": "synthetic-provider",
            "provider_locus": "MiFish",
            "provider_team": "SyntheticTeam",
            "provider_project_id": provider_project_id,
            "provider_run_id": f"synthetic-run-{index:06d}",
            "collection_date_utc": (
                date(2024, 1, 1) + timedelta(days=index % 366)
            ).isoformat(),
            "temporal_precision": "date",
            "lat": 38.5,
            "lon": 141.5,
            "coordinate_precision": "provider_grid_unconfirmed",
            "identity_status": "unresolved_physical_sample",
            "physical_sample_id": None,
            "active": index != 3,
            "source_snapshot_id": source_snapshot,
            "provider_sample_id": provider_sample,
        }
        occurrence["scientific_content_sha256"] = _hash(occurrence)
        rows["occurrences"].append(occurrence)
        kind = (
            "negative_control"
            if index == 1
            else "unknown"
            if index == 2
            else "environmental"
        )
        rows["classifications"].append(
            {
                "sample_id": sample,
                "sample_kind": kind,
                "is_control": True if index == 1 else None if index == 2 else False,
                "classification_basis": "synthetic provider classification; no researcher approval",
                "classification_review_json": None,
                "source_snapshot_id": source_snapshot,
                "provider_sample_id": provider_sample,
            }
        )
        available = [
            method
            for method in RAW_METHODS
            if not (index == 7 and method == "qcauto_95pct_3nn_target")
        ]
        availability = {
            method: {
                "status": "available",
                "source_file_id": _hash([assay, method, "source"]),
                "source_snapshot_id": source_snapshot,
                "row_count": 0 if index == 6 else 1,
            }
            for method in available
        }
        assay_row = {
            "assay_id": assay,
            "sample_id": sample,
            "target_gene": "18S" if index == 8 else "12S",
            "primer_set": None if index == 5 else "Synthetic-MiFish",
            "sequencing_method": "synthetic-amplicon-sequencing",
            "library_layout": "PAIRED",
            "instrument_model": "synthetic-instrument",
            "community_availability_json": json.dumps(
                availability, sort_keys=True, separators=(",", ":")
            ),
            "active": index != 4,
        }
        assay_row["scientific_content_sha256"] = _hash(assay_row)
        rows["assays"].append(assay_row)
        if index == 6:
            continue
        for method in available:
            taxonomy = (
                {"genus": "Scomber", "species": "Scomber japonicus"}
                if index % 2 == 0
                else {"genus": "Scomber", "species": "unknown fish"}
            )
            taxon_name = "Scomber japonicus" if index % 2 == 0 else "Scomber"
            concentration = None if index % 3 else float(index)
            detection = {
                "detection_id": _hash([assay, method, "detection"]),
                "assay_id": assay,
                "assignment_method": method,
                "target_status": "nontarget"
                if method.endswith("_nontarget")
                else "target",
                "read_count": index,
                "copies_per_ml": concentration,
                "concentration_status": "reported"
                if concentration is not None
                else "missing"
                if index % 3 == 1
                else "column_absent",
                "sequence_sha256": _hash([assay, "sequence"]),
                "assigned_taxon_name": taxon_name,
                "assigned_taxon_rank": "species" if index % 2 == 0 else "genus",
                "taxonomy_json": json.dumps(
                    taxonomy, sort_keys=True, separators=(",", ":")
                ),
                "active": True,
            }
            detection["scientific_content_sha256"] = _hash(detection)
            rows["detections"].append(detection)
    frames = {
        role: pd.DataFrame(value, columns=TABLE_COLUMNS[role])
        for role, value in rows.items()
    }
    frames["detections"] = frames["detections"].astype(
        {"read_count": "Int64", "copies_per_ml": "Float64"}
    )
    frames["occurrences"] = frames["occurrences"].astype(
        {"lat": "Float64", "lon": "Float64"}
    )
    metadata = EDNADataset.model_validate(
        {
            "dataset_id": dataset_id,
            "source_id": source_id,
            "provider": "synthetic-provider",
            "provider_locus": "MiFish",
            "provider_team": "SyntheticTeam",
            "provider_project_id": provider_project_id,
            "collection_id": f"{dataset_id}:collection",
            "title": {
                "en": "Synthetic canonical eDNA project",
                "ja": "合成正規eDNAプロジェクト",
            },
            "purpose": {
                "en": "Frozen raw inventory and qualified descriptive cohorts",
                "ja": "固定の生インベントリと条件付き記述集団",
            },
            "descriptor": {
                "family": "edna_metabarcoding",
                "protocol_id": "synthetic-mixed-protocols",
                "protocol": "Mixed retained assay protocols; inspect assay records",
                "population": "raw_inventory",
                "assignment_method": "mixed",
                "sample_kind": "mixed",
                "is_control": None,
                "measurement": "assigned_reads",
                "unit": "reads",
            },
            "qualification": "Synthetic source occurrences are not independently resolved physical samples; raw inventory grants no scientific approval",
            "methods": [
                "Four alternative assignment methods retain shared sequence evidence",
                "Scientific eligibility requires active environmental records, complete assay protocols and source-backed supported methods",
                "Reads are not organism abundance; filtered zero is not ecological absence",
            ],
            "tables": [
                {
                    "name": role,
                    "object_id": f"{dataset_id}:table:{role}",
                    "row_count": len(frame),
                    "availability": {"status": "available"},
                    "completeness": "complete",
                }
                for role, frame in frames.items()
            ],
        }
    )
    return metadata, frames


def seal_edna_fixture(
    store, datasets, *, publication="publication-1", classification="classification-1"
):
    """Seal explicit synthetic inputs only, retaining all source generations."""
    from ingestion.edna_catalogue_inputs import dataset_exports

    objects, contents, sources = [], {}, {}
    for metadata, frames in datasets:
        exported = dataset_exports(metadata, frames, generation=publication)
        objects.extend(exported.objects)
        if set(contents) & set(exported.contents):
            raise ValueError("Duplicate eDNA synthetic object identity")
        contents.update(exported.contents)
        capture = SourceCapture(
            source_id=metadata.source_id,
            source_family="edna_metabarcoding",
            source_generation=publication,
            publication_generation=publication,
            classification_generation=classification,
            relationship_generation="unresolved-physical-samples-v1",
            operation_generation="c12-v1",
            capture_method="synthetic-c12-frozen-parquet-v1",
            qualifiers=[metadata.qualification],
        )
        if metadata.source_id in sources and sources[metadata.source_id] != capture:
            raise ValueError("Conflicting eDNA synthetic source capture")
        sources[metadata.source_id] = capture
    manifest = SnapshotManifest(
        scope=edna_scope(),
        source_captures=list(sources.values()),
        objects=objects,
        operation_versions={obj.operation_id: obj.operation_version for obj in objects},
    )
    return store.seal(manifest, contents)
