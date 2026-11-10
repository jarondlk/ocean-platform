import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { ResearchHistoryScheduler } from "../src/research-history-scheduler.ts";
import * as history from "../src/research-answer-history.ts";
import * as state from "../src/research-answer-state.ts";
import * as service from "../src/research-evidence-service.ts";
import * as draft from "../src/research-state.ts";
import * as exports from "../src/exports.ts";
import * as f from "./research-evidence-fixtures.ts";

class Clock {
  now = 0; next = 0;
  timers = new Map<number, { at: number; callback: () => void }>();
  set = (callback: () => void, delay: number) => { const id = ++this.next; this.timers.set(id, { at: this.now + delay, callback }); return id; };
  clear = (id: unknown) => { this.timers.delete(id as number); };
  advance(milliseconds: number) {
    const end = this.now + milliseconds;
    while (true) {
      const due = [...this.timers].filter(([, value]) => value.at <= end).sort(([, a], [, b]) => a.at - b.at)[0];
      if (!due) break;
      this.now = due[1].at; this.timers.delete(due[0]); due[1].callback();
    }
    this.now = end;
  }
}

/** Drive the actual TSX hook's effects/state and real deadline schedulers without a DOM or extra test dependency. */
function harness() {
  const clock = new Clock(), polls: ResearchHistoryScheduler[] = [], slots: any[] = [];
  const effects = new Map<number, { deps: readonly unknown[]; cleanup?: () => void }>();
  let cursor = 0, dirty = true, output: any, historyStatus = 200, receiptStatus = 200;
  let holdHistory = false, holdReceipt = false, accessLost = 0;
  const pendingEffects: (() => void)[] = [], signals: { surface: string; signal?: AbortSignal }[] = [];
  const require = createRequire(import.meta.url);
  const hooks = {
    useState(initial: any) {
      const index = cursor++; if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
      return [slots[index], (value: any) => { const next = typeof value === "function" ? value(slots[index]) : value; if (!Object.is(next, slots[index])) { slots[index] = next; dirty = true; } }];
    },
    useRef(initial: any) { const index = cursor++; if (!(index in slots)) slots[index] = { current: initial }; return slots[index]; },
    useEffect(effect: () => void | (() => void), deps: readonly unknown[]) {
      const index = cursor++, previous = effects.get(index);
      if (previous && previous.deps.length === deps.length && deps.every((value, i) => Object.is(value, previous.deps[i]))) return;
      const entry = { deps: [...deps], cleanup: previous?.cleanup }; effects.set(index, entry);
      pendingEffects.push(() => { entry.cleanup?.(); entry.cleanup = effect() || undefined; });
    },
  };
  class TimedPoll extends ResearchHistoryScheduler {
    constructor(options: ConstructorParameters<typeof ResearchHistoryScheduler>[0]) { super({ ...options, setTimer: clock.set, clearTimer: clock.clear }); polls.push(this); }
  }
  const pending = () => new Promise<Response>(() => {});
  const fetcher = async (path: string, init?: RequestInit): Promise<Response> => {
    const body = JSON.parse(init!.body as string), surface = path.endsWith("evidence/open") || path.endsWith("evidence/page") ? "receipt" : "history";
    signals.push({ surface, signal: init?.signal as AbortSignal | undefined });
    const status = surface === "receipt" ? receiptStatus : historyStatus;
    if (status !== 200) return new Response(null, { status });
    if ((surface === "history" && holdHistory && path.endsWith("evidence/list")) || (surface === "receipt" && holdReceipt)) return pending();
    if (path.endsWith("answers/list")) return new Response(JSON.stringify(f.listing([f.job("completed")])));
    if (path.endsWith("answers/events")) return new Response(JSON.stringify(f.events(body.job_id, body.after_cursor, 0, body.after_cursor)));
    if (path.endsWith("evidence/list")) return new Response(JSON.stringify({ version: "research-evidence-v1", access_revision: f.evidencePolicy, run_id: f.run, input_version: 1, offset: 0, items: [f.receipt()], next_offset: null, total: 1 }));
    if (path.endsWith("evidence/open")) return new Response(JSON.stringify({ version: "research-evidence-v1", access_revision: f.evidencePolicy, receipt: f.receipt() }));
    if (path.endsWith("evidence/page")) return new Response(JSON.stringify(f.page()));
    throw new Error("Read tests must never dispatch a mutation");
  };
  const drafts = new draft.ResearchDraftStore(); drafts.bind({ accountId: "owner", permissionRevision: "current" });
  drafts.selectAnswer(f.inv, f.conv, { runId: f.run, jobId: f.jobId, receiptId: f.receiptAddress.receipt_id });
  const props: any = { locale: "en", accessKey: "owner:current", investigationId: f.inv, conversationId: f.conv, contextRevision: f.key, drafts, runs: [],
    answers: service.createAnswerClient({ fetcher }), evidence: service.createEvidenceClient({ fetcher }), submitEnabled: true, canExport: false, canAttach: false, externalBusy: false,
    onAttach: async () => false, onAccessLost() { accessLost++; }, onOpenEvidence() {} };
  const source = readFileSync(new URL("../src/research-answers.tsx", import.meta.url), "utf8"), module = { exports: {} as Record<string, any> };
  const dependencies: Record<string, unknown> = { react: hooks, "./research-history-scheduler": { ResearchHistoryScheduler: TimedPoll }, "./research-answer-history": history, "./research-answer-state": state,
    "./research-evidence-service": service, "./research-state": draft, "./exports": exports };
  new Function("require", "module", "exports", "setTimeout", "clearTimeout", "setInterval", "clearInterval", "window", "document",
    ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText)(
      (name: string) => name.endsWith(".css") ? {} : dependencies[name] ?? require(name), module, module.exports, clock.set, clock.clear, () => 0, () => {}, { addEventListener() {}, removeEventListener() {} }, { visibilityState: "visible" });
  async function flush() {
    for (let turn = 0; turn < 24; turn++) {
      if (dirty) { dirty = false; cursor = 0; output = module.exports.useResearchAnswers(props); for (const effect of pendingEffects.splice(0)) effect(); }
      await new Promise<void>(resolve => setImmediate(resolve));
    }
  }
  function click(node: any, label: string): boolean {
    if (Array.isArray(node)) return node.some(child => click(child, label));
    if (!node || typeof node !== "object") return false;
    if (node.type === "button" && node.props.children === label) { node.props.onClick(); return true; }
    return click(node.props?.children, label);
  }
  return { clock, polls, signals, flush,
    holdHistory(value: boolean) { holdHistory = value; }, holdReceipt(value: boolean) { holdReceipt = value; },
    historyStatus(value: number) { historyStatus = value; }, receiptStatus(value: number) { receiptStatus = value; },
    get accessLost() { return accessLost; },
    markup: () => ({ controls: renderToStaticMarkup(output.controls), evidence: renderToStaticMarkup(output.evidencePanel) }),
    changeScope(kind: "account/access" | "conversation" | "context revision") {
      if (kind === "account/access") props.accessKey = "different:current";
      else if (kind === "conversation") props.conversationId = f.key;
      else props.contextRevision = f.sha;
      dirty = true;
    },
    click(label: string) { assert.equal(click(output.controls, label), true, `Button ${label} must exist`); },
    dispose() { for (const effect of effects.values()) effect.cleanup?.(); },
  };
}

