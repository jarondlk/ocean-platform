import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { ExperimentSession, experimentDecision, parseExperimentSelection, experimentSelectionUrl, reconcileExperimentSelection, mergeExperimentEvents, mergeExperimentSnapshot } from "../src/experiment-state.ts";
import { executeExperimentMutation, type ExperimentMutationIntent } from "../src/experiment-service.ts";
import type { ExperimentSnapshot, ExperimentEventsResponse } from "../src/experiment-contract.ts";
const captured = JSON.parse(readFileSync(new URL("../../docs/plans/ocean-v1/evidence/C22/http-wire-current-source.json", import.meta.url), "utf8"));
const snapshot = () => structuredClone(captured.actions.find((row: any) => row.action === "approve").response.experiment) as ExperimentSnapshot;
const key = "b414e75c-e664-4be4-bf86-cfd944796f01", other = "b414e75c-e664-4be4-bf86-cfd944796f02";
function intent(): ExperimentMutationIntent { const value = snapshot(); return { method: "approve", request: experimentDecision(value, key), binding: value.binding }; }

test("uncertain mutation retains one immutable exact key across ordinary navigation and same identity binding", () => {
  const session = new ExperimentSession(), value = intent(); session.bind("user:permission1"); session.rememberPending(value.binding, value);
  session.bind("user:permission1"); assert.deepEqual(session.getPending(value.binding), value);
  assert.equal(Object.isFrozen(session.getPending(value.binding)!.request), true);
  const changedContext = { ...value.binding, context_revision_id: other };
  assert.deepEqual(session.getPending(changedContext), value); // caller must reconcile the original binding.
  assert.throws(() => session.rememberPending(value.binding, { ...value, request: { ...value.request, idempotency_key: other } } as any));
  session.forgetPending(value.binding, { ...value, request: { ...value.request, idempotency_key: other } } as any);
  assert.deepEqual(session.getPending(value.binding), value);
  session.forgetPending(value.binding, value); assert.equal(session.getPending(value.binding), null);
});

test("account/permission transitions clear private requests and invalidate every earlier callback epoch", () => {
  const session = new ExperimentSession(), value = intent();
  assert.throws(() => session.getPending(value.binding));
  session.bind("first:revision1"); const first = session.generation; session.rememberPending(value.binding, value);
  assert.equal(session.isCurrent("first:revision1", first), true);
  session.bind("first:revision2"); assert.equal(session.isCurrent("first:revision1", first), false); assert.equal(session.getPending(value.binding), null);
  session.rememberPending(value.binding, value); const second = session.generation;
  session.bind("second:revision2"); assert.equal(session.getPending(value.binding), null); assert.equal(session.isCurrent("first:revision2", second), false);
  session.bind(null); assert.throws(() => session.getPending(value.binding)); assert.equal(session.isCurrent(null as any, session.generation), false);
});

test("memory intent cannot bind a request from a different review context and mutation execution rejects it before transport", async () => {
  const session = new ExperimentSession(), value = intent(); session.bind("user");
  const forged = { ...value, request: { ...value.request, context_revision_id: other } } as any;
  assert.throws(() => session.rememberPending(value.binding, forged));
  let calls = 0; await assert.rejects(executeExperimentMutation({ approve: async () => { calls++; throw new Error(); } } as any, forged)); assert.equal(calls, 0);
});

test("a hard reload has no private request recovery fiction; committed history must be rediscovered", () => {
  const first = new ExperimentSession(), value = intent(); first.bind("user"); first.rememberPending(value.binding, value);
  const reload = new ExperimentSession(); reload.bind("user"); assert.equal(reload.getPending(value.binding), null);
});

test("bounded pending slots never evict uncertain mutations to make room", () => {
  const session = new ExperimentSession(); session.bind("user");
  for (let n = 1; n <= 64; n++) {
    const value = structuredClone(intent()), id = `00000000-0000-4000-8000-${n.toString(16).padStart(12, "0")}`;
    value.binding.conversation_id = id; (value.request as any).conversation_id = id;
    session.rememberPending(value.binding, value);
  }
  const extra = intent(); assert.throws(() => session.rememberPending(extra.binding, extra));
  const first = { ...extra.binding, conversation_id: "00000000-0000-4000-8000-000000000001" };
  assert.notEqual(session.getPending(first), null);
});

