import { catalogue } from "./fixtures.ts";
import type { FeedbackEntry } from "./feedback-model.ts";
import { safeCell } from "./exports.ts";

export type AdminRole = "viewer" | "researcher" | "admin";
export type AccountType = "research" | "commercial" | "internal";
export type AdminSection = "overview" | "users" | "feedback" | "database" | "catalogue" | "system" | "audit";
export type DemoUser = { id: string; name: string; email: string; role: AdminRole; accountType: AccountType; status: "active" | "suspended"; lastSeen: string };
export type DemoInvitation = { id: string; email: string; role: AdminRole; accountType: AccountType; status: "pending" | "revoked"; expiresAt: number };
export type JobStage = "inventory" | "validation" | "catalogue" | "export";
export type DemoJob = { id: string; stage: JobStage; status: "queued" | "running" | "completed" | "cancelled" | "error"; snapshotId: string; createdAt: number; logs: string[]; authority: "descriptive" };
export type AdminAudit = { id: string; createdAt: number; action: string; target: string; detail: string };
export type AdminConfig = { queuePaused: boolean; concurrency: number; retentionDays: number; timeoutSeconds: number; maxActions: number };
export type AdminState = { users: DemoUser[]; invitations: DemoInvitation[]; jobs: DemoJob[]; audit: AdminAudit[]; config: AdminConfig; sequence: number };
export const ADMIN_STORAGE_KEY = "ocean-p00-admin-v1";
export function sameAdminConfig(left: AdminConfig, right: AdminConfig): boolean {
  return left.queuePaused === right.queuePaused && left.concurrency === right.concurrency && left.retentionDays === right.retentionDays && left.timeoutSeconds === right.timeoutSeconds && left.maxActions === right.maxActions;
}
export function reconcileAdminConfigDraft(draft: AdminConfig, previousCommitted: AdminConfig, nextCommitted: AdminConfig): AdminConfig {
  return sameAdminConfig(previousCommitted, nextCommitted) ? draft : { ...nextCommitted };
}
export type AdminAction =
  | { type: "user"; id: string; changes: Partial<Pick<DemoUser, "role" | "accountType" | "status">> }
  | { type: "invite"; email: string; role: AdminRole; accountType: AccountType }
  | { type: "invitation"; id: string; status: DemoInvitation["status"] }
  | { type: "schedule"; stage: JobStage }
  | { type: "advance"; id: string }
  | { type: "cancel"; id: string }
  | { type: "config"; config: AdminConfig }
  | { type: "feedback"; id: string; status: FeedbackEntry["status"] }
  | { type: "check" };
export type AdminErrorCode = "access" | "self" | "missing" | "email" | "duplicate" | "paused" | "capacity" | "terminal" | "config";
export class AdminError extends Error {
  readonly code: AdminErrorCode;
  constructor(code: AdminErrorCode) { super(code); this.code = code; }
}

const roles: AdminRole[] = ["viewer", "researcher", "admin"];
const accounts: AccountType[] = ["research", "commercial", "internal"];
const stages: JobStage[] = ["inventory", "validation", "catalogue", "export"];
const fixtureTime = Date.UTC(2026, 9, 13, 0, 0);
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const string = (value: unknown, max = 10000): value is string => typeof value === "string" && value.length <= max;
const integer = (value: unknown, min: number, max: number): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
const timestamp = (value: unknown) => integer(value, 0, 8640000000000000);
const demoEmail = (value: unknown): value is string => string(value, 254) && /^[^\s@]+@[^\s@]+\.(example|test)$/.test(value);
const demoId = (value: unknown): value is string => string(value, 100) && /^demo-[a-zA-Z0-9-]+$/.test(value);
const oneOf = (value: unknown, allowed: readonly string[]) => typeof value === "string" && allowed.includes(value);
function validConfig(value: unknown): value is AdminConfig {
  return record(value) && typeof value.queuePaused === "boolean" && integer(value.concurrency, 1, 4) && integer(value.retentionDays, 7, 365) && integer(value.timeoutSeconds, 30, 180) && integer(value.maxActions, 1, 12);
}
function rows(value: unknown, valid: (row: Record<string, unknown>) => boolean): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.length <= 20000 && value.every((row) => record(row) && valid(row)) && new Set(value.map((row) => row.id)).size === value.length;
}

