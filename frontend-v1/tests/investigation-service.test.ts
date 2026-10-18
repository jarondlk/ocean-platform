import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createInvestigationClient, executeInvestigationMutation, InvestigationClientError, MAX_INVESTIGATION_RESPONSE_BYTES, validateInvestigationRequest } from "../src/investigation-service.ts";
import type { InvestigationClient, InvestigationMutationIntent, InvestigationRequests } from "../src/investigation-service.ts";

type WireCase = { method: keyof InvestigationRequests; path: string; payload: Record<string, unknown>; expected: Record<string, unknown>; status: number };
const wire = JSON.parse(readFileSync(new URL("../../docs/plans/ocean-v1/evidence/C18/client-wire.json", import.meta.url), "utf8")) as { cases: WireCase[]; method_count: number; request_count: number; source_before_sha256: Record<string, string>; source_after_sha256: Record<string, string> };
const invoke = (client: InvestigationClient, sample: WireCase, signal?: AbortSignal) => (client[sample.method] as (request: unknown, signal?: AbortSignal) => Promise<unknown>)(sample.payload, signal);
const response = (value: unknown, init?: ResponseInit) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" }, ...init });
const success = (method: WireCase["method"]) => wire.cases.find((sample) => sample.method === method && sample.status === 200)!;
const creation = success("create"), reading = success("get");
const invalidResponse = (error: unknown) => error instanceof InvestigationClientError && error.code === "invalid_response";
const invalidRequest = (error: unknown) => error instanceof InvestigationClientError && error.code === "invalid_request" && error.status_code === 422;

test("wire corpus is from all fourteen actual unchanged C17 HTTP operations", () => {
  assert.equal(wire.method_count, 14); assert.equal(wire.request_count, wire.cases.length);
  assert.deepEqual(wire.source_before_sha256, wire.source_after_sha256);
  assert.equal(new Set(wire.cases.map((sample) => sample.method)).size, 14);
});
for (const [index, sample] of wire.cases.entries()) test(`actual Python HTTP wire ${index + 1}: ${sample.method} ${sample.status}`, async () => {
  let called = 0;
  const client = createInvestigationClient({ fetcher: async (path, init) => {
    called++; assert.equal(path, sample.path); assert.equal(init?.method, "POST"); assert.equal(init.credentials, "omit"); assert.equal(init.cache, "no-store"); assert.equal(init.redirect, "error");
    assert.equal(new Headers(init.headers).get("Content-Type"), "application/json"); assert.equal(new Headers(init.headers).get("Authorization"), null);
    assert.deepEqual(JSON.parse(init.body as string), await validateInvestigationRequest(sample.method, sample.payload));
    return response(sample.expected, { status: sample.status });
  } });
  if (sample.status === 200) assert.deepEqual(await invoke(client, sample), sample.expected);
  else await assert.rejects(invoke(client, sample), (error: unknown) => error instanceof InvestigationClientError && error.status_code === sample.status);
  assert.equal(called, 1);
});

for (const [status, code] of [[401, "authentication_required"], [403, "access_denied"], [404, "not_found"], [409, "conflict"], [422, "invalid_request"], [503, "investigations_unavailable"]] as const) test(`HTTP ${status} remains authoritative with malformed or misleading bodies`, async () => {
  for (const body of ["<html>proxy error</html>", JSON.stringify({ error: { code: "pretend_success", message: "Do not trust this message" } }), "x".repeat(100000)]) {
    let cancelled = false;
    const stream = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(new TextEncoder().encode(body)); }, cancel() { cancelled = true; } });
    await assert.rejects(invoke(createInvestigationClient({ fetcher: async () => new Response(stream, { status }) }), reading), (error: unknown) => error instanceof InvestigationClientError && error.status_code === status && error.code === code);
    assert.equal(cancelled, true);
  }
});