test("history's unchanged 15s timeout cannot erase a receipt freshly verified by its own poll", async () => {
  const h = harness(); h.holdHistory(true);
  try {
    await h.flush(); assert.equal(h.polls.length, 2); assert.match(h.markup().evidence, /Retained evidence page/);
    h.clock.advance(10000); h.polls[1].request(); await h.flush();
    h.clock.advance(4999); await h.flush(); assert.doesNotMatch(h.markup().controls, /could not be verified/);
    h.clock.advance(1); await h.flush();
    assert.match(h.markup().controls, /could not be verified/);
    assert.match(h.markup().evidence, /Retained evidence page/);
    assert.match(h.markup().evidence, /海洋 \/ literal/);
    assert.equal(h.signals.filter(value => value.surface === "receipt").at(-1)?.signal?.aborted, false);
    assert.equal(h.accessLost, 0);
  } finally { h.dispose(); }
});

test("receipt's unchanged 15s deadline clears its own private page without erasing freshly verified answers", async () => {
  const h = harness();
  try {
    await h.flush(); assert.match(h.markup().controls, /321 measurements/); assert.match(h.markup().evidence, /Retained evidence page/);
    h.holdReceipt(true); h.polls[1].request(); await h.flush();
    h.clock.advance(10000); h.polls[0].request(); await h.flush();
    h.clock.advance(5000); await h.flush();
    assert.doesNotMatch(h.markup().evidence, /Retained evidence page|海洋 \/ literal/);
    assert.match(h.markup().evidence, /Retained evidence is unavailable/);
    assert.match(h.markup().controls, /321 measurements/);
    assert.equal(h.accessLost, 0);
  } finally { h.dispose(); }
});