export function serializeAdminState(state: AdminState): string {
  return JSON.stringify({ version: 1, mode: "local-simulation", state });
}

export function restoreAdminState(raw: string | null, canAdmin: boolean): AdminState | undefined {
  if (!canAdmin || !raw || raw.length > 5000000) return undefined;
  try {
    const stored: unknown = JSON.parse(raw);
    if (!record(stored) || stored.version !== 1 || stored.mode !== "local-simulation" || !record(stored.state)) return undefined;
    const value = stored.state;
    if (!integer(value.sequence, 10, Number.MAX_SAFE_INTEGER - 1) || !validConfig(value.config)) return undefined;
    if (!rows(value.users, (user) => demoId(user.id) && string(user.name, 200) && demoEmail(user.email) && oneOf(user.role, roles) && oneOf(user.accountType, accounts) && oneOf(user.status, ["active", "suspended"]) && string(user.lastSeen, 10) && /^\d{4}-\d{2}-\d{2}$/.test(user.lastSeen))) return undefined;
    if (!rows(value.invitations, (invite) => demoId(invite.id) && demoEmail(invite.email) && oneOf(invite.role, roles) && oneOf(invite.accountType, accounts) && oneOf(invite.status, ["pending", "revoked"]) && timestamp(invite.expiresAt))) return undefined;
    if (!rows(value.jobs, (job) => demoId(job.id) && oneOf(job.stage, stages) && oneOf(job.status, ["queued", "running", "completed", "cancelled", "error"]) && oneOf(job.snapshotId, ["sample-01", "sample-02"]) && timestamp(job.createdAt) && job.authority === "descriptive" && Array.isArray(job.logs) && job.logs.length <= 1000 && job.logs.every((line) => string(line)))) return undefined;
    if (!rows(value.audit, (event) => demoId(event.id) && timestamp(event.createdAt) && string(event.action, 100) && string(event.target, 200) && string(event.detail))) return undefined;
    const administrator = value.users.find((user) => user.id === "demo-admin");
    if (!administrator || administrator.role !== "admin" || administrator.status !== "active" || administrator.accountType !== "internal") return undefined;
    const generatedIds = [...value.invitations, ...value.jobs, ...value.audit].map((row) => Number(String(row.id).split("-").at(-1))).filter(Number.isFinite);
    if (generatedIds.some((id) => id > (value.sequence as number))) return undefined;
    // Explicit fields keep unknown persisted properties outside the prototype contract.
    const typed = value as unknown as AdminState;
    return {
      sequence: typed.sequence,
      config: { queuePaused: typed.config.queuePaused, concurrency: typed.config.concurrency, retentionDays: typed.config.retentionDays, timeoutSeconds: typed.config.timeoutSeconds, maxActions: typed.config.maxActions },
      users: typed.users.map(({ id, name, email, role, accountType, status, lastSeen }) => ({ id, name, email, role, accountType, status, lastSeen })),
      invitations: typed.invitations.map(({ id, email, role, accountType, status, expiresAt }) => ({ id, email, role, accountType, status, expiresAt })),
      jobs: typed.jobs.map(({ id, stage, status, snapshotId, createdAt, logs, authority }) => ({ id, stage, status, snapshotId, createdAt, logs: [...logs], authority })),
      audit: typed.audit.map(({ id, createdAt, action, target, detail }) => ({ id, createdAt, action, target, detail })),
    };
  } catch { return undefined; }
}

