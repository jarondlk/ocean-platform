const labels: Record<string, string> = {
  ctd: "CTD", metagenome: "Metagenome", remote_sensing: "SST", edna_metabarcoding: "ANEMONE eDNA",
};
const states: Record<string, string> = {
  retrieved: "Evidence retrieved", empty_under_scope: "No evidence retrieved under these filters",
  publication_unavailable: "Publication unavailable", backend_failed: "Source search failed",
  merge_budget_omitted: "Not included: increase the total evidence budget",
  prompt_budget_omitted: "Not supplied: answer context budget reached",
  prompt_evidence_omitted: "Not supplied after evidence validation", legacy_unknown: "Search status not recorded",
};
function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function count(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}
export function sourceCoverageRows(diagnostics: unknown) {
  const perSource = record(record(diagnostics).per_source);
  return Object.entries(labels).flatMap(([family, label]) => {
    const item = record(perSource[family]);
    if (item.enabled !== true) return [];
    const supplied = count(item.prompt_count), retrieved = count(item.merged_count);
    const text = supplied !== null ? `${supplied} evidence documents supplied` : retrieved !== null ? `${retrieved} primary documents retrieved` : "Per-source counts unavailable";
    const degraded = Array.isArray(item.failed_branches) && item.failed_branches.length > 0;
    return [{family, label, text, supplied, state: states[String(item.state)] || "Evidence status unavailable",
      limited: (supplied !== null ? supplied === 0 : retrieved === 0) || degraded,
      degraded}];
  });
}
export function coverageNotice(diagnostics: unknown): string | null {
  const data = record(diagnostics);
  if (data.comparison_status === "overlap_unverified") return "Date/location overlap is unverified. Retrieving both sources does not establish a match.";
  if (data.comparison_status === "incomplete_source_coverage") return "This comparison lacks required source evidence.";
  if (data.comparison_status === "source_disabled") return "A source required for this comparison is unchecked.";
  if (data.coverage_status === "partial") return "Evidence coverage is partial. Missing retrieved evidence does not establish absent source data.";
  return null;
}
