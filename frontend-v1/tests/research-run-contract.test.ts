import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React, { type ComponentType, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import * as contract from "../src/research-run-contract.ts";
import { defaultCatalogueScope } from "../src/catalogue-service.ts";
import { createC18RunFixture } from "../development/c18/run-fixture.ts";
import type { ResearchActivityProps } from "../src/research-activity";

const uuid = (n: number) => `00000000-0000-0000-0000-${n.toString().padStart(12, "0")}`;
const snapshot = "a".repeat(64), hash = "b".repeat(64);
function context(): contract.RunContext {
  return { binding: { investigation_id: uuid(1), conversation_id: uuid(2), revision_id: uuid(3), snapshot_id: snapshot, payload_sha256: hash },
    scope: defaultCatalogueScope(), attachments: [{ kind: "catalogue", id: "dataset:synthetic", snapshot_id: snapshot }], pins: [] };
}
const request = (key = 10) => ({ context: context(), question: "Compare synthetic interface states 🌊", idempotency_key: uuid(key) });
const address = contract.researchRunAddress;

test("submit snapshots and deeply freezes context without freezing or aliasing the caller", async () => {
  const fixture = createC18RunFixture({ now: () => 0 }); const input = request(); const before = structuredClone(input);
  const run = await fixture.submit(input);
  assert.deepEqual(input, before); assert.notEqual(run.context, input.context); assert.equal(Object.isFrozen(input.context), false);
  assert.equal(Object.isFrozen(run.context.scope.sources.ctd), true); assert.equal(Object.isFrozen(run.context.attachments[0]), true);
  input.context.scope.sources.ctd.enabled = false;
  (input.context.binding as { revision_id: string }).revision_id = uuid(99);
  assert.equal(run.context.scope.sources.ctd.enabled, true); assert.equal(run.context.binding.revision_id, uuid(3));
  assert.equal(run.synthetic, true); assert.equal(run.result, null);
});
test("a later context update affects new submissions while active activity and continuation retain the old revision", async () => {
  const fixture = createC18RunFixture({ scenario: "running" }); const original = await fixture.submit(request());
  const changed = request(11); (changed.context.binding as { revision_id: string }).revision_id = uuid(9); changed.context.scope.sources.ctd.enabled = false;
  const later = await fixture.submit(changed);
  assert.equal(later.context.binding.revision_id, uuid(9)); assert.equal(original.context.binding.revision_id, uuid(3)); assert.equal(original.context.scope.sources.ctd.enabled, true);
  const cancelled = await fixture.cancel(address(original)); const next = await fixture.continue({ ...address(cancelled), idempotency_key: uuid(12) });
  assert.deepEqual(next.context, original.context); assert.equal(next.continuation_of, original.id);
});
test("all six operations are exposed with no implicit production transport", () => {
  const fixture = createC18RunFixture();
  assert.deepEqual(Object.keys(fixture).sort(), ["cancel", "clarify", "continue", "events", "setScenario", "status", "submit"]);
});
for (const scenario of ["completed", "partial", "failed"] as const) test(`deterministic ${scenario} outcome and public evidence qualifications`, async () => {
  let time = 1000; const fixture = createC18RunFixture({ scenario, now: () => time });
  const run = await fixture.submit(request()); time += 2000;
  const started = await fixture.status(address(run)); assert.equal(started.status, "running");
  time += 3000; const finished = await fixture.status(address(run)); assert.equal(finished.status, scenario); assert.equal(finished.active_elapsed_ms, 5000);
  assert.deepEqual(await fixture.status(address(run)), finished);
  if (scenario === "failed") { assert.equal(finished.result, null); assert.ok(finished.error?.en.includes("Synthetic")); }
  else {
    assert.equal(finished.result?.complete, scenario === "completed");
    const evidence = finished.result!.evidence[0]; assert.equal(evidence.synthetic, true); assert.equal(evidence.availability, "unavailable"); assert.equal(evidence.artifact_id, null); assert.equal(evidence.authority, "descriptive");
    assert.equal(evidence.snapshot_id, run.context.binding.snapshot_id); assert.equal(evidence.revision_id, run.context.binding.revision_id);
  }
  assert.equal(Object.isFrozen(finished.activity[0].summary), true);
});
test("clarification pauses active elapsed time and resumes the original binding", async () => {
  let time = 0; const fixture = createC18RunFixture({ scenario: "clarification", now: () => time });
  const run = await fixture.submit(request()); time = 1000; await fixture.status(address(run)); time = 2000;
  const waiting = await fixture.status(address(run)); assert.equal(waiting.status, "awaiting_clarification");
  time = 902000; assert.equal((await fixture.status(address(run))).active_elapsed_ms, 2000);
  const resumed = await fixture.clarify({ ...address(run), idempotency_key: uuid(11), answer: "Use the original comparison." });
  assert.equal(resumed.active_elapsed_ms, 2000); assert.equal(resumed.status, "running"); assert.deepEqual(resumed.context, run.context);
  time += 1000; const done = await fixture.status(address(run)); assert.equal(done.status, "completed"); assert.equal(done.active_elapsed_ms, 3000);
  assert.equal((await fixture.clarify({ ...address(run), idempotency_key: uuid(11), answer: "Use the original comparison." })).id, run.id);
});
for (const scenario of ["partial", "failed", "running", "clarification"] as const) test(`cancellation or continuation from ${scenario} retains the immutable source run`, async () => {
  const fixture = createC18RunFixture({ scenario, now: () => 1000 });
  const original = await fixture.submit(request()); await fixture.status(address(original)); let run = await fixture.status(address(original));
  if (["running", "awaiting_clarification"].includes(run.status)) {
    run = await fixture.cancel(address(run)); assert.equal(run.status, "cancelled"); assert.deepEqual(await fixture.cancel(address(run)), run);
  }
  fixture.setScenario("completed");
  const next = await fixture.continue({ ...address(run), idempotency_key: uuid(12) });
  assert.notEqual(next.id, run.id); assert.equal(next.continuation_of, run.id); assert.deepEqual(next.context, original.context); assert.equal(next.question, original.question);
  assert.deepEqual(await fixture.status(address(run)), run);
  assert.equal((await fixture.continue({ ...address(run), idempotency_key: uuid(12) })).id, next.id);
});
test("monotonic public event pages replay exactly, reject reordered/context-substituted pages", async () => {
  let time = 0; const fixture = createC18RunFixture({ now: () => time });
  const accepted = await fixture.submit(request()); time = 1000; await fixture.status(address(accepted)); time = 2000; await fixture.status(address(accepted));
  const page = await fixture.events({ ...address(accepted), after_cursor: accepted.event_cursor });
  const merged = contract.mergeRunEvents(accepted, page); assert.deepEqual(merged.activity.map((event) => event.cursor), [1, 2, 3]);
  const empty = await fixture.events({ ...address(accepted), after_cursor: page.next_cursor }); assert.deepEqual(empty.events, []);
  assert.equal(contract.mergeRunEvents(merged, empty).event_cursor, 3);
  for (const altered of [ { ...page, after_cursor: 0 }, { ...page, next_cursor: 999 }, { ...page, events: [...page.events].reverse() }, { ...page, binding: { ...page.binding, revision_id: uuid(9) } } ]) assert.throws(() => contract.mergeRunEvents(accepted, altered), contract.ResearchRunContractError);
  const privateEvent = { ...page, events: [{ ...page.events[0], private_reasoning: "forbidden field" }, page.events[1]] };
  assert.throws(() => contract.mergeRunEvents(accepted, privateEvent), contract.ResearchRunContractError);
});
for (const cursor of [-1, 0.5, Infinity, 999]) test(`event cursor ${cursor} fails closed`, async () => {
  const fixture = createC18RunFixture(); const run = await fixture.submit(request());
  await assert.rejects(() => fixture.events({ ...address(run), after_cursor: cursor }));
});
test("status, events, cancellation, clarification and continuation cannot cross conversations", async () => {
  const fixture = createC18RunFixture(); const run = await fixture.submit(request()); const wrong = { ...address(run), conversation_id: uuid(99) };
  for (const operation of [() => fixture.status(wrong), () => fixture.events({ ...wrong, after_cursor: 0 }), () => fixture.cancel(wrong), () => fixture.clarify({ ...wrong, answer: "yes", idempotency_key: uuid(11) }), () => fixture.continue({ ...wrong, idempotency_key: uuid(12) })]) await assert.rejects(operation);
});
test("operation replay reuses its result and rejects changed payload", async () => {
  const fixture = createC18RunFixture(); const input = request(); const first = await fixture.submit(input);
  assert.equal((await fixture.submit(structuredClone(input))).id, first.id);
  await assert.rejects(() => fixture.submit({ ...input, question: "Different input" }));
  await assert.rejects(() => fixture.continue({ ...address(first), idempotency_key: uuid(11) }));
  await assert.rejects(() => fixture.clarify({ ...address(first), idempotency_key: uuid(12), answer: "yes" }));
});
test("aborted operations make no state changes", async () => {
  const fixture = createC18RunFixture(); const controller = new AbortController(); controller.abort();
  await assert.rejects(() => fixture.submit(request(), controller.signal), { name: "AbortError" });
  const run = await fixture.submit(request()); assert.equal(run.id, "c18-synthetic-1");
  for (const operation of [() => fixture.status(address(run), controller.signal), () => fixture.events({ ...address(run), after_cursor: 0 }, controller.signal), () => fixture.cancel(address(run), controller.signal), () => fixture.clarify({ ...address(run), idempotency_key: uuid(11), answer: "yes" }, controller.signal), () => fixture.continue({ ...address(run), idempotency_key: uuid(12) }, controller.signal)]) await assert.rejects(operation, { name: "AbortError" });
  assert.equal((await fixture.events({ ...address(run), after_cursor: 0 })).next_cursor, 1);
});
test("elapsed time is monotonic despite a backwards injected clock", async () => {
  let time = 2000; const fixture = createC18RunFixture({ now: () => time, scenario: "running" }); const run = await fixture.submit(request());
  time = 3000; assert.equal((await fixture.status(address(run))).active_elapsed_ms, 1000);
  time = 0; assert.equal((await fixture.status(address(run))).active_elapsed_ms, 1000);
  time = 4000; assert.equal((await fixture.status(address(run))).active_elapsed_ms, 2000);
});
for (const value of ["", " ", "a".repeat(8001), "bad\u0000text", "\ud800"]) test("invalid question does not enter a synthetic run", async () => {
  await assert.rejects(() => createC18RunFixture().submit({ ...request(), question: value }));
});
test("binding and reference identity validation rejects invalid/mismatched/duplicate input", () => {
  for (const binding of [{ ...context().binding, snapshot_id: "not-a-digest" }, { ...context().binding, revision_id: "latest" }, { ...context().binding, injected: "private" }]) assert.throws(() => contract.freezeRunContext({ ...context(), binding }), contract.ResearchRunContractError);
  const reference = context().attachments[0];
  for (const attachments of [[{ ...reference, snapshot_id: "c".repeat(64) }], [{ ...reference, id: "../../unsafe" }], [reference, reference], Array(257).fill(reference)]) assert.throws(() => contract.freezeRunContext({ ...context(), attachments }), contract.ResearchRunContractError);
  assert.throws(() => contract.freezeRunContext({ ...context(), private_reasoning: "not allowed" } as contract.RunContext));
  assert.throws(() => contract.freezeRunValue({ value: Infinity })); const cyclic: Record<string, unknown> = {}; cyclic.self = cyclic; assert.throws(() => contract.freezeRunValue(cyclic));
});
test("C17 retained artifact references keep their own snapshots while catalogue references require the current snapshot", async () => {
  const artifact = { kind: "artifact" as const, id: "artifact:retained", snapshot_id: "c".repeat(64) };
  const input = { ...context(), attachments: [...context().attachments, artifact], pins: [artifact] };
  const frozen = contract.freezeRunContext(input);
  assert.equal(frozen.binding.snapshot_id, snapshot); assert.equal(frozen.attachments[1].snapshot_id, artifact.snapshot_id);
  const fixture = createC18RunFixture({ scenario: "running" }); const original = await fixture.submit({ ...request(), context: input });
  artifact.snapshot_id = "d".repeat(64);
  assert.equal(original.context.attachments[1].snapshot_id, "c".repeat(64));
  const stopped = await fixture.cancel(address(original)); const next = await fixture.continue({ ...address(stopped), idempotency_key: uuid(11) });
  assert.deepEqual(next.context, original.context); assert.equal(next.context.pins[0].snapshot_id, "c".repeat(64));
  assert.throws(() => contract.freezeRunContext({ ...context(), attachments: [{ ...artifact, kind: "catalogue" }] }), contract.ResearchRunContractError);
});
test("reference uniqueness follows the complete C17 kind/id/snapshot identity", () => {
  const one = { kind: "artifact" as const, id: "artifact:retained", snapshot_id: "c".repeat(64) };
  const two = { ...one, snapshot_id: "d".repeat(64) };
  const result = contract.freezeRunContext({ ...context(), attachments: [one, two] });
  assert.equal(result.attachments.length, 2);
  assert.throws(() => contract.freezeRunContext({ ...context(), attachments: [one, { ...one }] }), contract.ResearchRunContractError);
});
test("production entry import graphs cannot select the development fixture", () => {
  const visited = new Set<string>();
  const walk = (path: string): void => {
    if (visited.has(path)) return; visited.add(path);
    assert.equal(path.includes("/development/"), false, `Production entry reached ${path}`);
    const source = ts.createSourceFile(path, readFileSync(path, "utf8"), ts.ScriptTarget.Latest, true);
    const imports: string[] = [];
    const visit = (node: ts.Node): void => {
      if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) imports.push(node.moduleSpecifier.text);
      if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword && node.arguments[0] && ts.isStringLiteral(node.arguments[0])) imports.push(node.arguments[0].text);
      ts.forEachChild(node, visit);
    };
    visit(source);
    for (const specifier of imports) {
      if (!specifier.startsWith(".") || specifier.endsWith(".css")) continue;
      const base = resolve(dirname(path), specifier); const target = [base, `${base}.ts`, `${base}.tsx`, `${base}/index.ts`, `${base}/index.tsx`].find(existsSync);
      if (target && /\.tsx?$/.test(target)) walk(target);
    }
  };
  walk(fileURLToPath(new URL("../src/v1-entry.tsx", import.meta.url)));
  walk(fileURLToPath(new URL("../src/runtime-app.tsx", import.meta.url)));
  assert.ok(visited.size > 5); assert.equal([...visited].some((path) => path.endsWith("run-fixture.ts")), false);
});
test("elapsed formatter preserves zero and avoids fabricated wall time", () => {
  assert.equal(contract.formatActiveElapsed(0), "0:00"); assert.equal(contract.formatActiveElapsed(61009), "1:01");
  for (const value of [-1, 0.5, Infinity, NaN]) assert.throws(() => contract.formatActiveElapsed(value));
});