export function createAdminState(): AdminState {
  return {
    sequence: 10,
    users: [
      { id: "demo-admin", name: "Preview administrator", email: "admin@ocean.example", role: "admin", accountType: "internal", status: "active", lastSeen: "2026-10-13" },
      { id: "demo-researcher", name: "Coastal research team", email: "coast@ocean.example", role: "researcher", accountType: "research", status: "active", lastSeen: "2026-10-12" },
      { id: "demo-viewer", name: "Research reviewer", email: "review@ocean.example", role: "viewer", accountType: "research", status: "active", lastSeen: "2026-10-11" },
      { id: "demo-commercial", name: "Commercial partner", email: "partner@ocean.example", role: "viewer", accountType: "commercial", status: "active", lastSeen: "2026-10-10" },
      { id: "demo-suspended", name: "Archived demo account", email: "archive@ocean.example", role: "researcher", accountType: "research", status: "suspended", lastSeen: "2026-10-01" },
    ],
    invitations: [{ id: "demo-invite-01", email: "new-team@ocean.example", role: "researcher", accountType: "research", status: "pending", expiresAt: fixtureTime + 7 * 86400000 }],
    jobs: [
      { id: "demo-job-03", stage: "catalogue", status: "queued", snapshotId: "sample-02", createdAt: fixtureTime, logs: ["Synthetic catalogue refresh queued."], authority: "descriptive" },
      { id: "demo-job-02", stage: "validation", status: "error", snapshotId: "sample-02", createdAt: fixtureTime - 600000, logs: ["Synthetic validation example started.", "Fixture qualification missing: ctd-2021. No publication changed."], authority: "descriptive" },
      { id: "demo-job-01", stage: "inventory", status: "completed", snapshotId: "sample-02", createdAt: fixtureTime - 3600000, logs: ["Synthetic inventory example started.", "Fixture records counted. Physical sampling units remain source-specific."], authority: "descriptive" },
    ],
    audit: [
      { id: "demo-audit-03", createdAt: fixtureTime, action: "job.queued", target: "demo-job-03", detail: "Synthetic fixture event." },
      { id: "demo-audit-02", createdAt: fixtureTime - 600000, action: "qualification.missing", target: "ctd-2021", detail: "Excluded from sample-02; retained in sample-01." },
      { id: "demo-audit-01", createdAt: fixtureTime - 3600000, action: "snapshot.loaded", target: "sample-02", detail: "Synthetic fixture event; no production access." },
    ],
    config: { queuePaused: false, concurrency: 2, retentionDays: 30, timeoutSeconds: 180, maxActions: 12 },
  };
}

