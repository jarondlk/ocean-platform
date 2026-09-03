export const analysisTables = ["membership", "composition", "diversity", "turnover", "exclusions", "methods", "method_summary", "controls", "control_overlap", "standards", "metadata", "environment_links", "environment_pairs", "associations"] as const;
export type AnalysisTable = typeof analysisTables[number];
export type AnalysisState = { analysisId?: string; table: AnalysisTable; method?: string; resultId?: string; offset: number };
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
  return { analysisId, resultId, table: table as AnalysisTable, method, offset: Number(rawOffset) };
}
export function analysisHref(state: AnalysisState): string {
  const p = new URLSearchParams({ view: "edna_analysis", table: state.table });
  if (state.analysisId) p.set("analysis_id", state.analysisId);
  if (state.resultId) p.set("result_id", state.resultId);
  if (state.method) p.set("assignment_method", state.method);
  if (state.offset) p.set("offset", String(state.offset));
  return `/data?${p}`;
}
