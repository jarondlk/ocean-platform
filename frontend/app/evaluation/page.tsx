"use client";

import { useEffect, useMemo, useState } from "react";
import { Play, RefreshCw, Square } from "lucide-react";
import { DataTable, formatCell } from "@/components/DataTable";
import {
  cancelEvaluationJob,
  compareEvaluationRuns,
  getEvaluationCatalog,
  getEvaluationJob,
  getEvaluationPreflight,
  getEvaluationReport,
  getEvaluationRun,
  getEvaluationRuns,
  startAblationEvaluation,
  startStandardEvaluation,
} from "@/lib/api";
import type {
  EvaluationCatalogResponse,
  EvaluationCompareResponse,
  EvaluationJobStatus,
  EvaluationQuestion,
  EvaluationReportResponse,
  EvaluationRunDetailResponse,
  EvaluationRunSummary,
} from "@/types";

type EvaluationView = "runs" | "questions" | "standard" | "ablation" | "compare";

const resultColumns = [
  "question_id",
  "category",
  "mode",
  "retrieval_precision",
  "source_coverage",
  "citation_count",
  "citation_accuracy",
  "context_utilization",
  "latency_seconds",
  "rouge_l",
  "faithfulness",
  "answer_completeness",
  "error",
];

export default function EvaluationPage() {
  const [view, setView] = useState<EvaluationView>("runs");
  const [catalog, setCatalog] = useState<EvaluationCatalogResponse | null>(null);
  const [preflight, setPreflight] = useState<Record<string, unknown> | null>(null);
  const [runs, setRuns] = useState<EvaluationRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [detail, setDetail] = useState<EvaluationRunDetailResponse | null>(null);
  const [report, setReport] = useState<EvaluationReportResponse | null>(null);
  const [selectedQuestionId, setSelectedQuestionId] = useState("");
  const [selectedResultKey, setSelectedResultKey] = useState("");
  const [category, setCategory] = useState("");
  const [modeFilter, setModeFilter] = useState("");
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareResult, setCompareResult] = useState<EvaluationCompareResponse | null>(null);
  const [job, setJob] = useState<EvaluationJobStatus | null>(null);
  const [runTag, setRunTag] = useState("");
  const [evalModel, setEvalModel] = useState("");
  const [judgeModel, setJudgeModel] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [topK, setTopK] = useState(8);
  const [numCtx, setNumCtx] = useState(8192);
  const [temperature, setTemperature] = useState(0);
  const [quickRun, setQuickRun] = useState(true);
  const [runQuality, setRunQuality] = useState(false);
  const [runJudge, setRunJudge] = useState(false);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [questionIdsText, setQuestionIdsText] = useState("");
  const [selectedModes, setSelectedModes] = useState<string[]>([]);
  const [selectedVariants, setSelectedVariants] = useState<string[]>([]);
  const [ablationRepeats, setAblationRepeats] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [catalogPayload, runsPayload, preflightPayload] = await Promise.all([
        getEvaluationCatalog(),
        getEvaluationRuns(),
        getEvaluationPreflight(),
      ]);
      setCatalog(catalogPayload);
      setRuns(runsPayload.runs);
      setPreflight(preflightPayload);
      const defaults = asRecord(preflightPayload.defaults);
      const defaultModel = typeof defaults.model === "string" ? defaults.model : "";
      const defaultEmbeddingModel = typeof defaults.embedding_model === "string" ? defaults.embedding_model : "";
      setEvalModel((current) => current || defaultModel);
      setJudgeModel((current) => current || defaultModel);
      setEmbeddingModel((current) => current || defaultEmbeddingModel);
      setSelectedModes((current) => current.length ? current : catalogPayload.modes.map((mode) => mode.name));
      setSelectedVariants((current) => current.length ? current : catalogPayload.variants.map((variant) => variant.name));
      const nextRunId = selectedRunId || runsPayload.runs[0]?.run_id || "";
      if (nextRunId) {
        setSelectedRunId(nextRunId);
        await loadRun(nextRunId);
      }
      if (!selectedQuestionId && catalogPayload.questions[0]) {
        setSelectedQuestionId(catalogPayload.questions[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation request failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadRun(runId: string, nextMode = modeFilter) {
    if (!runId) return;
    setError("");
    const [detailPayload, reportPayload] = await Promise.all([
      getEvaluationRun({ run_id: runId, limit: 250, mode: nextMode || undefined }),
      getEvaluationReport(runId),
    ]);
    setDetail(detailPayload);
    setReport(reportPayload);
    setSelectedResultKey("");
  }

  useEffect(() => {
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!job || isTerminalJob(job.status)) return;

    const jobId = job.job_id;
    let cancelled = false;
    async function pollJob() {
      try {
        const next = await getEvaluationJob(jobId);
        if (cancelled) return;
        setJob(next);
        if (isTerminalJob(next.status)) {
          await loadAll();
          if (next.result_run_id) {
            setSelectedRunId(next.result_run_id);
            await loadRun(next.result_run_id);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Evaluation status request failed");
        }
      }
    }

    const interval = window.setInterval(() => {
      void pollJob();
    }, 2000);
    void pollJob();
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.job_id, job?.status]);

  const selectedRun = runs.find((run) => run.run_id === selectedRunId) || null;
  const questions = useMemo(() => {
    const rows = catalog?.questions || [];
    return category ? rows.filter((question) => question.category === category) : rows;
  }, [catalog, category]);
  const selectedQuestion = (catalog?.questions || []).find((question) => question.id === selectedQuestionId) || questions[0] || null;
  const detailRows: Record<string, unknown>[] = useMemo(() => (detail?.rows || []).map((row) => ({ ...row, _row_key: resultRowKey(row) })), [detail]);
  const selectedResult = detailRows.find((row) => row._row_key === selectedResultKey) || detailRows[0] || null;
  const summary = asRecord(detail?.summary);
  const byMode = getRows(summary.by_mode);
  const byCategory = getRows(summary.by_category);
  const qualityByMode = getRows(summary.quality_by_mode);
  const questionIds = parseQuestionIds(questionIdsText);
  const selectedQuestionCount = estimateQuestionCount(catalog, selectedCategories, questionIdsText, quickRun);
  const qualityMultiplier = runQuality || runJudge ? 2 : 1;
  const standardEvalUnits = selectedQuestionCount * selectedModes.length;
  const ablationEvalUnits = selectedQuestionCount * selectedVariants.length * ablationRepeats;

  async function submitCompare() {
    if (compareIds.length < 2) return;
    setLoading(true);
    setError("");
    try {
      setCompareResult(await compareEvaluationRuns(compareIds));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison request failed");
    } finally {
      setLoading(false);
    }
  }

  function baseEvaluationControls() {
    return {
      model: evalModel || undefined,
      tag: runTag || undefined,
      quick: quickRun,
      question_ids: questionIds,
      categories: selectedCategories,
      top_k: topK,
      num_ctx: numCtx,
      temperature,
      run_quality: runQuality || runJudge,
      run_judge: runJudge,
      judge_model: judgeModel || undefined,
      embedding_model: embeddingModel || undefined,
    };
  }

  async function submitStandardRun() {
    if (!selectedModes.length) {
      setError("Select at least one evaluation mode.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const started = await startStandardEvaluation({
        ...baseEvaluationControls(),
        modes: selectedModes,
      });
      setJob(await getEvaluationJob(started.job_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Standard evaluation failed to start");
    } finally {
      setLoading(false);
    }
  }

  async function submitAblationRun() {
    if (!selectedVariants.length) {
      setError("Select at least one ablation variant.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const started = await startAblationEvaluation({
        ...baseEvaluationControls(),
        variants: selectedVariants,
        repeats: ablationRepeats,
      });
      setJob(await getEvaluationJob(started.job_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ablation evaluation failed to start");
    } finally {
      setLoading(false);
    }
  }

  async function cancelJob() {
    if (!job) return;
    setLoading(true);
    setError("");
    try {
      setJob(await cancelEvaluationJob(job.job_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cancellation request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <header className="page-header">
        <h2>Evaluation</h2>
      </header>

      <div className="data-tabs" role="tablist" aria-label="Evaluation views">
        <TabButton active={view === "runs"} label="Runs" onClick={() => setView("runs")} />
        <TabButton active={view === "questions"} label="Questions" onClick={() => setView("questions")} />
        <TabButton active={view === "standard"} label="Standard" onClick={() => setView("standard")} />
        <TabButton active={view === "ablation"} label="Ablation" onClick={() => setView("ablation")} />
        <TabButton active={view === "compare"} label="Compare" onClick={() => setView("compare")} />
      </div>

      <div className="section-toolbar">
        <span className="empty-state">
          {loading ? "Loading evaluation state." : `${runs.length} saved runs. ${catalog?.questions.length || 0} benchmark questions.`}
        </span>
        <button className="button secondary-button" onClick={() => void loadAll()} type="button">
          <RefreshCw size={15} aria-hidden="true" />
          Refresh
        </button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}

      <div className="grid metrics-grid system-metrics">
        <Metric label="Questions" value={catalog?.questions.length ?? "..."} />
        <Metric label="Modes" value={catalog?.modes.length ?? "..."} />
        <Metric label="Variants" value={catalog?.variants.length ?? "..."} />
        <Metric label="Saved runs" value={runs.length || "..."} />
      </div>

      {job ? <JobStatusPanel job={job} loading={loading} onCancel={() => void cancelJob()} /> : null}

      {view === "runs" ? (
        <section className="evaluation-layout">
          <aside className="evaluation-sidebar">
            <h3 className="section-title">Runs</h3>
            <div className="table-list">
              {runs.map((run) => (
                <button
                  className={selectedRunId === run.run_id ? "active" : ""}
                  key={run.run_id}
                  onClick={() => {
                    setSelectedRunId(run.run_id);
                    setModeFilter("");
                    void loadRun(run.run_id, "");
                  }}
                  type="button"
                >
                  <span>{run.run_id}</span>
                  <strong>{run.n_evaluations}</strong>
                </button>
              ))}
            </div>
          </aside>

          <main className="evaluation-main">
            {selectedRun ? (
              <>
                <section className="data-section">
                  <h3 className="section-title">Run Detail</h3>
                  <div className="summary-strip">
                    <SummaryCell label="Type" value={selectedRun.run_type} />
                    <SummaryCell label="Model" value={selectedRun.model || "unknown"} />
                    <SummaryCell label="Errors" value={selectedRun.n_errors} />
                    <SummaryCell label="Quality" value={selectedRun.has_quality_metrics ? "yes" : "no"} />
                  </div>
                  <div className="status-list">
                    <StatusRow label="CSV" value={selectedRun.csv_path} />
                    <StatusRow label="Meta" value={selectedRun.meta_path || "NA"} />
                    <StatusRow label="Report" value={selectedRun.report_path || "generated on request"} />
                  </div>
                </section>

                <section className="data-section">
                  <h3 className="section-title">Aggregate Metrics</h3>
                  <DataTable columns={["mode", ...metricKeys(byMode)]} rows={byMode} rowKeyColumn="mode" />
                  {qualityByMode.length ? (
                    <>
                      <h4 className="subsection-title">Quality Metrics</h4>
                      <DataTable columns={["mode", ...metricKeys(qualityByMode)]} rows={qualityByMode} rowKeyColumn="mode" />
                    </>
                  ) : null}
                </section>

                <section className="data-section">
                  <div className="section-toolbar">
                    <h3 className="section-title">Rows</h3>
                    <label className="settings-field compact-field" htmlFor="eval-mode-filter" title="Filter rows by evaluation mode or ablation variant.">
                      <span>Mode</span>
                      <select
                        id="eval-mode-filter"
                        className="field"
                        value={modeFilter}
                        onChange={(event) => {
                          setModeFilter(event.target.value);
                          void loadRun(selectedRun.run_id, event.target.value);
                        }}
                      >
                        <option value="">all</option>
                        {selectedRun.modes.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
                      </select>
                    </label>
                  </div>
                  <DataTable
                    columns={resultColumns.filter((column) => detail?.columns.includes(column))}
                    rows={detailRows}
                    rowKeyColumn="_row_key"
                    selectedKey={selectedResultKey}
                    onRowSelect={(row) => setSelectedResultKey(resultRowKey(row))}
                  />
                </section>

                {selectedResult ? (
                  <section className="data-section">
                    <h3 className="section-title">Trace</h3>
                    <div className="trace-grid">
                      <div>
                        <p className="metric-label">Question</p>
                        <pre className="code-block">{String(selectedResult.question || "")}</pre>
                      </div>
                      <div>
                        <p className="metric-label">Cited IDs</p>
                        <pre className="code-block">{String(selectedResult.cited_ids || "NA")}</pre>
                      </div>
                      <div className="trace-wide">
                        <p className="metric-label">Response</p>
                        <pre className="code-block tall-block">{String(selectedResult.response || "")}</pre>
                      </div>
                    </div>
                  </section>
                ) : null}

                <section className="data-section">
                  <h3 className="section-title">Report</h3>
                  <pre className="code-block report-block">{report?.markdown || "No report."}</pre>
                </section>
              </>
            ) : (
              <p className="empty-state">No evaluation run selected.</p>
            )}
          </main>
        </section>
      ) : null}

      {view === "questions" ? (
        <section className="evaluation-main">
          <div className="data-controls">
            <label className="settings-field" htmlFor="question-category" title="Filter benchmark questions by category.">
              <span>Category</span>
              <select id="question-category" className="field" value={category} onChange={(event) => setCategory(event.target.value)}>
                <option value="">all</option>
                {(catalog?.categories || []).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
          </div>
          <DataTable
            columns={["id", "category", "question", "expected_source_types", "expected_min_citations", "requires_analysis", "requires_reliability"]}
            rows={questions.map(questionToRow)}
            rowKeyColumn="id"
            selectedKey={selectedQuestionId}
            onRowSelect={(row) => setSelectedQuestionId(String(row.id))}
          />
          {selectedQuestion ? <QuestionDetail question={selectedQuestion} /> : null}
        </section>
      ) : null}

      {view === "standard" ? (
        <section className="evaluation-main">
          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">Standard Run Controls</h3>
              <button className="button" disabled={loading || standardEvalUnits === 0 || selectedModes.length === 0} onClick={() => void submitStandardRun()} type="button">
                <Play size={15} aria-hidden="true" />
                Start Standard
              </button>
            </div>
            <EvaluationControlPanel
              catalog={catalog}
              evalModel={evalModel}
              setEvalModel={setEvalModel}
              judgeModel={judgeModel}
              setJudgeModel={setJudgeModel}
              embeddingModel={embeddingModel}
              setEmbeddingModel={setEmbeddingModel}
              runTag={runTag}
              setRunTag={setRunTag}
              topK={topK}
              setTopK={setTopK}
              numCtx={numCtx}
              setNumCtx={setNumCtx}
              temperature={temperature}
              setTemperature={setTemperature}
              quickRun={quickRun}
              setQuickRun={setQuickRun}
              runQuality={runQuality}
              setRunQuality={setRunQuality}
              runJudge={runJudge}
              setRunJudge={setRunJudge}
              selectedCategories={selectedCategories}
              setSelectedCategories={setSelectedCategories}
              questionIdsText={questionIdsText}
              setQuestionIdsText={setQuestionIdsText}
            />
            <CheckboxGroup
              items={(catalog?.modes || []).map((mode) => mode.name)}
              label="Modes"
              selected={selectedModes}
              setSelected={setSelectedModes}
              titleFor={(name) => {
                const mode = catalog?.modes.find((item) => item.name === name);
                return mode ? `analysis=${mode.inject_analysis}, reliability=${mode.inject_reliability}` : name;
              }}
            />
            <RunEstimate
              label="Standard estimate"
              primary={`${standardEvalUnits} answer runs`}
              secondary={`${standardEvalUnits * qualityMultiplier} total work units with current quality settings`}
            />
          </section>

          <section className="data-section">
            <h3 className="section-title">Standard Protocol</h3>
            <DataTable columns={["name", "inject_analysis", "inject_reliability"]} rows={catalog?.modes || []} rowKeyColumn="name" />
          </section>

          <section className="data-section">
            <h3 className="section-title">Metric Contract</h3>
            <DataTable columns={["key", "label", "format"]} rows={catalog?.metrics || []} rowKeyColumn="key" />
          </section>
          <PreflightBlock preflight={preflight} />
        </section>
      ) : null}

      {view === "ablation" ? (
        <section className="evaluation-main">
          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">Ablation Run Controls</h3>
              <button className="button" disabled={loading || ablationEvalUnits === 0 || selectedVariants.length === 0} onClick={() => void submitAblationRun()} type="button">
                <Play size={15} aria-hidden="true" />
                Start Ablation
              </button>
            </div>
            <EvaluationControlPanel
              catalog={catalog}
              evalModel={evalModel}
              setEvalModel={setEvalModel}
              judgeModel={judgeModel}
              setJudgeModel={setJudgeModel}
              embeddingModel={embeddingModel}
              setEmbeddingModel={setEmbeddingModel}
              runTag={runTag}
              setRunTag={setRunTag}
              topK={topK}
              setTopK={setTopK}
              numCtx={numCtx}
              setNumCtx={setNumCtx}
              temperature={temperature}
              setTemperature={setTemperature}
              quickRun={quickRun}
              setQuickRun={setQuickRun}
              runQuality={runQuality}
              setRunQuality={setRunQuality}
              runJudge={runJudge}
              setRunJudge={setRunJudge}
              selectedCategories={selectedCategories}
              setSelectedCategories={setSelectedCategories}
              questionIdsText={questionIdsText}
              setQuestionIdsText={setQuestionIdsText}
            />
            <div className="evaluation-control-grid compact-controls">
              <label className="settings-field" htmlFor="ablation-repeats" title="Repeat each question and variant combination for stability checks.">
                <span>Repeats</span>
                <input
                  id="ablation-repeats"
                  className="field"
                  max={5}
                  min={1}
                  onChange={(event) => setAblationRepeats(clampNumber(event.target.value, 1, 5))}
                  type="number"
                  value={ablationRepeats}
                />
              </label>
            </div>
            <CheckboxGroup
              items={(catalog?.variants || []).map((variant) => variant.name)}
              label="Variants"
              selected={selectedVariants}
              setSelected={setSelectedVariants}
              titleFor={(name) => catalog?.variants.find((item) => item.name === name)?.description || name}
            />
            <RunEstimate
              label="Ablation estimate"
              primary={`${ablationEvalUnits} answer runs`}
              secondary={`${ablationEvalUnits * qualityMultiplier} total work units with current quality settings`}
            />
          </section>

          <section className="data-section">
            <h3 className="section-title">Ablation Protocol</h3>
            <DataTable columns={["name", "source_coverage", "inject_analysis", "inject_reliability", "description"]} rows={catalog?.variants || []} rowKeyColumn="name" />
          </section>

          <section className="data-section">
            <h3 className="section-title">Category Summary</h3>
            <DataTable columns={["category", ...metricKeys(byCategory)]} rows={byCategory} rowKeyColumn="category" />
          </section>
        </section>
      ) : null}

      {view === "compare" ? (
        <section className="evaluation-main">
          <h3 className="section-title">Run Selection</h3>
          <div className="compare-list">
            {runs.map((run) => (
              <label className="checkbox-row" key={run.run_id} title={run.csv_path}>
                <input
                  checked={compareIds.includes(run.run_id)}
                  onChange={(event) => {
                    setCompareIds((current) =>
                      event.target.checked
                        ? [...current, run.run_id]
                        : current.filter((id) => id !== run.run_id),
                    );
                  }}
                  type="checkbox"
                />
                <span>{run.run_id}</span>
              </label>
            ))}
          </div>
          <button className="button" disabled={compareIds.length < 2 || loading} onClick={() => void submitCompare()} type="button">
            Compare
          </button>
          {compareResult ? (
            <>
              <h3 className="section-title">Mode Comparison</h3>
              <DataTable columns={["run_id", "model", "mode", ...metricKeys(compareResult.by_mode)]} rows={compareResult.by_mode} rowKeyColumn="run_id" />
              <h3 className="section-title">Comparison Report</h3>
              <pre className="code-block report-block">{compareResult.markdown}</pre>
            </>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

function JobStatusPanel({ job, loading, onCancel }: { job: EvaluationJobStatus; loading: boolean; onCancel: () => void }) {
  const terminal = isTerminalJob(job.status);
  const percent = Math.max(0, Math.min(100, Number(job.percent) || 0));
  return (
    <section className="data-section job-panel">
      <div className="section-toolbar">
        <h3 className="section-title">Background Run</h3>
        {!terminal ? (
          <button className="button secondary-button" disabled={loading || job.status === "cancel_requested"} onClick={onCancel} type="button">
            <Square size={14} aria-hidden="true" />
            Cancel
          </button>
        ) : null}
      </div>
      <div className="summary-strip">
        <SummaryCell label="Status" value={job.status} />
        <SummaryCell label="Phase" value={job.phase} />
        <SummaryCell label="Progress" value={`${percent.toFixed(1)}%`} />
        <SummaryCell label="Rows" value={`${job.current}/${job.total || "?"}`} />
      </div>
      <div className="meter-track job-meter" aria-label="Evaluation progress">
        <div style={{ width: `${percent}%` }} />
      </div>
      <div className="status-list">
        <StatusRow label="Run ID" value={job.run_id} />
        <StatusRow label="Message" value={job.message || "NA"} />
        <StatusRow label="Output" value={job.output_dir || "NA"} />
        {job.error ? <StatusRow label="Error" value={job.error} /> : null}
      </div>
    </section>
  );
}

function EvaluationControlPanel({
  catalog,
  evalModel,
  setEvalModel,
  judgeModel,
  setJudgeModel,
  embeddingModel,
  setEmbeddingModel,
  runTag,
  setRunTag,
  topK,
  setTopK,
  numCtx,
  setNumCtx,
  temperature,
  setTemperature,
  quickRun,
  setQuickRun,
  runQuality,
  setRunQuality,
  runJudge,
  setRunJudge,
  selectedCategories,
  setSelectedCategories,
  questionIdsText,
  setQuestionIdsText,
}: {
  catalog: EvaluationCatalogResponse | null;
  evalModel: string;
  setEvalModel: (value: string) => void;
  judgeModel: string;
  setJudgeModel: (value: string) => void;
  embeddingModel: string;
  setEmbeddingModel: (value: string) => void;
  runTag: string;
  setRunTag: (value: string) => void;
  topK: number;
  setTopK: (value: number) => void;
  numCtx: number;
  setNumCtx: (value: number) => void;
  temperature: number;
  setTemperature: (value: number) => void;
  quickRun: boolean;
  setQuickRun: (value: boolean) => void;
  runQuality: boolean;
  setRunQuality: (value: boolean) => void;
  runJudge: boolean;
  setRunJudge: (value: boolean) => void;
  selectedCategories: string[];
  setSelectedCategories: (value: string[]) => void;
  questionIdsText: string;
  setQuestionIdsText: (value: string) => void;
}) {
  return (
    <>
      <div className="evaluation-control-grid">
        <label className="settings-field" htmlFor="eval-model" title="Ollama chat model used for answer generation. Leave as the configured default unless comparing models.">
          <span>Model</span>
          <input id="eval-model" className="field" onChange={(event) => setEvalModel(event.target.value)} value={evalModel} />
        </label>
        <label className="settings-field" htmlFor="eval-tag" title="Optional label stored in run metadata for later comparison.">
          <span>Tag</span>
          <input id="eval-tag" className="field" onChange={(event) => setRunTag(event.target.value)} placeholder="local-test, qwen-baseline" value={runTag} />
        </label>
        <label className="settings-field" htmlFor="eval-top-k" title="Number of retrieved source documents passed into each answer-generation run.">
          <span>Top K</span>
          <input id="eval-top-k" className="field" max={25} min={1} onChange={(event) => setTopK(clampNumber(event.target.value, 1, 25))} type="number" value={topK} />
        </label>
        <label className="settings-field" htmlFor="eval-num-ctx" title="Ollama context window for evaluation calls.">
          <span>Num ctx</span>
          <input id="eval-num-ctx" className="field" max={32768} min={512} onChange={(event) => setNumCtx(clampNumber(event.target.value, 512, 32768))} step={512} type="number" value={numCtx} />
        </label>
        <label className="settings-field" htmlFor="eval-temp" title="Generation temperature. Zero is preferred for deterministic benchmark runs.">
          <span>Temperature</span>
          <input id="eval-temp" className="field" max={2} min={0} onChange={(event) => setTemperature(clampNumber(event.target.value, 0, 2))} step={0.05} type="number" value={temperature} />
        </label>
        <label className="settings-field" htmlFor="eval-embedding-model" title="Embedding model used for semantic similarity when quality scoring is enabled.">
          <span>Embedding model</span>
          <input id="eval-embedding-model" className="field" onChange={(event) => setEmbeddingModel(event.target.value)} value={embeddingModel} />
        </label>
        <label className="settings-field" htmlFor="eval-judge-model" title="Model used for LLM-as-judge scoring when enabled.">
          <span>Judge model</span>
          <input id="eval-judge-model" className="field" onChange={(event) => setJudgeModel(event.target.value)} value={judgeModel} />
        </label>
      </div>

      <div className="evaluation-switch-grid">
        <label className="checkbox-row" title="Use one representative question per category unless explicit question IDs are provided.">
          <input checked={quickRun} onChange={(event) => setQuickRun(event.target.checked)} type="checkbox" />
          <span>Quick subset</span>
        </label>
        <label className="checkbox-row" title="Append ROUGE-L, semantic similarity, faithfulness, and answer-completeness metrics after answer generation.">
          <input checked={runQuality} onChange={(event) => setRunQuality(event.target.checked)} type="checkbox" />
          <span>Quality metrics</span>
        </label>
        <label className="checkbox-row" title="Run LLM-as-judge scoring. This also enables quality scoring and is intentionally expensive.">
          <input
            checked={runJudge}
            onChange={(event) => {
              setRunJudge(event.target.checked);
              if (event.target.checked) setRunQuality(true);
            }}
            type="checkbox"
          />
          <span>LLM judge</span>
        </label>
      </div>

      <CheckboxGroup
        items={catalog?.categories || []}
        label="Categories"
        selected={selectedCategories}
        setSelected={setSelectedCategories}
        titleFor={(name) => `Restrict evaluation questions to ${name}. Empty means all categories.`}
      />

      <label className="settings-field evaluation-question-field" htmlFor="eval-question-ids" title="Comma or whitespace separated benchmark question IDs. Explicit IDs override category and quick-subset sampling.">
        <span>Question IDs</span>
        <textarea
          id="eval-question-ids"
          className="textarea compact-textarea"
          onChange={(event) => setQuestionIdsText(event.target.value)}
          placeholder="q_ctd_001 q_sst_002"
          value={questionIdsText}
        />
      </label>
    </>
  );
}

function CheckboxGroup({
  items,
  label,
  selected,
  setSelected,
  titleFor,
}: {
  items: string[];
  label: string;
  selected: string[];
  setSelected: (value: string[]) => void;
  titleFor?: (item: string) => string;
}) {
  return (
    <fieldset className="settings-section evaluation-choice-group">
      <legend>{label}</legend>
      <div className="choice-actions">
        <button className="button secondary-button" onClick={() => setSelected(items)} type="button">Select all</button>
        <button className="button secondary-button" onClick={() => setSelected([])} type="button">Clear</button>
      </div>
      <div className="evaluation-checkbox-grid">
        {items.map((item) => (
          <label className="checkbox-row" key={item} title={titleFor ? titleFor(item) : item}>
            <input
              checked={selected.includes(item)}
              onChange={(event) => setSelected(toggleSelected(selected, item, event.target.checked))}
              type="checkbox"
            />
            <span>{item}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function RunEstimate({ label, primary, secondary }: { label: string; primary: string; secondary: string }) {
  return (
    <div className="run-estimate">
      <span>{label}</span>
      <strong>{primary}</strong>
      <small>{secondary}</small>
    </div>
  );
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return <button className={active ? "active" : ""} onClick={onClick} type="button">{label}</button>;
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <article className="card">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
    </article>
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

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function QuestionDetail({ question }: { question: EvaluationQuestion }) {
  return (
    <section className="data-section question-detail">
      <h3 className="section-title">{question.id}</h3>
      <div className="trace-grid">
        <div className="trace-wide">
          <p className="metric-label">Question</p>
          <pre className="code-block">{question.question}</pre>
        </div>
        <div>
          <p className="metric-label">Key facts</p>
          <pre className="code-block">{question.key_facts.join("\n") || "NA"}</pre>
        </div>
        <div>
          <p className="metric-label">Citation patterns</p>
          <pre className="code-block">{question.expected_citation_patterns.join("\n") || "NA"}</pre>
        </div>
        <div className="trace-wide">
          <p className="metric-label">Reference answer</p>
          <pre className="code-block tall-block">{question.reference_answer || "NA"}</pre>
        </div>
      </div>
    </section>
  );
}

function PreflightBlock({ preflight }: { preflight: Record<string, unknown> | null }) {
  const defaults = asRecord(preflight?.defaults);
  const artifacts = asRecord(preflight?.artifacts);
  return (
    <section className="data-section">
      <h3 className="section-title">Preflight</h3>
      <div className="status-list">
        <StatusRow label="Model" value={formatCell(defaults.model)} />
        <StatusRow label="Embedding model" value={formatCell(defaults.embedding_model)} />
        <StatusRow label="Ollama URL" value={formatCell(defaults.ollama_base_url)} />
        <StatusRow label="Evaluation runs" value={formatCell(artifacts.evaluation_runs)} />
        <StatusRow label="Retrieval documents" value={formatCell(artifacts.retrieval_documents)} />
      </div>
    </section>
  );
}

function questionToRow(question: EvaluationQuestion): Record<string, unknown> {
  return {
    id: question.id,
    category: question.category,
    question: question.question,
    expected_source_types: question.expected_source_types,
    expected_min_citations: question.expected_min_citations,
    requires_analysis: question.requires_analysis,
    requires_reliability: question.requires_reliability,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function getRows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object" && !Array.isArray(row)) : [];
}

function metricKeys(rows: Record<string, unknown>[]): string[] {
  const reserved = new Set(["mode", "category", "run_id", "model"]);
  const keys = new Set<string>();
  rows.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (!reserved.has(key)) keys.add(key);
    });
  });
  return Array.from(keys);
}

function resultRowKey(row: Record<string, unknown>): string {
  return `${row.question_id || "q"}:${row.mode || "mode"}:${row.repetition || ""}`;
}

function parseQuestionIds(value: string): string[] {
  return value
    .split(/[\s,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function estimateQuestionCount(
  catalog: EvaluationCatalogResponse | null,
  selectedCategories: string[],
  questionIdsText: string,
  quickRun: boolean,
): number {
  const explicitIds = parseQuestionIds(questionIdsText);
  if (explicitIds.length) return explicitIds.length;

  let rows = catalog?.questions || [];
  if (selectedCategories.length) {
    const allowed = new Set(selectedCategories);
    rows = rows.filter((question) => allowed.has(question.category));
  }
  if (!quickRun) return rows.length;
  return new Set(rows.map((question) => question.category)).size;
}

function toggleSelected(selected: string[], item: string, checked: boolean): string[] {
  if (checked) return selected.includes(item) ? selected : [...selected, item];
  return selected.filter((value) => value !== item);
}

function clampNumber(value: string, min: number, max: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return min;
  return Math.min(max, Math.max(min, parsed));
}

function isTerminalJob(status: string): boolean {
  return status === "complete" || status === "failed" || status === "cancelled";
}
