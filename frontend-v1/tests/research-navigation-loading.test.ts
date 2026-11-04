import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const source = ts.createSourceFile("research-workspace.tsx", readFileSync(
  new URL("../src/research-workspace.tsx", import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const effects = new Map<string, string>();
function find(node: ts.Node) {
  if (ts.isCallExpression(node) && node.expression.getText(source) === "useEffect" && node.arguments.length === 2) {
    const dependencies = node.arguments[1].getText(source);
    for (const tick of ["listTick", "snapshotTick"]) if (new RegExp(`\\b${tick}\\b`).test(dependencies)) {
      effects.set(tick, ts.transpileModule(`(${node.arguments[0].getText(source)})`, {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None },
      }).outputText);
    }
  }
  ts.forEachChild(node, find);
}
find(source);
assert.equal(effects.size, 2);

function harness() {
  const state = { investigations: [] as object[], snapshots: [] as object[], discoveryCalls: 0, status: "", error: null as number | null };
  let resolve!: (value: object) => void;
  const discovery = new Promise<object>(yes => { resolve = yes; });
  const timers = new Map<object, () => void>();
  const scope = {
    client: {}, investigationPages: 1,
    loadInvestigationPages: async () => ({ items: [{ id: "saved-investigation" }], next_after_id: null }),
    catalogue: { snapshots: () => { state.discoveryCalls++; return discovery; } },
    defaultCatalogueScope: () => ({}),
    setInvestigations: (items: object[]) => { state.investigations = items; },
    setSnapshots: (items: object[]) => { state.snapshots = items; },
    setCatalogueStatus: (value: string) => { state.status = value; },
    setError: (value: number) => { state.error = value; },
    setNextInvestigation: () => {}, setNewSnapshot: () => {}, setRefreshSnapshot: () => {}, fail: () => {},
    AbortController,
    setTimeout: (callback: () => void) => { const key = {}; timers.set(key, callback); return key; },
    clearTimeout: (key: object) => { timers.delete(key); },
  };
  return { state, timers, resolve,
    list: runInNewContext(effects.get("listTick")!, scope) as () => () => void,
    snapshots: runInNewContext(effects.get("snapshotTick")!, scope) as () => () => void };
}
const settle = () => new Promise<void>(resolve => setImmediate(resolve));

test("slow discovery cannot block saved investigations or repeat on list polling", async () => {
  const h = harness(); const cleanDiscovery = h.snapshots(); const cleanList = h.list();
  await settle();
  assert.equal(h.state.investigations.length, 1);
  assert.equal(h.state.discoveryCalls, 1);
  const cleanPoll = h.list(); await settle();
  assert.equal(h.state.discoveryCalls, 1);
  for (const timeout of [...h.timers.values()]) timeout();
  assert.equal(h.state.investigations.length, 1);
  assert.equal(h.state.status, "error");
  h.resolve({ snapshots: [{ snapshot_id: "late" }] }); await settle();
  assert.equal(h.state.snapshots.length, 0);
  cleanDiscovery(); cleanList(); cleanPoll();
});

test("cleanup prevents a late discovery from repopulating an old access context", async () => {
  const h = harness(); const cleanup = h.snapshots(); cleanup();
  h.resolve({ snapshots: [{ snapshot_id: "old-context" }] }); await settle();
  assert.equal(h.state.snapshots.length, 0);
});
