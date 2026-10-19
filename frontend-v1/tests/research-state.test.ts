import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { freezeSubmittedBinding, parseResearchLocation, ResearchDraftStore, researchLocationUrl, ResearchStateError, updateResearchLocation, WORKSPACE_TABS } from "../src/research-state.ts";
import type { Conversation, Investigation, InvestigationContext, InvestigationMutationIntent } from "../src/investigation-service.ts";
import { defaultCatalogueScope } from "../src/catalogue-service.ts";
import { executeRunMutation, type RunMutationIntent, type ResearchRunTransport } from "../src/research-run-contract.ts";
const inv = "11111111-1111-1111-1111-111111111111", other = "22222222-2222-2222-2222-222222222222", conv = "33333333-3333-3333-3333-333333333333";
const identity = { accountId: "account:owner", permissionRevision: "policy:one" };
const wire = JSON.parse(readFileSync(new URL("../../docs/plans/ocean-v1/evidence/C18/client-wire.json", import.meta.url), "utf8")) as { cases: { method: string; status: number; payload: Record<string, unknown>; expected: Record<string, any> }[] };

test("canonical empty research route remains explicitly in the real research view", () => {
  assert.deepEqual(parseResearchLocation(""), { investigationId: null, conversationId: null, workspaceTab: "context", mobilePane: "chat" });
  assert.equal(researchLocationUrl(parseResearchLocation("")), "/?view=research");
});
for (const tab of WORKSPACE_TABS) for (const pane of ["chat", "workspace"]) test(`reload/Back/Forward round trips selected conversation and ${tab}/${pane}`, () => {
  const original = parseResearchLocation(`?view=research&investigation=${inv}&conversation=${conv}&workspace=${tab}&pane=${pane}`), url = researchLocationUrl(original);
  assert.deepEqual(parseResearchLocation(new URL(url, "https://v1.invalid").search), original);
  assert.equal(new URL(url, "https://v1.invalid").searchParams.get("view"), "research");
});
for (const query of ["?view=preview", "?view=research&view=research", `?conversation=${conv}`, "?investigation=../private", `?investigation=${inv}&investigation=${other}`, `?investigation=${inv}&conversation=`, "?workspace=admin", "?workspace=Context", "?pane=preview", "?pane=chat&pane=workspace", "?workspace=context&workspace=evidence"]) test(`rejects invalid research restoration ${query.slice(0, 80)}`, () => {
  assert.throws(() => parseResearchLocation(query), ResearchStateError);
});
test("navigation never admits scientific scope, identity, fixture or attach side effects", () => {
  const before = parseResearchLocation(`?view=research&investigation=${inv}&conversation=${conv}`);
  const forged = parseResearchLocation(`?view=research&investigation=${inv}&conversation=${conv}&scope=all&role=admin&account=other&revision=forged&attach=1&pin=1&mode=synthetic-preview&preview=1`);
  assert.deepEqual(forged, before); assert.doesNotMatch(researchLocationUrl(forged), /scope|role|account|revision|attach|pin|preview|mode/);
});
test("changing investigation clears old conversation unless explicit without mutating inputs", () => {
  const before = parseResearchLocation(`?investigation=${inv}&conversation=${conv}&workspace=evidence`), copy = structuredClone(before);
  assert.equal(updateResearchLocation(before, { investigationId: other }).conversationId, null);
  assert.equal(updateResearchLocation(before, { investigationId: other, conversationId: conv }).conversationId, conv);
  assert.equal(updateResearchLocation(before, { workspaceTab: "results" }).conversationId, conv); assert.deepEqual(before, copy);
  assert.throws(() => updateResearchLocation(before, { role: "admin" } as never), ResearchStateError);
  assert.equal(updateResearchLocation(before, { investigationId: null }).conversationId, null);
});
test("restored explicit routes are sufficient for browser history selection", () => {
  const first = parseResearchLocation(`?investigation=${inv}&conversation=${conv}`), second = updateResearchLocation(first, { workspaceTab: "evidence" }), third = updateResearchLocation(second, { investigationId: other });
  const history = [first, second, third].map(researchLocationUrl);
  for (const i of [0, 1, 2, 1, 0, 1, 2]) assert.deepEqual(parseResearchLocation(new URL(history[i], "https://v1.invalid").search), [first, second, third][i]);
});
test("drafts are isolated by investigation/conversation and survive only an unchanged trusted binding", () => {
  const store = new ResearchDraftStore(); assert.throws(() => store.readDraft(inv, conv), ResearchStateError);
  store.bind(identity); store.writeDraft(inv, conv, "Private draft 調査"); store.writeDraft(other, conv, "Separate");
  store.bind({ ...identity }); assert.equal(store.readDraft(inv, conv), "Private draft 調査"); assert.equal(store.readDraft(other, conv), "Separate");
  store.bind({ ...identity, permissionRevision: "policy:two" }); assert.equal(store.readDraft(inv, conv), "");
  store.writeDraft(inv, conv, "New policy draft"); store.bind({ ...identity, accountId: "account:other" }); assert.equal(store.readDraft(inv, conv), "");
  store.writeDraft(inv, conv, "Other owner"); store.bind(null); assert.throws(() => store.readDraft(inv, conv), ResearchStateError);
  store.bind(identity); assert.equal(store.readDraft(inv, conv), "");
});
test("uncertain mutation keeps original key/head and cannot be silently replaced", () => {
  const store = new ResearchDraftStore(); store.bind(identity);
  const source = wire.cases.find((sample) => sample.method === "changeContext")!;
  const intent = { method: "changeContext", request: structuredClone(source.payload) } as InvestigationMutationIntent;
  store.rememberMutation("context-change", intent); const retained = store.pendingMutation("context-change")!;
  assert.deepEqual(retained, intent); assert.equal(Object.isFrozen(retained), true); assert.equal(Object.isFrozen(retained.request), true);
  intent.request.idempotency_key = crypto.randomUUID(); assert.notEqual(retained.request.idempotency_key, intent.request.idempotency_key);
  assert.throws(() => store.rememberMutation("context-change", intent), ResearchStateError);
  store.forgetMutation("context-change"); store.rememberMutation("context-change", intent); assert.deepEqual(store.pendingMutation("context-change"), intent);
  store.bind({ ...identity, permissionRevision: "revoked" }); assert.equal(store.pendingMutation("context-change"), null);
});
test("same exact pending intent can be remembered again across temporary presentation mounts", () => {
  const store = new ResearchDraftStore(); store.bind(identity);
  const source = wire.cases.find((sample) => sample.method === "create")!, intent = { method: "create", request: source.payload } as InvestigationMutationIntent;
  store.rememberMutation("create", intent); store.bind({ ...identity }); store.rememberMutation("create", structuredClone(intent)); assert.deepEqual(store.pendingMutation("create"), intent);
  store.clear(); store.bind(identity); assert.equal(store.pendingMutation("create"), null);
});
test("draft sizes and invalid private values are bounded without storage or transport side effects", () => {
  const store = new ResearchDraftStore(); store.bind(identity);
  assert.throws(() => store.writeDraft(inv, conv, "x".repeat(64001)), ResearchStateError);
  assert.throws(() => store.writeDraft(inv, conv, "\ud800"), ResearchStateError);
  assert.throws(() => store.bind({ ...identity, role: "admin" } as never), ResearchStateError);
  assert.throws(() => store.rememberMutation("slot", { method: "execute", request: {} } as never), ResearchStateError);
  store.writeDraft(inv, conv, "value"); store.writeDraft(inv, conv, ""); assert.equal(store.readDraft(inv, conv), "");
});
test("submitted activity preserves a complete detached immutable explicit revision across later changes", () => {
  const created = wire.cases.find((sample) => sample.method === "create")!.expected, chat = wire.cases.find((sample) => sample.method === "createConversation")!.expected.conversation as Conversation;
  const input = { investigation: structuredClone(created.investigation) as Investigation, context: structuredClone(created.context) as InvestigationContext, conversation: structuredClone(chat) };
  const before = structuredClone(input.context), bound = freezeSubmittedBinding(input);
  assert.equal(bound.revision_id, input.context.id); assert.equal(bound.conversation_id, chat.id); assert.deepEqual(bound.context, before);
  input.context.id = crypto.randomUUID(); input.context.scope.sources.ctd.enabled = false;
  assert.deepEqual(bound.context, before); assert.equal(Object.isFrozen(bound.context.scope.sources.ctd), true);
  assert.throws(() => { (bound.context as InvestigationContext).pins.push({ kind: "artifact", id: "forged", snapshot_id: bound.snapshot_id }); }, TypeError);
});
test("submission binding rejects cross-owner conversation/context joins and invalid hashes", () => {
  const created = wire.cases.find((sample) => sample.method === "create")!.expected, chat = wire.cases.find((sample) => sample.method === "createConversation")!.expected.conversation;
  for (const mutate of [(v: any) => { v.conversation.investigation_id = other; }, (v: any) => { v.context.investigation_id = other; }, (v: any) => { v.context.payload_sha256 = "wrong"; }]) {
    const input = structuredClone({ investigation: created.investigation, context: created.context, conversation: chat }); mutate(input); assert.throws(() => freezeSubmittedBinding(input), ResearchStateError);
  }
});

