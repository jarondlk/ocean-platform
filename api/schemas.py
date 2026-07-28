from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: Optional[str] = None
    role: str
    account_type: str
    status: str
    permissions: List[str] = Field(default_factory=list)


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    display_name: Optional[str] = None
    role: str
    account_type: str
    status: str
    auth_provider: str
    created_at: datetime
    last_login_at: Optional[datetime] = None


class InvitationCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    role: str = "viewer"
    account_type: str = "research"
    expires_in_days: int = Field(default=7, ge=1, le=90)


class InvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    account_type: str
    status: str
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    created_at: datetime


class UserUpdate(BaseModel):
    role: Optional[str] = None
    account_type: Optional[str] = None
    status: Optional[str] = None


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    k: int = Field(default=8, ge=1, le=25, validation_alias=AliasChoices("k", "top_k"))
    source_type: Optional[str] = Field(default=None, max_length=64)
    bay: Optional[str] = Field(default=None, max_length=64)
    time_from: Optional[str] = Field(default=None, max_length=64)
    time_to: Optional[str] = Field(default=None, max_length=64)
    vector_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    fts_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    rrf_k: int = Field(default=60, ge=1, le=200)
    expand_evidence: bool = True
    max_linked_sources: int = Field(default=5, ge=0, le=25)


class ChatRequest(RetrieveRequest):
    model: Optional[str] = Field(default=None, max_length=255)
    inject_analysis: bool = True
    inject_reliability: bool = True
    run_answer_audit: bool = True
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.1, ge=0.5, le=2.0)
    num_ctx: int = Field(default=8192, ge=512, le=32768)
    num_predict: Optional[int] = Field(default=None, ge=1, le=8192)
    sampling_top_k: Optional[int] = Field(default=None, ge=1, le=200)
    seed: Optional[int] = Field(default=None, ge=0)


class SourceDocument(BaseModel):
    doc_id: str
    title: str = ""
    source_type: str = "unknown"
    sample_id: Optional[str] = None
    event_id: Optional[str] = None
    time: Optional[str] = None
    bay: Optional[str] = None
    station: Optional[str] = None
    text: str = ""
    score: Optional[float] = None
    rank_sources: Dict[str, int] = Field(default_factory=dict)
    retrieval_role: str = "primary"
    link_type: Optional[str] = None
    linked_from_doc_id: Optional[str] = None
    linked_from_event_id: Optional[str] = None
    time_delta_days: Optional[float] = None
    distance_km: Optional[float] = None


class ContextDocument(BaseModel):
    doc_id: str
    title: str = ""
    context_type: str
    analysis_type: Optional[str] = None
    text: str = ""


class CitationAuditRecord(BaseModel):
    citation_id: str
    raw: str
    valid: bool
    evidence_role: Optional[str] = None
    source_type: Optional[str] = None
    context_type: Optional[str] = None
    covered_source_types: List[str] = Field(default_factory=list)
    title: Optional[str] = None
    detail: str = ""


class AnswerAudit(BaseModel):
    trust_level: str = "weak"
    trust_score: float = 0.0
    citation_count: int = 0
    valid_citation_count: int = 0
    invalid_citation_count: int = 0
    cited_source_types: List[str] = Field(default_factory=list)
    expected_source_types: List[str] = Field(default_factory=list)
    retrieved_source_types: List[str] = Field(default_factory=list)
    missing_expected_citations: List[str] = Field(default_factory=list)
    primary_sources_cited: int = 0
    linked_sources_cited: int = 0
    analysis_context_cited: int = 0
    reliability_context_cited: int = 0
    unused_linked_sources: List[str] = Field(default_factory=list)
    citation_requirements: Dict[str, Any] = Field(default_factory=dict)
    invalid_citations: List[CitationAuditRecord] = Field(default_factory=list)
    citations: List[CitationAuditRecord] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class RetrieveResponse(BaseModel):
    query: str
    sources: List[SourceDocument]
    linked_sources: List[SourceDocument] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    interaction_id: Optional[uuid.UUID] = None
    query: str
    answer: str
    sources: List[SourceDocument]
    analysis_context: List[ContextDocument] = Field(default_factory=list)
    reliability_context: List[ContextDocument] = Field(default_factory=list)
    linked_sources: List[SourceDocument] = Field(default_factory=list)
    model: str
    n_sources: int
    n_linked_sources: int = 0
    n_context_documents: int = 0
    prompt_diagnostics: Dict[str, Any] = Field(default_factory=dict)
    retrieval_diagnostics: Dict[str, Any] = Field(default_factory=dict)
    answer_audit: Optional[AnswerAudit] = None
    options: Dict[str, Any] = Field(default_factory=dict)


