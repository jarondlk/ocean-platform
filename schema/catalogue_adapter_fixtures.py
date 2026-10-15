"""C10 synthetic frozen scientific fixtures, never a runtime fallback."""

from __future__ import annotations

import pandas as pd

from ingestion.catalogue_adapter_inputs import dataset_exports
from retrieval.source_scope import EvidenceScope, FAMILIES
from schema.catalogue_adapter import FrozenDataset, FrozenTable, REQUIRED_COLUMNS
from schema.catalogue_snapshot import SnapshotManifest, SourceCapture


def adapter_scope(*families, **filters):
    return EvidenceScope.model_validate(
        {
            "version": 1,
            "sources": {
                family: {
                    "enabled": family in families,
                    "filters": filters if family in families else {},
                }
                for family in FAMILIES
            },
        }
    )


def _table(
    dataset_id,
    name,
    frame,
    *,
    units=None,
    extra_types=None,
    entity=None,
    completeness="complete",
    method=None,
    abundance_denominator=None,
):
    types = {**REQUIRED_COLUMNS[name], **(extra_types or {})}
    return FrozenTable.model_validate(
        {
            "name": name,
            "object_id": f"{dataset_id}:table:{name}",
            "row_count": len(frame),
            "entity": entity
            or {
                "casts": "casts",
                "depth_observations": "depth_observations",
                "collections": "libraries",
                "run_qc": "sequencing_runs",
                "ranked_taxa": "ranked_taxa",
            }.get(name, "library_taxon_cells"),
            "denominator": f"All retained matching {name} records in this source dataset",
            "columns": [
                {
                    "name": column,
                    "dtype": types[column],
                    "nullable": column
                    not in {
                        "cast_id",
                        "observation_id",
                        "sample_id",
                        "library_id",
                        "measurement_id",
                        "summary_id",
                        "run_id",
                        "has_kraken",
                        "has_metaeuk",
                    },
                    "unit": (units or {}).get(column),
                    "description": f"Synthetic source-owned {column}",
                }
                for column in frame.columns
            ],
            "availability": {"status": "available"},
            "completeness": completeness,
            "method": method,
            "taxonomic_rank": "genus" if name.endswith("abundance") else None,
            "abundance_denominator": abundance_denominator,
        }
    )


def ctd_fixture(
    count=1205, *, dataset_id="synthetic:ctd:campaign-a", source_id="synthetic-ctd"
):
    casts, depths = [], []
    for i in range(count):
        cast = f"cast-{i:06d}"
        casts.append(
            {
                "cast_id": cast,
                "sample_id": "shared-label" if i == 0 else f"sample-{i:06d}",
                "collection_date": "2024-01-01" if i % 2 == 0 else "2024-01-02",
                "bay": "O",
                "station": "station-1" if i % 2 == 0 else "station-2",
            }
        )
        for j in range(2):
            depths.append(
                {
                    "observation_id": f"obs-{i:06d}-{j}",
                    "cast_id": cast,
                    "depth": float(j * 10),
                    "temperature": -1.5 if i == j == 0 else float(i + j),
                    "salinity": 30.0 + j,
                }
            )
    frames = {
        "casts": pd.DataFrame(casts, columns=list(REQUIRED_COLUMNS["casts"])),
        "depth_observations": pd.DataFrame(
            depths,
            columns=[
                *REQUIRED_COLUMNS["depth_observations"],
                "temperature",
                "salinity",
            ],
        ),
    }
    tables = [
        _table(
            dataset_id,
            name,
            frame,
            units={"depth": "m", "temperature": "degC", "salinity": "PSU"},
            extra_types={"temperature": "number", "salinity": "number"},
        )
        for name, frame in frames.items()
    ]
    metadata = FrozenDataset.model_validate(
        {
            "dataset_id": dataset_id,
            "source_id": source_id,
            "family": "ctd",
            "collection_id": f"{dataset_id}:collection",
            "title": {"en": "Synthetic CTD campaign", "ja": "合成CTD観測"},
            "purpose": {
                "en": "Frozen cast and depth acceptance",
                "ja": "観測と深度の検証",
            },
            "descriptor": {
                "family": "ctd",
                "sampling_contract": "Observed campaign casts only; no expected sampling schedule",
                "observation_entity": "cast",
                "measurement": "temperature",
                "unit": "degC",
                "depth_unit": "m",
            },
            "collection_date_precision": "day",
            "depth_convention": "positive_down",
            "qualification": "Synthetic local acceptance only; not scientific publication",
            "methods": [
                "Distinct source-owned casts and depth observations; no inferred expected casts"
            ],
            "tables": tables,
        }
    )
    return metadata, frames