test("canonical experiment/proposal URL selection preserves existing research location parameters", () => {
  const value = snapshot(), base = `?view=research&investigation=${value.binding.investigation_id}&conversation=${value.binding.conversation_id}&workspace=experiments&pane=workspace`;
  const url = experimentSelectionUrl(base, { experiment_id: value.id, proposal_revision_id: value.proposal_revision_id });
  assert.deepEqual(parseExperimentSelection(url), { experiment_id: value.id, proposal_revision_id: value.proposal_revision_id });
  const query = new URLSearchParams(url); assert.equal(query.get("workspace"), "experiments"); assert.equal(query.get("pane"), "workspace");
  const next = base.replace("workspace=experiments", "workspace=context");
  assert.deepEqual(parseExperimentSelection(reconcileExperimentSelection(url, next)), parseExperimentSelection(url));
  const differentConversation = next.replace(value.binding.conversation_id, other);
  assert.equal(parseExperimentSelection(reconcileExperimentSelection(url, differentConversation)), null);
  assert.equal(parseExperimentSelection(reconcileExperimentSelection(url, "?view=catalogue")), null);
  assert.equal(parseExperimentSelection(experimentSelectionUrl(url, null)), null);
});

for (const query of ["?proposal=" + key, "?experiment=broken", "?experiment=" + key + "&experiment=" + key, "?experiment=" + key + "&proposal=broken", "?experiment=" + key + "&proposal=" + other + "&proposal=" + other]) {
  test(`malformed or duplicate selection is not a trusted request: ${query.slice(0, 70)}`, () => assert.equal(parseExperimentSelection(query), null));
}

test("an explicitly malformed next selection clears rather than resurrecting an old selection", () => {
  const value = snapshot(), base = `?view=research&investigation=${value.binding.investigation_id}&conversation=${value.binding.conversation_id}`;
  const previous = experimentSelectionUrl(base, { experiment_id: value.id, proposal_revision_id: null });
  assert.equal(parseExperimentSelection(reconcileExperimentSelection(previous, base + "&experiment=bad")), null);
});

test("consecutive retained events merge without erased history; gaps, stale heads and wrong experiments fail", () => {
  const value = snapshot(); value.latest_event_cursor = 2;
  const history = { snapshot: value, event_cursor: 0, events: [] };
  const page: ExperimentEventsResponse = { version: "research-experiments-v1", experiment_id: value.id, after_cursor: 0, next_cursor: 1,
    latest_event_cursor: 2, has_more: true, items: [{ cursor: 1, kind: "created", summary: { en: "Prepared", ja: "準備済み" } }] };
  const merged = mergeExperimentEvents(history, page); assert.equal(merged.events.length, 1); assert.equal(merged.event_cursor, 1);
  assert.throws(() => mergeExperimentEvents(history, { ...page, experiment_id: key }));
  assert.throws(() => mergeExperimentEvents(history, { ...page, items: [{ ...page.items[0], cursor: 2 }] }));
  assert.throws(() => mergeExperimentEvents(history, { ...page, latest_event_cursor: 1, has_more: false }));
  assert.throws(() => mergeExperimentEvents(merged, page));
});

test("status snapshot merges reject retained identity mutation, stale state and revision substitution", () => {
  const value = snapshot(); assert.equal(mergeExperimentSnapshot(undefined, value), value);
  assert.throws(() => mergeExperimentSnapshot(value, { ...value, id: key }));
  assert.throws(() => mergeExperimentSnapshot(value, { ...value, latest_event_cursor: 0 }));
  assert.throws(() => mergeExperimentSnapshot(value, { ...value, proposal_revision_id: key }));
  assert.throws(() => mergeExperimentSnapshot(value, { ...value, hashes: { ...value.hashes, code_sha256: "0".repeat(64) } }));
  assert.throws(() => mergeExperimentSnapshot(value, { ...value, binding: { ...value.binding, context_revision_id: other } }));
  const revision = { ...value, version: value.version + 1, proposal_revision_id: key, binding: { ...value.binding, context_revision_id: other } };
  assert.equal(mergeExperimentSnapshot(value, revision), revision);
  assert.throws(() => mergeExperimentSnapshot(value, { ...revision, binding: { ...revision.binding, investigation_id: key } }));
});
