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
    return rows


def _artifact_specs() -> List[Dict[str, Any]]:
    return [
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
            )
        )
    return rows


def _read_retrieval_documents() -> pd.DataFrame:
    parquet_path = config.SERVING_DIR / "retrieval_documents.parquet"
    jsonl_path = config.SERVING_DIR / "retrieval_documents.jsonl"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    if jsonl_path.exists():
        rows = []
        with jsonl_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return pd.DataFrame(rows)
    return pd.DataFrame()


def _document_source_artifacts(source_type: str) -> List[str]:
    if source_type == "ctd":
        return ["normalized:ctd_summary", "normalized:ctd_profile", "serving:retrieval_parquet"]
    if source_type == "metagenome":
        return ["serving:sample_context", "normalized:kraken", "normalized:metaeuk", "serving:retrieval_parquet"]
    if source_type == "remote_sensing":
        return ["normalized:sst_daily", "normalized:sst_point", "serving:retrieval_parquet"]
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
        metadata_hash = _stable_hash(
            {
                "source_type": source_type,
                "sample_id": sample_id,
                "event_id": event_id,
                "time": time_value,
                "bay": None if pd.isna(row.get("bay")) else row.get("bay"),
                "station": None if pd.isna(row.get("station")) else row.get("station"),
            }
        )
        source_keys = []
        if sample_id:
            source_keys.append(f"sample_id:{sample_id}")
        if event_id:
            source_keys.append(f"event_id:{event_id}")
        if source_type == "remote_sensing" and time_value:
            source_keys.append(f"date_jst:{time_value[:10]}")
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
                source_file_ids=_document_source_files(source_type),
                source_artifact_ids=_document_source_artifacts(source_type),
                source_record_keys=source_keys,
            )
        )
    return rows


def _database_embedding_status() -> Dict[str, Any]:
    try:
        engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT doc_id, embedding IS NOT NULL AS embedded FROM retrieval_document")).mappings().all()
        return {"available": True, "rows": {str(row["doc_id"]): bool(row["embedded"]) for row in rows}}
    except Exception as exc:
        return {"available": False, "error": str(exc), "rows": {}}


def build_embedding_traces(documents: List[DocumentTrace], *, include_database: bool = True) -> List[EmbeddingTrace]:
    db_status = _database_embedding_status() if include_database else {"available": False, "rows": {}, "error": "database embedding check skipped"}
    embedded_by_doc = db_status.get("rows") if isinstance(db_status.get("rows"), dict) else {}
    rows: List[EmbeddingTrace] = []
    for doc in documents:
        embedded_value = embedded_by_doc.get(doc.doc_id)
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
                embedding_model=config.EMBEDDING_MODEL,
                embedding_dim=config.EMBEDDING_DIM,
                embedding_source="postgresql.retrieval_document.embedding",
                embedded=embedded_value if isinstance(embedded_value, bool) else None,
                notes=notes,
            )
        )
    return rows


def build_provenance_manifest(
    *,
    limit_documents: Optional[int] = 500,
    include_embeddings: bool = True,
) -> Dict[str, Any]:
    source_files = build_source_file_traces()
    artifacts = build_artifact_versions()
    documents = build_document_traces(limit_documents=limit_documents)
    embeddings = build_embedding_traces(documents, include_database=include_embeddings) if include_embeddings else []
    registry_records = _read_registry_records()
    summary = {
        "source_files": len(source_files),
        "registered_source_records": len(registry_records),
        "artifacts": len(artifacts),
        "existing_artifacts": sum(1 for item in artifacts if item.exists),
        "documents": len(documents),
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


def build_upsert_dry_run_plan(limit_keys: int = 25) -> Dict[str, Any]:
    table_order = [
        "anchor_event",
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

    for table_name in table_order:
        incoming_df, artifact_id, key_columns = _incoming_dataframe_for_table(table_name)
        incoming_rows = incoming_df.to_dict(orient="records") if not incoming_df.empty else []
        incoming_keys = {_key_tuple(row, key_columns) for row in incoming_rows if key_columns}
        compare_columns = list(key_columns)
        if table_name == "retrieval_document":
            compare_columns.extend(["title", "text", "embedding IS NOT NULL AS embedded"])
        available, error, existing_rows = _database_rows(table_name, compare_columns)
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
            "candidate_updates": len(changed) if table_name == "retrieval_document" and available else len(matched) if available else None,
            "stale_existing": len(stale) if available else None,
            "embedding_refresh_candidates": len(embeddings_to_refresh) if table_name == "retrieval_document" and available else None,
            "sample_insert_keys": [list(key) for key in inserts[:limit_keys]] if available else [],
            "sample_stale_keys": [list(key) for key in stale[:limit_keys]] if available else [],
            "notes": (
                "Content-hash comparison protects unchanged embeddings; changed or inserted docs should be embedded after upsert."
                if table_name == "retrieval_document"
                else "Non-retrieval tables use key-level dry-run counts; column-level value diffing is planned."
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
    }
    return {
        "generated_at": _now_iso(),
        "dry_run": True,
        "ok": database_available,
        "database": {"available": database_available, "errors": database_errors[:5]},
        "summary": summary,
        "lineage_manifest_summary": manifest.get("summary", {}),
        "table_plans": table_plans,
        "warnings": [
            "This plan is read-only and does not mutate PostgreSQL.",
            "Mutating upserts retain rows reported as stale_existing; use an explicit reset only for full replacement.",
            "Retrieval-document estimates use content hashes so unchanged embeddings are retained; other table estimates conservatively classify matched keys as update candidates.",
        ],
    }
