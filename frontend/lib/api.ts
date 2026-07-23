import type {
  AdminFeedbackDetail,
  AdminFeedbackListResponse,
  AnalysisResponse,
  ChatFeedback,
  ChatResponse,
  CorpusStats,
  CtdProfileResponse,
  DataCatalogResponse,
  DatabaseSchemaResponse,
  DatabaseTableResponse,
  DebugState,
  DatasetCatalogItem,
  EvaluationAnalyticsResponse,
  EvaluationCatalogResponse,
  EvaluationAblationRunRequest,
  EvaluationCompareResponse,
  EvaluationJobStatus,
  EvaluationReportResponse,
  EvaluationRunDetailResponse,
  EvaluationRunsResponse,
  EvaluationStandardRunRequest,
  EvaluationStartResponse,
  ExploreSummaryResponse,
  ExploreTableResponse,
  ModelsResponse,
  PipelineJobStatus,
  PipelineLogResponse,
  PipelinePreflightResponse,
  PipelineRunDetailResponse,
  PipelineRunRequest,
  PipelineRunsResponse,
  PipelineStartResponse,
  PipelineStatusResponse,
  ProvenanceManifestResponse,
  ProvenanceTraceResponse,
  RetrieveResponse,
  SampleDetailResponse,
  SourceDocument,
  SstDataResponse,
  StatusResponse,
  TaxaSampleResponse,
  TimeSeriesResponse,
  UpsertDryRunResponse,
  UserInvitation,
  UserSummary,
} from "@/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_PROXY_BASE_URL ||
  "/api/backend";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }

  return response.json() as Promise<T>;
}

async function responseErrorMessage(response: Response): Promise<string> {
  const body = await response.text();
  let message = body;
  try {
    const payload = JSON.parse(body) as {
      detail?: string | { message?: string };
    };
    if (typeof payload.detail === "string") {
      message = payload.detail;
    } else if (payload.detail?.message) {
      message = payload.detail.message;
    }
  } catch {
    // Preserve a non-JSON response body as the most useful error message.
  }
  return message || `Request failed with ${response.status}`;
}

export async function getStatus(): Promise<StatusResponse> {
  return request<StatusResponse>("/health");
}

export async function getStats(): Promise<CorpusStats> {
  return request<CorpusStats>("/stats");
}

export async function getModels(): Promise<ModelsResponse> {
  return request<ModelsResponse>("/models");
}

export async function getUsers(): Promise<UserSummary[]> {
  return request<UserSummary[]>("/admin/users");
}

export async function getInvitations(): Promise<UserInvitation[]> {
  return request<UserInvitation[]>("/admin/invitations");
}

