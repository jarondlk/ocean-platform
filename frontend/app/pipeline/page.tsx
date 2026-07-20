"use client";

import { useEffect, useMemo, useState } from "react";
import { Play, RefreshCw, Square } from "lucide-react";
import { DataTable, formatCell } from "@/components/DataTable";
import {
  cancelPipelineJob,
  getPipelineJob,
  getPipelineJobLog,
  getPipelinePreflight,
  getPipelineRun,
  getPipelineRuns,
  getPipelineStatus,
  startPipelineJob,
} from "@/lib/api";
import type {
  PipelineArtifactFreshness,
  PipelineArtifactInfo,
  PipelineJobStatus,
  PipelineLogResponse,
  PipelinePreflightResponse,
  PipelineRunDetailResponse,
  PipelineStageLog,
  PipelineStageInfo,
  PipelineStatusResponse,
  PipelineRunSummary,
} from "@/types";

type PipelineView = "status" | "run" | "logs" | "history";

const artifactColumns = ["label", "exists", "rows", "size_bytes", "modified_at", "note", "path"];
const freshnessColumns = ["kind", "label", "freshness_status", "lineage_status", "age_days", "rows", "size_bytes", "modified_at", "path"];
const stageColumns = ["id", "label", "destructive", "expensive", "command", "expected_inputs", "expected_outputs"];
const preflightColumns = ["status", "severity", "required", "label", "detail"];
const runColumns = ["run_id", "status", "tag", "dry_run", "stage_count", "started_at", "completed_at", "duration_seconds", "failed_stage"];
const activeJobColumns = ["job_id", "status", "phase", "stage_id", "percent", "updated_at", "message"];
const diffColumns = ["label", "changed", "rows_before", "rows_after", "rows_delta", "size_before", "size_after", "modified_after"];
const defaultFullStages = ["validate_raw", "ingest", "build_retrieval_docs", "pre_analysis", "reliability", "load_db"];

