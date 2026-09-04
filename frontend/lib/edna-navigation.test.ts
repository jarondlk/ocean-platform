import assert from "node:assert/strict";
import test from "node:test";
import { ednaHref, parseEdnaState } from "./edna-navigation.ts";

test("eDNA URLs preserve exact evidence, false controls, zero coordinates and pagination", () => {
  const filters = {
    sample_id: "a".repeat(64), assay_id: "b".repeat(64),
    assignment_method: "qcauto_95pct_3nn_target", taxon: "Scomber japonicus",
    provider: "anemone", is_control: false, lat_min: 0, lat_max: 40,
    lon_min: 140, lon_max: 142, time_from: "2026-01-01", time_to: "2026-02-01",
  };
  const state = { detectionId: "c".repeat(64), sampleOffset: 100, detectionOffset: 200 };
  const href = ednaHref(filters, state);
  assert.deepEqual(parseEdnaState(href.split("?")[1]), { filters, ...state });
});

test("eDNA invalid destinations never fall back to another method or sample", () => {
  for (const query of [
    "sample_id=legacy-sample", "assignment_method=other", "sample_kind=field",
    "is_control=unknown", "lat_min=40&lat_max=30", "lon_max=181",
    "time_from=2026-02-30", "time_from=2026-03-01&time_to=2026-01-01",
    "sample_offset=-1", "detection_id=bad", "taxon=",
  ]) assert.throws(() => parseEdnaState(query), /Invalid eDNA/);
});

test("an unfiltered eDNA URL has no hidden method or control choice", () => {
  assert.deepEqual(parseEdnaState("view=edna").filters, {});
});
