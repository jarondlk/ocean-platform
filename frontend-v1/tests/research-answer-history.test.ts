import assert from "node:assert/strict";
import test from "node:test";
import { loadAnswerHistory } from "../src/research-answer-history.ts";
import { createAnswerClient, createEvidenceClient } from "../src/research-evidence-service.ts";
import { ResearchEvidenceClientError } from "../src/research-evidence-http.ts";
import { mergeAnswerSnapshot } from "../src/research-answer-state.ts";
import * as f from "./research-evidence-fixtures.ts";
const id = (index: number) => `00000000-0000-0000-0000-${index.toString(16).padStart(12, "0")}`;
function harness() {
  const jobs = Array.from({ length: 31 }, (_, index) => f.job("completed", id(index + 1))); jobs[30] = f.job("queued", id(31)); jobs[30].latest_event_cursor = 1;
  const calls: { path: string; body: any }[] = []; let current = true, denied = 0, revision = f.policy;
  let pause: Promise<void> | undefined;
  const fetcher = async (path: string, init?: RequestInit) => {
    const body = JSON.parse(init!.body as string); calls.push({ path, body }); if (pause) await pause;
    if (path.endsWith("answers/list")) return new Response(JSON.stringify({ ...f.listing(jobs.slice(body.cursor ? 25 : 0, body.cursor ? 31 : 25)), access_revision: revision, next_cursor: body.cursor ? null : "next25" }));
    if (path.endsWith("answers/status")) return denied ? new Response("untrusted malformed private error", { status: denied }) : new Response(JSON.stringify(f.response(jobs.find(job => job.id === body.job_id)!)));
    if (path.endsWith("answers/events")) return new Response(JSON.stringify(f.events(body.job_id, body.after_cursor, jobs[30].latest_event_cursor - body.after_cursor, jobs[30].latest_event_cursor)));
    if (path.endsWith("evidence/list")) { const original = f.receipt(); original.run_id = f.key; original.binding.conversation_id = f.key; original.input_version = 7; return new Response(JSON.stringify({ version: "research-evidence-v1", access_revision: f.evidencePolicy, run_id: f.run, input_version: 1, offset: 0, items: [original], next_offset: null, total: 1 })); }
    throw new Error("Read must never dispatch generation or mutation");
  };
  const options = { answers: createAnswerClient({ fetcher }), evidence: createEvidenceClient({ fetcher }), address: f.runAddress, pages: 1, receiptLimit: 100, selectedJobId: id(31), cached: [mergeAnswerSnapshot(undefined, jobs[30])], expectedAccessRevision: null, signal: new AbortController().signal, isCurrent: () => current };
  return { options, jobs, calls, setCurrent: (value: boolean) => { current = value; }, deny: (status: number) => { denied = status; }, revision: (value: string) => { revision = value; }, pause: (value: Promise<void>) => { pause = value; } };
}
test("31 server answers keep the freshly acknowledged off-page active job and poll its separate event cursor", async () => {
  const h = harness(), first = await loadAnswerHistory(h.options);
  assert.equal(first.views.length, 26); assert.equal(first.views.at(-1)?.job.id, id(31)); assert.equal(first.views.at(-1)?.event_cursor, 1); assert.equal(first.receipts[0].input_version, 7);
  h.jobs[30].latest_event_cursor = 2; const second = await loadAnswerHistory({ ...h.options, cached: first.views, expectedAccessRevision: f.policy });
  assert.equal(second.views.at(-1)?.event_cursor, 2); assert.deepEqual(second.views.at(-1)?.activity.map(value => value.cursor), [1, 2]);
  assert.equal(h.calls.filter(value => value.path.endsWith("/status")).length, 2); assert.equal(h.calls.filter(value => value.path.endsWith("/submit") || value.path.endsWith("/cancel")).length, 0);
  const more = await loadAnswerHistory({ ...h.options, pages: 2, cached: second.views }); assert.equal(more.views.length, 31); assert.equal(new Set(more.views.map(value => value.job.id)).size, 31); assert.equal(more.next, null);
  assert.equal(h.calls.filter(value => value.path.endsWith("/status")).length, 2);
});
for (const status of [401, 403, 503]) test(`off-page ${status} cannot retain cached private answers`, async () => { const h = harness(); h.deny(status); await assert.rejects(loadAnswerHistory(h.options), error => error instanceof ResearchEvidenceClientError && error.status_code === status); assert.equal(h.calls.some(value => value.path.endsWith("evidence/list")), false); });
test("a missing selected answer is reported for guarded publication rather than retained from stale cache", async () => {
  const h = harness(); h.deny(404); const result = await loadAnswerHistory(h.options); assert.equal(result.views.length, 25); assert.equal(result.unavailableJobId, id(31)); assert.equal(result.views.some(value => value.job.id === id(31)), false);
});
test("only an explicit current selection authorizes status backfill, not arbitrary cached private history", async () => {
  const h = harness(); const result = await loadAnswerHistory({ ...h.options, selectedJobId: null }); assert.equal(result.views.length, 25); assert.equal(h.calls.some(value => value.path.endsWith("/status")), false);
});
for (const name of ["account", "permission", "navigation", "mutation"]) test(`late ${name} transition prevents read publication or another request`, async () => {
  const h = harness(); let release!: () => void; h.pause(new Promise<void>(resolve => { release = resolve; })); const read = loadAnswerHistory(h.options); await new Promise(resolve => setImmediate(resolve)); h.setCurrent(false); release();
  await assert.rejects(read, { name: "AbortError" }); assert.equal(h.calls.length, 1);
});
test("already aborted request never starts a client or exposes cached views", async () => { const h = harness(), abort = new AbortController(); abort.abort(); await assert.rejects(loadAnswerHistory({ ...h.options, signal: abort.signal }), { name: "AbortError" }); assert.equal(h.calls.length, 0); });
test("answer policy changes require reauthorization; independent evidence resource revision is permitted", async () => {
  const h = harness(); const result = await loadAnswerHistory({ ...h.options, expectedAccessRevision: f.policy }); assert.equal(result.listing.access_revision, f.policy); assert.equal(result.receipts.length, 1);
  h.revision(f.sha); const before = h.calls.length; await assert.rejects(loadAnswerHistory({ ...h.options, expectedAccessRevision: f.policy }), error => error instanceof ResearchEvidenceClientError && error.status_code === 409); assert.equal(h.calls.length, before + 1);
});
test("bounded public read window rejects invalid page counts before contacting a service", async () => { const h = harness(); for (const pages of [0, 21, NaN]) await assert.rejects(loadAnswerHistory({ ...h.options, pages })); for (const receiptLimit of [0, 2001, 1.5]) await assert.rejects(loadAnswerHistory({ ...h.options, receiptLimit })); assert.equal(h.calls.length, 0); });
