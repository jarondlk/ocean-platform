const FILTER_KEYS = [
  "source_type",
  "sample_id",
  "bay",
  "time_from",
  "time_to",
  "provider",
  "provider_project_id",
  "provider_run_id",
  "assignment_method",
  "taxon",
  "sample_kind",
  "is_control",
  "lat_min",
  "lat_max",
  "lon_min",
  "lon_max",
] as const;

export function appliedFilterRows(
  options: Record<string, unknown> | undefined,
): Record<string, unknown>[] {
  if (!options) return [];
  const retrieval = asRecord(options.retrieval);
  const context = asRecord(options.context);
  const rows: Record<string, unknown>[] = FILTER_KEYS.flatMap((key) => {
    const value = retrieval[key];
    return isApplied(value) ? [{ filter: key, value }] : [];
  });
  if (isApplied(context.analysis_id)) {
    rows.push({ filter: "analysis_id", value: context.analysis_id });
  }
  return rows;
}

export function abstentionReasonLabel(reason?: string | null): string {
  const labels: Record<string, string> = {
    no_matching_evidence: "No matching evidence",
    empty_analysis_cohort: "Empty analysis cohort",
    publication_pending: "eDNA publication pending",
  };
  return reason ? labels[reason] || reason : "None";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object"
    ? value as Record<string, unknown>
    : {};
}

function isApplied(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "";
}