function runIntent(): Extract<RunMutationIntent, { method: "submit" }> {
  return { method: "submit", request: { idempotency_key: other, question: "Private question", context: { binding: { investigation_id: inv, conversation_id: conv, revision_id: other, snapshot_id: "a".repeat(64), payload_sha256: "b".repeat(64) }, scope: defaultCatalogueScope(), attachments: [], pins: [] } } };
}
test("uncertain run mutations preserve the complete original frozen intent across temporary mounts", async () => {
  const store = new ResearchDraftStore(); store.bind(identity); const intent = runIntent();
  store.rememberRunMutation("selected-chat", intent); store.bind({ ...identity });
  const retained = store.pendingRunMutation("selected-chat")!; assert.deepEqual(retained, intent);
  assert.equal(Object.isFrozen(retained.request), true); assert.equal(Object.isFrozen((retained as typeof intent).request.context.scope.sources.ctd), true);
  (intent.request as { idempotency_key: string }).idempotency_key = crypto.randomUUID(); assert.notEqual(retained.request.idempotency_key, intent.request.idempotency_key);
  assert.throws(() => store.rememberRunMutation("selected-chat", intent), ResearchStateError);
  store.rememberRunMutation("selected-chat", structuredClone(retained));
  const calls: unknown[] = [];
  const transport = { submit: async (body: unknown) => { calls.push(body); return {} as never; } } as unknown as ResearchRunTransport;
  await executeRunMutation(transport, retained); await executeRunMutation(transport, retained); assert.deepEqual(calls, [retained.request, retained.request]);
  store.forgetRunMutation("selected-chat"); assert.equal(store.pendingRunMutation("selected-chat"), null);
});
test("run intents remain account and permission bound and never migrate to a later identity", () => {
  const store = new ResearchDraftStore(); assert.throws(() => store.rememberRunMutation("slot", runIntent()), ResearchStateError);
  store.bind(identity); store.rememberRunMutation("slot", runIntent()); store.bind({ ...identity, permissionRevision: "changed" }); assert.equal(store.pendingRunMutation("slot"), null);
  store.rememberRunMutation("slot", runIntent()); store.bind({ ...identity, accountId: "other-owner" }); assert.equal(store.pendingRunMutation("slot"), null);
  store.rememberRunMutation("slot", runIntent()); store.bind(null); assert.throws(() => store.pendingRunMutation("slot"), ResearchStateError);
  store.bind(identity); assert.equal(store.pendingRunMutation("slot"), null);
});
test("run intent validation rejects missing binding, substituted addresses, non-JSON and oversized values", () => {
  const store = new ResearchDraftStore(); store.bind(identity);
  for (const intent of [ { method: "submit", request: { idempotency_key: other } }, { method: "cancel", request: { run_id: other, investigation_id: other, conversation_id: conv, idempotency_key: other }, binding: (runIntent() as Extract<RunMutationIntent, { method: "submit" }>).request.context.binding }, { ...runIntent(), binding: undefined }, { method: "unknown", request: {} }, { ...runIntent(), request: { ...(runIntent() as Extract<RunMutationIntent, { method: "submit" }>).request, question: "x".repeat(1024 * 1024) } } ]) assert.throws(() => store.rememberRunMutation("slot", intent as never), ResearchStateError);
  assert.equal(store.pendingRunMutation("slot"), null);
});
