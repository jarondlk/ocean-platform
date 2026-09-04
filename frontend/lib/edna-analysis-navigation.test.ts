import assert from "node:assert/strict";
import test from "node:test";
import { analysisHref, parseAnalysisState } from "./edna-analysis-navigation.ts";
import { evidenceDeepLinks } from "./citation-navigation.ts";

test("analysis navigation round-trips exact run/table/result/method/page", () => {
  const state = { analysisId: "a".repeat(64), table: "diversity" as const, resultId: "b".repeat(64), method: "qcauto_target", offset: 100 };
  assert.deepEqual(parseAnalysisState(analysisHref(state).split("?")[1]), state);
  for (const q of ["analysis_id=bad", "analysis_id=", "table=bad", "assignment_method=bad", "offset=-1", `result_id=${"b".repeat(64)}`]) assert.throws(() => parseAnalysisState(q));
});

test("eDNA analysis citations link to the exact analysis and provenance", () => {
  const id = "a".repeat(64);
  const links = evidenceDeepLinks({ valid: true, cited: true, evidenceRole: "context", kind: "context", citationId: `analysis_edna_${id}_diversity`, title: "eDNA diversity", detail: "", context: { doc_id: `analysis_edna_${id}_diversity`, context_type: "analysis", title: "eDNA diversity", text: "", source_family: "edna_metabarcoding", analysis_id: id, table: "diversity" } });
  assert.equal(links.length, 2);
  assert.ok(links[1].href.includes(`view=edna_analysis&analysis_id=${id}&table=diversity`));
});
