from __future__ import annotations

import csv
import io
import json
import logging
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from api.edna_analysis_routes import router as edna_analysis_router
from schema.time_range import matches_time
from retrieval.edna_publication import retrieval_path as edna_retrieval_path
from api.admin_feedback_routes import router as admin_feedback_router
from api.auth import CurrentUser, authorization_middleware, get_current_user
from api.auth_routes import router as auth_router
from api.chat_records import (
    complete_chat_interaction,
    create_chat_interaction,
    fail_chat_interaction,
    json_safe,
    record_chat_context,
)
from api.feedback_routes import router as feedback_router
from api.edna_service import (
    EDNA_ASSIGNMENT_METHODS,
    EDNA_SAMPLE_KINDS,
    edna_assay_detail,
    edna_catalog,
    edna_detection_detail,
    edna_detections,
    edna_sample_detail,
    edna_samples,
    validate_edna_id,
)
from api.provenance_snapshot_service import get_provenance_snapshot_service
from api.retention_routes import router as retention_router
from api.schemas import (
    ChatRequest,
    ChatResponse,
    ColumnProfile,
    ContextDocument,
    CorpusStats,
    CtdProfileResponse,
    AnalysisResponse,
    DataCatalogResponse,
    EdnaAssayDetailResponse,
    EdnaCatalogResponse,
    EdnaDetectionDetailResponse,
    EdnaPageResponse,
    EdnaSampleDetailResponse,
    DatabaseSchemaResponse,
    DatabaseTableResponse,
    DatasetCatalogItem,
    EvaluationAblationRunRequest,
    EvaluationAnalyticsResponse,
    EvaluationCatalogResponse,
    EvaluationCompareRequest,
    EvaluationCompareResponse,
    EvaluationJobStatus,
    EvaluationModeInfo,
    EvaluationQuestion,
    EvaluationReportResponse,
    EvaluationRunDetailResponse,
    EvaluationRunsResponse,
    EvaluationRunSummary,
    EvaluationStandardRunRequest,
    EvaluationStartResponse,
    EvaluationVariantInfo,
    ExploreSummaryResponse,
    ExploreTableResponse,
    ModelsResponse,
    OllamaModel,
    PipelineArtifactFreshness,
    PipelineArtifactInfo,
    PipelineJobStatus,
    PipelineLogResponse,
    PipelinePreflightCheck,
    PipelinePreflightResponse,
    PipelineRunDetailResponse,
    PipelineRunRequest,
    PipelineRunSummary,
    PipelineRunsResponse,
    PipelineStageLog,
    PipelineStageInfo,
    PipelineStartResponse,
    PipelineStatusResponse,
    ProvenanceManifestResponse,
    ProvenanceTraceResponse,
    RetrieveRequest,
    RetrieveResponse,
    SampleDetailResponse,
    SourceDocument,
    SstDailyPoint,
    SstDataResponse,
    SstPoint,
    StatusResponse,
    TaxaEntry,
    TaxaSampleResponse,
    TimeSeriesPoint,
    TimeSeriesResponse,
    UpsertDryRunResponse,
    validate_time_range,
)
from evaluation.benchmark import (
    EVAL_MODES,
    SYSTEM_VARIANTS,
    EvalMode,
    SystemVariant,
    compute_summary_metrics,
    run_single_ablation,
    run_single_evaluation,
)
from evaluation.questions import BENCHMARK_QUESTIONS, QUESTION_CATEGORIES
from evaluation.reference_answers import get_reference
from db.backup import backup_capability
from orchestration.answer_audit import audit_answer
from orchestration.unified import build_prompt_with_context, retrieve, retrieve_with_expansion
from retrieval.local_retriever import LocalRetriever
from ingestion.lineage import (
    build_document_trace,
    build_provenance_manifest,
    build_upsert_dry_run_plan,
)
from ingestion.provenance_snapshot import SnapshotError
from model_runtime import get_model_runtime


def _cors_origins() -> List[str]:
    raw = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    config.validate_security_configuration(require_auth_secret=True)
    config.validate_runtime_configuration()
    yield


app = FastAPI(
    title="OCEAN Platform API",
    description="API layer for the Next.js migration of the provenance-aware marine RAG system.",
    version="0.3.0",
    lifespan=_app_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
    expose_headers=["Content-Disposition", "X-Export-Truncated"],
)

app.middleware("http")(authorization_middleware)
app.include_router(auth_router)
app.include_router(admin_feedback_router)
app.include_router(feedback_router)
app.include_router(retention_router)
app.include_router(edna_analysis_router)

logger = logging.getLogger(__name__)


EXPLORE_DATASETS: Dict[str, Dict[str, Any]] = {
    "sample_registry": {
        "label": "Sample registry",
        "path": config.SERVING_DIR / "sample_registry.parquet",
        "date_columns": ["ctd_date", "first_run_date", "last_run_date"],
        "bay_column": "bay",
        "station_column": "station_code",
        "source_column": None,
        "default_x": "ctd_date",
        "default_y": "n_depth_points",
        "default_columns": [
            "sample_id",
            "sample_year_month",
            "bay",
            "station_code",
            "ctd_date",
            "n_runs",
            "n_depth_points",
            "max_depth_m",
            "has_ctd",
            "has_kraken",
            "has_metaeuk",
        ],
    },
    "ctd_summary": {
        "label": "CTD summary",
        "path": config.NORMALIZED_DIR / "ctd_summary.parquet",
        "date_columns": ["ctd_date"],
        "bay_column": "bay",
        "station_column": "station_code",
        "source_column": None,
        "default_x": "ctd_date",
        "default_y": "mean_temperature",
        "default_columns": [
            "sample_id",
            "ctd_date",
            "bay",
            "station_code",
            "n_depth_points",
            "max_depth_m",
            "mean_temperature",
            "mean_salinity",
            "mean_do_percent",
            "mean_chl_a",
            "mean_turbidity",
        ],
    },
    "sst_daily": {
        "label": "Satellite SST daily",
        "path": config.NORMALIZED_DIR / "sst_daily_summary.parquet",
        "date_columns": ["date_jst"],
        "bay_column": None,
        "station_column": None,
        "source_column": None,
        "default_x": "date_jst",
        "default_y": "mean_sst",
        "default_columns": ["date_jst", "mean_sst", "min_sst", "max_sst", "std_sst", "n_files"],
    },
    "diversity": {
        "label": "Diversity indices",
        "path": config.ANALYSIS_DIR / "diversity_indices.parquet",
        "date_columns": ["year_month"],
        "bay_column": "bay",
        "station_column": None,
        "source_column": "source",
        "default_x": "year_month",
        "default_y": "shannon_h",
        "default_columns": [
            "sample_id",
            "source",
            "bay",
            "year_month",
            "shannon_h",
            "simpson_1d",
            "richness",
            "evenness",
        ],
    },
    "ctd_monthly_trends": {
        "label": "CTD monthly trends",
        "path": config.ANALYSIS_DIR / "ctd_monthly_trends.parquet",
        "date_columns": ["year_month"],
        "bay_column": "bay",
        "station_column": None,
        "source_column": None,
        "default_x": "year_month",
        "default_y": "mean_temperature_mean",
        "default_columns": [
            "bay",
            "year_month",
            "mean_temperature_mean",
            "mean_salinity_mean",
            "mean_do_percent_mean",
            "mean_chl_a_mean",
            "strat_index_mean",
        ],
    },
    "sst_ctd_validation": {
        "label": "SST / CTD validation",
        "path": config.RELIABILITY_DIR / "sst_ctd_validation.parquet",
        "date_columns": ["ctd_date"],
        "bay_column": "bay",
        "station_column": None,
        "source_column": None,
        "default_x": "ctd_date",
        "default_y": "abs_delta_t",
        "default_columns": [
            "sample_id",
            "ctd_date",
            "bay",
            "ctd_surface_t",
            "sst_daily_mean",
            "abs_delta_t",
            "agrees",
            "reliability_score",
        ],
    },
    "corroboration": {
        "label": "Corroboration",
        "path": config.RELIABILITY_DIR / "corroboration.parquet",
        "date_columns": [],
        "bay_column": None,
        "station_column": None,
        "source_column": "source_type",
        "default_x": None,
        "default_y": "reliability_score",
        "default_columns": [
            "event_id",
            "sample_id",
            "source_type",
            "reliability_tier",
            "corroboration_sources",
            "reliability_score",
            "n_checks",
            "detail",
        ],
    },
    "gap_interpolation": {
        "label": "SST gap interpolation",
        "path": config.RELIABILITY_DIR / "gap_interpolation.parquet",
        "date_columns": ["date"],
        "bay_column": None,
        "station_column": None,
        "source_column": None,
        "default_x": "date",
        "default_y": "interpolated_surface_t",
        "default_columns": [
            "date",
            "sst_daily_mean",
            "interpolated_surface_t",
            "confidence",
            "nearest_ctd_days",
            "in_ctd_gap",
        ],
    },
    "taxa_env_correlations": {
        "label": "Taxa / environment correlations",
        "path": config.ANALYSIS_DIR / "taxa_env_correlations.parquet",
        "date_columns": [],
        "bay_column": None,
        "station_column": None,
        "source_column": None,
        "default_x": None,
        "default_y": "spearman_rho",
        "default_columns": [
            "genus",
            "env_variable",
            "spearman_rho",
            "p_value",
            "n_samples",
            "significant",
        ],
    },
}

EMBEDDING_ONLY_MODEL_HINTS = (
    "nomic-embed",
    "mxbai-embed",
    "all-minilm",
    "snowflake-arctic-embed",
    "embed-text",
)

CTD_PROFILE_VARIABLES = [
    "temperature",
    "salinity",
    "do_percent",
    "chl_a",
    "turbidity",
    "sigma_t",
    "do_mg_l",
    "ph",
    "par",
]

EVALUATION_METRICS = [
    {"key": "retrieval_precision", "label": "Retrieval Precision", "format": "percent"},
    {"key": "source_coverage", "label": "Source Coverage", "format": "percent"},
    {"key": "citation_count", "label": "Citation Count", "format": "number"},
    {"key": "citation_accuracy", "label": "Citation Accuracy", "format": "percent"},
    {"key": "context_utilization", "label": "Context Utilization", "format": "percent"},
    {"key": "latency_seconds", "label": "Latency Seconds", "format": "seconds"},
]

EVALUATION_QUALITY_METRICS = [
    {"key": "rouge_l", "label": "ROUGE-L", "format": "percent"},
    {"key": "semantic_similarity", "label": "Semantic Similarity", "format": "percent"},
    {"key": "faithfulness", "label": "Faithfulness", "format": "percent"},
    {"key": "answer_completeness", "label": "Answer Completeness", "format": "percent"},
    {"key": "judge_mean", "label": "Judge Mean", "format": "number"},
]

EVALUATION_JOB_LOCK = threading.Lock()
EVALUATION_CANCEL_EVENTS: Dict[str, threading.Event] = {}
EVALUATION_TERMINAL_STATES = {"complete", "failed", "cancelled"}
PIPELINE_TERMINAL_STATES = {"complete", "failed", "cancelled"}
PIPELINE_RESET_CONFIRMATION = "RESET DATABASE"
LOCAL_JOB_SLOTS = threading.BoundedSemaphore(config.LOCAL_MAX_ACTIVE_JOBS)
SAFE_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

PIPELINE_STAGES: List[Dict[str, Any]] = [
    {
        "id": "validate_raw",
        "label": "Validate raw sources",
        "description": "Check required CTD and metagenome source files before a batch rebuild.",
        "command": ["python", "scripts/ingest.py", "--validate-only"],
        "expected_inputs": ["data/raw/ctd/CTD_Onagawa.tsv", "data/raw/meta/*.tsv", "data/raw/meta/*.txt"],
        "expected_outputs": ["log only"],
        "destructive": False,
        "expensive": False,
    },
    {
        "id": "ingest",
        "label": "Ingest and normalize",
        "description": "Run CTD, metagenome, optional SST preprocessing, and provenance registration.",
        "command": ["python", "scripts/ingest.py"],
        "expected_inputs": ["data/raw/**", "onagawa_sst_subset/**/*.nc"],
        "expected_outputs": ["data/normalized/*.parquet", "data/serving/sample_*.parquet", "data/provenance/provenance.jsonl"],
        "destructive": False,
        "expensive": True,
    },
    {
        "id": "build_retrieval_docs",
        "label": "Build retrieval corpus",
        "description": "Build anchor events, retrieval documents, JSONL corpus, and cross-source links.",
        "command": ["python", "scripts/build_retrieval_docs.py"],
        "expected_inputs": ["data/normalized/*.parquet", "data/serving/sample_*.parquet"],
        "expected_outputs": ["data/serving/retrieval_documents.*", "data/canonical/*.parquet"],
        "destructive": False,
        "expensive": False,
    },
    {
        "id": "pre_analysis",
        "label": "Run pre-analysis",
        "description": "Compute ecological trends, correlations, diversity metrics, and analysis RAG documents.",
        "command": ["python", "scripts/run_pre_analysis.py"],
        "expected_inputs": ["data/normalized/*.parquet", "data/serving/*.parquet"],
        "expected_outputs": ["data/analysis/*.parquet", "data/analysis/analysis_documents.jsonl"],
        "destructive": False,
        "expensive": False,
    },
    {
        "id": "reliability",
        "label": "Run reliability",
        "description": "Compute cross-source validation, interpolation, anomaly, and corroboration outputs.",
        "command": ["python", "scripts/run_reliability.py"],
        "expected_inputs": ["data/normalized/*.parquet", "data/analysis/*.parquet"],
        "expected_outputs": ["data/reliability/*.parquet", "data/reliability/reliability_documents.jsonl"],
        "destructive": False,
        "expensive": False,
    },
    {
        "id": "backup_database",
        "label": "Back up database",
        "description": "Create an atomic PostgreSQL custom archive, verify it, and restore it into a disposable database before mutation.",
        "command": ["python", "scripts/database_backup.py", "create", "--restore-test"],
        "expected_inputs": ["PostgreSQL database", "pg_dump and pg_restore"],
        "expected_outputs": ["data/backups/*.dump", "data/backups/*.dump.json"],
        "destructive": False,
        "expensive": False,
    },
    {
        "id": "load_db",
        "label": "Load database",
        "description": "Transactionally upsert PostgreSQL corpus rows by default, or explicitly reset.",
        "command": ["python", "scripts/load_db.py", "--upsert"],
        "expected_inputs": ["data/normalized/*.parquet", "data/serving/retrieval_documents.parquet", "data/canonical/*.parquet"],
        "expected_outputs": ["PostgreSQL tables", "retrieval_document.text_tsv"],
        "destructive": True,
        "expensive": True,
    },
    {
        "id": "materialize_edna_retrieval",
        "label": "Build eDNA retrieval corpus",
        "description": "Materialize one active retrieval document per eDNA assay and assignment method.",
        "command": ["python", "scripts/materialize_edna_retrieval.py", "--execute"],
        "expected_inputs": ["Active PostgreSQL eDNA tables"],
        "expected_outputs": [
            "PostgreSQL retrieval_document rows",
            "data/serving/anemone_retrieval_documents.parquet",
            "data/serving/anemone_retrieval_documents.jsonl",
        ],
        "destructive": True,
        "expensive": False,
    },
    {
        "id": "edna_analysis",
        "label": "eDNA analysis",
        "description": "Run the operator-configured cohort recipe.",
        "command": ["python", "scripts/run_edna_analysis.py", "--recipe", str(config.EDNA_ANALYSIS_RECIPE), "--execute"],
        "expected_inputs": ["Active eDNA canonical rows", "Operator-configured recipe"],
        "expected_outputs": ["data/analysis/edna/<analysis_id>/manifest.json"],
        "destructive": False,
        "expensive": True,
    },
    {
        "id": "embed_documents",
        "label": "Refresh embeddings",
        "description": "Compute missing retrieval-document embeddings without reloading database rows.",
        "command": ["python", "scripts/update_embeddings.py"],
        "expected_inputs": [
            "PostgreSQL retrieval_document rows",
            "Configured embedding runtime",
        ],
        "expected_outputs": ["retrieval_document.embedding"],
        "destructive": False,
        "expensive": True,
    },
    {
        "id": "publish_provenance",
        "label": "Publish provenance snapshot",
        "description": "Build and validate the complete lineage manifest, publish an immutable snapshot, and advance the generation-guarded latest pointer.",
        "command": ["python", "scripts/build_provenance_manifest.py", "--publish"],
        "expected_inputs": [
            "data/provenance/provenance.jsonl",
            "data/serving/retrieval_documents.parquet",
            "PostgreSQL retrieval_document embedding status",
        ],
        "expected_outputs": [
            "provenance/manifests/<run-id>.json",
            "provenance/latest.json",
        ],
        "destructive": False,
        "expensive": True,
    },
]
PIPELINE_STAGE_IDS = {stage["id"] for stage in PIPELINE_STAGES}
PIPELINE_STAGE_BY_ID = {stage["id"]: stage for stage in PIPELINE_STAGES}
PIPELINE_DEFAULT_STAGES = [
    "validate_raw",
    "ingest",
    "build_retrieval_docs",
    "pre_analysis",
    "reliability",
    "backup_database",
    "load_db",
    "materialize_edna_retrieval",
    "embed_documents",
    "publish_provenance",
]
PIPELINE_JOB_LOCK = threading.Lock()
PIPELINE_CANCEL_EVENTS: Dict[str, threading.Event] = {}
PIPELINE_PROCESSES: Dict[str, subprocess.Popen[str]] = {}


def _acquire_local_job_slot(job_kind: str) -> None:
    if LOCAL_JOB_SLOTS.acquire(blocking=False):
        return
    raise HTTPException(
        status_code=429,
        detail={
            "code": "local_job_capacity_reached",
            "message": f"The local {job_kind.lower()} worker is at capacity.",
        },
        headers={"Retry-After": "60"},
    )


def _validate_artifact_id(value: str, kind: str) -> str:
    if not SAFE_ARTIFACT_ID.fullmatch(value):
        raise HTTPException(status_code=404, detail=f"Unknown {kind}: {value}")
    return value


def _artifact_path(root: Path, identifier: str, kind: str) -> Path:
    safe_identifier = _validate_artifact_id(identifier, kind)
    resolved_root = root.resolve()
    candidate = (resolved_root / safe_identifier).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown {kind}: {identifier}") from exc
    return candidate


def _require_local_job_execution(job_kind: str) -> None:
    if config.JOB_EXECUTION_MODE == "local":
        return
    raise HTTPException(
        status_code=503,
        detail={
            "code": "external_job_runner_required",
            "message": (
                f"{job_kind} execution is delegated to the external job "
                "runner for this deployment."
            ),
        },
    )


def _doc_id(doc: Dict[str, Any]) -> str:
    return str(doc.get("doc_id") or doc.get("id") or "unknown")


def _time(doc: Dict[str, Any]) -> Optional[str]:
    value = doc.get("time") or doc.get("date")
    return str(value) if value else None


def _source_document(doc: Dict[str, Any]) -> SourceDocument:
    return SourceDocument(
        doc_id=_doc_id(doc),
        title=str(doc.get("title") or _doc_id(doc)),
        source_type=str(doc.get("source_type") or "unknown"),
        sample_id=doc.get("sample_id"),
        event_id=doc.get("event_id"),
        time=_time(doc),
        bay=doc.get("bay"),
        station=doc.get("station"),
        text=str(doc.get("text") or ""),
        score=doc.get("score"),
        rank_sources=doc.get("rank_sources") or {},
        retrieval_role=str(doc.get("retrieval_role") or "primary"),
        link_type=doc.get("link_type"),
        linked_from_doc_id=doc.get("linked_from_doc_id"),
        linked_from_event_id=doc.get("linked_from_event_id"),
        time_delta_days=doc.get("time_delta_days"),
        distance_km=doc.get("distance_km"),
        provider=doc.get("provider"),
        provider_project_id=doc.get("provider_project_id"),
        provider_run_id=doc.get("provider_run_id"),
        assay_id=doc.get("assay_id"),
        assignment_method=doc.get("assignment_method"),
        sample_kind=doc.get("sample_kind"),
        is_control=doc.get("is_control"),
        source_snapshot_id=doc.get("source_snapshot_id"),
    )


def _context_document(doc: Dict[str, Any], context_type: str) -> ContextDocument:
    doc_id = str(doc.get("doc_id") or doc.get("id") or f"{context_type}:unknown")
    return ContextDocument(
        doc_id=doc_id,
        title=str(doc.get("title") or doc.get("analysis_type") or doc_id),
        context_type=context_type,
        analysis_type=doc.get("analysis_type"),
        text=str(doc.get("text") or ""),
        analysis_id=doc.get("analysis_id"),
        table=doc.get("table"),
        result_ids=doc.get("result_ids", []),
        source_family=doc.get("source_family"),
    )


