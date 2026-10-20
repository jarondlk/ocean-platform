import assert from "node:assert/strict";
import test from "node:test";
import { createEvidenceHttp, MAX_EVIDENCE_RESPONSE_BYTES, ResearchEvidenceClientError, type EvidenceHttpAction } from "../src/research-evidence-http.ts";
const invalid = (error: unknown) => error instanceof ResearchEvidenceClientError && error.code === "invalid_response";
for (const action of ["answers/submit", "answers/status", "answers/events", "answers/cancel", "answers/list", "evidence/list", "evidence/open", "evidence/page", "evidence/export"] as EvidenceHttpAction[]) test(`separate ${action} uses fixed same-origin safe transport`, async () => {
  const http = createEvidenceHttp({ tokenProvider: () => "in-memory-token", fetcher: async (path, init) => {
    assert.equal(path, `/research/${action}`); assert.equal(init!.method, "POST"); assert.equal(init!.credentials, "omit"); assert.equal(init!.cache, "no-store"); assert.equal(init!.redirect, "error");
    assert.equal((init!.headers as Record<string, string>).Authorization, "Bearer in-memory-token"); assert.deepEqual(JSON.parse(String(init!.body)), { id: "opaque" }); return new Response('{"ok":true}');
  } }); assert.deepEqual(await http(action, { id: "opaque" }), { ok: true });
});
for (const status of [401, 403, 404, 409, 422, 503]) test(`evidence HTTP${status} is authoritative despite unreadable error details`, async () => {
  await assert.rejects(createEvidenceHttp({ maxResponseBytes: 1, fetcher: async () => new Response("untrusted private backend error {", { status, headers: { "content-length": "9999999" } }) })("answers/status", {}), error => error instanceof ResearchEvidenceClientError && error.status_code === status && !error.message.includes("private"));
});
for (const raw of ['{"x":1,"x":2}', '{"x":1,"\\u0078":2}', '{"x":9007199254740992}', '{"x":1e999}', '{"x":"\\ud800"}', '{"\\ud800":1}', `{"x":${"[".repeat(129)}0${"]".repeat(129)}}`, '{bad']) test("ambiguous/nonfinite/unsafe/deep/malformed successful evidence JSON is rejected", async () => {
  await assert.rejects(createEvidenceHttp({ fetcher: async () => new Response(raw) })("evidence/open", {}), invalid);
});
test("response bounds apply to actual bytes, announced bytes and strict UTF-8", async () => {
  for (const response of [new Response("{}", { headers: { "content-length": "33" } }), new Response(" ".repeat(33)), new Response(new Uint8Array([0xc3, 0x28]))]) await assert.rejects(createEvidenceHttp({ maxResponseBytes: 32, fetcher: async () => response })("evidence/page", {}), invalid);
  assert.equal(MAX_EVIDENCE_RESPONSE_BYTES, 8 * 1024 * 1024);
});
test("invalid request values, excessive requests and arbitrary routes do not reach fetch", async () => {
  let calls = 0; const http = createEvidenceHttp({ fetcher: async () => { calls++; return new Response('{}'); } });
  const cyclic: Record<string, unknown> = {}; cyclic.self = cyclic;
  for (const input of [cyclic, { private: "x".repeat(65536) }, { value: "\ud800" }, { value: Infinity }, { get value() { throw new Error("must never run getter"); } }]) await assert.rejects(http("evidence/open", input), error => error instanceof ResearchEvidenceClientError && error.status_code === 422);
  await assert.rejects(http("../legacy/chat" as EvidenceHttpAction, {})); assert.equal(calls, 0);
});
test("abort during late noncooperative fetch discards the response without restoring protected data", async () => {
  let release!: (response: Response) => void, started!: () => void, discarded = false; const began = new Promise<void>(resolve => { started = resolve; });
  const http = createEvidenceHttp({ fetcher: async () => { started(); return new Promise(resolve => { release = resolve; }); } });
  const abort = new AbortController(); const pending = http("answers/status", {}, abort.signal); await began; abort.abort(); await assert.rejects(pending, { name: "AbortError" });
  release(new Response(new ReadableStream({ cancel() { discarded = true; } }))); await new Promise(resolve => setImmediate(resolve)); assert.equal(discarded, true);
});
