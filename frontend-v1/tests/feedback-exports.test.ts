import assert from "node:assert/strict";
import test from "node:test";
import { saveLocalFeedback, triageLocalFeedback, type FeedbackEntry } from "../src/feedback-model.ts";
import { exportTable, investigationExport, investigationMarkdown, receiptExport, safeCell, tableCsv } from "../src/exports.ts";
import { createPreviewState, locationUrl, parseLocation, restoreState } from "../src/state.ts";

test("answer feedback updates one run, preserves another run, and requires negative detail", () => {
  const entry: FeedbackEntry = { id: "f1", category: "answer", message: "", createdAt: 1000, status: "new", runId: "run-1", rating: "helpful" };
  const saved = saveLocalFeedback([], entry); assert.equal(saved.length, 1);
  assert.throws(() => saveLocalFeedback(saved, { ...entry, id: "f2", rating: "unhelpful" }));
  const updated = saveLocalFeedback(saved, { ...entry, id: "f2", rating: "unhelpful", reason: "coverage" });
  assert.equal(updated.length, 1); assert.equal(updated[0].rating, "unhelpful");
  const another = saveLocalFeedback(updated, { ...entry, id: "f3", runId: "run-2" }); assert.equal(another.length, 2);
  const triaged = triageLocalFeedback(another, "f2", "reviewing"); assert.equal(triaged.find((item) => item.id === "f2")!.status, "reviewing"); assert.equal(another[1].status, "new");
});
test("safe exports preserve negative numeric values, protect formulas, and retain units and complete rows", () => {
  assert.equal(safeCell(-2.5), '"-2.5"'); assert.equal(safeCell(" =HYPERLINK(\"x\")"), '"\' =HYPERLINK(""x"")"');
  const csv = tableCsv({ entity: { en: "rows", ja: "行" }, columns: [{ key: "value", title: { en: "Temperature", ja: "水温" }, unit: "°C" }], rows: [{ value: -2.5 }, { value: 3 }] }, "en");
  const labelled = exportTable({ entity: { en: "rows", ja: "行" }, columns: [{ key: "v", title: { en: "v", ja: "v" } }], rows: [{ v: 1 }, { v: 2 }] }, { snapshotId: "sample-02", recordId: "sst-2022" });
  assert.equal(labelled.rows.length, 2); assert.equal(labelled.rows[1]._preview, "P00 synthetic sample"); assert.equal(labelled.rows[1]._record, "sst-2022");
  assert.ok(csv.startsWith('\ufeff"Temperature (°C)"')); assert.ok(csv.includes('"-2.5"\r\n"3"'));
});
test("investigation and evidence exports retain frozen scope, identity and synthetic authority labels", () => {
  const investigation = createPreviewState().investigations[0]; const exported = investigationExport(investigation);
  assert.match(exported.label, /not scientific publication/); assert.equal(exported.investigation.snapshotId, investigation.snapshotId);
  exported.investigation.context.attachments.length = 0; assert.equal(investigation.context.attachments.length, 2);
  const receipt = investigation.conversations[0].messages[1].answer!.receipt; assert.equal(receiptExport(receipt).receipt.contentIdentity, receipt.contentIdentity);
  assert.match(investigationMarkdown(investigation, "en"), /Synthetic|synthetic/); assert.match(investigationMarkdown(investigation, "en"), /receipt-seed-inventory/);
});
test("dedicated support/admin routes restore and first-round local state migrates without losing drafts", () => {
  for (const view of ["about", "feedback", "admin"] as const) { const location = { ...parseLocation(""), view }; assert.ok(locationUrl(location).startsWith(`/${view}?`)); assert.equal(parseLocation("", view).view, view); }
  assert.equal(parseLocation("?view=catalogue").nodeId, "catalogue-home");
  const old = createPreviewState(); old.investigations[0].conversations[0].draft = "Keep my draft";
  delete (old.preferences as Partial<typeof old.preferences>).role; delete (old as Partial<typeof old>).feedback;
  const migrated = restoreState(JSON.stringify(old))!; assert.equal(migrated.preferences.role, "researcher"); assert.deepEqual(migrated.feedback, []); assert.equal(migrated.investigations[0].conversations[0].draft, "Keep my draft");
});
