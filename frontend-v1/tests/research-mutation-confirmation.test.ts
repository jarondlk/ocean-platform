import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const source = ts.createSourceFile("research-workspace.tsx",
  readFileSync(new URL("../src/research-workspace.tsx", import.meta.url), "utf8"),
  ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let mutation: ts.ArrowFunction | undefined;
function findMutation(node: ts.Node): void {
  if (ts.isVariableDeclaration(node) && node.name.getText(source) === "mutate"
      && node.initializer && ts.isArrowFunction(node.initializer)) mutation = node.initializer;
  ts.forEachChild(node, findMutation);
}
findMutation(source);
assert.ok(mutation);
const executable = ts.transpileModule(`const mutate = ${mutation.getText(source)}; mutate;`, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None },
}).outputText;

function harness() {
  let resolve!: (value: object) => void;
  let reject!: (error: object) => void;
  const response = new Promise<object>((yes, no) => { resolve = yes; reject = no; });
  const state = { pending: null as object | null, forgotten: 0, followupReads: 0,
    active: {} as object | null, checking: false, refreshes: 0, notice: "" };
  const guard = { current: "current-owner" };
  const ignore = () => {};
  const timers = new Map<object, { callback: () => void; milliseconds: number }>();
  const scope = {
    operation: { current: null }, guard, locationRef: { current: { investigationId: "investigation" } },
    mounted: { current: true }, mutationAbort: { current: null }, historyEpoch: { current: 0 },
    historyScheduler: { current: { pause: ignore, resume: ignore } },
    session: { drafts: {
      pendingMutation: () => state.pending,
      rememberMutation: (_slot: string, value: object) => { state.pending = value; },
      forgetMutation: () => { state.forgotten++; state.pending = null; },
    } },
    executeInvestigationMutation: () => response,
    client: { get: async () => { state.followupReads++; throw new Error("Unexpected extra read in save confirmation"); } },
    setPending: (value: object | null) => { state.pending = value; },
    setActive: (value: object | null) => { state.active = value; },
    setChecking: (value: boolean) => { state.checking = value; },
    setTick: () => { state.refreshes++; },
    setNotice: (value: string) => { state.notice = value; },
    setBusy: ignore, setError: ignore, setConflict: ignore, setListTick: ignore,
    setConversationName: ignore, navigate: ignore, fail: ignore,
    say: (_locale: string, english: string) => english, locale: "en",
    code: (error: { status_code?: number }) => error.status_code ?? 503,
    AbortController,
    setTimeout: (callback: () => void, milliseconds: number) => {
      const timer = {};
      timers.set(timer, { callback, milliseconds });
      return timer;
    },
    clearTimeout: (timer: object) => { timers.delete(timer); },
  };
  return { state, guard, timers, resolve, reject,
    mutate: runInNewContext(executable, scope) as (intent: object) => Promise<boolean> };
}

const intent = { method: "changeContext", request: { idempotency_key: "original-key" } };
const committed = { investigation: { id: "investigation" }, context: { id: "new-revision" },
  operation: { state: "committed" } };

test("a confirmed save clears retry uncertainty and revalidates separately", async () => {
  const h = harness();
  const result = h.mutate(intent);
  assert.equal(h.state.pending, intent);
  assert.equal([...h.timers.values()][0].milliseconds, 15_000);
  h.resolve(committed);
  assert.equal(await result, true);
  assert.equal(h.state.followupReads, 0);
  assert.equal(h.state.forgotten, 1);
  assert.equal(h.state.pending, null);
  assert.equal(h.state.active, null);
  assert.equal(h.state.checking, true);
  assert.equal(h.state.refreshes, 1);
  assert.match(h.state.notice, /Saved/);
  assert.equal(h.timers.size, 0);
});

test("a late reply after an access transition cannot publish a confirmation", async () => {
  const h = harness();
  const result = h.mutate(intent);
  h.guard.current = "different-owner";
  h.resolve(committed);
  assert.equal(await result, false);
  assert.equal(h.state.forgotten, 0);
  assert.equal(h.state.refreshes, 0);
  assert.equal(h.state.notice, "");
});

test("an uncertain save retains its exact intent for an idempotent retry", async () => {
  const h = harness();
  const result = h.mutate(intent);
  h.reject({ status_code: 503 });
  assert.equal(await result, false);
  assert.equal(h.state.pending, intent);
  assert.equal(h.state.forgotten, 0);
  assert.equal(h.state.refreshes, 0);
  assert.equal(h.timers.size, 0);
});
