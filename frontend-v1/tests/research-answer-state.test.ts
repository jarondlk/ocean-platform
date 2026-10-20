import assert from "node:assert/strict";
import test from "node:test";
import { ResearchDraftStore, ResearchStateError } from "../src/research-state.ts";
import { answerActive, mergeAnswerEvents, mergeAnswerSnapshot } from "../src/research-answer-state.ts";
import type { AnswerMutationIntent } from "../src/research-evidence-service.ts";
import * as f from "./research-evidence-fixtures.ts";
const identity = { accountId: "account:one", permissionRevision: "policy:one" }, slot = `${f.inv}:${f.conv}`;
const intent = (): AnswerMutationIntent => ({ method: "submit", request: { ...f.runAddress, input_version: 1, locale: "ja", idempotency_key: f.key }, binding: { ...f.binding } });
test("separate answer key and original submitted binding survive unchanged identity mounts, with no body storage", () => {
  const store = new ResearchDraftStore(); store.bind(identity); const original = intent();
  store.rememberAnswerMutation(slot, original); store.bind({ ...identity }); const pending = store.pendingAnswerMutation(slot)!;
  assert.deepEqual(pending, original); assert.equal(Object.isFrozen(pending.request), true); assert.equal(Object.isFrozen(pending.binding), true);
  original.request.idempotency_key = f.run; assert.equal(pending.request.idempotency_key, f.key); assert.throws(() => store.rememberAnswerMutation(slot, original), ResearchStateError);
  store.rememberAnswerMutation(slot, structuredClone(pending)); assert.equal(store.pendingRunMutation(slot), null); assert.equal(store.pendingMutation(slot), null);
  store.forgetAnswerMutation(slot); assert.equal(store.pendingAnswerMutation(slot), null);
});
test("volatile selected run/job/original receipt IDs restore within conversation and clear at permission/account/denial changes", () => {
  const store = new ResearchDraftStore(); store.bind(identity); const selected = { runId: f.run, jobId: f.jobId, receiptId: f.receiptAddress.receipt_id };
  store.selectAnswer(f.inv, f.conv, selected); store.rememberAnswerMutation(slot, intent()); assert.deepEqual(store.answerSelection(f.inv, f.conv), selected); assert.equal(store.answerSelection(f.inv, f.key).runId, null);
  store.bind({ ...identity }); assert.deepEqual(store.answerSelection(f.inv, f.conv), selected);
  for (const next of [{ ...identity, permissionRevision: "new-policy" }, { ...identity, accountId: "other-account" }]) {
    store.bind(next); assert.equal(store.answerSelection(f.inv, f.conv).runId, null); assert.equal(store.pendingAnswerMutation(slot), null); store.selectAnswer(f.inv, f.conv, selected); store.rememberAnswerMutation(slot, intent());
  }
  store.clear(); assert.throws(() => store.answerSelection(f.inv, f.conv), ResearchStateError); store.bind(identity); assert.equal(store.pendingAnswerMutation(slot), null);
});
for (const mutate of [(v: any) => { v.request.extra = "prose"; }, (v: any) => { v.request.input_version = 0; }, (v: any) => { v.request.locale = "fr"; }, (v: any) => { v.request.conversation_id = f.key; }, (v: any) => { v.binding.payload_sha256 = "forged"; }, (v: any) => { v.request.idempotency_key = "new"; }]) test("answer intents reject private payload additions and forged immutable request fields", () => { const store = new ResearchDraftStore(); store.bind(identity); const value = intent(); mutate(value); assert.throws(() => store.rememberAnswerMutation(slot, value), ResearchStateError); });
test("selection cannot restore a forged receipt, unbound job, arbitrary fields or invalid run URL", () => {
  const store = new ResearchDraftStore(); store.bind(identity);
  for (const value of [{ runId: f.run, jobId: null, receiptId: "other-receipt" }, { runId: null, jobId: f.jobId, receiptId: null }, { runId: "../run", jobId: null, receiptId: null }, { runId: f.run, jobId: null, receiptId: null, answer: "private prose" }]) assert.throws(() => store.selectAnswer(f.inv, f.conv, value as never), ResearchStateError);
});
test("wire snapshot highwater does not impersonate already merged answer events", () => {
  const initial = f.job(); initial.latest_event_cursor = 3; const view = mergeAnswerSnapshot(undefined, initial);
  assert.equal(view.event_cursor, 0); assert.equal(view.activity.length, 0); const merged = mergeAnswerEvents(view, f.events(f.jobId, 0, 2, 3));
  assert.equal(merged.event_cursor, 2); assert.equal(merged.job.latest_event_cursor, 3); assert.equal(merged.activity.length, 2);
  const refreshed = mergeAnswerSnapshot(merged, initial); assert.equal(refreshed.event_cursor, 2); assert.deepEqual(refreshed.activity, merged.activity);
  const final = mergeAnswerEvents(refreshed, f.events(f.jobId, 2, 1, 3)); assert.equal(final.event_cursor, 3); assert.equal(Object.isFrozen(final.activity[0].summary), true);
});
for (const mutate of [(v: any) => { v.id = f.run; }, (v: any) => { v.input_version = 2; }, (v: any) => { v.run_id = f.key; }, (v: any) => { v.binding.snapshot_id = f.policy; }, (v: any) => { v.locale = "ja"; }, (v: any) => { v.active_elapsed_ms = 0; }, (v: any) => { v.latest_event_cursor = 0; }, (v: any) => { v.budget.tool_actions = 0; }, (v: any) => { v.budget.model_calls = 0; }, (v: any) => { v.budget.cancellation_requested = false; }]) test("snapshot merge rejects changed binding or spent budget/highwater regression", () => {
  const before = f.job(); before.active_elapsed_ms = 100; before.latest_event_cursor = 1; before.budget.model_calls = 1; before.budget.cancellation_requested = true;
  const after = structuredClone(before); mutate(after); assert.throws(() => mergeAnswerSnapshot(mergeAnswerSnapshot(undefined, before), after));
});
test("immutable completed answer cannot be changed, removed or restarted; cancelled preparation remains distinct", () => {
  const complete = f.job("completed"), view = mergeAnswerSnapshot(undefined, complete); const altered = structuredClone(complete); altered.answer!.blocks[0].text = "Altered prose"; assert.throws(() => mergeAnswerSnapshot(view, altered));
  for (const status of ["queued", "running", "failed"] as const) assert.throws(() => mergeAnswerSnapshot(view, f.job(status)));
  assert.equal(answerActive(f.job("running")), true); assert.equal(answerActive(f.job("cancelled")), false); const cancelled = mergeAnswerSnapshot(undefined, f.job("cancelled")); assert.throws(() => mergeAnswerSnapshot(cancelled, f.job("queued")));
});
for (const mutate of [(v: any) => { v.events[0].cursor = 2; }, (v: any) => { v.events[0].job_id = f.key; }, (v: any) => { v.events[0].elapsed_ms = -1; }, (v: any) => { v.binding.revision_id = f.run; }, (v: any) => { v.has_more = true; }]) test("event merge rejects cross-job/context, repeated or regressing events before appending", () => { const initial = f.job(); initial.latest_event_cursor = 1; const value = f.events(); mutate(value); assert.throws(() => mergeAnswerEvents(mergeAnswerSnapshot(undefined, initial), value)); });
