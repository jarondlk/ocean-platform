const reasonLabels: Record<string, string> = {
  below_min_read_count: "Below minimum read count",
  control_or_unknown: "Control or unknown classification",
  method_unavailable: "Assignment method unavailable",
  no_active_assay: "No active assay",
  protocol_incomplete: "Assay protocol incomplete",
  unresolved_rank: "Taxon unresolved at selected rank",
};

export function exclusionReasonLabel(value: unknown): string {
  if (typeof value !== "string" || !value) return "NA";
  return reasonLabels[value] || value.replaceAll("_", " ");
}

export function exclusionReasonDisplay(value: unknown): string {
  if (typeof value !== "string" || !value) return "NA";
  return `${exclusionReasonLabel(value)} (${value})`;
}