for (const surface of ["history", "receipt"] as const) test(`${surface} 503 clears only its own verified private values`, async () => {
  const h = harness();
  try {
    await h.flush(); assert.match(h.markup().controls, /321 measurements/); assert.match(h.markup().evidence, /Retained evidence page/);
    if (surface === "history") h.historyStatus(503); else h.receiptStatus(503);
    h.polls[surface === "history" ? 0 : 1].request(); await h.flush();
    if (surface === "history") {
      assert.doesNotMatch(h.markup().controls, /321 measurements/); assert.match(h.markup().controls, /could not be verified/);
      assert.match(h.markup().evidence, /Retained evidence page/);
    } else {
      assert.match(h.markup().controls, /321 measurements/); assert.doesNotMatch(h.markup().evidence, /Retained evidence page|海洋 \/ literal/);
      assert.match(h.markup().evidence, /Retained evidence is unavailable/);
    }
    assert.equal(h.accessLost, 0);
  } finally { h.dispose(); }
});

for (const surface of ["history", "receipt"] as const) for (const status of [401, 403, 409]) test(`${surface} ${status} still clears both surfaces and cancels their readers`, async () => {
  const h = harness();
  try {
    await h.flush(); assert.match(h.markup().controls, /321 measurements/); assert.match(h.markup().evidence, /Retained evidence page/);
    if (surface === "history") h.historyStatus(status); else h.receiptStatus(status);
    h.polls[surface === "history" ? 0 : 1].request(); await h.flush();
    assert.doesNotMatch(h.markup().controls, /321 measurements/);
    assert.doesNotMatch(h.markup().evidence, /Retained evidence page|海洋 \/ literal/);
    assert.equal(h.accessLost, status === 401 || status === 403 ? 1 : 0);
    assert.equal(h.signals.at(-1)?.signal?.aborted, true);
  } finally { h.dispose(); }
});

for (const kind of ["account/access", "conversation", "context revision"] as const) test(`a ${kind} transition still aborts both readers and removes their private values`, async () => {
  const h = harness();
  try {
    await h.flush(); assert.match(h.markup().controls, /321 measurements/); assert.match(h.markup().evidence, /Retained evidence page/);
    h.holdHistory(true); h.holdReceipt(true); h.polls[0].request(); h.polls[1].request(); await h.flush();
    const oldHistory = h.signals.filter(value => value.surface === "history").at(-1)?.signal;
    const oldReceipt = h.signals.filter(value => value.surface === "receipt").at(-1)?.signal;
    h.changeScope(kind); await h.flush();
    assert.doesNotMatch(h.markup().controls, /321 measurements/);
    assert.doesNotMatch(h.markup().evidence, /Retained evidence page|海洋 \/ literal/);
    assert.equal(oldHistory?.aborted, true); assert.equal(oldReceipt?.aborted, true);
  } finally { h.dispose(); }
});

test("an answer mutation 503 still clears both surfaces rather than applying read-only isolation", async () => {
  const h = harness();
  try {
    await h.flush(); assert.match(h.markup().controls, /321 measurements/); assert.match(h.markup().evidence, /Retained evidence page/);
    h.historyStatus(503); h.click("Prepare answer"); await h.flush();
    assert.doesNotMatch(h.markup().controls, /321 measurements/);
    assert.doesNotMatch(h.markup().evidence, /Retained evidence page|海洋 \/ literal/);
    assert.match(h.markup().controls, /Retry last answer action/);
    assert.match(h.markup().evidence, /Retained evidence is unavailable/);
  } finally { h.dispose(); }
});

test("explicit reload reauthorizes both surfaces after an isolated timeout", async () => {
  const h = harness(); h.holdHistory(true);
  try {
    await h.flush(); h.clock.advance(15000); await h.flush();
    assert.match(h.markup().controls, /could not be verified/); assert.match(h.markup().evidence, /Retained evidence page/);
    h.holdHistory(false); h.click("Reload answers and evidence"); await h.flush();
    assert.match(h.markup().controls, /321 measurements/); assert.doesNotMatch(h.markup().controls, /could not be verified/);
    assert.match(h.markup().evidence, /Retained evidence page/);
  } finally { h.dispose(); }
});
