"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { DataTable, formatCell } from "@/components/DataTable";
import { EdnaEnvironmentPlot } from "@/components/EdnaEnvironmentPlot";
import { request } from "@/lib/api";
import { ednaHref } from "@/lib/edna-navigation";
import { analysisHref, analysisTables, parseAnalysisState, type AnalysisState, type AnalysisTable } from "@/lib/edna-analysis-navigation";

type Run = { analysis_id: string; status: string; recipe: { cohort: Record<string, unknown>; rank: string; assignment_methods: string[]; control_policy: string; min_read_count: number }; table_counts?: Record<string, number>; manifest?: { limitations: string[]; table_counts: Record<string, number> } };
type Page = { total: number; rows: Record<string, unknown>[] };
const base = "/data/edna/analysis";
const mainTables: [AnalysisTable, string][] = [["composition", "Composition"], ["diversity", "Diversity"], ["turnover", "Turnover"], ["methods", "Methods"], ["controls", "Controls"], ["environment_pairs", "Environment"]];
const apiBase = process.env.NEXT_PUBLIC_API_PROXY_BASE_URL || "/api/backend";
const displayColumns: Partial<Record<AnalysisTable, string[]>> = {
  composition: ["sample_id", "assignment_method", "collection_date_utc", "taxon", "read_count", "read_proportion"],
  diversity: ["sample_id", "assignment_method", "richness", "shannon", "simpson_1d", "evenness", "retained_reads", "excluded_reads", "metric_status"],
  turnover: ["left_sample_id", "right_sample_id", "assignment_method", "pair_type", "jaccard_similarity", "bray_curtis_relative_reads", "distance_km"],
  methods: ["sample_id", "sequence_sha256", "status", "qcauto_read_count", "three_nn_read_count", "read_count_difference"],
  controls: ["sample_id", "assignment_method", "sample_kind", "is_control", "status", "pairing_basis"],
  environment_pairs: ["sample_id", "assignment_method", "variable", "value", "unit", "evidence_type", "richness", "shannon"],
  environment_links: ["sample_id", "observation_id", "variable", "value", "unit", "status", "selected", "distance_km"],
};