class ChatFeedbackRequest(BaseModel):
    rating: Literal[-1, 1]
    reason_codes: List[str] = Field(default_factory=list, max_length=8)
    comment: Optional[str] = Field(default=None, max_length=1000)


class ChatFeedbackResponse(BaseModel):
    id: uuid.UUID
    interaction_id: uuid.UUID
    rating: Literal[-1, 1]
    reason_codes: List[str] = Field(default_factory=list)
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AdminFeedbackMetrics(BaseModel):
    total: int
    positive: int
    negative: int
    positive_rate: Optional[float] = None
    reason_counts: Dict[str, int] = Field(default_factory=dict)


class AdminFeedbackListItem(BaseModel):
    feedback_id: uuid.UUID
    interaction_id: uuid.UUID
    rating: Literal[-1, 1]
    reason_codes: List[str] = Field(default_factory=list)
    comment: Optional[str] = None
    feedback_created_at: datetime
    feedback_updated_at: datetime
    query: str
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    interaction_created_at: datetime
    user_id: uuid.UUID
    user_email: str
    user_display_name: Optional[str] = None
    user_role: str
    user_account_type: str


class AdminFeedbackListResponse(BaseModel):
    items: List[AdminFeedbackListItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
    metrics: AdminFeedbackMetrics


class AdminFeedbackDetail(AdminFeedbackListItem):
    interaction_status: str
    answer: Optional[str] = None
    request_options: Dict[str, Any] = Field(default_factory=dict)
    evidence_snapshot: Dict[str, Any] = Field(default_factory=dict)
    answer_audit_snapshot: Optional[Dict[str, Any]] = None
    corpus_fingerprint: Optional[str] = None
    prompt_version: Optional[str] = None
    prompt_sha256: Optional[str] = None


class OllamaModel(BaseModel):
    name: str
    modified_at: Optional[str] = None
    size: Optional[int] = None


class ModelsResponse(BaseModel):
    default_model: str
    embedding_model: str
    provider: str = "ollama"
    ollama_base_url: str
    available: bool
    models: List[OllamaModel] = Field(default_factory=list)
    error: Optional[str] = None


class StatusResponse(BaseModel):
    status: str
    database: Dict[str, Any]
    ollama: Dict[str, Any]
    artifacts: Dict[str, Any]


class CorpusStats(BaseModel):
    documents: Dict[str, int]
    samples: int
    ctd_casts: int
    sst_days: int
    analysis_docs: int
    reliability_docs: int
    provenance_records: int


class DatasetCatalogItem(BaseModel):
    id: str
    label: str
    row_count: int
    columns: List[str]
    date_columns: List[str] = []
    numeric_columns: List[str] = []
    default_columns: List[str] = []
    default_x: Optional[str] = None
    default_y: Optional[str] = None
    filters: Dict[str, str] = {}


class ExploreTableResponse(BaseModel):
    dataset: str
    total: int
    filtered: int
    limit: int
    offset: int
    columns: List[str]
    rows: List[Dict[str, Any]]


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    non_null: int
    missing: int
    unique: int
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    mean_value: Optional[float] = None


class ExploreSummaryResponse(BaseModel):
    dataset: str
    total_rows: int
    filtered_rows: int
    columns: List[str]
    numeric_columns: List[str]
    date_columns: List[str]
    profiles: List[ColumnProfile]


class TimeSeriesPoint(BaseModel):
    x: str
    y: float
    sample_id: Optional[str] = None
    bay: Optional[str] = None
    source: Optional[str] = None


class TimeSeriesResponse(BaseModel):
    dataset: str
    x_column: str
    y_column: str
    points: List[TimeSeriesPoint]


class SampleDetailResponse(BaseModel):
    sample_id: str
    registry: Optional[Dict[str, Any]] = None
    ctd: List[Dict[str, Any]] = []
    diversity: List[Dict[str, Any]] = []
    reliability: List[Dict[str, Any]] = []
    documents: List[SourceDocument] = []


class DataCatalogResponse(BaseModel):
    ctd_samples: List[str]
    taxa_samples: List[str]
    ctd_variables: List[str]
    sst_observations: int
    sst_days: int
    context_rows: int


class CtdProfileResponse(BaseModel):
    sample_id: str
    summary: Optional[Dict[str, Any]] = None
    variables: List[str]
    rows: List[Dict[str, Any]]


class TaxaEntry(BaseModel):
    label: str
    value: float


class TaxaSampleResponse(BaseModel):
    sample_id: str
    context: Optional[Dict[str, Any]] = None
    kraken_top: List[TaxaEntry] = []
    metaeuk_top: List[TaxaEntry] = []
    upper_groups: List[TaxaEntry] = []


class SstPoint(BaseModel):
    time_jst: str
    sst: float


class SstDailyPoint(BaseModel):
    date_jst: str
    mean_sst: Optional[float] = None
    min_sst: Optional[float] = None
    max_sst: Optional[float] = None


class SstDataResponse(BaseModel):
    observations: int
    days: int
    stats: Dict[str, Any]
    points: List[SstPoint]
    daily: List[SstDailyPoint]


class AnalysisResponse(BaseModel):
    catalog: Dict[str, Any]
    ctd_trends: Dict[str, Any]
    correlations: Dict[str, Any]
    diversity: Dict[str, Any]
    cooccurrence: Dict[str, Any]
    reliability: Dict[str, Any]


class DatabaseSchemaResponse(BaseModel):
    available: bool
    version: Optional[str] = None
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class DatabaseTableResponse(BaseModel):
    table: str
    total: int
    limit: int
    offset: int
    columns: List[str]
    rows: List[Dict[str, Any]]


class PipelineStageInfo(BaseModel):
    id: str
    label: str
    description: str
    command: List[str]
    expected_inputs: List[str] = Field(default_factory=list)
    expected_outputs: List[str] = Field(default_factory=list)
    destructive: bool = False
    expensive: bool = False


class PipelineArtifactInfo(BaseModel):
    id: str
    label: str
    path: str
    exists: bool
    is_file: bool = False
    is_dir: bool = False
    size_bytes: Optional[int] = None
    rows: Optional[int] = None
    modified_at: Optional[str] = None
    note: Optional[str] = None


class PipelineArtifactFreshness(BaseModel):
    id: str
    label: str
    kind: str
    path: str
    exists: bool
    freshness_status: str
    lineage_status: str
    age_days: Optional[float] = None
    modified_at: Optional[str] = None
    latest_raw_modified_at: Optional[str] = None
    rows: Optional[int] = None
    size_bytes: Optional[int] = None
    note: Optional[str] = None


class PipelinePreflightCheck(BaseModel):
    id: str
    label: str
    status: str
    severity: str = "info"
    required: bool = False
    detail: str = ""


class PipelinePreflightResponse(BaseModel):
    generated_at: str
    ok: bool
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    request: Dict[str, Any] = Field(default_factory=dict)
    checks: List[PipelinePreflightCheck] = Field(default_factory=list)
    command_plan: List[Dict[str, Any]] = Field(default_factory=list)
    raw_sources: List[PipelineArtifactInfo] = Field(default_factory=list)
    artifacts: List[PipelineArtifactInfo] = Field(default_factory=list)
    database: Dict[str, Any] = Field(default_factory=dict)
    ollama: Dict[str, Any] = Field(default_factory=dict)


class PipelineStatusResponse(BaseModel):
    stages: List[PipelineStageInfo]
    raw_sources: List[PipelineArtifactInfo]
    artifacts: List[PipelineArtifactInfo]
    artifact_freshness: List[PipelineArtifactFreshness] = Field(default_factory=list)
    readiness: Dict[str, Any]
    database: Dict[str, Any]
    ollama: Dict[str, Any]
    active_jobs: List[Dict[str, Any]] = Field(default_factory=list)
    pipeline_runs: int = 0


class PipelineRunRequest(BaseModel):
    stages: List[str] = Field(..., min_length=1)
    tag: Optional[str] = None
    dry_run: bool = True
    skip_sst: bool = False
    reset_database: bool = False
    reset_confirmation: Optional[str] = Field(default=None, max_length=64)
    embed_after_load: bool = True
    embedding_model: Optional[str] = None
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    notes: Optional[str] = None


class PipelineStartResponse(BaseModel):
    job_id: str
    run_id: str
    status: str
    status_url: str


class PipelineJobStatus(BaseModel):
    job_id: str
    run_id: str
    status: str
    current: int = 0
    total: int = 0
    percent: float = 0.0
    phase: str = "queued"
    stage_id: Optional[str] = None
    message: str = ""
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    output_dir: Optional[str] = None
    log_path: Optional[str] = None
    stages: List[str] = Field(default_factory=list)
    result_run_id: Optional[str] = None


class PipelineStageLog(BaseModel):
    stage_id: str
    label: Optional[str] = None
    command: Optional[str] = None
    status: Optional[str] = None
    return_code: Optional[int] = None
    duration_seconds: Optional[float] = None
    line_count: int = 0
    bytes: int = 0
    log: str = ""


class PipelineLogResponse(BaseModel):
    job_id: str
    log_path: str
    log: str
    bytes: int
    stage_logs: List[PipelineStageLog] = Field(default_factory=list)


class PipelineRunSummary(BaseModel):
    run_id: str
    job_id: Optional[str] = None
    status: str = "unknown"
    tag: Optional[str] = None
    dry_run: bool = False
    stages: List[str] = Field(default_factory=list)
    stage_count: int = 0
    failed_stage: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    output_dir: Optional[str] = None
    manifest_path: Optional[str] = None
    log_path: Optional[str] = None
    error: Optional[str] = None


class PipelineRunsResponse(BaseModel):
    runs: List[PipelineRunSummary] = Field(default_factory=list)


class PipelineRunDetailResponse(BaseModel):
    summary: PipelineRunSummary
    manifest: Dict[str, Any] = Field(default_factory=dict)
    progress: Dict[str, Any] = Field(default_factory=dict)
    log_tail: str = ""
    stage_logs: List[PipelineStageLog] = Field(default_factory=list)


class ProvenanceManifestResponse(BaseModel):
    schema_version: int
    generated_at: str
    project_root: str
    summary: Dict[str, Any] = Field(default_factory=dict)
    source_files: List[Dict[str, Any]] = Field(default_factory=list)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    embeddings: List[Dict[str, Any]] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class ProvenanceTraceResponse(BaseModel):
    doc_id: str
    found: bool
    trace: Dict[str, Any] = Field(default_factory=dict)


class UpsertDryRunResponse(BaseModel):
    generated_at: str
    dry_run: bool = True
    ok: bool
    database: Dict[str, Any] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)
    lineage_manifest_summary: Dict[str, Any] = Field(default_factory=dict)
    table_plans: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class EvaluationQuestion(BaseModel):
    id: str
    category: str
    question: str
    expected_source_types: List[str]
    expected_min_citations: int
    requires_analysis: bool = False
    requires_reliability: bool = False
    reference_answer: Optional[str] = None
    key_facts: List[str] = Field(default_factory=list)
    expected_citation_patterns: List[str] = Field(default_factory=list)


