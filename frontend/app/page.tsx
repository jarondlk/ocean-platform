"use client";

import { useEffect, useMemo, useState } from "react";
import { DataTable } from "@/components/DataTable";
import { getStats, getStatus } from "@/lib/api";
import type { CorpusStats, StatusResponse } from "@/types";

const sourceOrder = ["ctd", "metagenome", "remote_sensing"];
const sourceLabels: Record<string, string> = {
  ctd: "CTD casts",
  metagenome: "Metagenome samples",
  remote_sensing: "Satellite SST days",
};

const interfaceTabs = [
  {
    tab: "Overview",
    route: "/",
    purpose: "System-level register for corpus size, source balance, service health, and interface map.",
    primary_controls: "Read-only refresh by page load",
    outputs: "Corpus metrics, service status, tab feature inventory",
  },
  {
    tab: "Explore",
    route: "/explore",
    purpose: "General data exploration across normalized and analysis datasets.",
    primary_controls: "Dataset, bay, station, source, date range, search, sort, columns, sample drill-down",
    outputs: "Tables, column profiles, time series, sample-linked evidence",
  },
  {
    tab: "Data",
    route: "/data",
    purpose: "Domain-specific CTD, taxa, and SST inspection by sample or date range.",
    primary_controls: "Sample selector, CTD variable selector, SST date bounds",
    outputs: "CTD profiles, taxa summaries, SST observations and daily aggregates",
  },
  {
    tab: "Analysis",
    route: "/analysis",
    purpose: "Inspection of ecological pre-analysis and reliability outputs.",
    primary_controls: "Co-occurrence pair limit, table limit, analysis sections",
    outputs: "Trends, correlations, diversity, co-occurrence, reliability tables and summaries",
  },
  {
    tab: "Database",
    route: "/database",
    purpose: "PostgreSQL schema and read-only SQL inspection for expert debugging.",
    primary_controls: "Table selector, ordering, heavy-column toggle, read-only SQL editor",
    outputs: "Schema metadata, table rows, SQL result sets",
  },
  {
    tab: "Pipeline",
    route: "/pipeline",
    purpose: "Manual batch control for ingestion, corpus rebuilds, analysis, database load, and embeddings.",
    primary_controls: "Stage selection, dry run, skip SST, reset database, embedding batch/model, cancel",
    outputs: "Readiness checks, artifact registry, background job progress, persisted logs",
  },
  {
    tab: "Evaluation",
    route: "/evaluation",
    purpose: "Benchmark control and evaluation artifact inspection.",
    primary_controls: "Run browser, question catalog, standard/ablation controls, comparison, cancel",
    outputs: "Metrics, traces, reports, background job progress, CSV-backed run records",
  },
  {
    tab: "Chat",
    route: "/chat",
    purpose: "Expert RAG query interface with retrieval and generation knobs.",
    primary_controls: "Query, k, filters, retrieval weights, model, context injection, sampling controls",
    outputs: "Citation-grounded answer, source list, model/options trace",
  },
  {
    tab: "Evidence",
    route: "/evidence",
    purpose: "Source-level evidence retrieval without answer generation.",
    primary_controls: "Query, source type, bay, date bounds, retrieval parameters",
    outputs: "Ranked source documents and retrieval diagnostics",
  },
  {
    tab: "System",
    route: "/system",
    purpose: "Operational status page for services, artifacts, models, and environment defaults.",
    primary_controls: "Refresh and model/status inspection",
    outputs: "Health cards, artifact inventory, model availability, configuration values",
  },
  {
    tab: "Debug",
    route: "/debug",
    purpose: "Raw debug surface for backend state and page/API diagnostics.",
    primary_controls: "Expandable debug blocks",
    outputs: "Routes, config, datasets, cache info, artifacts, selected environment",
  },
];

export default function OverviewPage() {
  const [stats, setStats] = useState<CorpusStats | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    Promise.all([getStats(), getStatus()])
      .then(([statsData, statusData]) => {
        setStats(statsData);
        setStatus(statusData);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const totalDocuments = useMemo(() => {
    if (!stats) return 0;
    return Object.values(stats.documents).reduce((sum, value) => sum + value, 0);
  }, [stats]);

  return (
    <section>
      <header className="page-header">
        <h2>Overview</h2>
      </header>

      {error ? <p className="error-text">{error}</p> : null}

      <div className="grid metrics-grid">
        <MetricCard label="Retrieval documents" value={totalDocuments} />
        <MetricCard label="Registered samples" value={stats?.samples} />
        <MetricCard label="CTD casts" value={stats?.ctd_casts} />
        <MetricCard label="SST days" value={stats?.sst_days} />
      </div>

      <div className="grid two-column" style={{ marginTop: 16 }}>
        <article className="card">
          <h3 className="section-title">Documents by source</h3>
          <div className="source-bars">
            {sourceOrder.map((source) => {
              const value = stats?.documents[source] || 0;
              const pct = totalDocuments ? Math.round((value / totalDocuments) * 100) : 0;
              return (
                <div className="source-bar-row" key={source}>
                  <span>{sourceLabels[source]}</span>
                  <strong>{value}</strong>
                  <span>{pct}%</span>
                </div>
              );
            })}
          </div>
        </article>

        <article className="card">
          <h3 className="section-title">System</h3>
          <div className="status-list">
            <StatusRow label="API" value={status?.status || "loading"} />
            <StatusRow
              label="Database"
              value={String(status?.database?.available ?? "loading")}
            />
            <StatusRow
              label="Ollama"
              value={String(status?.ollama?.available ?? "loading")}
            />
            <StatusRow
              label="Analysis documents"
              value={String(stats?.analysis_docs ?? "loading")}
            />
            <StatusRow
              label="Reliability documents"
              value={String(stats?.reliability_docs ?? "loading")}
            />
          </div>
        </article>
      </div>

      <section className="data-section overview-register">
        <h3 className="section-title">Interface Register</h3>
        <DataTable
          columns={["tab", "route", "purpose", "primary_controls", "outputs"]}
          rows={interfaceTabs}
          rowKeyColumn="route"
        />
      </section>
    </section>
  );
}

function MetricCard({ label, value }: { label: string; value?: number }) {
  return (
    <article className="card">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value ?? "..."}</p>
    </article>
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
