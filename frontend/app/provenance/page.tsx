"use client";

import { useEffect, useMemo, useState } from "react";
import { FileJson, RefreshCw, Search } from "lucide-react";
import { DataTable, formatCell } from "@/components/DataTable";
import {
  getProvenanceManifest,
  getProvenanceTrace,
  getProvenanceUpsertDryRun,
} from "@/lib/api";
import type {
  ProvenanceManifestResponse,
  ProvenanceTraceResponse,
  UpsertDryRunResponse,
} from "@/types";

type ProvenanceView = "manifest" | "trace" | "upsert";

const sourceColumns = [
  "id",
  "source_dataset",
  "role",
  "exists",
  "registry_seen",
  "registry_records",
  "child_count",
  "sha256",
  "collection_fingerprint",
  "latest_processing_run",
  "modified_at",
  "path",
];
const artifactColumns = [
  "id",
  "kind",
  "label",
  "exists",
  "row_count",
  "schema_hash",
  "sha256",
  "producer_stage",
  "table_name",
  "key_columns",
  "source_file_ids",
  "input_artifact_ids",
  "modified_at",
  "path",
];
const documentColumns = [
  "doc_id",
  "source_type",
  "sample_id",
  "event_id",
  "time",
  "content_hash",
  "metadata_hash",
  "source_record_keys",
  "source_artifact_ids",
];
const embeddingColumns = [
  "doc_id",
  "embedding_status",
  "embedding_model",
  "embedding_dim",
  "embedded",
  "embedding_source",
  "notes",
];
const tracePathColumns = ["step", "level", "key", "keys"];
const upsertColumns = [
  "table",
  "artifact_id",
  "key_columns",
  "database_available",
  "incoming_count",
  "existing_count",
  "planned_inserts",
  "matched_existing",
  "candidate_updates",
  "stale_existing",
  "embedding_refresh_candidates",
  "notes",
];

