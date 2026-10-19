import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
import { defaultCatalogueScope } from "../src/catalogue-service.ts";
import { loadResearchRunHistory, type RunHistoryRequest } from "../src/research-history.ts";
import { ResearchHistoryScheduler } from "../src/research-history-scheduler.ts";
import { createResearchRunTransport, RESEARCH_RUNS_VERSION } from "../src/research-run-service.ts";
import { isRunActive, ResearchRunContractError, type ResearchRun, type ResearchRunTransport, type RunContextBinding, type RunEventPage } from "../src/research-run-contract.ts";
import { MAX_RETAINED_RUNS_PER_CONVERSATION, ResearchDraftStore, ResearchStateError } from "../src/research-state.ts";

const uuid = (number: number) => `00000000-0000-0000-0000-${String(number).padStart(12, "0")}`;
const address = { investigation_id: uuid(1), conversation_id: uuid(2) };
const identity = { accountId: "account:one", permissionRevision: "policy:one" };
const binding = (): RunContextBinding => ({ ...address, revision_id: uuid(3), snapshot_id: "a".repeat(64), payload_sha256: "b".repeat(64) });
const run = (id: number, overrides: Partial<ResearchRun> = {}): ResearchRun => ({ id: uuid(id), context: { binding: binding(), scope: defaultCatalogueScope(), attachments: [], pins: [] }, question: `Inventory question ${id}`, status: "completed", active_elapsed_ms: 0, event_cursor: 0, latest_event_cursor: 0, activity: [], continuation_of: null, clarification: null, clarification_id: null, result: null, error: null, synthetic: false, ...overrides });
const explicit = (value: ResearchRun) => ({ id: value.id, binding: value.context.binding });
const settle = async () => { await new Promise<void>(resolve => setImmediate(resolve)); };
function options(transport: ResearchRunTransport, overrides: Partial<RunHistoryRequest> = {}): RunHistoryRequest {
  return { transport, address, pages: 1, cached: [], retained: [], signal: new AbortController().signal, isCurrent: () => true, ...overrides };
}
function transport(overrides: Partial<ResearchRunTransport> = {}): ResearchRunTransport {
  return { list: async () => ({ items: [], next_cursor: null }), status: async () => { throw new Error("Unexpected status call"); }, events: async () => { throw new Error("Unexpected events call"); }, ...overrides } as unknown as ResearchRunTransport;
}

test("more than25 actual HTTP history records keep an acknowledged off-page queued run active through repeated scheduler polls", async () => {
  const records = Array.from({ length: 30 }, (_, index) => run(100 + index));
  let accepted = run(999, { status: "queued", latest_event_cursor: 1 }); records.push(accepted);
  const calls: { method: string; body: any }[] = [];
  const client = createResearchRunTransport({ fetcher: async (path, init) => {
    const method = path.split("/").at(-1)!, body = JSON.parse(String(init!.body)); calls.push({ method, body });
    let response: unknown;
    if (method === "list") {
      const start = body.cursor === null ? 0 : Number(body.cursor), items = records.slice(start, start + body.limit);
      response = { version: RESEARCH_RUNS_VERSION, items, next_cursor: start + items.length < records.length ? String(start + items.length) : null };
    } else if (method === "status") response = { version: RESEARCH_RUNS_VERSION, run: accepted };
    else if (method === "events") {
      const latest = accepted.latest_event_cursor!;
      response = { version: RESEARCH_RUNS_VERSION, run_id: accepted.id, binding: accepted.context.binding, after_cursor: body.after_cursor, next_cursor: latest, latest_event_cursor: latest, has_more: false,
        events: Array.from({ length: latest - body.after_cursor }, (_, index) => { const cursor = body.after_cursor + index + 1; return { cursor, run_id: accepted.id, elapsed_ms: 0, kind: cursor === 1 ? "accepted" : "progress", summary: { en: "Inventory checked", ja: "一覧を確認" } }; }) };
    } else throw new Error("Unexpected HTTP action");
    return new Response(JSON.stringify(response));
  } });
  const store = new ResearchDraftStore(); store.bind(identity); store.retainRun(accepted.id, accepted.context.binding);
  let cached: ResearchRun[] = [accepted, run(888, { status: "running" })], published = 0, failure: unknown;
  const scheduler = new ResearchHistoryScheduler({ run: async signal => {
    const page = await loadResearchRunHistory(options(client, { cached, retained: store.retainedRunBindings(address.investigation_id, address.conversation_id), signal }));
    cached = page.runs; published++;
  }, onFailure: error => { failure = error; }, onTimeout: () => { failure = new Error("Unexpected timeout"); } });
  scheduler.request(); for (let index = 0; published < 1 && index < 20; index++) await settle();
  assert.equal(failure, undefined); assert.equal(published, 1); assert.equal(cached.length, 26);
  assert.equal(cached.some(value => value.id === uuid(888)), false); assert.equal(isRunActive(cached.find(value => value.id === accepted.id)!.status), true);
  assert.equal(cached.find(value => value.id === accepted.id)!.event_cursor, 1);
  accepted = run(999, { status: "running", latest_event_cursor: 2 }); records[30] = accepted;
  scheduler.request(); for (let index = 0; published < 2 && index < 20; index++) await settle();
  assert.equal(failure, undefined); assert.equal(published, 2); assert.equal(isRunActive(cached.find(value => value.id === accepted.id)!.status), true);
  assert.deepEqual(cached.find(value => value.id === accepted.id)!.activity.map(value => value.cursor), [1, 2]);
  assert.equal(calls.filter(value => value.method === "status").length, 2);
  assert.deepEqual(calls.filter(value => value.method === "events").map(value => value.body.after_cursor), [0, 1]);
  const statusCount = calls.filter(value => value.method === "status").length;
  const more = await loadResearchRunHistory(options(client, { pages: 2, cached, retained: [explicit(accepted)] }));
  assert.equal(more.runs.length, 31); assert.equal(new Set(more.runs.map(value => value.id)).size, 31); assert.equal(more.next_cursor, null);
  assert.equal(calls.filter(value => value.method === "status").length, statusCount); scheduler.dispose();
});

