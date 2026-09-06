import type { ClassificationReviewPreview } from "@/types";

export function classificationPreviewMethodRows(
  preview: ClassificationReviewPreview,
): Record<string, unknown>[] {
  return ([
    ["Current", preview.baseline.methods],
    ["Proposed", preview.proposed.methods],
  ] as const).flatMap(([scenario, methods]) => methods.map((row) => ({
    scenario,
    assay_id: row.assay_id,
    assignment_method: row.assignment_method,
    status: row.status,
    reason: row.reason,
    source_detection_count: row.source_detection_count,
    retained_detection_count: row.retained_detection_count,
    excluded_detection_count: row.excluded_detection_count,
    source_reads: row.source_reads,
    retained_reads: row.retained_reads,
    excluded_reads: row.excluded_reads,
    richness: row.richness,
    shannon: row.shannon,
    simpson_1d: row.simpson_1d,
    evenness: row.evenness,
    metric_status: row.metric_status,
    top_taxa: row.top_taxa,
  })));
}

export function classificationPreviewDeltaRows(
  preview: ClassificationReviewPreview,
): Record<string, unknown>[] {
  return Object.entries(preview.table_count_delta)
    .filter(([, delta]) => delta !== 0)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([table, delta]) => ({
      table,
      current: preview.baseline.table_counts[table] || 0,
      proposed: preview.proposed.table_counts[table] || 0,
      delta,
    }));
}
