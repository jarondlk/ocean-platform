"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { RotateCcw, Send } from "lucide-react";
import { CsvExportButton } from "@/components/CsvExportButton";
import { ChatFeedback } from "@/components/ChatFeedback";
import { DataTable, formatCell } from "@/components/DataTable";
import { MarkdownAnswer } from "@/components/MarkdownAnswer";
import { askQuestion, getModels } from "@/lib/api";
import type { AnswerAudit, ChatResponse, CitationAuditRecord, ContextDocument, ModelsResponse, SourceDocument } from "@/types";
import { SourceTable } from "@/components/SourceTable";
import { useAppPreferences } from "@/lib/preferences";

type ChatSettings = {
  model: string;
  k: number;
  sourceType: string;
  bay: string;
  timeFrom: string;
  timeTo: string;
  vectorWeight: number;
  ftsWeight: number;
  rrfK: number;
  expandEvidence: boolean;
  maxLinkedSources: number;
  injectAnalysis: boolean;
  injectReliability: boolean;
  runAnswerAudit: boolean;
  temperature: number;
  topP: number;
  repeatPenalty: number;
  numCtx: number;
  numPredict: string;
  samplingTopK: string;
  seed: string;
};

const defaultSettings: ChatSettings = {
  model: "",
  k: 8,
  sourceType: "",
  bay: "",
  timeFrom: "",
  timeTo: "",
  vectorWeight: 0.6,
  ftsWeight: 0.4,
  rrfK: 60,
  expandEvidence: true,
  maxLinkedSources: 5,
  injectAnalysis: true,
  injectReliability: true,
  runAnswerAudit: true,
  temperature: 0,
  topP: 0.9,
  repeatPenalty: 1.1,
  numCtx: 8192,
  numPredict: "",
  samplingTopK: "",
  seed: "",
};

const quickQuestions = [
  {
    label: "Temperature Reliability",
    query: "Compare CTD surface temperature and satellite SST reliability in Onagawa Bay.",
  },
  {
    label: "Seasonal CTD Trend",
    query: "What seasonal CTD temperature and salinity patterns are visible across the monitoring period?",
  },
  {
    label: "Taxa-Environment",
    query: "Which taxa show the strongest correlations with temperature, salinity, dissolved oxygen, or chlorophyll?",
  },
  {
    label: "Diversity Anomaly",
    query: "Which samples show anomalous community diversity relative to environmental expectations?",
  },
  {
    label: "Cross-Source Gaps",
    query: "Where do cross-source links or reliability checks reveal gaps, standalone observations, or corroborated evidence?",
  },
];