test("cached activity without an explicit acknowledgement cannot retain or authorize itself", async () => {
  let statuses = 0; const client = transport({ list: async () => ({ items: [run(10)], next_cursor: "next" }), status: async () => { statuses++; return run(999, { status: "running" }); } });
  const page = await loadResearchRunHistory(options(client, { cached: [run(999, { status: "running" })] }));
  assert.deepEqual(page.runs.map(value => value.id), [uuid(10)]); assert.equal(statuses, 0);
});
for (const status_code of [401, 403, 503]) test(`off-page status${status_code} cannot publish a list-only replacement or stale cached run`, async () => {
  const accepted = run(999, { status: "running" }); let published: ResearchRun[] | null = null;
  const client = transport({ list: async () => ({ items: [run(10)], next_cursor: null }), status: async () => { throw { status_code }; } });
  await assert.rejects(async () => { published = (await loadResearchRunHistory(options(client, { cached: [accepted], retained: [explicit(accepted)] }))).runs; }, error => (error as { status_code: number }).status_code === status_code);
  assert.equal(published, null);
});
test("404 omission is returned without mutating retention before the guarded workspace publication", async () => {
  const accepted = run(999); const store = new ResearchDraftStore(); store.bind(identity); store.retainRun(accepted.id, accepted.context.binding);
  const page = await loadResearchRunHistory(options(transport({ status: async () => { throw { status_code: 404 }; } }), { cached: [accepted], retained: store.retainedRunBindings(address.investigation_id, address.conversation_id) }));
  assert.deepEqual(page.runs, []); assert.deepEqual(page.unavailable_ids, [accepted.id]); assert.equal(store.retainedRunBindings(address.investigation_id, address.conversation_id).length, 1);
  for (const id of page.unavailable_ids) store.forgetRetainedRun(address.investigation_id, address.conversation_id, id);
  assert.deepEqual(store.retainedRunBindings(address.investigation_id, address.conversation_id), []);
});
for (const field of ["investigation_id", "conversation_id", "revision_id", "snapshot_id", "payload_sha256"] as const) test(`off-page status cannot change retained ${field}`, async () => {
  const accepted = run(999), changed = { ...accepted, context: { ...accepted.context, binding: { ...accepted.context.binding, [field]: field.endsWith("sha256") || field === "snapshot_id" ? "c".repeat(64) : uuid(44) } } };
  await assert.rejects(loadResearchRunHistory(options(transport({ status: async () => changed }), { retained: [explicit(accepted)], cached: [accepted] })), ResearchRunContractError);
});
test("off-page status cannot substitute its run ID, scope or references under the same retained binding", async () => {
  const accepted = run(999), scopeChanged = structuredClone(accepted); scopeChanged.context.scope.sources.ctd.enabled = false;
  const referencesChanged = { ...accepted, context: { ...accepted.context, attachments: [{ kind: "artifact" as const, id: "artifact:substituted", snapshot_id: "c".repeat(64) }] } };
  for (const changed of [{ ...accepted, id: uuid(998) }, scopeChanged, referencesChanged]) await assert.rejects(loadResearchRunHistory(options(transport({ status: async () => changed }), { retained: [explicit(accepted)], cached: [accepted] })), ResearchRunContractError);
});
test("a listed retained run must match its binding too; status backfill cannot bypass this check", async () => {
  const accepted = run(999), changed = { ...accepted, context: { ...accepted.context, binding: { ...binding(), revision_id: uuid(99) } } };
  await assert.rejects(loadResearchRunHistory(options(transport({ list: async () => ({ items: [changed], next_cursor: null }) }), { retained: [explicit(accepted)] })), ResearchRunContractError);
});
test("off-page event high water and immutable history cannot regress or substitute the submitted context", async () => {
  const accepted = run(999, { latest_event_cursor: 2 });
  await assert.rejects(loadResearchRunHistory(options(transport({ status: async () => run(999, { latest_event_cursor: 1 }) }), { retained: [explicit(accepted)], cached: [accepted] })), ResearchRunContractError);
  const page: RunEventPage = { run_id: accepted.id, binding: { ...binding(), revision_id: uuid(99) }, after_cursor: 0, next_cursor: 0, latest_event_cursor: 2, has_more: true, events: [] };
  await assert.rejects(loadResearchRunHistory(options(transport({ status: async () => accepted, events: async () => page }), { retained: [explicit(accepted)] })), ResearchRunContractError);
});
for (const change of ["account", "permission", "navigation", "mutation", "abort"] as const) test(`${change} change during late status hydration cannot publish or request subsequent events`, async () => {
  const accepted = run(999, { status: "running", latest_event_cursor: 1 }), store = new ResearchDraftStore(); store.bind(identity); store.retainRun(accepted.id, accepted.context.binding);
  let release!: (value: ResearchRun) => void, started!: () => void, current = true, eventCalls = 0;
  const began = new Promise<void>(resolve => { started = resolve; }), abort = new AbortController();
  const client = transport({ status: async () => { started(); return new Promise(resolve => { release = resolve; }); }, events: async () => { eventCalls++; throw new Error("Must not run after stale hydration"); } });
  const pending = loadResearchRunHistory(options(client, { retained: store.retainedRunBindings(address.investigation_id, address.conversation_id), signal: abort.signal, isCurrent: () => current }));
  await began;
  if (change === "abort") abort.abort(); else current = false;
  if (change === "account") store.bind({ ...identity, accountId: "account:two" });
  if (change === "permission") store.bind({ ...identity, permissionRevision: "policy:two" });
  release(accepted); await assert.rejects(pending, { name: "AbortError" }); assert.equal(eventCalls, 0);
  if (change === "account" || change === "permission") assert.deepEqual(store.retainedRunBindings(address.investigation_id, address.conversation_id), []);
});
test("navigation during list discovery aborts before any explicit off-page request", async () => {
  let release!: () => void, started!: () => void, current = true, statuses = 0; const began = new Promise<void>(resolve => { started = resolve; });
  const client = transport({ list: async () => { started(); await new Promise<void>(resolve => { release = resolve; }); return { items: [], next_cursor: null }; }, status: async () => { statuses++; return run(999); } });
  const pending = loadResearchRunHistory(options(client, { retained: [explicit(run(999))], isCurrent: () => current })); await began; current = false; release();
  await assert.rejects(pending, { name: "AbortError" }); assert.equal(statuses, 0);
});
test("retention bounds always keep newest acknowledgements, refresh explicit actions and clear on denied identity", () => {
  const store = new ResearchDraftStore(); assert.throws(() => store.retainRun(uuid(10), binding()), ResearchStateError); store.bind(identity);
  for (let index = 0; index < 30; index++) store.retainRun(uuid(100 + index), binding());
  let values = store.retainedRunBindings(address.investigation_id, address.conversation_id);
  assert.equal(values.length, MAX_RETAINED_RUNS_PER_CONVERSATION); assert.equal(values[0].id, uuid(105)); assert.equal(values.at(-1)!.id, uuid(129));
  store.retainRun(uuid(105), binding()); store.retainRun(uuid(130), binding()); values = store.retainedRunBindings(address.investigation_id, address.conversation_id);
  assert.equal(values.some(value => value.id === uuid(106)), false); assert.equal(values.some(value => value.id === uuid(105)), true); assert.equal(values.at(-1)!.id, uuid(130));
  assert.equal(Object.isFrozen(values), true); assert.equal(Object.isFrozen(values[0].binding), true);
  store.bind({ ...identity }); assert.equal(store.retainedRunBindings(address.investigation_id, address.conversation_id).length, 25);
  store.bind(null); assert.throws(() => store.retainedRunBindings(address.investigation_id, address.conversation_id), ResearchStateError);
  store.bind(identity); assert.deepEqual(store.retainedRunBindings(address.investigation_id, address.conversation_id), []);
});
test("retained identities are detached, conversation scoped, immutable and bounded across conversations", () => {
  const store = new ResearchDraftStore(); store.bind(identity); const original = { ...binding() }; store.retainRun(uuid(100), original); original.revision_id = uuid(99);
  assert.equal(store.retainedRunBindings(address.investigation_id, address.conversation_id)[0].binding.revision_id, uuid(3));
  assert.throws(() => store.retainRun(uuid(100), original), ResearchStateError);
  for (let index = 0; index < 128; index++) store.retainRun(uuid(200 + index), { ...binding(), conversation_id: uuid(2000 + index) });
  assert.deepEqual(store.retainedRunBindings(address.investigation_id, address.conversation_id), []);
  assert.equal(store.retainedRunBindings(address.investigation_id, uuid(2127))[0].id, uuid(327));
});
test("forged or oversized retained metadata fails before any transport call", async () => {
  let calls = 0; const client = transport({ list: async () => { calls++; return { items: [], next_cursor: null }; } });
  for (const retained of [Array.from({ length: 26 }, (_, index) => explicit(run(100 + index))), [explicit(run(10)), explicit(run(10))], [{ id: uuid(10), binding: { ...binding(), conversation_id: uuid(99) } }], [{ id: "latest", binding: binding() }]]) await assert.rejects(loadResearchRunHistory(options(client, { retained })), ResearchRunContractError);
  assert.equal(calls, 0);
});
test("actual workspace acknowledges after response guards and publishes only complete current hydration", () => {
  const content = readFileSync(new URL("../src/research-workspace.tsx", import.meta.url), "utf8"), source = ts.createSourceFile("research-workspace.tsx", content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const bodies = new Map<string, string>();
  const walk = (node: ts.Node): void => { if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer && ts.isArrowFunction(node.initializer)) bodies.set(node.name.text, node.initializer.body.getText(source)); ts.forEachChild(node, walk); }; walk(source);
  const action = bodies.get("runAction")!, save = bodies.get("saveRun")!;
  assert.ok(action.indexOf("guard.current !== mine") < action.indexOf("saveRun(run)")); assert.ok(action.indexOf("Run binding mismatch") < action.indexOf("saveRun(run)"));
  assert.ok(save.indexOf("session.drafts.retainRun") < save.indexOf("session.runs.set"));
  assert.match(save, /if \(runSource === "service"\) session\.drafts\.retainRun/);
  assert.match(content, /retained: session\.drafts\.retainedRunBindings/);
  assert.match(content, /isCurrent: \(\) => current\(\) && historyEpoch\.current === epoch/);
  const check = content.indexOf("if (signal.aborted || !current() || historyEpoch.current !== epoch) return;");
  assert.ok(check < content.indexOf("session.drafts.forgetRetainedRun")); assert.ok(check < content.indexOf("session.runs.set(slot, page.runs)"));
  assert.match(content, /session\.drafts\.clear\(\); session\.runs\.clear\(\)/);
  assert.match(content, /runs\.some\(run => isRunActive\(run\.status\)\)/);
  assert.match(content, /onFailure: error => \{ if \(current\(\)\) \{ setRuns\(\[\]\); setHistoryVerified\(false\); fail\(error\)/);
});
