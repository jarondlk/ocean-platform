export type CurrentUser = {
  id: string;
  email: string;
  display_name?: string | null;
  role: "viewer" | "researcher" | "admin";
  account_type: "research" | "commercial" | "internal";
  status: "active" | "suspended";
  permissions: string[];
};

export type UserSummary = {
  id: string;
  email: string;
  display_name?: string | null;
  role: "viewer" | "researcher" | "admin";
  account_type: "research" | "commercial" | "internal";
  status: "active" | "suspended";
  auth_provider: string;
  created_at: string;
  last_login_at?: string | null;
};

export type UserInvitation = {
  id: string;
  email: string;
  role: "viewer" | "researcher" | "admin";
  account_type: "research" | "commercial" | "internal";
  status: "pending" | "accepted" | "revoked" | "expired";
  expires_at: string;
  accepted_at?: string | null;
  created_at: string;
};

export type SourceDocument = {
  doc_id: string;
  title: string;
  source_type: string;
  sample_id?: string | null;
  event_id?: string | null;
  time?: string | null;
  bay?: string | null;
  station?: string | null;
  text: string;
  score?: number | null;
  rank_sources?: Record<string, number>;
  retrieval_role?: string;
  link_type?: string | null;
  linked_from_doc_id?: string | null;
  linked_from_event_id?: string | null;
  time_delta_days?: number | null;
  distance_km?: number | null;
};

export type ContextDocument = {
  doc_id: string;
  title: string;
  context_type: string;
  analysis_type?: string | null;
  text: string;
};

export type CitationAuditRecord = {
  citation_id: string;
  raw: string;
  valid: boolean;
  evidence_role?: string | null;
  source_type?: string | null;
  context_type?: string | null;
  covered_source_types: string[];
  title?: string | null;
  detail: string;
};

export type AnswerAudit = {
  trust_level: string;
  trust_score: number;
  citation_count: number;
  valid_citation_count: number;
  invalid_citation_count: number;
  cited_source_types: string[];
  expected_source_types: string[];
  retrieved_source_types: string[];
  missing_expected_citations: string[];
  primary_sources_cited: number;
  linked_sources_cited: number;
  analysis_context_cited: number;
  reliability_context_cited: number;
  unused_linked_sources: string[];
  citation_requirements: Record<string, unknown>;
  invalid_citations: CitationAuditRecord[];
  citations: CitationAuditRecord[];
  warnings: string[];
};

export type StatusResponse = {
  status: string;
  database: Record<string, unknown>;
  ollama: Record<string, unknown>;
  artifacts: Record<string, unknown>;
};

export type CorpusStats = {
  documents: Record<string, number>;
  samples: number;
  ctd_casts: number;
  sst_days: number;
  analysis_docs: number;
  reliability_docs: number;
  provenance_records: number;
};

export type ChatResponse = {
  interaction_id?: string | null;
  query: string;
  answer: string;
  sources: SourceDocument[];
  linked_sources: SourceDocument[];
  analysis_context: ContextDocument[];
  reliability_context: ContextDocument[];
  model: string;
  n_sources: number;
  n_linked_sources: number;
  n_context_documents: number;
  prompt_diagnostics: Record<string, unknown>;
  retrieval_diagnostics: Record<string, unknown>;
  answer_audit?: AnswerAudit | null;
  options: Record<string, unknown>;
};

