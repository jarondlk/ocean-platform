"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { getDebugState, getModels, getStats, getStatus } from "@/lib/api";
import type { CorpusStats, DebugState, ModelsResponse, StatusResponse } from "@/types";

type ArtifactRow = {
  name: string;
  path?: string;
  exists?: boolean;
  is_file?: boolean;
  is_dir?: boolean;
  size_bytes?: number;
  rows?: number;
};

export default function SystemPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [stats, setStats] = useState<CorpusStats | null>(null);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [debug, setDebug] = useState<DebugState | null>(null);
  const [refreshSeconds, setRefreshSeconds] = useState(0);
  const [lastUpdated, setLastUpdated] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [statusData, statsData, modelsData, debugData] = await Promise.all([
        getStatus(),
        getStats(),
        getModels(),
        getDebugState(),
      ]);
      setStatus(statusData);
      setStats(statsData);
      setModels(modelsData);
      setDebug(debugData);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "System request failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!refreshSeconds) return;
    const id = window.setInterval(() => void load(), refreshSeconds * 1000);
    return () => window.clearInterval(id);
  }, [load, refreshSeconds]);

  const totalDocuments = useMemo(() => {
    if (!stats) return 0;
    return Object.values(stats.documents).reduce((sum, value) => sum + value, 0);
  }, [stats]);

  const artifacts = useMemo<ArtifactRow[]>(() => {
    const rows = Object.entries(asRecord(debug?.artifacts)).map(([name, value]) => ({
      name,
      ...asRecord(value),
    })) as ArtifactRow[];
    return rows.sort((a, b) => Number(a.exists) - Number(b.exists) || a.name.localeCompare(b.name));
  }, [debug]);

  const existingArtifacts = artifacts.filter((artifact) => artifact.exists).length;
  const healthRows = [
    { label: "API", value: status?.status || "loading", ok: status?.status === "ok" },
    {
      label: "Database",
      value: String(asRecord(status?.database).available ?? "loading"),
      ok: asRecord(status?.database).available === true,
    },
    {
      label: "Ollama",
      value: String(asRecord(status?.ollama).available ?? "loading"),
      ok: asRecord(status?.ollama).available === true,
    },
    {
      label: "Artifacts",
      value: `${existingArtifacts}/${artifacts.length || "..."}`,
      ok: Boolean(artifacts.length && existingArtifacts === artifacts.length),
    },
    {
      label: "Models",
      value: models?.available ? `${models.models.length}` : "unavailable",
      ok: models?.available === true,
    },
  ];

  return (
    <section>
      <header className="page-header">
        <h2>System</h2>
      </header>

      <div className="section-toolbar system-toolbar">
        <span className="empty-state">
          {loading ? "Refreshing." : lastUpdated ? `Updated ${lastUpdated}` : "Not loaded."}
        </span>
        <div className="system-actions">
          <label className="settings-field" htmlFor="system-refresh" title="Automatically refresh system diagnostics.">
            <span>Auto-refresh</span>
            <select
              id="system-refresh"
              className="field"
              value={refreshSeconds}
              onChange={(event) => setRefreshSeconds(Number(event.target.value))}
            >
              <option value={0}>Off</option>
              <option value={15}>15s</option>
              <option value={30}>30s</option>
              <option value={60}>60s</option>
            </select>
          </label>
          <button className="button secondary-button" onClick={() => void load()} type="button">
            <RefreshCw size={15} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      <div className="grid metrics-grid system-metrics">
        <Metric label="Retrieval documents" value={totalDocuments} />
        <Metric label="Samples" value={stats?.samples ?? "..."} />
        <Metric label="Artifacts present" value={`${existingArtifacts}/${artifacts.length || "..."}`} />
        <Metric label="Chat models" value={models?.models.length ?? "..."} />
      </div>

      <section className="system-section">
        <h3 className="section-title">Health</h3>
        <div className="health-grid">
          {healthRows.map((row) => (
            <div className="health-card" key={row.label}>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
              <StatusPill ok={row.ok} />
            </div>
          ))}
        </div>
      </section>

      <section className="system-section">
        <h3 className="section-title">Artifacts</h3>
        <div className="table-wrap compact-table-wrap">
          <table className="artifact-table">
            <thead>
              <tr>
                <th>Artifact</th>
                <th>State</th>
                <th>Rows</th>
                <th>Size</th>
                <th>Path</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map((artifact) => (
                <tr key={artifact.name}>
                  <td>{artifact.name}</td>
                  <td>
                    <StatusPill ok={artifact.exists === true} label={artifact.exists ? "present" : "missing"} />
                  </td>
                  <td>{artifact.rows ?? "NA"}</td>
                  <td>{formatBytes(artifact.size_bytes)}</td>
                  <td>{artifact.path || "NA"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="system-section">
        <h3 className="section-title">Models</h3>
        <div className="status-list">
          <StatusRow label="Ollama URL" value={models?.ollama_base_url || "loading"} />
          <StatusRow label="Default chat model" value={models?.default_model || "loading"} />
          <StatusRow label="Embedding model" value={models?.embedding_model || "loading"} />
        </div>
        <div className="table-wrap compact-table-wrap">
          <table className="model-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Size</th>
                <th>Modified</th>
              </tr>
            </thead>
            <tbody>
              {(models?.models || []).map((model) => (
                <tr key={model.name}>
                  <td>{model.name}</td>
                  <td>{formatBytes(model.size)}</td>
                  <td>{model.modified_at || "NA"}</td>
                </tr>
              ))}
              {!models?.models.length ? (
                <tr>
                  <td colSpan={3}>No chat models returned.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <div className="system-register">
        <StatusSection title="Database" rows={status?.database || { available: "loading" }} />
        <StatusSection title="Ollama" rows={status?.ollama || { available: "loading" }} />
        <StatusSection title="Config" rows={asRecord(debug?.config)} />
        <StatusSection title="Cache" rows={asRecord(debug?.cache)} />
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <article className="card">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
    </article>
  );
}

function StatusPill({ ok, label }: { ok?: boolean; label?: string }) {
  return <span className={`status-pill ${ok ? "ok" : "bad"}`}>{label || (ok ? "ok" : "check")}</span>;
}

function StatusSection({ title, rows }: { title: string; rows: Record<string, unknown> }) {
  return (
    <section className="system-section">
      <h3 className="section-title">{title}</h3>
      <table className="system-table">
        <tbody>
          {Object.entries(rows).map(([key, value]) => (
            <tr key={key}>
              <th scope="row">{key}</th>
              <td>{formatValue(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
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

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.join("\n") : "none";
  if (value && typeof value === "object") return JSON.stringify(value, null, 2);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value === null || value === undefined) return "NA";
  return String(value);
}

function formatBytes(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "NA";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
}
