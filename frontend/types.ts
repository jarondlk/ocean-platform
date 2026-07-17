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
  query: string;
  answer: string;
  sources: SourceDocument[];
  model: string;
  n_sources: number;
  options: Record<string, unknown>;
};

export type OllamaModel = {
  name: string;
  modified_at?: string | null;
  size?: number | null;
};

export type ModelsResponse = {
  default_model: string;
  embedding_model: string;
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

export type DatabaseQueryResponse = {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  elapsed_ms: number;
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

export type PipelineStatusResponse = {
  stages: PipelineStageInfo[];
  raw_sources: PipelineArtifactInfo[];
  artifacts: PipelineArtifactInfo[];
  readiness: Record<string, unknown>;
  database: Record<string, unknown>;
  ollama: Record<string, unknown>;
  pipeline_runs: number;
};

export type PipelineRunRequest = {
  stages: string[];
  tag?: string;
  dry_run: boolean;
  skip_sst: boolean;
  reset_database: boolean;
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