export function applyAdminAction(state: AdminState, action: AdminAction, canAdmin: boolean, now = Date.now()): AdminState {
  if (!canAdmin) throw new AdminError("access");
  const next = structuredClone(state);
  const sequence = ++next.sequence;
  let target = "preview";
  let detail = "Local simulation only.";
  switch (action.type) {
    case "user": {
      const user = next.users.find((item) => item.id === action.id);
      if (!user) throw new AdminError("missing");
      if (user.id === "demo-admin") throw new AdminError("self");
      if ((action.changes.role && !roles.includes(action.changes.role)) || (action.changes.accountType && !accounts.includes(action.changes.accountType)) || (action.changes.status && !["active", "suspended"].includes(action.changes.status))) throw new AdminError("config");
      Object.assign(user, action.changes);
      target = user.id; detail = JSON.stringify(action.changes); break;
    }
    case "invite": {
      const email = action.email.trim().toLowerCase();
      if (!demoEmail(email)) throw new AdminError("email");
      if (!roles.includes(action.role) || !accounts.includes(action.accountType)) throw new AdminError("config");
      if (next.users.some((item) => item.email === email) || next.invitations.some((item) => item.email === email && item.status === "pending" && item.expiresAt > now)) throw new AdminError("duplicate");
      target = `demo-invite-${sequence}`;
      next.invitations.unshift({ id: target, email, role: action.role, accountType: action.accountType, status: "pending", expiresAt: now + 7 * 86400000 });
      detail = "Demo invitation created. No email sent."; break;
    }
    case "invitation": {
      const invitation = next.invitations.find((item) => item.id === action.id);
      if (!invitation) throw new AdminError("missing");
      invitation.status = action.status; target = invitation.id; detail = action.status; break;
    }
    case "schedule": {
      if (next.config.queuePaused) throw new AdminError("paused");
      if (!stages.includes(action.stage)) throw new AdminError("config");
      target = `demo-job-${sequence}`;
      next.jobs.unshift({ id: target, stage: action.stage, status: "queued", snapshotId: "sample-02", createdAt: now, logs: ["Local simulation queued. No worker started."], authority: "descriptive" });
      detail = action.stage; break;
    }
    case "advance": {
      const job = next.jobs.find((item) => item.id === action.id);
      if (!job) throw new AdminError("missing");
      if (!["queued", "running"].includes(job.status)) throw new AdminError("terminal");
      if (job.status === "queued") {
        if (next.config.queuePaused) throw new AdminError("paused");
        if (next.jobs.filter((item) => item.status === "running").length >= next.config.concurrency) throw new AdminError("capacity");
        job.status = "running";
        job.logs.push("Manually advanced to running. No analysis executed.");
      } else {
        job.status = "completed";
        job.logs.push("Local simulation completed. Scientific approval and publication unchanged.");
      }
      target = job.id; detail = job.status; break;
    }
    case "cancel": {
      const job = next.jobs.find((item) => item.id === action.id);
      if (!job) throw new AdminError("missing");
      if (!["queued", "running"].includes(job.status)) throw new AdminError("terminal");
      job.status = "cancelled"; job.logs.push("Local simulation cancelled; no external worker exists.");
      target = job.id; detail = job.status; break;
    }
    case "config": {
      const value = action.config;
      if (!validConfig(value)) throw new AdminError("config");
      next.config = { ...value }; detail = "Preview settings updated. No storage policy or backend changed."; break;
    }
    case "feedback": {
      if (!["new", "reviewing", "resolved"].includes(action.status)) throw new AdminError("config");
      target = action.id; detail = `Local feedback status: ${action.status}`; break;
    }
    case "check": detail = "Synthetic health inspection recorded; backend and model remain disconnected."; break;
  }
  next.audit.unshift({ id: `demo-audit-${sequence}`, createdAt: now, action: `preview.${action.type}`, target, detail });
  return next;
}

export type DatabaseInventory = { id: string; columns: string[]; rows: Record<string, string | number | boolean>[] };
export function databaseInventory(state: AdminState, feedback: FeedbackEntry[]): DatabaseInventory[] {
  return [
    { id: "catalogue_nodes", columns: ["id", "root", "kind", "source"], rows: catalogue.map((node) => ({ id: node.id, root: node.root, kind: node.kind, source: node.source ?? "—" })) },
    { id: "demo_users", columns: ["id", "email", "role", "account_type", "status"], rows: state.users.map((user) => ({ id: user.id, email: user.email, role: user.role, account_type: user.accountType, status: user.status })) },
    { id: "demo_invitations", columns: ["id", "email", "role", "status"], rows: state.invitations.map((invite) => ({ id: invite.id, email: invite.email, role: invite.role, status: invite.status })) },
    { id: "local_feedback", columns: ["id", "category", "status", "message"], rows: feedback.map((entry) => ({ id: entry.id, category: entry.category, status: entry.status, message: entry.message })) },
    { id: "demo_audit", columns: ["id", "action", "target", "detail"], rows: state.audit.map((event) => ({ id: event.id, action: event.action, target: event.target, detail: event.detail })) },
  ];
}

export function adminCsv(columns: string[], rows: Record<string, unknown>[], canAdmin: boolean): string {
  if (!canAdmin) throw new AdminError("access");
  return [["Local P00 preview", "Synthetic / local-only"].map(safeCell).join(","), columns.map(safeCell).join(","), ...rows.map((row) => columns.map((column) => safeCell(row[column])).join(","))].join("\r\n");
}
