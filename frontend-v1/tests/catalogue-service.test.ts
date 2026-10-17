import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { CatalogueClientError, createCatalogueClient, defaultCatalogueScope } from "../src/catalogue-service.ts";
import type { CatalogueBaseRequest, CatalogueClient, CatalogueCoverageRequest, CatalogueListRequest, CatalogueOpenRequest, CataloguePublishedRequest, CatalogueQueryRequest, CatalogueRelationshipsRequest, CatalogueSnapshotsRequest } from "../src/catalogue-service.ts";

type WireCase = { name: string; path: string; payload: Record<string, unknown>; expected: Record<string, unknown>; http_tool_parity: boolean };
const wire = JSON.parse(readFileSync(new URL("../../docs/plans/ocean-v1/evidence/C16/actual-wire.json", import.meta.url), "utf8")) as { cases: WireCase[] };
const paths = { "/catalogue/snapshots": "snapshots", "/catalogue/overview": "overview", "/catalogue/list": "list", "/catalogue/open": "open", "/catalogue/coverage": "coverage", "/catalogue/query": "query", "/catalogue/relationships": "relationships", "/catalogue/analysis/get-published": "getPublished" } as const;
function invoke(client: CatalogueClient, item: WireCase, signal?: AbortSignal): Promise<unknown> {
  const method = paths[item.path as keyof typeof paths]; assert.ok(method);
  return (client[method] as (payload: unknown, signal?: AbortSignal) => Promise<unknown>)(item.payload, signal);
}
function response(value: unknown, init?: ResponseInit) { return new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" }, ...init }); }
const listing = wire.cases.find((c) => c.path === "/catalogue/list")!;
const opening = wire.cases.find((c) => c.path === "/catalogue/open" && c.payload.include_details !== true)!;
const detail = wire.cases.find((c) => c.path === "/catalogue/open" && c.payload.include_details === true)!;
const science = wire.cases.find((c) => c.path === "/catalogue/coverage")!;

for (const [index, item] of wire.cases.entries()) test(`actual frozen HTTP/tool wire ${index + 1}: ${item.name}`, async () => {
  assert.equal(item.http_tool_parity, true);
  let calls = 0;
  const client = createCatalogueClient({ fetcher: async (path, init) => {
    calls++; assert.equal(path, item.path); assert.equal(init?.method, "POST"); assert.equal(init?.credentials, "omit"); assert.equal(init?.cache, "no-store"); assert.equal(init?.redirect, "error");
    assert.equal(new Headers(init?.headers).has("Cookie"), false); assert.equal(new Headers(init?.headers).has("Authorization"), false);
    const payload = JSON.parse(init?.body as string); for (const key of ["access_binding", "access_revision", "role", "account_type", "user_id"]) assert.equal(Object.hasOwn(payload, key), false);
    assert.deepEqual(payload.scope, item.payload.scope); if (item.payload.snapshot_id) assert.equal(payload.snapshot_id, item.payload.snapshot_id);
    return response(item.expected);
  } });
  assert.deepEqual(await invoke(client, item), item.expected); assert.equal(calls, 1);
});
test("scope defaults are detached and enable all four canonical families", () => {
  const a = defaultCatalogueScope(), b = defaultCatalogueScope(); assert.deepEqual(Object.keys(a.sources), ["ctd", "metagenome", "remote_sensing", "edna_metabarcoding"]);
  assert.ok(Object.values(a.sources).every((v) => v.enabled)); a.sources.ctd.enabled = false; assert.equal(b.sources.ctd.enabled, true);
});
for (const [label, mutation] of [
  ["client access binding", (p: Record<string, unknown>) => { p.access_binding = "forged"; }],
  ["client access revision", (p: Record<string, unknown>) => { p.access_revision = "forged"; }],
  ["client role", (p: Record<string, unknown>) => { p.role = "admin"; }],
  ["limit above500", (p: Record<string, unknown>) => { p.limit = 501; }],
  ["boolean limit", (p: Record<string, unknown>) => { p.limit = true; }],
  ["null limit", (p: Record<string, unknown>) => { p.limit = null; }],
  ["null filters", (p: Record<string, unknown>) => { p.filters = null; }],
  ["null ordering", (p: Record<string, unknown>) => { p.ordering = null; }],
  ["empty cursor", (p: Record<string, unknown>) => { p.cursor = ""; }],
  ["long cursor", (p: Record<string, unknown>) => { p.cursor = "x".repeat(2049); }],
  ["foreign snapshot path", (p: Record<string, unknown>) => { p.snapshot_id = "../../private"; }],
  ["no ID tie breaker", (p: Record<string, unknown>) => { p.ordering = [{ field: "title" }]; }],
  ["duplicate order", (p: Record<string, unknown>) => { p.ordering = [{ field: "id" }, { field: "id" }]; }],
  ["alias source scope", (p: Record<string, unknown>) => { (p.scope as { sources: Record<string, unknown> }).sources.edna = {}; }],
] as const) test(`public request rejects ${label} before any fetch`, async () => {
  let calls = 0; const client = createCatalogueClient({ fetcher: async () => { calls++; return response({}); } }); const payload = structuredClone(listing.payload); mutation(payload);
  await assert.rejects(invoke(client, { ...listing, payload }), (e: unknown) => e instanceof CatalogueClientError && e.code === "invalid_request" && e.status_code === 422); assert.equal(calls, 0);
});
for (const [label, sample, mutate] of [
  ["listing snapshot mismatch", listing, (v: Record<string, unknown>) => { (v.request as Record<string, unknown>).snapshot_id = "other"; }],
  ["listing scope mismatch", listing, (v: Record<string, unknown>) => { ((v.request as { scope: ReturnType<typeof defaultCatalogueScope> }).scope).sources.ctd.enabled = false; }],
  ["listing filter mismatch", listing, (v: Record<string, unknown>) => { (v.request as Record<string, unknown>).filters = { kinds: ["dataset"] }; }],
  ["listing parent mismatch", listing, (v: Record<string, unknown>) => { (v.request as Record<string, unknown>).parent_id = "other"; }],
  ["listing limit mismatch", listing, (v: Record<string, unknown>) => { (v.request as Record<string, unknown>).limit = 499; }],
  ["open object mismatch", opening, (v: Record<string, unknown>) => { v.id = "other"; }],
  ["open snapshot mismatch", opening, (v: Record<string, unknown>) => { v.snapshot_id = "other"; }],
  ["detail extra envelope", detail, (v: Record<string, unknown>) => { v.authorized = true; }],
  ["detail wrong object", detail, (v: Record<string, unknown>) => { (v.node as Record<string, unknown>).id = "other"; }],
  ["science adapter version", science, (v: Record<string, unknown>) => { v.adapter_version = "c12-v1"; }],
  ["science extension key", science, (v: Record<string, unknown>) => { v.total = 12; }],
  ["science offset mismatch", science, (v: Record<string, unknown>) => { v.offset = 1; }],
  ["science nonprogress page", science, (v: Record<string, unknown>) => { v.next_offset = 0; }],
  ["science invented qualification", science, (v: Record<string, unknown>) => { v.qualifications = [true]; }],
  ["science wrong operation", science, (v: Record<string, unknown>) => { (v.receipt as Record<string, unknown>).operation_id = "c13.quality"; }],
  ["science wrong parameters", science, (v: Record<string, unknown>) => { (v.receipt as { parameters: Record<string, unknown> }).parameters.limit = 1; }],
  ["science wrong dataset input", science, (v: Record<string, unknown>) => { (v.receipt as { inputs: { object_id: string }[] }).inputs[1].object_id = "c13:input:" + "0".repeat(64); }],
] as const) test(`response rejects ${label}`, async () => {
  const value = structuredClone(sample.expected); mutate(value); const client = createCatalogueClient({ fetcher: async () => response(value) });
  await assert.rejects(invoke(client, sample), (e: unknown) => e instanceof CatalogueClientError && e.code === "invalid_response");
});
for (const [status, code, message] of [[401, "authentication_required", "Authentication is required"], [403, "access_denied", "Catalogue access is denied"], [404, "not_found", "Catalogue object is unavailable"], [409, "invalid_cursor", "Catalogue cursor is stale or invalid"], [422, "invalid_request", "Catalogue request is invalid"], [503, "catalogue_unavailable", "Catalogue is unavailable"]] as const) test(`preserves typed backend ${status} error parity`, async () => {
  const client = createCatalogueClient({ fetcher: async () => response({ error: { code, message } }, { status }) });
  await assert.rejects(invoke(client, listing), (e: unknown) => e instanceof CatalogueClientError && e.code === code && e.message === message && e.status_code === status);
});
for (const [label, text] of [
  ["duplicate top-level JSON", '{"error":{"code":"one","message":"m"},"error":{"code":"two","message":"m"}}'],
  ["duplicate escaped JSON", '{"error":{"code":"one","co\\u0064e":"two","message":"m"}}'],
  ["unsafe integer", '{"error":{"code":"invalid_request","message":"m","number":9007199254740993}}'],
  ["nonfinite number", '{"error":{"code":"invalid_request","message":"m","number":1e400}}'],
  ["HTML fallback", '<html>sign in</html>'],
  ["deep payload", '['.repeat(130) + '0' + ']'.repeat(130)],
] as const) test(`rejects ${label}`, async () => {
  const client = createCatalogueClient({ fetcher: async () => new Response(text) });
  await assert.rejects(invoke(client, listing), (e: unknown) => e instanceof CatalogueClientError && e.code === "invalid_response");
});
test("actual stream bytes bound missing/lying Content-Length and cancel live body", async () => {
  for (const contentLength of [null, "1", "1001", "not-a-number"]) {
    let cancelled = false;
    const stream = new ReadableStream<Uint8Array>({ pull(controller) { controller.enqueue(new TextEncoder().encode("x".repeat(600))); }, cancel() { cancelled = true; } });
    const client = createCatalogueClient({ maxResponseBytes: 1000, fetcher: async () => new Response(stream, { headers: contentLength === null ? {} : { "Content-Length": contentLength } }) });
    await assert.rejects(invoke(client, listing), CatalogueClientError); assert.equal(cancelled, true);
  }
});
test("error streams have a separate bounded budget and are cancelled", async () => {
  let cancelled = false; const stream = new ReadableStream<Uint8Array>({ pull(controller) { controller.enqueue(new Uint8Array(40_000)); }, cancel() { cancelled = true; } });
  const client = createCatalogueClient({ fetcher: async () => new Response(stream, { status: 500 }) }); await assert.rejects(invoke(client, listing), CatalogueClientError); assert.equal(cancelled, true);
});
test("invalid UTF8 is rejected", async () => {
  const client = createCatalogueClient({ fetcher: async () => new Response(new Uint8Array([0xc0, 0xaf])) }); await assert.rejects(invoke(client, listing), CatalogueClientError);
});
test("caller cancellation works before and during transport, including ignored signals", async () => {
  const before = new AbortController(); before.abort(); let called = false;
  await assert.rejects(invoke(createCatalogueClient({ fetcher: async () => { called = true; return response({}); } }), listing, before.signal), { name: "AbortError" }); assert.equal(called, false);
  const during = new AbortController(); let deliver!: (v: Response) => void; let entered!: () => void;
  const started = new Promise<void>((resolve) => { entered = resolve; }); let cancelled = false;
  const client = createCatalogueClient({ fetcher: () => { entered(); return new Promise<Response>((resolve) => { deliver = resolve; }); } });
  const pending = invoke(client, listing, during.signal); await started; during.abort(); await assert.rejects(pending, { name: "AbortError" });
  deliver(new Response(new ReadableStream({ cancel() { cancelled = true; } }))); await new Promise((resolve) => setImmediate(resolve)); assert.equal(cancelled, true);
});
test("abort while consuming a stalled response cancels its reader", async () => {
  let cancelled = false, read!: () => void; const reading = new Promise<void>((resolve) => { read = resolve; });
  const stream = new ReadableStream<Uint8Array>({ pull() { read(); }, cancel() { cancelled = true; } }); const controller = new AbortController();
  const pending = invoke(createCatalogueClient({ fetcher: async () => new Response(stream) }), listing, controller.signal); await reading; await new Promise((resolve) => setImmediate(resolve)); assert.equal(stream.locked, true); controller.abort();
  await assert.rejects(pending, { name: "AbortError" }); assert.equal(cancelled, true);
});
test("only trusted in-memory bearer provider supplies authorization", async () => {
  const client = createCatalogueClient({ tokenProvider: () => "trusted-memory-token", fetcher: async (_path, init) => { assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer trusted-memory-token"); return response(opening.expected); } });
  await invoke(client, opening);
  for (const token of ["", "bad token", "a\r\nb", "a".repeat(8193)]) await assert.rejects(invoke(createCatalogueClient({ tokenProvider: () => token, fetcher: async () => { assert.fail("invalid token must never fetch"); } }), opening), (e: unknown) => e instanceof CatalogueClientError && e.status_code === 401);
});
test("no implicit fixture fallback on network or redirect refusal", async () => {
  const client = createCatalogueClient({ fetcher: async () => { throw new TypeError("redirect refused"); } });
  await assert.rejects(invoke(client, listing), (e: unknown) => e instanceof CatalogueClientError && e.code === "invalid_response");
});
for (const [sample, key, value] of [
  [opening, "include_details", null], [opening, "include_details", "true"], [science, "parameters", null], [science, "offset", null], [science, "offset", -1],
  [science, "offset", 2 ** 53], [science, "parameters", { value: Infinity }], [science, "parameters", { value: 2 ** 53 }],
  [wire.cases.find((v) => v.path.endsWith("query"))!, "operation_id", "c14.execute"],
  [wire.cases.find((v) => v.path.endsWith("query"))!, "operation_version", "c12-v1"],
  [wire.cases.find((v) => v.path.endsWith("query"))!, "input_ids", ["one", "two"]],
] as const) test(`method-specific public request rejects ${key}=${JSON.stringify(value)}`, async () => {
  const payload = { ...sample.payload, [key]: value };
  await assert.rejects(invoke(createCatalogueClient({ fetcher: async () => { assert.fail("invalid request must never fetch"); } }), { ...sample, payload }), (e: unknown) => e instanceof CatalogueClientError && e.code === "invalid_request");
});
test("relationships reject simultaneous object and parent selectors", async () => {
  const sample = wire.cases.find((v) => v.path.endsWith("relationships"))!;
  await assert.rejects(invoke(createCatalogueClient({ fetcher: async () => { assert.fail("invalid request must never fetch"); } }), { ...sample, payload: { ...sample.payload, object_id: "one", parent_id: "two" } }), (e: unknown) => e instanceof CatalogueClientError && e.code === "invalid_request");
});
test("initial discovery cannot silently omit remaining authorized snapshots", async () => {
  const sample = wire.cases[0], value = structuredClone(sample.expected); value.next_cursor = null;
  await assert.rejects(invoke(createCatalogueClient({ fetcher: async () => response(value) }), sample), CatalogueClientError);
});
test("scientific page cannot silently lose a known remaining table page", async () => {
  const sample = wire.cases.find((v) => v.path.endsWith("get-published"))!, value = structuredClone(sample.expected); value.next_offset = null;
  await assert.rejects(invoke(createCatalogueClient({ fetcher: async () => response(value) }), sample), CatalogueClientError);
});
test("actual truncated C12 aggregate preserves known total and honest preview without a cursor", async () => {
  const sample = wire.cases.find((v) => v.path.endsWith("query") && (v.payload.parameters as Record<string, unknown>).operation_id === "c12.summary")!;
  assert.ok(sample); const expected = sample.expected as Record<string, any>;
  assert.equal(expected.rows.length, 1); assert.equal(expected.receipt.total_rows.value, 12); assert.equal(expected.receipt.preview_truncated, true); assert.equal(expected.next_offset, null);
  const actual = await invoke(createCatalogueClient({ fetcher: async () => response(sample.expected) }), sample);
  assert.deepEqual(actual, sample.expected);
});
for (const [index, sample] of wire.cases.filter((v) => v.path.endsWith("query") && ["c10.table", "c11.table", "c12.table"].includes((v.payload.parameters as Record<string, unknown>).operation_id as string) && (v.expected.receipt as { total_rows: { value: number | null } }).total_rows.value !== null).entries()) test(`actual pageable source table ${index + 1} cannot lose a known continuation`, async () => {
  assert.notEqual(sample.expected.next_offset, null); const value = structuredClone(sample.expected); value.next_offset = null;
  await assert.rejects(invoke(createCatalogueClient({ fetcher: async () => response(value) }), sample), CatalogueClientError);
});
test("actual aggregate rejects a nonprogressing continuation rather than inventing pages", async () => {
  const sample = wire.cases.find((v) => v.path.endsWith("query") && (v.payload.parameters as Record<string, unknown>).operation_id === "c12.summary")!;
  const value = structuredClone(sample.expected); value.next_offset = 0;
  await assert.rejects(invoke(createCatalogueClient({ fetcher: async () => response(value) }), sample), CatalogueClientError);
});
for (const [status, code] of [[401, "authentication_required"], [403, "access_denied"], [404, "not_found"], [409, "invalid_cursor"]] as const) test(`HTTP ${status} remains authoritative with malformed, misleading or unbounded error body`, async () => {
  for (const body of ["<html>proxy error</html>", JSON.stringify({ error: { code: "catalogue_unavailable", message: "misleading" } }), "x".repeat(65_537)]) {
    let cancelled = false;
    const stream = new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode(body)); }, cancel() { cancelled = true; } });
    const client = createCatalogueClient({ fetcher: async () => new Response(stream, { status }) });
    await assert.rejects(invoke(client, listing), (e: unknown) => e instanceof CatalogueClientError && e.code === code && e.status_code === status); assert.equal(cancelled, true);
  }
});
test("qualified unavailable scientific results preserve reasons without inventing input dependencies", async () => {
  const value = structuredClone(science.expected) as Record<string, any>;
  value.columns = []; value.rows = []; value.next_offset = null;
  value.receipt.inputs = value.receipt.inputs.filter((row: { object_id: string }) => row.object_id === "scientific:registry");
  value.receipt.availability = { status: "unavailable", reason: "No registered quality operation; metadata remains inspectable" };
  value.receipt.total_rows = { state: "unknown", entity: "rows", denominator: "Complete scoped scientific operation output rows", reason: "No registered quality operation", basis: "complete_scope", value: null };
  value.receipt.returned_count = 0; value.receipt.preview_truncated = false; value.receipt.source_completeness = "unavailable"; value.receipt.query_completion = "not_started";
  const client = createCatalogueClient({ fetcher: async () => response(value) }); assert.deepEqual(await invoke(client, science), value);
});
test("statistics aliases retain exact source dataset dependency identity", async () => {
  const value = structuredClone(science.expected) as Record<string, any>, hashed = value.receipt.inputs.find((row: { object_id: string }) => row.object_id.startsWith("c13:input:")).object_id as string;
  const sample = { ...science, payload: { ...science.payload, object_id: hashed.replace("c13:input:", "c13:statistics:") } };
  assert.deepEqual(await invoke(createCatalogueClient({ fetcher: async () => response(value) }), sample), value);
});
// Compile-time public API anchors: no server-owned authorization fields are required.
type PublicRequests = CatalogueBaseRequest | CatalogueCoverageRequest | CatalogueListRequest | CatalogueOpenRequest | CataloguePublishedRequest | CatalogueQueryRequest | CatalogueRelationshipsRequest | CatalogueSnapshotsRequest;
const publicRequest: PublicRequests = { snapshot_id: "synthetic-snapshot-1", scope: defaultCatalogueScope() }; void publicRequest;