export type ChatFeedback = {
  id: string;
  interaction_id: string;
  rating: -1 | 1;
  reason_codes: string[];
  comment?: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminFeedbackMetrics = {
  total: number;
  positive: number;
  negative: number;
  positive_rate?: number | null;
  reason_counts: Record<string, number>;
};

export type AdminFeedbackListItem = {
  feedback_id: string;
  interaction_id: string;
  rating: -1 | 1;
  reason_codes: string[];
  comment?: string | null;
  feedback_created_at: string;
  feedback_updated_at: string;
  query: string;
  model?: string | null;
  latency_ms?: number | null;
  interaction_created_at: string;
  user_id: string;
  user_email: string;
  user_display_name?: string | null;
  user_role: CurrentUser["role"];
  user_account_type: CurrentUser["account_type"];
};

export type AdminFeedbackListResponse = {
  items: AdminFeedbackListItem[];
  total: number;
  limit: number;
  offset: number;
  metrics: AdminFeedbackMetrics;
};

export type AdminFeedbackDetail = AdminFeedbackListItem & {
  interaction_status: "running" | "completed" | "failed";
  answer?: string | null;
  request_options: Record<string, unknown>;
  evidence_snapshot: Record<string, unknown>;
  answer_audit_snapshot?: Record<string, unknown> | null;
  corpus_fingerprint?: string | null;
  prompt_version?: string | null;
  prompt_sha256?: string | null;
};

export type RetrieveResponse = {
  query: string;
  sources: SourceDocument[];
  linked_sources: SourceDocument[];
  diagnostics: Record<string, unknown>;
};

export type OllamaModel = {
  name: string;
  modified_at?: string | null;
  size?: number | null;
};

export type ModelsResponse = {
  default_model: string;
  embedding_model: string;
  provider: string;
  ollama_base_url: string;
  available: boolean;
  models: OllamaModel[];
  error?: string | null;
};

export type DatasetCatalogItem = {
  id: string;
  label: string;
  row_count: number;
  columns: string[];
  date_columns: string[];
  numeric_columns: string[];
  default_columns: string[];
  default_x?: string | null;
  default_y?: string | null;
  filters: Record<string, string>;
};

export type ExploreTableResponse = {
  dataset: string;
  total: number;
  filtered: number;
  limit: number;
  offset: number;
  columns: string[];
  rows: Record<string, unknown>[];
};

export type ColumnProfile = {
  name: string;
  dtype: string;
  non_null: number;
  missing: number;
  unique: number;
  min_value?: unknown;
  max_value?: unknown;
  mean_value?: number | null;
};

export type ExploreSummaryResponse = {
  dataset: string;
  total_rows: number;
  filtered_rows: number;
  columns: string[];
  numeric_columns: string[];
  date_columns: string[];
  profiles: ColumnProfile[];
};

export type TimeSeriesPoint = {
  x: string;
  y: number;
  sample_id?: string | null;
  bay?: string | null;
  source?: string | null;
};

export type TimeSeriesResponse = {
  dataset: string;
  x_column: string;
  y_column: string;
  points: TimeSeriesPoint[];
};

export type SampleDetailResponse = {
  sample_id: string;
  registry?: Record<string, unknown> | null;
  ctd: Record<string, unknown>[];
  diversity: Record<string, unknown>[];
  reliability: Record<string, unknown>[];
  documents: SourceDocument[];
};

export type DebugState = Record<string, unknown>;

export type DataCatalogResponse = {
  ctd_samples: string[];
  taxa_samples: string[];
  ctd_variables: string[];
  sst_observations: number;
  sst_days: number;
  context_rows: number;
};

export type CtdProfileResponse = {
  sample_id: string;
  summary?: Record<string, unknown> | null;
  variables: string[];
  rows: Record<string, unknown>[];
};

export type TaxaEntry = {
  label: string;
  value: number;
};

export type TaxaSampleResponse = {
  sample_id: string;
  context?: Record<string, unknown> | null;
  kraken_top: TaxaEntry[];
  metaeuk_top: TaxaEntry[];
  upper_groups: TaxaEntry[];
};

export type SstPoint = {
  time_jst: string;
  sst: number;
};

export type SstDailyPoint = {
  date_jst: string;
  mean_sst?: number | null;
  min_sst?: number | null;
  max_sst?: number | null;
};

export type SstDataResponse = {
  observations: number;
  days: number;
  stats: Record<string, unknown>;
  points: SstPoint[];
  daily: SstDailyPoint[];
};

export type AnalysisResponse = {
  catalog: Record<string, unknown>;
  ctd_trends: Record<string, unknown>;
  correlations: Record<string, unknown>;
  diversity: Record<string, unknown>;
  cooccurrence: Record<string, unknown>;
  reliability: Record<string, unknown>;
};

export type DatabaseSchemaResponse = {
  available: boolean;
  version?: string | null;
  tables: Array<Record<string, unknown>>;
  error?: string | null;
};

export type DatabaseTableResponse = {
  table: string;
  total: number;
  limit: number;
  offset: number;
  columns: string[];
  rows: Record<string, unknown>[];
};

export type PipelineStageInfo = {
  id: string;
  label: string;
  description: string;
  command: string[];
  expected_inputs: string[];
  expected_outputs: string[];
  destructive: boolean;
  expensive: boolean;
};

export type PipelineArtifactInfo = {
  id: string;
  label: string;
  path: string;
  exists: boolean;
  is_file: boolean;
  is_dir: boolean;
  size_bytes?: number | null;
  rows?: number | null;
  modified_at?: string | null;
  note?: string | null;
};

export type PipelineArtifactFreshness = {
  id: string;
  label: string;
  kind: string;
  path: string;
  exists: boolean;
  freshness_status: string;
  lineage_status: string;
  age_days?: number | null;
  modified_at?: string | null;
  latest_raw_modified_at?: string | null;
  rows?: number | null;
  size_bytes?: number | null;
  note?: string | null;
};

export type PipelineStatusResponse = {
  stages: PipelineStageInfo[];
  raw_sources: PipelineArtifactInfo[];
  artifacts: PipelineArtifactInfo[];
  artifact_freshness: PipelineArtifactFreshness[];
  readiness: Record<string, unknown>;
  database: Record<string, unknown>;
  ollama: Record<string, unknown>;
  active_jobs: PipelineJobStatus[];
  pipeline_runs: number;
};

export type PipelinePreflightCheck = {
  id: string;
  label: string;
  status: string;
  severity: string;
  required: boolean;
  detail: string;
};

export type PipelinePreflightResponse = {
  generated_at: string;
  ok: boolean;
  blockers: string[];
  warnings: string[];
  request: Record<string, unknown>;
  checks: PipelinePreflightCheck[];
  command_plan: Record<string, unknown>[];
  raw_sources: PipelineArtifactInfo[];
  artifacts: PipelineArtifactInfo[];
  database: Record<string, unknown>;
  ollama: Record<string, unknown>;
};

export type PipelineRunRequest = {
  stages: string[];
  tag?: string;
  dry_run: boolean;
  skip_sst: boolean;
  reset_database: boolean;
  reset_confirmation?: string;
  embed_after_load: boolean;
  embedding_model?: string;
  embedding_batch_size: number;
  notes?: string;
};

export type PipelineStartResponse = {
  job_id: string;
  run_id: string;
  status: string;
  status_url: string;
};

export type PipelineJobStatus = {
  job_id: string;
  run_id: string;
  status: string;
  current: number;
  total: number;
  percent: number;
  phase: string;
  stage_id?: string | null;
  message: string;
  started_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
  output_dir?: string | null;
  log_path?: string | null;
  stages: string[];
  result_run_id?: string | null;
};

export type PipelineLogResponse = {
  job_id: string;
  log_path: string;
  log: string;
  bytes: number;
  stage_logs: PipelineStageLog[];
};

export type PipelineStageLog = {
  stage_id: string;
  label?: string | null;
  command?: string | null;
  status?: string | null;
  return_code?: number | null;
  duration_seconds?: number | null;
  line_count: number;
  bytes: number;
  log: string;
};

export type PipelineRunSummary = {
  run_id: string;
  job_id?: string | null;
  status: string;
  tag?: string | null;
  dry_run: boolean;
  stages: string[];
  stage_count: number;
  failed_stage?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  output_dir?: string | null;
  manifest_path?: string | null;
  log_path?: string | null;
  error?: string | null;
};

export type PipelineRunsResponse = {
  runs: PipelineRunSummary[];
};

export type PipelineRunDetailResponse = {
  summary: PipelineRunSummary;
  manifest: Record<string, unknown>;
  progress: Record<string, unknown>;
  log_tail: string;
  stage_logs: PipelineStageLog[];
};

export type ProvenanceManifestResponse = {
  schema_version: number;
  generated_at: string;
  project_root: string;
  snapshot: Record<string, unknown>;
  summary: Record<string, unknown>;
  source_files: Record<string, unknown>[];
  artifacts: Record<string, unknown>[];
  documents: Record<string, unknown>[];
  embeddings: Record<string, unknown>[];
  limitations: string[];
};

export type ProvenanceTraceResponse = {
  doc_id: string;
  found: boolean;
  snapshot: Record<string, unknown>;
  trace: Record<string, unknown>;
};

export type UpsertDryRunResponse = {
  generated_at: string;
  dry_run: boolean;
  ok: boolean;
  database: Record<string, unknown>;
  summary: Record<string, unknown>;
  lineage_manifest_summary: Record<string, unknown>;
  table_plans: Record<string, unknown>[];
  warnings: string[];
};

export type EvaluationQuestion = {
  id: string;
  category: string;
  question: string;
  expected_source_types: string[];
  expected_min_citations: number;
  requires_analysis: boolean;
  requires_reliability: boolean;
  reference_answer?: string | null;
  key_facts: string[];
  expected_citation_patterns: string[];
};

export type EvaluationModeInfo = {
  name: string;
  inject_analysis: boolean;
  inject_reliability: boolean;
};

export type EvaluationVariantInfo = {
  name: string;
  source_coverage: number;
  inject_analysis: boolean;
  inject_reliability: boolean;
  description: string;
};

export type EvaluationCatalogResponse = {
  questions: EvaluationQuestion[];
  categories: string[];
  modes: EvaluationModeInfo[];
  variants: EvaluationVariantInfo[];
  metrics: Array<Record<string, string>>;
  quality_metrics: Array<Record<string, string>>;
};

export type EvaluationRunControls = {
  model?: string;
  tag?: string;
  quick: boolean;
  question_ids: string[];
  categories: string[];
  top_k: number;
  num_ctx: number;
  temperature: number;
  run_quality: boolean;
  run_judge: boolean;
  judge_model?: string;
  embedding_model?: string;
};

export type EvaluationStandardRunRequest = EvaluationRunControls & {
  modes: string[];
};

export type EvaluationAblationRunRequest = EvaluationRunControls & {
  variants: string[];
  repeats: number;
};

export type EvaluationStartResponse = {
  job_id: string;
  run_id: string;
  status: string;
  status_url: string;
};

export type EvaluationJobStatus = {
  job_id: string;
  run_id: string;
  run_type: string;
  status: string;
  current: number;
  total: number;
  percent: number;
  phase: string;
  message: string;
  started_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
  output_dir?: string | null;
  result_run_id?: string | null;
};

export type EvaluationRunSummary = {
  run_id: string;
  run_type: string;
  path: string;
  csv_path: string;
  meta_path?: string | null;
  report_path?: string | null;
  model?: string | null;
  tag?: string | null;
  timestamp?: string | null;
  status: string;
  n_evaluations: number;
  n_questions: number;
  n_modes: number;
  n_errors: number;
  modes: string[];
  categories: string[];
  has_quality_metrics: boolean;
  has_report: boolean;
  metrics: Record<string, unknown>;
};

export type EvaluationRunsResponse = {
  runs: EvaluationRunSummary[];
};

export type EvaluationRunDetailResponse = {
  run: EvaluationRunSummary;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  limit: number;
  offset: number;
  summary: Record<string, unknown>;
};

export type EvaluationAnalyticsResponse = {
  run: EvaluationRunSummary;
  selected_metric: string;
  baseline_mode?: string | null;
  filters: Record<string, unknown>;
  metric_catalog: Array<Record<string, unknown>>;
  by_mode: Record<string, unknown>[];
  by_category: Record<string, unknown>[];
  by_mode_category: Record<string, unknown>[];
  mode_category_matrix: Record<string, unknown>;
  metric_distributions: Record<string, unknown>[];
  quality_by_mode: Record<string, unknown>[];
  latency_by_mode: Record<string, unknown>[];
  citation_by_mode: Record<string, unknown>[];
  source_coverage_by_mode: Record<string, unknown>[];
  lowest_scoring_questions: Record<string, unknown>[];
  highest_latency_questions: Record<string, unknown>[];
  best_by_metric: Record<string, unknown>[];
  statistical_tests: Record<string, unknown>;
};

export type EvaluationReportResponse = {
  run_id: string;
  markdown: string;
};

export type EvaluationCompareResponse = {
  run_ids: string[];
  runs: EvaluationRunSummary[];
  markdown: string;
  by_mode: Record<string, unknown>[];
};
