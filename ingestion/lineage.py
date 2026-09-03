"""
Traceability manifest and upsert dry-run planning.

This module is intentionally read-only with respect to the operational
database. It creates a provenance-first view of source files, generated
artifacts, retrieval documents, and embedding treatment so incremental database
updates can be planned before any mutation path exists.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text

import config
from retrieval.edna_publication import retrieval_path as edna_retrieval_path


MANIFEST_SCHEMA_VERSION = 1
LATEST_MANIFEST_NAME = "latest_provenance_manifest.json"


@dataclass
class SourceFileTrace:
    id: str
    source_dataset: str
    path: str
    role: str
    exists: bool
    sha256: Optional[str] = None
    collection_fingerprint: Optional[str] = None
    file_size_bytes: Optional[int] = None
    child_count: Optional[int] = None
    modified_at: Optional[str] = None
    registry_seen: bool = False
    registry_records: int = 0
    latest_processing_run: Optional[str] = None
    notes: Optional[str] = None
    source_url: Optional[str] = None
    source_snapshot_id: Optional[str] = None


@dataclass
class ArtifactVersion:
    id: str
    label: str
    kind: str
    path: str
    producer: str
    producer_stage: str
    source_file_ids: List[str] = field(default_factory=list)
    input_artifact_ids: List[str] = field(default_factory=list)
    table_name: Optional[str] = None
    key_columns: List[str] = field(default_factory=list)
    exists: bool = False
    sha256: Optional[str] = None
    row_count: Optional[int] = None
    columns: List[str] = field(default_factory=list)
    schema_hash: Optional[str] = None
    file_size_bytes: Optional[int] = None
    modified_at: Optional[str] = None
    notes: Optional[str] = None
    source_snapshot_id: Optional[str] = None


@dataclass
class DocumentTrace:
    doc_id: str
    source_type: str
    sample_id: Optional[str]
    event_id: Optional[str]
    time: Optional[str]
    title: str
    content_hash: str
    metadata_hash: str
    lineage_level: str
    source_file_ids: List[str]
    source_artifact_ids: List[str]
    source_record_keys: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingTrace:
    doc_id: str
    content_hash: Optional[str]
    embedding_status: str
    embedding_model: str
    embedding_dim: int
    embedding_source: str
    embedded: Optional[bool] = None
    notes: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedded_at: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _modified_at(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _collection_fingerprint(path: Path, pattern: str = "*.nc") -> Tuple[Optional[str], int]:
    if not path.exists() or not path.is_dir():
        return None, 0
    rows = []
    for child in sorted(path.rglob(pattern)):
        if not child.is_file():
            continue
        stat = child.stat()
        try:
            rel = str(child.relative_to(path))
        except ValueError:
            rel = str(child)
        rows.append({"path": rel, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return _stable_hash(rows), len(rows)


def _jsonl_rows(path: Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _artifact_columns(path: Path) -> List[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        if path.suffix == ".parquet":
            return list(pd.read_parquet(path).columns)
        if path.suffix == ".jsonl":
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        row = json.loads(line)
                        return sorted(row.keys()) if isinstance(row, dict) else []
    except Exception:
        return []
    return []


def _artifact_row_count(path: Path) -> Optional[int]:
    if not path.exists() or not path.is_file():
        return None
    try:
        if path.suffix == ".parquet":
            return int(len(pd.read_parquet(path)))
        if path.suffix == ".jsonl":
            return _jsonl_rows(path)
    except Exception:
        return None
    return None


def _read_registry_records() -> List[Dict[str, Any]]:
    path = config.PROVENANCE_DIR / "provenance.jsonl"
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _registry_matches(records: List[Dict[str, Any]], path: Path, dataset: str) -> List[Dict[str, Any]]:
    path_text = str(path)
    name = path.name
    matches = []
    for record in records:
        source_file = str(record.get("source_file") or "")
        source_dataset = str(record.get("source_dataset") or "")
        if source_file == path_text or (source_dataset == dataset and Path(source_file).name == name):
            matches.append(record)
    return matches


def _latest_processing_run(records: List[Dict[str, Any]]) -> Optional[str]:
    if not records:
        return None
    records_sorted = sorted(records, key=lambda row: str(row.get("ingested_at") or ""))
    return records_sorted[-1].get("processing_run")


def _resolve_anemone_lineage_bundle(
    normalization_id: Optional[str] = None,
) -> Optional[Tuple[Path, Dict[str, Any]]]:
    """Resolve an immutable bundle, returning None when no active one exists."""
    pointer = config.ANEMONE_NORMALIZED_DIR / "current.json"
    if normalization_id is None and not pointer.exists():
        return None
    from preprocessing.anemone import resolve_normalized_bundle

    return resolve_normalized_bundle(
        normalization_id,
        normalized_root=config.ANEMONE_NORMALIZED_DIR,
    )


def _anemone_source_file_traces(normalization_id: Optional[str] = None) -> List[SourceFileTrace]:
    resolved = _resolve_anemone_lineage_bundle(normalization_id)
    if resolved is None:
        return []
    root, manifest = resolved
    artifact = manifest.get("artifacts", {}).get("external_source_file")
    if not artifact:
        return []
    frame = pd.read_parquet(root / str(artifact["path"]))
    raw_snapshot_root = (
        config.RAW_ANEMONE_DIR
        / "snapshots"
        / str(manifest["source_snapshot_id"])
    )
    traces: List[SourceFileTrace] = []
    for row in frame.to_dict(orient="records"):
        relative_path = str(row.get("relative_path") or "")
        local_path = raw_snapshot_root / relative_path
        source_file_id = str(row.get("source_file_id") or "")
        traces.append(
            SourceFileTrace(
                id=f"raw:anemone:{source_file_id}",
                source_dataset="anemone_mifish",
                path=str(local_path),
                role=str(row.get("role") or "source_file"),
                exists=local_path.is_file(),
                sha256=(
                    str(row["sha256"])
                    if row.get("sha256") and not pd.isna(row.get("sha256"))
                    else None
                ),
                file_size_bytes=(
                    int(row["size_bytes"])
                    if row.get("size_bytes") is not None
                    and not pd.isna(row.get("size_bytes"))
                    else None
                ),
                modified_at=_modified_at(local_path),
                source_url=str(row.get("source_url") or ""),
                source_snapshot_id=str(manifest["source_snapshot_id"]),
                notes=(
                    f"snapshot={manifest['source_snapshot_id']}; "
                    f"selection={row.get('selection_status')}; "
                    f"source_url={row.get('source_url')}"
                ),
            )
        )
    return traces


def _database_anemone_source_file_traces() -> List[SourceFileTrace]:
    """Read immutable external-file provenance across all loaded eDNA scopes."""
    try:
        engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT source_file_id, snapshot_id, relative_path, "
                    "source_url, role, sha256, size_bytes, last_modified, "
                    "selection_status, validation_status "
                    "FROM external_source_file ORDER BY source_file_id"
                )
            ).mappings().all()
    except Exception:
        return []
    return [
        SourceFileTrace(
            id=f"raw:anemone:{row['source_file_id']}",
            source_dataset="anemone_mifish",
            path=str(row.get("source_url") or row.get("relative_path") or ""),
            role=str(row.get("role") or "source_file"),
            exists=True,
            sha256=str(row["sha256"]) if row.get("sha256") else None,
            file_size_bytes=(
                int(row["size_bytes"])
                if row.get("size_bytes") is not None
                else None
            ),
            modified_at=(
                str(row["last_modified"])
                if row.get("last_modified")
                else None
            ),
            registry_seen=True,
            source_url=str(row.get("source_url") or ""),
            source_snapshot_id=str(row.get("snapshot_id") or ""),
            registry_records=1,
            notes=(
                f"snapshot={row.get('snapshot_id')}; "
                f"selection={row.get('selection_status')}; "
                f"validation={row.get('validation_status')}; "
                f"source_url={row.get('source_url')}"
            ),
        )
        for row in rows
    ]


def build_source_file_traces() -> List[SourceFileTrace]:
    registry_records = _read_registry_records()
    rows: List[SourceFileTrace] = []
    for key, path in sorted(config.RAW_FILES.items()):
        matches = _registry_matches(registry_records, path, key)
        rows.append(
            SourceFileTrace(
                id=f"raw:{key}",
                source_dataset=key,
                path=str(path),
                role="raw_file",
                exists=path.exists(),
                sha256=_sha256_file(path),
                file_size_bytes=path.stat().st_size if path.exists() and path.is_file() else None,
                modified_at=_modified_at(path),
                registry_seen=bool(matches),
                registry_records=len(matches),
                latest_processing_run=_latest_processing_run(matches),
            )
        )

    sst_fingerprint, sst_count = _collection_fingerprint(config.SST_NETCDF_DIR)
    sst_matches = [row for row in registry_records if row.get("source_dataset") == "sst_netcdf"]
    rows.append(
        SourceFileTrace(
            id="raw:sst_netcdf",
            source_dataset="sst_netcdf",
            path=str(config.SST_NETCDF_DIR),
            role="raw_collection",
            exists=config.SST_NETCDF_DIR.exists(),
            collection_fingerprint=sst_fingerprint,
            child_count=sst_count,
            modified_at=_modified_at(config.SST_NETCDF_DIR),
            registry_seen=bool(sst_matches),
            registry_records=len(sst_matches),
            latest_processing_run=_latest_processing_run(sst_matches),
            notes="Collection fingerprint is based on child paths, sizes, and mtimes; per-file SHA records come from provenance.jsonl.",
        )
    )

    himawari_fingerprint, himawari_count = _collection_fingerprint(config.HIMAWARI_RAW_DIR, pattern="*")
    rows.append(
        SourceFileTrace(
            id="raw:himawari_raw",
            source_dataset="himawari_raw",
            path=str(config.HIMAWARI_RAW_DIR),
            role="optional_raw_collection",
            exists=config.HIMAWARI_RAW_DIR.exists(),
            collection_fingerprint=himawari_fingerprint,
            child_count=himawari_count,
            modified_at=_modified_at(config.HIMAWARI_RAW_DIR),
            notes="Optional raw Himawari DAT directory.",
        )
    )
    anemone_by_id = {
        row.id: row for row in _database_anemone_source_file_traces()
    }
    normalization_ids = sorted({
        spec["id"].split(":")[2]
        for spec in _active_anemone_artifact_specs()
    })
    for normalization_id in normalization_ids:
        anemone_by_id.update({
            row.id: row
            for row in _anemone_source_file_traces(normalization_id)
        })
    rows.extend(anemone_by_id[key] for key in sorted(anemone_by_id))
    return rows


def _anemone_artifact_specs(normalization_id: Optional[str] = None) -> List[Dict[str, Any]]:
    resolved = _resolve_anemone_lineage_bundle(normalization_id)
    if resolved is None:
        return []
    root, manifest = resolved
    normalization_id = str(manifest["normalization_id"])
    source_file_artifact = manifest.get("artifacts", {}).get(
        "external_source_file"
    )
    source_file_ids: List[str] = []
    if source_file_artifact:
        frame = pd.read_parquet(root / str(source_file_artifact["path"]))
        source_file_ids = [
            f"raw:anemone:{value}"
            for value in frame.get("source_file_id", pd.Series(dtype="string"))
            .dropna()
            .astype(str)
            .tolist()
        ]
    table_keys = {
        "external_source_snapshot": ("external_source_snapshot", ["snapshot_id"]),
        "external_source_file": ("external_source_file", ["source_file_id"]),
        "edna_sample": ("edna_sample", ["sample_id"]),
        "edna_assay": ("edna_assay", ["assay_id"]),
        "edna_detection": ("edna_detection", ["detection_id"]),
        "edna_internal_standard": (
            "edna_internal_standard",
            ["internal_standard_id"],
        ),
        "edna_anchor_event": (None, ["event_id"]),
    }
    specs: List[Dict[str, Any]] = []
    for name, artifact in sorted(manifest.get("artifacts", {}).items()):
        table_name, key_columns = table_keys.get(name, (None, []))
        specs.append(
            {
                "id": f"normalized:anemone:{normalization_id}:{name}",
                "label": name,
                "kind": "normalized",
                "path": root / str(artifact["path"]),
                "producer": "scripts/normalize_anemone.py",
                "producer_stage": "normalize_anemone",
                "source_file_ids": source_file_ids,
                "table_name": table_name,
                "key_columns": key_columns,
                "source_snapshot_id": str(manifest["source_snapshot_id"]),
                "notes": (
                    f"normalization_id={normalization_id}; "
                    f"source_snapshot_id={manifest['source_snapshot_id']}; "
                    "active=true"
                ),
            }
        )
    return specs


def _active_anemone_artifact_specs() -> List[Dict[str, Any]]:
    """Include normalized bundles referenced by any active eDNA scope."""
    specs = _anemone_artifact_specs()
    known = {spec["source_snapshot_id"] for spec in specs}
    needed: set[str] = set()
    documents = _read_retrieval_documents()
    for row in documents.to_dict(orient="records"):
        if row.get("source_type") != "edna_metabarcoding":
            continue
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            metadata = json.loads(row.get("metadata_json") or "{}")
        needed.update(metadata.get("source_snapshot_ids") or [])
    for path in sorted(config.ANEMONE_NORMALIZED_DIR.glob("snapshots/*/normalization_manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        snapshot_id = manifest.get("source_snapshot_id")
        if snapshot_id not in needed or snapshot_id in known:
            continue
        historical = _anemone_artifact_specs(path.parent.name)
        for spec in historical:
            # Only the current bundle is a canonical upsert candidate.
            spec["table_name"] = None
        specs.extend(historical)
        known.add(snapshot_id)
    return specs


def _artifact_specs() -> List[Dict[str, Any]]:
    specs = [
        {
            "id": "normalized:ctd_profile",
            "label": "ctd_profile_standardized",
            "kind": "normalized",
            "path": config.NORMALIZED_DIR / "ctd_profile_standardized.parquet",
            "producer": "scripts/ingest.py",
            "producer_stage": "ingest",
            "source_file_ids": ["raw:ctd"],
            "table_name": "ctd_profile",
            "key_columns": ["sample_id", "ctd_date", "depth_m"],
        },
        {
            "id": "normalized:ctd_summary",
            "label": "ctd_summary",
            "kind": "normalized",
            "path": config.NORMALIZED_DIR / "ctd_summary.parquet",
            "producer": "scripts/ingest.py",
            "producer_stage": "ingest",
            "source_file_ids": ["raw:ctd"],
            "table_name": "ctd_summary",
            "key_columns": ["sample_id"],
        },
        {
            "id": "normalized:sample_qc",
            "label": "sample_qc",
            "kind": "normalized",
            "path": config.NORMALIZED_DIR / "sample_qc.parquet",
            "producer": "scripts/ingest.py",
            "producer_stage": "ingest",
            "source_file_ids": ["raw:runid", "raw:read_summary", "raw:coverage_log"],
        },
        {
            "id": "normalized:kraken",
            "label": "kraken_genus_enriched",
            "kind": "normalized",
            "path": config.NORMALIZED_DIR / "kraken_genus_enriched.parquet",
            "producer": "scripts/ingest.py",
            "producer_stage": "ingest",
            "source_file_ids": ["raw:kraken_genus_sample_tsv", "raw:kraken_genus_group", "raw:gn_consistency"],
        },
        {
            "id": "normalized:metaeuk",
            "label": "metaeuk_genus_enriched",
            "kind": "normalized",
            "path": config.NORMALIZED_DIR / "metaeuk_genus_enriched.parquet",
            "producer": "scripts/ingest.py",
            "producer_stage": "ingest",
            "source_file_ids": ["raw:metaeuk_genus_sample", "raw:genus_group", "raw:gn_consistency"],
        },
        {
            "id": "normalized:sst_point",
            "label": "sst_point_timeseries",
            "kind": "normalized",
            "path": config.NORMALIZED_DIR / "sst_point_timeseries.parquet",
            "producer": "scripts/ingest.py",
            "producer_stage": "ingest",
            "source_file_ids": ["raw:sst_netcdf"],
            "table_name": "sst_point_observation",
            "key_columns": ["file", "time_utc"],
        },
        {
            "id": "normalized:sst_daily",
            "label": "sst_daily_summary",
            "kind": "normalized",
            "path": config.NORMALIZED_DIR / "sst_daily_summary.parquet",
            "producer": "scripts/ingest.py",
            "producer_stage": "ingest",
            "source_file_ids": ["raw:sst_netcdf"],
            "table_name": "sst_daily_summary",
            "key_columns": ["date_jst"],
        },
        {
            "id": "serving:sample_registry",
            "label": "sample_registry",
            "kind": "serving",
            "path": config.SERVING_DIR / "sample_registry.parquet",
            "producer": "scripts/ingest.py",
            "producer_stage": "ingest",
            "source_file_ids": ["raw:ctd", "raw:runid", "raw:kraken_genus_sample_tsv", "raw:metaeuk_genus_sample"],
        },
        {
            "id": "serving:sample_context",
            "label": "sample_multisource_context",
            "kind": "serving",
            "path": config.SERVING_DIR / "sample_multisource_context.parquet",
            "producer": "scripts/ingest.py",
            "producer_stage": "ingest",
            "source_file_ids": ["raw:ctd", "raw:runid", "raw:kraken_genus_sample_tsv", "raw:metaeuk_genus_sample"],
            "table_name": "metagenome_sample",
            "key_columns": ["sample_id"],
        },
        {
            "id": "canonical:anchors",
            "label": "anchor_events",
            "kind": "canonical",
            "path": config.CANONICAL_DIR / "anchor_events.parquet",
            "producer": "scripts/build_retrieval_docs.py",
            "producer_stage": "build_retrieval_docs",
            "input_artifact_ids": ["serving:sample_registry", "normalized:ctd_summary", "normalized:sst_daily"],
            "table_name": "anchor_event",
            "key_columns": ["event_id"],
        },
        {
            "id": "canonical:links",
            "label": "cross_source_links",
            "kind": "canonical",
            "path": config.CANONICAL_DIR / "cross_source_links.parquet",
            "producer": "scripts/build_retrieval_docs.py",
            "producer_stage": "build_retrieval_docs",
            "input_artifact_ids": ["canonical:anchors"],
            "table_name": "cross_source_link",
            "key_columns": ["source_event_id", "target_event_id", "link_type"],
        },
        {
            "id": "serving:retrieval_parquet",
            "label": "retrieval_documents.parquet",
            "kind": "serving",
            "path": config.SERVING_DIR / "retrieval_documents.parquet",
            "producer": "scripts/build_retrieval_docs.py",
            "producer_stage": "build_retrieval_docs",
            "input_artifact_ids": [
                "normalized:ctd_summary",
                "normalized:ctd_profile",
                "serving:sample_context",
                "normalized:sst_daily",
                "normalized:sst_point",
            ],
            "table_name": "retrieval_document",
            "key_columns": ["doc_id"],
        },
        {
            "id": "serving:retrieval_jsonl",
            "label": "retrieval_documents.jsonl",
            "kind": "serving",
            "path": config.SERVING_DIR / "retrieval_documents.jsonl",
            "producer": "scripts/build_retrieval_docs.py",
            "producer_stage": "build_retrieval_docs",
            "input_artifact_ids": ["serving:retrieval_parquet"],
        },
        {
            "id": "serving:edna_retrieval_parquet",
            "label": "anemone_retrieval_documents.parquet",
            "kind": "serving",
            "path": edna_retrieval_path("parquet"),
            "producer": "scripts/materialize_edna_retrieval.py",
            "producer_stage": "materialize_edna_retrieval",
            "table_name": "retrieval_document",
            "key_columns": ["doc_id"],
            "notes": "Database-wide active eDNA retrieval corpus.",
        },
        {
            "id": "serving:edna_retrieval_jsonl",
            "label": "anemone_retrieval_documents.jsonl",
            "kind": "serving",
            "path": edna_retrieval_path("jsonl"),
            "producer": "scripts/materialize_edna_retrieval.py",
            "producer_stage": "materialize_edna_retrieval",
            "input_artifact_ids": ["serving:edna_retrieval_parquet"],
        },
        {
            "id": "analysis:documents",
            "label": "analysis_documents",
            "kind": "analysis",
            "path": config.ANALYSIS_DIR / "analysis_documents.jsonl",
            "producer": "scripts/run_pre_analysis.py",
            "producer_stage": "pre_analysis",
            "input_artifact_ids": ["normalized:ctd_summary", "serving:sample_context", "normalized:sst_daily"],
        },
        {
            "id": "reliability:documents",
            "label": "reliability_documents",
            "kind": "reliability",
            "path": config.RELIABILITY_DIR / "reliability_documents.jsonl",
            "producer": "scripts/run_reliability.py",
            "producer_stage": "reliability",
            "input_artifact_ids": ["analysis:documents", "normalized:ctd_summary", "serving:sample_context", "normalized:sst_daily"],
        },
        {
            "id": "provenance:jsonl",
            "label": "provenance",
            "kind": "provenance",
            "path": config.PROVENANCE_DIR / "provenance.jsonl",
            "producer": "scripts/ingest.py",
            "producer_stage": "ingest",
            "source_file_ids": [f"raw:{key}" for key in sorted(config.RAW_FILES)] + ["raw:sst_netcdf"],
        },
    ]
    specs.extend(_active_anemone_artifact_specs())
    return specs


def build_artifact_versions() -> List[ArtifactVersion]:
    rows: List[ArtifactVersion] = []
    for spec in _artifact_specs():
        path = Path(spec["path"])
        columns = _artifact_columns(path)
        rows.append(
            ArtifactVersion(
                id=spec["id"],
                label=spec["label"],
                kind=spec["kind"],
                path=str(path),
                producer=spec["producer"],
                producer_stage=spec["producer_stage"],
                source_file_ids=list(spec.get("source_file_ids", [])),
                input_artifact_ids=list(spec.get("input_artifact_ids", [])),
                table_name=spec.get("table_name"),
                key_columns=list(spec.get("key_columns", [])),
                exists=path.exists(),
                sha256=_sha256_file(path),
                row_count=_artifact_row_count(path),
                columns=columns,
                schema_hash=_stable_hash(columns) if columns else None,
                file_size_bytes=path.stat().st_size if path.exists() and path.is_file() else None,
                modified_at=_modified_at(path),
                notes=spec.get("notes"),
                source_snapshot_id=spec.get("source_snapshot_id"),
            )
        )
    return rows


def _read_retrieval_documents() -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for name in ("retrieval_documents", "anemone_retrieval_documents"):
        parquet_path = config.SERVING_DIR / f"{name}.parquet"
        jsonl_path = config.SERVING_DIR / f"{name}.jsonl"
        if name == "anemone_retrieval_documents":
            parquet_path, jsonl_path = edna_retrieval_path("parquet"), edna_retrieval_path("jsonl")
        if parquet_path.exists():
            frames.append(pd.read_parquet(parquet_path))
            continue
        if jsonl_path.exists():
            rows = []
            with jsonl_path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if "active" in combined.columns:
        combined = combined[
            combined["active"].fillna(True).astype(bool)
        ]
    id_column = "doc_id" if "doc_id" in combined.columns else "id"
    return combined.drop_duplicates(id_column, keep="last").sort_values(id_column)


def _document_source_artifacts(source_type: str) -> List[str]:
    if source_type == "ctd":
        return ["normalized:ctd_summary", "normalized:ctd_profile", "serving:retrieval_parquet"]
    if source_type == "metagenome":
        return ["serving:sample_context", "normalized:kraken", "normalized:metaeuk", "serving:retrieval_parquet"]
    if source_type == "remote_sensing":
        return ["normalized:sst_daily", "normalized:sst_point", "serving:retrieval_parquet"]
    if source_type == "edna_metabarcoding":
        return ["serving:edna_retrieval_parquet"]
    return ["serving:retrieval_parquet"]


def _document_source_files(source_type: str) -> List[str]:
    if source_type == "ctd":
        return ["raw:ctd"]
    if source_type == "metagenome":
        return [
            "raw:runid",
            "raw:read_summary",
            "raw:coverage_log",
            "raw:kraken_genus_sample_tsv",
            "raw:metaeuk_genus_sample",
            "raw:kraken_genus_group",
            "raw:genus_group",
            "raw:gn_consistency",
            "raw:km_consistency",
        ]
    if source_type == "remote_sensing":
        return ["raw:sst_netcdf"]
    return []


def build_document_traces(limit_documents: Optional[int] = 500) -> List[DocumentTrace]:
    df = _read_retrieval_documents()
    if df.empty:
        return []
    rows: List[DocumentTrace] = []
    anemone_artifacts = _active_anemone_artifact_specs()
    selected = df if limit_documents is None else df.head(limit_documents)
    for _, row in selected.iterrows():
        doc_id = str(row.get("doc_id") or row.get("id") or "")
        if not doc_id:
            continue
        source_type = str(row.get("source_type") or "unknown")
        sample_id = None if pd.isna(row.get("sample_id")) else str(row.get("sample_id") or "")
        event_id = None if pd.isna(row.get("event_id")) else str(row.get("event_id") or "")
        time_value = None if pd.isna(row.get("time")) else str(row.get("time") or "")
        title = str(row.get("title") or doc_id)
        text_value = str(row.get("text") or "")
        content_hash = _stable_hash({"title": title, "text": text_value})
        metadata_value: Dict[str, Any] = {}
        raw_metadata = row.get("metadata_json") or row.get("metadata")
        if isinstance(raw_metadata, dict):
            metadata_value = raw_metadata
        elif isinstance(raw_metadata, str) and raw_metadata:
            try:
                metadata_value = json.loads(raw_metadata)
            except json.JSONDecodeError:
                metadata_value = {}
        metadata_hash = _stable_hash(
            {
                "source_type": source_type,
                "sample_id": sample_id,
                "event_id": event_id,
                "time": time_value,
                "bay": None if pd.isna(row.get("bay")) else row.get("bay"),
                "station": None if pd.isna(row.get("station")) else row.get("station"),
                "provider": row.get("provider"),
                "assay_id": row.get("assay_id"),
                "assignment_method": row.get("assignment_method"),
                "sample_kind": row.get("sample_kind"),
                "is_control": row.get("is_control"),
                "source_snapshot_id": row.get("source_snapshot_id"),
                "metadata": metadata_value,
            }
        )
        source_keys = []
        if sample_id:
            source_keys.append(f"sample_id:{sample_id}")
        if event_id:
            source_keys.append(f"event_id:{event_id}")
        if source_type == "remote_sensing" and time_value:
            source_keys.append(f"date_jst:{time_value[:10]}")
        if source_type == "edna_metabarcoding":
            assay_id = row.get("assay_id")
            assignment_method = row.get("assignment_method")
            if assay_id:
                source_keys.append(f"assay_id:{assay_id}")
            if assignment_method:
                source_keys.append(
                    f"assignment_method:{assignment_method}"
                )
            source_keys.extend(
                f"detection_id:{value}"
                for value in metadata_value.get("featured_detection_ids", [])
            )
        source_file_ids = _document_source_files(source_type)
        if source_type == "edna_metabarcoding":
            source_file_ids = [
                f"raw:anemone:{value}"
                for value in metadata_value.get("source_file_ids", [])
            ]
        source_artifact_ids = _document_source_artifacts(source_type)
        if source_type == "edna_metabarcoding":
            source_artifact_ids.extend(
                spec["id"] for spec in anemone_artifacts
                if spec["source_snapshot_id"] in metadata_value.get("source_snapshot_ids", [])
            )
        rows.append(
            DocumentTrace(
                doc_id=doc_id,
                source_type=source_type,
                sample_id=sample_id or None,
                event_id=event_id or None,
                time=time_value or None,
                title=title,
                content_hash=content_hash,
                metadata_hash=metadata_hash,
                lineage_level="document_to_artifact_and_source_key",
                source_file_ids=source_file_ids,
                source_artifact_ids=source_artifact_ids,
                source_record_keys=source_keys,
                metadata=metadata_value,
            )
        )
    return rows


def _database_embedding_status() -> Dict[str, Any]:
    try:
        engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT doc_id, embedding IS NOT NULL AS embedded, "
                "embedding_provider, embedding_model, embedding_dim, embedded_at "
                "FROM retrieval_document WHERE active IS TRUE"
            )).mappings().all()
        return {
            "available": True,
            "rows": {str(row["doc_id"]): bool(row["embedded"]) for row in rows},
            "metadata": {str(row["doc_id"]): dict(row) for row in rows},
        }
    except Exception as exc:
        return {"available": False, "error": str(exc), "rows": {}}


def build_embedding_traces(documents: List[DocumentTrace], *, include_database: bool = True) -> List[EmbeddingTrace]:
    db_status = _database_embedding_status() if include_database else {"available": False, "rows": {}, "error": "database embedding check skipped"}
    embedded_by_doc = db_status.get("rows") if isinstance(db_status.get("rows"), dict) else {}
    rows: List[EmbeddingTrace] = []
    for doc in documents:
        embedded_value = embedded_by_doc.get(doc.doc_id)
        embedding_metadata = (db_status.get("metadata") or {}).get(doc.doc_id, {})
        if db_status.get("available"):
            status = "embedded" if embedded_value else "missing"
            notes = None
        else:
            status = "unknown"
            notes = str(db_status.get("error") or "database unavailable")
        rows.append(
            EmbeddingTrace(
                doc_id=doc.doc_id,
                content_hash=doc.content_hash,
                embedding_status=status,
                embedding_model=embedding_metadata.get("embedding_model") or config.EMBEDDING_MODEL,
                embedding_dim=embedding_metadata.get("embedding_dim") or config.EMBEDDING_DIM,
                embedding_provider=embedding_metadata.get("embedding_provider"),
                embedded_at=str(embedding_metadata["embedded_at"]) if embedding_metadata.get("embedded_at") else None,
                embedding_source="postgresql.retrieval_document.embedding",
                embedded=embedded_value if isinstance(embedded_value, bool) else None,
                notes=notes,
            )
        )
    return rows


def build_anemone_row_traces() -> List[Dict[str, Any]]:
    """Trace each canonical eDNA row to its immutable source file and row."""
    resolved = _resolve_anemone_lineage_bundle()
    if resolved is None:
        return []
    root, manifest = resolved
    normalization_id = str(manifest["normalization_id"])
    specs = (
        ("edna_sample", "sample_id", "source_row_numbers_json"),
        ("edna_assay", "assay_id", "source_row_numbers_json"),
        ("edna_detection", "detection_id", "source_row_number"),
        (
            "edna_internal_standard",
            "internal_standard_id",
            "source_row_number",
        ),
    )
    traces: List[Dict[str, Any]] = []
    for table_name, key_column, locator_column in specs:
        artifact = manifest.get("artifacts", {}).get(table_name)
        if not artifact:
            continue
        frame = pd.read_parquet(root / str(artifact["path"]))
        for row in frame.to_dict(orient="records"):
            source_file_id = str(row.get("source_file_id") or "")
            traces.append(
                {
                    "table": table_name,
                    "record_id": str(row.get(key_column) or ""),
                    "source_snapshot_id": str(
                        row.get("source_snapshot_id") or ""
                    ),
                    "source_file_id": source_file_id,
                    "source_file_trace_id": f"raw:anemone:{source_file_id}",
                    "source_row_locator": row.get(locator_column),
                    "scientific_content_sha256": row.get(
                        "scientific_content_sha256"
                    ),
                    "source_row_hash": row.get("source_row_hash"),
                    "normalization_artifact_id": (
                        f"normalized:anemone:{normalization_id}:{table_name}"
                    ),
                }
            )
    return traces


def build_provenance_manifest(
    *,
    limit_documents: Optional[int] = 500,
    include_embeddings: bool = True,
) -> Dict[str, Any]:
    from ingestion.edna_analysis_bundle import provenance_descriptors
    edna_analyses = provenance_descriptors()
    source_files = build_source_file_traces()
    artifacts = build_artifact_versions()
    documents = build_document_traces(limit_documents=limit_documents)
    embeddings = build_embedding_traces(documents, include_database=include_embeddings) if include_embeddings else []
    anemone_rows = build_anemone_row_traces()
    registry_records = _read_registry_records()
    summary = {
        "source_files": len(source_files),
        "registered_source_records": len(registry_records),
        "artifacts": len(artifacts),
        "existing_artifacts": sum(1 for item in artifacts if item.exists),
        "documents": len(documents),
        "anemone_canonical_rows": len(anemone_rows),
        "embedded_documents_in_manifest": sum(1 for item in embeddings if item.embedding_status == "embedded"),
        "embedding_model": config.EMBEDDING_MODEL,
        "embedding_dim": config.EMBEDDING_DIM,
        "document_limit": limit_documents,
    }
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "project_root": str(config.PROJECT_ROOT),
        "summary": summary,
        "source_files": [asdict(item) for item in source_files],
        "artifacts": [asdict(item) for item in artifacts],
        "documents": [asdict(item) for item in documents],
        "embeddings": [asdict(item) for item in embeddings],
        "anemone_canonical_rows": anemone_rows,
        "edna_analyses": edna_analyses,
        "limitations": [
            "Corpus database rows carry source_row_hash values generated from normalized row content; document traces additionally retain stable source keys and file hashes.",
            "SST collection manifests use a directory fingerprint at API time; per-file SHA records are available after ingestion registration.",
            "Embedding provenance records current model/dimension/status; unchanged retrieval rows retain their existing embeddings during transactional upserts.",
        ],
    }


def write_provenance_manifest(
    *,
    run_id: Optional[str] = None,
    limit_documents: int = 500,
    include_embeddings: bool = True,
) -> Path:
    manifest = build_provenance_manifest(limit_documents=limit_documents, include_embeddings=include_embeddings)
    safe_run_id = run_id or datetime.now().strftime("provenance_%Y%m%dT%H%M%S")
    manifest["manifest_id"] = safe_run_id
    out_dir = config.PROVENANCE_DIR / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{safe_run_id}.json"
    latest_path = config.PROVENANCE_DIR / LATEST_MANIFEST_NAME
    out_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    latest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return out_path


def build_document_trace(doc_id: str) -> Dict[str, Any]:
    manifest = build_provenance_manifest(limit_documents=10000, include_embeddings=True)
    from ingestion.edna_analysis_bundle import analysis_trace
    analysis = analysis_trace(doc_id, manifest.get('edna_analyses', []))
    if analysis:
        return analysis
    documents = manifest.get("documents", [])
    document = next((row for row in documents if row.get("doc_id") == doc_id), None)
    if not document:
        return {"doc_id": doc_id, "found": False, "trace": {}}
    artifact_ids = set(document.get("source_artifact_ids") or [])
    source_file_ids = set(document.get("source_file_ids") or [])
    embedding = next((row for row in manifest.get("embeddings", []) if row.get("doc_id") == doc_id), None)
    artifacts = [row for row in manifest.get("artifacts", []) if row.get("id") in artifact_ids]
    source_files = [row for row in manifest.get("source_files", []) if row.get("id") in source_file_ids]
    return {
        "doc_id": doc_id,
        "found": True,
        "trace": {
            "document": document,
            "embedding": embedding,
            "artifacts": artifacts,
            "source_files": source_files,
            "trace_path": [
                {"level": "citation", "key": doc_id},
                {"level": "retrieval_document", "key": document.get("content_hash")},
                {"level": "derived_artifacts", "keys": sorted(artifact_ids)},
                {"level": "source_files", "keys": sorted(source_file_ids)},
                {"level": "embedding_treatment", "key": embedding.get("embedding_model") if embedding else None},
            ],
        },
    }


def _normalize_key_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return str(value)


def _key_tuple(row: Dict[str, Any], columns: List[str]) -> Tuple[str, ...]:
    return tuple(_normalize_key_value(row.get(column)) for column in columns)


def _incoming_dataframe_for_table(table_name: str) -> Tuple[pd.DataFrame, Optional[str], List[str]]:
    if table_name == "retrieval_document":
        return (
            _read_retrieval_documents(),
            "serving:retrieval_parquet",
            ["doc_id"],
        )
    artifact_by_table = {
        spec.get("table_name"): spec
        for spec in _artifact_specs()
        if spec.get("table_name")
    }
    spec = artifact_by_table.get(table_name)
    if not spec:
        return pd.DataFrame(), None, []
    path = Path(spec["path"])
    if not path.exists():
        return pd.DataFrame(), spec["id"], list(spec.get("key_columns", []))
    if table_name == "metagenome_sample":
        source = pd.read_parquet(path)
        records = []
        for _, row in source.iterrows():
            sid = row.get("sample_id")
            if pd.isna(sid):
                continue
            has_kraken = bool(row.get("has_kraken", False))
            has_metaeuk = bool(row.get("has_metaeuk", False))
            if not has_kraken and not has_metaeuk:
                continue
            records.append(
                {
                    "sample_id": sid,
                    "bay": row.get("bay"),
                    "station_code": row.get("station_code"),
                    "sample_year_month": row.get("sample_year_month"),
                    "n_runs": int(row["n_runs"]) if pd.notna(row.get("n_runs")) else None,
                    "first_run_date": row.get("first_run_date"),
                    "last_run_date": row.get("last_run_date"),
                    "sum_reads_gt1kb": row.get("sum_reads_gt1kb"),
                    "sum_bases_gt1kb": row.get("sum_bases_gt1kb"),
                    "has_kraken": has_kraken,
                    "has_metaeuk": has_metaeuk,
                    "has_ctd": bool(row.get("has_ctd", False)),
                    "top_kraken_genera_json": row.get("top_genus_10_json_x"),
                    "top_metaeuk_genera_json": row.get("top_genus_10_json_y"),
                    "top_upper_groups_json": row.get("top_upper_group_10_json"),
                }
            )
        return pd.DataFrame(records), spec["id"], list(spec.get("key_columns", []))
    return pd.read_parquet(path), spec["id"], list(spec.get("key_columns", []))


def _database_rows(table_name: str, columns: Iterable[str]) -> Tuple[bool, Optional[str], List[Dict[str, Any]]]:
    try:
        engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
        selected = ", ".join(columns)
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT {selected} FROM {table_name}")).mappings().all()
        return True, None, [dict(row) for row in rows]
    except Exception as exc:
        return False, str(exc), []


def _database_scoped_anemone_rows(
    table_name: str,
    columns: Iterable[str],
    *,
    scope_template: str,
    scope_parameters: Dict[str, Any],
) -> Tuple[bool, Optional[str], List[Dict[str, Any]]]:
    joins = {
        "edna_sample": ("", "target"),
        "edna_assay": (
            "JOIN edna_sample AS sample ON target.sample_id = sample.sample_id",
            "sample",
        ),
        "edna_detection": (
            "JOIN edna_assay AS assay ON target.assay_id = assay.assay_id "
            "JOIN edna_sample AS sample ON assay.sample_id = sample.sample_id",
            "sample",
        ),
        "edna_internal_standard": (
            "JOIN edna_assay AS assay ON target.assay_id = assay.assay_id "
            "JOIN edna_sample AS sample ON assay.sample_id = sample.sample_id",
            "sample",
        ),
    }
    join_clause, scope_alias = joins[table_name]
    try:
        engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
        preparer = engine.dialect.identifier_preparer
        selected = ", ".join(
            f"target.{preparer.quote(column)} AS {preparer.quote(column)}"
            for column in columns
        )
        sql = (
            f"SELECT {selected} FROM {preparer.quote(table_name)} AS target "
            f"{join_clause} WHERE "
            f"{scope_template.format(alias=scope_alias)}"
        )
        with engine.connect() as conn:
            rows = conn.execute(text(sql), scope_parameters).mappings().all()
        return True, None, [dict(row) for row in rows]
    except Exception as exc:
        return False, str(exc), []


def build_upsert_dry_run_plan(
    limit_keys: int = 25,
    *,
    anemone_normalization_id: Optional[str] = None,
    allow_anemone_noncurrent: bool = False,
) -> Dict[str, Any]:
    table_order = [
        "external_source_snapshot",
        "external_source_file",
        "anchor_event",
        "edna_sample",
        "edna_assay",
        "edna_detection",
        "edna_internal_standard",
        "ctd_profile",
        "ctd_summary",
        "metagenome_sample",
        "sst_point_observation",
        "sst_daily_summary",
        "retrieval_document",
        "cross_source_link",
    ]
    manifest = build_provenance_manifest(limit_documents=10000, include_embeddings=False)
    table_plans: List[Dict[str, Any]] = []
    database_available = True
    database_errors: List[str] = []
    from scripts.load_db import _load_anemone_bundle_frames, _scope_parameters

    anemone_bundle = _load_anemone_bundle_frames(
        anemone_normalization_id,
        allow_noncurrent=allow_anemone_noncurrent,
    )
    anemone_frames: Dict[str, pd.DataFrame] = {}
    anemone_manifest: Dict[str, Any] = {}
    scope_template: Optional[str] = None
    scope_parameters: Dict[str, Any] = {}
    if anemone_bundle is not None:
        anemone_frames, anemone_manifest = anemone_bundle
        scope_template, scope_parameters = _scope_parameters(
            anemone_frames["edna_sample"],
            anemone_manifest,
        )
    anemone_table_frames = {
        name: frame
        for name, frame in anemone_frames.items()
        if name != "edna_anchor_event"
    }
    anemone_key_columns = {
        "external_source_snapshot": ["snapshot_id"],
        "external_source_file": ["source_file_id"],
        "edna_sample": ["sample_id"],
        "edna_assay": ["assay_id"],
        "edna_detection": ["detection_id"],
        "edna_internal_standard": ["internal_standard_id"],
    }

    for table_name in table_order:
        if table_name in anemone_table_frames:
            incoming_df = anemone_table_frames[table_name]
            artifact_id = (
                "normalized:anemone:"
                f"{anemone_manifest['normalization_id']}:{table_name}"
            )
            key_columns = anemone_key_columns[table_name]
        else:
            incoming_df, artifact_id, key_columns = (
                _incoming_dataframe_for_table(table_name)
            )
            if (
                table_name == "anchor_event"
                and "edna_anchor_event" in anemone_frames
                and not anemone_frames["edna_anchor_event"].empty
            ):
                incoming_df = pd.concat(
                    [incoming_df, anemone_frames["edna_anchor_event"]],
                    ignore_index=True,
                )
            if table_name in anemone_key_columns and not key_columns:
                key_columns = anemone_key_columns[table_name]
        incoming_rows = incoming_df.to_dict(orient="records") if not incoming_df.empty else []
        incoming_keys = {_key_tuple(row, key_columns) for row in incoming_rows if key_columns}
        compare_columns = list(key_columns)
        if table_name == "retrieval_document":
            compare_columns.extend(["title", "text", "embedding IS NOT NULL AS embedded"])
        elif table_name.startswith("edna_"):
            compare_columns.extend(
                ["scientific_content_sha256", "source_row_hash", "active"]
            )
        if table_name.startswith("edna_") and scope_template:
            available, error, existing_rows = _database_scoped_anemone_rows(
                table_name,
                compare_columns,
                scope_template=scope_template,
                scope_parameters=scope_parameters,
            )
        else:
            available, error, existing_rows = _database_rows(
                table_name,
                compare_columns,
            )
        if not available:
            database_available = False
            if error:
                database_errors.append(f"{table_name}: {error}")
        existing_keys = {_key_tuple(row, key_columns) for row in existing_rows if key_columns}
        inserts = sorted(incoming_keys - existing_keys)
        stale = sorted(existing_keys - incoming_keys)
        matched = sorted(incoming_keys & existing_keys)
        changed = []
        embeddings_to_refresh = []
        scientific_corrections = []
        provenance_refreshes = []
        if available and table_name == "retrieval_document":
            incoming_by_key = {_key_tuple(row, key_columns): row for row in incoming_rows}
            existing_by_key = {_key_tuple(row, key_columns): row for row in existing_rows}
            for key in matched:
                incoming_row = incoming_by_key.get(key, {})
                existing_row = existing_by_key.get(key, {})
                incoming_hash = _stable_hash({"title": incoming_row.get("title"), "text": incoming_row.get("text")})
                existing_hash = _stable_hash({"title": existing_row.get("title"), "text": existing_row.get("text")})
                if incoming_hash != existing_hash:
                    changed.append(key)
                    embeddings_to_refresh.append(key)
            embeddings_to_refresh.extend(inserts)
        elif available and table_name.startswith("edna_"):
            incoming_by_key = {
                _key_tuple(row, key_columns): row for row in incoming_rows
            }
            existing_by_key = {
                _key_tuple(row, key_columns): row for row in existing_rows
            }
            for key in matched:
                incoming_row = incoming_by_key[key]
                existing_row = existing_by_key[key]
                if (
                    incoming_row.get("scientific_content_sha256")
                    != existing_row.get("scientific_content_sha256")
                ):
                    scientific_corrections.append(key)
                elif (
                    incoming_row.get("source_row_hash")
                    != existing_row.get("source_row_hash")
                    or existing_row.get("active") is not True
                ):
                    provenance_refreshes.append(key)
        is_immutable = table_name.startswith("external_source_")
        planned_inactivations = (
            len(stale)
            if available
            and anemone_bundle is not None
            and table_name.startswith("edna_")
            else 0 if available else None
        )
        candidate_updates = (
            len(changed)
            if table_name == "retrieval_document" and available
            else len(scientific_corrections) + len(provenance_refreshes)
            if table_name.startswith("edna_") and available
            else 0
            if is_immutable and available
            else len(matched)
            if available
            else None
        )
        plan = {
            "table": table_name,
            "artifact_id": artifact_id,
            "key_columns": key_columns,
            "database_available": available,
            "error": error,
            "incoming_count": len(incoming_rows),
            "existing_count": len(existing_rows) if available else None,
            "planned_inserts": len(inserts) if available else None,
            "matched_existing": len(matched) if available else None,
            "candidate_updates": candidate_updates,
            "scientific_corrections": (
                len(scientific_corrections) if available else None
            ),
            "provenance_refreshes": (
                len(provenance_refreshes) if available else None
            ),
            "planned_inactivations": planned_inactivations,
            "stale_existing": (
                0
                if available
                and (
                    is_immutable
                    or (
                        table_name.startswith("edna_")
                        and anemone_bundle is None
                    )
                )
                else len(stale)
                if available
                else None
            ),
            "embedding_refresh_candidates": len(embeddings_to_refresh) if table_name == "retrieval_document" and available else None,
            "sample_insert_keys": [list(key) for key in inserts[:limit_keys]] if available else [],
            "sample_stale_keys": [list(key) for key in stale[:limit_keys]] if available else [],
            "notes": (
                "Content-hash comparison protects unchanged embeddings; changed or inserted docs should be embedded after upsert."
                if table_name == "retrieval_document"
                else "Stable scientific and provenance hashes separate corrections, source refreshes, and scoped inactivation."
                if table_name.startswith("edna_")
                else "Immutable source records are inserted once; identity/content conflicts fail the transaction."
                if is_immutable
                else "Non-retrieval tables use key-level dry-run counts."
            ),
        }
        table_plans.append(plan)

    summary = {
        "tables": len(table_plans),
        "database_available": database_available,
        "incoming_rows": sum(int(plan["incoming_count"] or 0) for plan in table_plans),
        "planned_inserts": sum(int(plan["planned_inserts"] or 0) for plan in table_plans if plan["planned_inserts"] is not None),
        "candidate_updates": sum(int(plan["candidate_updates"] or 0) for plan in table_plans if plan["candidate_updates"] is not None),
        "stale_existing": sum(int(plan["stale_existing"] or 0) for plan in table_plans if plan["stale_existing"] is not None),
        "embedding_refresh_candidates": sum(
            int(plan["embedding_refresh_candidates"] or 0)
            for plan in table_plans
            if plan["embedding_refresh_candidates"] is not None
        ),
        "scientific_corrections": sum(
            int(plan["scientific_corrections"] or 0)
            for plan in table_plans
            if plan["scientific_corrections"] is not None
        ),
        "provenance_refreshes": sum(
            int(plan["provenance_refreshes"] or 0)
            for plan in table_plans
            if plan["provenance_refreshes"] is not None
        ),
        "planned_inactivations": sum(
            int(plan["planned_inactivations"] or 0)
            for plan in table_plans
            if plan["planned_inactivations"] is not None
        ),
    }
    return {
        "generated_at": _now_iso(),
        "dry_run": True,
        "ok": database_available,
        "database": {"available": database_available, "errors": database_errors[:5]},
        "summary": summary,
        "lineage_manifest_summary": manifest.get("summary", {}),
        "anemone": {
            "included": anemone_bundle is not None,
            "normalization_id": anemone_manifest.get("normalization_id"),
            "source_snapshot_id": anemone_manifest.get("source_snapshot_id"),
            "scope_level": anemone_manifest.get("source_scope_level"),
            "scope_url": anemone_manifest.get("source_scope_url"),
            "noncurrent_override": allow_anemone_noncurrent,
        },
        "table_plans": table_plans,
        "warnings": [
            "This plan is read-only and does not mutate PostgreSQL.",
            "Mutating upserts retain rows reported as stale_existing; use an explicit reset only for full replacement.",
            "Retrieval-document estimates use content hashes so unchanged embeddings are retained; other table estimates conservatively classify matched keys as update candidates.",
            "ANEMONE inactivation estimates are limited to the selected provider sample or provider project/run scope.",
        ],
    }
