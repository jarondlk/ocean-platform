import assert from "node:assert/strict";
import test from "node:test";
import { parseEvidenceModel } from "../src/research-evidence-contract.ts";
import { createAnswerClient, createEvidenceClient } from "../src/research-evidence-service.ts";
import { ResearchEvidenceClientError } from "../src/research-evidence-http.ts";
import * as f from "./research-evidence-fixtures.ts";
const json = (value: unknown) => new Response(JSON.stringify(value));
const bad = (error: unknown) => error instanceof ResearchEvidenceClientError;
const hash = async (text: string) => Buffer.from(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text))).toString("hex");
test("answer reads, explicit submit and cancellation use all five separate typed HTTP actions", async () => {
  const calls: { path: string; body: any; init: RequestInit }[] = [];
  const client = createAnswerClient({ fetcher: async (path, init) => { const body = JSON.parse(init!.body as string); calls.push({ path, body, init: init! });
    return json(path.endsWith("/list") ? f.listing([f.job()]) : path.endsWith("/events") ? f.events() : f.response()); } });
  assert.equal((await client.list(f.runAddress)).input_version, 1); await client.status(f.jobAddress); await client.events(f.jobAddress); await client.cancel({ ...f.jobAddress, idempotency_key: f.key }); await client.submit({ ...f.runAddress, input_version: 1, locale: "en", idempotency_key: f.key });
  assert.deepEqual(calls.map(value => value.path), ["list", "status", "events", "cancel", "submit"].map(value => `/research/answers/${value}`));
  for (const call of calls) { assert.equal(call.init.cache, "no-store"); assert.equal(call.init.credentials, "omit"); assert.equal(call.init.method, "POST"); }
});
test("evidence list preserves explicitly attached original run bindings, while reads bind selected receipt/hash", async () => {
  const original = f.receipt(); original.run_id = f.key; original.input_version = 7; original.binding = { ...f.binding, conversation_id: f.key };
  const client = createEvidenceClient({ fetcher: async path => json(path.endsWith("list") ? { version: "research-evidence-v1", access_revision: f.policy, run_id: f.run, input_version: 1, offset: 0, items: [original], next_offset: null, total: 1 } : { version: "research-evidence-v1", access_revision: f.evidencePolicy, receipt: original }) });
  const value = await client.list({ ...f.runAddress, input_version: 1 }); assert.equal(value.items[0].run_id, f.key); assert.equal((await client.open(f.receiptAddress)).receipt.binding.conversation_id, f.key);
  assert.equal(Object.isFrozen(value.items[0].scope.sources.ctd), true);
});
test("page/export preserve literal retained values, scoped page totals, UTF8 content digest and server CSV escaping", async () => {
  const content = "literal,temperature\r\n'海洋 / literal,0\r\n";
  const { rows: _rows, ...base } = f.page();
  const exported = { ...base, returned_count: 1, format: "csv", filename: "retained-page.csv", mime_type: "text/csv; charset=utf-8", content_text: content, content_sha256: await hash(content), provenance: { snapshot: f.sha } };
  const client = createEvidenceClient({ fetcher: async path => json(path.endsWith("export") ? exported : f.page()) });
  assert.equal((await client.page(f.receiptAddress)).rows[0].literal, "海洋 / literal"); assert.equal((await client.export(f.receiptAddress)).content_text, content);
  exported.content_text = "unbound altered bytes"; await assert.rejects(client.export(f.receiptAddress), bad);
});
for (const [name, mutate] of [
  ["missing version", (v: any) => { delete v.version; }], ["wrong version", (v: any) => { v.version = "research-runs-v1"; }], ["unknown field", (v: any) => { v.legacy = true; }], ["synthetic flag", (v: any) => { v.job.synthetic = true; }], ["bool cursor", (v: any) => { v.job.event_cursor = false; }], ["snapshot activity injection", (v: any) => { v.job.activity = [{}]; }], ["unpublished prose", (v: any) => { v.job.status = "queued"; }], ["independent scientific approval", (v: any) => { v.job.answer.scientific_verification = "approved"; }], ["missing scientific qualification", (v: any) => { delete v.job.answer.scientific_verification; }], ["uncited receipt", (v: any) => { v.job.answer.receipt_ids = []; }], ["repeated block", (v: any) => { v.job.answer.blocks.push(v.job.answer.blocks[0]); }], ["unsafe elapsed", (v: any) => { v.job.active_elapsed_ms = Number.MAX_SAFE_INTEGER + 1; }],
] as const) test(`strict answer model rejects ${name}`, async () => { const value = f.response(f.job("completed")); mutate(value); await assert.rejects(parseEvidenceModel("AnswerResponse", value), bad); });
for (const [name, mutate] of [
  ["id/hash mismatch", (v: any) => { v.receipt.sha256 = f.policy; }], ["attachment snapshot mismatch", (v: any) => { v.receipt.attachment_reference.snapshot_id = f.policy; }], ["pin substitution", (v: any) => { v.receipt.attachment_reference.kind = "catalogue"; }], ["unknown rendered as zero", (v: any) => { v.section_total = { state: "unknown", value: 0, reason: "Source coverage unavailable" }; }], ["known without actual count", (v: any) => { v.section_total = { state: "known", value: null, reason: null }; }], ["coverage unknown without reason", (v: any) => { v.receipt.counts[0] = { state: "unknown", entity: "measurements", denominator: "complete scope" }; }], ["invalid scope dates", (v: any) => { v.receipt.scope.sources.ctd.filters.time_from = "not-a-date"; }], ["duplicate columns", (v: any) => { v.receipt.columns.push(v.receipt.columns[0]); }], ["documentary promoted to exact result", (v: any) => { v.receipt.authority = "documentary"; }],
] as const) test(`strict evidence rejects ${name}`, async () => { const value = f.page(); mutate(value); await assert.rejects(parseEvidenceModel("EvidencePageResponse", value), bad); });
test("known zero and unknown totals remain distinct, valid and immutable", async () => {
  assert.deepEqual(await parseEvidenceModel("EvidenceTotal", { state: "known", value: 0, reason: null }), { state: "known", value: 0, reason: null });
  assert.equal((await parseEvidenceModel("EvidenceTotal", { state: "unknown", value: null, reason: "Incomplete source publication" })).value, null);
});
test("quoted scientific rows and answer data never become protocol receipts by matching field names", async () => {
  const quoted = { id: "c21:receipt:domain-name", scope: { domain_specific: "literal source field / 元の値" } };
  const value = f.page(); value.rows = [quoted]; value.receipt.preview_rows = [quoted];
  assert.deepEqual((await parseEvidenceModel("EvidencePageResponse", value)).rows[0], quoted);
  const answer = f.response(f.job("completed")); answer.job.answer!.blocks[0].data = quoted;
  assert.deepEqual((await parseEvidenceModel("AnswerResponse", answer)).job.answer!.blocks[0].data, quoted);
  value.receipt.scope.sources.ctd.filters.time_from = "invalid"; await assert.rejects(parseEvidenceModel("EvidencePageResponse", value), bad);
});
for (const key of ["constructor", "__proto__", "toString", "hasOwnProperty"]) test(`strict envelopes reject undeclared inherited property name ${key}`, async () => {
  const value = Object.fromEntries([...Object.entries(f.response()), [key, { injected: true }]]);
  await assert.rejects(parseEvidenceModel("AnswerResponse", value), bad);
});
test("bad requests fail before network, including forged receipt hashes and unsafe cursors", async () => {
  let count = 0; const fetcher = async () => { count++; return json({}); }, evidence = createEvidenceClient({ fetcher }), answers = createAnswerClient({ fetcher });
  for (const request of [{ ...f.receiptAddress, expected_sha256: f.policy }, { ...f.receiptAddress, offset: -1 }, { ...f.receiptAddress, limit: 501 }, { ...f.receiptAddress, legacy: true }]) await assert.rejects(evidence.page(request as never), error => bad(error) && (error as ResearchEvidenceClientError).status_code === 422);
  for (const request of [{ ...f.runAddress, cursor: "x".repeat(4097) }, { ...f.runAddress, run_id: "../run" }]) await assert.rejects(answers.list(request as never), bad);
  assert.equal(count, 0);
});
test("typed clients reject wrong run/job/list identity, cursor bindings, locale and changed page offsets", async () => {
  for (const mutate of [(v: any) => { v.job.run_id = f.key; }, (v: any) => { v.job.id = f.key; }, (v: any) => { v.job.binding.conversation_id = f.key; }]) {
    const value = f.response(); mutate(value); await assert.rejects(createAnswerClient({ fetcher: async () => json(value) }).status(f.jobAddress), bad);
  }
  const wrongLocale = f.response(); wrongLocale.job.locale = "ja"; await assert.rejects(createAnswerClient({ fetcher: async () => json(wrongLocale) }).submit({ ...f.runAddress, input_version: 1, locale: "en", idempotency_key: f.key }), bad);
  const wrongList = f.listing([f.job()]); wrongList.items[0].input_version = 2; await assert.rejects(createAnswerClient({ fetcher: async () => json(wrongList) }).list(f.runAddress), bad);
  const wrongPage = f.page(); wrongPage.offset = 5; await assert.rejects(createEvidenceClient({ fetcher: async () => json(wrongPage) }).page(f.receiptAddress), bad);
});
for (const mutate of [(v: any) => { v.events[0].cursor = 2; }, (v: any) => { v.events[0].job_id = f.run; }, (v: any) => { v.latest_event_cursor = 0; }, (v: any) => { v.has_more = true; }, (v: any) => { v.after_cursor = 3; }]) test("events reject nonconsecutive, cross-job or inconsistent highwater pages", async () => { const value = f.events(); mutate(value); await assert.rejects(createAnswerClient({ fetcher: async () => json(value) }).events(f.jobAddress), bad); });