export async function createInvitation(input: {
  email: string;
  role: UserSummary["role"];
  account_type: UserSummary["account_type"];
  expires_in_days?: number;
}): Promise<UserInvitation> {
  return request<UserInvitation>("/admin/invitations", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateUser(
  userId: string,
  input: Partial<Pick<UserSummary, "role" | "account_type" | "status">>,
): Promise<UserSummary> {
  return request<UserSummary>(`/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export type AdminFeedbackFilters = {
  rating?: -1 | 1;
  reason_code?: string;
  date_from?: string;
  date_to?: string;
  model?: string;
  role?: UserSummary["role"];
  account_type?: UserSummary["account_type"];
  search?: string;
};

export async function getAdminFeedback(
  filters: AdminFeedbackFilters & { limit?: number; offset?: number },
): Promise<AdminFeedbackListResponse> {
  return request<AdminFeedbackListResponse>(
    `/admin/feedback?${searchParams(filters)}`,
  );
}

export async function getAdminFeedbackDetail(
  feedbackId: string,
): Promise<AdminFeedbackDetail> {
  return request<AdminFeedbackDetail>(
    `/admin/feedback/${encodeURIComponent(feedbackId)}`,
  );
}

export async function downloadAdminFeedbackCsv(
  filters: AdminFeedbackFilters,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(
    `${API_BASE_URL}/admin/feedback/export?${searchParams(filters)}`,
    { cache: "no-store" },
  );
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const filenameMatch = disposition.match(/filename="([^"]+)"/);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] || "chat-feedback.csv",
  };
}

export async function getDocuments(params: {
  q?: string;
  source_type?: string;
  bay?: string;
  time_from?: string;
  time_to?: string;
  limit?: number;
}): Promise<SourceDocument[]> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  });
  return request<SourceDocument[]>(`/documents?${search.toString()}`);
}

export async function askQuestion(input: {
  query: string;
  k: number;
  source_type?: string;
  bay?: string;
  time_from?: string;
  time_to?: string;
  vector_weight?: number;
  fts_weight?: number;
  rrf_k?: number;
  expand_evidence?: boolean;
  max_linked_sources?: number;
  model?: string;
  inject_analysis?: boolean;
  inject_reliability?: boolean;
  run_answer_audit?: boolean;
  temperature?: number;
  top_p?: number;
  repeat_penalty?: number;
  num_ctx?: number;
  num_predict?: number;
  sampling_top_k?: number;
  seed?: number;
}): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function putChatFeedback(
  interactionId: string,
  input: {
    rating: -1 | 1;
    reason_codes: string[];
    comment?: string;
  },
): Promise<ChatFeedback> {
  return request<ChatFeedback>(
    `/chat/interactions/${encodeURIComponent(interactionId)}/feedback`,
    {
      method: "PUT",
      body: JSON.stringify(input),
    },
  );
}

export async function getChatFeedback(
  interactionId: string,
): Promise<ChatFeedback | null> {
  return request<ChatFeedback | null>(
    `/chat/interactions/${encodeURIComponent(interactionId)}/feedback`,
  );
}

export async function retrieveSources(input: {
  query: string;
  k?: number;
  source_type?: string;
  bay?: string;
  time_from?: string;
  time_to?: string;
  vector_weight?: number;
  fts_weight?: number;
  rrf_k?: number;
  expand_evidence?: boolean;
  max_linked_sources?: number;
}): Promise<RetrieveResponse> {
  return request<RetrieveResponse>("/retrieve", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

type ExploreParams = {
  dataset: string;
  bay?: string;
  station?: string;
  source?: string;
  time_from?: string;
  time_to?: string;
  search?: string;
};

function searchParams(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });
  return search.toString();
}

export async function getExploreCatalog(): Promise<DatasetCatalogItem[]> {
  return request<DatasetCatalogItem[]>("/explore/catalog");
}

export async function getExploreTable(
  params: ExploreParams & {
    limit?: number;
    offset?: number;
    sort?: string;
    direction?: "asc" | "desc";
    columns?: string;
  },
): Promise<ExploreTableResponse> {
  return request<ExploreTableResponse>(`/explore/table?${searchParams(params)}`);
}

export async function getExploreSummary(
  params: ExploreParams,
): Promise<ExploreSummaryResponse> {
  return request<ExploreSummaryResponse>(`/explore/summary?${searchParams(params)}`);
}

export async function getExploreTimeseries(
  params: ExploreParams & {
    x_column?: string;
    y_column?: string;
    limit?: number;
  },
): Promise<TimeSeriesResponse> {
  return request<TimeSeriesResponse>(`/explore/timeseries?${searchParams(params)}`);
}

export async function getSampleDetail(sampleId: string): Promise<SampleDetailResponse> {
  return request<SampleDetailResponse>(`/explore/sample/${encodeURIComponent(sampleId)}`);
}

export async function getDebugState(): Promise<DebugState> {
  return request<DebugState>("/debug");
}

export async function getDataCatalog(): Promise<DataCatalogResponse> {
  return request<DataCatalogResponse>("/data/catalog");
}

export async function getCtdProfile(sampleId: string): Promise<CtdProfileResponse> {
  return request<CtdProfileResponse>(`/data/ctd-profile/${encodeURIComponent(sampleId)}`);
}

export async function getTaxaSample(sampleId: string): Promise<TaxaSampleResponse> {
  return request<TaxaSampleResponse>(`/data/taxa/${encodeURIComponent(sampleId)}`);
}

export async function getSstData(params: {
  time_from?: string;
  time_to?: string;
  limit?: number;
}): Promise<SstDataResponse> {
  return request<SstDataResponse>(`/data/sst?${searchParams(params)}`);
}

export async function getAnalysis(params: {
  cooccurrence_pairs?: number;
  table_limit?: number;
} = {}): Promise<AnalysisResponse> {
  return request<AnalysisResponse>(`/analysis?${searchParams(params)}`);
}

export async function getDatabaseSchema(): Promise<DatabaseSchemaResponse> {
  return request<DatabaseSchemaResponse>("/database/schema");
}

export async function getDatabaseTable(params: {
  table: string;
  limit?: number;
  offset?: number;
  order_by?: string;
  direction?: "asc" | "desc";
  include_heavy?: boolean;
}): Promise<DatabaseTableResponse> {
  return request<DatabaseTableResponse>(`/database/table?${searchParams(params)}`);
}

export async function getPipelineStatus(): Promise<PipelineStatusResponse> {
  return request<PipelineStatusResponse>("/pipeline/status");
}

export async function getPipelinePreflight(input: PipelineRunRequest): Promise<PipelinePreflightResponse> {
  return request<PipelinePreflightResponse>("/pipeline/preflight", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getPipelineRuns(limit = 50): Promise<PipelineRunsResponse> {
  return request<PipelineRunsResponse>(`/pipeline/runs?${searchParams({ limit })}`);
}

export async function getPipelineRun(runId: string, limitBytes = 50000): Promise<PipelineRunDetailResponse> {
  return request<PipelineRunDetailResponse>(`/pipeline/runs/${encodeURIComponent(runId)}?${searchParams({ limit_bytes: limitBytes })}`);
}

export async function startPipelineJob(input: PipelineRunRequest): Promise<PipelineStartResponse> {
  return request<PipelineStartResponse>("/pipeline/jobs", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getPipelineJob(jobId: string): Promise<PipelineJobStatus> {
  return request<PipelineJobStatus>(`/pipeline/jobs/${encodeURIComponent(jobId)}`);
}

export async function getPipelineJobLog(jobId: string, limitBytes = 30000): Promise<PipelineLogResponse> {
  return request<PipelineLogResponse>(`/pipeline/jobs/${encodeURIComponent(jobId)}/log?${searchParams({ limit_bytes: limitBytes })}`);
}

export async function cancelPipelineJob(jobId: string): Promise<PipelineJobStatus> {
  return request<PipelineJobStatus>(`/pipeline/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function getProvenanceManifest(params: {
  limit_documents?: number;
  include_embeddings?: boolean;
} = {}): Promise<ProvenanceManifestResponse> {
  return request<ProvenanceManifestResponse>(`/provenance/manifest?${searchParams(params)}`);
}

export async function getProvenanceTrace(docId: string): Promise<ProvenanceTraceResponse> {
  return request<ProvenanceTraceResponse>(`/provenance/trace/${encodeURIComponent(docId)}`);
}

export async function getProvenanceUpsertDryRun(limitKeys = 25): Promise<UpsertDryRunResponse> {
  return request<UpsertDryRunResponse>(`/provenance/upsert-dry-run?${searchParams({ limit_keys: limitKeys })}`);
}

export async function getEvaluationCatalog(): Promise<EvaluationCatalogResponse> {
  return request<EvaluationCatalogResponse>("/evaluation/catalog");
}

export async function getEvaluationPreflight(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/evaluation/preflight");
}

export async function getEvaluationRuns(): Promise<EvaluationRunsResponse> {
  return request<EvaluationRunsResponse>("/evaluation/runs");
}

export async function startStandardEvaluation(input: EvaluationStandardRunRequest): Promise<EvaluationStartResponse> {
  return request<EvaluationStartResponse>("/evaluation/runs/standard", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function startAblationEvaluation(input: EvaluationAblationRunRequest): Promise<EvaluationStartResponse> {
  return request<EvaluationStartResponse>("/evaluation/runs/ablation", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getEvaluationJob(jobId: string): Promise<EvaluationJobStatus> {
  return request<EvaluationJobStatus>(`/evaluation/jobs/${encodeURIComponent(jobId)}`);
}

export async function cancelEvaluationJob(jobId: string): Promise<EvaluationJobStatus> {
  return request<EvaluationJobStatus>(`/evaluation/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function getEvaluationRun(params: {
  run_id: string;
  limit?: number;
  offset?: number;
  mode?: string;
  category?: string;
  question_id?: string;
}): Promise<EvaluationRunDetailResponse> {
  const { run_id, ...query } = params;
  return request<EvaluationRunDetailResponse>(`/evaluation/runs/${encodeURIComponent(run_id)}?${searchParams(query)}`);
}

export async function getEvaluationAnalytics(params: {
  run_id: string;
  metric?: string;
  baseline_mode?: string;
  category?: string;
}): Promise<EvaluationAnalyticsResponse> {
  const { run_id, ...query } = params;
  return request<EvaluationAnalyticsResponse>(`/evaluation/runs/${encodeURIComponent(run_id)}/analytics?${searchParams(query)}`);
}

export async function getEvaluationReport(runId: string): Promise<EvaluationReportResponse> {
  return request<EvaluationReportResponse>(`/evaluation/runs/${encodeURIComponent(runId)}/report`);
}

export async function compareEvaluationRuns(runIds: string[]): Promise<EvaluationCompareResponse> {
  return request<EvaluationCompareResponse>("/evaluation/compare", {
    method: "POST",
    body: JSON.stringify({ run_ids: runIds }),
  });
}