export function EdnaAnalysisView() {
  const router = useRouter();
  const query = useSearchParams().toString();
  const parsed = useMemo(() => { try { return { state: parseAnalysisState(query), error: "" }; } catch (e) { return { state: null, error: (e as Error).message }; } }, [query]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [catalogError, setCatalogError] = useState("");
  const [exportStatus, setExportStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const state = parsed.state;
  useEffect(() => { let active = true; request<{ runs: Run[] }>(`${base}/catalog`).then(v => { if (active) setRuns(v.runs); }).catch(e => { if (active) setCatalogError(e.message); }); return () => { active = false; }; }, []);
  useEffect(() => {
    let active = true;
    setRun(null); setPage(null); setTrace(null); setError(""); setExportStatus("");
    if (!state?.analysisId) { setLoading(false); return; }
    setLoading(true);
    const p = new URLSearchParams({ limit: "100", offset: String(state.offset) });
    if (state.method) p.set("assignment_method", state.method);
    if (state.resultId) p.set("result_id", state.resultId);
    Promise.all([request<Run>(`${base}/runs/${state.analysisId}`), request<Page>(`${base}/runs/${state.analysisId}/tables/${state.table}?${p}`)])
      .then(([r, rows]) => { if (active) { setRun(r); setPage(rows); } })
      .catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [state]);
  useEffect(() => {
    let active = true;
    if (state?.analysisId && state.resultId && page) {
      request<Record<string, unknown>>(`${base}/runs/${state.analysisId}/provenance?table=${state.table}&result_id=${state.resultId}`)
        .then(v => { if (active) setTrace(v); }).catch(e => { if (active) setError(e.message); });
    }
    return () => { active = false; };
  }, [state, page]);
  function navigate(update: Partial<AnalysisState>) { if (state) router.push(analysisHref({ ...state, ...update })); }
  async function download(format: "csv" | "bundle") {
    if (!state?.analysisId || !run || loading || error) return;
    const p = new URLSearchParams({ table: state.table, format });
    if (format === "csv") {
      if (state.method) p.set("assignment_method", state.method);
      if (state.resultId) p.set("result_id", state.resultId);
    }
    try {
      const response = await fetch(`${apiBase}${base}/runs/${state.analysisId}/export?${p}`);
      if (!response.ok) throw new Error("Export unavailable.");
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a"); a.href = url; a.download = `edna-${state.analysisId}-${state.table}.${format === "csv" ? "csv" : "zip"}`; a.click(); URL.revokeObjectURL(url);
      setExportStatus(response.headers.get("X-Export-Truncated") === "true" ? "Export limited to 25,000 rows. Download the complete bundle for all records." : "Export complete.");
    } catch (e) { setExportStatus((e as Error).message); }
  }
  const columns = state && page?.rows.length ? displayColumns[state.table] || Object.keys(page.rows[0]).filter(k => !["result_id", "taxonomy", "target", "protocol", "evidence", "qcauto_taxonomy", "three_nn_taxonomy", "source_row_hash"].includes(k)) : [];
  const result = trace?.result as Record<string, unknown> | undefined;
  const sourceIds = result ? [...new Set([result.sample_id, result.left_sample_id, result.right_sample_id].filter((v): v is string => typeof v === "string" && /^[a-f0-9]{64}$/.test(v)))] : [];
  return <section className="analysis-workbench" aria-label="eDNA analysis">
    <label className="control-label">Analysis run
      <select className="field" value={state?.analysisId || ""} disabled={!state} onChange={e => navigate({ analysisId: e.target.value || undefined, resultId: undefined, offset: 0, method: undefined })}>
        <option value="">Select a run</option>
        {state?.analysisId && !runs.some(r => r.analysis_id === state.analysisId) ? <option value={state.analysisId}>{state.analysisId}</option> : null}
        {runs.map(r => <option key={r.analysis_id} value={r.analysis_id}>{String(r.recipe.cohort.provider_project_id || r.recipe.cohort.provider_run_id || "Selected cohort")} · {r.recipe.rank} · {r.analysis_id.slice(0, 12)}</option>)}
      </select>
    </label>
    <nav className="tab-row" aria-label="Analysis tables">{mainTables.map(([table, label]) => <button type="button" key={table} className={state?.table === table ? "button" : "button secondary-button"} onClick={() => navigate({ table, resultId: undefined, offset: 0, method: undefined })}>{label}</button>)}</nav>
    <div className="filter-grid">
      <label className="control-label">Table<select className="field" value={state?.table || "diversity"} onChange={e => navigate({ table: e.target.value as AnalysisTable, resultId: undefined, offset: 0, method: undefined })}>{analysisTables.map(t => <option key={t} value={t}>{t.replaceAll("_", " ")}</option>)}</select></label>
      <label className="control-label">Assignment method<select className="field" value={state?.method || ""} disabled={!!state && ["methods", "method_summary", "standards", "metadata", "environment_links"].includes(state.table)} onChange={e => navigate({ method: e.target.value || undefined, resultId: undefined, offset: 0 })}><option value="">All</option>{(run?.recipe.assignment_methods || ["qcauto_target", "qcauto_95pct_3nn_target"]).map(method => <option key={method} value={method}>{method === "qcauto_target" ? "QCauto" : "QCauto 95%-3NN"}</option>)}</select></label>
    </div>
    {parsed.error || error || catalogError ? <p role="alert">{parsed.error || error || catalogError}</p> : null}
    {loading ? <p role="status">Loading…</p> : null}
    {run && !loading && !error ? <>
      <p>{run.recipe.rank} · {run.recipe.control_policy.replaceAll("_", " ")} · minimum reads {run.recipe.min_read_count} · {run.status.replaceAll("_", " ")}</p>
      <div className="button-row">
        <button type="button" className="button secondary-button" onClick={() => download("csv")}>Export table CSV</button>
        <button type="button" className="button secondary-button" onClick={() => download("bundle")}>Download analysis bundle</button>
        {run.status === "current" ? <Link className="button secondary-button" href={`/chat?analysis_id=${run.analysis_id}`}>Query this analysis</Link> : null}
        {state?.resultId ? <button className="button secondary-button" type="button" onClick={() => navigate({ resultId: undefined, offset: 0 })}>All results</button> : null}
      </div>
      {exportStatus ? <p role="status">{exportStatus}</p> : null}
      <p>{page?.total || 0} rows</p>
      {state?.table === "environment_pairs" && page?.rows.length ? <EdnaEnvironmentPlot key={query} rows={page.rows} onSelect={id => navigate({ resultId: id, offset: 0 })} /> : null}
      <DataTable columns={columns} rows={page?.rows || []} rowKeyColumn="result_id" selectedKey={state?.resultId} onRowSelect={r => navigate({ resultId: String(r.result_id), offset: 0 })} renderCell={value => typeof value === "string" && /^[a-f0-9]{64}$/.test(value) ? <span title={value}>{value.slice(0, 12)}…</span> : formatCell(value)} />
      <div className="button-row"><button type="button" className="button secondary-button" disabled={!state?.offset} onClick={() => navigate({ offset: Math.max(0, (state?.offset || 0)-100) })}>Previous</button><button type="button" className="button secondary-button" disabled={(state?.offset || 0)+100 >= (page?.total || 0)} onClick={() => navigate({ offset: (state?.offset || 0)+100 })}>Next</button></div>
      {sourceIds.length ? <div className="button-row">{sourceIds.map((id, index) => <Link key={id} className="button secondary-button" href={ednaHref({ sample_id: id, assignment_method: typeof result?.assignment_method === "string" ? result.assignment_method : undefined })}>Source sample{sourceIds.length > 1 ? ` ${index + 1}` : ""}</Link>)}</div> : null}
      {trace ? <details><summary>Result provenance</summary><pre className="json-view">{JSON.stringify(trace, null, 2)}</pre></details> : null}
      <details><summary>Recipe</summary><pre className="json-view">{JSON.stringify(run.recipe, null, 2)}</pre></details>
      <details><summary>Methods and limitations</summary><ul>{run.manifest?.limitations.map(text => <li key={text}>{text}</li>)}</ul></details>
    </> : null}
  </section>;
}
