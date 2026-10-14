import assert from "node:assert/strict";
import test from "node:test";
import { catalogue } from "../src/fixtures.ts";
import { ADMIN_STORAGE_KEY, AdminError, adminCsv, applyAdminAction, createAdminState, databaseInventory, reconcileAdminConfigDraft, restoreAdminState, sameAdminConfig, serializeAdminState } from "../src/admin-model.ts";

const errorCode = (code: string) => (error: unknown) => error instanceof AdminError && error.code === code;

test("unrelated demo checks preserve unsaved settings while a committed save updates the draft", () => {
  const initial = createAdminState();
  const draft = { ...initial.config, retentionDays: 60, queuePaused: true };
  const checked = applyAdminAction(initial, { type: "check" }, true, 1000);
  assert.notEqual(checked.config, initial.config);
  assert.equal(reconcileAdminConfigDraft(draft, initial.config, checked.config), draft);
  assert.equal(sameAdminConfig(draft, checked.config), false);
  const saved = applyAdminAction(checked, { type: "config", config: draft }, true, 2000);
  const afterSave = reconcileAdminConfigDraft(draft, checked.config, saved.config);
  assert.deepEqual(afterSave, draft); assert.equal(sameAdminConfig(afterSave, saved.config), true);
  const discarded = { ...checked.config };
  assert.equal(sameAdminConfig(discarded, checked.config), true);
  assert.equal(checked.config.retentionDays, 30);
});

test("versioned local restore preserves admin workflows across reopening and refuses non-admin access", () => {
  let state = applyAdminAction(createAdminState(), { type: "user", id: "demo-commercial", changes: { role: "researcher" } }, true, 1000);
  state = applyAdminAction(state, { type: "invite", email: "reviewer@ocean.example", role: "viewer", accountType: "research" }, true, 2000);
  state = applyAdminAction(state, { type: "schedule", stage: "export" }, true, 3000);
  const raw = serializeAdminState(state);
  assert.equal(ADMIN_STORAGE_KEY, "ocean-p00-admin-v1");
  assert.deepEqual(restoreAdminState(raw, true), state);
  assert.equal(restoreAdminState(raw, false), undefined);
  const reopened = restoreAdminState(raw, true)!;
  const next = applyAdminAction(reopened, { type: "advance", id: reopened.jobs[0].id }, true, 4000);
  assert.equal(next.jobs[0].status, "running");
  assert.equal(next.sequence, state.sequence + 1);
  assert.equal(new Set(next.audit.map((event) => event.id)).size, next.audit.length);
});

test("restore rejects unknown versions, corrupt records, invalid authority and sequence collisions", () => {
  const stored = JSON.parse(serializeAdminState(createAdminState()));
  assert.equal(restoreAdminState("{broken", true), undefined);
  assert.equal(restoreAdminState(JSON.stringify({ ...stored, version: 2 }), true), undefined);
  assert.equal(restoreAdminState(JSON.stringify({ ...stored, mode: "production" }), true), undefined);
  for (const corrupt of [
    (state: ReturnType<typeof createAdminState>) => { state.jobs[0].authority = "published" as never; },
    (state: ReturnType<typeof createAdminState>) => { state.users[0].status = "suspended"; },
    (state: ReturnType<typeof createAdminState>) => { state.users[1].email = "someone@gmail.com"; },
    (state: ReturnType<typeof createAdminState>) => { state.config.timeoutSeconds = 181; },
    (state: ReturnType<typeof createAdminState>) => { state.jobs.push({ ...state.jobs[0] }); },
    (state: ReturnType<typeof createAdminState>) => { state.audit[0].id = "demo-audit-200"; },
    (state: ReturnType<typeof createAdminState>) => { state.audit[0].createdAt = Infinity; },
    (state: ReturnType<typeof createAdminState>) => { state.jobs[0].logs = null as never; },
  ]) {
    const state = createAdminState(); corrupt(state);
    assert.equal(restoreAdminState(serializeAdminState(state), true), undefined);
  }
  const withExtras = { ...stored, state: { ...stored.state, secret: "unexpected", config: { ...stored.state.config, token: "unexpected" } } };
  const restored = restoreAdminState(JSON.stringify(withExtras), true)!;
  assert.equal("secret" in restored, false); assert.equal("token" in restored.config, false);
});

test("non-admin role cannot mutate or export admin preview records", () => {
  const initial = createAdminState();
  const before = structuredClone(initial);
  assert.throws(() => applyAdminAction(initial, { type: "user", id: "demo-researcher", changes: { role: "admin" } }, false), errorCode("access"));
  assert.throws(() => applyAdminAction(initial, { type: "schedule", stage: "export" }, false), errorCode("access"));
  assert.throws(() => adminCsv(["id"], [{ id: "demo-admin" }], false), errorCode("access"));
  assert.deepEqual(initial, before);
});

test("role and account type remain independent and the demo administrator cannot be locked out", () => {
  const initial = createAdminState();
  const updated = applyAdminAction(initial, { type: "user", id: "demo-commercial", changes: { role: "researcher" } }, true, 1000);
  assert.equal(updated.users.find((user) => user.id === "demo-commercial")!.accountType, "commercial");
  assert.equal(initial.users.find((user) => user.id === "demo-commercial")!.role, "viewer");
  assert.throws(() => applyAdminAction(updated, { type: "user", id: "demo-admin", changes: { status: "suspended" } }, true), errorCode("self"));
  assert.equal(updated.audit[0].target, "demo-commercial");
});

