import assert from "node:assert/strict";
import test from "node:test";
import { decodeSettings, defaultScope, defaultSettings, encodeSettings, scopeForAnalysis, scopeErrors, settingsErrors, settingsStorageKey } from "./chat-settings.ts";
import { appliedFilterRows } from "./chat-presentation.ts";

test("source scope supports all sixteen combinations, including empty", () => {
  for (let bits = 0; bits < 16; bits++) {
    const scope = defaultScope();
    Object.values(scope.sources).forEach((source, index) => { source.enabled = !!(bits & (1 << index)); });
    assert.deepEqual(scopeErrors(scope), []);
    assert.deepEqual(decodeSettings(encodeSettings(defaultSettings, scope)).scope, scope);
  }
});
test("per-source validation rejects invalid dates, ranges, types, conflicts and unsupported filters", () => {
  for (const mutate of [
    (s: any) => { s.version = true; }, (s: any) => { s.sources.ctd.enabled = "false"; },
    (s: any) => { delete s.sources.ctd.filters; }, (s: any) => { s.sources.remote_sensing.filters.bay = "O"; },
    (s: any) => { s.sources.ctd.filters.time_from = "2026-02-30"; },
    (s: any) => { s.sources.ctd.filters.time_from = "2026-02-02"; s.sources.ctd.filters.time_to = "2026-02-01"; },
    (s: any) => { s.sources.remote_sensing.filters.lat_min = 5; s.sources.remote_sensing.filters.lat_max = 0; },
    (s: any) => { s.sources.edna_metabarcoding.filters = {sample_kind: "environmental", is_control: true}; },
  ]) { const scope = defaultScope(); mutate(scope); assert(scopeErrors(scope).length > 0); }
});
test("false controls and zero coordinates survive storage and the applied ledger", () => {
  const scope = defaultScope();
  scope.sources.edna_metabarcoding.filters = {is_control: false, lat_min: 0, lon_max: 0};
  const restored = decodeSettings(encodeSettings(defaultSettings, scope));
  assert.deepEqual(restored.scope, scope);
  const rows = appliedFilterRows({evidence_scope: restored.scope});
  assert(rows.some(row => row.filter === "edna_metabarcoding.is_control" && row.value === false));
  assert(rows.some(row => row.filter === "edna_metabarcoding.lat_min" && row.value === 0));
});
test("saved source corruption requires reset rather than unfiltered defaults", () => {
  for (const raw of ["{", JSON.stringify({version: 2}), JSON.stringify({version: 1, scope: {sources: {ctd: {enabled: true}}}})]) assert.throws(() => decodeSettings(raw));
  assert.deepEqual(decodeSettings(null).scope, defaultScope());
});
test("account keys are distinct and only settings persist, excluding pinned analyses and chat content", () => {
  assert.notEqual(settingsStorageKey("alice"), settingsStorageKey("bob"));
  const scope = defaultScope(); scope.sources.edna_metabarcoding.analysis_id = "a".repeat(64);
  const encoded = encodeSettings({...defaultSettings, seed: "0", query: "PRIVATE", response: "PRIVATE"} as typeof defaultSettings, scope);
  assert(!encoded.includes("PRIVATE") && !encoded.includes("analysis_id"));
  assert.equal(decodeSettings(encoded).settings.seed, "0");
  assert.equal(decodeSettings(JSON.stringify({version: 1, settings: defaultSettings, scope})).scope.sources.edna_metabarcoding.analysis_id, undefined);
});
test("generation controls validate bounds and output limits", () => {
  assert.deepEqual(settingsErrors(defaultSettings), []);
  assert(settingsErrors({...defaultSettings, numPredict: "2049"}, 2048).length > 0);
  assert(settingsErrors({...defaultSettings, vectorWeight: 0, ftsWeight: 0}).length > 0);
  assert(settingsErrors({...defaultSettings, seed: "-1"}).length > 0);
  assert.deepEqual(settingsErrors({...defaultSettings, seed: "0", numPredict: "2048"}, 2048), []);
});

test("clearing a selected analysis after editing source filters removes its request binding", () => {
  const scope = defaultScope();
  scope.sources.edna_metabarcoding.filters = {provider_project_id: "2023KibanS", is_control: false, lat_min: 0};
  // Source controls can return the submitted scope with a previously pinned ID.
  const filtered = scopeForAnalysis(scope, "a".repeat(64));
  assert.equal(filtered.sources.edna_metabarcoding.analysis_id, "a".repeat(64));
  assert.equal(scope.sources.edna_metabarcoding.analysis_id, undefined);
  const cleared = scopeForAnalysis(filtered, "");
  assert.equal(cleared.sources.edna_metabarcoding.analysis_id, undefined);
  assert.deepEqual(cleared.sources.edna_metabarcoding.filters, scope.sources.edna_metabarcoding.filters);
  assert.equal(scopeForAnalysis(filtered, "b".repeat(64)).sources.edna_metabarcoding.analysis_id, "b".repeat(64));
  filtered.sources.edna_metabarcoding.enabled = false;
  assert.equal(scopeForAnalysis(filtered, "a".repeat(64)).sources.edna_metabarcoding.analysis_id, undefined);
});