class EvaluationModeInfo(BaseModel):
    name: str
    inject_analysis: bool = False
    inject_reliability: bool = False


class EvaluationVariantInfo(BaseModel):
    name: str
    source_coverage: int
    inject_analysis: bool = False
    inject_reliability: bool = False
    description: str = ""


class EvaluationCatalogResponse(BaseModel):
    questions: List[EvaluationQuestion]
    categories: List[str]
    modes: List[EvaluationModeInfo]
    variants: List[EvaluationVariantInfo]
    metrics: List[Dict[str, str]]
    quality_metrics: List[Dict[str, str]]


class EvaluationRunControlBase(BaseModel):
    model: Optional[str] = None
    tag: Optional[str] = None
    quick: bool = True
    question_ids: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=25)
    num_ctx: int = Field(default=8192, ge=512, le=32768)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    run_quality: bool = False
    run_judge: bool = False
    judge_model: Optional[str] = None
    embedding_model: Optional[str] = None


class EvaluationStandardRunRequest(EvaluationRunControlBase):
    modes: List[str] = Field(default_factory=list)


class EvaluationAblationRunRequest(EvaluationRunControlBase):
    variants: List[str] = Field(default_factory=list)
    repeats: int = Field(default=1, ge=1, le=5)


class EvaluationStartResponse(BaseModel):
    job_id: str
    run_id: str
    status: str
    status_url: str