export default function ProvenancePage() {
  const [view, setView] = useState<ProvenanceView>("manifest");
  const [manifest, setManifest] = useState<ProvenanceManifestResponse | null>(null);
  const [trace, setTrace] = useState<ProvenanceTraceResponse | null>(null);
  const [upsertPlan, setUpsertPlan] = useState<UpsertDryRunResponse | null>(null);
  const [docId, setDocId] = useState("");
  const [limitDocuments, setLimitDocuments] = useState(100);
  const [includeEmbeddings, setIncludeEmbeddings] = useState(true);
  const [limitKeys, setLimitKeys] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadManifest() {
    setLoading(true);
    setError("");
    try {
      const payload = await getProvenanceManifest({
        limit_documents: limitDocuments,
        include_embeddings: includeEmbeddings,
      });
      setManifest(payload);
      const firstDocId = asString(payload.documents[0]?.doc_id);
      setDocId((current) => current || firstDocId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Provenance manifest request failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadTrace(targetDocId = docId) {
    if (!targetDocId) return;
    setLoading(true);
    setError("");
    try {
      setTrace(await getProvenanceTrace(targetDocId));
      setView("trace");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document trace request failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadUpsertDryRun() {
    setLoading(true);
    setError("");
    try {
      setUpsertPlan(await getProvenanceUpsertDryRun(limitKeys));
      setView("upsert");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upsert dry-run request failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadManifest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const summary = asRecord(manifest?.summary);
  const sourceRows = useMemo(() => (manifest?.source_files || []).map(sourceToRow), [manifest]);
  const artifactRows = useMemo(() => (manifest?.artifacts || []).map(artifactToRow), [manifest]);
  const documentRows = useMemo(() => (manifest?.documents || []).map(documentToRow), [manifest]);
  const embeddingRows = useMemo(() => manifest?.embeddings || [], [manifest]);
  const tracePayload = asRecord(trace?.trace);
  const traceDocument = asRecord(tracePayload.document);
  const traceEmbedding = asRecord(tracePayload.embedding);
  const traceArtifacts = asRecords(tracePayload.artifacts).map(artifactToRow);
  const traceSourceFiles = asRecords(tracePayload.source_files).map(sourceToRow);
  const tracePathRows = asRecords(tracePayload.trace_path).map((row, index) => ({
    step: index + 1,
    ...row,
  }));
  const upsertSummary = asRecord(upsertPlan?.summary);
  const database = asRecord(upsertPlan?.database);
  const artifactClassRows = countBy(manifest?.artifacts || [], "kind");
  const sourceRegistrationRows = [
    {
      label: "Registered",
      value: sourceRows.filter((row) => row.registry_seen === true).length,
      total: sourceRows.length,
    },
    {
      label: "Existing",
      value: sourceRows.filter((row) => row.exists === true).length,
      total: sourceRows.length,
    },
    {
      label: "Collections",
      value: sourceRows.filter((row) => String(row.role || "").includes("collection")).length,
      total: sourceRows.length,
    },
  ];
  const embeddingStatusRows = countBy(embeddingRows, "embedding_status");
  const lineageNodes = [
    {
      label: "Raw Sources",
      value: formatCell(summary.source_files),
      meta: `${formatCell(summary.registered_source_records)} registry records`,
    },
    {
      label: "Artifacts",
      value: `${formatCell(summary.existing_artifacts)} / ${formatCell(summary.artifacts)}`,
      meta: "existing / tracked",
    },
    {
      label: "Documents",
      value: formatCell(summary.documents),
      meta: `limit ${formatCell(summary.document_limit)}`,
    },
    {
      label: "Embeddings",
      value: formatCell(summary.embedded_documents_in_manifest),
      meta: `${formatCell(summary.embedding_model)} (${formatCell(summary.embedding_dim)})`,
    },
    {
      label: "Dry-Run",
      value: upsertPlan ? formatCell(upsertSummary.planned_inserts) : "manual",
      meta: upsertPlan ? "planned inserts" : "not loaded",
    },
  ];

  return (
    <section>
      <header className="page-header">
        <h2>Provenance</h2>
      </header>

      <div className="data-tabs" role="tablist" aria-label="Provenance views">
        <TabButton active={view === "manifest"} label="Manifest" onClick={() => setView("manifest")} />
        <TabButton active={view === "trace"} label="Document Trace" onClick={() => setView("trace")} />
        <TabButton active={view === "upsert"} label="Upsert Dry-Run" onClick={() => setView("upsert")} />
      </div>

      <div className="section-toolbar">
        <span className="empty-state">
          {loading ? "Loading provenance state." : `${formatCell(summary.documents)} manifest documents. ${formatCell(summary.artifacts)} tracked artifacts.`}
        </span>
        <button className="button secondary-button" onClick={() => void loadManifest()} type="button">
          <RefreshCw size={15} aria-hidden="true" />
          Refresh
        </button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}

      <div className="grid metrics-grid system-metrics">
        <Metric label="Source files" value={formatCell(summary.source_files)} />
        <Metric label="Registry records" value={formatCell(summary.registered_source_records)} />
        <Metric label="Existing artifacts" value={formatCell(summary.existing_artifacts)} />
        <Metric label="Documents indexed" value={formatCell(summary.documents)} />
        <Metric label="Embedded in view" value={formatCell(summary.embedded_documents_in_manifest)} />
      </div>

      <section className="dashboard-grid provenance-dashboard">
        <article className="data-section dashboard-wide">
          <h3 className="section-title">Lineage Flow</h3>
          <LineageFlow nodes={lineageNodes} />
        </article>
        <article className="data-section">
          <h3 className="section-title">Artifact Classes</h3>
          <CompositionBars rows={artifactClassRows} emptyText="No artifact classes loaded." />
        </article>
        <article className="data-section">
          <h3 className="section-title">Source Registration</h3>
          <CompositionBars rows={sourceRegistrationRows} emptyText="No source files loaded." />
        </article>
        <article className="data-section">
          <h3 className="section-title">Embedding Status</h3>
          <CompositionBars rows={embeddingStatusRows} emptyText="Embedding status is not included." />
        </article>
      </section>

      {view === "manifest" ? (
        <section className="provenance-main">
          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">Manifest Controls</h3>
              <button className="button secondary-button" disabled={loading} onClick={() => void loadManifest()} type="button">
                <FileJson size={15} aria-hidden="true" />
                Build Manifest
              </button>
            </div>
            <div className="provenance-control-grid">
              <label className="settings-field" htmlFor="provenance-limit-documents" title="Maximum retrieval documents included in the visible manifest payload.">
                <span>Document limit</span>
                <input
                  className="field"
                  id="provenance-limit-documents"
                  max={10000}
                  min={1}
                  onChange={(event) => setLimitDocuments(clampNumber(event.target.value, 1, 10000))}
                  type="number"
                  value={limitDocuments}
                />
              </label>
              <label className="checkbox-row provenance-checkbox" title="Query database embedding status for the manifest document window.">
                <input checked={includeEmbeddings} onChange={(event) => setIncludeEmbeddings(event.target.checked)} type="checkbox" />
                <span>Include embedding treatment</span>
              </label>
            </div>
          </section>

          <section className="data-section">
            <h3 className="section-title">Source Files</h3>
            <DataTable columns={sourceColumns} rows={sourceRows} rowKeyColumn="id" />
          </section>

          <section className="data-section">
            <h3 className="section-title">Artifact Versions</h3>
            <DataTable columns={artifactColumns} rows={artifactRows} rowKeyColumn="id" />
          </section>

          <section className="data-section">
            <h3 className="section-title">Document Trace Index</h3>
            <DataTable
              columns={documentColumns}
              rows={documentRows}
              rowKeyColumn="doc_id"
              selectedKey={docId}
              onRowSelect={(row) => {
                const selectedDocId = asString(row.doc_id);
                if (!selectedDocId) return;
                setDocId(selectedDocId);
                void loadTrace(selectedDocId);
              }}
            />
          </section>

          <section className="data-section">
            <h3 className="section-title">Embedding Treatment</h3>
            <DataTable columns={embeddingColumns} rows={embeddingRows} rowKeyColumn="doc_id" />
          </section>

          <section className="data-section">
            <h3 className="section-title">Limitations</h3>
            <pre className="code-block">{JSON.stringify(manifest?.limitations || [], null, 2)}</pre>
          </section>
        </section>
      ) : null}

      {view === "trace" ? (
        <section className="provenance-main">
          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">Document Lookup</h3>
              <button className="button" disabled={!docId || loading} onClick={() => void loadTrace()} type="button">
                <Search size={15} aria-hidden="true" />
                Trace
              </button>
            </div>
            <div className="provenance-search-grid">
              <label className="settings-field" htmlFor="provenance-doc-id" title="Retrieval document identifier returned by citations and stored in retrieval_document.doc_id.">
                <span>doc_id</span>
                <input
                  className="field"
                  id="provenance-doc-id"
                  onChange={(event) => setDocId(event.target.value)}
                  value={docId}
                />
              </label>
            </div>
          </section>

          {trace ? (
            <>
              <section className="data-section">
                <h3 className="section-title">Trace Summary</h3>
                <div className="summary-strip">
                  <SummaryCell label="Found" value={formatCell(trace.found)} />
                  <SummaryCell label="Source" value={formatCell(traceDocument.source_type)} />
                  <SummaryCell label="Sample" value={formatCell(traceDocument.sample_id)} />
                  <SummaryCell label="Embedding" value={formatCell(traceEmbedding.embedding_status)} />
                </div>
              </section>

              <section className="data-section">
                <h3 className="section-title">Trace Rail</h3>
                <TraceRail rows={tracePathRows} />
              </section>

              <section className="trace-grid">
                <article className="data-section">
                  <h3 className="section-title">Trace Path</h3>
                  <DataTable columns={tracePathColumns} rows={tracePathRows} rowKeyColumn="step" />
                </article>
                <article className="data-section">
                  <h3 className="section-title">Document</h3>
                  <table className="debug-table">
                    <tbody>
                      {Object.entries(traceDocument).map(([key, value]) => (
                        <tr key={key}>
                          <th scope="row">{key}</th>
                          <td>{formatCell(value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </article>
              </section>

              <section className="data-section">
                <h3 className="section-title">Derived Artifacts</h3>
                <DataTable columns={artifactColumns} rows={traceArtifacts} rowKeyColumn="id" />
              </section>

              <section className="data-section">
                <h3 className="section-title">Source Files</h3>
                <DataTable columns={sourceColumns} rows={traceSourceFiles} rowKeyColumn="id" />
              </section>

              <section className="data-section">
                <h3 className="section-title">Raw Trace Payload</h3>
                <pre className="code-block report-block">{JSON.stringify(trace, null, 2)}</pre>
              </section>
            </>
          ) : (
            <p className="empty-state">No document trace loaded.</p>
          )}
        </section>
      ) : null}

      {view === "upsert" ? (
        <section className="provenance-main">
          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">Dry-Run Controls</h3>
              <button className="button" disabled={loading} onClick={() => void loadUpsertDryRun()} type="button">
                <RefreshCw size={15} aria-hidden="true" />
                Run Dry-Run
              </button>
            </div>
            <div className="provenance-control-grid">
              <label className="settings-field" htmlFor="provenance-limit-keys" title="Maximum example keys retained per insert/stale group.">
                <span>Sample key limit</span>
                <input
                  className="field"
                  id="provenance-limit-keys"
                  max={250}
                  min={0}
                  onChange={(event) => setLimitKeys(clampNumber(event.target.value, 0, 250))}
                  type="number"
                  value={limitKeys}
                />
              </label>
            </div>
          </section>

          {upsertPlan ? (
            <>
              <section className="data-section">
                <h3 className="section-title">Plan Summary</h3>
                <div className="summary-strip">
                  <SummaryCell label="Database" value={formatCell(database.available)} />
                  <SummaryCell label="Incoming rows" value={formatCell(upsertSummary.incoming_rows)} />
                  <SummaryCell label="Planned inserts" value={formatCell(upsertSummary.planned_inserts)} />
                  <SummaryCell label="Embedding refresh" value={formatCell(upsertSummary.embedding_refresh_candidates)} />
                </div>
              </section>

              <section className="data-section">
                <h3 className="section-title">Mutation Candidates</h3>
                <CompositionBars
                  rows={[
                    { label: "Planned inserts", value: toNumber(upsertSummary.planned_inserts), total: toNumber(upsertSummary.incoming_rows) },
                    { label: "Candidate updates", value: toNumber(upsertSummary.candidate_updates), total: toNumber(upsertSummary.incoming_rows) },
                    { label: "Stale existing", value: toNumber(upsertSummary.stale_existing), total: Math.max(1, toNumber(upsertSummary.incoming_rows)) },
                    { label: "Embedding refresh", value: toNumber(upsertSummary.embedding_refresh_candidates), total: Math.max(1, toNumber(upsertSummary.incoming_rows)) },
                  ]}
                  emptyText="No dry-run candidate counts loaded."
                />
              </section>

              <section className="data-section">
                <h3 className="section-title">Table Plans</h3>
                <DataTable columns={upsertColumns} rows={upsertPlan.table_plans} rowKeyColumn="table" />
              </section>

              <section className="trace-grid">
                <article className="data-section">
                  <h3 className="section-title">Warnings</h3>
                  <pre className="code-block">{JSON.stringify(upsertPlan.warnings, null, 2)}</pre>
                </article>
                <article className="data-section">
                  <h3 className="section-title">Database Errors</h3>
                  <pre className="code-block">{JSON.stringify(database.errors || [], null, 2)}</pre>
                </article>
              </section>

              <section className="data-section">
                <h3 className="section-title">Raw Dry-Run Payload</h3>
                <pre className="code-block report-block">{JSON.stringify(upsertPlan, null, 2)}</pre>
              </section>
            </>
          ) : (
            <p className="empty-state">No upsert dry-run plan loaded.</p>
          )}
        </section>
      ) : null}
    </section>
  );
}

function TabButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button className={active ? "active" : undefined} onClick={onClick} type="button">
      {label}
    </button>
  );
}

function LineageFlow({
  nodes,
}: {
  nodes: { label: string; value: string; meta: string }[];
}) {
  return (
    <div className="lineage-flow" aria-label="Provenance lineage flow">
      {nodes.map((node, index) => (
        <div className="lineage-node" key={node.label}>
          <span>{index + 1}</span>
          <strong>{node.label}</strong>
          <em>{node.value}</em>
          <small>{node.meta}</small>
        </div>
      ))}
    </div>
  );
}

function TraceRail({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <p className="empty-state">No trace path loaded.</p>;
  return (
    <div className="trace-rail" aria-label="Document trace path">
      {rows.map((row) => (
        <div className="trace-rail-step" key={String(row.step)}>
          <span>{formatCell(row.step)}</span>
          <strong>{formatCell(row.level)}</strong>
          <small>{formatCell(row.key || row.keys)}</small>
        </div>
      ))}
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article className="card">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
    </article>
  );
}

function SummaryCell({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{formatCell(value)}</strong>
    </div>
  );
}

function sourceToRow(value: Record<string, unknown>): Record<string, unknown> {
  return {
    ...value,
    sha256: compactHash(value.sha256),
    collection_fingerprint: compactHash(value.collection_fingerprint),
  };
}

function artifactToRow(value: Record<string, unknown>): Record<string, unknown> {
  return {
    ...value,
    schema_hash: compactHash(value.schema_hash),
    sha256: compactHash(value.sha256),
  };
}

function documentToRow(value: Record<string, unknown>): Record<string, unknown> {
  return {
    ...value,
    content_hash: compactHash(value.content_hash),
    metadata_hash: compactHash(value.metadata_hash),
  };
}

function compactHash(value: unknown): string {
  const text = asString(value);
  return text.length > 18 ? `${text.slice(0, 18)}...` : text;
}

function clampNumber(value: string, min: number, max: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return min;
  return Math.min(max, Math.max(min, Math.round(parsed)));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function asString(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function countBy(rows: Record<string, unknown>[], key: string): { label: string; value: number; total: number }[] {
  const counts = new Map<string, number>();
  rows.forEach((row) => {
    const label = asString(row[key]) || "unknown";
    counts.set(label, (counts.get(label) || 0) + 1);
  });
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label, value, total: rows.length }));
}

function toNumber(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