def _prompt_diagnostics(
    prompt: str,
    retrieved: List[Dict[str, Any]],
    context: Dict[str, List[Dict[str, Any]]],
    linked: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    analysis_docs = context.get("analysis") or []
    reliability_docs = context.get("reliability") or []
    linked_docs = linked or []
    retrieved_chars = sum(len(str(row.get("text") or "")) for row in retrieved)
    linked_chars = sum(len(str(row.get("text") or "")) for row in linked_docs)
    context_chars = sum(len(str(row.get("text") or "")) for row in [*analysis_docs, *reliability_docs])
    return {
        "prompt_chars": len(prompt),
        "retrieved_documents": len(retrieved),
        "linked_documents": len(linked_docs),
        "analysis_context_documents": len(analysis_docs),
        "reliability_context_documents": len(reliability_docs),
        "context_documents": len(analysis_docs) + len(reliability_docs),
        "retrieved_text_chars": retrieved_chars,
        "linked_text_chars": linked_chars,
        "supplementary_text_chars": context_chars,
        "ranked_documents": sum(1 for row in retrieved if row.get("rank_sources")),
    }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [
            LocalRetriever._normalize_document(json.loads(line))
            for line in f
            if line.strip()
        ]


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _parquet_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return len(pd.read_parquet(path))
    except Exception:
        return 0


def _redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if not parts.netloc or not parts.password:
            return value
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        user = parts.username or ""
        return urlunsplit((parts.scheme, f"{user}:***@{host}", parts.path, parts.query, parts.fragment))
    except Exception:
        return "<redacted>"


def _artifact_info(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return info
    info["is_file"] = path.is_file()
    info["is_dir"] = path.is_dir()
    info["modified_at"] = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    if path.is_file():
        info["size_bytes"] = path.stat().st_size
        if path.suffix == ".parquet":
            info["rows"] = _parquet_rows(path)
        elif path.suffix == ".jsonl":
            info["rows"] = _count_jsonl(path)
    return info


def _pipeline_artifact(id_: str, label: str, path: Path, note: Optional[str] = None) -> PipelineArtifactInfo:
    info = _artifact_info(path)
    return PipelineArtifactInfo(
        id=id_,
        label=label,
        path=str(path),
        exists=bool(info.get("exists")),
        is_file=bool(info.get("is_file", False)),
        is_dir=bool(info.get("is_dir", False)),
        size_bytes=info.get("size_bytes"),
        rows=info.get("rows"),
        modified_at=info.get("modified_at"),
        note=note,
    )


def _pipeline_raw_sources() -> List[PipelineArtifactInfo]:
    rows = [
        _pipeline_artifact(f"raw:{key}", key, path)
        for key, path in sorted(config.RAW_FILES.items())
    ]
    sst_count = len(list(config.SST_NETCDF_DIR.rglob("*.nc"))) if config.SST_NETCDF_DIR.exists() else 0
    rows.append(
        _pipeline_artifact(
            "raw:sst_netcdf",
            "sst_netcdf",
            config.SST_NETCDF_DIR,
            note=f"{sst_count} NetCDF files",
        )
    )
    rows.append(
        _pipeline_artifact(
            "raw:himawari_raw",
            "himawari_raw",
            config.HIMAWARI_RAW_DIR,
            note="optional raw Himawari DAT directory",
        )
    )
    return rows


def _pipeline_artifacts() -> List[PipelineArtifactInfo]:
    artifact_paths = [
        ("normalized:ctd_profile", "ctd_profile_standardized", config.NORMALIZED_DIR / "ctd_profile_standardized.parquet"),
        ("normalized:ctd_summary", "ctd_summary", config.NORMALIZED_DIR / "ctd_summary.parquet"),
        ("normalized:sample_qc", "sample_qc", config.NORMALIZED_DIR / "sample_qc.parquet"),
        ("normalized:kraken", "kraken_genus_enriched", config.NORMALIZED_DIR / "kraken_genus_enriched.parquet"),
        ("normalized:metaeuk", "metaeuk_genus_enriched", config.NORMALIZED_DIR / "metaeuk_genus_enriched.parquet"),
        ("normalized:sst_daily", "sst_daily_summary", config.NORMALIZED_DIR / "sst_daily_summary.parquet"),
        ("serving:sample_registry", "sample_registry", config.SERVING_DIR / "sample_registry.parquet"),
        ("serving:sample_context", "sample_multisource_context", config.SERVING_DIR / "sample_multisource_context.parquet"),
        ("canonical:anchors", "anchor_events", config.CANONICAL_DIR / "anchor_events.parquet"),
        ("canonical:links", "cross_source_links", config.CANONICAL_DIR / "cross_source_links.parquet"),
        ("serving:retrieval_parquet", "retrieval_documents.parquet", config.SERVING_DIR / "retrieval_documents.parquet"),
        ("serving:retrieval_jsonl", "retrieval_documents.jsonl", config.SERVING_DIR / "retrieval_documents.jsonl"),
        ("analysis:documents", "analysis_documents", config.ANALYSIS_DIR / "analysis_documents.jsonl"),
        ("reliability:documents", "reliability_documents", config.RELIABILITY_DIR / "reliability_documents.jsonl"),
        ("provenance:jsonl", "provenance", config.PROVENANCE_DIR / "provenance.jsonl"),
    ]
    artifacts = [_pipeline_artifact(id_, label, path) for id_, label, path in artifact_paths]
    for suffix in ('parquet', 'jsonl'):
        identity, label = f'serving:edna_retrieval_{suffix}', f'anemone_retrieval_documents.{suffix}'
        try:
            artifacts.append(_pipeline_artifact(identity, label, edna_retrieval_path(suffix)))
        except (ValueError, OSError, KeyError, SnapshotError):
            # Keep recovery/preflight available while withholding incomplete data.
            artifacts.append(PipelineArtifactInfo(id=identity, label=label,
                path=str(config.SERVING_DIR/'edna_current.json'), exists=False,
                note='eDNA publication unavailable; rerun materialization.'))
    return artifacts


def _pipeline_database_snapshot() -> Dict[str, Any]:
    payload = _database_status()
    if not payload.get("available"):
        return payload
    try:
        engine = create_engine(
            config.DATABASE_URL,
            **config.database_engine_options(),
        )
        with engine.connect() as conn:
            payload["retrieval_documents"] = int(conn.execute(text("SELECT count(*) FROM retrieval_document WHERE active IS TRUE")).scalar() or 0)
            payload["embedded_documents"] = int(conn.execute(text("SELECT count(*) FROM retrieval_document WHERE active IS TRUE AND embedding IS NOT NULL")).scalar() or 0)
            payload["anchor_events"] = int(conn.execute(text("SELECT count(*) FROM anchor_event")).scalar() or 0)
            payload["cross_source_links"] = int(conn.execute(text("SELECT count(*) FROM cross_source_link")).scalar() or 0)
    except Exception:
        logger.exception("Pipeline database detail check failed")
        payload["detail_error"] = "Database detail check is unavailable"
    return payload


def _pipeline_stage_infos() -> List[PipelineStageInfo]:
    return [PipelineStageInfo(**stage) for stage in PIPELINE_STAGES]


def _pipeline_readiness(
    raw_sources: List[PipelineArtifactInfo],
    artifacts: List[PipelineArtifactInfo],
) -> Dict[str, Any]:
    required_raw_ids = {f"raw:{key}" for key in config.RAW_FILES}
    missing_raw = [
        item.id.removeprefix("raw:")
        for item in raw_sources
        if item.id in required_raw_ids and not item.exists
    ]
    missing_core_artifacts = [
        item.label
        for item in artifacts
        if item.id in {
            "serving:sample_registry",
            "serving:sample_context",
            "serving:retrieval_jsonl",
            "serving:retrieval_parquet",
            "canonical:anchors",
            "canonical:links",
        }
        and not item.exists
    ]
    return {
        "required_raw_ready": not missing_raw,
        "corpus_artifacts_ready": not missing_core_artifacts,
        "sst_available": any(item.id == "raw:sst_netcdf" and item.exists for item in raw_sources),
        "missing_required_raw": missing_raw,
        "missing_core_artifacts": missing_core_artifacts,
        "manual_only": True,
    }


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()
    except ValueError:
        return None


def _artifact_freshness_status(item: PipelineArtifactInfo, now: datetime) -> tuple[str, Optional[float]]:
    if not item.exists:
        return "missing", None
    modified_at = _parse_iso_datetime(item.modified_at)
    if not modified_at:
        return "unknown", None
    age_days = round((now - modified_at).total_seconds() / 86400, 2)
    if age_days <= 7:
        return "recent", age_days
    if age_days <= 30:
        return "aged", age_days
    return "archival", age_days


def _pipeline_artifact_freshness(
    raw_sources: List[PipelineArtifactInfo],
    artifacts: List[PipelineArtifactInfo],
) -> List[PipelineArtifactFreshness]:
    now = datetime.now().astimezone()
    raw_datetimes = [
        parsed
        for parsed in (_parse_iso_datetime(item.modified_at) for item in raw_sources if item.exists)
        if parsed is not None
    ]
    latest_raw = max(raw_datetimes) if raw_datetimes else None
    latest_raw_text = latest_raw.isoformat(timespec="seconds") if latest_raw else None
    rows: List[PipelineArtifactFreshness] = []

    for kind, items in (("raw", raw_sources), ("derived", artifacts)):
        for item in items:
            freshness_status, age_days = _artifact_freshness_status(item, now)
            modified_at = _parse_iso_datetime(item.modified_at)
            if kind == "raw":
                lineage_status = "source"
            elif not item.exists:
                lineage_status = "missing"
            elif not latest_raw or not modified_at:
                lineage_status = "unknown"
            elif modified_at >= latest_raw:
                lineage_status = "fresh_against_raw"
            else:
                lineage_status = "older_than_latest_raw"
            rows.append(
                PipelineArtifactFreshness(
                    id=item.id,
                    label=item.label,
                    kind=kind,
                    path=item.path,
                    exists=item.exists,
                    freshness_status=freshness_status,
                    lineage_status=lineage_status,
                    age_days=age_days,
                    modified_at=item.modified_at,
                    latest_raw_modified_at=latest_raw_text,
                    rows=item.rows,
                    size_bytes=item.size_bytes,
                    note=item.note,
                )
            )
    return rows


def _debug_artifacts() -> Dict[str, Dict[str, Any]]:
    artifacts: Dict[str, Path] = {
        "project_root": PROJECT_ROOT,
        "data_dir": config.DATA_DIR,
        "raw_dir": config.RAW_DIR,
        "normalized_dir": config.NORMALIZED_DIR,
        "canonical_dir": config.CANONICAL_DIR,
        "serving_dir": config.SERVING_DIR,
        "analysis_dir": config.ANALYSIS_DIR,
        "reliability_dir": config.RELIABILITY_DIR,
        "provenance_dir": config.PROVENANCE_DIR,
        "retrieval_documents_jsonl": config.SERVING_DIR / "retrieval_documents.jsonl",
        "retrieval_documents_parquet": config.SERVING_DIR / "retrieval_documents.parquet",
        "sample_registry": config.SERVING_DIR / "sample_registry.parquet",
        "sample_multisource_context": config.SERVING_DIR / "sample_multisource_context.parquet",
        "provenance_jsonl": config.PROVENANCE_DIR / "provenance.jsonl",
    }
    for dataset, cfg in EXPLORE_DATASETS.items():
        artifacts[f"dataset:{dataset}"] = cfg["path"]
    return {name: _artifact_info(path) for name, path in artifacts.items()}


def _dataset_config(dataset: str) -> Dict[str, Any]:
    try:
        return EXPLORE_DATASETS[dataset]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset}") from exc


def _derive_sample_fields(df: pd.DataFrame) -> pd.DataFrame:
    if "sample_id" not in df.columns:
        return df
    parts = df["sample_id"].astype("string").str.split("-", expand=True)
    if "year_month" not in df.columns and parts.shape[1] >= 2:
        df["year_month"] = parts[0].astype("string") + "-" + parts[1].astype("string")
    if "bay" not in df.columns and parts.shape[1] >= 3:
        df["bay"] = parts[2].astype("string")
    if "station_code" not in df.columns and parts.shape[1] >= 4:
        df["station_code"] = parts[3].astype("string")
    return df


@lru_cache(maxsize=16)
def _read_explore_dataset(dataset: str) -> pd.DataFrame:
    cfg = _dataset_config(dataset)
    path = cfg["path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset artifact is missing: {path}")
    return _derive_sample_fields(pd.read_parquet(path))


@lru_cache(maxsize=8)
def _read_parquet_artifact(path_text: str) -> pd.DataFrame:
    path = Path(path_text)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Data artifact is missing: {path}")
    return pd.read_parquet(path)


def _ctd_profiles_df() -> pd.DataFrame:
    return _read_parquet_artifact(str(config.NORMALIZED_DIR / "ctd_profile_standardized.parquet"))


def _ctd_summary_df() -> pd.DataFrame:
    return _read_explore_dataset("ctd_summary")


def _sample_context_df() -> pd.DataFrame:
    return _read_parquet_artifact(str(config.SERVING_DIR / "sample_multisource_context.parquet"))


def _sst_points_df() -> pd.DataFrame:
    return _read_parquet_artifact(str(config.NORMALIZED_DIR / "sst_point_timeseries.parquet"))


def _sst_daily_df() -> pd.DataFrame:
    return _read_explore_dataset("sst_daily")


def _parse_taxa_json(value: Any, *, label_keys: Iterable[str]) -> List[TaxaEntry]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        rows = json.loads(value)
    except Exception:
        return []
    entries: List[TaxaEntry] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        label = next((str(row[key]) for key in label_keys if row.get(key)), "")
        raw_value = row.get("abundance_value", row.get("abundance", row.get("value")))
        if not label or raw_value is None:
            continue
        try:
            numeric = float(raw_value)
        except (TypeError, ValueError):
            continue
        entries.append(TaxaEntry(label=label, value=numeric))
    return entries


def _analysis_artifacts() -> Dict[str, Path]:
    return {
        "ctd_monthly_trends": config.ANALYSIS_DIR / "ctd_monthly_trends.parquet",
        "taxa_env_correlations": config.ANALYSIS_DIR / "taxa_env_correlations.parquet",
        "diversity_indices": config.ANALYSIS_DIR / "diversity_indices.parquet",
        "taxa_cooccurrence": config.ANALYSIS_DIR / "taxa_cooccurrence.parquet",
        "sst_ctd_validation": config.RELIABILITY_DIR / "sst_ctd_validation.parquet",
        "gap_interpolation": config.RELIABILITY_DIR / "gap_interpolation.parquet",
        "diversity_prediction": config.RELIABILITY_DIR / "diversity_prediction.parquet",
        "corroboration": config.RELIABILITY_DIR / "corroboration.parquet",
    }


def _analysis_df(name: str) -> pd.DataFrame:
    try:
        return _read_parquet_artifact(str(_analysis_artifacts()[name]))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown analysis artifact: {name}") from exc


def _records_limited(df: pd.DataFrame, limit: int = 500) -> List[Dict[str, Any]]:
    return _records(df.head(limit))


def _mean_by_group(df: pd.DataFrame, group: str, columns: List[str]) -> List[Dict[str, Any]]:
    existing = [column for column in columns if column in df.columns]
    if group not in df.columns or not existing:
        return []
    grouped = df.groupby(group, dropna=False)[existing].mean(numeric_only=True).reset_index()
    return _records(grouped)


def _cooccurrence_pairs(df: pd.DataFrame, limit: int) -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    labels = list(df.index.astype(str))
    for i, first in enumerate(labels):
        for j in range(i + 1, len(labels)):
            value = _json_safe_value(df.iloc[i, j])
            if value is None:
                continue
            pairs.append({"genus_a": first, "genus_b": labels[j], "jaccard": value})
    pairs.sort(key=lambda row: float(row["jaccard"]), reverse=True)
    return pairs[:limit]


def _database_engine():
    return create_engine(
        config.DATABASE_URL,
        **config.database_engine_options(),
    )


def _quote_identifier(engine: Any, identifier: str) -> str:
    return engine.dialect.identifier_preparer.quote(identifier)


def _validate_table_and_columns(engine: Any, table: str) -> List[str]:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if table not in table_names:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")
    return [column["name"] for column in inspector.get_columns(table)]


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        return _json_safe_value(value.item())
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    return [
        {column: _json_safe_value(row[column]) for column in df.columns}
        for _, row in df.iterrows()
    ]


def _read_json_file(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _evaluation_csv_candidates() -> List[Dict[str, Any]]:
    eval_dir = config.EVALUATION_DIR
    if not eval_dir.exists():
        return []

    candidates: Dict[str, Dict[str, Any]] = {}

    def add_candidate(run_id: str, csv_path: Path, root_path: Path) -> None:
        if run_id in candidates or not csv_path.exists():
            return
        candidates[run_id] = {
            "run_id": run_id,
            "csv_path": csv_path,
            "root_path": root_path,
        }

    for csv_path in sorted(eval_dir.rglob("*.csv")):
        if "comparison" in csv_path.stem:
            continue
        if "__pycache__" in csv_path.parts:
            continue
        run_id = csv_path.parent.name if csv_path.name in {"results.csv", "ablation_results.csv"} else csv_path.stem
        add_candidate(run_id, csv_path, csv_path.parent)

    return list(candidates.values())


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _evaluation_runs_root() -> Path:
    root = config.EVALUATION_DIR / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(value: Optional[str]) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value or "").strip("-_.")
    return cleaned[:60]


def _new_evaluation_run_id(run_type: str, model: str, tag: Optional[str]) -> str:
    parts = [
        "eval",
        _slug(run_type),
        datetime.now().strftime("%Y%m%dT%H%M%S"),
        _slug(model),
        _slug(tag),
        uuid.uuid4().hex[:8],
    ]
    return "_".join(part for part in parts if part)


def _job_output_dir(run_id: str) -> Path:
    return _artifact_path(_evaluation_runs_root(), run_id, "evaluation run")


def _job_status_path(job_id: str) -> Path:
    return _artifact_path(_evaluation_runs_root(), job_id, "evaluation job") / "progress.json"


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp_path.replace(path)


def _pipeline_runs_root() -> Path:
    root = config.DATA_DIR / "pipeline_runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _new_pipeline_run_id(tag: Optional[str]) -> str:
    parts = [
        "pipeline",
        datetime.now().strftime("%Y%m%dT%H%M%S"),
        _slug(tag),
        uuid.uuid4().hex[:8],
    ]
    return "_".join(part for part in parts if part)


def _pipeline_output_dir(run_id: str) -> Path:
    return _artifact_path(_pipeline_runs_root(), run_id, "pipeline run")


def _pipeline_status_path(job_id: str) -> Path:
    return _artifact_path(_pipeline_runs_root(), job_id, "pipeline job") / "progress.json"


def _pipeline_log_path(job_id: str) -> Path:
    return _artifact_path(_pipeline_runs_root(), job_id, "pipeline job") / "run.log"


def _pipeline_meta_path(job_id: str) -> Path:
    return _artifact_path(_pipeline_runs_root(), job_id, "pipeline job") / "run_meta.json"


def _pipeline_append_log(job_id: str, text_value: str) -> None:
    path = _pipeline_log_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text_value)
        if text_value and not text_value.endswith("\n"):
            f.write("\n")


def _pipeline_tail_log(job_id: str, limit_bytes: int = 20000) -> str:
    path = _pipeline_log_path(job_id)
    if not path.exists():
        return ""
    with path.open("rb") as f:
        size = path.stat().st_size
        f.seek(max(0, size - limit_bytes))
        return f.read().decode("utf-8", errors="replace")


def _pipeline_manifest_path(job_id: str) -> Path:
    return _artifact_path(_pipeline_runs_root(), job_id, "pipeline job") / "manifest.json"


def _model_dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def _git_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _pipeline_artifacts_payload(items: List[PipelineArtifactInfo]) -> List[Dict[str, Any]]:
    return [_model_dump(item) for item in items]


def _pipeline_needs_model_runtime(request: PipelineRunRequest) -> bool:
    return "embed_documents" in request.stages or (
        "load_db" in request.stages and request.embed_after_load
    )


def _pipeline_model_status(*, required: bool) -> Dict[str, Any]:
    if required:
        return _ollama_status()
    return {
        "available": None,
        "provider": config.MODEL_PROVIDER,
        "skipped": True,
        "reason": "The selected pipeline stages do not use a model runtime.",
    }


def _pipeline_runtime_snapshot(*, include_model_runtime: bool) -> Dict[str, Any]:
    raw_sources = _pipeline_raw_sources()
    artifacts = _pipeline_artifacts()
    return {
        "captured_at": _now_iso(),
        "raw_sources": _pipeline_artifacts_payload(raw_sources),
        "artifacts": _pipeline_artifacts_payload(artifacts),
        "database": _pipeline_database_snapshot(),
        "ollama": _pipeline_model_status(required=include_model_runtime),
    }


def _pipeline_command_plan(request: PipelineRunRequest) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = []
    for index, stage_id in enumerate(request.stages, start=1):
        stage = PIPELINE_STAGE_BY_ID[stage_id]
        command = _pipeline_command(stage_id, request)
        plan.append(
            {
                "index": index,
                "stage_id": stage_id,
                "label": stage["label"],
                "description": stage["description"],
                "command": command,
                "display_command": _display_command(command),
                "destructive": bool(stage.get("destructive")),
                "expensive": bool(stage.get("expensive")),
            }
        )
    return plan


def _pipeline_check(
    checks: List[PipelinePreflightCheck],
    *,
    id_: str,
    label: str,
    passed: bool,
    detail: str,
    required: bool = False,
    warning: bool = False,
) -> None:
    status = "pass" if passed else ("warn" if warning else "fail")
    severity = "info" if passed else ("warning" if warning else "blocker")
    checks.append(
        PipelinePreflightCheck(
            id=id_,
            label=label,
            status=status,
            severity=severity,
            required=required,
            detail=detail,
        )
    )


def _producer_selected(stage_ids: List[str], producer: str) -> bool:
    return producer in stage_ids


