import assert from "node:assert/strict";
import test from "node:test";
import { defaultCatalogueScope } from "../src/catalogue-service.ts";
import { mergeRunEvents, mergeRunSnapshot, researchRunAddress, type ResearchRun, type RunContext, type RunEventPage } from "../src/research-run-contract.ts";
import { createResearchRunTransport, MAX_RUN_RESPONSE_BYTES, ResearchRunClientError, RESEARCH_RUNS_VERSION } from "../src/research-run-service.ts";

const uuid = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, "0")}`;
const snapshot = "a".repeat(64), digest = "b".repeat(64);
function context(): RunContext { return { binding: { investigation_id: uuid(1), conversation_id: uuid(2), revision_id: uuid(3), snapshot_id: snapshot, payload_sha256: digest }, scope: defaultCatalogueScope(), attachments: [{ kind: "catalogue", id: "dataset:public", snapshot_id: snapshot }, { kind: "artifact", id: "artifact:retained", snapshot_id: "c".repeat(64) }], pins: [] }; }
function run(overrides: Partial<ResearchRun> = {}): ResearchRun { return { id: uuid(4), context: context(), question: "Explore selected inventory 🌊", status: "queued", active_elapsed_ms: 0, event_cursor: 0, latest_event_cursor: 1, activity: [], continuation_of: null, clarification: null, clarification_id: null, result: null, error: null, synthetic: false, ...overrides }; }
const submit = () => ({ context: context(), question: run().question, idempotency_key: uuid(5) });
const address = () => researchRunAddress(run());
const envelope = (value = run()) => ({ version: RESEARCH_RUNS_VERSION, run: value });
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
const invalidResponse = (error: unknown) => error instanceof ResearchRunClientError && error.code === "invalid_response";
const invalidRequest = (error: unknown) => error instanceof ResearchRunClientError && error.code === "invalid_request" && error.status_code === 422;
function eventPage(): RunEventPage & { version: string } { return { version: RESEARCH_RUNS_VERSION, run_id: uuid(4), binding: context().binding, after_cursor: 0, next_cursor: 1, latest_event_cursor: 2, has_more: true, events: [{ cursor: 1, run_id: uuid(4), elapsed_ms: 0, kind: "accepted", summary: { en: "Accepted", ja: "受付済み" } }] }; }

test("all seven HTTP operations use fixed same-origin POST, no cookies/cache/redirects, and an injected memory token", async () => {
  const calls: { path: string; init: RequestInit; body: Record<string, unknown> }[] = [];
  const client = createResearchRunTransport({ tokenProvider: () => "private-memory-token", fetcher: async (path, init) => {
    calls.push({ path, init: init!, body: JSON.parse(String(init!.body)) as Record<string, unknown> });
    if (path.endsWith("/events")) return json(eventPage());
    if (path.endsWith("/list")) return json({ version: RESEARCH_RUNS_VERSION, items: [run()], next_cursor: null });
    return json(envelope(path.endsWith("/continue") ? run({ id: uuid(8), continuation_of: uuid(4) }) : run()));
  } });
  await client.submit(submit()); await client.status(address()); await client.events({ ...address(), after_cursor: 0 });
  await client.cancel({ ...address(), idempotency_key: uuid(6) });
  await client.clarify({ ...address(), idempotency_key: uuid(7), clarification_id: uuid(9), answer: "Keep this scope" });
  await client.continue({ ...address(), idempotency_key: uuid(8) });
  await client.list({ investigation_id: uuid(1), conversation_id: uuid(2) });
  assert.deepEqual(calls.map(item => item.path), ["submit", "status", "events", "cancel", "clarify", "continue", "list"].map(name => `/research/runs/${name}`));
  for (const { init } of calls) {
    assert.equal(init.method, "POST"); assert.equal(init.credentials, "omit"); assert.equal(init.cache, "no-store"); assert.equal(init.redirect, "error");
    assert.deepEqual(init.headers, { Accept: "application/json", "Content-Type": "application/json", Authorization: "Bearer private-memory-token" });
  }
  assert.deepEqual(calls[0].body, { investigation_id: uuid(1), conversation_id: uuid(2), revision_id: uuid(3), expected_snapshot_id: snapshot, expected_payload_sha256: digest, question: run().question, idempotency_key: uuid(5) });
  assert.equal("scope" in calls[0].body, false); assert.equal("attachments" in calls[0].body, false);
  assert.equal(calls[2].body.limit, 100); assert.deepEqual(calls[6].body, { investigation_id: uuid(1), conversation_id: uuid(2), limit: 25, cursor: null });
});

test("production run context and retained artifact identity are detached and deeply frozen", async () => {
  const source = envelope(); const result = await createResearchRunTransport({ fetcher: async () => json(source) }).submit(submit());
  assert.equal(result.synthetic, false); assert.equal(result.result, null); assert.equal(Object.isFrozen(result.context.scope.sources.ctd), true);
  assert.equal(Object.isFrozen(result.context.attachments[1]), true); assert.equal(result.context.attachments[1].snapshot_id, "c".repeat(64));
  source.run.context.scope.sources.ctd.enabled = false; assert.equal(result.context.scope.sources.ctd.enabled, true);
});

test("lost acknowledgement replay sends the exact original key, question and expected revision", async () => {
  const bodies: string[] = []; let attempts = 0;
  const client = createResearchRunTransport({ fetcher: async (_path, init) => { bodies.push(String(init!.body)); if (++attempts === 1) throw new Error("private infrastructure details"); return json(envelope()); } });
  const input = submit(); await assert.rejects(client.submit(input), error => invalidResponse(error) && !(error as Error).message.includes("infrastructure"));
  const recovered = await client.submit(input); assert.equal(recovered.id, uuid(4)); assert.equal(bodies[0], bodies[1]);
});

test("caller mutation during asynchronous token resolution cannot rebind the accepted submission", async () => {
  let release!: () => void; const ready = new Promise<void>(resolve => { release = resolve; }); let tokenStarted!: () => void; const started = new Promise<void>(resolve => { tokenStarted = resolve; });
  const client = createResearchRunTransport({ tokenProvider: async () => { tokenStarted(); await ready; return undefined; }, fetcher: async (_path, init) => { assert.equal(JSON.parse(String(init!.body)).revision_id, uuid(3)); return json(envelope()); } });
  const input = submit(); const pending = client.submit(input); await started;
  (input.context.binding as { revision_id: string }).revision_id = uuid(99); input.question = "Changed"; release();
  assert.equal((await pending).context.binding.revision_id, uuid(3));
});

const runMutations: [string, (value: any) => void][] = [
  ["version", value => { value.version = "old"; }], ["unknown envelope field", value => { value.private = "secret"; }],
  ["foreign owner", value => { value.run.context.binding.investigation_id = uuid(99); }], ["foreign conversation", value => { value.run.context.binding.conversation_id = uuid(99); }],
  ["foreign run", value => { value.run.id = uuid(99); }], ["status", value => { value.run.status = "approved"; }],
  ["synthetic production flag", value => { value.run.synthetic = true; }], ["numeric fixture flag", value => { value.run.synthetic = 0; }],
  ["fabricated result", value => { value.run.result = { body: { en: "answer", ja: "答え" } }; }], ["embedded private events", value => { value.run.activity = eventPage().events; }],
  ["nonzero snapshot cursor", value => { value.run.event_cursor = 1; }], ["boolean snapshot cursor", value => { value.run.event_cursor = false; }],
  ["unsafe high water", value => { value.run.latest_event_cursor = Number.MAX_SAFE_INTEGER + 1; }], ["negative elapsed", value => { value.run.active_elapsed_ms = -1; }],
  ["missing high water", value => { delete value.run.latest_event_cursor; }], ["unknown scope field", value => { value.run.context.scope.made_up = true; }],
  ["substituted catalogue snapshot", value => { value.run.context.attachments[0].snapshot_id = "d".repeat(64); }],
  ["duplicate references", value => { value.run.context.pins = [value.run.context.attachments[0], value.run.context.attachments[0]]; }],
  ["missing clarification token", value => { value.run.status = "awaiting_clarification"; value.run.clarification = { en: "Which period?", ja: "どの期間？" }; }],
  ["nonwaiting clarification", value => { value.run.clarification_id = uuid(9); }], ["oversized public text", value => { value.run.error = { en: "x".repeat(2001), ja: "失敗" }; }],
  ["unsafe event counter", value => { value.run.event_cursor = 9007199254740992; }], ["lone surrogate", value => { value.run.question = "\ud800"; }],
];
for (const [label, mutate] of runMutations) test(`run responses fail closed on ${label}`, async () => {
  const value = structuredClone(envelope()); mutate(value);
  await assert.rejects(createResearchRunTransport({ fetcher: async () => json(value) }).status(address()), invalidResponse);
});

test("submit responses must match the original expected context and question; continuation must link to its parent", async () => {
  for (const value of [run({ context: { ...context(), binding: { ...context().binding, revision_id: uuid(99) } } }), run({ question: "Substituted" })]) await assert.rejects(createResearchRunTransport({ fetcher: async () => json(envelope(value)) }).submit(submit()), invalidResponse);
  await assert.rejects(createResearchRunTransport({ fetcher: async () => json(envelope(run({ id: uuid(8), continuation_of: uuid(99) }))) }).continue({ ...address(), idempotency_key: uuid(7) }), invalidResponse);
});

test("bounded event pages preserve high water separately from committed cursor and continue across status snapshots", async () => {
  const client = createResearchRunTransport({ fetcher: async () => json(eventPage()) });
  const page = await client.events({ ...address(), after_cursor: 0 }); const first = mergeRunEvents(run(), page);
  assert.equal(first.event_cursor, 1); assert.equal(first.latest_event_cursor, 2); assert.equal(first.activity.length, 1);
  const status = mergeRunSnapshot(first, run({ status: "running", active_elapsed_ms: 100, latest_event_cursor: 3 }));
  assert.equal(status.event_cursor, 1); assert.deepEqual(status.activity, first.activity); assert.equal(status.latest_event_cursor, 3);
  const second = mergeRunEvents(status, { run_id: uuid(4), binding: context().binding, after_cursor: 1, next_cursor: 3, latest_event_cursor: 3, has_more: false, events: [2, 3].map(cursor => ({ cursor, run_id: uuid(4), elapsed_ms: cursor * 100, kind: "progress", summary: { en: "Checked inventory", ja: "一覧を確認" } })) });
  assert.deepEqual(second.activity.map(item => item.cursor), [1, 2, 3]); assert.equal(second.active_elapsed_ms, 300);
  const changedScope = context(); changedScope.scope.sources.ctd.enabled = false;
  for (const changed of [run({ latest_event_cursor: 1 }), run({ question: "Changed" }), run({ context: { ...context(), binding: { ...context().binding, revision_id: uuid(99) } } }), run({ context: changedScope }), run({ context: { ...context(), attachments: [] } })]) assert.throws(() => mergeRunSnapshot(status, changed));
  const reordered = { ...status, context: Object.fromEntries(Object.entries(status.context).reverse()) as RunContext };
  assert.deepEqual(mergeRunSnapshot(status, reordered), status);
});

const pageMutations: [string, (value: any) => void][] = [
  ["gapped cursor", value => { value.events[0].cursor = 2; }], ["foreign event", value => { value.events[0].run_id = uuid(99); }],
  ["mismatched next cursor", value => { value.next_cursor = 2; }], ["inconsistent more flag", value => { value.has_more = false; }],
  ["unknown private field", value => { value.events[0].private_reasoning = "secret"; }], ["empty nonprogressing page", value => { value.events = []; value.next_cursor = 0; }],
  ["wrong initial cursor", value => { value.after_cursor = 1; }], ["wrong binding", value => { value.binding.conversation_id = uuid(99); }],
  ["unsafe cursor", value => { value.latest_event_cursor = 9007199254740992; }], ["oversized summary", value => { value.events[0].summary.ja = "海".repeat(2001); }],
  ["decreasing elapsed", value => { value.events.push({ ...value.events[0], cursor: 2, elapsed_ms: 0 }); value.events[0].elapsed_ms = 100; value.next_cursor = 2; value.has_more = false; }],
];
for (const [label, mutate] of pageMutations) test(`event page rejects ${label}`, async () => {
  const value = structuredClone(eventPage()); mutate(value);
  await assert.rejects(createResearchRunTransport({ fetcher: async () => json(value) }).events({ ...address(), after_cursor: 0 }), invalidResponse);
});

test("list pages preserve exact opaque 4096-character cursors and accept the schema's 500-item request bound", async () => {
  const opaque = ` opaque:${"x".repeat(4087)} `; assert.equal(opaque.length, 4096); let body: any;
  const client = createResearchRunTransport({ fetcher: async (_path, init) => { body = JSON.parse(String(init!.body)); return json({ version: RESEARCH_RUNS_VERSION, items: [run()], next_cursor: opaque }); } });
  assert.equal((await client.list({ investigation_id: uuid(1), conversation_id: uuid(2), limit: 500 })).next_cursor, opaque);
  assert.equal(body.limit, 500);
  const second = createResearchRunTransport({ fetcher: async (_path, init) => { assert.equal(JSON.parse(String(init!.body)).cursor, opaque); return json({ version: RESEARCH_RUNS_VERSION, items: [], next_cursor: null }); } });
  await second.list({ investigation_id: uuid(1), conversation_id: uuid(2), cursor: opaque });
});
for (const kind of ["duplicate", "foreign", "empty-more", "same-cursor", "too-many", "long-cursor"] as const) test(`list rejects ${kind} discovery`, async () => {
  const value: any = { version: RESEARCH_RUNS_VERSION, items: [run()], next_cursor: null };
  if (kind === "duplicate") value.items.push(run());
  if (kind === "foreign") value.items[0].context.binding.investigation_id = uuid(99);
  if (kind === "empty-more") { value.items = []; value.next_cursor = "next"; }
  if (kind === "same-cursor") value.next_cursor = "previous";
  if (kind === "too-many") value.items.push(run({ id: uuid(99) }));
  if (kind === "long-cursor") value.next_cursor = "x".repeat(4097);
  await assert.rejects(createResearchRunTransport({ fetcher: async () => json(value) }).list({ investigation_id: uuid(1), conversation_id: uuid(2), limit: kind === "too-many" ? 1 : 25, cursor: kind === "same-cursor" ? "previous" : null }), invalidResponse);
});

for (const [label, mutate] of [
  ["unknown authority", (value: any) => { value.role = "admin"; }], ["invalid key", (value: any) => { value.idempotency_key = "latest"; }],
  ["empty question", (value: any) => { value.question = " \n"; }], ["long question", (value: any) => { value.question = "🌊".repeat(8001); }],
  ["invalid unicode", (value: any) => { value.question = "\ud800"; }], ["control text", (value: any) => { value.question = "a\u0000b"; }],
  ["unknown scope", (value: any) => { value.context.scope.private = true; }], ["cycle", (value: any) => { value.question = value; }],
  ["accessor", (value: any) => { Object.defineProperty(value, "question", { get() { throw new Error("must never execute"); }, enumerable: true }); }],
  ["symbol", (value: any) => { value[Symbol("extra")] = true; }], ["unsafe number", (value: any) => { value.question = Number.MAX_SAFE_INTEGER + 1; }],
] as const) test(`invalid ${label} request never reaches HTTP`, async () => {
  let fetched = false; const input = submit(); mutate(input);
  await assert.rejects(createResearchRunTransport({ fetcher: async () => { fetched = true; return json(envelope()); } }).submit(input), invalidRequest); assert.equal(fetched, false);
});

test("production mutation keys, clarification token and paging bounds are mandatory before HTTP", async () => {
  let fetched = false; const client = createResearchRunTransport({ fetcher: async () => { fetched = true; return json(envelope()); } });
  for (const operation of [() => client.cancel(address()), () => client.clarify({ ...address(), idempotency_key: uuid(6), answer: "yes" }), () => client.events({ ...address(), after_cursor: -1 }), () => client.events({ ...address(), after_cursor: 0, limit: 501 }), () => client.list({ investigation_id: uuid(1), conversation_id: uuid(2), limit: 0 }), () => client.list({ investigation_id: uuid(1), conversation_id: uuid(2), cursor: "x".repeat(4097) })]) await assert.rejects(operation, invalidRequest);
  assert.equal(fetched, false);
});

for (const status of [401, 403, 404, 409, 422, 503]) test(`HTTP ${status} remains authoritative despite malformed and oversized error bodies`, async () => {
  const client = createResearchRunTransport({ maxResponseBytes: 1, fetcher: async () => new Response("private malformed server detail {", { status, headers: { "content-length": "999999999" } }) });
  await assert.rejects(client.status(address()), error => error instanceof ResearchRunClientError && error.status_code === status && !error.message.includes("private"));
});

for (const body of ['{"version":"research-runs-v1","version":"other"}', '{"version":"research-runs-v1","\\u0076ersion":"other"}', `{"x":${"[".repeat(129)}0${"]".repeat(129)}}`, '{"x":9007199254740992}', '{"x":1e999}', '{"x":"\\ud800"}', '{bad']) test("ambiguous or invalid JSON is rejected before typed presentation", async () => {
  await assert.rejects(createResearchRunTransport({ fetcher: async () => new Response(body) }).status(address()), invalidResponse);
});
test("response limits cover announced and actual streamed bytes and invalid UTF-8", async () => {
  for (const response of [new Response("{}", { headers: { "content-length": "100" } }), new Response(new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode(" ".repeat(33))); controller.close(); } })), new Response(new Uint8Array([0xc3, 0x28]))]) await assert.rejects(createResearchRunTransport({ maxResponseBytes: 32, fetcher: async () => response }).status(address()), invalidResponse);
  assert.equal(MAX_RUN_RESPONSE_BYTES, 16 * 1024 * 1024);
  for (const maximum of [0, -1, NaN, Infinity, MAX_RUN_RESPONSE_BYTES + 1]) assert.throws(() => createResearchRunTransport({ maxResponseBytes: maximum }), RangeError);
});

test("aborting before send or while token resolution waits makes no HTTP call", async () => {
  let fetched = false; const abort = new AbortController(); abort.abort();
  const client = createResearchRunTransport({ fetcher: async () => { fetched = true; return json(envelope()); } });
  await assert.rejects(client.status(address(), abort.signal), { name: "AbortError" });
  let started!: () => void; const tokenStarted = new Promise<void>(resolve => { started = resolve; }); const waiting = new AbortController();
  const tokenClient = createResearchRunTransport({ tokenProvider: () => { started(); return new Promise(() => undefined); }, fetcher: async () => { fetched = true; return json(envelope()); } });
  const pending = tokenClient.status(address(), waiting.signal); await tokenStarted; waiting.abort(); await assert.rejects(pending, { name: "AbortError" }); assert.equal(fetched, false);
});
test("late fetch replies and blocked stream reads are discarded after abort even if fetch ignores the signal", async () => {
  let release!: (value: Response) => void, started!: () => void; const fetchStarted = new Promise<void>(resolve => { started = resolve; }); let discarded = false;
  const client = createResearchRunTransport({ fetcher: async () => { started(); return new Promise(resolve => { release = resolve; }); } });
  const abort = new AbortController(); const pending = client.status(address(), abort.signal); await fetchStarted; abort.abort(); await assert.rejects(pending, { name: "AbortError" });
  release(new Response(new ReadableStream({ cancel() { discarded = true; } }))); await new Promise(resolve => setTimeout(resolve, 0)); assert.equal(discarded, true);
  let readStarted!: () => void; const reading = new Promise<void>(resolve => { readStarted = resolve; }); const streamAbort = new AbortController();
  const streamed = createResearchRunTransport({ fetcher: async () => new Response(new ReadableStream({ pull() { readStarted(); return new Promise(() => undefined); } })) }).status(address(), streamAbort.signal);
  await reading; streamAbort.abort(); await assert.rejects(streamed, { name: "AbortError" });
});
