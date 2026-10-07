import assert from "node:assert/strict";
import test from "node:test";
import { coverageMonths, sharedMonths, coverageRange, type CoverageSource } from "./temporal-coverage.ts";

function source(id: string, months: string[], status: CoverageSource["status"] = "available"): CoverageSource {
  return { id, label: id, status, count_unit: "samples", temporal_precision: "month", date_basis: "month", scope: "fixture", reason: null,
    observed_start: months[0] || null, observed_end: months.at(-1) || null, total_count: months.length, undated_count: 0, excluded_count: 0,
    source_binding: {}, categories: {}, bins: months.map(month => ({ month, count: 1, observed_days: null })),
    missing_dates_within_extent: [], missing_day_count: null, missing_dates_truncated: false };
}

test("shared months use occupied bins rather than broad envelopes", () => {
  const rows = [source("a", ["2025-12", "2026-02"]), source("b", ["2026-01", "2026-02"])];
  assert.deepEqual(sharedMonths(rows, ["a", "b"]), { state: "known", months: ["2026-02"] });
  assert.deepEqual(coverageMonths(rows), ["2025-12", "2026-01", "2026-02"]);
});

test("an unavailable or missing selected source cannot become zero overlap", () => {
  const rows = [source("a", ["2026-01"]), source("b", [], "unavailable")];
  assert.equal(sharedMonths(rows, ["a", "b"]).state, "unknown");
  assert.equal(sharedMonths(rows, ["a", "missing"]).state, "unknown");
  assert.equal(sharedMonths(rows, ["a"]).state, "choose");
});

test("disjoint and empty sources have known zero overlap", () => {
  assert.deepEqual(sharedMonths([source("a", ["2023-12"]), source("b", ["2024-01"])], ["a", "b"]), { state: "known", months: [] });
  assert.deepEqual(sharedMonths([source("a", ["2023-12"]), source("b", [], "empty")], ["a", "b"]), { state: "known", months: [] });
});

test("single-month geometry and coarse date labels remain valid", () => {
  const row = source("a", ["2026-01"]);
  assert.deepEqual(coverageMonths([row]), ["2026-01"]);
  assert.equal(coverageRange(row), "2026-01 – 2026-01");
  assert.deepEqual(coverageMonths([source("b", [])]), []);
});