for (const [label, sample, mutate] of [
  ["wrong version", reading, (v: Record<string, any>) => { v.version = "other"; }],
  ["unknown owner response field", reading, (v: Record<string, any>) => { v.owner_user_id = "private-other"; }],
  ["cross-investigation context", reading, (v: Record<string, any>) => { v.context.investigation_id = crypto.randomUUID(); }],
  ["wrong current context revision", reading, (v: Record<string, any>) => { v.context.id = crypto.randomUUID(); }],
  ["wrong hash", reading, (v: Record<string, any>) => { v.context.payload_sha256 = "bad"; }],
  ["noninteger version", reading, (v: Record<string, any>) => { v.investigation.metadata_version = 1.5; }],
  ["null timestamp", reading, (v: Record<string, any>) => { v.investigation.created_at = null; }],
  ["noncanonical UUID", reading, (v: Record<string, any>) => { v.investigation.id = v.investigation.id.toUpperCase(); }],
  ["legacy imported history", reading, (v: Record<string, any>) => { v.legacy_history_import = "ready"; }],
  ["wrong create snapshot", creation, (v: Record<string, any>) => { v.context.snapshot_id = "0".repeat(64); }],
  ["uncommitted successful mutation", creation, (v: Record<string, any>) => { v.operation.state = "prepared"; }],
  ["wrong operation kind", creation, (v: Record<string, any>) => { v.operation.kind = "refresh"; }],
  ["wrong candidate revision", creation, (v: Record<string, any>) => { v.operation.candidate_revision_id = crypto.randomUUID(); }],
  ["conversation from another owner investigation", success("getConversation"), (v: Record<string, any>) => { v.conversation.investigation_id = crypto.randomUUID(); }],
  ["unavailable history silently ready", success("getConversation"), (v: Record<string, any>) => { v.conversation.history_status = "available"; }],
  ["wrong refresh predecessor", success("refresh"), (v: Record<string, any>) => { v.investigation.predecessor_revision_id = crypto.randomUUID(); }],
  ["renamed different metadata", success("rename"), (v: Record<string, any>) => { v.investigation.name = "Different"; }],
  ["renamed different conversation", success("renameConversation"), (v: Record<string, any>) => { v.conversation.name = "Different"; }],
  ["archive failed to archive", success("archive"), (v: Record<string, any>) => { v.investigation.status = "active"; }],
  ["omitted list continuation", success("listConversations"), (v: Record<string, any>) => { v.next_after_id = crypto.randomUUID(); }],
] as const) test(`rejects ${label}`, async () => {
  const value = structuredClone(sample.expected); mutate(value);
  await assert.rejects(invoke(createInvestigationClient({ fetcher: async () => response(value) }), sample), invalidResponse);
});
test("attached and pinned references remain distinct while resolution joins exact order", async () => {
  const sample = wire.cases.find((sample) => sample.method === "changeContext" && (sample.payload.change as { op: string }).op === "pin")!;
  const value = structuredClone(sample.expected) as Record<string, any>;
  assert.equal(value.context.attachments.length, 1); assert.equal(value.context.pins.length, 1); assert.equal(value.context.resolution.length, 2);
  assert.deepEqual(await invoke(createInvestigationClient({ fetcher: async () => response(value) }), sample), value);
  value.context.resolution[1].reference.id = "different:object";
  await assert.rejects(invoke(createInvestigationClient({ fetcher: async () => response(value) }), sample), invalidResponse);
});
test("refresh branch exposes unavailable selections without rewriting old snapshots", async () => {
  const sample = success("refresh"), expected = sample.expected as Record<string, any>;
  assert.notEqual(expected.context.snapshot_id, (creation.expected.context as Record<string, unknown>).snapshot_id);
  assert.equal(expected.context.refresh_unresolved.length, 2);
  assert.equal(expected.context.resolution[0].status, "unavailable");
  assert.deepEqual(await invoke(createInvestigationClient({ fetcher: async () => response(expected) }), sample), expected);
});