def _pipeline_preflight_payload(request: PipelineRunRequest) -> PipelinePreflightResponse:
    _validate_pipeline_stages(request.stages)
    if request.embedding_model:
        _allowed_model(
            request.embedding_model,
            default=config.EMBEDDING_MODEL,
            allowed=config.ALLOWED_EMBEDDING_MODELS,
            label="embedding model",
        )
    raw_sources = _pipeline_raw_sources()
    artifacts = _pipeline_artifacts()
    readiness = _pipeline_readiness(raw_sources, artifacts)
    database = _pipeline_database_snapshot()
    needs_model_runtime = _pipeline_needs_model_runtime(request)
    ollama = _pipeline_model_status(required=needs_model_runtime)
    checks: List[PipelinePreflightCheck] = []
    if 'edna_analysis' in request.stages:
        from preprocessing.edna_recipe import AnalysisRecipe
        try:
            AnalysisRecipe.model_validate_json(config.EDNA_ANALYSIS_RECIPE.read_text())
            recipe_valid = True
        except (ValueError, OSError):
            recipe_valid = False
        _pipeline_check(checks, id_='edna_recipe', label='eDNA analysis recipe', passed=recipe_valid,
                        detail='Validated operator recipe.' if recipe_valid else 'Missing or invalid EDNA_ANALYSIS_RECIPE.', required=True)
        index = request.stages.index('edna_analysis')
        ordered = all(stage not in request.stages or request.stages.index(stage) < index for stage in ('load_db', 'materialize_edna_retrieval')) and ('publish_provenance' not in request.stages or index < request.stages.index('publish_provenance'))
        _pipeline_check(checks, id_='edna_analysis_order', label='eDNA analysis order', passed=ordered,
                        detail='Analysis must follow canonical loading/materialization and precede provenance publication.', required=True)

    _pipeline_check(
        checks,
        id_="manual_only",
        label="Manual batch mode",
        passed=True,
        detail="This runner only starts from an explicit operator request.",
        required=True,
    )
    _pipeline_check(
        checks,
        id_="stages_selected",
        label="Stages selected",
        passed=bool(request.stages),
        detail=", ".join(request.stages) if request.stages else "No stages selected.",
        required=True,
    )

    missing_raw = list(readiness.get("missing_required_raw") or [])
    _pipeline_check(
        checks,
        id_="required_raw",
        label="Required CTD/metagenome raw files",
        passed=not missing_raw or set(request.stages) == {'edna_analysis'},
        detail="All required raw source files are present." if not missing_raw else f"Missing: {', '.join(missing_raw)}",
        required=True,
    )

    sst_source = next((item for item in raw_sources if item.id == "raw:sst_netcdf"), None)
    sst_files = 0
    if sst_source and sst_source.exists:
        match = re.search(r"(\d+) NetCDF", str(sst_source.note or ""))
        sst_files = int(match.group(1)) if match else 0
    if "ingest" in request.stages and not request.skip_sst:
        _pipeline_check(
            checks,
            id_="sst_source",
            label="SST NetCDF source",
            passed=sst_files > 0,
            detail=f"{sst_files} NetCDF files available." if sst_files > 0 else "No SST NetCDF files found; use skip_sst for CTD/metagenome-only ingestion.",
            required=True,
        )
    elif "ingest" in request.stages and request.skip_sst:
        _pipeline_check(
            checks,
            id_="sst_source",
            label="SST NetCDF source",
            passed=True,
            detail="SST preprocessing is explicitly skipped for this run.",
            required=False,
        )

    artifact_by_id = {item.id: item for item in artifacts}
    dependency_checks = [
        ("build_retrieval_docs", "normalized:ctd_summary", "ingest", "CTD summary artifact"),
        ("build_retrieval_docs", "serving:sample_registry", "ingest", "Sample registry artifact"),
        ("pre_analysis", "serving:sample_context", "ingest", "Sample context artifact"),
        ("reliability", "analysis:documents", "pre_analysis", "Analysis documents"),
        ("load_db", "serving:retrieval_parquet", "build_retrieval_docs", "Retrieval parquet corpus"),
        ("load_db", "canonical:anchors", "build_retrieval_docs", "Anchor events"),
        ("load_db", "canonical:links", "build_retrieval_docs", "Cross-source links"),
        ("publish_provenance", "serving:retrieval_parquet", "build_retrieval_docs", "Retrieval parquet corpus"),
        ("publish_provenance", "serving:edna_retrieval_parquet", "materialize_edna_retrieval", "eDNA retrieval corpus"),
    ]
    for stage_id, artifact_id, producer, label in dependency_checks:
        if stage_id not in request.stages:
            continue
        artifact = artifact_by_id.get(artifact_id)
        produced_in_run = _producer_selected(request.stages, producer)
        exists = bool(artifact and artifact.exists)
        _pipeline_check(
            checks,
            id_=f"input:{stage_id}:{artifact_id}",
            label=label,
            passed=exists or produced_in_run,
            detail=(
                f"Present: {artifact.path}" if exists and artifact
                else f"Expected to be produced by stage '{producer}' in this run." if produced_in_run
                else f"Missing required input artifact: {artifact_id}"
            ),
            required=not produced_in_run,
            warning=produced_in_run and not exists,
        )

    needs_database = (
        "backup_database" in request.stages
        or "load_db" in request.stages
        or "materialize_edna_retrieval" in request.stages
        or "edna_analysis" in request.stages
        or "embed_documents" in request.stages
        or "publish_provenance" in request.stages
    )
    if needs_database:
        db_available = bool(database.get("available"))
        _pipeline_check(
            checks,
            id_="database",
            label="PostgreSQL connection",
            passed=db_available,
            detail="Database connection available." if db_available else str(database.get("error") or "Database is unavailable."),
            required=not request.dry_run,
            warning=request.dry_run,
        )

    mutation_stages = [
        stage
        for stage in ("load_db", "materialize_edna_retrieval")
        if stage in request.stages
    ]
    if mutation_stages:
        backup_index = (
            request.stages.index("backup_database")
            if "backup_database" in request.stages
            else -1
        )
        mutation_index = min(request.stages.index(stage) for stage in mutation_stages)
        backup_ordered = backup_index >= 0 and backup_index < mutation_index
        _pipeline_check(
            checks,
            id_="database_backup_guard",
            label="Pre-mutation database backup",
            passed=request.dry_run or backup_ordered,
            detail=(
                "Dry-run does not modify the database."
                if request.dry_run
                else "A verified database backup is ordered before load_db."
                if backup_ordered and mutation_stages == ["load_db"]
                else "A verified database backup is ordered before database mutation."
                if backup_ordered
                else "Non-dry-run database loading requires backup_database before load_db."
                if mutation_stages == ["load_db"]
                else "Non-dry-run database mutation requires backup_database first."
            ),
            required=not request.dry_run,
        )
        _pipeline_check(
            checks,
            id_="database_reset_guard",
            label="Database mutation mode",
            passed=True,
            detail=(
                "Dry-run does not modify the database."
                if request.dry_run
                else "Explicit reset mode selected; the corpus tables will be replaced."
                if request.reset_database
                else "Transactional incremental upsert selected; stale rows are retained."
            ),
            required=False,
        )
        reset_confirmation_required = (
            not request.dry_run and request.reset_database
        )
        reset_confirmation_valid = (
            request.reset_confirmation == PIPELINE_RESET_CONFIRMATION
        )
        _pipeline_check(
            checks,
            id_="database_reset_confirmation",
            label="Destructive reset confirmation",
            passed=(
                not reset_confirmation_required
                or reset_confirmation_valid
            ),
            detail=(
                "Destructive reset confirmation is not required."
                if not reset_confirmation_required
                else "Destructive reset confirmation accepted."
                if reset_confirmation_valid
                else (
                    "A non-dry-run database reset requires the exact "
                    f"confirmation phrase: {PIPELINE_RESET_CONFIRMATION}"
                )
            ),
            required=reset_confirmation_required,
        )

    if "publish_provenance" in request.stages:
        publication_id = (request.tag or "").strip()
        has_publication_id = bool(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", publication_id)
        )
        _pipeline_check(
            checks,
            id_="provenance_publication_id",
            label="Immutable provenance publication ID",
            passed=request.dry_run or has_publication_id,
            detail=(
                "Dry-run uses a placeholder and does not publish objects."
                if request.dry_run and not has_publication_id
                else f"Snapshot publication ID: {publication_id}"
                if has_publication_id
                else "Executing publish_provenance requires a unique 1-128 character pipeline tag using letters, numbers, '.', '_', or '-'."
            ),
            required=not request.dry_run,
        )

    if "backup_database" in request.stages:
        capability = backup_capability()
        _pipeline_check(
            checks,
            id_="database_backup_tools",
            label="Database backup tooling",
            passed=bool(capability.get("available")),
            detail=str(capability.get("detail") or "Backup tooling unavailable."),
            required=not request.dry_run,
            warning=request.dry_run,
        )

    if needs_model_runtime:
        model_runtime_available = bool(ollama.get("available"))
        _pipeline_check(
            checks,
            id_="model_runtime_embeddings",
            label="Embedding model runtime",
            passed=model_runtime_available,
            detail=(
                "The configured model runtime is available for embeddings."
                if model_runtime_available
                else str(ollama.get("error") or "Model runtime is unavailable.")
            ),
            required=not request.dry_run,
            warning=request.dry_run,
        )

    blockers = [check.detail for check in checks if check.status == "fail"]
    warnings = [check.detail for check in checks if check.status == "warn"]
    return PipelinePreflightResponse(
        generated_at=_now_iso(),
        ok=not blockers,
        blockers=blockers,
        warnings=warnings,
        request=_model_dump(request),
        checks=checks,
        command_plan=_pipeline_command_plan(request),
        raw_sources=raw_sources,
        artifacts=artifacts,
        database=database,
        ollama=ollama,
    )


