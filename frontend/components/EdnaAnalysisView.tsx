"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { DataTable, formatCell } from "@/components/DataTable";
import { EdnaEnvironmentPlot } from "@/components/EdnaEnvironmentPlot";
import { ResearchAreaPlot, ResearchSeriesPlot, type ResearchArea } from "@/components/ResearchFrequencyPlot";
import { request } from "@/lib/api";
import { ednaHref } from "@/lib/edna-navigation";
import { analysisHref, legacyAnalysisTables, researchAnalysisTables, parseAnalysisState, type AnalysisState, type AnalysisTable } from "@/lib/edna-analysis-navigation";
import { exclusionReasonDisplay } from "@/lib/edna-exclusions";

type Run = { operational_publication?: {label: string} | null; analysis_id: string; status: string; recipe: { schema_version?: number; analysis_kind?: string; region_id?: string; time_from?: string; time_to?: string; calendar?: string; analysis_unit?: string; cohort?: Record<string, unknown>; rank: string; assignment_methods?: string[]; assignment_method?: string; control_policy: string; min_read_count: number }; tables?: AnalysisTable[]; table_counts?: Record<string, number>; manifest?: { limitations: string[]; table_counts: Record<string, number> } };
type Page = { total: number; rows: Record<string, unknown>[] };
type RunChoices = {areas: ResearchArea[]; taxa: {taxon_key: string; species: string}[]; protocols: {protocol_id: string; primer_set: string; target_gene: string; sequencing_method: string; library_layout: string}[]; tables: Record<string, Record<string, string[]>>};
const researchFilters = [["protocolId", "protocol_id", "Assay protocol"], ["taxonKey", "taxon_key", "Fish species"], ["areaId", "area_id", "Area"], ["periodKind", "period_kind", "Period"], ["bin", "bin", "Temperature bin"]] as const;
const base = "/data/edna/analysis";
const mainTables: [AnalysisTable, string][] = [["membership", "Eligibility"], ["composition", "Composition"], ["diversity", "Diversity"], ["turnover", "Turnover"], ["exclusions", "Exclusions"], ["methods", "Methods"], ["controls", "Controls"], ["environment_pairs", "Environment"]];
const researchWorkflows: [AnalysisTable, string][] = [["ranking", "Detection frequency"], ["temperature_contrasts", "Temperature comparisons"], ["spatial", "Monthly areas"], ["change_ranking", "Distribution changes"], ["follow_through", "Follow-through"], ["membership", "Eligibility"], ["exclusions", "Exclusions"]];
const apiBase = process.env.NEXT_PUBLIC_API_PROXY_BASE_URL || "/api/backend";
const displayColumns: Partial<Record<AnalysisTable, string[]>> = {
  membership: ["sample_id", "assay_id", "assignment_method", "status", "reason", "sample_kind", "is_control", "detection_count"],
  composition: ["sample_id", "assignment_method", "collection_date_utc", "taxon", "read_count", "read_proportion"],
  diversity: ["sample_id", "assignment_method", "richness", "shannon", "simpson_1d", "evenness", "retained_reads", "excluded_reads", "metric_status"],
  turnover: ["left_sample_id", "right_sample_id", "assignment_method", "pair_type", "jaccard_similarity", "bray_curtis_relative_reads", "distance_km"],
  methods: ["sample_id", "sequence_sha256", "status", "qcauto_read_count", "three_nn_read_count", "read_count_difference"],
  controls: ["sample_id", "assignment_method", "sample_kind", "is_control", "status", "pairing_basis"],
  environment_pairs: ["sample_id", "assignment_method", "variable", "value", "unit", "evidence_type", "richness", "shannon"],
  environment_links: ["sample_id", "observation_id", "variable", "value", "unit", "status", "selected", "distance_km"],
  exclusions: ["sample_id", "assay_id", "assignment_method", "detection_id", "reason", "read_count", "sample_kind", "is_control"],
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
  const [choices, setChoices] = useState<RunChoices | null>(null);
  const [choicesError, setChoicesError] = useState("");
  const state = parsed.state;
  const showRunControls = !state?.analysisId || run?.analysis_id === state.analysisId;
  const research = showRunControls && run?.recipe.schema_version === 2;
  const availableTables = run?.tables || (research ? researchAnalysisTables : legacyAnalysisTables);
  useEffect(() => {
    let active = true;
    setChoices(null); setChoicesError("");
    if (!state?.analysisId) return;
    request<RunChoices>(`${base}/runs/${state.analysisId}/choices`).then(value => { if (active) setChoices(value); }).catch(() => { if (active) setChoicesError("Research filter choices are unavailable."); });
    return () => { active = false; };
  }, [state?.analysisId]);
  useEffect(() => { let active = true; request<{ runs: Run[] }>(`${base}/catalog`).then(v => { if (active) setRuns(v.runs); }).catch(e => { if (active) setCatalogError(e.message); }); return () => { active = false; }; }, []);
  useEffect(() => {
    let active = true;
    setRun(current => current?.analysis_id === state?.analysisId ? current : null); setPage(null); setTrace(null); setError(""); setExportStatus("");
    if (!state?.analysisId) { setLoading(false); return; }
    setLoading(true);
    const p = new URLSearchParams({ limit: "100", offset: String(state.offset) });
    if (state.method) p.set("assignment_method", state.method);
    if (state.resultId) p.set("result_id", state.resultId);
    for (const [key, name] of researchFilters) if (state[key]) p.set(name, state[key]!);
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
  function navigate(update: Partial<AnalysisState>) { if (state) router.push(analysisHref({ ...state, ...((update.table && update.table !== state.table) || (update.analysisId && update.analysisId !== state.analysisId) ? {protocolId: undefined, taxonKey: undefined, areaId: undefined, periodKind: undefined, bin: undefined} : {}), ...update })); }
  async function download(format: "csv" | "bundle") {
    if (!state?.analysisId || !run || loading || error) return;
    const p = new URLSearchParams({ table: state.table, format });
    if (format === "csv") {
      if (state.method) p.set("assignment_method", state.method);
      if (state.resultId) p.set("result_id", state.resultId);
      for (const [key, name] of researchFilters) if (state[key]) p.set(name, state[key]!);
    }
    try {
      const response = await fetch(`${apiBase}${base}/runs/${state.analysisId}/export?${p}`);
      if (!response.ok) throw new Error("Export unavailable.");
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a"); a.href = url; a.download = `edna-${state.analysisId}-${state.table}.${format === "csv" ? "csv" : "zip"}`; a.click(); URL.revokeObjectURL(url);
      setExportStatus(response.headers.get("X-Export-Truncated") === "true" ? "Export limited to 25,000 rows. Download the complete bundle for all records." : "Export complete.");
    } catch (e) { setExportStatus((e as Error).message); }
  }
  const columns = state && page?.rows.length ? (!research && displayColumns[state.table]) || Object.keys(page.rows[0]).filter(k => !["result_id", "taxonomy", "lineage", "target", "protocol", "evidence", "qcauto_taxonomy", "three_nn_taxonomy", "source_row_hash", "member_ids", "detected_member_ids", "observation_ids", "source_granule_ids", "occurrence_ids"].includes(k)) : [];
  const result = trace?.result as Record<string, unknown> | undefined;
  const sourceIds = result ? [...new Set([result.sample_id, result.left_sample_id, result.right_sample_id, ...(Array.isArray(result.occurrence_ids) ? result.occurrence_ids : [])].filter((v): v is string => typeof v === "string" && /^[a-f0-9]{64}$/.test(v)))] : [];
  return <section className="analysis-workbench" aria-label="eDNA analysis">
    <label className="control-label">Analysis run
      <select className="field" value={state?.analysisId || ""} disabled={!state} onChange={e => navigate({ analysisId: e.target.value || undefined, table: runs.find(r => r.analysis_id === e.target.value)?.recipe.schema_version === 2 ? "ranking" : "diversity", resultId: undefined, offset: 0, method: undefined })}>
        <option value="">Select a run</option>
        {state?.analysisId && !runs.some(r => r.analysis_id === state.analysisId) ? <option value={state.analysisId}>{state.analysisId}</option> : null}
        {runs.map(r => <option key={r.analysis_id} value={r.analysis_id}>{String(r.recipe.region_id || r.recipe.cohort?.provider_project_id || r.recipe.cohort?.provider_run_id || "Selected cohort")} · {r.operational_publication ? "Regional analysis" : r.recipe.analysis_unit === "provisional_singleton_occurrence" ? "PROVISIONAL DEMO" : r.recipe.schema_version === 2 ? "Detection frequency" : r.recipe.rank} · {r.status.replaceAll("_", " ")} · {r.analysis_id.slice(0, 12)}</option>)}
      </select>
    </label>
    {showRunControls ? <>
    <nav className="tab-row" aria-label="Analysis tables">{(research ? researchWorkflows : mainTables).map(([table, label]) => <button type="button" key={table} className={state?.table === table ? "button" : "button secondary-button"} onClick={() => navigate({ table, resultId: undefined, offset: 0, method: undefined })}>{label}</button>)}</nav>
    <div className="filter-grid">
      <label className="control-label">Table<select className="field" value={state?.table || "diversity"} onChange={e => navigate({ table: e.target.value as AnalysisTable, resultId: undefined, offset: 0, method: undefined })}>{availableTables.map(t => <option key={t} value={t}>{t.replaceAll("_", " ")}</option>)}</select></label>
      <label className="control-label">Assignment method<select className="field" value={state?.method || ""} disabled={!!state && ["methods", "method_summary", "standards", "metadata", "environment_links", "area_month_sst", "sst_exclusions", "relative_sst_thresholds", "read_ranking"].includes(state.table)} onChange={e => navigate({ method: e.target.value || undefined, resultId: undefined, offset: 0 })}><option value="">All</option>{(run?.recipe.assignment_methods || (run?.recipe.assignment_method ? [run.recipe.assignment_method] : ["qcauto_target", "qcauto_95pct_3nn_target"])).map(method => <option key={method} value={method}>{method === "qcauto_target" ? "QCauto" : "QCauto 95%-3NN"}</option>)}</select></label>
    </div>
    {research && state ? <div className="filter-grid">{researchFilters.filter(([,field]) => choices?.tables[state.table]?.[field]).map(([key, field, label]) => <label className="control-label" key={key}>{label}<select className="field" value={state[key] || ""} onChange={event => navigate({[key]: event.target.value || undefined, offset: 0, resultId: undefined})}><option value="">All published groups</option>{choices?.tables[state.table][field].map(value => <option key={value} value={value}>{field === "taxon_key" ? choices.taxa.find(t => t.taxon_key === value)?.species || value.slice(0,12) : field === "protocol_id" ? (() => { const protocol = choices.protocols.find(p => p.protocol_id === value); return protocol ? `${protocol.target_gene} · ${protocol.primer_set} · ${protocol.sequencing_method} · ${value.slice(0,8)}` : value.slice(0,12); })() : field === "area_id" ? choices.areas.find(a => a.area_id === value)?.label || value : value}</option>)}</select></label>)}</div> : null}
    </> : null}
    {research && choicesError ? <p role="status">{choicesError}</p> : null}
    {parsed.error || error || catalogError ? <p role="alert">{parsed.error || error || catalogError}</p> : null}
    {loading || (!showRunControls && !error) ? <p role="status">Loading analysis…</p> : null}
    {run && showRunControls && !loading && !error ? <>
      <p>{run.recipe.rank} · {run.recipe.control_policy.replaceAll("_", " ")} · minimum reads {run.recipe.min_read_count} · {run.status.replaceAll("_", " ")}</p>
      {research ? <p>{run.recipe.region_id} · {run.recipe.time_from}–{run.recipe.time_to} · {run.recipe.calendar}. {run.recipe.analysis_unit === "provisional_singleton_occurrence" ? "Regional analysis. Frequencies use singleton occurrence proxies, not confirmed water collections. Read counts are sequencing signals, not fish abundance." : "Frequencies use eligible physical samples."} Unsampled areas have no rate; temperature-linked counts are separate.</p> : null}
      <div className="button-row">
        <button type="button" className="button secondary-button" onClick={() => download("csv")}>Export table CSV</button>
        <button type="button" className="button secondary-button" onClick={() => download("bundle")}>Download analysis bundle</button>
        {run.status === "current" ? <Link className="button secondary-button" href={`/chat?analysis_id=${run.analysis_id}`}>Query this analysis</Link> : null}
        {state?.resultId ? <button className="button secondary-button" type="button" onClick={() => navigate({ resultId: undefined, offset: 0 })}>All results</button> : null}
      </div>
      {exportStatus ? <p role="status">{exportStatus}</p> : null}
      <p>{page?.total || 0} rows</p>
      {page?.total === 0 && ["composition", "diversity", "turnover", "environment_pairs"].includes(state?.table || "") && (run.manifest?.table_counts.exclusions || 0) > 0 ? (
        <p role="status">
          No included rows. {run.manifest?.table_counts.exclusions} excluded detections.{" "}
          <button className="document-link-button" type="button" onClick={() => navigate({ table: "exclusions", resultId: undefined, offset: 0 })}>View exclusions</button>
        </p>
      ) : null}
      {state?.table === "environment_pairs" && page?.rows.length ? <EdnaEnvironmentPlot key={query} rows={page.rows} onSelect={id => navigate({ resultId: id, offset: 0 })} /> : null}
      {research && choices && state && ["spatial", "area_month_sst", "spatial_temperature_bins"].includes(state.table) ? <ResearchAreaPlot key={query} rows={page?.rows || []} areas={choices.areas} exportMetadata={{analysis_id:run.analysis_id, recipe:run.recipe, table:state.table, total_rows:page?.total, offset:state.offset, rows_truncated:(page?.rows.length || 0) < (page?.total || 0)}} onSelect={id => navigate({resultId: id, offset: 0})} /> : null}
      {research && choices && state && ["series", "temperature_series", "follow_through"].includes(state.table) ? <ResearchSeriesPlot key={query} rows={page?.rows || []} taxa={choices.taxa} exportMetadata={{analysis_id:run.analysis_id, recipe:run.recipe, table:state.table, total_rows:page?.total, offset:state.offset, rows_truncated:(page?.rows.length || 0) < (page?.total || 0)}} onSelect={id => navigate({resultId: id, offset: 0})} /> : null}
      <DataTable columns={columns} rows={page?.rows || []} rowKeyColumn="result_id" selectedKey={state?.resultId} onRowSelect={r => navigate({ resultId: String(r.result_id), offset: 0 })} renderCell={(value, column) => column === "reason" ? exclusionReasonDisplay(value) : research && column === "taxon_key" ? choices?.taxa.find(t => t.taxon_key === value)?.species || formatCell(value) : typeof value === "string" && /^[a-f0-9]{64}$/.test(value) ? <span title={value}>{value.slice(0, 12)}…</span> : formatCell(value)} />
      <div className="button-row"><button type="button" className="button secondary-button" disabled={!state?.offset} onClick={() => navigate({ offset: Math.max(0, (state?.offset || 0)-100) })}>Previous</button><button type="button" className="button secondary-button" disabled={(state?.offset || 0)+100 >= (page?.total || 0)} onClick={() => navigate({ offset: (state?.offset || 0)+100 })}>Next</button></div>
      {sourceIds.length ? <div className="button-row">{sourceIds.map((id, index) => <Link key={id} className="button secondary-button" href={ednaHref({ sample_id: id, assignment_method: typeof result?.assignment_method === "string" ? result.assignment_method : undefined })}>Source sample{sourceIds.length > 1 ? ` ${index + 1}` : ""}</Link>)}</div> : null}
      {trace ? <details><summary>Result provenance</summary><pre className="json-view">{JSON.stringify(trace, null, 2)}</pre></details> : null}
      <details><summary>Recipe</summary><pre className="json-view">{JSON.stringify(run.recipe, null, 2)}</pre></details>
      <details><summary>Methods and limitations</summary><ul>{run.manifest?.limitations.map(text => <li key={text}>{text}</li>)}</ul></details>
    </> : null}
  </section>;
}