// Compile the actual TSX presentation into an isolated in-memory CommonJS module.
// This executes real React markup without adding a second browser/test runtime.
const require = createRequire(import.meta.url);
const activityModule = { exports: {} as {
  ResearchActivity: ComponentType<ResearchActivityProps>;
  ResearchResults: ComponentType<{ locale: "en" | "ja"; runs: readonly contract.ResearchRun[]; onOpenEvidence?: (e: contract.RunEvidence, r: contract.ResearchRun) => void }>;
  ResearchEvidence: ComponentType<{ locale: "en" | "ja"; evidence: contract.RunEvidence | null }>;
} };
const compiled = ts.transpileModule(readFileSync(new URL("../src/research-activity.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
new Function("require", "module", "exports", compiled)((name: string) => name === "./research-run-contract" ? contract : name.endsWith(".css") ? {} : require(name), activityModule, activityModule.exports);
const { ResearchActivity, ResearchResults, ResearchEvidence } = activityModule.exports;

for (const locale of ["en", "ja"] as const) test(`actual React activity/results/evidence render localized empty/running/error/partial/cancelled/clarification states (${locale})`, async () => {
  const empty = renderToStaticMarkup(React.createElement(ResearchActivity, { locale, runs: [] }));
  assert.match(empty, locale === "en" ? /No submitted activity/ : /実行履歴はありません/); assert.match(empty, /C20/);
  const runs: contract.ResearchRun[] = [];
  for (const scenario of ["running", "failed", "partial", "clarification"] as const) {
    const fixture = createC18RunFixture({ scenario }); const run = await fixture.submit(request()); await fixture.status(address(run)); runs.push(await fixture.status(address(run)));
  }
  const cancelledFixture = createC18RunFixture(); const started = await cancelledFixture.submit(request()); runs.push(await cancelledFixture.cancel(address(started)));
  const html = renderToStaticMarkup(React.createElement(ResearchActivity, { locale, runs }));
  for (const status of ["running", "failed", "partial", "awaiting_clarification", "cancelled"]) assert.match(html, new RegExp(`data-status="${status}"`));
  assert.match(html, locale === "en" ? /Synthetic development activity/ : /合成された開発用の処理/);
  assert.match(html, locale === "en" ? /Incomplete output/ : /未完了の出力/); assert.match(html, /textarea/); assert.match(html, /disabled=""/);
  assert.equal(html.includes("private_reasoning"), false);
  const results = renderToStaticMarkup(React.createElement(ResearchResults, { locale, runs })); assert.match(results, locale === "en" ? /Descriptive query/ : /記述的なクエリ/);
  const evidence = runs.find((run) => run.result)!.result!.evidence[0];
  const detail = renderToStaticMarkup(React.createElement(ResearchEvidence, { locale, evidence })); assert.match(detail, snapshot === "a".repeat(64) ? /aaaaaaaaaaaaaaaa/ : /impossible/);
  assert.match(detail, locale === "en" ? /Retained artifact content is unavailable/ : /保持された成果物の内容は利用できません/);
});
test("a result citation invokes the supplied evidence action with the exact run and identity", async () => {
  const fixture = createC18RunFixture(); const run = await fixture.submit(request()); await fixture.status(address(run)); const done = await fixture.status(address(run));
  const calls: unknown[] = [];
  const tree = (ResearchResults as (props: { locale: "en"; runs: readonly contract.ResearchRun[]; onOpenEvidence: (e: contract.RunEvidence, r: contract.ResearchRun) => void }) => ReactElement)({ locale: "en", runs: [done], onOpenEvidence: (e, r) => calls.push([e, r]) });
  const buttons: ReactElement<{ onClick?: () => void; "aria-label"?: string }>[] = [];
  const walk = (node: ReactNode): void => {
    if (Array.isArray(node)) { node.forEach(walk); return; }
    if (!React.isValidElement(node)) return;
    const element = node as ReactElement<{ children?: ReactNode; onClick?: () => void; "aria-label"?: string }>;
    if (typeof element.type === "function") { walk((element.type as (props: unknown) => ReactNode)(element.props)); return; }
    if (element.type === "button") buttons.push(element); walk(element.props.children);
  };
  walk(tree); assert.equal(buttons.length, 1); assert.match(buttons[0].props["aria-label"]!, /Open evidence 1/); buttons[0].props.onClick!();
  assert.deepEqual(calls, [[done.result!.evidence[0], done]]);
});
