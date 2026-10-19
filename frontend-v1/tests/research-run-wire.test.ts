/** Saved actual Python service envelopes; frontend CI never starts Python or a database. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createResearchRunTransport } from "../src/research-run-service.ts";
import type { ResearchRun, RunEventPage, RunListPage } from "../src/research-run-contract.ts";

type Method = "submit" | "status" | "events" | "cancel" | "clarify" | "continue" | "list";
type WireCase = { method: Method; request: Record<string, unknown>; response: Record<string, any>; status_code: number };
const fixture = JSON.parse(readFileSync(new URL("../../docs/plans/ocean-v1/evidence/C20/wire-fixtures.json", import.meta.url), "utf8")) as { version: string; synthetic_only: boolean; cases: WireCase[] };
test("saved actual wire evidence covers all seven production HTTP actions with synthetic TEST data", () => {
  assert.equal(fixture.version, "research-runs-wire-v1"); assert.equal(fixture.synthetic_only, true);
  assert.deepEqual([...new Set(fixture.cases.map(item => item.method))].sort(), ["cancel", "clarify", "continue", "events", "list", "status", "submit"]);
});
for (const [index, item] of fixture.cases.entries()) test(`actual Python envelope ${index + 1}: ${item.method} decodes through the production TypeScript client`, async () => {
  let calls = 0;
  const client = createResearchRunTransport({ fetcher: async (path, init) => {
    calls++; assert.equal(path, `/research/runs/${item.method}`); assert.equal(init?.credentials, "omit"); assert.equal(init?.cache, "no-store");
    const body = JSON.parse(String(init!.body)) as Record<string, any>;
    assert.equal(body.investigation_id, item.request.investigation_id ?? (item.request.context as any)?.binding.investigation_id);
    assert.equal(body.conversation_id, item.request.conversation_id ?? (item.request.context as any)?.binding.conversation_id);
    if (item.method === "submit") {
      const binding = (item.request.context as any).binding;
      assert.equal(body.revision_id, binding.revision_id); assert.equal(body.expected_snapshot_id, binding.snapshot_id); assert.equal(body.expected_payload_sha256, binding.payload_sha256);
      assert.equal("scope" in body, false); assert.equal("context" in body, false);
    }
    return new Response(JSON.stringify(item.response), { status: item.status_code, headers: { "Content-Type": "application/json" } });
  } });
  const invoke = client[item.method] as (request: unknown) => Promise<ResearchRun | RunEventPage | RunListPage>;
  const actual = await invoke(item.request); assert.equal(calls, 1); assert.equal(Object.isFrozen(actual), true);
  if (item.method === "events") {
    const { version: _version, ...page } = item.response; assert.deepEqual(actual, page);
    const events = actual as RunEventPage; assert.equal(events.next_cursor, events.after_cursor + events.events.length);
    assert.equal(events.has_more, events.next_cursor < events.latest_event_cursor!);
  } else if (item.method === "list") {
    assert.deepEqual(actual, { items: item.response.items, next_cursor: item.response.next_cursor });
    for (const run of (actual as RunListPage).items) { assert.equal(run.synthetic, false); assert.equal(run.result, null); assert.equal(run.event_cursor, 0); }
  } else {
    assert.deepEqual(actual, item.response.run);
    const run = actual as ResearchRun; assert.equal(run.synthetic, false); assert.equal(run.result, null); assert.deepEqual(run.activity, []); assert.equal(run.event_cursor, 0);
    if (item.method === "submit") assert.deepEqual(run.context.binding, (item.request.context as any).binding);
    if (item.method === "continue") assert.equal(run.continuation_of, item.request.run_id);
  }
});