test("demo invitations require synthetic addresses, reject duplicates and can be revoked without sending", () => {
  const initial = createAdminState();
  assert.throws(() => applyAdminAction(initial, { type: "invite", email: "someone@gmail.com", role: "researcher", accountType: "research" }, true, 1000), errorCode("email"));
  const invited = applyAdminAction(initial, { type: "invite", email: "  Team@ocean.example ", role: "researcher", accountType: "research" }, true, 1000);
  assert.equal(invited.invitations[0].email, "team@ocean.example");
  assert.equal(invited.invitations[0].expiresAt, 1000 + 7 * 86400000);
  assert.match(invited.audit[0].detail, /No email sent/);
  assert.throws(() => applyAdminAction(invited, { type: "invite", email: "team@ocean.example", role: "viewer", accountType: "commercial" }, true, 2000), errorCode("duplicate"));
  const revoked = applyAdminAction(invited, { type: "invitation", id: invited.invitations[0].id, status: "revoked" }, true, 3000);
  assert.equal(revoked.invitations[0].status, "revoked");
  assert.equal(invited.invitations[0].status, "pending");
});

test("pause and capacity constrain local jobs, while running work can finish after a pause", () => {
  let state = createAdminState();
  state = applyAdminAction(state, { type: "config", config: { ...state.config, concurrency: 1 } }, true, 1000);
  state = applyAdminAction(state, { type: "schedule", stage: "inventory" }, true, 2000);
  const first = state.jobs[0].id;
  state = applyAdminAction(state, { type: "advance", id: first }, true, 3000);
  state = applyAdminAction(state, { type: "schedule", stage: "validation" }, true, 4000);
  const second = state.jobs[0].id;
  assert.throws(() => applyAdminAction(state, { type: "advance", id: second }, true, 5000), errorCode("capacity"));
  state = applyAdminAction(state, { type: "config", config: { ...state.config, queuePaused: true } }, true, 6000);
  assert.throws(() => applyAdminAction(state, { type: "schedule", stage: "export" }, true), errorCode("paused"));
  assert.throws(() => applyAdminAction(state, { type: "advance", id: second }, true), errorCode("paused"));
  state = applyAdminAction(state, { type: "advance", id: first }, true, 7000);
  assert.equal(state.jobs.find((job) => job.id === first)!.status, "completed");
  assert.equal(state.jobs.find((job) => job.id === first)!.authority, "descriptive");
  assert.match(state.jobs.find((job) => job.id === first)!.logs.at(-1)!, /Scientific approval and publication unchanged/);
});

test("cancelling a simulation retains its snapshot and log, and terminal states cannot be advanced", () => {
  const initial = createAdminState();
  const stopped = applyAdminAction(initial, { type: "cancel", id: "demo-job-03" }, true, 1000);
  const job = stopped.jobs.find((item) => item.id === "demo-job-03")!;
  assert.equal(job.status, "cancelled"); assert.equal(job.snapshotId, "sample-02"); assert.equal(job.logs.length, 2);
  assert.throws(() => applyAdminAction(stopped, { type: "advance", id: job.id }, true), errorCode("terminal"));
  assert.throws(() => applyAdminAction(stopped, { type: "cancel", id: job.id }, true), errorCode("terminal"));
  assert.equal(initial.jobs.find((item) => item.id === job.id)!.status, "queued");
});

test("retention settings cannot remove retained fixture evidence or silently raise execution limits", () => {
  const initial = createAdminState();
  const next = applyAdminAction(initial, { type: "config", config: { ...initial.config, retentionDays: 7 } }, true, 1000);
  assert.equal(next.jobs.length, initial.jobs.length); assert.equal(next.users.length, initial.users.length);
  assert.equal(catalogue.find((node) => node.id === "ctd-2021")!.kind, "dataset");
  assert.throws(() => applyAdminAction(next, { type: "config", config: { ...next.config, maxActions: 13 } }, true), errorCode("config"));
  assert.throws(() => applyAdminAction(next, { type: "config", config: { ...next.config, timeoutSeconds: 181 } }, true), errorCode("config"));
});

test("database inventory counts all local records and feedback triage records an audit without altering evidence", () => {
  const feedback = [{ id: "feedback-01", category: "answer" as const, message: "Check the qualification.", createdAt: 1000, status: "new" as const, runId: "demo-run-01" }];
  const initial = createAdminState();
  const tables = databaseInventory(initial, feedback);
  assert.equal(tables.find((table) => table.id === "catalogue_nodes")!.rows.length, catalogue.length);
  assert.equal(tables.find((table) => table.id === "local_feedback")!.rows[0].id, "feedback-01");
  const next = applyAdminAction(initial, { type: "feedback", id: "feedback-01", status: "reviewing" }, true, 2000);
  assert.deepEqual(next.jobs, initial.jobs);
  assert.equal(feedback[0].status, "new");
  assert.equal(next.audit[0].target, "feedback-01");
});

test("CSV exports identify synthetic scope, preserve all rows and escape spreadsheet formulas and quotes", () => {
  const csv = adminCsv(["id", "message"], [
    { id: 1, message: '=HYPERLINK("https://invalid.example")' },
    { id: 2, message: "  @SUM(1,2)" },
    { id: 3, message: "Coastal data, with \"quotes\"\nand a new line" },
  ], true);
  assert.match(csv, /Local P00 preview/); assert.match(csv, /Synthetic \/ local-only/);
  assert.match(csv, /'=HYPERLINK/); assert.match(csv, /'  @SUM/);
  assert.match(csv, /with ""quotes""/); assert.match(csv, /"3"/);
});
