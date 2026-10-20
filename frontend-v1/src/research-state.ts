/** C18 pure navigation and deliberately volatile, trusted-account-bound private drafts. */
import type { Conversation, Investigation, InvestigationContext, InvestigationMutationIntent } from "./investigation-service.ts";
import type { RunContextBinding, RunMutationIntent } from "./research-run-contract.ts";
import type { AnswerMutationIntent } from "./research-evidence-service.ts";
export const WORKSPACE_TABS = ["context", "results", "experiments", "evidence"] as const;
export type WorkspaceTab = typeof WORKSPACE_TABS[number];
export type ResearchLocation = { investigationId: string | null; conversationId: string | null; workspaceTab: WorkspaceTab; mobilePane: "chat" | "workspace" };
export type ResearchDraftIdentity = { accountId: string; permissionRevision: string };
export type RetainedResearchRun = Readonly<{ id: string; binding: RunContextBinding }>;
export type AnswerSelection = Readonly<{ runId: string | null; jobId: string | null; receiptId: string | null }>;
export const MAX_RETAINED_RUNS_PER_CONVERSATION = 25;
const MAX_RETAINED_CONVERSATIONS = 128;
export class ResearchStateError extends Error { constructor() { super("Research state is invalid"); this.name = "ResearchStateError"; } }
const uuidPattern = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const shaPattern = /^[a-f0-9]{64}$/;
function fail(): never { throw new ResearchStateError(); }
function uuid(value: unknown): string { if (typeof value !== "string" || !uuidPattern.test(value)) return fail(); return value; }
function nullableUuid(value: unknown): string | null { return value === null ? null : uuid(value); }
function plain(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value)); }
function location(value: ResearchLocation): ResearchLocation {
  if (!plain(value) || Object.keys(value).some((key) => !["investigationId", "conversationId", "workspaceTab", "mobilePane"].includes(key)) || !WORKSPACE_TABS.includes(value.workspaceTab) || !["chat", "workspace"].includes(value.mobilePane)) return fail();
  const investigationId = nullableUuid(value.investigationId), conversationId = nullableUuid(value.conversationId);
  if (investigationId === null && conversationId !== null) return fail();
  return { investigationId, conversationId, workspaceTab: value.workspaceTab, mobilePane: value.mobilePane };
}
export function parseResearchLocation(search: string): ResearchLocation {
  if (typeof search !== "string" || search.length > 64 * 1024) return fail();
  const query = new URLSearchParams(search), keys = ["view", "investigation", "conversation", "workspace", "pane"];
  if (keys.some((key) => query.getAll(key).length > 1) || (query.has("view") && query.get("view") !== "research")) return fail();
  return location({ investigationId: query.get("investigation"), conversationId: query.get("conversation"), workspaceTab: (query.get("workspace") ?? "context") as WorkspaceTab, mobilePane: (query.get("pane") ?? "chat") as "chat" | "workspace" });
}
export function researchLocationUrl(input: ResearchLocation): string {
  const value = location(input), query = new URLSearchParams({ view: "research" });
  if (value.investigationId !== null) query.set("investigation", value.investigationId);
  if (value.conversationId !== null) query.set("conversation", value.conversationId);
  if (value.workspaceTab !== "context") query.set("workspace", value.workspaceTab);
  if (value.mobilePane !== "chat") query.set("pane", value.mobilePane);
  return `/?${query.toString()}`;
}
export function updateResearchLocation(current: ResearchLocation, patch: Partial<ResearchLocation>): ResearchLocation {
  if (!plain(patch) || Object.keys(patch).some((key) => !["investigationId", "conversationId", "workspaceTab", "mobilePane"].includes(key))) return fail();
  const before = location(current), merged = { ...before, ...patch };
  if (merged.investigationId !== before.investigationId && !Object.hasOwn(patch, "conversationId")) merged.conversationId = null;
  return location(merged);
}
type DeepReadonly<T> = T extends (infer Item)[] ? readonly DeepReadonly<Item>[] : T extends object ? { readonly [K in keyof T]: DeepReadonly<T[K]> } : T;
function copiedJson(value: unknown, ancestors = new Set<object>(), depth = 0): unknown {
  if (depth > 128) return fail();
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") { if (!value.isWellFormed()) return fail(); return value; }
  if (typeof value === "number") { if (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value))) return fail(); return value; }
  if ((!plain(value) && !Array.isArray(value)) || ancestors.has(value) || Object.getOwnPropertySymbols(value).length || Object.values(Object.getOwnPropertyDescriptors(value)).some((d) => d.get || d.set)) return fail();
  ancestors.add(value);
  const result = Array.isArray(value) ? Array.from(value, (item) => copiedJson(item, ancestors, depth + 1)) : Object.fromEntries(Object.entries(value).map(([key, item]) => [key, copiedJson(item, ancestors, depth + 1)]));
  ancestors.delete(value); return result;
}
function frozen<T>(value: T): DeepReadonly<T> {
  if (value !== null && typeof value === "object") { for (const item of Object.values(value)) frozen(item); Object.freeze(value); }
  return value as DeepReadonly<T>;
}
function textKey(value: unknown, maximum = 512): string { if (typeof value !== "string" || !value || value.length > maximum || !value.isWellFormed() || /[\x00-\x1f\x7f]/.test(value)) return fail(); return value; }
function runBinding(value: unknown): RunContextBinding {
  const binding = copiedJson(value);
  if (!plain(binding) || Object.keys(binding).sort().join(",") !== "conversation_id,investigation_id,payload_sha256,revision_id,snapshot_id") return fail();
  uuid(binding.investigation_id); uuid(binding.conversation_id); uuid(binding.revision_id);
  if (typeof binding.snapshot_id !== "string" || !shaPattern.test(binding.snapshot_id) || typeof binding.payload_sha256 !== "string" || !shaPattern.test(binding.payload_sha256)) return fail();
  return frozen(binding) as RunContextBinding;
}
/** Root retains this instance across temporary verification/unmount; no private value enters storage. */
export class ResearchDraftStore {
  private identity: ResearchDraftIdentity | null = null;
  private readonly drafts = new Map<string, string>();
  private readonly mutations = new Map<string, InvestigationMutationIntent>();
  private readonly runMutations = new Map<string, RunMutationIntent>();
  private readonly retainedRuns = new Map<string, Map<string, RetainedResearchRun>>();
  private readonly answerMutations = new Map<string, AnswerMutationIntent>();
  private readonly answerSelections = new Map<string, AnswerSelection>();
  bind(identity: ResearchDraftIdentity | null): void {
    if (identity === null) { this.clear(); return; }
    if (!plain(identity) || Object.keys(identity).some((key) => !["accountId", "permissionRevision"].includes(key))) return fail();
    const next = { accountId: textKey(identity.accountId), permissionRevision: textKey(identity.permissionRevision) };
    if (this.identity?.accountId !== next.accountId || this.identity.permissionRevision !== next.permissionRevision) { this.drafts.clear(); this.mutations.clear(); this.runMutations.clear(); this.retainedRuns.clear(); this.answerMutations.clear(); this.answerSelections.clear(); }
    this.identity = next;
  }
  private bound(): void { if (this.identity === null) return fail(); }
  private draftKey(investigationId: string, conversationId: string): string { this.bound(); return `${uuid(investigationId)}/${uuid(conversationId)}`; }
  readDraft(investigationId: string, conversationId: string): string { return this.drafts.get(this.draftKey(investigationId, conversationId)) ?? ""; }
  writeDraft(investigationId: string, conversationId: string, value: string): void {
    const key = this.draftKey(investigationId, conversationId);
    if (typeof value !== "string" || !value.isWellFormed() || Array.from(value).length > 64000) return fail();
    if (!value) { this.drafts.delete(key); return; }
    if (!this.drafts.has(key) && this.drafts.size >= 128) return fail(); this.drafts.set(key, value);
  }
  rememberMutation(slot: string, intent: InvestigationMutationIntent): void {
    this.bound(); textKey(slot);
    const copied = copiedJson(intent) as InvestigationMutationIntent;
    if (!plain(copied) || Object.keys(copied).length !== 2 || !Object.hasOwn(copied, "method") || !Object.hasOwn(copied, "request") || !["create", "rename", "archive", "createConversation", "renameConversation", "changeContext", "refresh"].includes(copied.method)) return fail();
    if (new TextEncoder().encode(JSON.stringify(copied.request)).byteLength > 262144 || !plain(copied.request)) return fail(); uuid(copied.request.idempotency_key);
    const existing = this.mutations.get(slot);
    // Uncertain mutations cannot silently acquire a different expected head or key.
    if (existing && JSON.stringify(existing) !== JSON.stringify(copied)) return fail();
    if (!existing && this.mutations.size >= 32) return fail();
    this.mutations.set(slot, frozen(copied) as InvestigationMutationIntent);
  }
  pendingMutation(slot: string): InvestigationMutationIntent | null { this.bound(); textKey(slot); return this.mutations.get(slot) ?? null; }
  forgetMutation(slot: string): void { this.bound(); textKey(slot); this.mutations.delete(slot); }
  rememberRunMutation(slot: string, intent: RunMutationIntent): void {
    this.bound(); textKey(slot); const copied = copiedJson(intent) as RunMutationIntent;
    if (!plain(copied) || !["submit", "cancel", "clarify", "continue"].includes(copied.method) || !plain(copied.request)
      || Object.keys(copied).some(key => !["method", "request", "binding"].includes(key))
      || new TextEncoder().encode(JSON.stringify(copied)).byteLength > 1024 * 1024) return fail();
    uuid(copied.request.idempotency_key);
    if (copied.method === "submit" && (!plain(copied.request.context) || !plain(copied.request.context.binding))) return fail();
    const binding = runBinding(copied.method === "submit" ? copied.request.context.binding : copied.binding);
    if (copied.method !== "submit" && (copied.request.investigation_id !== binding.investigation_id || copied.request.conversation_id !== binding.conversation_id)) return fail();
    const existing = this.runMutations.get(slot);
    if (existing && JSON.stringify(existing) !== JSON.stringify(copied)) return fail();
    if (!existing && this.runMutations.size >= 32) return fail();
    this.runMutations.set(slot, frozen(copied) as RunMutationIntent);
  }
  pendingRunMutation(slot: string): RunMutationIntent | null { this.bound(); textKey(slot); return this.runMutations.get(slot) ?? null; }
  forgetRunMutation(slot: string): void { this.bound(); textKey(slot); this.runMutations.delete(slot); }
  /** Explicit acknowledgements identify off-page runs to reauthorize; cache alone grants no retention. */
  retainRun(id: string, supplied: RunContextBinding): void {
    this.bound(); uuid(id); const binding = runBinding(supplied), key = this.draftKey(binding.investigation_id, binding.conversation_id);
    const retained = this.retainedRuns.get(key) ?? new Map<string, RetainedResearchRun>();
    const previous = retained.get(id);
    if (previous && Object.keys(binding).some(field => previous.binding[field as keyof RunContextBinding] !== binding[field as keyof RunContextBinding])) return fail();
    // Keep the newest successful acknowledgement even when capacity is full.
    retained.delete(id); retained.set(id, frozen({ id, binding }));
    while (retained.size > MAX_RETAINED_RUNS_PER_CONVERSATION) retained.delete(retained.keys().next().value!);
    this.retainedRuns.delete(key); this.retainedRuns.set(key, retained);
    while (this.retainedRuns.size > MAX_RETAINED_CONVERSATIONS) this.retainedRuns.delete(this.retainedRuns.keys().next().value!);
  }
  retainedRunBindings(investigationId: string, conversationId: string): readonly RetainedResearchRun[] {
    return Object.freeze([...(this.retainedRuns.get(this.draftKey(investigationId, conversationId))?.values() ?? [])]);
  }
  forgetRetainedRun(investigationId: string, conversationId: string, id: string): void {
    uuid(id); const key = this.draftKey(investigationId, conversationId), retained = this.retainedRuns.get(key);
    retained?.delete(id); if (retained?.size === 0) this.retainedRuns.delete(key);
  }
  rememberAnswerMutation(slot: string, intent: AnswerMutationIntent): void {
    this.bound(); textKey(slot); const copied = copiedJson(intent) as AnswerMutationIntent;
    if (!plain(copied) || Object.keys(copied).sort().join(",") !== "binding,method,request" || !["submit", "cancel"].includes(copied.method) || !plain(copied.request)
      || new TextEncoder().encode(JSON.stringify(copied)).byteLength > 65536) return fail();
    const binding = runBinding(copied.binding); uuid(copied.request.idempotency_key); uuid(copied.request.run_id);
    if (copied.request.investigation_id !== binding.investigation_id || copied.request.conversation_id !== binding.conversation_id) return fail();
    if (copied.method === "submit") {
      if (Object.keys(copied.request).sort().join(",") !== ["conversation_id", "idempotency_key", "input_version", "investigation_id", "locale", "run_id"].filter(key => key !== "locale" || Object.hasOwn(copied.request, key)).sort().join(",")
        || !Number.isSafeInteger(copied.request.input_version) || copied.request.input_version < 1 || copied.request.locale !== undefined && !["en", "ja"].includes(copied.request.locale)) return fail();
    } else { if (Object.keys(copied.request).sort().join(",") !== "conversation_id,idempotency_key,investigation_id,job_id,run_id") return fail(); uuid(copied.request.job_id); }
    const previous = this.answerMutations.get(slot); if (previous && JSON.stringify(previous) !== JSON.stringify(copied)) return fail();
    if (!previous && this.answerMutations.size >= 32) return fail(); this.answerMutations.set(slot, frozen(copied));
  }
  pendingAnswerMutation(slot: string): AnswerMutationIntent | null { this.bound(); textKey(slot); return this.answerMutations.get(slot) ?? null; }
  forgetAnswerMutation(slot: string): void { this.bound(); textKey(slot); this.answerMutations.delete(slot); }
  answerSelection(investigationId: string, conversationId: string): AnswerSelection {
    return this.answerSelections.get(this.draftKey(investigationId, conversationId)) ?? { runId: null, jobId: null, receiptId: null };
  }
  selectAnswer(investigationId: string, conversationId: string, supplied: AnswerSelection): void {
    const key = this.draftKey(investigationId, conversationId), value = copiedJson(supplied) as AnswerSelection;
    if (!plain(value) || Object.keys(value).sort().join(",") !== "jobId,receiptId,runId") return fail();
    nullableUuid(value.runId); nullableUuid(value.jobId);
    if (value.receiptId !== null && (typeof value.receiptId !== "string" || !/^c21:receipt:[a-f0-9]{64}$/.test(value.receiptId)) || value.runId === null && (value.jobId !== null || value.receiptId !== null)) return fail();
    this.answerSelections.delete(key); this.answerSelections.set(key, frozen(value));
    while (this.answerSelections.size > 128) this.answerSelections.delete(this.answerSelections.keys().next().value!);
  }
  clear(): void { this.drafts.clear(); this.mutations.clear(); this.runMutations.clear(); this.retainedRuns.clear(); this.answerMutations.clear(); this.answerSelections.clear(); this.identity = null; }
}
export type SubmittedResearchBinding = {
  investigation_id: string; conversation_id: string; revision_id: string; snapshot_id: string;
  payload_sha256: string; context: InvestigationContext;
};
/** This is a presentation binding. C20 must freshly authorize/freeze it at actual submission. */
export function freezeSubmittedBinding(input: { investigation: Investigation; conversation: Conversation; context: InvestigationContext }): DeepReadonly<SubmittedResearchBinding> {
  const i = uuid(input.investigation.id), c = uuid(input.conversation.id), revision = uuid(input.context.id);
  if (input.conversation.investigation_id !== i || input.context.investigation_id !== i || !shaPattern.test(input.context.snapshot_id) || !shaPattern.test(input.context.payload_sha256)) return fail();
  return frozen({ investigation_id: i, conversation_id: c, revision_id: revision, snapshot_id: input.context.snapshot_id, payload_sha256: input.context.payload_sha256, context: copiedJson(input.context) as InvestigationContext });
}