for (const [key, value] of [
  ["name", " padded "], ["name", "control\nname"], ["name", "x".repeat(201)], ["name", "\ud800"], ["name", 4],
  ["idempotency_key", "UPPERCASE"], ["idempotency_key", null], ["snapshot_id", "../real-data"], ["snapshot_id", "a".repeat(63)],
  ["scope", null], ["scope", { version: 1, role: "admin" }], ["user_id", crypto.randomUUID()], ["__test_identity", "admin"],
] as const) test(`invalid create request never dispatches ${key}=${JSON.stringify(value)}`, async () => {
  await assert.rejects(invoke(createInvestigationClient({ fetcher: async () => { assert.fail("Invalid request must not dispatch"); } }), { ...creation, payload: { ...creation.payload, [key]: value } }), invalidRequest);
});
for (const [method, request] of [
  ["list", { limit: 0 }], ["list", { limit: 101 }], ["list", { limit: null }], ["list", { limit: "25" }], ["list", { after_id: "" }],
  ["archive", { ...success("archive").payload, archived: null }], ["archive", { ...success("archive").payload, expected_version: Number.MAX_SAFE_INTEGER + 1 }],
  ["getContext", { ...success("getContext").payload, revision_id: "latest" }],
  ["changeContext", { ...success("changeContext").payload, change: { op: "attach", scope: creation.payload.scope } }],
  ["changeContext", { ...success("changeContext").payload, change: { op: "scope", scope: creation.payload.scope, reference: { kind: "catalogue", id: "d", snapshot_id: "a".repeat(64) } } }],
  ["changeContext", { ...success("changeContext").payload, change: { op: "attach", reference: { kind: "url", id: "https://remote", snapshot_id: "a".repeat(64) } } }],
  ["changeContext", { ...success("changeContext").payload, change: { op: "attach", reference: { kind: "catalogue", id: "../private", snapshot_id: "a".repeat(64) } } }],
  ["refresh", { ...success("refresh").payload, target_snapshot_id: null }],
] as const) test(`strict method request ${method} ${JSON.stringify(request).slice(0, 70)}`, async () => {
  await assert.rejects(validateInvestigationRequest(method, request), invalidRequest);
});
test("non-JSON, cyclic, undefined, sparse and accessor requests cannot bypass validation", async () => {
  const cycle: Record<string, unknown> = {}; cycle.self = cycle;
  for (const supplied of [cycle, undefined, new Date(), { ...creation.payload, name: undefined }, { ...creation.payload, scope: { value: Infinity } }, { get name() { return assert.fail("Getter must not execute"); } }, [,,,]]) await assert.rejects(validateInvestigationRequest("create", supplied), invalidRequest);
});
test("oversized malformed scientific filters never reach network side effects", async () => {
  const request = structuredClone(creation.payload) as Record<string, any>;
  request.scope.sources.ctd.filters.variables = Array.from({ length: 5000 }, (_, i) => `v${i}${"x".repeat(100)}`);
  await assert.rejects(validateInvestigationRequest("create", request), invalidRequest);
});
for (const [label, body] of [
  ["duplicate top-level key", '{"version":"investigations-v1","version":"investigations-v1"}'],
  ["escaped duplicate key", '{"version":"investigations-v1","ver\\u0073ion":"investigations-v1"}'],
  ["nested duplicate key", '{"version":"investigations-v1","context":{"id":"one","id":"two"}}'],
  ["unsafe integer", '{"value":9007199254740993}'], ["nonfinite number", '{"value":1e400}'], ["lone surrogate", '{"value":"\\ud800"}'],
  ["deep JSON", "[".repeat(130) + "0" + "]".repeat(130)], ["HTML", "<html>sign in</html>"],
] as const) test(`bounded decoder rejects ${label}`, async () => {
  await assert.rejects(invoke(createInvestigationClient({ fetcher: async () => new Response(body) }), reading), invalidResponse);
});
test("invalid UTF8 does not become a replacement-character name", async () => {
  await assert.rejects(invoke(createInvestigationClient({ fetcher: async () => new Response(new Uint8Array([0xc0, 0xaf])) }), reading), invalidResponse);
});
test("actual streamed bytes bound missing and lying Content-Length and cancel the source", async () => {
  for (const length of [null, "1", "1025", "invalid", "-1"]) {
    let cancelled = false;
    const stream = new ReadableStream<Uint8Array>({ pull(controller) { controller.enqueue(new Uint8Array(600)); }, cancel() { cancelled = true; } });
    await assert.rejects(invoke(createInvestigationClient({ maxResponseBytes: 1024, fetcher: async () => new Response(stream, { headers: length === null ? {} : { "Content-Length": length } }) }), reading), invalidResponse);
    assert.equal(cancelled, true);
  }
  for (const budget of [0, -1, 1.5, MAX_INVESTIGATION_RESPONSE_BYTES + 1]) assert.throws(() => createInvestigationClient({ maxResponseBytes: budget }), RangeError);
});
test("trusted bearer injection is optional and URL/requests never choose an identity", async () => {
  const client = createInvestigationClient({ tokenProvider: () => "trusted-in-memory", fetcher: async (_path, init) => { assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer trusted-in-memory"); return response(reading.expected); } });
  await invoke(client, reading);
  for (const token of ["", "bad token", "a\r\nb", "x".repeat(8193)]) await assert.rejects(invoke(createInvestigationClient({ tokenProvider: () => token, fetcher: async () => { assert.fail("Invalid token must not dispatch"); } }), reading), (error: unknown) => error instanceof InvestigationClientError && error.status_code === 401);
});
test("abort is honored before dispatch and for a transport which ignores the signal", async () => {
  const pre = new AbortController(); pre.abort();
  await assert.rejects(invoke(createInvestigationClient({ fetcher: async () => { assert.fail("Pre-aborted request dispatched"); } }), reading, pre.signal), { name: "AbortError" });
  let deliver!: (response: Response) => void, started!: () => void; const ready = new Promise<void>((resolve) => { started = resolve; });
  const controller = new AbortController(); let cancelled = false;
  const pending = invoke(createInvestigationClient({ fetcher: () => { started(); return new Promise<Response>((resolve) => { deliver = resolve; }); } }), reading, controller.signal);
  await ready; controller.abort(); await assert.rejects(pending, { name: "AbortError" });
  deliver(new Response(new ReadableStream({ cancel() { cancelled = true; } }))); await new Promise((resolve) => setImmediate(resolve)); assert.equal(cancelled, true);
});
test("abort cancels a stalled response reader rather than publishing its late result", async () => {
  let started!: () => void; const ready = new Promise<void>((resolve) => { started = resolve; }); let cancelled = false;
  const stream = new ReadableStream<Uint8Array>({ pull() { started(); }, cancel() { cancelled = true; } }), controller = new AbortController();
  const pending = invoke(createInvestigationClient({ fetcher: async () => new Response(stream) }), reading, controller.signal);
  await ready; await new Promise((resolve) => setImmediate(resolve)); controller.abort();
  await assert.rejects(pending, { name: "AbortError" }); assert.equal(cancelled, true);
});
test("uncertain acknowledgement replays the exact original idempotent request", async () => {
  const intent = { method: "create", request: structuredClone(creation.payload) } as InvestigationMutationIntent;
  const bodies: string[] = []; let calls = 0;
  const client = createInvestigationClient({ fetcher: async (_path, init) => { bodies.push(init?.body as string); if (++calls === 1) throw new TypeError("lost acknowledgement"); return response(creation.expected); } });
  await assert.rejects(executeInvestigationMutation(client, intent), InvestigationClientError);
  assert.deepEqual(await executeInvestigationMutation(client, intent), creation.expected); assert.equal(bodies[0], bodies[1]);
});