class EvaluationJobStatus(BaseModel):
    job_id: str
    run_id: str
    run_type: str
    status: str
    current: int = 0
    total: int = 0
    percent: float = 0.0
    phase: str = "queued"
    message: str = ""
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    output_dir: Optional[str] = None
    result_run_id: Optional[str] = None


class EvaluationRunSummary(BaseModel):
    run_id: str
    run_type: str
    path: str
    csv_path: str
    meta_path: Optional[str] = None
    report_path: Optional[str] = None
    model: Optional[str] = None
    tag: Optional[str] = None
    timestamp: Optional[str] = None
    status: str = "complete"
    n_evaluations: int = 0
    n_questions: int = 0
    n_modes: int = 0
    n_errors: int = 0
    modes: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    has_quality_metrics: bool = False
    has_report: bool = False
    metrics: Dict[str, Any] = Field(default_factory=dict)


class EvaluationRunsResponse(BaseModel):
    runs: List[EvaluationRunSummary]


class EvaluationRunDetailResponse(BaseModel):
    run: EvaluationRunSummary
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    limit: int
    offset: int
    summary: Dict[str, Any]


class EvaluationAnalyticsResponse(BaseModel):
    run: EvaluationRunSummary
    selected_metric: str
    baseline_mode: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    metric_catalog: List[Dict[str, Any]] = Field(default_factory=list)
    by_mode: List[Dict[str, Any]] = Field(default_factory=list)
    by_category: List[Dict[str, Any]] = Field(default_factory=list)
    by_mode_category: List[Dict[str, Any]] = Field(default_factory=list)
    mode_category_matrix: Dict[str, Any] = Field(default_factory=dict)
    metric_distributions: List[Dict[str, Any]] = Field(default_factory=list)
    quality_by_mode: List[Dict[str, Any]] = Field(default_factory=list)
    latency_by_mode: List[Dict[str, Any]] = Field(default_factory=list)
    citation_by_mode: List[Dict[str, Any]] = Field(default_factory=list)
    source_coverage_by_mode: List[Dict[str, Any]] = Field(default_factory=list)
    lowest_scoring_questions: List[Dict[str, Any]] = Field(default_factory=list)
    highest_latency_questions: List[Dict[str, Any]] = Field(default_factory=list)
    best_by_metric: List[Dict[str, Any]] = Field(default_factory=list)
    statistical_tests: Dict[str, Any] = Field(default_factory=dict)


class EvaluationReportResponse(BaseModel):
    run_id: str
    markdown: str


class EvaluationCompareRequest(BaseModel):
    run_ids: List[str] = Field(..., min_length=2, max_length=8)


class EvaluationCompareResponse(BaseModel):
    run_ids: List[str]
    runs: List[EvaluationRunSummary]
    markdown: str
    by_mode: List[Dict[str, Any]]
