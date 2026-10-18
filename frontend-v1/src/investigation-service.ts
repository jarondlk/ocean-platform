/** C18 transport for the actual owner-private C17 API. No ambient identity or fixtures. */
import { parseCatalogueContractModel } from "./catalogue-contract.ts";
import type { EvidenceScope } from "./catalogue-contract.ts";
export type { EvidenceScope } from "./catalogue-contract.ts";

export type ContextReference = { kind: "catalogue" | "artifact"; id: string; snapshot_id: string };
export type ContextResolution = { reference: ContextReference; status: "available" | "unavailable" | "artifact_capability_unavailable" };
export type Investigation = {
  id: string; name: string; metadata_version: number; status: "preparing" | "active" | "archived" | "retired";
  head_revision_id: string | null; predecessor_investigation_id: string | null; predecessor_revision_id: string | null;
  legal_hold: boolean; created_at: string; updated_at: string;
};
export type Conversation = {
  id: string; investigation_id: string; name: string; metadata_version: number;
  created_at: string; updated_at: string; history_status: "unavailable_until_c20_c21";
};
export type InvestigationContext = {
  id: string; investigation_id: string; sequence: number; predecessor_revision_id: string | null;
  snapshot_id: string; payload_sha256: string; scope: EvidenceScope; attachments: ContextReference[]; pins: ContextReference[];
  resolution: ContextResolution[]; refresh_unresolved: ContextResolution[]; created_by_user_id: string; created_at: string;
  artifact_capability: "configured" | "unavailable";
};
export type InvestigationOperation = {
  id: string; investigation_id: string;
  kind: "create" | "context/change" | "refresh" | "rename" | "archive" | "conversations/create" | "conversations/rename";
  state: "prepared" | "committed" | "conflict" | "unavailable" | "uncertain";
  error_code: string | null; candidate_revision_id: string | null;
};
export type Operation = InvestigationOperation;
type Version = { version: "investigations-v1" };
export type InvestigationBundle = Version & { investigation: Investigation; context: InvestigationContext; legacy_history_import: "unavailable" };
export type InvestigationMutationBundle = Version & { operation: InvestigationOperation; investigation: Investigation; context: InvestigationContext };
export type InvestigationMetadataResult = Version & { operation: InvestigationOperation; investigation: Investigation };
export type ConversationResult = Version & { conversation: Conversation };
export type ConversationMutationResult = ConversationResult & { operation: InvestigationOperation };
export type ContextResult = Version & { context: InvestigationContext };
export type OperationResult = Version & { operation: InvestigationOperation };
export type OperationRetryResult = OperationResult & { investigation?: Investigation; context?: InvestigationContext };
export type InvestigationPage = Version & { items: Investigation[]; next_after_id: string | null };
export type ConversationPage = Version & { items: Conversation[]; next_after_id: string | null };

export type InvestigationCreateRequest = { name: string; snapshot_id: string; scope: EvidenceScope; idempotency_key: string };
export type InvestigationListRequest = { limit?: number; after_id?: string | null };
export type InvestigationGetRequest = { investigation_id: string };
export type InvestigationRenameRequest = InvestigationGetRequest & { name: string; expected_version: number; idempotency_key: string };
export type InvestigationArchiveRequest = InvestigationGetRequest & { archived?: boolean; expected_version: number; idempotency_key: string };
export type ConversationCreateRequest = InvestigationGetRequest & { name: string; idempotency_key: string };
export type ConversationListRequest = InvestigationGetRequest & InvestigationListRequest;
export type ConversationGetRequest = InvestigationGetRequest & { conversation_id: string };
export type ConversationRenameRequest = ConversationGetRequest & { name: string; expected_version: number; idempotency_key: string };
export type ContextGetRequest = InvestigationGetRequest & { revision_id?: string | null };
export type ContextChange = { op: "attach" | "detach" | "pin" | "unpin"; reference: ContextReference } | { op: "scope"; scope: EvidenceScope };
export type ContextChangeRequest = InvestigationGetRequest & { expected_revision_id: string; idempotency_key: string; change: ContextChange };
export type InvestigationRefreshRequest = InvestigationGetRequest & { expected_revision_id: string; target_snapshot_id: string; name: string; idempotency_key: string };
export type OperationGetRequest = { operation_id: string };
export type OperationRetryRequest = OperationGetRequest;

