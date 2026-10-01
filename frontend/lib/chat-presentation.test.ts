import assert from "node:assert/strict";
import test from "node:test";

import { abstentionReasonLabel, appliedFilterRows } from "./chat-presentation.ts";

test("appliedFilterRows includes only explicit scientific scope", () => {
  assert.deepEqual(
    appliedFilterRows({
      retrieval: {
        k: 8,
        source_type: "edna_metabarcoding",
        bay: "",
        is_control: false,
        vector_weight: 0.6,
      },
      context: { analysis_id: "abc", inject_analysis: true },
    }),
    [
      { filter: "source_type", value: "edna_metabarcoding" },
      { filter: "is_control", value: false },
      { filter: "analysis_id", value: "abc" },
    ],
  );
});

test("abstentionReasonLabel presents stable direct labels", () => {
  assert.equal(abstentionReasonLabel("aggregate_scope_required"), "Exact count needs clarification");
  assert.equal(abstentionReasonLabel("publication_pending"), "eDNA publication pending");
  assert.equal(abstentionReasonLabel(null), "None");
});


test("resolved aggregate filters display inferred and explicit scope", () => {
  assert.deepEqual(appliedFilterRows({ retrieval: {}, context: { aggregate_scope: { filters: { provider: "anemone", is_control: false } } } }), [
    { filter: "provider", value: "anemone" }, { filter: "is_control", value: false },
  ]);
});