export default function ChatPage() {
  const { ui } = useAppPreferences();
  const [query, setQuery] = useState("");
  const [settings, setSettings] = useState<ChatSettings>(defaultSettings);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const providerLabel = models?.provider === "vertex" ? "Vertex AI" : models?.provider || "Model runtime";

  useEffect(() => {
    getModels()
      .then((payload) => {
        setModels(payload);
        setSettings((current) => ({
          ...current,
          model: current.model || payload.default_model,
        }));
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const appliedSettings = useMemo(() => {
    if (!response?.options) return null;
    return JSON.stringify(response.options, null, 2);
  }, [response]);
  const contextRows = useMemo(() => {
    if (!response) return [];
    return [
      ...(response.analysis_context || []).map((document) => contextDocumentRow(document)),
      ...(response.reliability_context || []).map((document) => contextDocumentRow(document)),
    ];
  }, [response]);
  const evidenceSources = useMemo(() => {
    if (!response) return [];
    return [...(response.sources || []), ...(response.linked_sources || [])];
  }, [response]);
  const evidenceRows = useMemo(() => evidenceSources.map(sourceDocumentRow), [evidenceSources]);
  const diagnosticRows = useMemo(() => diagnosticsToRows(response?.prompt_diagnostics || {}), [response]);
  const retrievalDiagnosticRows = useMemo(() => diagnosticsToRows(response?.retrieval_diagnostics || {}), [response]);
  const auditCitationRows = useMemo(() => citationAuditRows(response?.answer_audit), [response]);
  const auditRequirementRows = useMemo(() => citationRequirementRows(response?.answer_audit), [response]);
  const auditWarningRows = useMemo(() => warningRows(response?.answer_audit), [response]);
  const promptDiagnostics = response?.prompt_diagnostics || {};
  const retrievalDiagnostics = response?.retrieval_diagnostics || {};
  const answerAudit = response?.answer_audit;
  const missingSourceTypes = formatSourceTypeList(retrievalDiagnostics.missing_source_types);

  function updateSetting<K extends keyof ChatSettings>(key: K, value: ChatSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  function resetControls() {
    setSettings({
      ...defaultSettings,
      model: models?.default_model || defaultSettings.model,
    });
  }

  async function runQuestion(nextQuery: string) {
    const trimmedQuery = nextQuery.trim();
    if (!trimmedQuery || loading) return;
    setQuery(nextQuery);
    setLoading(true);
    setError("");
    setResponse(null);
    try {
      const result = await askQuestion({
        query: trimmedQuery,
        k: settings.k,
        source_type: settings.sourceType || undefined,
        bay: settings.bay || undefined,
        time_from: settings.timeFrom || undefined,
        time_to: settings.timeTo || undefined,
        vector_weight: settings.vectorWeight,
        fts_weight: settings.ftsWeight,
        rrf_k: settings.rrfK,
        expand_evidence: settings.expandEvidence,
        max_linked_sources: settings.maxLinkedSources,
        model: settings.model.trim() || undefined,
        inject_analysis: settings.injectAnalysis,
        inject_reliability: settings.injectReliability,
        run_answer_audit: settings.runAnswerAudit,
        temperature: settings.temperature,
        top_p: settings.topP,
        repeat_penalty: settings.repeatPenalty,
        num_ctx: settings.numCtx,
        num_predict: optionalInteger(settings.numPredict),
        sampling_top_k: optionalInteger(settings.samplingTopK),
        seed: optionalInteger(settings.seed),
      });
      setResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runQuestion(query);
  }

  return (
    <section>
      <header className="page-header">
        <h2>{ui("Query")}</h2>
      </header>

      <form className="chat-form" onSubmit={submit}>
        <div className="chat-layout">
          <section className="chat-main">
            <article className="card">
              <label className="section-label" htmlFor="query-input" title={ui("User question sent to retrieval and the selected chat model.")}>
                {ui("Question")}
              </label>
              <textarea
                id="query-input"
                className="textarea"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label={ui("Question")}
                placeholder={ui("Enter question")}
              />
              <div className="quick-question-grid" aria-label={ui("Quick questions")}>
                {quickQuestions.map((item) => (
                  <button
                    className="button secondary-button quick-question-button"
                    disabled={loading}
                    key={item.label}
                    onClick={() => void runQuestion(item.query)}
                    title={item.query}
                    type="button"
                  >
                    {ui(item.label)}
                  </button>
                ))}
              </div>
              <div className="section-toolbar chat-actions">
                <span className="empty-state">
                  {response ? `${response.n_sources} ${ui("primary")} | ${response.n_linked_sources || 0} ${ui("linked")}` : ui("No response.")}
                </span>
                <button className="button" disabled={loading || !query.trim()}>
                  <Send size={16} aria-hidden="true" />
                  {loading ? ui("Asking") : ui("Ask")}
                </button>
              </div>
              {error ? <p className="error-text">{error}</p> : null}
            </article>

            <article className="card">
              <h3 className="section-title">{ui("Response")}</h3>
              <MarkdownAnswer text={response?.answer || ""} />
              {response?.interaction_id ? (
                <ChatFeedback
                  interactionId={response.interaction_id}
                  key={response.interaction_id}
                />
              ) : null}
            </article>

            {answerAudit ? (
              <article className="card">
                <div className="section-toolbar">
                  <h3 className="section-title">{ui("Trust Report")}</h3>
                  <span className="empty-state">
                    {answerAudit.valid_citation_count} valid | {answerAudit.invalid_citation_count} invalid | {answerAudit.warnings.length} warnings
                  </span>
                </div>

                <div className="summary-strip chat-diagnostics">
                  <SummaryCell label={ui("Trust")} value={titleCase(answerAudit.trust_level)} />
                  <SummaryCell label={ui("Score")} value={formatCoverage(answerAudit.trust_score)} />
                  <SummaryCell label={ui("Citations")} value={answerAudit.citation_count} />
                  <SummaryCell label={ui("Valid")} value={answerAudit.valid_citation_count} />
                  <SummaryCell label={ui("Invalid")} value={answerAudit.invalid_citation_count} />
                  <SummaryCell label={ui("Primary cited")} value={answerAudit.primary_sources_cited} />
                  <SummaryCell label={ui("Linked cited")} value={answerAudit.linked_sources_cited} />
                  <SummaryCell label={ui("Req context")} value={requirementList(answerAudit, "required_context_types") || ui("None")} />
                  <SummaryCell label={ui("Context cited")} value={requirementList(answerAudit, "satisfied_context_types") || ui("None")} />
                  <SummaryCell label={ui("Sources ok")} value={requirementList(answerAudit, "satisfied_source_types") || ui("None")} />
                  <SummaryCell label={ui("Missing req")} value={requirementList(answerAudit, "missing_source_types") || ui("None")} />
                </div>

                <div className="section-toolbar compact-toolbar">
                  <h4 className="subsection-title">{ui("Audit Warnings")}</h4>
                  <CsvExportButton
                    columns={["warning"]}
                    filename="chat_trust_warnings"
                    rows={auditWarningRows}
                  />
                </div>
                <DataTable
                  columns={["warning"]}
                  emptyText="No audit warnings."
                  rows={auditWarningRows}
                  rowKeyColumn="warning"
                />

                <div className="section-toolbar compact-toolbar">
                  <h4 className="subsection-title">{ui("Citation Requirements")}</h4>
                  <CsvExportButton
                    columns={["requirement", "required", "satisfied_by", "status"]}
                    filename="chat_citation_requirements"
                    rows={auditRequirementRows}
                  />
                </div>
                <DataTable
                  columns={["requirement", "required", "satisfied_by", "status"]}
                  emptyText="No inferred citation requirements."
                  rows={auditRequirementRows}
                  rowKeyColumn="_row_key"
                />

                <div className="section-toolbar compact-toolbar">
                  <h4 className="subsection-title">{ui("Citation Resolution")}</h4>
                  <CsvExportButton
                    columns={["citation_id", "raw", "valid", "evidence_role", "source_type", "context_type", "covered_source_types", "title", "detail"]}
                    filename="chat_citation_audit"
                    rows={auditCitationRows}
                  />
                </div>
                <DataTable
                  columns={["citation_id", "raw", "valid", "evidence_role", "source_type", "context_type", "covered_source_types", "title", "detail"]}
                  emptyText="No bracket citations found."
                  rows={auditCitationRows}
                  rowKeyColumn="_row_key"
                />
              </article>
            ) : null}

            {response ? (
              <article className="card">
                <div className="section-toolbar">
                  <h3 className="section-title">{ui("Context Ledger")}</h3>
                  <span className="empty-state">
                    {response.n_sources} primary | {response.n_linked_sources || 0} linked | {(response.n_context_documents || 0)} injected
                  </span>
                </div>

                <div className="summary-strip chat-diagnostics">
                  <SummaryCell label={ui("Model")} value={response.model} />
                  <SummaryCell label={ui("Primary")} value={response.n_sources} />
                  <SummaryCell label={ui("Linked")} value={response.n_linked_sources || 0} />
                  <SummaryCell label={ui("Coverage")} value={formatCoverage(retrievalDiagnostics.source_coverage_ratio)} />
                  <SummaryCell label={ui("Analysis")} value={(response.analysis_context || []).length} />
                  <SummaryCell label={ui("Reliability")} value={(response.reliability_context || []).length} />
                  <SummaryCell label={ui("Prompt chars")} value={formatCell(promptDiagnostics.prompt_chars)} />
                  <SummaryCell label={ui("Missing")} value={missingSourceTypes || ui("None")} />
                </div>

                <div className="section-toolbar compact-toolbar">
                  <h4 className="subsection-title">{ui("Retrieved Evidence")}</h4>
                  <CsvExportButton
                    columns={["retrieval_role", "doc_id", "title", "source_type", "sample_id", "event_id", "time", "bay", "station", "score", "vector_rank", "fts_rank", "link_type", "linked_from_doc_id", "linked_from_event_id", "time_delta_days", "distance_km", "text"]}
                    filename="chat_retrieved_evidence"
                    rows={evidenceRows}
                  />
                </div>
                <SourceTable sources={evidenceSources} />

                <div className="section-toolbar compact-toolbar">
                  <h4 className="subsection-title">{ui("Injected Context")}</h4>
                  <CsvExportButton
                    columns={["context_type", "doc_id", "analysis_type", "title", "text"]}
                    filename="chat_injected_context"
                    rows={contextRows}
                  />
                </div>
                <DataTable
                  columns={["context_type", "doc_id", "analysis_type", "title", "text"]}
                  emptyText="No supplementary context injected."
                  rows={contextRows}
                  rowKeyColumn="doc_id"
                />

                <details className="debug-block chat-debug-block">
                  <summary>{ui("Retrieval Diagnostics")}</summary>
                  <DataTable columns={["key", "value"]} rows={retrievalDiagnosticRows} rowKeyColumn="key" />
                </details>

                <details className="debug-block chat-debug-block">
                  <summary>{ui("Prompt Diagnostics")}</summary>
                  <DataTable columns={["key", "value"]} rows={diagnosticRows} rowKeyColumn="key" />
                </details>
              </article>
            ) : null}

            {appliedSettings ? (
              <details className="debug-block">
                <summary>{ui("Applied Settings")}</summary>
                <pre>{appliedSettings}</pre>
              </details>
            ) : null}
          </section>

          <aside className="chat-settings" aria-label={ui("Chat settings")}>
            <div className="settings-header">
              <h3 className="section-title">{ui("Settings")}</h3>
              <button className="button secondary-button icon-button" onClick={resetControls} title={ui("Reset all chat controls to defaults.")} type="button">
                <RotateCcw size={15} aria-hidden="true" />
              </button>
            </div>

            <fieldset className="settings-section">
              <legend>{ui("Retrieval")}</legend>
              <NumericControl
                id="chat-top-k"
                label="Top-K sources"
                help="Number of retrieved documents sent into the prompt."
                min={1}
                max={25}
                step={1}
                value={settings.k}
                onChange={(value) => updateSetting("k", value)}
              />
              <label className="settings-field" htmlFor="chat-source-type" title="Restrict retrieval to one source type.">
                  <span>{ui("Source type")}</span>
                <select
                  id="chat-source-type"
                  className="field"
                  value={settings.sourceType}
                  onChange={(event) => updateSetting("sourceType", event.target.value)}
                >
                  <option value="">{ui("All source types")}</option>
                  <option value="ctd">CTD</option>
                  <option value="metagenome">Metagenome</option>
                  <option value="remote_sensing">{ui("Satellite SST")}</option>
                </select>
              </label>
              <label className="settings-field" htmlFor="chat-bay" title="Restrict retrieval to one bay when source metadata supports it.">
                <span>{ui("Bay")}</span>
                <select
                  id="chat-bay"
                  className="field"
                  value={settings.bay}
                  onChange={(event) => updateSetting("bay", event.target.value)}
                >
                  <option value="">{ui("All bays")}</option>
                  <option value="O">Onagawa</option>
                  <option value="I">Ishinomaki</option>
                  <option value="M">Mutsu</option>
                </select>
              </label>
              <div className="settings-pair">
                <label className="settings-field" htmlFor="chat-time-from" title="Inclusive lower bound for document time metadata.">
                  <span>{ui("From")}</span>
                  <input
                    id="chat-time-from"
                    className="field"
                    type="date"
                    value={settings.timeFrom}
                    onChange={(event) => updateSetting("timeFrom", event.target.value)}
                  />
                </label>
                <label className="settings-field" htmlFor="chat-time-to" title="Inclusive upper bound for document time metadata.">
                  <span>{ui("To")}</span>
                  <input
                    id="chat-time-to"
                    className="field"
                    type="date"
                    value={settings.timeTo}
                    onChange={(event) => updateSetting("timeTo", event.target.value)}
                  />
                </label>
              </div>
              <NumericControl
                id="chat-vector-weight"
                label="Vector weight"
                help="Hybrid retrieval weight for semantic vector ranking. Used by PostgreSQL/pgvector retrieval."
                min={0}
                max={1}
                step={0.05}
                value={settings.vectorWeight}
                onChange={(value) => updateSetting("vectorWeight", value)}
              />
              <NumericControl
                id="chat-fts-weight"
                label="FTS weight"
                help="Hybrid retrieval weight for PostgreSQL full-text ranking."
                min={0}
                max={1}
                step={0.05}
                value={settings.ftsWeight}
                onChange={(value) => updateSetting("ftsWeight", value)}
              />
              <NumericControl
                id="chat-rrf-k"
                label="RRF-k"
                help="Reciprocal Rank Fusion smoothing constant. Lower values sharpen top-rank differences."
                min={1}
                max={200}
                step={1}
                value={settings.rrfK}
                onChange={(value) => updateSetting("rrfK", value)}
              />
              <CheckboxControl
                checked={settings.expandEvidence}
                label="Expand cross-source evidence"
                help="Follow anchor-event links from primary retrieval into corroborating CTD, metagenome, or satellite SST records."
                onChange={(value) => updateSetting("expandEvidence", value)}
              />
              <NumericControl
                id="chat-max-linked"
                label="Max linked"
                help="Maximum number of linked cross-source documents added after primary retrieval."
                min={0}
                max={25}
                step={1}
                value={settings.maxLinkedSources}
                onChange={(value) => updateSetting("maxLinkedSources", value)}
              />
            </fieldset>

            <fieldset className="settings-section">
              <legend>{ui("Prompt Context")}</legend>
              <CheckboxControl
                checked={settings.injectAnalysis}
                label="Inject analysis"
                help="Add precomputed ecological analysis documents when the query triggers them."
                onChange={(value) => updateSetting("injectAnalysis", value)}
              />
              <CheckboxControl
                checked={settings.injectReliability}
                label="Inject reliability"
                help="Add cross-source validation and corroboration documents when the query triggers them."
                onChange={(value) => updateSetting("injectReliability", value)}
              />
              <CheckboxControl
                checked={settings.runAnswerAudit}
                label="Run trust report"
                help="Audit answer citations against retrieved evidence, linked evidence, analysis context, and reliability context."
                onChange={(value) => updateSetting("runAnswerAudit", value)}
              />
            </fieldset>

            <fieldset className="settings-section">
              <legend>{ui("Generation")}</legend>
              <label className="settings-field" htmlFor="chat-model" title="Chat model used for answer generation. The field remains editable for provider-supported model names.">
                <span>{ui("Model")}</span>
                <input
                  id="chat-model"
                  className="field"
                  list="chat-model-options"
                  value={settings.model}
                  onChange={(event) => updateSetting("model", event.target.value)}
                />
                <datalist id="chat-model-options">
                  {(models?.models || []).map((model) => (
                    <option key={model.name} value={model.name} />
                  ))}
                </datalist>
              </label>
              <div className="settings-status">
                {providerLabel}: {models?.available ? "available" : "unknown"} | Embedding: {models?.embedding_model || "unknown"}
              </div>
              <NumericControl
                id="chat-temperature"
                label="Temperature"
                help="Sampling randomness. Use 0 for deterministic answers."
                min={0}
                max={2}
                step={0.05}
                value={settings.temperature}
                onChange={(value) => updateSetting("temperature", value)}
              />
              <NumericControl
                id="chat-top-p"
                label="Top-P"
                help="Nucleus sampling probability mass. Lower values make output more focused."
                min={0}
                max={1}
                step={0.05}
                value={settings.topP}
                onChange={(value) => updateSetting("topP", value)}
              />
              <NumericControl
                id="chat-repeat-penalty"
                label="Repeat penalty"
                help="Penalty for repeated tokens. Higher values discourage repetition."
                min={0.5}
                max={2}
                step={0.05}
                value={settings.repeatPenalty}
                onChange={(value) => updateSetting("repeatPenalty", value)}
              />
              <label className="settings-field" htmlFor="chat-num-ctx" title="Maximum model context window requested from the configured runtime when supported.">
                <span>{ui("Context window")}</span>
                <select
                  id="chat-num-ctx"
                  className="field"
                  value={settings.numCtx}
                  onChange={(event) => updateSetting("numCtx", Number(event.target.value))}
                >
                  {[2048, 4096, 8192, 16384, 32768].map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <div className="settings-pair">
                <OptionalIntegerControl
                  id="chat-num-predict"
                  label="Max tokens"
                  help="Maximum generated tokens. Leave blank for the configured runtime default."
                  max={8192}
                  min={1}
                  value={settings.numPredict}
                  onChange={(value) => updateSetting("numPredict", value)}
                />
                <OptionalIntegerControl
                  id="chat-sampling-top-k"
                  label="Sampling top-k"
                  help="Sampling top-k when supported. Leave blank for the configured runtime default."
                  max={200}
                  min={1}
                  value={settings.samplingTopK}
                  onChange={(value) => updateSetting("samplingTopK", value)}
                />
              </div>
              <OptionalIntegerControl
                id="chat-seed"
                label="Seed"
                help="Optional deterministic seed when supported by the configured runtime."
                min={0}
                value={settings.seed}
                onChange={(value) => updateSetting("seed", value)}
              />
            </fieldset>
          </aside>
        </div>
      </form>

    </section>
  );
}

function SummaryCell({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function sourceDocumentRow(source: SourceDocument): Record<string, unknown> {
  return {
    retrieval_role: source.retrieval_role || "primary",
    doc_id: source.doc_id,
    title: source.title,
    source_type: source.source_type,
    sample_id: source.sample_id,
    event_id: source.event_id,
    time: source.time,
    bay: source.bay,
    station: source.station,
    score: source.score,
    vector_rank: source.rank_sources?.vector,
    fts_rank: source.rank_sources?.fts,
    link_type: source.link_type,
    linked_from_doc_id: source.linked_from_doc_id,
    linked_from_event_id: source.linked_from_event_id,
    time_delta_days: source.time_delta_days,
    distance_km: source.distance_km,
    text: source.text,
  };
}

function contextDocumentRow(document: ContextDocument): Record<string, unknown> {
  return {
    context_type: document.context_type,
    doc_id: document.doc_id,
    analysis_type: document.analysis_type,
    title: document.title,
    text: document.text,
  };
}

function diagnosticsToRows(diagnostics: Record<string, unknown>): Record<string, unknown>[] {
  return Object.entries(diagnostics).map(([key, value]) => ({ key, value }));
}

function citationAuditRows(audit?: AnswerAudit | null): Record<string, unknown>[] {
  return (audit?.citations || []).map((record, index) => citationAuditRow(record, index));
}

function citationAuditRow(record: CitationAuditRecord, index: number): Record<string, unknown> {
  return {
    citation_id: record.citation_id,
    raw: record.raw,
    valid: record.valid,
    evidence_role: record.evidence_role,
    source_type: record.source_type,
    context_type: record.context_type,
    covered_source_types: record.covered_source_types,
    title: record.title,
    detail: record.detail,
    _row_key: `${record.citation_id}:${index}`,
  };
}

function citationRequirementRows(audit?: AnswerAudit | null): Record<string, unknown>[] {
  const rows = audit?.citation_requirements?.requirement_rows;
  if (!Array.isArray(rows)) return [];
  return rows.map((row, index) => {
    const record = row && typeof row === "object" ? row as Record<string, unknown> : {};
    return {
      requirement: record.requirement,
      required: record.required,
      satisfied_by: record.satisfied_by,
      status: record.status,
      _row_key: `${record.requirement || "requirement"}:${index}`,
    };
  });
}

function warningRows(audit?: AnswerAudit | null): Record<string, unknown>[] {
  return (audit?.warnings || []).map((warning) => ({ warning }));
}

function formatCoverage(value: unknown): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "NA";
}

function formatSourceTypeList(value: unknown): string {
  if (!Array.isArray(value)) return "";
  return value.map((item) => String(item)).join(", ");
}

function requirementList(audit: AnswerAudit, key: string): string {
  return formatSourceTypeList(audit.citation_requirements?.[key]);
}

function titleCase(value: string): string {
  return value ? `${value[0].toUpperCase()}${value.slice(1)}` : "NA";
}

function NumericControl({
  id,
  label,
  help,
  min,
  max,
  step,
  value,
  onChange,
}: {
  id: string;
  label: string;
  help: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (value: number) => void;
}) {
  const { ui } = useAppPreferences();
  return (
    <label className="settings-field" htmlFor={id} title={ui(help)}>
      <span>{ui(label)}</span>
      <div className="range-row">
        <input
          id={id}
          max={max}
          min={min}
          onChange={(event) => onChange(Number(event.target.value))}
          step={step}
          type="range"
          value={value}
        />
        <input
          aria-label={`${ui(label)} ${ui("value")}`}
          className="field numeric-field"
          max={max}
          min={min}
          onChange={(event) => onChange(Number(event.target.value))}
          step={step}
          type="number"
          value={value}
        />
      </div>
    </label>
  );
}

function OptionalIntegerControl({
  id,
  label,
  help,
  min,
  max,
  value,
  onChange,
}: {
  id: string;
  label: string;
  help: string;
  min: number;
  max?: number;
  value: string;
  onChange: (value: string) => void;
}) {
  const { ui } = useAppPreferences();
  return (
    <label className="settings-field" htmlFor={id} title={ui(help)}>
      <span>{ui(label)}</span>
      <input
        id={id}
        className="field"
        inputMode="numeric"
        max={max}
        min={min}
        onChange={(event) => onChange(event.target.value)}
        placeholder={ui("default")}
        type="number"
        value={value}
      />
    </label>
  );
}

function CheckboxControl({
  checked,
  label,
  help,
  onChange,
}: {
  checked: boolean;
  label: string;
  help: string;
  onChange: (value: boolean) => void;
}) {
  const { ui } = useAppPreferences();
  return (
    <label className="checkbox-row" title={ui(help)}>
      <input checked={checked} onChange={(event) => onChange(event.target.checked)} type="checkbox" />
      <span>{ui(label)}</span>
    </label>
  );
}

function optionalInteger(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}
