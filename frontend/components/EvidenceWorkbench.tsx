"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { RotateCcw, Search } from "lucide-react";
import { CsvExportButton } from "@/components/CsvExportButton";
import { getDocuments } from "@/lib/api";
import { SourceTable } from "@/components/SourceTable";
import type { SourceDocument } from "@/types";

const sourceLabels: Record<string, string> = {
  ctd: "CTD",
  metagenome: "Metagenome",
  remote_sensing: "SST",
};

export function EvidenceWorkbench() {
  const [query, setQuery] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [bay, setBay] = useState("");
  const [timeFrom, setTimeFrom] = useState("");
  const [timeTo, setTimeTo] = useState("");
  const [limit, setLimit] = useState(25);
  const [minScore, setMinScore] = useState(0);
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const visibleDocuments = useMemo(() => {
    return documents.filter((document) => (document.score ?? 0) >= minScore);
  }, [documents, minScore]);

  const sourceCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    visibleDocuments.forEach((document) => {
      counts[document.source_type] = (counts[document.source_type] || 0) + 1;
    });
    return counts;
  }, [visibleDocuments]);

  const scoreStats = useMemo(() => {
    const scores = visibleDocuments
      .map((document) => document.score)
      .filter((score): score is number => typeof score === "number");
    if (!scores.length) return { max: "NA", mean: "NA" };
    const mean = scores.reduce((sum, score) => sum + score, 0) / scores.length;
    return { max: Math.max(...scores).toFixed(4), mean: mean.toFixed(4) };
  }, [visibleDocuments]);
  const exportRows = visibleDocuments.map((document) => ({
    doc_id: document.doc_id,
    title: document.title,
    source_type: document.source_type,
    sample_id: document.sample_id,
    event_id: document.event_id,
    time: document.time,
    bay: document.bay,
    station: document.station,
    score: document.score,
    vector_rank: document.rank_sources?.vector,
    fts_rank: document.rank_sources?.fts,
    text: document.text,
  }));

  async function load() {
    setLoading(true);
    setError("");
    try {
      const rows = await getDocuments({
        q: query,
        source_type: sourceType || undefined,
        bay: bay || undefined,
        time_from: timeFrom || undefined,
        time_to: timeTo || undefined,
        limit,
      });
      setDocuments(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void load();
  }

  function resetControls() {
    setQuery("");
    setSourceType("");
    setBay("");
    setTimeFrom("");
    setTimeTo("");
    setLimit(25);
    setMinScore(0);
  }

  const maxSourceCount = Math.max(1, ...Object.values(sourceCounts));

  return (
    <section className="evidence-workbench">
      <section className="explore-section">
        <form className="evidence-expert-form" onSubmit={submit}>
          <label className="settings-field" htmlFor="evidence-query" title="Full-text or retrieval query. Leave blank to list corpus records by filter.">
            <span>Query</span>
            <input
              id="evidence-query"
              className="field"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search evidence"
            />
          </label>
          <label className="settings-field" htmlFor="evidence-source" title="Restrict retrieval to a single evidence source type.">
            <span>Source</span>
            <select
              id="evidence-source"
              className="field"
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value)}
            >
              <option value="">All source types</option>
              <option value="ctd">CTD</option>
              <option value="metagenome">Metagenome</option>
              <option value="remote_sensing">Satellite SST</option>
            </select>
          </label>
          <label className="settings-field" htmlFor="evidence-bay" title="Filter by bay metadata where available.">
            <span>Bay</span>
            <select id="evidence-bay" className="field" value={bay} onChange={(event) => setBay(event.target.value)}>
              <option value="">All bays</option>
              <option value="O">Onagawa</option>
              <option value="I">Ishinomaki</option>
              <option value="M">Mutsu</option>
            </select>
          </label>
          <label className="settings-field" htmlFor="evidence-time-from" title="Inclusive lower bound for document time metadata.">
            <span>From</span>
            <input
              id="evidence-time-from"
              className="field"
              type="date"
              value={timeFrom}
              onChange={(event) => setTimeFrom(event.target.value)}
            />
          </label>
          <label className="settings-field" htmlFor="evidence-time-to" title="Inclusive upper bound for document time metadata.">
            <span>To</span>
            <input
              id="evidence-time-to"
              className="field"
              type="date"
              value={timeTo}
              onChange={(event) => setTimeTo(event.target.value)}
            />
          </label>
          <label className="settings-field" htmlFor="evidence-limit" title="Maximum number of documents requested from the API.">
            <span>Limit</span>
            <select
              id="evidence-limit"
              className="field"
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </label>
          <label className="settings-field" htmlFor="evidence-min-score" title="Client-side threshold applied after retrieval.">
            <span>Min score</span>
            <input
              id="evidence-min-score"
              className="field"
              min={0}
              step={0.0001}
              type="number"
              value={minScore}
              onChange={(event) => setMinScore(Number(event.target.value))}
            />
          </label>
          <div className="evidence-actions">
            <button className="button" disabled={loading}>
              <Search size={16} aria-hidden="true" />
              {loading ? "Searching" : "Search"}
            </button>
            <button className="button secondary-button icon-button" onClick={resetControls} title="Reset evidence controls." type="button">
              <RotateCcw size={15} aria-hidden="true" />
            </button>
          </div>
        </form>
        {error ? <p className="error-text">{error}</p> : null}
      </section>

      <section className="explore-section">
        <h3 className="section-title">Result Diagnostics</h3>
        <div className="summary-strip">
          <SummaryCell label="Displayed" value={visibleDocuments.length} />
          <SummaryCell label="Fetched" value={documents.length} />
          <SummaryCell label="Max score" value={scoreStats.max} />
          <SummaryCell label="Mean score" value={scoreStats.mean} />
        </div>
        <div className="evidence-source-grid">
          {Object.entries(sourceCounts).map(([source, count]) => (
            <div className="source-meter" key={source}>
              <span>{sourceLabels[source] || source}</span>
              <strong>{count}</strong>
              <div className="meter-track">
                <div style={{ width: `${(count / maxSourceCount) * 100}%` }} />
              </div>
            </div>
          ))}
          {!visibleDocuments.length ? <p className="empty-state">No documents match the active score threshold.</p> : null}
        </div>
      </section>

      <section className="explore-section">
        <div className="section-toolbar">
          <h3 className="section-title">{visibleDocuments.length} documents</h3>
          <CsvExportButton
            columns={["doc_id", "title", "source_type", "sample_id", "event_id", "time", "bay", "station", "score", "vector_rank", "fts_rank", "text"]}
            filename="explore_evidence_documents"
            rows={exportRows}
          />
        </div>
        <SourceTable sources={visibleDocuments} />
      </section>
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
