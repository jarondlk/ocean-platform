const FILTER_KEYS = [
  "source_type",
  "sample_id",
  "bay",
  "station",
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
  const envelope = asRecord(options.evidence_scope);
  const scopedRows = Object.entries(asRecord(envelope.sources)).flatMap(([family, raw]) => {
    const selection = asRecord(raw);
    return [{filter: `${family}.enabled`, value: selection.enabled},
      ...Object.entries(asRecord(selection.filters)).filter(([, value]) => isApplied(value)).map(([key, value]) => ({filter: `${family}.${key}`, value})),
      ...(isApplied(selection.analysis_id) ? [{filter: `${family}.analysis_id`, value: selection.analysis_id}] : [])];
  });
  const retrieval = asRecord(options.retrieval);
  const context = asRecord(options.context);
  const rows: Record<string, unknown>[] = FILTER_KEYS.flatMap((key) => {
    const value = retrieval[key];
    return isApplied(value) ? [{ filter: key, value }] : [];
  });
  if (isApplied(context.analysis_id)) {
    rows.push({ filter: "analysis_id", value: context.analysis_id });
  }
  const resolved = asRecord(context.aggregate_scope);
  if (resolved.filters) {
    return [...scopedRows, ...Object.entries(asRecord(resolved.filters)).map(([filter, value]) => ({ filter: scopedRows.length ? `aggregate.${filter}` : filter, value }))];
  }
  const aggregation = asRecord(context.aggregation);
  Object.entries(aggregation).forEach(([filter, value]) => {
    if (isApplied(value)) rows.push({ filter, value });
  });
  return scopedRows.length ? scopedRows : rows;
}

export function abstentionReasonLabel(reason?: string | null): string {
  const labels: Record<string, string> = {
    aggregate_scope_required: "Exact count needs clarification",
    aggregate_unavailable: "Exact aggregate unavailable",
    no_sources_selected: "No evidence sources selected",
    source_disabled: "Requested source is unchecked",
    freshness_unavailable: "Data arrival cannot be verified",
    no_matching_evidence: "No matching evidence",
    empty_analysis_cohort: "Empty analysis cohort",
    publication_pending: "eDNA publication pending",
    incomplete_source_coverage: "Required source evidence unavailable",
    overlap_unverified: "Date/location overlap not verified",
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