def _pipeline_snapshot_diffs(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    before_items = {
        str(item.get("id")): item
        for item in list(before.get("raw_sources") or []) + list(before.get("artifacts") or [])
        if isinstance(item, dict)
    }
    after_items = {
        str(item.get("id")): item
        for item in list(after.get("raw_sources") or []) + list(after.get("artifacts") or [])
        if isinstance(item, dict)
    }
    artifact_diffs: List[Dict[str, Any]] = []
    for item_id in sorted(set(before_items) | set(after_items)):
        before_item = before_items.get(item_id, {})
        after_item = after_items.get(item_id, {})
        before_rows = before_item.get("rows")
        after_rows = after_item.get("rows")
        row_delta = None
        if isinstance(before_rows, int) and isinstance(after_rows, int):
            row_delta = after_rows - before_rows
        changed = any(
            before_item.get(key) != after_item.get(key)
            for key in ("exists", "rows", "size_bytes", "modified_at")
        )
        artifact_diffs.append(
            {
                "id": item_id,
                "label": after_item.get("label") or before_item.get("label") or item_id,
                "exists_before": before_item.get("exists"),
                "exists_after": after_item.get("exists"),
                "rows_before": before_rows,
                "rows_after": after_rows,
                "rows_delta": row_delta,
                "size_before": before_item.get("size_bytes"),
                "size_after": after_item.get("size_bytes"),
                "modified_before": before_item.get("modified_at"),
                "modified_after": after_item.get("modified_at"),
                "changed": changed,
            }
        )

    before_db = before.get("database") if isinstance(before.get("database"), dict) else {}
    after_db = after.get("database") if isinstance(after.get("database"), dict) else {}
    database_diffs = {
        key: {
            "before": before_db.get(key),
            "after": after_db.get(key),
            "delta": after_db.get(key) - before_db.get(key)
            if isinstance(before_db.get(key), int) and isinstance(after_db.get(key), int)
            else None,
        }
        for key in sorted(set(before_db) | set(after_db))
        if before_db.get(key) != after_db.get(key)
    }
    return {"artifacts": artifact_diffs, "database": database_diffs}


def _pipeline_summary_from_payload(run_id: str, payload: Dict[str, Any]) -> PipelineRunSummary:
    stage_results = payload.get("stage_results") if isinstance(payload.get("stage_results"), list) else []
    failed_stage = next(
        (
            str(result.get("stage_id"))
            for result in stage_results
            if isinstance(result, dict) and result.get("status") == "failed"
        ),
        None,
    )
    request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    stages = payload.get("stages")
    if not isinstance(stages, list):
        stages = request_payload.get("stages") if isinstance(request_payload.get("stages"), list) else []
    job_id = str(payload.get("job_id") or run_id)
    return PipelineRunSummary(
        run_id=str(payload.get("run_id") or run_id),
        job_id=job_id,
        status=str(payload.get("status") or "unknown"),
        tag=payload.get("tag") or request_payload.get("tag"),
        dry_run=bool(payload.get("dry_run", request_payload.get("dry_run", False))),
        stages=[str(stage) for stage in stages],
        stage_count=len(stage_results) if stage_results else len(stages),
        failed_stage=failed_stage,
        started_at=payload.get("started_at"),
        completed_at=payload.get("completed_at"),
        duration_seconds=payload.get("duration_seconds"),
        output_dir=payload.get("output_dir"),
        manifest_path=payload.get("manifest_path"),
        log_path=payload.get("log_path"),
        error=payload.get("error"),
    )


def _pipeline_manifest_for_dir(run_dir: Path) -> Dict[str, Any]:
    manifest = _read_json_file(run_dir / "manifest.json")
    if manifest:
        return manifest
    meta = _read_json_file(run_dir / "run_meta.json")
    progress = _read_json_file(run_dir / "progress.json")
    merged = {**progress, **meta}
    if merged:
        merged.setdefault("run_id", run_dir.name)
        merged.setdefault("job_id", run_dir.name)
        merged.setdefault("output_dir", str(run_dir))
        merged.setdefault("manifest_path", str(run_dir / "manifest.json"))
        merged.setdefault("log_path", str(run_dir / "run.log"))
    return merged


def _pipeline_run_summaries(limit: int = 50) -> List[PipelineRunSummary]:
    runs_root = _pipeline_runs_root()
    summaries: List[PipelineRunSummary] = []
    for run_dir in sorted((path for path in runs_root.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True):
        payload = _pipeline_manifest_for_dir(run_dir)
        if not payload:
            continue
        summary = _pipeline_summary_from_payload(run_dir.name, payload)
        summaries.append(summary)
    summaries.sort(key=lambda item: item.started_at or item.completed_at or item.run_id, reverse=True)
    return summaries[:limit]


def _pipeline_job_statuses(limit: int = 50, *, active_only: bool = False) -> List[PipelineJobStatus]:
    runs_root = _pipeline_runs_root()
    statuses: List[PipelineJobStatus] = []
    for progress_path in sorted(runs_root.glob("*/progress.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        payload = _read_json_file(progress_path)
        if not payload:
            continue
        if active_only and str(payload.get("status") or "") in PIPELINE_TERMINAL_STATES:
            continue
        try:
            statuses.append(PipelineJobStatus(**payload))
        except Exception:
            continue
    statuses.sort(key=lambda item: item.updated_at or item.started_at or item.run_id, reverse=True)
    return statuses[:limit]


def _pipeline_stage_logs(
    job_id: str,
    manifest: Optional[Dict[str, Any]] = None,
    limit_bytes: int = 200000,
) -> List[PipelineStageLog]:
    manifest_payload = manifest or _pipeline_manifest_for_dir(_pipeline_output_dir(job_id))
    log_text = _pipeline_tail_log(job_id, limit_bytes)
    buffers: Dict[str, List[str]] = {}
    stage_order: List[str] = []
    current_stage: Optional[str] = None
    header_pattern = re.compile(r"^## \[\d+/\d+\] ([a-zA-Z0-9_.-]+)\s*$")

    for line in log_text.splitlines():
        match = header_pattern.match(line)
        if match:
            current_stage = match.group(1)
            if current_stage not in buffers:
                buffers[current_stage] = []
                stage_order.append(current_stage)
        if current_stage:
            buffers.setdefault(current_stage, []).append(line)

    stage_results = manifest_payload.get("stage_results") if isinstance(manifest_payload.get("stage_results"), list) else []
    for result in stage_results:
        if not isinstance(result, dict):
            continue
        stage_id = str(result.get("stage_id") or "")
        if stage_id and stage_id not in stage_order:
            stage_order.append(stage_id)

    request_payload = manifest_payload.get("request") if isinstance(manifest_payload.get("request"), dict) else {}
    request_stages = request_payload.get("stages") if isinstance(request_payload.get("stages"), list) else manifest_payload.get("stages")
    for stage_id in request_stages if isinstance(request_stages, list) else []:
        stage_text = str(stage_id)
        if stage_text and stage_text not in stage_order:
            stage_order.append(stage_text)

    result_by_stage = {
        str(result.get("stage_id")): result
        for result in stage_results
        if isinstance(result, dict) and result.get("stage_id")
    }
    rows: List[PipelineStageLog] = []
    for stage_id in stage_order:
        result = result_by_stage.get(stage_id, {})
        log = "\n".join(buffers.get(stage_id, []))
        stage_info = PIPELINE_STAGE_BY_ID.get(stage_id, {})
        rows.append(
            PipelineStageLog(
                stage_id=stage_id,
                label=stage_info.get("label") or stage_id,
                command=result.get("command"),
                status=result.get("status"),
                return_code=result.get("return_code"),
                duration_seconds=result.get("duration_seconds"),
                line_count=len(buffers.get(stage_id, [])),
                bytes=len(log.encode("utf-8")),
                log=log,
            )
        )
    return rows


def _pipeline_run_detail_or_404(run_id: str, limit_bytes: int = 50000) -> PipelineRunDetailResponse:
    run_dir = _pipeline_output_dir(run_id)
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown pipeline run: {run_id}")
    manifest = _pipeline_manifest_for_dir(run_dir)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Pipeline run has no manifest: {run_id}")
    progress = _read_json_file(run_dir / "progress.json")
    summary = _pipeline_summary_from_payload(run_id, manifest)
    return PipelineRunDetailResponse(
        summary=summary,
        manifest=manifest,
        progress=progress,
        log_tail=_pipeline_tail_log(summary.job_id or run_id, limit_bytes),
        stage_logs=_pipeline_stage_logs(summary.job_id or run_id, manifest, limit_bytes),
    )


def _pipeline_status_payload(
    *,
    job_id: str,
    run_id: str,
    status: str,
    stages: List[str],
    current: int = 0,
    total: Optional[int] = None,
    phase: str = "queued",
    stage_id: Optional[str] = None,
    message: str = "",
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    error: Optional[str] = None,
    result_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    total_value = len(stages) if total is None else total
    percent = round((current / total_value) * 100, 2) if total_value else 0.0
    return {
        "job_id": job_id,
        "run_id": run_id,
        "status": status,
        "current": current,
        "total": total_value,
        "percent": percent,
        "phase": phase,
        "stage_id": stage_id,
        "message": message,
        "started_at": started_at,
        "updated_at": _now_iso(),
        "completed_at": completed_at,
        "error": error,
        "output_dir": str(_pipeline_output_dir(run_id)),
        "log_path": str(_pipeline_log_path(job_id)),
        "stages": stages,
        "result_run_id": result_run_id,
    }


def _write_pipeline_status(payload: Dict[str, Any], **updates: Any) -> PipelineJobStatus:
    next_payload = {**payload, **updates}
    current = int(next_payload.get("current") or 0)
    total = int(next_payload.get("total") or 0)
    next_payload["current"] = current
    next_payload["total"] = total
    next_payload["percent"] = round((current / total) * 100, 2) if total else 0.0
    next_payload["updated_at"] = _now_iso()
    _write_json_atomic(_pipeline_status_path(str(next_payload["job_id"])), next_payload)
    payload.clear()
    payload.update(next_payload)
    return PipelineJobStatus(**next_payload)


def _read_pipeline_status_or_404(job_id: str) -> PipelineJobStatus:
    path = _pipeline_status_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Unknown pipeline job: {job_id}")
    payload = _read_json_file(path)
    return PipelineJobStatus(**payload)


def _validate_pipeline_stages(stage_ids: List[str]) -> None:
    unknown = [stage_id for stage_id in stage_ids if stage_id not in PIPELINE_STAGE_IDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown pipeline stage: {unknown[0]}")


def _pipeline_command(
    stage_id: str,
    request: PipelineRunRequest,
    *,
    pipeline_run_id: Optional[str] = None,
) -> List[str]:
    command_map: Dict[str, List[str]] = {
        "edna_analysis": [sys.executable, "scripts/run_edna_analysis.py", "--recipe", str(config.EDNA_ANALYSIS_RECIPE), "--execute"],
        "validate_raw": [sys.executable, "scripts/ingest.py", "--validate-only"],
        "ingest": [sys.executable, "scripts/ingest.py"],
        "build_retrieval_docs": [sys.executable, "scripts/build_retrieval_docs.py"],
        "pre_analysis": [sys.executable, "scripts/run_pre_analysis.py"],
        "reliability": [sys.executable, "scripts/run_reliability.py"],
        "backup_database": [
            sys.executable,
            "scripts/database_backup.py",
            "create",
            "--output-dir",
            str(config.DATABASE_BACKUP_DIR),
            "--label",
            request.tag or "pipeline",
            "--restore-test",
        ],
        "load_db": [sys.executable, "scripts/load_db.py"],
        "materialize_edna_retrieval": [
            sys.executable,
            "scripts/materialize_edna_retrieval.py",
            "--execute",
        ],
        "embed_documents": [
            sys.executable,
            "scripts/update_embeddings.py",
            "--batch-size",
            str(request.embedding_batch_size),
        ],
        "publish_provenance": [
            sys.executable,
            "scripts/build_provenance_manifest.py",
            "--publish",
            "--run-id",
            request.tag or "dry-run-placeholder",
            "--pipeline-run-id",
            pipeline_run_id or request.tag or "dry-run-placeholder",
        ],
    }
    command = list(command_map[stage_id])
    if stage_id == "ingest" and request.skip_sst:
        command.append("--skip-sst")
    if stage_id == "load_db" and request.reset_database:
        command.append("--reset")
    if stage_id == "load_db" and not request.reset_database:
        command.append("--upsert")
    if (
        stage_id == "load_db"
        and request.embed_after_load
        and "materialize_edna_retrieval" not in request.stages
    ):
        command.append("--embed")
    return command


def _display_command(command: List[str]) -> str:
    return " ".join("python" if part == sys.executable else part for part in command)


def _pipeline_env(request: PipelineRunRequest) -> Dict[str, str]:
    env = os.environ.copy()
    if request.embedding_model:
        env["EMBEDDING_MODEL"] = request.embedding_model
    return env


def _run_pipeline_job(
    *,
    request: PipelineRunRequest,
    job_id: str,
    run_id: str,
    cancel_event: threading.Event,
    status_payload: Dict[str, Any],
) -> None:
    started = time.time()
    started_at = _now_iso()
    stage_results: List[Dict[str, Any]] = []
    preflight = _pipeline_preflight_payload(request)
    include_model_runtime = _pipeline_needs_model_runtime(request)
    before_snapshot = _pipeline_runtime_snapshot(
        include_model_runtime=include_model_runtime
    )
    command_plan = _pipeline_command_plan(request)
    meta: Dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "job_id": job_id,
        "tag": request.tag,
        "notes": request.notes,
        "dry_run": request.dry_run,
        "skip_sst": request.skip_sst,
        "reset_database": request.reset_database,
        "embed_after_load": request.embed_after_load,
        "embedding_model": request.embedding_model or config.EMBEDDING_MODEL,
        "embedding_batch_size": request.embedding_batch_size,
        "stages": request.stages,
        "request": _model_dump(request),
        "manual_only": True,
        "git_commit": _git_commit(),
        "command_plan": command_plan,
        "preflight": _model_dump(preflight),
        "artifacts_before": before_snapshot,
        "stage_results": stage_results,
        "status": "running",
        "started_at": started_at,
        "output_dir": str(_pipeline_output_dir(run_id)),
        "manifest_path": str(_pipeline_manifest_path(job_id)),
        "log_path": str(_pipeline_log_path(job_id)),
    }
    _write_json_atomic(_pipeline_manifest_path(job_id), meta)
    _write_json_atomic(_pipeline_meta_path(job_id), meta)
    _write_pipeline_status(status_payload, status="running", phase="starting", started_at=started_at)
    _pipeline_append_log(job_id, f"# Pipeline run {run_id}")
    _pipeline_append_log(job_id, f"started_at={started_at}")
    _pipeline_append_log(job_id, f"dry_run={request.dry_run}")
    _pipeline_append_log(job_id, f"manifest={_pipeline_manifest_path(job_id)}")

    for index, stage_id in enumerate(request.stages, start=1):
        if cancel_event.is_set():
            meta["status"] = "cancelled"
            break

        command = _pipeline_command(stage_id, request, pipeline_run_id=run_id)
        command_text = _display_command(command)
        stage_started = time.time()
        _pipeline_append_log(job_id, "")
        _pipeline_append_log(job_id, f"## [{index}/{len(request.stages)}] {stage_id}")
        _pipeline_append_log(job_id, f"$ {command_text}")
        _write_pipeline_status(
            status_payload,
            phase="dry_run" if request.dry_run else "running_stage",
            stage_id=stage_id,
            message=f"{'Planned' if request.dry_run else 'Running'} {stage_id}",
        )

        if request.dry_run:
            result = {
                "stage_id": stage_id,
                "command": command_text,
                "status": "planned",
                "return_code": 0,
                "duration_seconds": 0.0,
            }
            stage_results.append(result)
            meta["stage_results"] = stage_results
            _write_json_atomic(_pipeline_manifest_path(job_id), meta)
            _pipeline_append_log(job_id, "DRY RUN: command not executed.")
            _write_pipeline_status(
                status_payload,
                current=index,
                phase="dry_run",
                message=f"Planned {stage_id}",
            )
            continue

        process: Optional[subprocess.Popen[str]] = None
        try:
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                env=_pipeline_env(request),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            with PIPELINE_JOB_LOCK:
                PIPELINE_PROCESSES[job_id] = process

            assert process.stdout is not None
            for line in process.stdout:
                _pipeline_append_log(job_id, line)
                if cancel_event.is_set() and process.poll() is None:
                    process.terminate()

            return_code = process.wait()
        finally:
            with PIPELINE_JOB_LOCK:
                PIPELINE_PROCESSES.pop(job_id, None)

        duration = round(time.time() - stage_started, 2)
        if cancel_event.is_set():
            result = {
                "stage_id": stage_id,
                "command": command_text,
                "status": "cancelled",
                "return_code": process.returncode if process else None,
                "duration_seconds": duration,
            }
            stage_results.append(result)
            meta["stage_results"] = stage_results
            _write_json_atomic(_pipeline_manifest_path(job_id), meta)
            meta["status"] = "cancelled"
            break

        result_status = "complete" if return_code == 0 else "failed"
        result = {
            "stage_id": stage_id,
            "command": command_text,
            "status": result_status,
            "return_code": return_code,
            "duration_seconds": duration,
        }
        stage_results.append(result)
        meta["stage_results"] = stage_results
        _write_json_atomic(_pipeline_manifest_path(job_id), meta)
        _write_pipeline_status(
            status_payload,
            current=index,
            phase="stage_complete" if return_code == 0 else "failed",
            stage_id=stage_id,
            message=f"{stage_id} exited with {return_code}",
        )
        if return_code != 0:
            meta["status"] = "failed"
            meta["error"] = f"{stage_id} exited with {return_code}"
            break

    final_status = str(meta.get("status") or "")
    if final_status not in {"failed", "cancelled"}:
        final_status = "complete"
        meta["status"] = "complete"
    completed_at = _now_iso()
    meta["completed_at"] = completed_at
    meta["duration_seconds"] = round(time.time() - started, 2)
    meta["stage_results"] = stage_results
    after_snapshot = _pipeline_runtime_snapshot(
        include_model_runtime=include_model_runtime
    )
    meta["artifacts_after"] = after_snapshot
    meta["diffs"] = _pipeline_snapshot_diffs(before_snapshot, after_snapshot)
    _write_json_atomic(_pipeline_manifest_path(job_id), meta)
    _write_json_atomic(_pipeline_meta_path(job_id), meta)
    if final_status == "complete":
        message = "Dry-run plan complete." if request.dry_run else "Pipeline run complete."
    elif final_status == "cancelled":
        message = "Pipeline run cancelled."
    else:
        message = str(meta.get("error") or "Pipeline run failed.")
    _pipeline_append_log(job_id, "")
    _pipeline_append_log(job_id, f"completed_at={completed_at}")
    _pipeline_append_log(job_id, f"status={final_status}")
    _write_pipeline_status(
        status_payload,
        status=final_status,
        phase=final_status,
        current=len(stage_results),
        completed_at=completed_at,
        error=meta.get("error"),
        message=message,
        result_run_id=run_id if final_status == "complete" else None,
    )


def _validate_pipeline_request_for_start(request: PipelineRunRequest) -> PipelinePreflightResponse:
    _validate_pipeline_stages(request.stages)
    preflight = _pipeline_preflight_payload(request)
    if not request.dry_run and preflight.blockers:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Pipeline preflight failed.",
                "blockers": preflight.blockers,
            },
        )
    return preflight


def run_pipeline_sync(request: PipelineRunRequest, run_id: Optional[str] = None) -> PipelineJobStatus:
    _validate_pipeline_request_for_start(request)
    actual_run_id = run_id or _new_pipeline_run_id(request.tag)
    job_id = actual_run_id
    output_dir = _pipeline_output_dir(actual_run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    status_payload = _pipeline_status_payload(
        job_id=job_id,
        run_id=actual_run_id,
        status="queued",
        stages=request.stages,
        message="Pipeline job queued.",
    )
    _write_pipeline_status(status_payload)
    _run_pipeline_job(
        request=request,
        job_id=job_id,
        run_id=actual_run_id,
        cancel_event=threading.Event(),
        status_payload=status_payload,
    )
    return _read_pipeline_status_or_404(job_id)


def build_pipeline_preflight(request: PipelineRunRequest) -> PipelinePreflightResponse:
    return _pipeline_preflight_payload(request)


def _start_pipeline_job(request: PipelineRunRequest) -> PipelineStartResponse:
    _require_local_job_execution("Pipeline")
    _acquire_local_job_slot("pipeline")
    try:
        _validate_pipeline_request_for_start(request)
        run_id = _new_pipeline_run_id(request.tag)
        job_id = run_id
        output_dir = _pipeline_output_dir(run_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        cancel_event = threading.Event()
        status_payload = _pipeline_status_payload(
            job_id=job_id,
            run_id=run_id,
            status="queued",
            stages=request.stages,
            message="Pipeline job queued.",
        )
        _write_pipeline_status(status_payload)
    except Exception:
        LOCAL_JOB_SLOTS.release()
        raise

    def run_worker() -> None:
        try:
            _run_pipeline_job(
                request=request,
                job_id=job_id,
                run_id=run_id,
                cancel_event=cancel_event,
                status_payload=status_payload,
            )
        except Exception:
            logger.exception("Pipeline job %s failed", job_id)
            _pipeline_append_log(job_id, "ERROR: Pipeline job failed.")
            _write_pipeline_status(
                status_payload,
                status="failed",
                phase="failed",
                completed_at=_now_iso(),
                error="Pipeline job failed",
                message="Pipeline job failed.",
            )
        finally:
            with PIPELINE_JOB_LOCK:
                PIPELINE_CANCEL_EVENTS.pop(job_id, None)
                PIPELINE_PROCESSES.pop(job_id, None)
            LOCAL_JOB_SLOTS.release()

    with PIPELINE_JOB_LOCK:
        PIPELINE_CANCEL_EVENTS[job_id] = cancel_event
    thread = threading.Thread(target=run_worker, name=f"pipeline-{run_id}", daemon=True)
    try:
        thread.start()
    except Exception:
        with PIPELINE_JOB_LOCK:
            PIPELINE_CANCEL_EVENTS.pop(job_id, None)
        LOCAL_JOB_SLOTS.release()
        raise
    return PipelineStartResponse(
        job_id=job_id,
        run_id=run_id,
        status="queued",
        status_url=f"/pipeline/jobs/{job_id}",
    )


def _status_payload(
    *,
    job_id: str,
    run_id: str,
    run_type: str,
    status: str,
    current: int = 0,
    total: int = 0,
    phase: str = "queued",
    message: str = "",
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    error: Optional[str] = None,
    result_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    percent = round((current / total) * 100, 2) if total else 0.0
    return {
        "job_id": job_id,
        "run_id": run_id,
        "run_type": run_type,
        "status": status,
        "current": current,
        "total": total,
        "percent": percent,
        "phase": phase,
        "message": message,
        "started_at": started_at,
        "updated_at": _now_iso(),
        "completed_at": completed_at,
        "error": error,
        "output_dir": str(_job_output_dir(run_id)),
        "result_run_id": result_run_id,
    }


def _write_job_status(payload: Dict[str, Any], **updates: Any) -> EvaluationJobStatus:
    next_payload = {**payload, **updates}
    current = int(next_payload.get("current") or 0)
    total = int(next_payload.get("total") or 0)
    next_payload["current"] = current
    next_payload["total"] = total
    next_payload["percent"] = round((current / total) * 100, 2) if total else 0.0
    next_payload["updated_at"] = _now_iso()
    _write_json_atomic(_job_status_path(str(next_payload["job_id"])), next_payload)
    payload.clear()
    payload.update(next_payload)
    return EvaluationJobStatus(**next_payload)


def _read_job_status_or_404(job_id: str) -> EvaluationJobStatus:
    path = _job_status_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Unknown evaluation job: {job_id}")
    payload = _read_json_file(path)
    return EvaluationJobStatus(**payload)


def _select_benchmark_questions(
    question_ids: List[str],
    categories: List[str],
    quick: bool,
) -> List[Any]:
    by_id = {question.id: question for question in BENCHMARK_QUESTIONS}
    unknown_ids = [question_id for question_id in question_ids if question_id not in by_id]
    if unknown_ids:
        raise HTTPException(status_code=400, detail=f"Unknown question_id: {unknown_ids[0]}")

    unknown_categories = [category for category in categories if category not in QUESTION_CATEGORIES]
    if unknown_categories:
        raise HTTPException(status_code=400, detail=f"Unknown category: {unknown_categories[0]}")

    if question_ids:
        questions = [by_id[question_id] for question_id in question_ids]
    elif categories:
        allowed = set(categories)
        questions = [question for question in BENCHMARK_QUESTIONS if question.category in allowed]
    else:
        questions = list(BENCHMARK_QUESTIONS)

    if quick and not question_ids:
        selected: List[Any] = []
        seen_categories = set()
        for question in questions:
            if question.category not in seen_categories:
                selected.append(question)
                seen_categories.add(question.category)
        questions = selected

    if not questions:
        raise HTTPException(status_code=400, detail="Evaluation selection produced no questions")
    return questions


def _select_evaluation_modes(mode_names: List[str]) -> List[EvalMode]:
    by_name = {mode.name: mode for mode in EVAL_MODES}
    if not mode_names:
        return list(EVAL_MODES)
    unknown = [name for name in mode_names if name not in by_name]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown evaluation mode: {unknown[0]}")
    return [by_name[name] for name in mode_names]


def _select_system_variants(variant_names: List[str]) -> List[SystemVariant]:
    by_name = {variant.name: variant for variant in SYSTEM_VARIANTS}
    if not variant_names:
        return list(SYSTEM_VARIANTS)
    unknown = [name for name in variant_names if name not in by_name]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown ablation variant: {unknown[0]}")
    return [by_name[name] for name in variant_names]


def _job_backend_label() -> str:
    status = _database_status()
    return "postgresql" if status.get("available") else "local"


def _write_run_outputs(
    output_dir: Path,
    df: pd.DataFrame,
    meta: Dict[str, Any],
    *,
    write_report: bool,
) -> None:
    if not df.empty:
        df.to_csv(output_dir / "results.csv", index=False)
    _write_json_atomic(output_dir / "run_meta.json", meta)
    if write_report and not df.empty:
        from evaluation.report import generate_report

        report = generate_report(df, meta)
        (output_dir / "report.md").write_text(report, encoding="utf-8")


def _quality_context_docs(row: Dict[str, Any], top_k: int) -> List[Dict[str, Any]]:
    if int(row.get("n_retrieved") or 0) == 0 or str(row.get("mode") or "") == "LLM-only":
        return []
    try:
        docs = retrieve(str(row.get("question") or ""), k=top_k)
    except Exception:
        return []
    source_types = {
        source_type
        for source_type in str(row.get("retrieved_source_types") or "").split(",")
        if source_type
    }
    if source_types:
        docs = [doc for doc in docs if doc.get("source_type") in source_types]
    return docs


def _append_quality_metrics(
    df: pd.DataFrame,
    *,
    top_k: int,
    ollama_url: str,
    embedding_model: str,
    run_judge: bool,
    judge_model: str,
    cancel_event: threading.Event,
    status_payload: Dict[str, Any],
) -> pd.DataFrame:
    if df.empty:
        return df

    from evaluation.quality_metrics import score_single_response

    score_rows: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        if cancel_event.is_set():
            break

        row_payload = {column: _json_safe_value(row[column]) for column in df.columns}
        question_id = str(row_payload.get("question_id") or "")
        reference = get_reference(question_id)
        scores: Dict[str, Any] = {
            "rouge_l": 0.0,
            "semantic_similarity": 0.0,
            "faithfulness": 0.0,
            "answer_completeness": 0.0,
            "judge_correctness": 0,
            "judge_completeness": 0,
            "judge_citation_quality": 0,
            "judge_coherence": 0,
            "judge_mean": 0.0,
        }
        if reference and str(row_payload.get("response") or "").strip():
            quality = score_single_response(
                question_id=question_id,
                variant_name=str(row_payload.get("mode") or ""),
                question_text=str(row_payload.get("question") or ""),
                response=str(row_payload.get("response") or ""),
                context_docs=_quality_context_docs(row_payload, top_k),
                reference_text=reference.reference_text,
                key_facts=reference.key_facts,
                ollama_url=ollama_url,
                embedding_model=embedding_model,
                run_judge=run_judge,
                judge_model=judge_model,
            )
            scores.update(
                {
                    "rouge_l": quality.rouge_l,
                    "semantic_similarity": quality.semantic_similarity,
                    "faithfulness": quality.faithfulness,
                    "answer_completeness": quality.answer_completeness,
                    "judge_correctness": quality.judge_correctness,
                    "judge_completeness": quality.judge_completeness,
                    "judge_citation_quality": quality.judge_citation_quality,
                    "judge_coherence": quality.judge_coherence,
                    "judge_mean": quality.judge_mean,
                }
            )

        score_rows.append(scores)
        _write_job_status(
            status_payload,
            current=int(status_payload.get("current") or 0) + 1,
            phase="scoring_quality",
            message=f"Scored quality for {question_id} ({idx + 1}/{len(df)})",
        )

    if score_rows:
        quality_df = pd.DataFrame(score_rows)
        for column in quality_df.columns:
            df.loc[df.index[: len(quality_df)], column] = quality_df[column].values
    return df


def _run_standard_evaluation_job(
    *,
    request: EvaluationStandardRunRequest,
    job_id: str,
    run_id: str,
    output_dir: Path,
    cancel_event: threading.Event,
    status_payload: Dict[str, Any],
) -> None:
    model = request.model or config.CHAT_MODEL
    questions = _select_benchmark_questions(request.question_ids, request.categories, request.quick)
    modes = _select_evaluation_modes(request.modes)
    quality_requested = request.run_quality or request.run_judge
    eval_total = len(questions) * len(modes)
    total = eval_total + (eval_total if quality_requested else 0)
    started = time.time()
    timestamp = _now_iso()
    results: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {
        "run_id": run_id,
        "run_type": "standard",
        "status": "running",
        "timestamp": timestamp,
        "model": model,
        "tag": request.tag,
        "backend": _job_backend_label(),
        "top_k": request.top_k,
        "temperature": request.temperature,
        "num_ctx": request.num_ctx,
        "quick": request.quick,
        "question_ids": [question.id for question in questions],
        "categories": sorted({question.category for question in questions}),
        "modes": [mode.name for mode in modes],
        "n_questions": len(questions),
        "n_modes": len(modes),
        "n_evaluations": eval_total,
        "run_quality": quality_requested,
        "run_judge": request.run_judge,
        "embedding_model": request.embedding_model or config.EMBEDDING_MODEL,
        "judge_model": request.judge_model or model,
    }
    _write_json_atomic(output_dir / "run_meta.json", meta)
    _write_job_status(status_payload, status="running", phase="evaluating", total=total, started_at=timestamp)

    for question in questions:
        for mode in modes:
            if cancel_event.is_set():
                meta["status"] = "cancelled"
                meta["duration_seconds"] = round(time.time() - started, 2)
                _write_run_outputs(output_dir, pd.DataFrame(results), meta, write_report=False)
                _write_job_status(
                    status_payload,
                    status="cancelled",
                    phase="cancelled",
                    completed_at=_now_iso(),
                    result_run_id=run_id if results else None,
                    message="Evaluation cancelled before completion.",
                )
                return

            _write_job_status(
                status_payload,
                phase="evaluating",
                message=f"Running {question.id} / {mode.name}",
            )
            result = run_single_evaluation(
                question,
                mode,
                model=model,
                ollama_url=config.OLLAMA_BASE_URL,
                top_k=request.top_k,
                temperature=request.temperature,
                num_ctx=request.num_ctx,
            )
            results.append(asdict(result))
            df = pd.DataFrame(results)
            df.to_csv(output_dir / "results.csv", index=False)
            _write_job_status(
                status_payload,
                current=int(status_payload.get("current") or 0) + 1,
                message=f"Completed {question.id} / {mode.name}",
            )

    df = pd.DataFrame(results)
    if quality_requested and not cancel_event.is_set():
        df = _append_quality_metrics(
            df,
            top_k=request.top_k,
            ollama_url=config.OLLAMA_BASE_URL,
            embedding_model=request.embedding_model or config.EMBEDDING_MODEL,
            run_judge=request.run_judge,
            judge_model=request.judge_model or model,
            cancel_event=cancel_event,
            status_payload=status_payload,
        )

    if cancel_event.is_set():
        meta["status"] = "cancelled"
        meta["duration_seconds"] = round(time.time() - started, 2)
        _write_run_outputs(output_dir, df, meta, write_report=False)
        _write_job_status(
            status_payload,
            status="cancelled",
            phase="cancelled",
            completed_at=_now_iso(),
            result_run_id=run_id if not df.empty else None,
            message="Evaluation cancelled during quality scoring.",
        )
        return

    meta["status"] = "complete"
    meta["duration_seconds"] = round(time.time() - started, 2)
    _write_run_outputs(output_dir, df, meta, write_report=True)
    _write_job_status(
        status_payload,
        status="complete",
        phase="complete",
        current=total,
        completed_at=_now_iso(),
        result_run_id=run_id,
        message=f"Completed {len(df)} evaluation rows.",
    )


def _run_ablation_evaluation_job(
    *,
    request: EvaluationAblationRunRequest,
    job_id: str,
    run_id: str,
    output_dir: Path,
    cancel_event: threading.Event,
    status_payload: Dict[str, Any],
) -> None:
    model = request.model or config.CHAT_MODEL
    questions = _select_benchmark_questions(request.question_ids, request.categories, request.quick)
    variants = _select_system_variants(request.variants)
    quality_requested = request.run_quality or request.run_judge
    eval_total = len(questions) * len(variants) * request.repeats
    total = eval_total + (eval_total if quality_requested else 0)
    started = time.time()
    timestamp = _now_iso()
    results: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {
        "run_id": run_id,
        "run_type": "ablation",
        "status": "running",
        "timestamp": timestamp,
        "model": model,
        "tag": request.tag,
        "backend": _job_backend_label(),
        "top_k": request.top_k,
        "temperature": request.temperature,
        "num_ctx": request.num_ctx,
        "quick": request.quick,
        "repeats": request.repeats,
        "question_ids": [question.id for question in questions],
        "categories": sorted({question.category for question in questions}),
        "variants": [variant.name for variant in variants],
        "n_questions": len(questions),
        "n_modes": len(variants),
        "n_variants": len(variants),
        "n_evaluations": eval_total,
        "run_quality": quality_requested,
        "run_judge": request.run_judge,
        "embedding_model": request.embedding_model or config.EMBEDDING_MODEL,
        "judge_model": request.judge_model or model,
    }
    _write_json_atomic(output_dir / "run_meta.json", meta)
    _write_job_status(status_payload, status="running", phase="evaluating", total=total, started_at=timestamp)

    for repetition in range(1, request.repeats + 1):
        for question in questions:
            for variant in variants:
                if cancel_event.is_set():
                    meta["status"] = "cancelled"
                    meta["duration_seconds"] = round(time.time() - started, 2)
                    _write_run_outputs(output_dir, pd.DataFrame(results), meta, write_report=False)
                    _write_job_status(
                        status_payload,
                        status="cancelled",
                        phase="cancelled",
                        completed_at=_now_iso(),
                        result_run_id=run_id if results else None,
                        message="Ablation cancelled before completion.",
                    )
                    return

                _write_job_status(
                    status_payload,
                    phase="evaluating",
                    message=f"Running rep {repetition}/{request.repeats}: {question.id} / {variant.name}",
                )
                result = run_single_ablation(
                    question,
                    variant,
                    model=model,
                    ollama_url=config.OLLAMA_BASE_URL,
                    top_k=request.top_k,
                    temperature=request.temperature,
                    num_ctx=request.num_ctx,
                )
                row = asdict(result)
                row["repetition"] = repetition
                results.append(row)
                df = pd.DataFrame(results)
                df.to_csv(output_dir / "results.csv", index=False)
                _write_job_status(
                    status_payload,
                    current=int(status_payload.get("current") or 0) + 1,
                    message=f"Completed rep {repetition}/{request.repeats}: {question.id} / {variant.name}",
                )

    df = pd.DataFrame(results)
    if quality_requested and not cancel_event.is_set():
        df = _append_quality_metrics(
            df,
            top_k=request.top_k,
            ollama_url=config.OLLAMA_BASE_URL,
            embedding_model=request.embedding_model or config.EMBEDDING_MODEL,
            run_judge=request.run_judge,
            judge_model=request.judge_model or model,
            cancel_event=cancel_event,
            status_payload=status_payload,
        )

    if cancel_event.is_set():
        meta["status"] = "cancelled"
        meta["duration_seconds"] = round(time.time() - started, 2)
        _write_run_outputs(output_dir, df, meta, write_report=False)
        _write_job_status(
            status_payload,
            status="cancelled",
            phase="cancelled",
            completed_at=_now_iso(),
            result_run_id=run_id if not df.empty else None,
            message="Ablation cancelled during quality scoring.",
        )
        return

    meta["status"] = "complete"
    meta["duration_seconds"] = round(time.time() - started, 2)
    _write_run_outputs(output_dir, df, meta, write_report=True)
    _write_job_status(
        status_payload,
        status="complete",
        phase="complete",
        current=total,
        completed_at=_now_iso(),
        result_run_id=run_id,
        message=f"Completed {len(df)} ablation rows.",
    )


def _start_evaluation_job(
    run_type: str,
    request: EvaluationStandardRunRequest | EvaluationAblationRunRequest,
) -> EvaluationStartResponse:
    _require_local_job_execution("Evaluation")
    _acquire_local_job_slot("evaluation")
    try:
        model = _allowed_model(
            request.model,
            default=config.CHAT_MODEL,
            allowed=config.ALLOWED_CHAT_MODELS,
            label="chat model",
        )
        if request.judge_model:
            _allowed_model(
                request.judge_model,
                default=model,
                allowed=config.ALLOWED_CHAT_MODELS,
                label="judge model",
            )
        if request.embedding_model:
            _allowed_model(
                request.embedding_model,
                default=config.EMBEDDING_MODEL,
                allowed=config.ALLOWED_EMBEDDING_MODELS,
                label="embedding model",
            )
        if run_type == "standard":
            _select_benchmark_questions(request.question_ids, request.categories, request.quick)
            _select_evaluation_modes(request.modes)  # type: ignore[union-attr]
        else:
            _select_benchmark_questions(request.question_ids, request.categories, request.quick)
            _select_system_variants(request.variants)  # type: ignore[union-attr]

        run_id = _new_evaluation_run_id(run_type, model, request.tag)
        job_id = run_id
        output_dir = _job_output_dir(run_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        cancel_event = threading.Event()
        status_payload = _status_payload(
            job_id=job_id,
            run_id=run_id,
            run_type=run_type,
            status="queued",
            phase="queued",
            message="Evaluation job queued.",
        )
        _write_job_status(status_payload)
    except Exception:
        LOCAL_JOB_SLOTS.release()
        raise

    target = _run_standard_evaluation_job if run_type == "standard" else _run_ablation_evaluation_job

    def run_worker() -> None:
        try:
            target(
                request=request,  # type: ignore[arg-type]
                job_id=job_id,
                run_id=run_id,
                output_dir=output_dir,
                cancel_event=cancel_event,
                status_payload=status_payload,
            )
        except Exception:
            logger.exception("Evaluation job %s failed", job_id)
            _write_job_status(
                status_payload,
                status="failed",
                phase="failed",
                completed_at=_now_iso(),
                error="Evaluation job failed",
                message="Evaluation job failed.",
            )
        finally:
            with EVALUATION_JOB_LOCK:
                EVALUATION_CANCEL_EVENTS.pop(job_id, None)
            LOCAL_JOB_SLOTS.release()

    with EVALUATION_JOB_LOCK:
        EVALUATION_CANCEL_EVENTS[job_id] = cancel_event
    thread = threading.Thread(target=run_worker, name=f"evaluation-{run_id}", daemon=True)
    try:
        thread.start()
    except Exception:
        with EVALUATION_JOB_LOCK:
            EVALUATION_CANCEL_EVENTS.pop(job_id, None)
        LOCAL_JOB_SLOTS.release()
        raise
    return EvaluationStartResponse(
        job_id=job_id,
        run_id=run_id,
        status="queued",
        status_url=f"/evaluation/jobs/{job_id}",
    )


def _evaluation_meta_path(record: Dict[str, Any]) -> Optional[Path]:
    csv_path: Path = record["csv_path"]
    root_path: Path = record["root_path"]
    candidates = [
        root_path / "ablation_meta.json",
        root_path / "run_meta.json",
        root_path / f"{csv_path.stem}_meta.json",
        csv_path.with_name(f"{csv_path.stem}_meta.json"),
        csv_path.with_suffix(".json"),
    ]
    return next((path for path in candidates if path.exists()), None)


def _evaluation_report_path(record: Dict[str, Any]) -> Optional[Path]:
    csv_path: Path = record["csv_path"]
    root_path: Path = record["root_path"]
    candidates = [
        root_path / "report.md",
        root_path / "ablation_report.md",
        root_path / f"{csv_path.stem}_report.md",
        csv_path.with_name(f"{csv_path.stem}_report.md"),
    ]
    report_path = next((path for path in candidates if path.exists()), None)
    if report_path:
        return report_path
    reports = sorted(root_path.glob("*report*.md"))
    return reports[0] if reports else None


def _evaluation_run_type(run_id: str, meta: Dict[str, Any], df: pd.DataFrame) -> str:
    if "variants" in meta or "ablation" in run_id.lower():
        return "ablation"
    modes = set(df["mode"].dropna().astype(str).tolist()) if "mode" in df else set()
    variant_names = {variant.name for variant in SYSTEM_VARIANTS}
    if modes & variant_names:
        return "ablation"
    return "standard"


def _evaluation_results_frame(record: Dict[str, Any]) -> pd.DataFrame:
    df = pd.read_csv(record["csv_path"])
    if "error" in df.columns:
        df["error"] = df["error"].fillna("").astype(str)
        df.loc[df["error"].str.lower() == "nan", "error"] = ""
    return df


def _evaluation_summary_from_frame(df: pd.DataFrame) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    metric_cols = [metric["key"] for metric in EVALUATION_METRICS if metric["key"] in df.columns]
    if {"mode", "category"}.issubset(df.columns) and metric_cols:
        try:
            summaries = compute_summary_metrics(df)
            payload["by_mode"] = _records(summaries["by_mode"].reset_index())
            payload["by_category"] = _records(summaries["by_category"].reset_index())
            payload["by_mode_category"] = _records(summaries["by_mode_category"].reset_index())
        except Exception:
            logger.exception("Evaluation summary computation failed")
            payload["error"] = "Evaluation summary is unavailable"

    quality_cols = [metric["key"] for metric in EVALUATION_QUALITY_METRICS if metric["key"] in df.columns]
    if quality_cols and "mode" in df.columns:
        quality = df.groupby("mode")[quality_cols].mean(numeric_only=True).round(4)
        payload["quality_by_mode"] = _records(quality.reset_index())

    return payload


def _safe_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _evaluation_metric_catalog(df: pd.DataFrame) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for group, definitions in (
        ("core", EVALUATION_METRICS),
        ("quality", EVALUATION_QUALITY_METRICS),
    ):
        for metric in definitions:
            key = metric["key"]
            if key in df.columns:
                rows.append({**metric, "group": group})
    return rows


def _evaluation_metric_columns(df: pd.DataFrame) -> List[str]:
    columns: List[str] = []
    for metric in _evaluation_metric_catalog(df):
        key = str(metric["key"])
        numeric = pd.to_numeric(df[key], errors="coerce")
        if numeric.notna().any():
            columns.append(key)
    return columns


def _evaluation_group_summary(
    df: pd.DataFrame,
    group_cols: List[str],
    metric_cols: List[str],
) -> List[Dict[str, Any]]:
    if not set(group_cols).issubset(df.columns) or not metric_cols:
        return []

    working = df.copy()
    for metric in metric_cols:
        working[metric] = pd.to_numeric(working[metric], errors="coerce")

    grouped = working.groupby(group_cols, dropna=False)
    payload = grouped[metric_cols].mean(numeric_only=True).round(4).reset_index()
    payload = payload.merge(grouped.size().rename("n_evaluations").reset_index(), on=group_cols)

    if "question_id" in working.columns:
        question_counts = grouped["question_id"].nunique().rename("n_questions").reset_index()
        payload = payload.merge(question_counts, on=group_cols)

    if "error" in working.columns:
        error_counts = (
            grouped["error"]
            .apply(lambda values: int((values.fillna("").astype(str).str.strip() != "").sum()))
            .rename("n_errors")
            .reset_index()
        )
        payload = payload.merge(error_counts, on=group_cols)

    ordered = group_cols + ["n_evaluations", "n_questions", "n_errors"] + metric_cols
    payload = payload[[column for column in ordered if column in payload.columns]]
    return _records(payload)


def _choose_baseline_mode(rows: List[Dict[str, Any]], requested: Optional[str]) -> Optional[str]:
    modes = [str(row.get("mode")) for row in rows if row.get("mode") is not None]
    if requested and requested in modes:
        return requested
    for candidate in ("Full framework", "Full", "+Reliability", "Multi-source RAG"):
        if candidate in modes:
            return candidate
    return modes[-1] if modes else None


def _attach_baseline_deltas(
    rows: List[Dict[str, Any]],
    metric: str,
    baseline_mode: Optional[str],
) -> Optional[str]:
    chosen = _choose_baseline_mode(rows, baseline_mode)
    if not chosen:
        return None
    baseline_row = next((row for row in rows if row.get("mode") == chosen), None)
    baseline_value = _safe_float(baseline_row.get(metric) if baseline_row else None)
    if baseline_value is None:
        return chosen

    for row in rows:
        value = _safe_float(row.get(metric))
        row["baseline_mode"] = chosen
        if value is None:
            row["delta_from_baseline"] = None
            row["relative_delta_pct"] = None
            continue
        delta = value - baseline_value
        row["delta_from_baseline"] = round(delta, 4)
        row["relative_delta_pct"] = round((delta / abs(baseline_value)) * 100, 2) if baseline_value else None
    return chosen


def _project_rows(rows: List[Dict[str, Any]], columns: List[str]) -> List[Dict[str, Any]]:
    return [
        {column: row.get(column) for column in columns if column in row}
        for row in rows
    ]


def _evaluation_mode_category_matrix(df: pd.DataFrame, metric: str) -> Dict[str, Any]:
    if not {"mode", "category", metric}.issubset(df.columns):
        return {"metric": metric, "modes": [], "categories": [], "rows": [], "cells": []}

    working = df[["mode", "category", metric]].copy()
    working[metric] = pd.to_numeric(working[metric], errors="coerce")
    pivot = working.pivot_table(index="mode", columns="category", values=metric, aggfunc="mean").round(4)
    pivot = pivot.sort_index().sort_index(axis=1)
    rows = _records(pivot.reset_index())
    cells: List[Dict[str, Any]] = []
    for mode, row in pivot.iterrows():
        for category, value in row.items():
            cells.append(
                {
                    "mode": str(mode),
                    "category": str(category),
                    "value": _json_safe_value(value),
                }
            )
    values = pd.to_numeric(pivot.stack(), errors="coerce")
    return {
        "metric": metric,
        "modes": [str(item) for item in pivot.index.tolist()],
        "categories": [str(item) for item in pivot.columns.tolist()],
        "rows": rows,
        "cells": cells,
        "min": _json_safe_value(values.min(skipna=True)) if values.notna().any() else None,
        "max": _json_safe_value(values.max(skipna=True)) if values.notna().any() else None,
    }


def _evaluation_metric_distributions(df: pd.DataFrame, metric: str) -> List[Dict[str, Any]]:
    if not {"mode", metric}.issubset(df.columns):
        return []
    working = df[["mode", metric]].copy()
    working[metric] = pd.to_numeric(working[metric], errors="coerce")
    rows: List[Dict[str, Any]] = []
    for mode, group in working.groupby("mode", dropna=False):
        values = group[metric].dropna()
        if values.empty:
            continue
        rows.append(
            {
                "mode": _json_safe_value(mode),
                "n": int(values.count()),
                "min": _json_safe_value(values.min()),
                "q1": _json_safe_value(values.quantile(0.25)),
                "median": _json_safe_value(values.quantile(0.5)),
                "q3": _json_safe_value(values.quantile(0.75)),
                "max": _json_safe_value(values.max()),
                "mean": _json_safe_value(values.mean()),
            }
        )
    return rows


def _evaluation_extreme_questions(
    df: pd.DataFrame,
    metric: str,
    *,
    ascending: bool,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    if metric not in df.columns:
        return []
    working = df.copy()
    working[metric] = pd.to_numeric(working[metric], errors="coerce")
    working = working[working[metric].notna()].sort_values(metric, ascending=ascending).head(limit)
    if "response" in working.columns:
        working["response_excerpt"] = working["response"].fillna("").astype(str).str.slice(0, 240)
    columns = [
        "question_id",
        "category",
        "mode",
        "question",
        metric,
        "retrieval_precision",
        "source_coverage",
        "citation_accuracy",
        "context_utilization",
        "latency_seconds",
        "error",
        "response_excerpt",
    ]
    selected_columns: List[str] = []
    for column in columns:
        if column in working.columns and column not in selected_columns:
            selected_columns.append(column)
    return _records(working[selected_columns])


def _evaluation_best_by_metric(by_mode: List[Dict[str, Any]], metric_cols: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for metric in metric_cols:
        candidates = [
            (row, _safe_float(row.get(metric)))
            for row in by_mode
            if row.get("mode") is not None
        ]
        candidates = [(row, value) for row, value in candidates if value is not None]
        if not candidates:
            continue
        lower_is_better = metric == "latency_seconds"
        best_row, best_value = min(candidates, key=lambda item: item[1]) if lower_is_better else max(candidates, key=lambda item: item[1])
        rows.append(
            {
                "metric": metric,
                "direction": "lower" if lower_is_better else "higher",
                "best_mode": best_row.get("mode"),
                "value": _json_safe_value(best_value),
            }
        )
    return rows


def _statistical_matrix_payload(metric: str, matrix: pd.DataFrame) -> Dict[str, Any]:
    matrix = matrix.copy()
    matrix.index = matrix.index.astype(str)
    matrix.columns = matrix.columns.astype(str)
    rows = _records(matrix.reset_index().rename(columns={"index": "mode"}))
    values = pd.to_numeric(matrix.stack(), errors="coerce")
    return {
        "metric": metric,
        "modes": [str(item) for item in matrix.index.tolist()],
        "rows": rows,
        "min": _json_safe_value(values.min(skipna=True)) if values.notna().any() else None,
        "max": _json_safe_value(values.max(skipna=True)) if values.notna().any() else None,
    }


def _evaluation_statistics_payload(df: pd.DataFrame, metric_cols: List[str]) -> Dict[str, Any]:
    if not {"mode", "question_id"}.issubset(df.columns):
        return {
            "status": "skipped",
            "reason": "Statistical tests require mode and question_id columns.",
        }

    usable_metrics = [metric for metric in metric_cols if metric in df.columns]
    if not usable_metrics:
        return {"status": "skipped", "reason": "No numeric evaluation metrics are available."}

    working = df[["mode", "question_id", *usable_metrics]].copy()
    working = working.dropna(subset=["mode", "question_id"])
    for metric in usable_metrics:
        working[metric] = pd.to_numeric(working[metric], errors="coerce")
    working = working.groupby(["mode", "question_id"], as_index=False)[usable_metrics].mean(numeric_only=True)

    mode_count = int(working["mode"].nunique()) if "mode" in working.columns else 0
    question_count = int(working["question_id"].nunique()) if "question_id" in working.columns else 0
    if mode_count < 2 or question_count < 3:
        return {
            "status": "skipped",
            "reason": "Statistical tests require at least two modes and three paired questions.",
            "n_modes": mode_count,
            "n_questions": question_count,
        }

    try:
        from evaluation.statistical_analysis import pairwise_to_dataframe, run_full_statistical_analysis

        report = run_full_statistical_analysis(working, metrics=usable_metrics)
        pairwise_df = pairwise_to_dataframe(report.pairwise_tests)
        matrices = {
            metric: _statistical_matrix_payload(metric, matrix)
            for metric, matrix in report.significance_matrix.items()
        }
        return {
            "status": "available",
            "summary": {key: _json_safe_value(value) for key, value in report.summary.items()},
            "friedman": [{key: _json_safe_value(value) for key, value in asdict(result).items()} for result in report.friedman_tests],
            "pairwise": _records(pairwise_df) if not pairwise_df.empty else [],
            "significant_pairwise": _records(pairwise_df[pairwise_df["significant"]]) if "significant" in pairwise_df else [],
            "significance_matrix": matrices,
        }
    except Exception:
        logger.exception("Statistical analysis failed")
        return {
            "status": "skipped",
            "reason": "Statistical analysis is unavailable",
            "n_modes": mode_count,
            "n_questions": question_count,
        }


def _evaluation_analytics_payload(
    record: Dict[str, Any],
    *,
    metric: Optional[str],
    baseline_mode: Optional[str],
    category: Optional[str],
) -> EvaluationAnalyticsResponse:
    run = _evaluation_run_summary(record)
    source_df = _evaluation_results_frame(record)
    df = source_df.copy()
    if category and "category" in df.columns:
        df = df[df["category"].astype(str) == category]

    metric_catalog = _evaluation_metric_catalog(source_df)
    metric_cols = _evaluation_metric_columns(df)
    if not metric_cols:
        raise HTTPException(status_code=400, detail="Evaluation run has no numeric metrics to analyze.")
    selected_metric = metric or metric_cols[0]
    if selected_metric not in metric_cols:
        raise HTTPException(status_code=400, detail=f"Unknown or unavailable evaluation metric: {selected_metric}")

    by_mode = _evaluation_group_summary(df, ["mode"], metric_cols)
    selected_baseline = _attach_baseline_deltas(by_mode, selected_metric, baseline_mode)
    by_category = _evaluation_group_summary(df, ["category"], metric_cols)
    by_mode_category = _evaluation_group_summary(df, ["mode", "category"], metric_cols)
    quality_cols = [metric_def["key"] for metric_def in EVALUATION_QUALITY_METRICS if metric_def["key"] in metric_cols]

    return EvaluationAnalyticsResponse(
        run=run,
        selected_metric=selected_metric,
        baseline_mode=selected_baseline,
        filters={"category": category},
        metric_catalog=metric_catalog,
        by_mode=by_mode,
        by_category=by_category,
        by_mode_category=by_mode_category,
        mode_category_matrix=_evaluation_mode_category_matrix(df, selected_metric),
        metric_distributions=_evaluation_metric_distributions(df, selected_metric),
        quality_by_mode=_evaluation_group_summary(df, ["mode"], quality_cols) if quality_cols else [],
        latency_by_mode=_project_rows(by_mode, ["mode", "n_evaluations", "latency_seconds", "delta_from_baseline"]),
        citation_by_mode=_project_rows(by_mode, ["mode", "citation_count", "citation_accuracy", "context_utilization"]),
        source_coverage_by_mode=_project_rows(by_mode, ["mode", "retrieval_precision", "source_coverage", "n_evaluations"]),
        lowest_scoring_questions=_evaluation_extreme_questions(df, selected_metric, ascending=True),
        highest_latency_questions=_evaluation_extreme_questions(df, "latency_seconds", ascending=False) if "latency_seconds" in metric_cols else [],
        best_by_metric=_evaluation_best_by_metric(by_mode, metric_cols),
        statistical_tests=_evaluation_statistics_payload(df, metric_cols),
    )


def _evaluation_run_summary(record: Dict[str, Any]) -> EvaluationRunSummary:
    csv_path: Path = record["csv_path"]
    root_path: Path = record["root_path"]
    meta_path = _evaluation_meta_path(record)
    report_path = _evaluation_report_path(record)
    meta = _read_json_file(meta_path)
    try:
        df = _evaluation_results_frame(record)
    except Exception:
        logger.exception("Evaluation run %s could not be read", record["run_id"])
        return EvaluationRunSummary(
            run_id=record["run_id"],
            run_type="unreadable",
            path=str(root_path),
            csv_path=str(csv_path),
            meta_path=str(meta_path) if meta_path else None,
            report_path=str(report_path) if report_path else None,
            status="error",
            metrics={"error": "Evaluation results are unreadable"},
        )

    metrics: Dict[str, Any] = {}
    for metric in [*EVALUATION_METRICS, *EVALUATION_QUALITY_METRICS]:
        key = metric["key"]
        if key in df.columns:
            numeric = pd.to_numeric(df[key], errors="coerce")
            if numeric.notna().any():
                metrics[key] = _json_safe_value(numeric.mean(skipna=True))

    modes = sorted(df["mode"].dropna().astype(str).unique().tolist()) if "mode" in df else []
    categories = sorted(df["category"].dropna().astype(str).unique().tolist()) if "category" in df else []
    question_count = int(df["question_id"].nunique()) if "question_id" in df else int(meta.get("n_questions") or 0)
    errors = int((df["error"] != "").sum()) if "error" in df else int(meta.get("n_errors") or 0)
    timestamp = meta.get("timestamp")
    if not timestamp:
        timestamp = datetime.fromtimestamp(csv_path.stat().st_mtime).astimezone().isoformat(timespec="seconds")

    meta_status = str(meta.get("status") or "")
    if meta_status in {"queued", "running", "cancel_requested", "cancelled", "failed", "complete"}:
        run_status = meta_status
    else:
        run_status = "complete" if errors == 0 else "complete_with_errors"

    return EvaluationRunSummary(
        run_id=record["run_id"],
        run_type=_evaluation_run_type(record["run_id"], meta, df),
        path=str(root_path),
        csv_path=str(csv_path),
        meta_path=str(meta_path) if meta_path else None,
        report_path=str(report_path) if report_path else None,
        model=meta.get("model"),
        tag=meta.get("tag"),
        timestamp=str(timestamp) if timestamp else None,
        status=run_status,
        n_evaluations=len(df),
        n_questions=question_count,
        n_modes=len(modes) or int(meta.get("n_modes") or meta.get("n_variants") or 0),
        n_errors=errors,
        modes=modes,
        categories=categories,
        has_quality_metrics=any(metric["key"] in df.columns for metric in EVALUATION_QUALITY_METRICS),
        has_report=bool(report_path),
        metrics=metrics,
    )


def _evaluation_run_registry() -> Dict[str, Dict[str, Any]]:
    return {record["run_id"]: record for record in _evaluation_csv_candidates()}


def _evaluation_record_or_404(run_id: str) -> Dict[str, Any]:
    registry = _evaluation_run_registry()
    try:
        return registry[run_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown evaluation run: {run_id}") from exc


def _date_columns(df: pd.DataFrame, cfg: Dict[str, Any]) -> List[str]:
    configured = [column for column in cfg.get("date_columns", []) if column in df.columns]
    inferred = [
        column
        for column in df.columns
        if pd.api.types.is_datetime64_any_dtype(df[column]) and column not in configured
    ]
    return configured + inferred


def _numeric_columns(df: pd.DataFrame) -> List[str]:
    return [
        column
        for column in df.columns
        if pd.api.types.is_numeric_dtype(df[column]) and not pd.api.types.is_bool_dtype(df[column])
    ]


def _filter_explore_df(
    df: pd.DataFrame,
    cfg: Dict[str, Any],
    *,
    bay: Optional[str],
    station: Optional[str],
    source: Optional[str],
    time_from: Optional[str],
    time_to: Optional[str],
    search: Optional[str],
) -> pd.DataFrame:
    filtered = df.copy()

    bay_column = cfg.get("bay_column")
    if bay and bay_column and bay_column in filtered.columns:
        filtered = filtered[filtered[bay_column].astype("string") == bay]

    station_column = cfg.get("station_column")
    if station and station_column and station_column in filtered.columns:
        filtered = filtered[filtered[station_column].astype("string") == station]

    source_column = cfg.get("source_column")
    if source and source_column and source_column in filtered.columns:
        filtered = filtered[filtered[source_column].astype("string") == source]

    date_column = next((column for column in cfg.get("date_columns", []) if column in filtered.columns), None)
    if date_column and (time_from or time_to):
        dates = pd.to_datetime(filtered[date_column].astype("string"), errors="coerce")
        if time_from:
            filtered = filtered[dates >= pd.to_datetime(time_from)]
            dates = pd.to_datetime(filtered[date_column].astype("string"), errors="coerce")
        if time_to:
            filtered = filtered[dates <= pd.to_datetime(time_to)]

    if search:
        needle = search.lower()
        text_columns = [
            column
            for column in filtered.columns
            if pd.api.types.is_object_dtype(filtered[column])
            or pd.api.types.is_string_dtype(filtered[column])
            or pd.api.types.is_bool_dtype(filtered[column])
        ]
        if text_columns:
            mask = pd.Series(False, index=filtered.index)
            for column in text_columns:
                mask = mask | filtered[column].astype("string").str.lower().str.contains(
                    needle,
                    na=False,
                    regex=False,
                )
            filtered = filtered[mask]

    return filtered


def _profile_column(name: str, series: pd.Series) -> ColumnProfile:
    non_null = int(series.notna().sum())
    missing = int(series.isna().sum())
    unique = int(series.nunique(dropna=True))
    min_value: Any = None
    max_value: Any = None
    mean_value: Optional[float] = None

    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        min_value = _json_safe_value(series.min(skipna=True))
        max_value = _json_safe_value(series.max(skipna=True))
        mean = series.mean(skipna=True)
        mean_value = None if pd.isna(mean) else float(mean)
    elif pd.api.types.is_datetime64_any_dtype(series):
        min_value = _json_safe_value(series.min())
        max_value = _json_safe_value(series.max())

    return ColumnProfile(
        name=name,
        dtype=str(series.dtype),
        non_null=non_null,
        missing=missing,
        unique=unique,
        min_value=min_value,
        max_value=max_value,
        mean_value=mean_value,
    )


def _selected_columns(df: pd.DataFrame, cfg: Dict[str, Any], columns: Optional[str]) -> List[str]:
    if columns:
        requested = [column.strip() for column in columns.split(",") if column.strip()]
    else:
        requested = cfg.get("default_columns", [])
    selected = [column for column in requested if column in df.columns]
    return selected or list(df.columns[:12])


def _database_status() -> Dict[str, Any]:
    try:
        engine = create_engine(
            config.DATABASE_URL,
            **config.database_engine_options(),
        )
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            n_docs = conn.execute(text("SELECT count(*) FROM retrieval_document WHERE active IS TRUE")).scalar()
        return {"available": True, "documents": int(n_docs or 0), "version": version}
    except Exception as exc:
        logger.warning("Database status check failed: %s", type(exc).__name__)
        logger.debug("Database status check traceback", exc_info=True)
        return {"available": False, "error": "Database is unavailable"}


def _ollama_status() -> Dict[str, Any]:
    try:
        runtime = get_model_runtime()
        models = [
            model.get("name")
            for model in runtime.list_models(timeout=2)
            if model.get("name")
        ]
        return {
            "available": True,
            "provider": runtime.provider,
            "base_url": runtime.endpoint,
            "models": models,
        }
    except Exception as exc:
        logger.warning("Model runtime status check failed: %s", type(exc).__name__)
        logger.debug("Model runtime status check traceback", exc_info=True)
        return {
            "available": False,
            "provider": config.MODEL_PROVIDER,
            "base_url": (
                config.OLLAMA_BASE_URL
                if config.MODEL_PROVIDER == "ollama"
                else f"vertex://{config.GOOGLE_CLOUD_PROJECT}/{config.GOOGLE_CLOUD_LOCATION}"
            ),
            "error": "Model runtime is unavailable",
        }


def _is_embedding_only_model(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in EMBEDDING_ONLY_MODEL_HINTS)


def _allowed_model(
    requested: Optional[str],
    *,
    default: str,
    allowed: frozenset[str],
    label: str,
) -> str:
    model = (requested or default).strip()
    if model not in allowed:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "model_not_allowed",
                "message": f"The requested {label} is not configured for this deployment.",
            },
        )
    return model


def _ollama_options(request: ChatRequest) -> Dict[str, Any]:
    options: Dict[str, Any] = {
        "temperature": request.temperature,
        "top_p": request.top_p,
        "repeat_penalty": request.repeat_penalty,
        "num_ctx": request.num_ctx,
    }
    if request.num_predict is not None:
        options["num_predict"] = request.num_predict
    if request.sampling_top_k is not None:
        options["top_k"] = request.sampling_top_k
    if request.seed is not None:
        options["seed"] = request.seed
    return options


def _artifact_status() -> Dict[str, Any]:
    docs_path = config.SERVING_DIR / "retrieval_documents.jsonl"
    try:
        edna_docs_path = edna_retrieval_path("jsonl")
        edna_count = _count_jsonl(edna_docs_path)
        edna_exists = edna_docs_path.exists()
        publication = 'ready' if edna_exists else 'not_materialized'
    except (ValueError, OSError, KeyError, SnapshotError):
        edna_count, edna_exists, publication = None, False, 'unavailable'
    return {
        "retrieval_documents_jsonl": docs_path.exists(),
        "edna_retrieval_documents_jsonl": edna_exists,
        "edna_publication": publication,
        "retrieval_documents": (
            _count_jsonl(docs_path) + (edna_count or 0)
        ),
        "edna_retrieval_documents": edna_count,
        "analysis_documents": _count_jsonl(config.ANALYSIS_DIR / "analysis_documents.jsonl"),
        "reliability_documents": _count_jsonl(config.RELIABILITY_DIR / "reliability_documents.jsonl"),
        "embeddings_cache": (config.SERVING_DIR / "retrieval_embeddings.npy").exists(),
    }


def _filter_documents(
    documents: Iterable[Dict[str, Any]],
    *,
    source_type: Optional[str],
    bay: Optional[str],
    time_from: Optional[str],
    time_to: Optional[str],
) -> List[Dict[str, Any]]:
    rows = []
    for doc in documents:
        if source_type and doc.get("source_type") != source_type:
            continue
        if bay and doc.get("bay") != bay:
            continue
        doc_time = _time(doc) or ""
        if not matches_time(doc_time, time_from, time_to):
            continue
        rows.append(doc)
    return rows


@app.get("/health/live")
def health_live() -> Dict[str, str]:
    """Unauthenticated process liveness without dependency details."""
    return {"status": "ok"}


@app.get("/health", response_model=StatusResponse)
def health() -> StatusResponse:
    database = _database_status()
    ollama = _ollama_status()
    artifacts = _artifact_status()
    state = "ok" if artifacts["retrieval_documents"] and artifacts['edna_publication'] != 'unavailable' else "degraded"
    return StatusResponse(status=state, database=database, ollama=ollama, artifacts=artifacts)


@app.get("/stats", response_model=CorpusStats)
def stats() -> CorpusStats:
    docs = _read_jsonl(config.SERVING_DIR / "retrieval_documents.jsonl")
    docs.extend(
        _read_jsonl(
            edna_retrieval_path("jsonl")
        )
    )
    counts: Dict[str, int] = {}
    for doc in docs:
        source_type = str(doc.get("source_type") or "unknown")
        counts[source_type] = counts.get(source_type, 0) + 1

    return CorpusStats(
        documents=counts,
        samples=_parquet_rows(config.SERVING_DIR / "sample_registry.parquet"),
        ctd_casts=_parquet_rows(config.NORMALIZED_DIR / "ctd_summary.parquet"),
        sst_days=_parquet_rows(config.NORMALIZED_DIR / "sst_daily_summary.parquet"),
        analysis_docs=_count_jsonl(config.ANALYSIS_DIR / "analysis_documents.jsonl"),
        reliability_docs=_count_jsonl(config.RELIABILITY_DIR / "reliability_documents.jsonl"),
        provenance_records=_count_jsonl(config.PROVENANCE_DIR / "provenance.jsonl"),
    )


@app.get("/models", response_model=ModelsResponse)
def models() -> ModelsResponse:
    try:
        runtime = get_model_runtime()
        raw_models = runtime.list_models(timeout=3)
        chat_models = [
            OllamaModel(
                name=str(model.get("name") or ""),
                modified_at=model.get("modified_at"),
                size=model.get("size"),
            )
            for model in raw_models
            if (
                model.get("name")
                and str(model.get("name")) in config.ALLOWED_CHAT_MODELS
                and not _is_embedding_only_model(str(model.get("name")))
            )
        ]
        return ModelsResponse(
            default_model=config.CHAT_MODEL,
            embedding_model=config.EMBEDDING_MODEL,
            provider=runtime.provider,
            ollama_base_url=runtime.endpoint,
            available=True,
            models=chat_models,
        )
    except Exception as exc:
        logger.warning("Model discovery unavailable: %s", exc)
        return ModelsResponse(
            default_model=config.CHAT_MODEL,
            embedding_model=config.EMBEDDING_MODEL,
            provider=config.MODEL_PROVIDER,
            ollama_base_url=config.OLLAMA_BASE_URL,
            available=False,
            error="Model discovery is unavailable",
        )


@app.get("/pipeline/status", response_model=PipelineStatusResponse)
def pipeline_status() -> PipelineStatusResponse:
    raw_sources = _pipeline_raw_sources()
    artifacts = _pipeline_artifacts()
    active_jobs = _pipeline_job_statuses(limit=25, active_only=True)
    return PipelineStatusResponse(
        stages=_pipeline_stage_infos(),
        raw_sources=raw_sources,
        artifacts=artifacts,
        artifact_freshness=_pipeline_artifact_freshness(raw_sources, artifacts),
        readiness=_pipeline_readiness(raw_sources, artifacts),
        database=_pipeline_database_snapshot(),
        ollama=_ollama_status(),
        active_jobs=[_model_dump(job) for job in active_jobs],
        pipeline_runs=len(_pipeline_run_summaries(limit=10000)),
    )


@app.post("/pipeline/preflight", response_model=PipelinePreflightResponse)
def pipeline_preflight(request: PipelineRunRequest) -> PipelinePreflightResponse:
    return _pipeline_preflight_payload(request)


@app.post("/pipeline/jobs", response_model=PipelineStartResponse)
def pipeline_start_job(request: PipelineRunRequest) -> PipelineStartResponse:
    return _start_pipeline_job(request)


@app.get("/pipeline/runs", response_model=PipelineRunsResponse)
def pipeline_runs(limit: int = Query(default=50, ge=1, le=250)) -> PipelineRunsResponse:
    return PipelineRunsResponse(runs=_pipeline_run_summaries(limit=limit))


@app.get("/pipeline/runs/{run_id}", response_model=PipelineRunDetailResponse)
def pipeline_run_detail(
    run_id: str,
    limit_bytes: int = Query(default=50000, ge=1000, le=200000),
) -> PipelineRunDetailResponse:
    return _pipeline_run_detail_or_404(run_id, limit_bytes)


@app.get("/pipeline/jobs/{job_id}", response_model=PipelineJobStatus)
def pipeline_job_status(job_id: str) -> PipelineJobStatus:
    return _read_pipeline_status_or_404(job_id)


@app.get("/pipeline/jobs/{job_id}/log", response_model=PipelineLogResponse)
def pipeline_job_log(
    job_id: str,
    limit_bytes: int = Query(default=20000, ge=1000, le=200000),
) -> PipelineLogResponse:
    _read_pipeline_status_or_404(job_id)
    path = _pipeline_log_path(job_id)
    log = _pipeline_tail_log(job_id, limit_bytes)
    return PipelineLogResponse(
        job_id=job_id,
        log_path=str(path),
        log=log,
        bytes=path.stat().st_size if path.exists() else 0,
        stage_logs=_pipeline_stage_logs(job_id, limit_bytes=limit_bytes),
    )


@app.post("/pipeline/jobs/{job_id}/cancel", response_model=PipelineJobStatus)
def pipeline_cancel_job(job_id: str) -> PipelineJobStatus:
    _require_local_job_execution("Pipeline")
    path = _pipeline_status_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Unknown pipeline job: {job_id}")
    payload = _read_json_file(path)
    status = str(payload.get("status") or "")
    if status in PIPELINE_TERMINAL_STATES:
        return PipelineJobStatus(**payload)
    with PIPELINE_JOB_LOCK:
        cancel_event = PIPELINE_CANCEL_EVENTS.get(job_id)
        process = PIPELINE_PROCESSES.get(job_id)
        if cancel_event:
            cancel_event.set()
        if process and process.poll() is None:
            process.terminate()
    _pipeline_append_log(job_id, "Cancellation requested.")
    return _write_pipeline_status(
        payload,
        status="cancel_requested",
        phase="cancel_requested",
        message="Cancellation requested. The active stage will stop at the next subprocess checkpoint.",
    )


@app.get("/provenance/manifest", response_model=ProvenanceManifestResponse)
def provenance_manifest(
    limit_documents: int = Query(default=100, ge=1, le=500),
    include_embeddings: bool = Query(default=True),
) -> ProvenanceManifestResponse:
    if config.PROVENANCE_READ_MODE == "snapshot":
        try:
            payload = get_provenance_snapshot_service().manifest_payload(
                limit_documents=limit_documents,
                include_embeddings=include_embeddings,
            )
        except SnapshotError as exc:
            logger.warning("Provenance snapshot unavailable: %s", exc)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "provenance_snapshot_unavailable",
                    "message": "The published Provenance snapshot is unavailable or invalid.",
                },
            ) from exc
        return ProvenanceManifestResponse(**payload)
    return ProvenanceManifestResponse(
        **build_provenance_manifest(
            limit_documents=limit_documents,
            include_embeddings=include_embeddings,
        )
    )


@app.get("/provenance/trace/{doc_id}", response_model=ProvenanceTraceResponse)
def provenance_trace(doc_id: str) -> ProvenanceTraceResponse:
    if config.PROVENANCE_READ_MODE == "snapshot":
        try:
            payload = get_provenance_snapshot_service().trace_payload(doc_id)
        except SnapshotError as exc:
            logger.warning("Provenance snapshot unavailable: %s", exc)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "provenance_snapshot_unavailable",
                    "message": "The published Provenance snapshot is unavailable or invalid.",
                },
            ) from exc
        return ProvenanceTraceResponse(**payload)
    return ProvenanceTraceResponse(**build_document_trace(doc_id))


@app.get("/provenance/upsert-dry-run", response_model=UpsertDryRunResponse)
def provenance_upsert_dry_run(
    limit_keys: int = Query(default=25, ge=0, le=250),
) -> UpsertDryRunResponse:
    return UpsertDryRunResponse(**build_upsert_dry_run_plan(limit_keys=limit_keys))


@app.get("/debug")
def debug_state() -> Dict[str, Any]:
    datasets: Dict[str, Dict[str, Any]] = {}
    for dataset, cfg in EXPLORE_DATASETS.items():
        try:
            df = _read_explore_dataset(dataset)
            datasets[dataset] = {
                "label": cfg["label"],
                "path": str(cfg["path"]),
                "exists": cfg["path"].exists(),
                "rows": len(df),
                "columns": list(df.columns),
                "date_columns": _date_columns(df, cfg),
                "numeric_columns": _numeric_columns(df),
                "default_columns": [column for column in cfg.get("default_columns", []) if column in df.columns],
                "default_x": cfg.get("default_x"),
                "default_y": cfg.get("default_y"),
                "filters": {
                    "bay": cfg.get("bay_column"),
                    "station": cfg.get("station_column"),
                    "source": cfg.get("source_column"),
                },
            }
        except HTTPException as exc:
            datasets[dataset] = {
                "label": cfg["label"],
                "path": str(cfg["path"]),
                "exists": cfg["path"].exists(),
                "error": str(exc.detail),
            }
        except Exception:
            logger.exception("Debug dataset inspection failed for %s", dataset)
            datasets[dataset] = {
                "label": cfg["label"],
                "path": str(cfg["path"]),
                "exists": cfg["path"].exists(),
                "error": "Dataset inspection failed",
            }

    routes = []
    for route in app.routes:
        routes.append(
            {
                "path": getattr(route, "path", ""),
                "name": getattr(route, "name", ""),
                "methods": sorted(getattr(route, "methods", []) or []),
            }
        )

    return {
        "app": {
            "title": app.title,
            "version": app.version,
            "project_root": str(PROJECT_ROOT),
            "cwd": os.getcwd(),
            "python": sys.version,
            "pandas": pd.__version__,
            "pid": os.getpid(),
        },
        "config": {
            "database_url": _redact_url(config.DATABASE_URL),
            "model_provider": config.MODEL_PROVIDER,
            "ollama_base_url": config.OLLAMA_BASE_URL,
            "embedding_model": config.EMBEDDING_MODEL,
            "chat_model": config.CHAT_MODEL,
            "job_execution_mode": config.JOB_EXECUTION_MODE,
            "cors_origins": _cors_origins(),
            "data_dir": str(config.DATA_DIR),
            "serving_dir": str(config.SERVING_DIR),
            "analysis_dir": str(config.ANALYSIS_DIR),
            "reliability_dir": str(config.RELIABILITY_DIR),
        },
        "selected_environment": {
            "DATABASE_URL": _redact_url(os.environ["DATABASE_URL"]) if os.environ.get("DATABASE_URL") else None,
            "OLLAMA_BASE_URL": os.environ.get("OLLAMA_BASE_URL"),
            "MODEL_PROVIDER": os.environ.get("MODEL_PROVIDER"),
            "EMBEDDING_MODEL": os.environ.get("EMBEDDING_MODEL"),
            "CHAT_MODEL": os.environ.get("CHAT_MODEL"),
            "JOB_EXECUTION_MODE": os.environ.get("JOB_EXECUTION_MODE"),
            "CORS_ORIGINS": os.environ.get("CORS_ORIGINS"),
        },
        "health": health().model_dump(),
        "stats": stats().model_dump(),
        "artifacts": _debug_artifacts(),
        "datasets": datasets,
        "routes": sorted(routes, key=lambda item: item["path"]),
        "cache": {
            "explore_dataset_cache": _read_explore_dataset.cache_info()._asdict(),
        },
        "notes": [
            "DATABASE_URL credentials are redacted.",
            "Raw process environment is intentionally omitted.",
        ],
    }


@app.get("/data/catalog", response_model=DataCatalogResponse)
def data_catalog() -> DataCatalogResponse:
    ctd_profiles = _ctd_profiles_df()
    context = _sample_context_df()
    sst_points = _sst_points_df()
    sst_daily = _sst_daily_df()

    ctd_samples = sorted(ctd_profiles["sample_id"].dropna().astype("string").unique().tolist())
    taxa_mask = (
        context.get("has_kraken", pd.Series(False, index=context.index)).fillna(False).astype(bool)
        | context.get("has_metaeuk", pd.Series(False, index=context.index)).fillna(False).astype(bool)
        | context.get("has_kraken_upper_group", pd.Series(False, index=context.index)).fillna(False).astype(bool)
    )
    taxa_samples = sorted(context.loc[taxa_mask, "sample_id"].dropna().astype("string").unique().tolist())
    variables = [column for column in CTD_PROFILE_VARIABLES if column in ctd_profiles.columns]

    return DataCatalogResponse(
        ctd_samples=ctd_samples,
        taxa_samples=taxa_samples,
        ctd_variables=variables,
        sst_observations=len(sst_points),
        sst_days=len(sst_daily),
        context_rows=len(context),
    )


@app.get("/data/ctd-profile/{sample_id}", response_model=CtdProfileResponse)
def data_ctd_profile(sample_id: str) -> CtdProfileResponse:
    profiles = _ctd_profiles_df()
    rows = profiles[profiles["sample_id"].astype("string") == sample_id].sort_values("depth_m")
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"Unknown CTD sample: {sample_id}")

    summary_df = _ctd_summary_df()
    summary_rows = summary_df[summary_df["sample_id"].astype("string") == sample_id]
    variables = [column for column in CTD_PROFILE_VARIABLES if column in rows.columns and rows[column].notna().any()]
    return CtdProfileResponse(
        sample_id=sample_id,
        summary=_records(summary_rows.head(1))[0] if not summary_rows.empty else None,
        variables=variables,
        rows=_records(rows[["ctd_date", "sample_id", "depth_m"] + variables]),
    )


@app.get("/data/taxa/{sample_id}", response_model=TaxaSampleResponse)
def data_taxa(sample_id: str) -> TaxaSampleResponse:
    context = _sample_context_df()
    rows = context[context["sample_id"].astype("string") == sample_id]
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"Unknown taxa sample: {sample_id}")
    row = rows.iloc[0]
    return TaxaSampleResponse(
        sample_id=sample_id,
        context=_records(rows.head(1))[0],
        kraken_top=_parse_taxa_json(row.get("top_genus_10_json_x"), label_keys=["genus", "taxon", "name"]),
        metaeuk_top=_parse_taxa_json(row.get("top_genus_10_json_y"), label_keys=["genus", "taxon", "name"]),
        upper_groups=_parse_taxa_json(row.get("top_upper_group_10_json"), label_keys=["upper_group", "group", "name"]),
    )


@app.get("/data/sst", response_model=SstDataResponse)
def data_sst(
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> SstDataResponse:
    points = _sst_points_df().copy()
    daily = _sst_daily_df().copy()

    if time_from:
        start = pd.to_datetime(time_from)
        points = points[pd.to_datetime(points["time_jst"], errors="coerce") >= start]
        daily = daily[pd.to_datetime(daily["date_jst"], errors="coerce") >= start]
    if time_to:
        end = pd.to_datetime(time_to)
        points = points[pd.to_datetime(points["time_jst"], errors="coerce") <= end]
        daily = daily[pd.to_datetime(daily["date_jst"], errors="coerce") <= end]

    points = points.sort_values("time_jst").head(limit)
    daily = daily.sort_values("date_jst")
    sst_values = pd.to_numeric(points["sst"], errors="coerce")
    stats_payload: Dict[str, Any] = {
        "min_sst": _json_safe_value(sst_values.min(skipna=True)) if not sst_values.empty else None,
        "max_sst": _json_safe_value(sst_values.max(skipna=True)) if not sst_values.empty else None,
        "mean_sst": _json_safe_value(sst_values.mean(skipna=True)) if not sst_values.empty else None,
        "nearest_lat": _json_safe_value(points["nearest_lat"].dropna().iloc[0]) if "nearest_lat" in points and points["nearest_lat"].notna().any() else None,
        "nearest_lon": _json_safe_value(points["nearest_lon"].dropna().iloc[0]) if "nearest_lon" in points and points["nearest_lon"].notna().any() else None,
    }

    return SstDataResponse(
        observations=len(points),
        days=len(daily),
        stats=stats_payload,
        points=[
            SstPoint(time_jst=str(_json_safe_value(row["time_jst"])), sst=float(row["sst"]))
            for _, row in points.dropna(subset=["sst"]).iterrows()
        ],
        daily=[
            SstDailyPoint(
                date_jst=str(_json_safe_value(row["date_jst"])),
                mean_sst=_json_safe_value(row.get("mean_sst")),
                min_sst=_json_safe_value(row.get("min_sst")),
                max_sst=_json_safe_value(row.get("max_sst")),
            )
            for _, row in daily.iterrows()
        ],
    )


def _edna_filters(
    *,
    sample_id: Optional[str] = None,
    assay_id: Optional[str] = None,
    provider: Optional[str] = None,
    provider_project_id: Optional[str] = None,
    provider_run_id: Optional[str] = None,
    assignment_method: Optional[str] = None,
    taxon: Optional[str] = None,
    sample_kind: Optional[str] = None,
    is_control: Optional[bool] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    lat_min: Optional[float] = None,
    lat_max: Optional[float] = None,
    lon_min: Optional[float] = None,
    lon_max: Optional[float] = None,
    strict_ids: bool = False,
) -> Dict[str, Any]:
    try:
        validate_time_range(time_from, time_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if assignment_method and assignment_method not in EDNA_ASSIGNMENT_METHODS:
        raise HTTPException(status_code=400, detail="Unsupported assignment_method")
    if sample_kind and sample_kind not in EDNA_SAMPLE_KINDS:
        raise HTTPException(status_code=400, detail="Unsupported sample_kind")
    if strict_ids:
        for value, label in ((sample_id, "sample_id"), (assay_id, "assay_id")):
            if value is not None:
                try:
                    validate_edna_id(value, label)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
    if lat_min is not None and lat_max is not None and lat_min > lat_max:
        raise HTTPException(status_code=400, detail="lat_min must not exceed lat_max")
    if lon_min is not None and lon_max is not None and lon_min > lon_max:
        raise HTTPException(status_code=400, detail="lon_min must not exceed lon_max")
    return {
        key: value
        for key, value in {
            "sample_id": sample_id,
            "assay_id": assay_id,
            "provider": provider,
            "provider_project_id": provider_project_id,
            "provider_run_id": provider_run_id,
            "assignment_method": assignment_method,
            "taxon": taxon,
            "sample_kind": sample_kind,
            "is_control": is_control,
            "time_from": time_from,
            "time_to": time_to,
            "lat_min": lat_min,
            "lat_max": lat_max,
            "lon_min": lon_min,
            "lon_max": lon_max,
        }.items()
        if value is not None
    }


def _documents_source_type(
    source_type: Optional[str], filters: Dict[str, Any]
) -> Optional[str]:
    if source_type is None:
        return None
    aliases = {
        "edna": "edna_metabarcoding",
        "environmental_dna": "edna_metabarcoding",
        "metabarcoding": "edna_metabarcoding",
        "mifish": "edna_metabarcoding",
        "anemone": "edna_metabarcoding",
    }
    normalized = aliases.get(source_type.strip().lower(), source_type.strip().lower())
    edna_only = {
        "provider",
        "provider_project_id",
        "provider_run_id",
        "assignment_method",
        "taxon",
        "sample_kind",
        "is_control",
    }
    if normalized != "edna_metabarcoding" and any(
        key in filters for key in edna_only
    ):
        raise HTTPException(
            status_code=400,
            detail="eDNA-only filters cannot be combined with a non-eDNA source_type",
        )
    return normalized


@app.get("/data/edna/catalog", response_model=EdnaCatalogResponse)
def data_edna_catalog() -> EdnaCatalogResponse:
    return EdnaCatalogResponse(**edna_catalog())


@app.get("/data/edna/samples", response_model=EdnaPageResponse)
def data_edna_samples(
    sample_id: Optional[str] = Query(default=None, max_length=64),
    assay_id: Optional[str] = Query(default=None, max_length=64),
    provider: Optional[str] = Query(default=None, max_length=64),
    provider_project_id: Optional[str] = Query(default=None, max_length=128),
    provider_run_id: Optional[str] = Query(default=None, max_length=128),
    assignment_method: Optional[str] = Query(default=None, max_length=64),
    taxon: Optional[str] = Query(default=None, min_length=1, max_length=200),
    sample_kind: Optional[str] = Query(default=None, max_length=32),
    is_control: Optional[bool] = None,
    time_from: Optional[str] = Query(default=None, max_length=64),
    time_to: Optional[str] = Query(default=None, max_length=64),
    lat_min: Optional[float] = Query(default=None, ge=-90, le=90),
    lat_max: Optional[float] = Query(default=None, ge=-90, le=90),
    lon_min: Optional[float] = Query(default=None, ge=-180, le=180),
    lon_max: Optional[float] = Query(default=None, ge=-180, le=180),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="collection_date_utc", max_length=64),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> EdnaPageResponse:
    filters = _edna_filters(
        sample_id=sample_id,
        assay_id=assay_id,
        provider=provider,
        provider_project_id=provider_project_id,
        provider_run_id=provider_run_id,
        assignment_method=assignment_method,
        taxon=taxon,
        sample_kind=sample_kind,
        is_control=is_control,
        time_from=time_from,
        time_to=time_to,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        strict_ids=True,
    )
    try:
        return EdnaPageResponse(
            **edna_samples(
                filters,
                limit=limit,
                offset=offset,
                sort=sort,
                direction=direction,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/data/edna/samples/{sample_id}",
    response_model=EdnaSampleDetailResponse,
)
def data_edna_sample(sample_id: str) -> EdnaSampleDetailResponse:
    try:
        payload = edna_sample_detail(sample_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload is None:
        raise HTTPException(status_code=404, detail="Unknown active eDNA sample")
    return EdnaSampleDetailResponse(**payload)


@app.get(
    "/data/edna/assays/{assay_id}",
    response_model=EdnaAssayDetailResponse,
)
def data_edna_assay(assay_id: str) -> EdnaAssayDetailResponse:
    try:
        payload = edna_assay_detail(assay_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload is None:
        raise HTTPException(status_code=404, detail="Unknown active eDNA assay")
    return EdnaAssayDetailResponse(**payload)


@app.get("/data/edna/detections", response_model=EdnaPageResponse)
def data_edna_detections(
    sample_id: Optional[str] = Query(default=None, max_length=200),
    assay_id: Optional[str] = Query(default=None, max_length=200),
    provider: Optional[str] = Query(default=None, max_length=64),
    provider_project_id: Optional[str] = Query(default=None, max_length=128),
    provider_run_id: Optional[str] = Query(default=None, max_length=128),
    assignment_method: Optional[str] = Query(default=None, max_length=64),
    taxon: Optional[str] = Query(default=None, min_length=1, max_length=200),
    sample_kind: Optional[str] = Query(default=None, max_length=32),
    is_control: Optional[bool] = None,
    time_from: Optional[str] = Query(default=None, max_length=64),
    time_to: Optional[str] = Query(default=None, max_length=64),
    lat_min: Optional[float] = Query(default=None, ge=-90, le=90),
    lat_max: Optional[float] = Query(default=None, ge=-90, le=90),
    lon_min: Optional[float] = Query(default=None, ge=-180, le=180),
    lon_max: Optional[float] = Query(default=None, ge=-180, le=180),
    include_sequence: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="read_count", max_length=64),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> EdnaPageResponse:
    filters = _edna_filters(
        sample_id=sample_id,
        assay_id=assay_id,
        provider=provider,
        provider_project_id=provider_project_id,
        provider_run_id=provider_run_id,
        assignment_method=assignment_method,
        taxon=taxon,
        sample_kind=sample_kind,
        is_control=is_control,
        time_from=time_from,
        time_to=time_to,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        strict_ids=True,
    )
    try:
        return EdnaPageResponse(
            **edna_detections(
                filters,
                limit=limit,
                offset=offset,
                sort=sort,
                direction=direction,
                include_sequence=include_sequence,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/data/edna/detections/{detection_id}",
    response_model=EdnaDetectionDetailResponse,
)
def data_edna_detection(detection_id: str) -> EdnaDetectionDetailResponse:
    try:
        payload = edna_detection_detail(detection_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload is None:
        raise HTTPException(status_code=404, detail="Unknown active eDNA detection")
    return EdnaDetectionDetailResponse(**payload)


@app.get("/data/edna/controls", response_model=EdnaPageResponse)
def data_edna_controls(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> EdnaPageResponse:
    return EdnaPageResponse(
        **edna_samples(
            {"is_control": True},
            limit=limit,
            offset=offset,
            sort="provider_sample_id",
            direction="asc",
        )
    )


@app.get("/data/edna/export")
def data_edna_export(
    sample_id: Optional[str] = Query(default=None, max_length=200),
    assay_id: Optional[str] = Query(default=None, max_length=200),
    provider: Optional[str] = Query(default=None, max_length=64),
    provider_project_id: Optional[str] = Query(default=None, max_length=128),
    provider_run_id: Optional[str] = Query(default=None, max_length=128),
    assignment_method: Optional[str] = Query(default=None, max_length=64),
    taxon: Optional[str] = Query(default=None, min_length=1, max_length=200),
    sample_kind: Optional[str] = Query(default=None, max_length=32),
    is_control: Optional[bool] = None,
    time_from: Optional[str] = Query(default=None, max_length=64),
    time_to: Optional[str] = Query(default=None, max_length=64),
    lat_min: Optional[float] = Query(default=None, ge=-90, le=90),
    lat_max: Optional[float] = Query(default=None, ge=-90, le=90),
    lon_min: Optional[float] = Query(default=None, ge=-180, le=180),
    lon_max: Optional[float] = Query(default=None, ge=-180, le=180),
) -> StreamingResponse:
    filters = _edna_filters(
        sample_id=sample_id,
        assay_id=assay_id,
        provider=provider,
        provider_project_id=provider_project_id,
        provider_run_id=provider_run_id,
        assignment_method=assignment_method,
        taxon=taxon,
        sample_kind=sample_kind,
        is_control=is_control,
        time_from=time_from,
        time_to=time_to,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        strict_ids=True,
    )
    payload = edna_detections(
        filters,
        limit=25_001,
        offset=0,
        sort="detection_id",
        direction="asc",
        include_sequence=False,
    )
    truncated = len(payload["rows"]) > 25_000
    rows = payload["rows"][:25_000]
    columns = [
        "detection_id",
        "assay_id",
        "sample_id",
        "provider",
        "provider_sample_id",
        "provider_project_id",
        "provider_run_id",
        "sample_kind",
        "is_control",
        "collection_date_utc",
        "lat",
        "lon",
        "target_gene",
        "primer_set",
        "sequencing_method",
        "assignment_method",
        "sequence_sha256",
        "assigned_taxon_name",
        "assigned_taxon_rank",
        "read_count",
        "copies_per_ml",
        "superkingdom",
        "kingdom",
        "phylum",
        "class",
        "order",
        "family",
        "genus",
        "species",
        "subspecies",
        "source_snapshot_id",
        "source_file_id",
        "source_row_number",
        "source_url",
        "source_sha256",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows({
        key: "'" + value
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
        else value
        for key, value in row.items()
    } for row in rows)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="anemone-edna-evidence.csv"',
            "X-Export-Truncated": str(truncated).lower(),
        },
    )


@app.get("/evaluation/catalog", response_model=EvaluationCatalogResponse)
def evaluation_catalog() -> EvaluationCatalogResponse:
    questions: List[EvaluationQuestion] = []
    for question in BENCHMARK_QUESTIONS:
        reference = get_reference(question.id)
        questions.append(
            EvaluationQuestion(
                id=question.id,
                category=question.category,
                question=question.question,
                expected_source_types=question.expected_source_types,
                expected_min_citations=question.expected_min_citations,
                requires_analysis=question.requires_analysis,
                requires_reliability=question.requires_reliability,
                reference_answer=reference.reference_text if reference else None,
                key_facts=reference.key_facts if reference else [],
                expected_citation_patterns=reference.expected_citation_patterns if reference else [],
            )
        )

    return EvaluationCatalogResponse(
        questions=questions,
        categories=QUESTION_CATEGORIES,
        modes=[
            EvaluationModeInfo(
                name=mode.name,
                inject_analysis=mode.inject_analysis,
                inject_reliability=mode.inject_reliability,
            )
            for mode in EVAL_MODES
        ],
        variants=[
            EvaluationVariantInfo(
                name=variant.name,
                source_coverage=variant.source_coverage,
                inject_analysis=variant.inject_analysis,
                inject_reliability=variant.inject_reliability,
                description=variant.description,
            )
            for variant in SYSTEM_VARIANTS
        ],
        metrics=EVALUATION_METRICS,
        quality_metrics=EVALUATION_QUALITY_METRICS,
    )


@app.get("/evaluation/preflight")
def evaluation_preflight() -> Dict[str, Any]:
    return {
        "ollama": _ollama_status(),
        "database": _database_status(),
        "artifacts": {
            **_artifact_status(),
            "evaluation_dir": _artifact_info(config.EVALUATION_DIR),
            "evaluation_runs": len(_evaluation_run_registry()),
        },
        "defaults": {
            "model": config.CHAT_MODEL,
            "embedding_model": config.EMBEDDING_MODEL,
            "ollama_base_url": config.OLLAMA_BASE_URL,
        },
    }


@app.post("/evaluation/runs/standard", response_model=EvaluationStartResponse)
def evaluation_start_standard(request: EvaluationStandardRunRequest) -> EvaluationStartResponse:
    return _start_evaluation_job("standard", request)


@app.post("/evaluation/runs/ablation", response_model=EvaluationStartResponse)
def evaluation_start_ablation(request: EvaluationAblationRunRequest) -> EvaluationStartResponse:
    return _start_evaluation_job("ablation", request)


@app.get("/evaluation/jobs/{job_id}", response_model=EvaluationJobStatus)
def evaluation_job_status(job_id: str) -> EvaluationJobStatus:
    return _read_job_status_or_404(job_id)


@app.post("/evaluation/jobs/{job_id}/cancel", response_model=EvaluationJobStatus)
def evaluation_cancel_job(job_id: str) -> EvaluationJobStatus:
    _require_local_job_execution("Evaluation")
    path = _job_status_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Unknown evaluation job: {job_id}")
    payload = _read_json_file(path)
    status = str(payload.get("status") or "")
    if status in EVALUATION_TERMINAL_STATES:
        return EvaluationJobStatus(**payload)
    with EVALUATION_JOB_LOCK:
        cancel_event = EVALUATION_CANCEL_EVENTS.get(job_id)
        if cancel_event:
            cancel_event.set()
    return _write_job_status(
        payload,
        status="cancel_requested",
        phase="cancel_requested",
        message="Cancellation requested. The current evaluation will stop at the next checkpoint.",
    )


@app.get("/evaluation/runs", response_model=EvaluationRunsResponse)
def evaluation_runs() -> EvaluationRunsResponse:
    runs = [_evaluation_run_summary(record) for record in _evaluation_csv_candidates()]
    runs.sort(key=lambda run: run.timestamp or "", reverse=True)
    return EvaluationRunsResponse(runs=runs)


@app.get("/evaluation/runs/{run_id}", response_model=EvaluationRunDetailResponse)
def evaluation_run_detail(
    run_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    mode: Optional[str] = None,
    category: Optional[str] = None,
    question_id: Optional[str] = None,
) -> EvaluationRunDetailResponse:
    record = _evaluation_record_or_404(run_id)
    summary = _evaluation_run_summary(record)
    source_df = _evaluation_results_frame(record)
    df = source_df.copy()

    if mode and "mode" in df.columns:
        df = df[df["mode"].astype(str) == mode]
    if category and "category" in df.columns:
        df = df[df["category"].astype(str) == category]
    if question_id and "question_id" in df.columns:
        df = df[df["question_id"].astype(str) == question_id]

    row_count = len(df)
    rows = _records(df.iloc[offset:offset + limit])
    return EvaluationRunDetailResponse(
        run=summary,
        columns=list(df.columns),
        rows=rows,
        row_count=row_count,
        limit=limit,
        offset=offset,
        summary=_evaluation_summary_from_frame(source_df),
    )


@app.get("/evaluation/runs/{run_id}/analytics", response_model=EvaluationAnalyticsResponse)
def evaluation_run_analytics(
    run_id: str,
    metric: Optional[str] = None,
    baseline_mode: Optional[str] = None,
    category: Optional[str] = None,
) -> EvaluationAnalyticsResponse:
    record = _evaluation_record_or_404(run_id)
    return _evaluation_analytics_payload(
        record,
        metric=metric,
        baseline_mode=baseline_mode,
        category=category,
    )


@app.get("/evaluation/runs/{run_id}/report", response_model=EvaluationReportResponse)
def evaluation_run_report(run_id: str) -> EvaluationReportResponse:
    record = _evaluation_record_or_404(run_id)
    report_path = _evaluation_report_path(record)
    if report_path and report_path.exists():
        return EvaluationReportResponse(run_id=run_id, markdown=report_path.read_text(encoding="utf-8"))

    df = _evaluation_results_frame(record)
    meta = _read_json_file(_evaluation_meta_path(record))
    meta.setdefault("run_id", run_id)
    meta.setdefault("model", _evaluation_run_summary(record).model or "unknown")
    from evaluation.report import generate_report

    return EvaluationReportResponse(run_id=run_id, markdown=generate_report(df, meta))


@app.post("/evaluation/compare", response_model=EvaluationCompareResponse)
def evaluation_compare(request: EvaluationCompareRequest) -> EvaluationCompareResponse:
    registry = _evaluation_run_registry()
    missing = [run_id for run_id in request.run_ids if run_id not in registry]
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown evaluation run: {missing[0]}")

    records = [registry[run_id] for run_id in request.run_ids]
    runs = [_evaluation_run_summary(record) for record in records]
    by_mode: List[Dict[str, Any]] = []
    for run, record in zip(runs, records):
        df = _evaluation_results_frame(record)
        summary = _evaluation_summary_from_frame(df).get("by_mode", [])
        for row in summary:
            row["run_id"] = run.run_id
            row["model"] = run.model
            by_mode.append(row)

    from evaluation.report import compare_runs

    markdown = compare_runs([record["csv_path"] for record in records])
    return EvaluationCompareResponse(
        run_ids=request.run_ids,
        runs=runs,
        markdown=markdown,
        by_mode=by_mode,
    )


@app.get("/analysis", response_model=AnalysisResponse)
def analysis_state(
    cooccurrence_pairs: int = Query(default=30, ge=1, le=200),
    table_limit: int = Query(default=500, ge=10, le=2000),
) -> AnalysisResponse:
    trends = _analysis_df("ctd_monthly_trends")
    correlations = _analysis_df("taxa_env_correlations")
    diversity = _analysis_df("diversity_indices")
    cooccurrence = _analysis_df("taxa_cooccurrence")
    sst_ctd = _analysis_df("sst_ctd_validation")
    gap = _analysis_df("gap_interpolation")
    div_pred = _analysis_df("diversity_prediction")
    corroboration = _analysis_df("corroboration")

    trend_variables = sorted(
        column.removesuffix("_mean")
        for column in trends.columns
        if column.endswith("_mean") and column not in {"strat_index_mean"}
    )
    catalog = {
        name: _artifact_info(path)
        for name, path in _analysis_artifacts().items()
    }
    catalog["trend_variables"] = trend_variables
    catalog["diversity_sources"] = sorted(diversity["source"].dropna().astype("string").unique().tolist()) if "source" in diversity else []
    catalog["correlation_variables"] = sorted(correlations["env_variable"].dropna().astype("string").unique().tolist()) if "env_variable" in correlations else []

    ctd_trends = {
        "rows": _records_limited(trends, table_limit),
        "variables": trend_variables,
        "by_bay": _mean_by_group(
            trends,
            "bay",
            ["mean_temperature_mean", "mean_salinity_mean", "mean_do_percent_mean", "mean_chl_a_mean", "mean_turbidity_mean", "strat_index_mean"],
        ),
    }
    correlations_payload = {
        "rows": _records_limited(correlations.sort_values(["significant", "p_value"], ascending=[False, True]), table_limit),
        "significant": _records_limited(correlations[correlations["significant"]].sort_values("p_value"), table_limit) if "significant" in correlations else [],
        "summary": {
            "total": len(correlations),
            "significant": int(correlations["significant"].sum()) if "significant" in correlations else 0,
            "genera": int(correlations["genus"].nunique()) if "genus" in correlations else 0,
            "env_variables": int(correlations["env_variable"].nunique()) if "env_variable" in correlations else 0,
        },
    }
    diversity_payload = {
        "rows": _records_limited(diversity.sort_values(["source", "year_month", "sample_id"]), table_limit),
        "by_source": _mean_by_group(diversity, "source", ["shannon_h", "simpson_1d", "richness", "evenness"]),
        "by_bay": _mean_by_group(diversity, "bay", ["shannon_h", "simpson_1d", "richness", "evenness"]),
    }
    cooccurrence_payload = {
        "labels": list(cooccurrence.index.astype(str)),
        "matrix": [
            [_json_safe_value(value) for value in row]
            for row in cooccurrence.to_numpy().tolist()
        ],
        "top_pairs": _cooccurrence_pairs(cooccurrence, cooccurrence_pairs),
    }
    reliability_payload = {
        "sst_ctd": {
            "rows": _records_limited(sst_ctd.sort_values("ctd_date"), table_limit),
            "summary": {
                "paired": len(sst_ctd),
                "agree": int(sst_ctd["agrees"].sum()) if "agrees" in sst_ctd else 0,
                "mean_abs_delta_t": _json_safe_value(sst_ctd["abs_delta_t"].mean()) if "abs_delta_t" in sst_ctd else None,
                "mean_score": _json_safe_value(sst_ctd["reliability_score"].mean()) if "reliability_score" in sst_ctd else None,
            },
        },
        "gap": {
            "rows": _records_limited(gap.sort_values("date"), table_limit),
            "summary": {
                "days": len(gap),
                "in_ctd_gap": int(gap["in_ctd_gap"].sum()) if "in_ctd_gap" in gap else 0,
                "mean_confidence": _json_safe_value(gap["confidence"].mean()) if "confidence" in gap else None,
            },
        },
        "diversity_prediction": {
            "rows": _records_limited(div_pred.sort_values("sample_id"), table_limit),
            "summary": {
                "samples": len(div_pred),
                "anomalies": int(div_pred["is_anomaly"].sum()) if "is_anomaly" in div_pred else 0,
                "mean_abs_deviation_sigma": _json_safe_value(div_pred["deviation_sigma"].abs().mean()) if "deviation_sigma" in div_pred else None,
            },
        },
        "corroboration": {
            "rows": _records_limited(corroboration.sort_values(["reliability_tier", "sample_id"]), table_limit),
            "tier_counts": {str(key): int(value) for key, value in corroboration["reliability_tier"].value_counts().items()} if "reliability_tier" in corroboration else {},
            "mean_score": _json_safe_value(corroboration["reliability_score"].mean()) if "reliability_score" in corroboration else None,
        },
    }
    return AnalysisResponse(
        catalog=catalog,
        ctd_trends=ctd_trends,
        correlations=correlations_payload,
        diversity=diversity_payload,
        cooccurrence=cooccurrence_payload,
        reliability=reliability_payload,
    )


@app.get("/database/schema", response_model=DatabaseSchemaResponse)
def database_schema() -> DatabaseSchemaResponse:
    try:
        engine = _database_engine()
        inspector = inspect(engine)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            tables = []
            for table_name in inspector.get_table_names():
                quoted = _quote_identifier(engine, table_name)
                row_count = conn.execute(text(f"SELECT count(*) FROM {quoted}")).scalar()
                tables.append(
                    {
                        "name": table_name,
                        "row_count": int(row_count or 0),
                        "columns": [
                            {
                                "name": column["name"],
                                "type": str(column["type"]),
                                "nullable": bool(column.get("nullable", True)),
                                "default": str(column.get("default") or ""),
                            }
                            for column in inspector.get_columns(table_name)
                        ],
                        "primary_key": inspector.get_pk_constraint(table_name).get("constrained_columns", []),
                        "indexes": inspector.get_indexes(table_name),
                    }
                )
        return DatabaseSchemaResponse(available=True, version=str(version), tables=tables)
    except Exception:
        logger.exception("Database schema inspection failed")
        return DatabaseSchemaResponse(
            available=False,
            error="Database schema is unavailable",
        )


@app.get("/database/table", response_model=DatabaseTableResponse)
def database_table(
    table_name: str = Query(..., alias="table"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    order_by: Optional[str] = None,
    direction: str = Query(default="asc", pattern="^(asc|desc)$"),
    include_heavy: bool = False,
) -> DatabaseTableResponse:
    engine = _database_engine()
    columns = _validate_table_and_columns(engine, table_name)
    if order_by and order_by not in columns:
        raise HTTPException(status_code=400, detail=f"Unknown order_by column: {order_by}")
    visible_columns = columns if include_heavy else [column for column in columns if column not in {"embedding", "text_tsv"}]
    quoted_table = _quote_identifier(engine, table_name)
    quoted_columns = ", ".join(_quote_identifier(engine, column) for column in visible_columns) or "*"
    if direction == "asc":
        direction_sql = "ASC"
    elif direction == "desc":
        direction_sql = "DESC"
    else:
        raise HTTPException(status_code=400, detail="Unknown sort direction")
    order_sql = f" ORDER BY {_quote_identifier(engine, order_by)} {direction_sql}" if order_by else ""
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT count(*) FROM {quoted_table}")).scalar()
        rows = conn.execute(text(f"SELECT {quoted_columns} FROM {quoted_table}{order_sql} LIMIT :limit OFFSET :offset"), {"limit": limit, "offset": offset}).mappings().all()
    return DatabaseTableResponse(
        table=table_name,
        total=int(total or 0),
        limit=limit,
        offset=offset,
        columns=visible_columns,
        rows=[{key: _json_safe_value(value) for key, value in row.items()} for row in rows],
    )


@app.get("/explore/catalog", response_model=List[DatasetCatalogItem])
def explore_catalog() -> List[DatasetCatalogItem]:
    items: List[DatasetCatalogItem] = []
    for dataset, cfg in EXPLORE_DATASETS.items():
        df = _read_explore_dataset(dataset)
        filters: Dict[str, str] = {}
        for filter_name, column_key in [
            ("bay", "bay_column"),
            ("station", "station_column"),
            ("source", "source_column"),
        ]:
            column = cfg.get(column_key)
            if column and column in df.columns:
                filters[filter_name] = column

        items.append(
            DatasetCatalogItem(
                id=dataset,
                label=cfg["label"],
                row_count=len(df),
                columns=list(df.columns),
                date_columns=_date_columns(df, cfg),
                numeric_columns=_numeric_columns(df),
                default_columns=[column for column in cfg.get("default_columns", []) if column in df.columns],
                default_x=cfg.get("default_x") if cfg.get("default_x") in df.columns else None,
                default_y=cfg.get("default_y") if cfg.get("default_y") in df.columns else None,
                filters=filters,
            )
        )
    return items


@app.get("/explore/table", response_model=ExploreTableResponse)
def explore_table(
    dataset: str,
    bay: Optional[str] = None,
    station: Optional[str] = None,
    source: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    search: Optional[str] = Query(default=None, max_length=200),
    columns: Optional[str] = None,
    sort: Optional[str] = None,
    direction: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ExploreTableResponse:
    cfg = _dataset_config(dataset)
    df = _read_explore_dataset(dataset)
    filtered = _filter_explore_df(
        df,
        cfg,
        bay=bay,
        station=station,
        source=source,
        time_from=time_from,
        time_to=time_to,
        search=search,
    )

    selected = _selected_columns(filtered, cfg, columns)
    sort_column = sort or cfg.get("default_x") or selected[0]
    if sort_column not in filtered.columns:
        raise HTTPException(status_code=400, detail=f"Unknown sort column: {sort_column}")
    filtered = filtered.sort_values(
        by=sort_column,
        ascending=direction == "asc",
        na_position="last",
        kind="mergesort",
    )
    page = filtered.iloc[offset : offset + limit][selected]
    return ExploreTableResponse(
        dataset=dataset,
        total=len(df),
        filtered=len(filtered),
        limit=limit,
        offset=offset,
        columns=selected,
        rows=_records(page),
    )


@app.get("/explore/summary", response_model=ExploreSummaryResponse)
def explore_summary(
    dataset: str,
    bay: Optional[str] = None,
    station: Optional[str] = None,
    source: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    search: Optional[str] = Query(default=None, max_length=200),
) -> ExploreSummaryResponse:
    cfg = _dataset_config(dataset)
    df = _read_explore_dataset(dataset)
    filtered = _filter_explore_df(
        df,
        cfg,
        bay=bay,
        station=station,
        source=source,
        time_from=time_from,
        time_to=time_to,
        search=search,
    )
    return ExploreSummaryResponse(
        dataset=dataset,
        total_rows=len(df),
        filtered_rows=len(filtered),
        columns=list(df.columns),
        numeric_columns=_numeric_columns(df),
        date_columns=_date_columns(df, cfg),
        profiles=[_profile_column(column, filtered[column]) for column in filtered.columns],
    )


@app.get("/explore/timeseries", response_model=TimeSeriesResponse)
def explore_timeseries(
    dataset: str,
    x_column: Optional[str] = None,
    y_column: Optional[str] = None,
    bay: Optional[str] = None,
    station: Optional[str] = None,
    source: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    search: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=500, ge=1, le=2000),
) -> TimeSeriesResponse:
    cfg = _dataset_config(dataset)
    df = _read_explore_dataset(dataset)
    filtered = _filter_explore_df(
        df,
        cfg,
        bay=bay,
        station=station,
        source=source,
        time_from=time_from,
        time_to=time_to,
        search=search,
    )
    x = x_column or cfg.get("default_x") or next(iter(_date_columns(filtered, cfg)), None)
    y = y_column or cfg.get("default_y")
    if not x or x not in filtered.columns:
        raise HTTPException(status_code=400, detail="No valid x column for this dataset")
    if not y or y not in filtered.columns:
        raise HTTPException(status_code=400, detail="No valid y column for this dataset")
    if not pd.api.types.is_numeric_dtype(filtered[y]):
        raise HTTPException(status_code=400, detail=f"Column is not numeric: {y}")

    meta_columns = [
        column
        for column in ["sample_id", "bay", "source", "source_type"]
        if column in filtered.columns and column not in {x, y}
    ]
    plot_columns = [x, y] + meta_columns
    plot_df = filtered[plot_columns].dropna(subset=[x, y]).copy()
    plot_df["_sort_x"] = pd.to_datetime(plot_df[x].astype("string"), errors="coerce")
    plot_df = plot_df.sort_values(["_sort_x", x], na_position="last").head(limit)

    points: List[TimeSeriesPoint] = []
    for _, row in plot_df.iterrows():
        value = _json_safe_value(row[y])
        if value is None:
            continue
        points.append(
            TimeSeriesPoint(
                x=str(_json_safe_value(row[x])),
                y=float(value),
                sample_id=str(row["sample_id"]) if "sample_id" in plot_df.columns and not pd.isna(row.get("sample_id")) else None,
                bay=str(row["bay"]) if "bay" in plot_df.columns and not pd.isna(row.get("bay")) else None,
                source=(
                    str(row["source"])
                    if "source" in plot_df.columns and not pd.isna(row.get("source"))
                    else str(row["source_type"])
                    if "source_type" in plot_df.columns and not pd.isna(row.get("source_type"))
                    else None
                ),
            )
        )
    return TimeSeriesResponse(dataset=dataset, x_column=x, y_column=y, points=points)


@app.get("/explore/sample/{sample_id}", response_model=SampleDetailResponse)
def explore_sample(sample_id: str) -> SampleDetailResponse:
    def sample_rows(dataset: str) -> List[Dict[str, Any]]:
        df = _read_explore_dataset(dataset)
        if "sample_id" not in df.columns:
            return []
        return _records(df[df["sample_id"].astype("string") == sample_id])

    registry_rows = sample_rows("sample_registry")
    documents = [
        _source_document(row)
        for row in _read_jsonl(config.SERVING_DIR / "retrieval_documents.jsonl")
        if str(row.get("sample_id") or "") == sample_id
    ]
    reliability = sample_rows("corroboration") + sample_rows("sst_ctd_validation")
    if (config.RELIABILITY_DIR / "diversity_prediction.parquet").exists():
        prediction_df = _derive_sample_fields(
            pd.read_parquet(config.RELIABILITY_DIR / "diversity_prediction.parquet")
        )
        reliability.extend(_records(prediction_df[prediction_df["sample_id"].astype("string") == sample_id]))

    return SampleDetailResponse(
        sample_id=sample_id,
        registry=registry_rows[0] if registry_rows else None,
        ctd=sample_rows("ctd_summary"),
        diversity=sample_rows("diversity"),
        reliability=reliability,
        documents=documents[:10],
    )


@app.get("/documents", response_model=List[SourceDocument])
def documents(
    q: Optional[str] = None,
    source_type: Optional[str] = None,
    sample_id: Optional[str] = None,
    bay: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    provider: Optional[str] = None,
    provider_project_id: Optional[str] = None,
    provider_run_id: Optional[str] = None,
    assignment_method: Optional[str] = None,
    taxon: Optional[str] = None,
    sample_kind: Optional[str] = None,
    is_control: Optional[bool] = None,
    lat_min: Optional[float] = Query(default=None, ge=-90, le=90),
    lat_max: Optional[float] = Query(default=None, ge=-90, le=90),
    lon_min: Optional[float] = Query(default=None, ge=-180, le=180),
    lon_max: Optional[float] = Query(default=None, ge=-180, le=180),
    limit: int = Query(default=25, ge=1, le=100),
) -> List[SourceDocument]:
    filters = _edna_filters(
        sample_id=sample_id,
        provider=provider,
        provider_project_id=provider_project_id,
        provider_run_id=provider_run_id,
        assignment_method=assignment_method,
        taxon=taxon,
        sample_kind=sample_kind,
        is_control=is_control,
        time_from=time_from,
        time_to=time_to,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
    )
    source_type = _documents_source_type(source_type, filters)
    if q:
        rows = retrieve(
            q,
            k=limit,
            source_type=source_type,
            sample_id=sample_id,
            bay=bay,
            time_from=time_from,
            time_to=time_to,
            **{key: value for key, value in filters.items() if key not in {"sample_id", "time_from", "time_to"}},
        )
    else:
        local = LocalRetriever()
        local.load()
        rows = local.search(
            "",
            k=limit,
            source_type=source_type,
            sample_id=sample_id,
            bay=bay,
            time_from=time_from,
            time_to=time_to,
            **{key: value for key, value in filters.items() if key not in {"sample_id", "time_from", "time_to"}},
        )
    return [_source_document(row) for row in rows]


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve_sources(request: RetrieveRequest) -> RetrieveResponse:
    request, analysis_members, analysis_methods = _resolve_analysis_request(request)
    bundle = retrieve_with_expansion(
        request.query,
        k=request.k,
        sample_ids=None if analysis_members is None else sorted(analysis_members),
        assignment_methods=None if analysis_methods is None else sorted(analysis_methods),
        source_type=request.source_type,
        sample_id=request.sample_id,
        bay=request.bay,
        time_from=request.time_from,
        time_to=request.time_to,
        provider=request.provider,
        provider_project_id=request.provider_project_id,
        provider_run_id=request.provider_run_id,
        assignment_method=request.assignment_method,
        taxon=request.taxon,
        sample_kind=request.sample_kind,
        is_control=request.is_control,
        lat_min=request.lat_min,
        lat_max=request.lat_max,
        lon_min=request.lon_min,
        lon_max=request.lon_max,
        vector_weight=request.vector_weight,
        fts_weight=request.fts_weight,
        rrf_k=request.rrf_k,
        expand_evidence=request.expand_evidence,
        max_linked_sources=request.max_linked_sources,
    )
    primary_rows = bundle.get("primary") or []
    linked_rows = bundle.get("linked") or []
    if analysis_members is not None:
        primary_rows = [r for r in primary_rows if r.get('sample_id') in analysis_members and r.get('assignment_method') in analysis_methods]
        linked_rows = []
    return RetrieveResponse(
        query=request.query,
        sources=[_source_document(row) for row in primary_rows],
        linked_sources=[_source_document(row) for row in linked_rows],
        diagnostics=bundle.get("diagnostics") or {},
    )


def _resolve_analysis_request(request):
    if not request.analysis_id:
        return request, None, None
    from ingestion.edna_analysis_bundle import request_scope
    from ingestion.provenance_snapshot import SnapshotError
    try:
        updates, members, methods = request_scope(request.model_dump())
        return request.model_copy(update=updates), members, methods
    except (ValueError, OSError, KeyError, SnapshotError) as exc:
        raise HTTPException(409, str(exc)) from exc


def _chat_latency_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _mark_chat_failed_safely(
    *,
    interaction_id: Optional[uuid.UUID],
    user: CurrentUser,
    error_code: str,
    started_at: float,
) -> None:
    try:
        fail_chat_interaction(
            interaction_id=interaction_id,
            user=user,
            error_code=error_code,
            latency_ms=_chat_latency_ms(started_at),
        )
    except Exception:
        logger.exception(
            "Could not mark chat interaction %s as failed",
            interaction_id,
        )


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    request, analysis_members, analysis_methods = _resolve_analysis_request(request)
    started_at = time.perf_counter()
    model = _allowed_model(
        request.model,
        default=config.CHAT_MODEL,
        allowed=config.ALLOWED_CHAT_MODELS,
        label="chat model",
    )
    ollama_options = _ollama_options(request)
    response_options = {
        "generation": ollama_options,
        "retrieval": {
            "k": request.k,
            "source_type": request.source_type,
            "sample_id": request.sample_id,
            "bay": request.bay,
            "time_from": request.time_from,
            "time_to": request.time_to,
            "provider": request.provider,
            "provider_project_id": request.provider_project_id,
            "provider_run_id": request.provider_run_id,
            "assignment_method": request.assignment_method,
            "taxon": request.taxon,
            "sample_kind": request.sample_kind,
            "is_control": request.is_control,
            "lat_min": request.lat_min,
            "lat_max": request.lat_max,
            "lon_min": request.lon_min,
            "lon_max": request.lon_max,
            "vector_weight": request.vector_weight,
            "fts_weight": request.fts_weight,
            "rrf_k": request.rrf_k,
            "expand_evidence": request.expand_evidence,
            "max_linked_sources": request.max_linked_sources,
        },
        "context": {
            "analysis_id": request.analysis_id,
            "inject_analysis": request.inject_analysis,
            "inject_reliability": request.inject_reliability,
            "run_answer_audit": request.run_answer_audit,
        },
    }
    interaction_id = create_chat_interaction(
        user=user,
        query=request.query,
        model=model,
        request_options=response_options,
    )

    try:
        bundle = retrieve_with_expansion(
            request.query,
            k=request.k,
            sample_ids=None if analysis_members is None else sorted(analysis_members),
            assignment_methods=None if analysis_methods is None else sorted(analysis_methods),
            source_type=request.source_type,
            sample_id=request.sample_id,
            bay=request.bay,
            time_from=request.time_from,
            time_to=request.time_to,
            provider=request.provider,
            provider_project_id=request.provider_project_id,
            provider_run_id=request.provider_run_id,
            assignment_method=request.assignment_method,
            taxon=request.taxon,
            sample_kind=request.sample_kind,
            is_control=request.is_control,
            lat_min=request.lat_min,
            lat_max=request.lat_max,
            lon_min=request.lon_min,
            lon_max=request.lon_max,
            vector_weight=request.vector_weight,
            fts_weight=request.fts_weight,
            rrf_k=request.rrf_k,
            expand_evidence=request.expand_evidence,
            max_linked_sources=request.max_linked_sources,
        )
        rows = bundle.get("primary") or []
        if analysis_members is not None:
            rows = [r for r in rows if r.get('sample_id') in analysis_members and r.get('assignment_method') in analysis_methods]
        linked_rows = bundle.get("linked") or []
        if analysis_members is not None:
            linked_rows = []
        retrieval_diagnostics = bundle.get("diagnostics") or {}
        prompt, context = build_prompt_with_context(
            request.query,
            rows,
            evidence_scope=request.model_dump(),
            linked_results=linked_rows,
            inject_analysis=request.inject_analysis,
            inject_reliability=request.inject_reliability,
        )
        sources = [_source_document(row) for row in rows]
        linked_sources = [_source_document(row) for row in linked_rows]
        analysis_context = [
            _context_document(row, "analysis")
            for row in context.get("analysis", [])
        ]
        reliability_context = [
            _context_document(row, "reliability")
            for row in context.get("reliability", [])
        ]
        prompt_diagnostics = _prompt_diagnostics(
            prompt,
            rows,
            context,
            linked_rows,
        )
        evidence_snapshot = {
            "sources": sources,
            "linked_sources": linked_sources,
            "analysis_context": analysis_context,
            "reliability_context": reliability_context,
            "retrieval_diagnostics": retrieval_diagnostics,
            "prompt_diagnostics": prompt_diagnostics,
        }
        record_chat_context(
            interaction_id=interaction_id,
            user=user,
            evidence_snapshot=evidence_snapshot,
            prompt=prompt,
        )

        try:
            answer = get_model_runtime().chat(
                model=model,
                prompt=prompt,
                options=ollama_options,
                timeout=120,
            )
        except Exception as exc:
            _mark_chat_failed_safely(
                interaction_id=interaction_id,
                user=user,
                error_code="llm_request_failed",
                started_at=started_at,
            )
            logger.exception("Language model request failed")
            detail = {
                "code": "llm_request_failed",
                "message": "The language model could not complete the request",
            }
            if interaction_id is not None:
                detail["interaction_id"] = str(interaction_id)
            raise HTTPException(status_code=502, detail=detail) from exc

        answer_audit = (
            audit_answer(
                query=request.query,
                answer=answer,
                primary_sources=rows,
                linked_sources=linked_rows,
                analysis_context=context.get("analysis", []),
                reliability_context=context.get("reliability", []),
                retrieval_diagnostics=retrieval_diagnostics,
            )
            if request.run_answer_audit
            else None
        )
        complete_chat_interaction(
            interaction_id=interaction_id,
            user=user,
            answer=answer,
            answer_audit_snapshot=json_safe(answer_audit),
            latency_ms=_chat_latency_ms(started_at),
        )

        return ChatResponse(
            interaction_id=interaction_id,
            query=request.query,
            answer=answer,
            sources=sources,
            linked_sources=linked_sources,
            analysis_context=analysis_context,
            reliability_context=reliability_context,
            model=model,
            n_sources=len(rows),
            n_linked_sources=len(linked_rows),
            n_context_documents=(
                len(analysis_context) + len(reliability_context)
            ),
            prompt_diagnostics=prompt_diagnostics,
            retrieval_diagnostics=retrieval_diagnostics,
            answer_audit=answer_audit,
            options=response_options,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _mark_chat_failed_safely(
            interaction_id=interaction_id,
            user=user,
            error_code="chat_processing_failed",
            started_at=started_at,
        )
        logger.exception("Chat request failed before completion")
        detail = {
            "code": "chat_processing_failed",
            "message": "The chat request could not be completed",
        }
        if interaction_id is not None:
            detail["interaction_id"] = str(interaction_id)
        raise HTTPException(status_code=500, detail=detail) from exc