export default function PipelinePage() {
  const [view, setView] = useState<PipelineView>("status");
  const [status, setStatus] = useState<PipelineStatusResponse | null>(null);
  const [selectedStages, setSelectedStages] = useState<string[]>(["validate_raw"]);
  const [tag, setTag] = useState("");
  const [notes, setNotes] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [skipSst, setSkipSst] = useState(false);
  const [resetDatabase, setResetDatabase] = useState(false);
  const [embedAfterLoad, setEmbedAfterLoad] = useState(true);
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [embeddingBatchSize, setEmbeddingBatchSize] = useState(32);
  const [preflight, setPreflight] = useState<PipelinePreflightResponse | null>(null);
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runDetail, setRunDetail] = useState<PipelineRunDetailResponse | null>(null);
  const [job, setJob] = useState<PipelineJobStatus | null>(null);
  const [jobLog, setJobLog] = useState<PipelineLogResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function buildRequest() {
    return {
      stages: selectedStages,
      tag: tag || undefined,
      dry_run: dryRun,
      skip_sst: skipSst,
      reset_database: resetDatabase,
      embed_after_load: embedAfterLoad,
      embedding_model: embeddingModel || undefined,
      embedding_batch_size: embeddingBatchSize,
      notes: notes || undefined,
    };
  }

  async function loadStatus() {
    setLoading(true);
    setError("");
    try {
      const [payload, runsPayload] = await Promise.all([
        getPipelineStatus(),
        getPipelineRuns(),
      ]);
      setStatus(payload);
      setRuns(runsPayload.runs);
      const nextRunId = selectedRunId || runsPayload.runs[0]?.run_id || "";
      if (nextRunId && nextRunId !== selectedRunId) {
        setSelectedRunId(nextRunId);
      }
      if (nextRunId) {
        await loadRun(nextRunId);
      }
      const activeJobs = payload.active_jobs || [];
      if (activeJobs.length && (!job || isTerminalJob(job.status))) {
        const activeJob = activeJobs[0];
        setJob(activeJob);
        setJobLog(await getPipelineJobLog(activeJob.job_id));
      }
      const embeddingDefault = asString(payload.ollama.embedding_model) || asString(payload.database.embedding_model);
      setEmbeddingModel((current) => current || embeddingDefault);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline status request failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadRun(runId: string) {
    if (!runId) return;
    const detail = await getPipelineRun(runId);
    setRunDetail(detail);
    setSelectedRunId(runId);
  }

  async function refreshPreflight() {
    if (!selectedStages.length) return;
    setLoading(true);
    setError("");
    try {
      setPreflight(await getPipelinePreflight(buildRequest()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline preflight failed");
    } finally {
      setLoading(false);
    }
  }

  async function refreshJob(jobId: string) {
    const [nextJob, nextLog] = await Promise.all([
      getPipelineJob(jobId),
      getPipelineJobLog(jobId),
    ]);
    setJob(nextJob);
    setJobLog(nextLog);
    if (isTerminalJob(nextJob.status)) {
      await loadStatus();
    }
  }

  useEffect(() => {
    void loadStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!job || isTerminalJob(job.status)) return;
    const jobId = job.job_id;
    let cancelled = false;

    async function poll() {
      try {
        const [nextJob, nextLog] = await Promise.all([
          getPipelineJob(jobId),
          getPipelineJobLog(jobId),
        ]);
        if (cancelled) return;
        setJob(nextJob);
        setJobLog(nextLog);
        if (isTerminalJob(nextJob.status)) {
          await loadStatus();
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Pipeline job polling failed");
      }
    }

    const interval = window.setInterval(() => {
      void poll();
    }, 2000);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.job_id, job?.status]);

  const stages = status?.stages || [];
  const selectedStageInfos = stages.filter((stage) => selectedStages.includes(stage.id));
  const readiness = asRecord(status?.readiness);
  const database = asRecord(status?.database);
  const ollama = asRecord(status?.ollama);
  const stageRows = stages.map(stageToRow);
  const rawRows = (status?.raw_sources || []).map(artifactToRow);
  const artifactRows = (status?.artifacts || []).map(artifactToRow);
  const freshnessRows = (status?.artifact_freshness || []).map(freshnessToRow);
  const activeJobRows = (status?.active_jobs || []).map(jobToRow);
  const selectedCommandRows = preflight?.command_plan?.length
    ? preflight.command_plan.map(commandPlanToRow)
    : selectedStageInfos.map(stageToCommandRow);
  const preflightRows = (preflight?.checks || []).map(preflightCheckToRow);
  const runRows = runs.map(runToRow);
  const diffRows = artifactDiffRows(runDetail?.manifest);
  const readinessRows = [
    { label: "Raw", value: formatCell(readiness.required_raw_ready), ok: readiness.required_raw_ready === true },
    { label: "Corpus", value: formatCell(readiness.corpus_artifacts_ready), ok: readiness.corpus_artifacts_ready === true },
    { label: "SST", value: formatCell(readiness.sst_available), ok: readiness.sst_available === true },
    { label: "Database", value: formatCell(database.available), ok: database.available === true },
    { label: "Ollama", value: formatCell(ollama.available), ok: ollama.available === true },
  ];
  const artifactAvailabilityRows = [
    {
      label: "Raw sources",
      value: rawRows.filter((row) => row.exists === true).length,
      total: rawRows.length,
    },
    {
      label: "Derived artifacts",
      value: artifactRows.filter((row) => row.exists === true).length,
      total: artifactRows.length,
    },
    {
      label: "Fresh artifacts",
      value: freshnessRows.filter((row) => row.freshness_status === "fresh").length,
      total: freshnessRows.length,
    },
  ];
  const freshnessBreakdown = countRowsBy(freshnessRows, "freshness_status");
  const canStart = selectedStages.length > 0 && !loading && (!selectedStages.includes("load_db") || dryRun || resetDatabase);

  async function submitJob() {
    if (!selectedStages.length) return;
    setLoading(true);
    setError("");
    try {
      const request = buildRequest();
      setPreflight(await getPipelinePreflight(request));
      const started = await startPipelineJob(request);
      setView("logs");
      await refreshJob(started.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline job failed to start");
    } finally {
      setLoading(false);
    }
  }

  async function cancelJob() {
    if (!job) return;
    setLoading(true);
    setError("");
    try {
      const next = await cancelPipelineJob(job.job_id);
      setJob(next);
      setJobLog(await getPipelineJobLog(next.job_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline cancellation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <header className="page-header">
        <h2>Pipeline</h2>
      </header>

      <div className="data-tabs" role="tablist" aria-label="Pipeline views">
        <TabButton active={view === "status"} label="Status" onClick={() => setView("status")} />
        <TabButton active={view === "run"} label="Run" onClick={() => setView("run")} />
        <TabButton active={view === "logs"} label="Logs" onClick={() => setView("logs")} />
        <TabButton active={view === "history"} label="History" onClick={() => setView("history")} />
      </div>

      <div className="section-toolbar">
        <span className="empty-state">
          {loading ? "Loading pipeline state." : `${stages.length || 0} stages. ${status?.pipeline_runs || 0} recorded manual runs.`}
        </span>
        <button className="button secondary-button" onClick={() => void loadStatus()} type="button">
          <RefreshCw size={15} aria-hidden="true" />
          Refresh
        </button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}

      <div className="grid metrics-grid system-metrics">
        <Metric label="Raw ready" value={formatCell(readiness.required_raw_ready)} />
        <Metric label="Corpus ready" value={formatCell(readiness.corpus_artifacts_ready)} />
        <Metric label="DB docs" value={formatCell(database.retrieval_documents)} />
        <Metric label="Embedded" value={formatCell(database.embedded_documents)} />
        <Metric label="Active jobs" value={status?.active_jobs?.length || 0} />
      </div>

      <section className="dashboard-grid pipeline-dashboard">
        <article className="data-section dashboard-wide">
          <h3 className="section-title">Stage Flow</h3>
          <PipelineStageFlow stages={stages} selectedStages={selectedStages} activeStageId={job?.stage_id || ""} />
        </article>
        <article className="data-section">
          <h3 className="section-title">Artifact Availability</h3>
          <CompositionBars rows={artifactAvailabilityRows} emptyText="No pipeline artifacts loaded." />
        </article>
        <article className="data-section">
          <h3 className="section-title">Freshness Classes</h3>
          <CompositionBars rows={freshnessBreakdown} emptyText="No freshness records loaded." />
        </article>
        <article className="data-section">
          <h3 className="section-title">Readiness Matrix</h3>
          <StatusMatrix rows={readinessRows} />
        </article>
      </section>

      {job ? <PipelineJobPanel job={job} log={jobLog} loading={loading} onCancel={() => void cancelJob()} /> : null}

      {view === "status" ? (
        <section className="pipeline-main">
          <section className="data-section">
            <h3 className="section-title">Readiness</h3>
            <div className="status-list">
              <StatusRow label="Manual only" value={formatCell(readiness.manual_only)} />
              <StatusRow label="Required raw ready" value={formatCell(readiness.required_raw_ready)} />
              <StatusRow label="SST available" value={formatCell(readiness.sst_available)} />
              <StatusRow label="Missing raw" value={formatCell(readiness.missing_required_raw)} />
              <StatusRow label="Missing corpus artifacts" value={formatCell(readiness.missing_core_artifacts)} />
              <StatusRow label="Database" value={formatCell(database.available)} />
              <StatusRow label="Ollama" value={formatCell(ollama.available)} />
            </div>
          </section>

          <section className="data-section">
            <h3 className="section-title">Active Background Jobs</h3>
            <DataTable
              columns={activeJobColumns}
              rows={activeJobRows}
              emptyText="No active manual pipeline jobs."
              rowKeyColumn="job_id"
              selectedKey={job?.job_id}
              onRowSelect={(row) => {
                const jobId = asString(row.job_id);
                if (!jobId) return;
                void refreshJob(jobId).then(() => setView("logs")).catch((err) => {
                  setError(err instanceof Error ? err.message : "Pipeline job status request failed");
                });
              }}
            />
          </section>

          <section className="data-section">
            <h3 className="section-title">Raw Sources</h3>
            <DataTable columns={artifactColumns} rows={rawRows} rowKeyColumn="id" />
          </section>

          <section className="data-section">
            <h3 className="section-title">Artifact Freshness</h3>
            <DataTable columns={freshnessColumns} rows={freshnessRows} rowKeyColumn="id" />
          </section>

          <section className="data-section">
            <h3 className="section-title">Derived Artifacts</h3>
            <DataTable columns={artifactColumns} rows={artifactRows} rowKeyColumn="id" />
          </section>

          <section className="data-section">
            <h3 className="section-title">Stage Catalog</h3>
            <DataTable columns={stageColumns} rows={stageRows} rowKeyColumn="id" />
          </section>
        </section>
      ) : null}

      {view === "run" ? (
        <section className="pipeline-main">
          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">Manual Batch Controls</h3>
              <button className="button" disabled={!canStart} onClick={() => void submitJob()} type="button">
                <Play size={15} aria-hidden="true" />
                Start Job
              </button>
            </div>

            <div className="pipeline-control-grid">
              <label className="settings-field" htmlFor="pipeline-tag" title="Optional run label stored in run metadata.">
                <span>Tag</span>
                <input id="pipeline-tag" className="field" onChange={(event) => setTag(event.target.value)} value={tag} />
              </label>
              <label className="settings-field" htmlFor="pipeline-embedding-model" title="Embedding model used by the embedding refresh stage.">
                <span>Embedding model</span>
                <input id="pipeline-embedding-model" className="field" onChange={(event) => setEmbeddingModel(event.target.value)} value={embeddingModel} />
              </label>
              <label className="settings-field" htmlFor="pipeline-batch-size" title="Embedding batch size for scripts/update_embeddings.py.">
                <span>Embedding batch</span>
                <input
                  id="pipeline-batch-size"
                  className="field"
                  max={256}
                  min={1}
                  onChange={(event) => setEmbeddingBatchSize(clampNumber(event.target.value, 1, 256))}
                  type="number"
                  value={embeddingBatchSize}
                />
              </label>
            </div>

            <div className="pipeline-switch-grid">
              <label className="checkbox-row" title="Plan selected commands and write a log without executing scripts.">
                <input checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} type="checkbox" />
                <span>Dry run</span>
              </label>
              <label className="checkbox-row" title="Skip SST preprocessing during ingest.">
                <input checked={skipSst} onChange={(event) => setSkipSst(event.target.checked)} type="checkbox" />
                <span>Skip SST</span>
              </label>
              <label className="checkbox-row" title="Required for non-dry-run database load to avoid duplicate appended rows.">
                <input checked={resetDatabase} onChange={(event) => setResetDatabase(event.target.checked)} type="checkbox" />
                <span>Reset database</span>
              </label>
              <label className="checkbox-row" title="Append --embed to scripts/load_db.py when the database load stage is selected.">
                <input checked={embedAfterLoad} onChange={(event) => setEmbedAfterLoad(event.target.checked)} type="checkbox" />
                <span>Embed during load</span>
              </label>
            </div>

            <label className="settings-field pipeline-notes" htmlFor="pipeline-notes" title="Optional notes stored in run metadata.">
              <span>Notes</span>
              <textarea id="pipeline-notes" className="textarea compact-textarea" onChange={(event) => setNotes(event.target.value)} value={notes} />
            </label>

            {!canStart && selectedStages.includes("load_db") && !dryRun && !resetDatabase ? (
              <p className="error-text">Non-dry-run database load requires Reset database.</p>
            ) : null}
          </section>

          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">Preflight</h3>
              <button className="button secondary-button" disabled={!selectedStages.length || loading} onClick={() => void refreshPreflight()} type="button">
                <RefreshCw size={15} aria-hidden="true" />
                Run Preflight
              </button>
            </div>
            {preflight ? (
              <>
                <div className="summary-strip">
                  <SummaryCell label="OK" value={formatCell(preflight.ok)} />
                  <SummaryCell label="Blockers" value={preflight.blockers.length} />
                  <SummaryCell label="Warnings" value={preflight.warnings.length} />
                  <SummaryCell label="Generated" value={preflight.generated_at} />
                </div>
                <DataTable columns={preflightColumns} rows={preflightRows} rowKeyColumn="id" />
              </>
            ) : (
              <p className="empty-state">No preflight run for the current selection.</p>
            )}
          </section>

          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">Stages</h3>
              <div className="choice-actions">
                <button className="button secondary-button" onClick={() => setSelectedStages(defaultFullStages)} type="button">Full rebuild</button>
                <button className="button secondary-button" onClick={() => setSelectedStages(stages.map((stage) => stage.id))} type="button">Select all</button>
                <button className="button secondary-button" onClick={() => setSelectedStages(["validate_raw"])} type="button">Validate only</button>
                <button className="button secondary-button" onClick={() => setSelectedStages([])} type="button">Clear</button>
              </div>
            </div>
            <div className="pipeline-stage-grid">
              {stages.map((stage) => (
                <label className="pipeline-stage-row" key={stage.id} title={stage.description}>
                  <input
                    checked={selectedStages.includes(stage.id)}
                    onChange={(event) => setSelectedStages(toggleSelected(selectedStages, stage.id, event.target.checked))}
                    type="checkbox"
                  />
                  <span>
                    <strong>{stage.label}</strong>
                    <small>{stage.id}</small>
                  </span>
                  {stage.destructive ? <em>destructive</em> : null}
                  {stage.expensive ? <em>expensive</em> : null}
                </label>
              ))}
            </div>
          </section>

          <section className="data-section">
            <h3 className="section-title">Selected Command Plan</h3>
            <DataTable columns={["id", "command", "destructive", "expensive"]} rows={selectedCommandRows} rowKeyColumn="id" />
          </section>
        </section>
      ) : null}

      {view === "logs" ? (
        <section className="pipeline-main">
          {job ? (
            <>
              <section className="data-section">
                <h3 className="section-title">Per-Stage Logs</h3>
                <StageLogList logs={jobLog?.stage_logs || []} />
              </section>
              <section className="data-section">
                <h3 className="section-title">Full Run Log</h3>
                <pre className="code-block report-block">{jobLog?.log || "No log yet."}</pre>
              </section>
            </>
          ) : (
            <p className="empty-state">No pipeline job selected.</p>
          )}
        </section>
      ) : null}

      {view === "history" ? (
        <section className="pipeline-main">
          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">Run History</h3>
              <button className="button secondary-button" disabled={loading} onClick={() => void loadStatus()} type="button">
                <RefreshCw size={15} aria-hidden="true" />
                Refresh
              </button>
            </div>
            <RunTimeline runs={runs.slice(0, 12)} selectedRunId={selectedRunId} />
            <DataTable
              columns={runColumns}
              rows={runRows}
              rowKeyColumn="run_id"
              selectedKey={selectedRunId}
              onRowSelect={(row) => {
                const runId = asString(row.run_id);
                if (!runId) return;
                void loadRun(runId).catch((err) => {
                  setError(err instanceof Error ? err.message : "Pipeline run detail request failed");
                });
              }}
            />
          </section>

          {runDetail ? (
            <section className="data-section">
              <h3 className="section-title">Selected Run</h3>
              <div className="summary-strip">
                <SummaryCell label="Status" value={runDetail.summary.status} />
                <SummaryCell label="Dry run" value={formatCell(runDetail.summary.dry_run)} />
                <SummaryCell label="Stages" value={runDetail.summary.stage_count} />
                <SummaryCell label="Duration" value={formatCell(runDetail.summary.duration_seconds)} />
              </div>
              <div className="status-list">
                <StatusRow label="Run ID" value={runDetail.summary.run_id} />
                <StatusRow label="Tag" value={runDetail.summary.tag || "NA"} />
                <StatusRow label="Started" value={runDetail.summary.started_at || "NA"} />
                <StatusRow label="Completed" value={runDetail.summary.completed_at || "NA"} />
                <StatusRow label="Manifest" value={runDetail.summary.manifest_path || "NA"} />
                <StatusRow label="Log" value={runDetail.summary.log_path || "NA"} />
                {runDetail.summary.error ? <StatusRow label="Error" value={runDetail.summary.error} /> : null}
              </div>
            </section>
          ) : null}

          {runDetail && diffRows.length ? (
            <section className="data-section">
              <h3 className="section-title">Artifact Diffs</h3>
              <DataTable columns={diffColumns} rows={diffRows} rowKeyColumn="id" />
            </section>
          ) : null}

          {runDetail ? (
            <section className="data-section">
              <h3 className="section-title">Per-Stage Logs</h3>
              <StageLogList logs={runDetail.stage_logs || []} />
            </section>
          ) : null}

          {runDetail ? (
            <section className="data-section">
              <h3 className="section-title">Manifest JSON</h3>
              <pre className="code-block report-block">{JSON.stringify(runDetail.manifest, null, 2)}</pre>
            </section>
          ) : null}

          {runDetail?.log_tail ? (
            <section className="data-section">
              <h3 className="section-title">Log Tail</h3>
              <pre className="code-block report-block">{runDetail.log_tail}</pre>
            </section>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

function PipelineStageFlow({
  stages,
  selectedStages,
  activeStageId,
}: {
  stages: PipelineStageInfo[];
  selectedStages: string[];
  activeStageId: string;
}) {
  if (!stages.length) return <p className="empty-state">No stage catalog loaded.</p>;
  return (
    <div className="lineage-flow stage-flow" aria-label="Manual pipeline stage flow">
      {stages.map((stage, index) => {
        const state = stage.id === activeStageId ? "active" : selectedStages.includes(stage.id) ? "selected" : "idle";
        return (
          <div className="lineage-node" data-state={state} key={stage.id} title={stage.description}>
            <span>{index + 1}</span>
            <strong>{stage.label}</strong>
            <em>{stage.id}</em>
            <small>{stage.expensive ? "expensive" : stage.destructive ? "destructive" : "standard"}</small>
          </div>
        );
      })}
    </div>
  );
}

function CompositionBars({
  rows,
  emptyText,
}: {
  rows: { label: string; value: number; total: number }[];
  emptyText: string;
}) {
  if (!rows.length) return <p className="empty-state">{emptyText}</p>;
  return (
    <div className="visual-bars">
      {rows.map((row) => {
        const safeTotal = Math.max(1, row.total || 0);
        const pct = Math.round((row.value / safeTotal) * 100);
        return (
          <div className="visual-bar-row" key={row.label}>
            <span>{row.label}</span>
            <div className="visual-track" aria-label={`${row.label}: ${pct}%`}>
              <div style={{ width: `${Math.min(100, pct)}%` }} />
            </div>
            <strong>{row.value.toLocaleString()}</strong>
            <em>{pct}%</em>
          </div>
        );
      })}
    </div>
  );
}

function StatusMatrix({ rows }: { rows: { label: string; value: string; ok: boolean }[] }) {
  return (
    <div className="status-matrix">
      {rows.map((row) => (
        <div className="status-tile" data-state={row.ok ? "ok" : "warn"} key={row.label}>
          <span>{row.label}</span>
          <strong>{row.value}</strong>
        </div>
      ))}
    </div>
  );
}

function RunTimeline({
  runs,
  selectedRunId,
}: {
  runs: PipelineRunSummary[];
  selectedRunId: string;
}) {
  if (!runs.length) return <p className="empty-state">No pipeline runs recorded.</p>;
  return (
    <div className="run-timeline" aria-label="Recent pipeline runs">
      {runs.map((run) => (
        <div className="run-tick" data-state={run.status} data-selected={run.run_id === selectedRunId} key={run.run_id} title={run.run_id}>
          <span>{run.status}</span>
          <strong>{run.stage_count}</strong>
          <small>{run.completed_at || run.started_at || "NA"}</small>
        </div>
      ))}
    </div>
  );
}

function PipelineJobPanel({
  job,
  log,
  loading,
  onCancel,
}: {
  job: PipelineJobStatus;
  log: PipelineLogResponse | null;
  loading: boolean;
  onCancel: () => void;
}) {
  const terminal = isTerminalJob(job.status);
  const percent = Math.max(0, Math.min(100, Number(job.percent) || 0));
  return (
    <section className="data-section job-panel">
      <div className="section-toolbar">
        <h3 className="section-title">Background Pipeline Job</h3>
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
        <SummaryCell label="Stage" value={job.stage_id || "NA"} />
        <SummaryCell label="Progress" value={`${percent.toFixed(1)}%`} />
      </div>
      <div className="meter-track job-meter" aria-label="Pipeline progress">
        <div style={{ width: `${percent}%` }} />
      </div>
      <div className="status-list">
        <StatusRow label="Run ID" value={job.run_id} />
        <StatusRow label="Message" value={job.message || "NA"} />
        <StatusRow label="Stages" value={job.stages.join(", ")} />
        <StatusRow label="Started" value={job.started_at || "NA"} />
        <StatusRow label="Updated" value={job.updated_at || "NA"} />
        <StatusRow label="Output" value={job.output_dir || "NA"} />
        <StatusRow label="Log bytes" value={formatCell(log?.bytes)} />
        {job.error ? <StatusRow label="Error" value={job.error} /> : null}
      </div>
    </section>
  );
}

function StageLogList({ logs }: { logs: PipelineStageLog[] }) {
  if (!logs.length) return <p className="empty-state">No per-stage log sections available.</p>;
  return (
    <div className="stage-log-list">
      {logs.map((stage) => (
        <details className="stage-log-panel" key={stage.stage_id} open={stage.status === "failed" || stage.status === "running"}>
          <summary>
            <span>
              <strong>{stage.label || stage.stage_id}</strong>
              <small>{stage.stage_id}</small>
            </span>
            <span>{stage.status || "pending"}</span>
            <span>{stage.duration_seconds === null || stage.duration_seconds === undefined ? "NA" : `${formatCell(stage.duration_seconds)}s`}</span>
            <span>{stage.line_count} lines</span>
          </summary>
          <div className="stage-log-meta">
            <StatusRow label="Command" value={stage.command || "NA"} />
            <StatusRow label="Return code" value={formatCell(stage.return_code)} />
            <StatusRow label="Bytes" value={formatCell(stage.bytes)} />
          </div>
          <pre className="code-block report-block">{stage.log || "No stage log captured."}</pre>
        </details>
      ))}
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

function artifactToRow(item: PipelineArtifactInfo): Record<string, unknown> {
  return {
    id: item.id,
    label: item.label,
    exists: item.exists,
    rows: item.rows,
    size_bytes: item.size_bytes,
    modified_at: item.modified_at,
    note: item.note,
    path: item.path,
  };
}

function freshnessToRow(item: PipelineArtifactFreshness): Record<string, unknown> {
  return {
    id: item.id,
    kind: item.kind,
    label: item.label,
    freshness_status: item.freshness_status,
    lineage_status: item.lineage_status,
    age_days: item.age_days,
    rows: item.rows,
    size_bytes: item.size_bytes,
    modified_at: item.modified_at,
    path: item.path,
  };
}

function stageToRow(stage: PipelineStageInfo): Record<string, unknown> {
  return {
    id: stage.id,
    label: stage.label,
    destructive: stage.destructive,
    expensive: stage.expensive,
    command: stage.command.join(" "),
    expected_inputs: stage.expected_inputs,
    expected_outputs: stage.expected_outputs,
  };
}

function stageToCommandRow(stage: PipelineStageInfo): Record<string, unknown> {
  return {
    id: stage.id,
    command: stage.command.join(" "),
    destructive: stage.destructive,
    expensive: stage.expensive,
  };
}

function commandPlanToRow(row: Record<string, unknown>): Record<string, unknown> {
  return {
    id: row.stage_id,
    command: row.display_command || row.command,
    destructive: row.destructive,
    expensive: row.expensive,
  };
}

function preflightCheckToRow(row: { id: string; label: string; status: string; severity: string; required: boolean; detail: string }): Record<string, unknown> {
  return {
    id: row.id,
    status: row.status,
    severity: row.severity,
    required: row.required,
    label: row.label,
    detail: row.detail,
  };
}

function runToRow(run: PipelineRunSummary): Record<string, unknown> {
  return {
    run_id: run.run_id,
    status: run.status,
    tag: run.tag,
    dry_run: run.dry_run,
    stage_count: run.stage_count,
    started_at: run.started_at,
    completed_at: run.completed_at,
    duration_seconds: run.duration_seconds,
    failed_stage: run.failed_stage,
  };
}

function jobToRow(job: PipelineJobStatus): Record<string, unknown> {
  return {
    job_id: job.job_id,
    status: job.status,
    phase: job.phase,
    stage_id: job.stage_id,
    percent: job.percent,
    updated_at: job.updated_at,
    message: job.message,
  };
}

function artifactDiffRows(manifest: Record<string, unknown> | undefined): Record<string, unknown>[] {
  const diffs = asRecord(manifest?.diffs);
  const rows = Array.isArray(diffs.artifacts) ? diffs.artifacts : [];
  return rows
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object" && !Array.isArray(row))
    .filter((row) => Boolean(row.changed))
    .map((row) => ({
      id: row.id,
      label: row.label,
      changed: row.changed,
      rows_before: row.rows_before,
      rows_after: row.rows_after,
      rows_delta: row.rows_delta,
      size_before: row.size_before,
      size_after: row.size_after,
      modified_after: row.modified_after,
    }));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function countRowsBy(rows: Record<string, unknown>[], key: string): { label: string; value: number; total: number }[] {
  const counts = new Map<string, number>();
  rows.forEach((row) => {
    const label = asString(row[key]) || "unknown";
    counts.set(label, (counts.get(label) || 0) + 1);
  });
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label, value, total: rows.length }));
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
