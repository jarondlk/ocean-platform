import assert from "node:assert/strict";
import test from "node:test";
import { fixtureAdapter } from "../src/adapter.ts";
import { activeRun, advanceRun, approveProposal, beginRun, changeContext, createPreviewState, locationUrl, newConversation, newInvestigation, newProposal, parseLocation, refreshInvestigation, restoreState, reviseProposal, simulateProposal, tickConversation } from "../src/state.ts";

test("catalogue totals and membership remain complete across pages and languages", () => {
  const one = fixtureAdapter.list({ nodeId: "data", snapshotId: "sample-02", search: "2022", pageSize: 2 });
  const two = fixtureAdapter.list({ nodeId: "data", snapshotId: "sample-02", search: "2022", pageSize: 2, page: 2 });
  const all = fixtureAdapter.list({ nodeId: "data", snapshotId: "sample-02", search: "2022", pageSize: 100 });
  assert.equal(one.total, 4); assert.equal(two.total, 4);
  assert.deepEqual([...one.items, ...two.items].map((node) => node.id), all.items.map((node) => node.id));
  const japanese = fixtureAdapter.list({ nodeId: "data", snapshotId: "sample-02", search: "水温" });
  assert.ok(japanese.items.some((node) => node.source === "SST"));
});
test("unknown, unavailable, revoked and zero inventory outcomes are distinct", () => {
  assert.equal(fixtureAdapter.list({ nodeId: "data", snapshotId: "sample-02", scenario: "zero" }).total, 0);
  assert.equal(fixtureAdapter.list({ nodeId: "data", snapshotId: "sample-02", scenario: "unavailable" }).total, null);
  assert.equal(fixtureAdapter.list({ nodeId: "data", snapshotId: "sample-02", scenario: "revoked" }).status, "revoked");
});
test("browsing has no context side effect, adding context does not restrict scope", () => {
  const investigation = newInvestigation("Research"); const before = structuredClone(investigation.context);
  fixtureAdapter.list({ nodeId: "sst", snapshotId: investigation.snapshotId });
  assert.deepEqual(investigation.context, before);
  const attached = changeContext(before, "sst-2022", "attach");
  assert.deepEqual(attached.attachments, ["sst-2022"]); assert.deepEqual(attached.constraints, []);
  assert.deepEqual(before.attachments, []);
  const pinned = changeContext(attached, "ctd-2022", "pin");
  assert.deepEqual(pinned.constraints, ["ctd-2022"]); assert.deepEqual(pinned.attachments, ["sst-2022"]);
});
test("each run freezes context and snapshot, so later context changes affect only future runs", () => {
  const investigation = newInvestigation("Scope"); investigation.context = changeContext(investigation.context, "sst-2022", "pin");
  const chat = beginRun(investigation, investigation.conversations[0], "Count available data", "normal", 1000);
  investigation.context = changeContext(investigation.context, "ctd-2022", "pin"); investigation.snapshotId = "sample-01";
  assert.deepEqual(chat.runs[0].context.constraints, ["sst-2022"]); assert.equal(chat.runs[0].snapshotId, "sample-02");
  const done = tickConversation(chat, 6000); const receipt = done.messages.at(-1)!.answer!.receipt;
  assert.deepEqual(receipt.inputIds, ["sst-2022"]); assert.equal(receipt.totalRows, 1);
});
test("drafts and transcripts stay separate, including while opening an evidence deep link", () => {
  const state = createPreviewState(); const first = state.investigations[0].conversations[0]; const second = state.investigations[0].conversations[1];
  second.draft = "A question to keep";
  const url = locationUrl({ ...parseLocation(""), investigationId: "miyagi", conversationId: second.id, workspaceTab: "evidence", receiptId: first.messages.at(-1)!.answer!.receipt.id });
  assert.equal(parseLocation(url.split("?")[1]).receiptId, "receipt-seed-inventory");
  const restored = restoreState(JSON.stringify(state))!;
  assert.equal(restored.investigations[0].conversations[1].draft, "A question to keep");
  assert.equal(restored.investigations[0].conversations[1].messages.length, 0);
});
test("completed and partial runs produce one retained answer, even after repeated ticks", () => {
  const investigation = newInvestigation("Results");
  const chat = beginRun(investigation, investigation.conversations[0], "SST temperature", "partial", 1000);
  const done = tickConversation(chat, 6000); const again = tickConversation(done, 9000);
  assert.equal(done.runs[0].status, "partial"); assert.equal(again.messages.length, 2);
  assert.equal(done.messages[1].answer!.receipt.complete, false);
  assert.equal(done.messages[1].answer!.receipt.totalRows, 36);
});
test("cancellation terminates the simulation and a continuation keeps the original scope and a new draft", () => {
  const investigation = newInvestigation("Cancellation"); investigation.context = changeContext(investigation.context, "sst-2022", "pin");
  const chat = beginRun(investigation, investigation.conversations[0], "Temperature", "normal", 1000);
  chat.runs[0] = { ...chat.runs[0], status: "cancelling", cancellationAt: 1500 };
  const stopped = tickConversation(chat, 2200); assert.equal(stopped.runs[0].status, "cancelled"); assert.equal(stopped.messages.length, 1);
  investigation.context = changeContext(investigation.context, "ctd-2022", "pin"); stopped.draft = "Keep this next question";
  const continued = beginRun(investigation, stopped, stopped.runs[0].question, "normal", 3000, stopped.runs[0]);
  assert.equal(continued.draft, "Keep this next question");
  assert.equal(continued.runs[1].continuationOf, stopped.runs[0].id); assert.deepEqual(continued.runs[1].context.constraints, ["sst-2022"]);
});
test("clarification and interruption retain the question and never fabricate a result", () => {
  const investigation = newInvestigation("Clarification");
  const chat = beginRun(investigation, newConversation(), "Which area?", "clarification", 1000);
  const paused = tickConversation(chat, 3000); assert.equal(paused.draft, "Which area?"); assert.equal(paused.messages.length, 1); assert.equal(activeRun(paused), undefined);
  const interrupted = advanceRun({ ...chat.runs[0], scenario: "interrupted" }, 4000); assert.equal(interrupted.status, "interrupted");
  for (const scenario of ["error", "unavailable", "revoked"] as const) {
    const failed = tickConversation(beginRun(investigation, newConversation(), "Question", scenario, 1000), 6000);
    assert.equal(failed.runs[0].status, "error"); assert.equal(failed.messages.length, 1);
  }
});
test("refresh creates an independent branch, flags withdrawn context and preserves old evidence", () => {
  const original = createPreviewState().investigations[1]; const before = structuredClone(original);
  const branch = refreshInvestigation(original);
  assert.deepEqual(original, before); assert.notEqual(branch.id, original.id); assert.equal(branch.branchOf, original.id);
  assert.deepEqual(branch.removedContextIds, ["ctd-2021"]); assert.deepEqual(branch.context.attachments, ["sst-2022"]);
  assert.ok(fixtureAdapter.open("ctd-2021", original.snapshotId)); assert.equal(fixtureAdapter.open("ctd-2021", branch.snapshotId), undefined);
});
test("approval binds the reviewed proposal version and code edits invalidate it", () => {
  const investigation = createPreviewState().investigations[0]; const proposal = newProposal(investigation)!;
  assert.deepEqual(proposal.datasetIds, ["sst-2022"]);
  assert.equal(simulateProposal(proposal).status, "draft");
  const approved = approveProposal(proposal, proposal.version); assert.equal(approved.status, "approved");
  assert.equal(simulateProposal(approved, 1000).status, "queued");
  const revised = reviseProposal(approved, "print('changed')"); assert.equal(revised.status, "draft"); assert.equal(revised.approvedVersion, undefined);
  assert.equal(approveProposal(revised, proposal.version).status, "draft"); assert.equal(simulateProposal(revised).status, "draft");
  investigation.context.constraints = ["edna-2022"]; assert.equal(newProposal(investigation), undefined);
});
test("empty scope cannot produce fabricated matching datasets", () => {
  const investigation = newInvestigation("Empty");
  const done = tickConversation(beginRun(investigation, newConversation(), "Data", "zero", 1000), 6000);
  assert.equal(done.messages.at(-1)!.answer!.receipt.totalRows, 0); assert.deepEqual(done.messages.at(-1)!.answer!.receipt.inputIds, []);
});
test("malformed or stale local state fails safely and navigation preserves catalogue state", () => {
  assert.equal(restoreState("not json"), undefined); assert.equal(restoreState('{"version":0}'), undefined);
  const malformed = createPreviewState(); (malformed.investigations[0].conversations[0] as unknown as { draft: unknown }).draft = null;
  assert.equal(restoreState(JSON.stringify(malformed)), undefined);
  const location = parseLocation("?view=catalogue&node=sst-2022&snapshot=sample-01&section=methods&q=water&page=2");
  assert.deepEqual(parseLocation(locationUrl(location).split("?")[1]), location);
  assert.equal(parseLocation("?snapshot=invalid&page=-50&section=invalid").page, 1);
  assert.equal(parseLocation("?page=Infinity").page, 1);
  const brokenAnswer = createPreviewState();
  (brokenAnswer.investigations[0].conversations[0].messages[1].body as unknown as { en: unknown }).en = { unsafe: true };
  assert.equal(restoreState(JSON.stringify(brokenAnswer)), undefined);
});
