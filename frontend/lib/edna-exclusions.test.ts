import assert from "node:assert/strict";
import test from "node:test";
import {
  exclusionReasonDisplay,
  exclusionReasonLabel,
} from "./edna-exclusions.ts";

test("exclusion reason labels retain exact reason codes", () => {
  assert.equal(
    exclusionReasonDisplay("control_or_unknown"),
    "Control or unknown classification (control_or_unknown)",
  );
  assert.equal(exclusionReasonLabel("unresolved_rank"), "Taxon unresolved at selected rank");
  assert.equal(exclusionReasonDisplay("new_reason"), "new reason (new_reason)");
  assert.equal(exclusionReasonDisplay(null), "NA");
});
