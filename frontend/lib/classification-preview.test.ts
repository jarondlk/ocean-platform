import assert from "node:assert/strict";
import test from "node:test";
import {
  classificationPreviewDeltaRows,
  classificationPreviewMethodRows,
} from "./classification-preview.ts";
import type { ClassificationReviewPreview } from "../types.ts";

const preview = {
  review_id: "1".repeat(64),
  review_state: "draft",
  review_version: 1,
  review_content_sha256: "2".repeat(64),
  source_snapshot_id: "3".repeat(64),
  sample_id: "4".repeat(64),
  provider_sample_id: "sample",
  algorithm_version: "edna-descriptive-v1",
  recipe: {},
  canonical_input_sha256: "5".repeat(64),
  preview_sha256: "6".repeat(64),
  eligibility_changed: true,
  table_count_delta: { diversity: 1, controls: 0, composition: 2 },
  baseline: {
    sample_kind: "unknown",
    is_control: null,
    eligibility: "excluded",
    exclusion_reasons: ["control_or_unknown"],
    analysis_id: "7".repeat(64),
    input_sha256: "8".repeat(64),
    table_counts: { diversity: 0, controls: 1, composition: 0 },
    methods: [],
  },
  proposed: {
    sample_kind: "environmental",
    is_control: false,
    eligibility: "included",
    exclusion_reasons: [],
    analysis_id: "9".repeat(64),
    input_sha256: "a".repeat(64),
    table_counts: { diversity: 1, controls: 1, composition: 2 },
    methods: [{
      assay_id: "b".repeat(64),
      assignment_method: "qcauto_target",
      status: "included",
      exclusion_reasons: [],
      source_detection_count: 2,
      retained_detection_count: 1,
      excluded_detection_count: 1,
      source_reads: 4,
      retained_reads: 3,
      excluded_reads: 1,
      richness: 1,
      shannon: 0,
      simpson_1d: 0,
      evenness: null,
      metric_status: "single_taxon",
      top_taxa: [{ taxon: "Beta", read_count: 3, read_proportion: 1 }],
    }],
  },
  limitations: [],
} satisfies ClassificationReviewPreview;

test("classification preview rows preserve scenario and scientific values", () => {
  const rows = classificationPreviewMethodRows(preview);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].scenario, "Proposed");
  assert.equal(rows[0].retained_reads, 3);
  assert.equal(rows[0].reason, undefined);
  assert.deepEqual(rows[0].top_taxa, [
    { taxon: "Beta", read_count: 3, read_proportion: 1 },
  ]);
});

test("classification preview deltas omit unchanged tables", () => {
  assert.deepEqual(classificationPreviewDeltaRows(preview), [
    { table: "composition", current: 0, proposed: 2, delta: 2 },
    { table: "diversity", current: 0, proposed: 1, delta: 1 },
  ]);
});