def metagenome_fixture(
    count=601,
    *,
    dataset_id="synthetic:metagenome:collection-a",
    source_id="synthetic-metagenome",
):
    collections, runs, kraken, metaeuk, ranked = [], [], [], [], []
    taxa = ["BeyondTopTen", "MeasuredZero", "MissingCell", "Trend"]
    for i in range(count):
        library = f"library-{i:06d}"
        collections.append(
            {
                "library_id": library,
                "sample_id": "shared-label" if i == 0 else f"meta-{i:06d}",
                "collection_date": "2024-01" if i % 2 == 0 else "2024-02",
                "bay": "O",
                "station": "station-1",
                "has_kraken": True,
                "has_metaeuk": True,
            }
        )
        runs.append(
            {
                "run_id": f"run-{i:06d}",
                "library_id": library,
                "run_date": "2025-07-01",
                "sequencing_method": "synthetic-long-read",
                "reads": 1000 + i,
                "bases": 100000 + i,
            }
        )
        for j, taxon in enumerate(taxa):
            for method, records in [("Kraken", kraken), ("MetaEuk", metaeuk)]:
                abundance = (
                    None
                    if taxon == "MissingCell"
                    else 0.0
                    if taxon == "MeasuredZero"
                    else (
                        (0.05 if method == "Kraken" else 0.15)
                        if taxon == "BeyondTopTen"
                        else (i + 1) / (count + 1)
                    )
                )
                records.append(
                    {
                        "measurement_id": f"{method}-{i:06d}-{j}",
                        "library_id": library,
                        "taxon": taxon,
                        "method": method,
                        "taxonomic_rank": "genus",
                        "abundance": abundance,
                    }
                )
        ranked.append(
            {
                "summary_id": f"summary-{i:06d}",
                "library_id": library,
                "taxon": "Trend",
                "method": "Kraken",
                "abundance": (i + 1) / (count + 1),
            }
        )
    frames = {
        "collections": pd.DataFrame(
            collections, columns=list(REQUIRED_COLUMNS["collections"])
        ),
        "run_qc": pd.DataFrame(
            runs,
            columns=[
                *REQUIRED_COLUMNS["run_qc"],
                "sequencing_method",
                "reads",
                "bases",
            ],
        ),
        "kraken_abundance": pd.DataFrame(
            kraken, columns=list(REQUIRED_COLUMNS["kraken_abundance"])
        ),
        "metaeuk_abundance": pd.DataFrame(
            metaeuk, columns=list(REQUIRED_COLUMNS["metaeuk_abundance"])
        ),
        "ranked_taxa": pd.DataFrame(
            ranked, columns=list(REQUIRED_COLUMNS["ranked_taxa"])
        ),
    }
    tables = [
        _table(
            dataset_id,
            name,
            frame,
            units={"abundance": "fraction", "reads": "reads", "bases": "bases"},
            extra_types={
                "sequencing_method": "string",
                "reads": "integer",
                "bases": "integer",
            },
            completeness="partial" if name == "ranked_taxa" else "complete",
            method="Kraken"
            if name == "kraken_abundance"
            else "MetaEuk"
            if name == "metaeuk_abundance"
            else None,
            abundance_denominator=f"{name} method-classified reads per library"
            if name.endswith("abundance")
            else None,
        )
        for name, frame in frames.items()
    ]
    metadata = FrozenDataset.model_validate(
        {
            "dataset_id": dataset_id,
            "source_id": source_id,
            "family": "metagenome",
            "collection_id": f"{dataset_id}:collection",
            "title": {"en": "Synthetic metagenome collection", "ja": "合成メタゲノム"},
            "purpose": {
                "en": "Complete method-owned normalized abundance",
                "ja": "手法別の全正規化データ",
            },
            "descriptor": {
                "family": "metagenome",
                "measurement": "normalized_abundance",
                "abundance_unit": "fraction",
                "abundance_denominator": "See each retained method table",
                "method": "Kraken and MetaEuk, kept separate",
                "taxonomic_rank": "genus",
                "omitted_taxa": "retained_elsewhere",
            },
            "collection_date_precision": "month",
            "qualification": "Synthetic local acceptance only; collection months are not sequencing dates",
            "methods": [
                "Kraken and MetaEuk use separate normalized tables",
                "Ranked omission is unknown, explicit normalized zero is measured zero",
            ],
            "tables": tables,
        }
    )
    return metadata, frames


def seal_fixture(store, datasets, *, generation="synthetic-generation-1"):
    """Seal explicit synthetic datasets; never promote latest or access a real source."""
    objects, contents, sources = [], {}, {}
    for metadata, frames in datasets:
        captured = dataset_exports(metadata, frames, generation=generation)
        objects.extend(captured.objects)
        if set(contents) & set(captured.contents):
            raise ValueError("Duplicate synthetic object identity")
        contents.update(captured.contents)
        sources[metadata.source_id] = SourceCapture(
            source_id=metadata.source_id,
            source_family=metadata.family,
            source_generation=generation,
            publication_generation=generation,
            classification_generation="no-scientific-approval-v1",
            relationship_generation="no-unified-samples-v1",
            operation_generation="c10-v1",
            capture_method="synthetic-c10-frozen-parquet-v1",
            qualifiers=[metadata.qualification],
        )
    manifest = SnapshotManifest(
        scope=adapter_scope(*{s.source_family for s in sources.values()}),
        source_captures=list(sources.values()),
        objects=objects,
        operation_versions={obj.operation_id: obj.operation_version for obj in objects},
    )
    return store.seal(manifest, contents)
