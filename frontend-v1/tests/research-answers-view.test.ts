import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import * as scheduler from "../src/research-history-scheduler.ts";
import * as history from "../src/research-answer-history.ts";
import * as state from "../src/research-answer-state.ts";
import * as service from "../src/research-evidence-service.ts";
import * as draft from "../src/research-state.ts";
import * as exports from "../src/exports.ts";
import * as f from "./research-evidence-fixtures.ts";
const require = createRequire(import.meta.url), source = readFileSync(new URL("../src/research-answers.tsx", import.meta.url), "utf8");
const module = { exports: {} as Record<string, any> };
const dependencies: Record<string, unknown> = { "./research-history-scheduler": scheduler, "./research-answer-history": history, "./research-answer-state": state, "./research-evidence-service": service, "./research-state": draft, "./exports": exports };
new Function("require", "module", "exports", ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText)((name: string) => name.endsWith(".css") ? {} : dependencies[name] ?? require(name), module, module.exports);
const { AnswerCard, RetainedEvidence, useResearchAnswers } = module.exports;
for (const locale of ["en", "ja"] as const) test(`actual React answer markup retains qualifiers, literal host table values and citations (${locale})`, () => {
  const job = f.job("partial"); job.answer!.blocks[0].text = "<img src=x onerror=alert(1)> source text / 原文";
  job.answer!.blocks[0].data = { rows: [{ literal: "海洋 / literal", temperature: 0 }], columns: f.receipt().columns, preview_truncated: true };
  const html = renderToStaticMarkup(React.createElement(AnswerCard, { locale, view: state.mergeAnswerSnapshot(undefined, job), busy: false, onCancel() {}, onCitation() {}, receipts: [f.receipt()] }));
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/); assert.doesNotMatch(html, /<img|<script|C21|C20|synthetic|sample answer|P00/);
  assert.match(html, /海洋 \/ literal/); assert.match(html, /°C/); assert.match(html, /<td>0<\/td>/); assert.match(html, locale === "en" ? /Literal \/ unchanged/ : /原文 \/ そのまま/);
  assert.match(html, locale === "en" ? /Partial answer/ : /途中の回答/); assert.match(html, locale === "en" ? /Open evidence/ : /エビデンスを開く/); assert.match(html, locale === "en" ? /not independent scientific verification/ : /独立した科学的検証を意味しません/);
});
for (const locale of ["en", "ja"] as const) test(`actual React retained page shows exact totals, denominator, unit, original snapshot and current export gates (${locale})`, () => {
  const value = f.page(), html = renderToStaticMarkup(React.createElement(RetainedEvidence, { locale, value, section: "rows", busy: false, canExport: false, canAttach: true, onSection() {}, onPage() {}, onExport() {}, onAttach() {} }));
  assert.match(html, /321/); assert.match(html, /all observations in the selected scope/); assert.match(html, /海洋 \/ literal/); assert.match(html, /°C/); assert.match(html, new RegExp(f.sha)); assert.doesNotMatch(html, /P00|synthetic|C21|sample table/);
  assert.match(html, locale === "en" ? /Download page CSV/ : /ページのCSV/); assert.match(html, locale === "en" ? /Downloads require current export permission/ : /現在のエクスポート権限/); assert.match(html, /disabled=""/);
  assert.match(html, locale === "en" ? /does not copy answer prose or restrict inventory/ : /回答文のコピーや一覧の制限は行いません/);
});
test("actual retained empty states distinguish known zero and unknown population without preview-count promotion", () => {
  const render = (total: any) => renderToStaticMarkup(React.createElement(RetainedEvidence, { locale: "en", value: { ...f.page(), rows: [], section_total: total, next_offset: null }, section: "rows", busy: false, canExport: true, canAttach: true, onSection() {}, onPage() {}, onExport() {}, onAttach() {} }));
  const zero = render({ state: "known", value: 0, reason: null }), unknown = render({ state: "unknown", value: null, reason: "Provider has not published source coverage" });
  assert.match(zero, /No matching retained rows/); assert.match(unknown, /Unknown/); assert.match(unknown, /Provider has not published source coverage/); assert.doesNotMatch(unknown, /No matching retained rows/);
});
for (const row of [{ text: "Actual source quotation / 元の引用 <img src=x onerror=alert(1)>", start_byte: 42, end_byte: 110 }, { node: { id: "relationship:one", category: "proximity", qualification: "Physical identity is not established / 原文" } }]) test("actual zero-column retained documentary/catalogue payload remains visible as literal objects", () => {
  const value = f.page(); value.receipt.columns = []; value.rows = [row]; value.receipt.preview_rows = [];
  const html = renderToStaticMarkup(React.createElement(RetainedEvidence, { locale: "en", value, section: "rows", busy: false, canExport: true, canAttach: true, onSection() {}, onPage() {}, onExport() {}, onAttach() {} }));
  assert.match(html, /Retained literal objects/); assert.match(html, "text" in row ? /Actual source quotation \/ 元の引用/ : /Physical identity is not established \/ 原文/); assert.doesNotMatch(html, /<img|<script/);
});
test("actual answer terminal, active and cancelled states keep cancellation and shared budget separate", () => {
  const render = (status: Parameters<typeof f.job>[0]) => renderToStaticMarkup(React.createElement(AnswerCard, { locale: "en", view: state.mergeAnswerSnapshot(undefined, f.job(status)), busy: false, onCancel() {}, onCitation() {} }));
  assert.match(render("queued"), /Cancel answer preparation/); assert.match(render("running"), /Preparing answer/); assert.match(render("cancelled"), /Answer preparation was cancelled/); assert.doesNotMatch(render("cancelled"), /Cancel answer preparation|321 measurements/); assert.match(render("completed"), /shared budget/);
});
test("initial actual React hook render never dispatches generation from reads/restoration", () => {
  let calls = 0; const drafts = new draft.ResearchDraftStore(); drafts.bind({ accountId: "one", permissionRevision: "policy" }); drafts.selectAnswer(f.inv, f.conv, { runId: f.run, jobId: f.jobId, receiptId: f.receiptAddress.receipt_id });
  const client = service.createAnswerClient({ fetcher: async () => { calls++; throw new Error(); } });
  function Host() { return useResearchAnswers({ locale: "en", accessKey: "one:policy", investigationId: f.inv, conversationId: f.conv, contextRevision: f.key, drafts, runs: [], answers: client, evidence: service.createEvidenceClient(), submitEnabled: true, canExport: false, canAttach: false, externalBusy: false, onAttach: async () => false, onAccessLost() {}, onOpenEvidence() {} }).controls; }
  const html = renderToStaticMarkup(React.createElement(Host)); assert.equal(calls, 0); assert.match(html, /Prepare answer/); assert.match(html, /Checking saved answers/); assert.doesNotMatch(html, /synthetic|C21/);
});
test("production runtime and workspace wire independent transport and explicit attachment without changing C20 synthesis", () => {
  const runtime = readFileSync(new URL("../src/runtime-app.tsx", import.meta.url), "utf8"), workspace = readFileSync(new URL("../src/research-workspace.tsx", import.meta.url), "utf8");
  assert.match(runtime, /answerClient=\{!researchRunTransport && bootstrap\.research_evidence\?\.transport === "http-v1" \? serviceAnswers : undefined\}/);
  assert.match(runtime, /answerSubmitEnabled=\{!researchRunTransport && bootstrap\.research_evidence\?\.submit_enabled === true\}/); assert.match(runtime, /canExport=\{bootstrap\.identity\.permissions\.includes\("data:export"\)\}/);
  assert.match(workspace, /onAttach: reference => changeContext\(\{ op: "attach", reference \}\)/); assert.match(workspace, /onAccessLost: \(\) => fail\(\{ status_code: 403 \}\)/);
  assert.doesNotMatch(source, /dangerouslySetInnerHTML|localStorage|sessionStorage|exportTable\(|receiptExport\(|investigationExport\(/);
  assert.match(source, /downloadBlob\(result\.content_text, result\.filename, result\.mime_type\)/); assert.match(source, /scheduler\.current\?\.pause\(\); receiptScheduler\.current\?\.pause\(\)/);
  assert.match(source, /window\.addEventListener\("focus", check\)/); assert.match(source, /setInterval\(\(\) => \{ if \(document\.visibilityState !== "hidden"\) poll\.request\(\); \}, 10000\)/);
});