export type InvestigationRequests = {
  create: InvestigationCreateRequest; list: InvestigationListRequest; get: InvestigationGetRequest;
  rename: InvestigationRenameRequest; archive: InvestigationArchiveRequest; createConversation: ConversationCreateRequest;
  listConversations: ConversationListRequest; getConversation: ConversationGetRequest; renameConversation: ConversationRenameRequest;
  getContext: ContextGetRequest; changeContext: ContextChangeRequest; refresh: InvestigationRefreshRequest;
  getOperation: OperationGetRequest; retryOperation: OperationRetryRequest;
};
export type InvestigationResponses = {
  create: InvestigationMutationBundle; list: InvestigationPage; get: InvestigationBundle;
  rename: InvestigationMetadataResult; archive: InvestigationMetadataResult; createConversation: ConversationMutationResult;
  listConversations: ConversationPage; getConversation: ConversationResult; renameConversation: ConversationMutationResult;
  getContext: ContextResult; changeContext: InvestigationMutationBundle; refresh: InvestigationMutationBundle;
  getOperation: OperationResult; retryOperation: OperationRetryResult;
};
export type InvestigationClient = { [K in keyof InvestigationRequests]: (request: InvestigationRequests[K], signal?: AbortSignal) => Promise<InvestigationResponses[K]> };
export type InvestigationMutationMethod = "create" | "rename" | "archive" | "createConversation" | "renameConversation" | "changeContext" | "refresh";
export type InvestigationMutationIntent = { [K in InvestigationMutationMethod]: { method: K; request: InvestigationRequests[K] } }[InvestigationMutationMethod];
export type InvestigationMutationResponse = InvestigationMutationBundle | InvestigationMetadataResult | ConversationMutationResult;
/** Replays the same immutable request/key; callers must explicitly replace a conflicted intent. */
export function executeInvestigationMutation(client: InvestigationClient, intent: InvestigationMutationIntent, signal?: AbortSignal): Promise<InvestigationMutationResponse> {
  switch (intent.method) {
    case "create": return client.create(intent.request, signal);
    case "rename": return client.rename(intent.request, signal);
    case "archive": return client.archive(intent.request, signal);
    case "createConversation": return client.createConversation(intent.request, signal);
    case "renameConversation": return client.renameConversation(intent.request, signal);
    case "changeContext": return client.changeContext(intent.request, signal);
    case "refresh": return client.refresh(intent.request, signal);
  }
}
export class InvestigationClientError extends Error {
  readonly code: string; readonly status_code: number;
  constructor(code: string, message: string, status_code = 503) { super(message); this.name = "InvestigationClientError"; this.code = code; this.status_code = status_code; }
}
export const MAX_INVESTIGATION_RESPONSE_BYTES = 2 * 1024 * 1024;
export const MAX_INVESTIGATION_REQUEST_BYTES = 262144;
const uuidPattern = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const shaPattern = /^[a-f0-9]{64}$/;
const identifierPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
function invalid(): never { throw new InvestigationClientError("invalid_response", "Investigation response is invalid"); }
function badRequest(): never { throw new InvestigationClientError("invalid_request", "Investigation request is invalid", 422); }
function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value)); }
function shape(value: unknown, keys: readonly string[], required: readonly string[] = keys): Record<string, unknown> {
  if (!object(value) || Object.keys(value).some((key) => !keys.includes(key)) || required.some((key) => !Object.hasOwn(value, key))) return invalid();
  return value;
}
function string(value: unknown): string {
  if (typeof value !== "string" || !value.isWellFormed()) return invalid(); return value;
}
function uuid(value: unknown): string { const s = string(value); if (!uuidPattern.test(s)) return invalid(); return s; }
function sha(value: unknown): string { const s = string(value); if (!shaPattern.test(s)) return invalid(); return s; }
function identifier(value: unknown): string { const s = string(value); if (!identifierPattern.test(s)) return invalid(); return s; }
function name(value: unknown): string { const s = string(value); if (!s || Array.from(s).length > 200 || s !== s.trim() || /[\x00-\x1f\x7f]/.test(s)) return invalid(); return s; }
function integer(value: unknown, min = 1, max = Number.MAX_SAFE_INTEGER): number { if (typeof value !== "number" || !Number.isSafeInteger(value) || value < min || value > max) return invalid(); return value; }
function nullableUuid(value: unknown): string | null { return value === null ? null : uuid(value); }
function timestamp(value: unknown): string { const s = string(value); if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$/.test(s) || !Number.isFinite(Date.parse(s))) return invalid(); return s; }
function choice<T extends string>(value: unknown, values: readonly T[]): T { if (typeof value !== "string" || !values.includes(value as T)) return invalid(); return value as T; }
function finiteJson(value: unknown, ancestors = new Set<object>(), depth = 0): unknown {
  if (depth > 128) return invalid();
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") return string(value);
  if (typeof value === "number") { if (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value))) return invalid(); return value; }
  if ((!object(value) && !Array.isArray(value)) || ancestors.has(value)) return invalid();
  ancestors.add(value);
  // Requests must be ordinary finite JSON, including no getters, sparse arrays or symbol fields.
  if (Object.getOwnPropertySymbols(value).length || Object.values(Object.getOwnPropertyDescriptors(value)).some((d) => d.get || d.set)) return invalid();
  const result = Array.isArray(value) ? Array.from(value, (item) => finiteJson(item, ancestors, depth + 1)) : Object.fromEntries(Object.entries(value).map(([key, item]) => [string(key), finiteJson(item, ancestors, depth + 1)]));
  ancestors.delete(value); return result;
}
function equal(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) && Array.isArray(right)) return left.length === right.length && left.every((item, i) => equal(item, right[i]));
  if (object(left) && object(right)) return Object.keys(left).length === Object.keys(right).length && Object.keys(left).every((key) => Object.hasOwn(right, key) && equal(left[key], right[key]));
  return false;
}
function reference(raw: unknown): ContextReference { const p = shape(raw, ["kind", "id", "snapshot_id"]); return { kind: choice(p.kind, ["catalogue", "artifact"]), id: identifier(p.id), snapshot_id: sha(p.snapshot_id) }; }
const referenceKey = (r: ContextReference) => JSON.stringify([r.kind, r.id, r.snapshot_id]);
function references(raw: unknown): ContextReference[] {
  if (!Array.isArray(raw) || raw.length > 256) return invalid(); const items = raw.map(reference);
  if (new Set(items.map(referenceKey)).size !== items.length) return invalid(); return items;
}
function resolution(raw: unknown): ContextResolution {
  const p = shape(raw, ["reference", "status"]); const ref = reference(p.reference), status = choice(p.status, ["available", "unavailable", "artifact_capability_unavailable"]);
  if (status === "artifact_capability_unavailable" && ref.kind !== "artifact") return invalid(); return { reference: ref, status };
}
function investigation(raw: unknown): Investigation {
  const p = shape(raw, ["id", "name", "metadata_version", "status", "head_revision_id", "predecessor_investigation_id", "predecessor_revision_id", "legal_hold", "created_at", "updated_at"]);
  if (typeof p.legal_hold !== "boolean") return invalid();
  const result: Investigation = { id: uuid(p.id), name: name(p.name), metadata_version: integer(p.metadata_version), status: choice(p.status, ["preparing", "active", "archived", "retired"]), head_revision_id: nullableUuid(p.head_revision_id), predecessor_investigation_id: nullableUuid(p.predecessor_investigation_id), predecessor_revision_id: nullableUuid(p.predecessor_revision_id), legal_hold: p.legal_hold, created_at: timestamp(p.created_at), updated_at: timestamp(p.updated_at) };
  if ((result.predecessor_investigation_id === null) !== (result.predecessor_revision_id === null) || result.predecessor_investigation_id === result.id || (result.status !== "preparing" && result.head_revision_id === null)) return invalid(); return result;
}
function conversation(raw: unknown): Conversation {
  const p = shape(raw, ["id", "investigation_id", "name", "metadata_version", "created_at", "updated_at", "history_status"]);
  return { id: uuid(p.id), investigation_id: uuid(p.investigation_id), name: name(p.name), metadata_version: integer(p.metadata_version), created_at: timestamp(p.created_at), updated_at: timestamp(p.updated_at), history_status: choice(p.history_status, ["unavailable_until_c20_c21"]) };
}
async function context(raw: unknown): Promise<InvestigationContext> {
  const p = shape(raw, ["id", "investigation_id", "sequence", "predecessor_revision_id", "snapshot_id", "payload_sha256", "scope", "attachments", "pins", "resolution", "refresh_unresolved", "created_by_user_id", "created_at", "artifact_capability"]);
  const attachments = references(p.attachments), pins = references(p.pins);
  if (!Array.isArray(p.resolution) || p.resolution.length !== attachments.length + pins.length || !Array.isArray(p.refresh_unresolved) || p.refresh_unresolved.length > 512) return invalid();
  const resolved = p.resolution.map(resolution), unresolved = p.refresh_unresolved.map(resolution), all = [...attachments, ...pins];
  if (resolved.some((r, i) => !equal(r.reference, all[i])) || unresolved.some((r) => r.status === "available")) return invalid();
  // refresh_unresolved is an immutable record of branch creation, not the current policy result.
  // C17 excludes optional null scope fields in its canonical stored payload. Validate
  // without expanding defaults, so the DTO remains the exact retained wire value.
  await parseCatalogueContractModel("EvidenceScope", p.scope);
  const result: InvestigationContext = { id: uuid(p.id), investigation_id: uuid(p.investigation_id), sequence: integer(p.sequence), predecessor_revision_id: nullableUuid(p.predecessor_revision_id), snapshot_id: sha(p.snapshot_id), payload_sha256: sha(p.payload_sha256), scope: p.scope as EvidenceScope, attachments, pins, resolution: resolved, refresh_unresolved: unresolved, created_by_user_id: uuid(p.created_by_user_id), created_at: timestamp(p.created_at), artifact_capability: choice(p.artifact_capability, ["configured", "unavailable"]) };
  if ((result.sequence === 1) !== (result.predecessor_revision_id === null) || all.some((r) => r.kind === "catalogue" && r.snapshot_id !== result.snapshot_id) || (result.artifact_capability === "configured" && resolved.some((r) => r.status === "artifact_capability_unavailable"))) return invalid(); return result;
}
function operation(raw: unknown): InvestigationOperation {
  const p = shape(raw, ["id", "investigation_id", "kind", "state", "error_code", "candidate_revision_id"]);
  return { id: uuid(p.id), investigation_id: uuid(p.investigation_id), kind: choice(p.kind, ["create", "context/change", "refresh", "rename", "archive", "conversations/create", "conversations/rename"]), state: choice(p.state, ["prepared", "committed", "conflict", "unavailable", "uncertain"]), error_code: p.error_code === null ? null : identifier(p.error_code), candidate_revision_id: nullableUuid(p.candidate_revision_id) };
}
const endpoints = { create: "create", list: "list", get: "get", rename: "rename", archive: "archive", createConversation: "conversations/create", listConversations: "conversations/list", getConversation: "conversations/get", renameConversation: "conversations/rename", getContext: "context/get", changeContext: "context/change", refresh: "refresh", getOperation: "operations/get", retryOperation: "operations/retry" } as const;
type Method = keyof typeof endpoints;
const requestKeys: Record<Method, string[]> = {
  create: ["name", "snapshot_id", "scope", "idempotency_key"], list: ["limit", "after_id"], get: ["investigation_id"], rename: ["investigation_id", "name", "expected_version", "idempotency_key"], archive: ["investigation_id", "archived", "expected_version", "idempotency_key"],
  createConversation: ["investigation_id", "name", "idempotency_key"], listConversations: ["investigation_id", "limit", "after_id"], getConversation: ["investigation_id", "conversation_id"], renameConversation: ["investigation_id", "conversation_id", "name", "expected_version", "idempotency_key"], getContext: ["investigation_id", "revision_id"], changeContext: ["investigation_id", "expected_revision_id", "idempotency_key", "change"], refresh: ["investigation_id", "expected_revision_id", "target_snapshot_id", "name", "idempotency_key"], getOperation: ["operation_id"], retryOperation: ["operation_id"],
};
/** Validates once before a caller remembers an exact mutation intent for uncertain retries. */
export async function validateInvestigationRequest<K extends Method>(method: K, supplied: unknown): Promise<InvestigationRequests[K]> {
  try {
    if (!Object.hasOwn(requestKeys, method)) return badRequest();
    const optional = ["limit", "after_id", "revision_id", "archived"], p = shape(finiteJson(supplied), requestKeys[method], requestKeys[method].filter((key) => !optional.includes(key)));
    for (const key of ["investigation_id", "conversation_id", "idempotency_key", "expected_revision_id", "operation_id"]) if (Object.hasOwn(p, key)) p[key] = uuid(p[key]);
    for (const key of ["snapshot_id", "target_snapshot_id"]) if (Object.hasOwn(p, key)) p[key] = sha(p[key]);
    if (Object.hasOwn(p, "name")) p.name = name(p.name);
    if (Object.hasOwn(p, "expected_version")) p.expected_version = integer(p.expected_version);
    if (method === "list" || method === "listConversations") { p.limit = integer(p.limit === undefined ? 25 : p.limit, 1, 100); p.after_id = nullableUuid(p.after_id ?? null); }
    if (method === "getContext") p.revision_id = nullableUuid(p.revision_id ?? null);
    if (method === "archive") { p.archived = p.archived === undefined ? true : p.archived; if (typeof p.archived !== "boolean") return badRequest(); }
    if (method === "create") p.scope = await parseCatalogueContractModel("EvidenceScope", p.scope);
    if (method === "changeContext") {
      const c = shape(p.change, ["op", "scope", "reference"], ["op"]);
      if (c.op === "scope") { shape(c, ["op", "scope"]); p.change = { op: "scope", scope: await parseCatalogueContractModel("EvidenceScope", c.scope) }; }
      else { shape(c, ["op", "reference"]); p.change = { op: choice(c.op, ["attach", "detach", "pin", "unpin"]), reference: reference(c.reference) }; }
    }
    if (new TextEncoder().encode(JSON.stringify(p)).byteLength > MAX_INVESTIGATION_REQUEST_BYTES) return badRequest();
    return p as InvestigationRequests[K];
  } catch { return badRequest(); }
}
async function responsePayload(method: Method, raw: unknown, request: Record<string, unknown>): Promise<unknown> {
  const allowed: Record<Method, string[]> = { create: ["operation", "investigation", "context"], list: ["items", "next_after_id"], get: ["investigation", "context", "legacy_history_import"], rename: ["operation", "investigation"], archive: ["operation", "investigation"], createConversation: ["operation", "conversation"], listConversations: ["items", "next_after_id"], getConversation: ["conversation"], renameConversation: ["operation", "conversation"], getContext: ["context"], changeContext: ["operation", "investigation", "context"], refresh: ["operation", "investigation", "context"], getOperation: ["operation"], retryOperation: ["operation", "investigation", "context"] };
  const keys = ["version", ...allowed[method]], p = shape(raw, keys, method === "retryOperation" ? ["version", "operation"] : keys);
  if (p.version !== "investigations-v1") return invalid(); const result: Record<string, unknown> = { version: "investigations-v1" };
  if (method === "list" || method === "listConversations") {
    if (!Array.isArray(p.items) || p.items.length > (request.limit as number)) return invalid();
    const rows: (Investigation | Conversation)[] = p.items.map((item) => method === "list" ? investigation(item) : conversation(item)), next = nullableUuid(p.next_after_id);
    if (new Set(rows.map((row) => row.id)).size !== rows.length || rows.some((row, i) => i > 0 && rows[i - 1].id >= row.id) || rows.some((row) => request.after_id != null && row.id <= (request.after_id as string)) || (next !== null && (rows.length !== request.limit || next !== rows.at(-1)?.id))) return invalid();
    if (method === "list" && rows.some((row) => !["active", "archived"].includes((row as Investigation).status))) return invalid();
    if (method === "listConversations" && rows.some((row) => (row as Conversation).investigation_id !== request.investigation_id)) return invalid();
    return { ...result, items: rows, next_after_id: next };
  }
  const i = Object.hasOwn(p, "investigation") ? investigation(p.investigation) : undefined;
  const c = Object.hasOwn(p, "context") ? await context(p.context) : undefined;
  const conv = Object.hasOwn(p, "conversation") ? conversation(p.conversation) : undefined;
  const op = Object.hasOwn(p, "operation") ? operation(p.operation) : undefined;
  if (i) result.investigation = i; if (c) result.context = c; if (conv) result.conversation = conv; if (op) result.operation = op;
  if ((method !== "refresh" && request.investigation_id && [i?.id, c?.investigation_id, conv?.investigation_id, op?.investigation_id].some((id) => id !== undefined && id !== request.investigation_id)) || (i && c && (c.investigation_id !== i.id || (method === "get" && c.id !== i.head_revision_id))) || (i && op && op.investigation_id !== i.id) || (conv && op && conv.investigation_id !== op.investigation_id)) return invalid();
  if (request.conversation_id && conv?.id !== request.conversation_id) return invalid();
  if (request.revision_id && c?.id !== request.revision_id) return invalid();
  if (request.operation_id && op?.id !== request.operation_id) return invalid();
  if (method === "get") { if (p.legacy_history_import !== "unavailable") return invalid(); result.legacy_history_import = "unavailable"; }
  if (["create", "changeContext", "refresh", "rename", "archive", "createConversation", "renameConversation"].includes(method) && (op?.state !== "committed" || op.kind !== endpoints[method])) return invalid();
  if (c && op && op.candidate_revision_id !== c.id) return invalid();
  if ((method === "create" && (c?.snapshot_id !== request.snapshot_id || !equal(await parseCatalogueContractModel("EvidenceScope", c?.scope), request.scope))) || (method === "refresh" && (c?.snapshot_id !== request.target_snapshot_id || i?.predecessor_investigation_id !== request.investigation_id || i?.predecessor_revision_id !== request.expected_revision_id))) return invalid();
  if (method === "changeContext" && c?.predecessor_revision_id !== request.expected_revision_id) return invalid();
  if (method === "changeContext" && c) {
    const change = request.change as ContextChange;
    if (change.op === "scope") { if (!equal(await parseCatalogueContractModel("EvidenceScope", c.scope), change.scope)) return invalid(); }
    else {
      const rows = change.op === "attach" || change.op === "detach" ? c.attachments : c.pins;
      const contains = rows.some((row) => equal(row, change.reference));
      if (contains !== (change.op === "attach" || change.op === "pin")) return invalid();
    }
  }
  if (method === "rename" && i?.name !== request.name) return invalid();
  if ((method === "createConversation" || method === "renameConversation") && conv?.name !== request.name) return invalid();
  if (method === "archive" && i?.status !== (request.archived ? "archived" : "active")) return invalid();
  if (method === "retryOperation" && ((i === undefined) !== (c === undefined) || (c !== undefined && op?.state !== "committed"))) return invalid();
  return result;
}
function uniqueJson(text: string): unknown {
  const parsed: unknown = JSON.parse(text); let index = 0;
  const space = () => { while (index < text.length && /\s/.test(text[index])) index++; };
  function readString(): string { const start = index++; while (index < text.length) { if (text[index] === "\\") { index += 2; continue; } if (text[index++] === '"') return JSON.parse(text.slice(start, index)) as string; } return invalid(); }
  function scan(depth: number): void {
    if (depth > 128) return invalid(); space(); const token = text[index];
    if (token === "{") { index++; space(); const keys = new Set<string>(); if (text[index] === "}") { index++; return; } while (index < text.length) { space(); const key = readString(); if (keys.has(key)) return invalid(); keys.add(key); space(); index++; scan(depth + 1); space(); if (text[index++] === "}") return; } }
    else if (token === "[") { index++; space(); if (text[index] === "]") { index++; return; } while (index < text.length) { scan(depth + 1); space(); if (text[index++] === "]") return; } }
    else if (token === '"') readString(); else while (index < text.length && !/[\s,}\]]/.test(text[index])) index++;
  }
  scan(0); return finiteJson(parsed);
}
const abort = () => new DOMException("The investigation request was cancelled", "AbortError");
function aborted(signal?: AbortSignal): void { if (signal?.aborted) throw abort(); }
async function discard(response: Response): Promise<void> { try { await response.body?.cancel(); } catch { /* HTTP status remains authoritative. */ } }
async function cancellable<T>(pending: Promise<T>, signal?: AbortSignal, late?: (value: T) => void): Promise<T> {
  if (!signal) return pending;
  if (signal.aborted) { void pending.then((value) => late?.(value), () => undefined); throw abort(); }
  return new Promise<T>((resolve, reject) => {
    let cancelled = false;
    const cancel = () => { cancelled = true; reject(abort()); };
    signal.addEventListener("abort", cancel, { once: true });
    void pending.then((value) => { signal.removeEventListener("abort", cancel); if (cancelled) late?.(value); else resolve(value); }, (error: unknown) => { signal.removeEventListener("abort", cancel); if (!cancelled) reject(error); });
  });
}
async function boundedJson(response: Response, maximum: number, signal?: AbortSignal): Promise<unknown> {
  const length = response.headers.get("content-length");
  if ((length !== null && (!/^\d+$/.test(length) || Number(length) > maximum)) || !response.body) { await discard(response); return invalid(); }
  const reader = response.body.getReader(), chunks: Uint8Array[] = []; let total = 0;
  const cancel = () => { void reader.cancel().catch(() => undefined); }; signal?.addEventListener("abort", cancel, { once: true });
  try { while (true) { aborted(signal); const part = await cancellable(reader.read(), signal); aborted(signal); if (part.done) break; total += part.value.byteLength; if (total > maximum) { await reader.cancel(); return invalid(); } chunks.push(part.value); } }
  finally { signal?.removeEventListener("abort", cancel); reader.releaseLock(); }
  const bytes = new Uint8Array(total); let offset = 0; for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return uniqueJson(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
}
const statusErrors: Readonly<Record<number, readonly [string, string]>> = {
  401: ["authentication_required", "Authentication is required"], 403: ["access_denied", "Investigation access is denied"],
  404: ["not_found", "Investigation content is unavailable"], 409: ["conflict", "Investigation version has changed"],
  422: ["invalid_request", "Investigation request is invalid"], 503: ["investigations_unavailable", "Investigations are unavailable"],
};
export function createInvestigationClient(options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; tokenProvider?: () => string | undefined | Promise<string | undefined>; maxResponseBytes?: number } = {}): InvestigationClient {
  const fetcher = options.fetcher ?? ((input: string, init?: RequestInit) => fetch(input, init)), maximum = options.maxResponseBytes ?? MAX_INVESTIGATION_RESPONSE_BYTES;
  if (!Number.isSafeInteger(maximum) || maximum < 1 || maximum > MAX_INVESTIGATION_RESPONSE_BYTES) throw new RangeError("Invalid investigation response byte budget");
  async function call(method: Method, request: unknown, signal?: AbortSignal): Promise<unknown> {
    aborted(signal); const payload = await validateInvestigationRequest(method, request); aborted(signal);
    const token = await cancellable(Promise.resolve(options.tokenProvider?.()), signal); aborted(signal);
    if (token !== undefined && (typeof token !== "string" || !token || token.length > 8192 || /\s/.test(token))) throw new InvestigationClientError("authentication_required", "Authentication is required", 401);
    try {
      const response = await cancellable(fetcher(`/research/investigations/${endpoints[method]}`, { method: "POST", credentials: "omit", cache: "no-store", redirect: "error", signal, headers: { Accept: "application/json", "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(payload) }), signal, (late) => { void discard(late); });
      if (signal?.aborted) { await discard(response); throw abort(); }
      if (!response.ok && statusErrors[response.status]) { void discard(response); const [code, message] = statusErrors[response.status]; throw new InvestigationClientError(code, message, response.status); }
      if (!response.ok) { await discard(response); throw new InvestigationClientError("investigations_unavailable", "Investigations are unavailable", response.status); }
      const raw = await boundedJson(response, maximum, signal); aborted(signal);
      const result = await responsePayload(method, raw, payload as Record<string, unknown>); aborted(signal); return result;
    } catch (error) {
      if (signal?.aborted || (error instanceof Error && error.name === "AbortError")) throw abort();
      if (error instanceof InvestigationClientError) throw error;
      throw new InvestigationClientError("invalid_response", "Investigation response is invalid or unavailable");
    }
  }
  return Object.fromEntries((Object.keys(endpoints) as Method[]).map((method) => [method, (request: unknown, signal?: AbortSignal) => call(method, request, signal)])) as InvestigationClient;
}
