import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
import { ResearchHistoryScheduler } from "../src/research-history-scheduler.ts";

class Clock {
  now = 0; next = 0;
  timers = new Map<number, { at: number; callback: () => void }>();
  set = (callback: () => void, delay: number): number => { const id = ++this.next; this.timers.set(id, { at: this.now + delay, callback }); return id; };
  clear = (id: unknown): void => { this.timers.delete(id as number); };
  advance(milliseconds: number): void {
    const end = this.now + milliseconds;
    while (true) {
      const due = [...this.timers].filter(([, item]) => item.at <= end).sort(([, left], [, right]) => left.at - right.at)[0];
      if (!due) break;
      this.now = due[1].at; this.timers.delete(due[0]); due[1].callback();
    }
    this.now = end;
  }
}
const settle = async () => { for (let index = 0; index < 8; index++) await Promise.resolve(); };
function harness() {
  const clock = new Clock(), jobs: { signal: AbortSignal; complete: () => void; reject: (error: unknown) => void }[] = [], failures: unknown[] = [];
  let timeouts = 0;
  const scheduler = new ResearchHistoryScheduler({ setTimer: clock.set, clearTimer: clock.clear, timeoutMs: 15000,
    run: signal => new Promise<void>((complete, reject) => { jobs.push({ signal, complete, reject }); }),
    onFailure: error => { failures.push(error); }, onTimeout: () => { timeouts++; },
  });
  return { scheduler, clock, jobs, failures, get timeouts() { return timeouts; } };
}

test("a slow valid history request survives repeated 2s polls and the 10s context refresh without deadline reset", async () => {
  const h = harness(); h.scheduler.request(); await settle();
  const originalTimer = [...h.clock.timers.values()][0]; assert.equal(originalTimer.at, 15000);
  for (let index = 0; index < 6; index++) { h.clock.advance(2000); h.scheduler.request(); if (h.clock.now === 10000) h.scheduler.request(); await settle(); }
  assert.equal(h.jobs.length, 1); assert.equal(h.jobs[0].signal.aborted, false); assert.equal(h.timeouts, 0);
  assert.equal([...h.clock.timers.values()][0], originalTimer);
  h.jobs[0].complete(); await settle();
  assert.equal(h.jobs.length, 2); assert.equal(h.jobs[0].signal.aborted, false);
  assert.equal([...h.clock.timers.values()][0].at, 27000);
  h.jobs[1].complete(); await settle(); assert.equal(h.clock.timers.size, 0); h.scheduler.dispose();
});
test("poll requests coalesce and do not start another history read while a mutation is running", async () => {
  const h = harness(); h.scheduler.request(); await settle();
  h.scheduler.pause(); assert.equal(h.jobs[0].signal.aborted, true);
  for (let index = 0; index < 10; index++) h.scheduler.request();
  h.jobs[0].complete(); await settle(); assert.equal(h.jobs.length, 1); assert.equal(h.clock.timers.size, 0);
  h.scheduler.resume(); await settle(); assert.equal(h.jobs.length, 2);
  h.jobs[1].complete(); await settle(); assert.equal(h.jobs.length, 2); h.scheduler.dispose();
});
test("a scheduler created during a mutation waits for its release before fetching", async () => {
  const h = harness(); h.scheduler.pause(); h.scheduler.request(); h.scheduler.request(); await settle();
  assert.equal(h.jobs.length, 0); assert.equal(h.clock.timers.size, 0);
  h.scheduler.resume(); await settle(); assert.equal(h.jobs.length, 1); h.scheduler.dispose(); h.jobs[0].complete(); await settle();
});
test("one original deadline aborts an overlong read despite every refresh and reports timeout exactly once", async () => {
  const h = harness(); h.scheduler.request(); await settle();
  for (let index = 0; index < 7; index++) { h.clock.advance(2000); h.scheduler.request(); await settle(); }
  h.clock.advance(999); assert.equal(h.timeouts, 0); assert.equal(h.jobs[0].signal.aborted, false);
  h.clock.advance(1); assert.equal(h.timeouts, 1); assert.equal(h.jobs[0].signal.aborted, true);
  h.clock.advance(20000); assert.equal(h.timeouts, 1);
  h.jobs[0].reject(new DOMException("aborted", "AbortError")); await settle(); assert.equal(h.failures.length, 0);
  assert.equal(h.jobs.length, 2); h.scheduler.dispose(); h.jobs[1].complete(); await settle();
});
test("navigation or access disposal aborts immediately and late completion cannot start a queued refresh", async () => {
  const h = harness(); h.scheduler.request(); await settle(); h.scheduler.request(); h.scheduler.dispose();
  assert.equal(h.jobs[0].signal.aborted, true); assert.equal(h.clock.timers.size, 0);
  h.jobs[0].reject(new Error("late failure from previous owner")); await settle(); h.scheduler.resume(); h.scheduler.request(); h.clock.advance(20000); await settle();
  assert.equal(h.jobs.length, 1); assert.equal(h.failures.length, 0); assert.equal(h.timeouts, 0);
});
test("an ordinary failed read settles and permits a later refresh without leaking unhandled rejection", async () => {
  const h = harness(); h.scheduler.request(); await settle(); const error = new Error("unavailable"); h.jobs[0].reject(error); await settle();
  assert.deepEqual(h.failures, [error]); assert.equal(h.clock.timers.size, 0);
  h.scheduler.request(); await settle(); assert.equal(h.jobs.length, 2); h.jobs[1].complete(); await settle(); h.scheduler.dispose();
});
test("the actual React workspace wires polling to the coordinator and excludes periodic state from its lifecycle", () => {
  const path = new URL("../src/research-workspace.tsx", import.meta.url), content = readFileSync(path, "utf8");
  const source = ts.createSourceFile(path.pathname, content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const effects: ts.CallExpression[] = [], functions: ts.ArrowFunction[] = [];
  const walk = (node: ts.Node): void => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "useEffect") effects.push(node);
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && ["mutate", "runAction"].includes(node.name.text) && node.initializer && ts.isArrowFunction(node.initializer)) functions.push(node.initializer);
    ts.forEachChild(node, walk);
  };
  walk(source);
  const history = effects.find(effect => effect.arguments[0]?.getText(source).includes("new ResearchHistoryScheduler")); assert.ok(history);
  const dependencies = history.arguments[1]; assert.ok(ts.isArrayLiteralExpression(dependencies));
  assert.equal(dependencies.elements.some(item => ["tick", "historyTick", "runs", "busy"].includes(item.getText(source))), false);
  const callback = history.arguments[0].getText(source);
  assert.match(callback, /if \(operation\.current !== null\) scheduler\.pause\(\)/); assert.match(callback, /scheduler\.request\(\)/); assert.match(callback, /scheduler\.dispose\(\)/);
  assert.match(callback, /if \(signal\.aborted \|\| !current\(\) \|\| historyEpoch\.current !== epoch\) return/);
  assert.match(content, /historyScheduler\.current\?\.request\(\); \}, 2000\)/);
  for (const mutation of functions) { const body = mutation.body.getText(source); assert.match(body, /historyScheduler\.current\?\.pause\(\)/); assert.match(body, /historyScheduler\.current\?\.resume\(\)/); }
  assert.equal(functions.length, 2); assert.doesNotMatch(content, /setHistoryTick|historyAbort/);
});
