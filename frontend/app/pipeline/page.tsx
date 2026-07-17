"use client";

import { useEffect, useMemo, useState } from "react";
import { Play, RefreshCw, Square } from "lucide-react";
import { DataTable, formatCell } from "@/components/DataTable";
import {
  cancelPipelineJob,
  getPipelineJob,
  getPipelineJobLog,
  getPipelineStatus,
  startPipelineJob,
} from "@/lib/api";
import type {
  PipelineArtifactInfo,
  PipelineJobStatus,
  PipelineLogResponse,
  PipelineStageInfo,
  PipelineStatusResponse,
} from "@/types";

type PipelineView = "status" | "run" | "logs";

const artifactColumns = ["label", "exists", "rows", "size_bytes", "modified_at", "note", "path"];
const stageColumns = ["id", "label", "destructive", "expensive", "command", "expected_inputs", "expected_outputs"];

export default function PipelinePage() {
  const [view, setView] = useState<PipelineView>("status");
  const [status, setStatus] = useState<PipelineStatusResponse | null>(null);
  const [selectedStages, setSelectedStages] = useState<string[]>(["validate_raw"]);
  const [tag, setTag] = useState("");
  const [notes, setNotes] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [skipSst, setSkipSst] = useState(false);
  const [resetDatabase, setResetDatabase] = useState(false);
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [embeddingBatchSize, setEmbeddingBatchSize] = useState(32);
  const [job, setJob] = useState<PipelineJobStatus | null>(null);
  const [jobLog, setJobLog] = useState<PipelineLogResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadStatus() {
    setLoading(true);
    setError("");
    try {
      const payload = await getPipelineStatus();
      setStatus(payload);
      const embeddingDefault = asString(payload.ollama.embedding_model) || asString(payload.database.embedding_model);
      setEmbeddingModel((current) => current || embeddingDefault);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline status request failed");
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
  const selectedCommandRows = selectedStageInfos.map(stageToCommandRow);
  const canStart = selectedStages.length > 0 && !loading && (!selectedStages.includes("load_db") || dryRun || resetDatabase);

  async function submitJob() {
    if (!selectedStages.length) return;
    setLoading(true);
    setError("");
    try {
      const started = await startPipelineJob({
        stages: selectedStages,
        tag: tag || undefined,
        dry_run: dryRun,
        skip_sst: skipSst,
        reset_database: resetDatabase,
        embedding_model: embeddingModel || undefined,
        embedding_batch_size: embeddingBatchSize,
        notes: notes || undefined,
      });
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
      </div>

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
            <h3 className="section-title">Raw Sources</h3>
            <DataTable columns={artifactColumns} rows={rawRows} rowKeyColumn="id" />
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
              <h3 className="section-title">Stages</h3>
              <div className="choice-actions">
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
            <section className="data-section">
              <h3 className="section-title">Run Log</h3>
              <pre className="code-block report-block">{jobLog?.log || "No log yet."}</pre>
            </section>
          ) : (
            <p className="empty-state">No pipeline job selected.</p>
          )}
        </section>
      ) : null}
    </section>
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
        <StatusRow label="Output" value={job.output_dir || "NA"} />
        <StatusRow label="Log bytes" value={formatCell(log?.bytes)} />
        {job.error ? <StatusRow label="Error" value={job.error} /> : null}
      </div>
    </section>
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

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
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
