import assert from "node:assert/strict";
import { test } from "node:test";
import { coverageNotice, sourceCoverageRows } from "./source-coverage.ts";

test("final supplied counts distinguish empty, failed and disabled sources", () => {
  const rows = sourceCoverageRows({per_source: {
    ctd: {enabled: false, prompt_count: 0, state: "disabled"},
    remote_sensing: {enabled: true, prompt_count: 4, state: "retrieved"},
    edna_metabarcoding: {enabled: true, prompt_count: 0, state: "backend_failed"},
  }});
  assert.equal(rows.length, 2);
  assert.equal(rows[0].text, "4 evidence documents supplied");
  assert.equal(rows[1].state, "Source search failed");
  assert.equal(rows[1].limited, true);
});
test("retrieval workbench counts are not described as supplied prompt evidence", () => {
  const [row] = sourceCoverageRows({per_source: {ctd: {enabled: true, prompt_count: null, merged_count: 8, state: "retrieved"}}});
  assert.equal(row.text, "8 primary documents retrieved");
  assert.equal(row.supplied, null);
});
test("old and malformed histories do not manufacture complete coverage", () => {
  assert.deepEqual(sourceCoverageRows({}), []);
  assert.deepEqual(sourceCoverageRows(null), []);
  assert.equal(coverageNotice({}), null);
  const [row] = sourceCoverageRows({per_source: {ctd: {enabled: true, prompt_count: "8"}}});
  assert.equal(row.text, "Per-source counts unavailable");
});
test("unverified overlap is visible even when both sources were retrieved", () => {
  assert.match(coverageNotice({comparison_status: "overlap_unverified"})!, /does not establish a match/);
  assert.match(coverageNotice({coverage_status: "partial"})!, /does not establish absent source data/);
  assert.match(coverageNotice({comparison_status: "source_disabled"})!, /unchecked/);
});
test("degraded branch stays visible with a positive supplied count", () => {
  const [row] = sourceCoverageRows({per_source: {ctd: {enabled: true, prompt_count: 2, state: "retrieved", failed_branches: ["vector"]}}});
  assert.equal(row.degraded, true);
  assert.equal(row.limited, true);
});
