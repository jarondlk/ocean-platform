export const legacyAnalysisTables = ["membership", "composition", "diversity", "turnover", "exclusions", "methods", "method_summary", "controls", "control_overlap", "standards", "metadata", "environment_links", "environment_pairs", "associations"] as const;
export const researchAnalysisTables = ["membership", "exclusions", "coverage", "ranking", "series", "month_coverage", "spatial", "temperature_bins", "temperature_contrasts", "temperature_strata", "temperature_series", "spatial_temperature_bins", "stratum_coverage", "matched_panel", "change_ranking", "changes", "follow_through", "sst_links", "methods", "area_month_sst", "sst_exclusions"] as const;
export const analysisTables = [...legacyAnalysisTables, ...researchAnalysisTables.filter(t => !(legacyAnalysisTables as readonly string[]).includes(t))] as const;
export type AnalysisTable = typeof analysisTables[number];
export type AnalysisState = { analysisId?: string; table: AnalysisTable; method?: string; resultId?: string; offset: number; protocolId?: string; taxonKey?: string; areaId?: string; periodKind?: "year" | "season" | "month"; bin?: string };
export function parseAnalysisState(query: string): AnalysisState {
  const p = new URLSearchParams(query);
  const analysisId = p.get("analysis_id") ?? undefined;
  const resultId = p.get("result_id") ?? undefined;
  const table = p.get("table") ?? "diversity";
  const method = p.get("assignment_method") ?? undefined;
  for (const value of [analysisId, resultId]) if (value !== undefined && !/^[a-f0-9]{64}$/.test(value)) throw new Error("Invalid analysis identifier.");
  if (!analysisTables.includes(table as AnalysisTable)) throw new Error("Invalid analysis table.");
  if (method !== undefined && !["qcauto_target", "qcauto_95pct_3nn_target"].includes(method)) throw new Error("Invalid assignment method.");
  const rawOffset = p.get("offset") ?? "0";
  if (!/^\d+$/.test(rawOffset) || Number(rawOffset) > 10000000) throw new Error("Invalid analysis offset.");
  if (resultId && !analysisId) throw new Error("An analysis identifier is required.");
  const filters: Partial<AnalysisState> = {};
  for (const [key, name] of [["protocolId", "protocol_id"], ["taxonKey", "taxon_key"]] as const) {
    const value = p.get(name);
    if (value && !/^[a-f0-9]{64}$/.test(value)) throw new Error("Invalid research identifier.");
    if (value) filters[key] = value;
  }
  const area = p.get("area_id");
  if (area && area.length > 255) throw new Error("Invalid area identifier.");
  if (area) filters.areaId = area;
  const period = p.get("period_kind");
  if (period && !["year", "season", "month"].includes(period)) throw new Error("Invalid research period.");
  if (period) filters.periodKind = period as AnalysisState["periodKind"];
  const bin = p.get("bin");
  if (bin && bin.length > 32) throw new Error("Invalid temperature bin.");
  if (bin) filters.bin = bin;
  return { analysisId, resultId, table: table as AnalysisTable, method, offset: Number(rawOffset), ...filters };
}
export function analysisHref(state: AnalysisState): string {
  const p = new URLSearchParams({ view: "edna_analysis", table: state.table });
  if (state.analysisId) p.set("analysis_id", state.analysisId);
  if (state.resultId) p.set("result_id", state.resultId);
  if (state.method) p.set("assignment_method", state.method);
  if (state.offset) p.set("offset", String(state.offset));
  for (const [name, value] of [["protocol_id", state.protocolId], ["taxon_key", state.taxonKey], ["area_id", state.areaId], ["period_kind", state.periodKind], ["bin", state.bin]]) if (value) p.set(name!, value);
  return `/data?${p}`;
}
