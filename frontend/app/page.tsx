"use client";

import { useEffect, useMemo, useState } from "react";
import { DataTable } from "@/components/DataTable";
import { getStats, getStatus } from "@/lib/api";
import { useAppPreferences } from "@/lib/preferences";
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
    purpose: "Corpus workbench for normalized tables, time series, sample detail, and evidence retrieval.",
    primary_controls: "View tabs, dataset, bay, station, source, date range, search, sort, evidence query, score threshold",
    outputs: "Tables, column profiles, time series, sample detail, ranked source documents, retrieval diagnostics",
  },
  {
    tab: "Data",
    route: "/data",
    purpose: "Domain workbench for observations, CTD, taxa, SST, derived analysis, and reliability outputs.",
    primary_controls: "View tabs, sample selectors, CTD variables, SST bounds, analysis filters, reliability checks",
    outputs: "Observation catalog, CTD profiles, taxa summaries, SST charts, derived-analysis tables, reliability matrices",
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
    tab: "Provenance",
    route: "/provenance",
    purpose: "Traceability register for source files, artifact versions, retrieval documents, embeddings, and upsert planning.",
    primary_controls: "Manifest document limit, embedding status inclusion, doc_id trace lookup, dry-run sample key limit",
    outputs: "Lineage manifest, document trace path, source/artifact hashes, embedding treatment, upsert dry-run plan",
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
  const { ui } = useAppPreferences();
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
  const sourceComposition = sourceOrder.map((source) => ({
    label: ui(sourceLabels[source]),
    value: stats?.documents[source] || 0,
    total: totalDocuments,
  }));
  const runtimeSignals = [
    { label: ui("API"), value: status?.status || "loading", ok: status?.status === "ok" },
    { label: ui("Database"), value: String(status?.database?.available ?? "loading"), ok: Boolean(status?.database?.available) },
    { label: ui("Model runtime"), value: String(status?.ollama?.available ?? "loading"), ok: Boolean(status?.ollama?.available) },
    { label: ui("Analysis docs"), value: String(stats?.analysis_docs ?? "loading"), ok: Boolean(stats?.analysis_docs) },
    { label: ui("Reliability docs"), value: String(stats?.reliability_docs ?? "loading"), ok: Boolean(stats?.reliability_docs) },
  ];
  const routeGroups = [
    { label: ui("Data"), routes: ["/explore", "/data", "/database"] },
    { label: ui("Operations"), routes: ["/pipeline", "/provenance", "/evaluation", "/system", "/debug"] },
    { label: ui("RAG"), routes: ["/chat"] },
  ];
  const architectureNodes = [
    { label: ui("Raw Sources"), detail: `${stats?.provenance_records ?? "..."} files` },
    { label: ui("Normalized Artifacts"), detail: `${stats?.ctd_casts ?? "..."} CTD casts` },
    { label: ui("Analysis"), detail: `${stats?.analysis_docs ?? "..."} documents` },
    { label: ui("Reliability"), detail: `${stats?.reliability_docs ?? "..."} documents` },
    { label: ui("Retrieval Store"), detail: `${totalDocuments || "..."} documents` },
    { label: ui("Interfaces"), detail: ui("query, inspect, evaluate") },
  ];

  return (
    <section>
      <header className="page-header">
        <h2>{ui("Overview")}</h2>
      </header>

      {error ? <p className="error-text">{error}</p> : null}

      <div className="grid metrics-grid">
        <MetricCard label={ui("Retrieval documents")} value={totalDocuments} />
        <MetricCard label={ui("Registered samples")} value={stats?.samples} />
        <MetricCard label={ui("CTD casts")} value={stats?.ctd_casts} />
        <MetricCard label={ui("SST days")} value={stats?.sst_days} />
      </div>

      <section className="data-section architecture-panel">
        <h3 className="section-title">{ui("Architecture")}</h3>
        <ArchitectureFlow nodes={architectureNodes} />
      </section>

      <section className="dashboard-grid">
        <article className="data-section">
          <h3 className="section-title">{ui("Source Balance")}</h3>
          <CompositionBars rows={sourceComposition} />
        </article>

        <article className="data-section">
          <h3 className="section-title">{ui("Runtime Signals")}</h3>
          <StatusMatrix rows={runtimeSignals} />
        </article>

        <article className="data-section dashboard-wide">
          <h3 className="section-title">{ui("Operational Surface")}</h3>
          <RouteRail groups={routeGroups} />
        </article>
      </section>

      <section className="data-section overview-register">
        <h3 className="section-title">{ui("Interface Register")}</h3>
        <DataTable
          columns={["tab", "route", "purpose", "primary_controls", "outputs"]}
          rows={interfaceTabs}
          rowKeyColumn="route"
        />
      </section>
    </section>
  );
}

function ArchitectureFlow({ nodes }: { nodes: { label: string; detail: string }[] }) {
  return (
    <div className="architecture-flow" aria-label="System architecture flow">
      {nodes.map((node, index) => (
        <div className="architecture-step" key={node.label}>
          <div className="architecture-node">
            <span>{node.label}</span>
            <strong>{node.detail}</strong>
          </div>
          {index < nodes.length - 1 ? <div className="architecture-edge" aria-hidden="true" /> : null}
        </div>
      ))}
    </div>
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

function CompositionBars({ rows }: { rows: { label: string; value: number; total: number }[] }) {
  return (
    <div className="visual-bars">
      {rows.map((row) => {
        const pct = row.total ? Math.round((row.value / row.total) * 100) : 0;
        return (
          <div className="visual-bar-row" key={row.label}>
            <span>{row.label}</span>
            <div className="visual-track" aria-label={`${row.label}: ${pct}%`}>
              <div style={{ width: `${pct}%` }} />
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

function RouteRail({ groups }: { groups: { label: string; routes: string[] }[] }) {
  const total = groups.reduce((sum, group) => sum + group.routes.length, 0);
  return (
    <div className="route-rail" aria-label="Interface route groups">
      {groups.map((group) => {
        const pct = total ? (group.routes.length / total) * 100 : 0;
        return (
          <div className="route-segment" key={group.label} style={{ flexBasis: `${pct}%` }} title={group.routes.join(", ")}>
            <span>{group.label}</span>
            <strong>{group.routes.length}</strong>
          </div>
        );
      })}
    </div>
  );
}
