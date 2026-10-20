import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createAnswerClient, createEvidenceClient } from "../src/research-evidence-service.ts";
const wire = JSON.parse(readFileSync(new URL("../../docs/plans/ocean-v1/evidence/C21/wire-initial.json", import.meta.url), "utf8")) as { kind: string; independent_scientific_review: boolean; actions: { path: string; request: Record<string, unknown>; response: Record<string, any> }[] };
test("real TypeScript clients accept all nine saved actual local Python HTTP action envelopes without generated fallbacks", async () => {
  assert.equal(wire.kind, "actual-local-synthetic-http-capture"); assert.equal(wire.independent_scientific_review, false);
  const methods = new Set<string>(); let completed = false;
  for (const captured of wire.actions) {
    const [group, method] = captured.path.slice("/research/".length).split("/"); let count = 0;
    const options = { fetcher: async (path: string, init?: RequestInit) => { count++; assert.equal(path, captured.path); assert.deepEqual(JSON.parse(init!.body as string), captured.request); return new Response(JSON.stringify(captured.response)); } };
    const client = group === "answers" ? createAnswerClient(options) : createEvidenceClient(options);
    const result = await (client as any)[method](captured.request);
    assert.deepEqual(result, captured.response); assert.equal(count, 1); assert.equal(Object.isFrozen(result), true); methods.add(`${group}/${method}`);
    if (group === "answers" && result.job?.status === "completed") { assert.equal(result.job.synthetic, false); assert.equal(result.job.answer.scientific_verification, "not_independently_verified"); completed = true; }
    if (group === "evidence" && result.receipt) assert.equal(result.receipt.id, captured.request.receipt_id);
  }
  assert.deepEqual([...methods].sort(), ["answers/submit", "answers/status", "answers/events", "answers/cancel", "answers/list", "evidence/list", "evidence/open", "evidence/page", "evidence/export"].sort()); assert.equal(completed, true);
});
