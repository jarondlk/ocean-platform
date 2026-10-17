/** C16 public catalogue transport. All authorization context remains server-owned. */
import { parseCatalogueContractModel } from "./catalogue-contract.ts";
import type { CatalogueFilters, CatalogueListing, CatalogueNode, EvidenceScope, JsonValue, LocalizedText, Ordering, QueryResult } from "./catalogue-contract.ts";
export type { CatalogueFilters, CatalogueListing, CatalogueNode, EvidenceScope, Ordering } from "./catalogue-contract.ts";

export type CatalogueBaseRequest = { schema_version?: "context-catalogue-v1"; snapshot_id: string; scope: EvidenceScope };
export type CatalogueListRequest = CatalogueBaseRequest & { parent_id?: string | null; filters?: CatalogueFilters; ordering?: Ordering[]; limit?: number; cursor?: string | null };
export type CatalogueOpenRequest = CatalogueBaseRequest & { object_id: string; include_details?: boolean };
export type CatalogueCoverageRequest = CatalogueBaseRequest & { object_id: string; parameters?: Record<string, JsonValue>; limit?: number; offset?: number };
export type CatalogueQueryRequest = CatalogueBaseRequest & { operation_id: "c13.table" | "c13.inventory" | "c13.coverage" | "c13.quality" | "c13.operation"; operation_version: "c13-v1"; input_ids: string[]; parameters?: Record<string, JsonValue> };
export type CatalogueRelationshipsRequest = CatalogueListRequest & { object_id?: string | null };
export type CataloguePublishedRequest = CatalogueBaseRequest & { analysis_id: string; table?: string | null; workflow_kind?: string | null; protocol_id?: string | null; limit?: number; offset?: number };
export type CatalogueSnapshotsRequest = { schema_version?: "context-catalogue-v1"; scope: EvidenceScope; limit?: number; cursor?: string | null };
export type CatalogueSnapshotPage = { version: "catalogue-browser-v1"; scope: EvidenceScope; snapshots: { snapshot_id: string; label: LocalizedText }[]; latest_snapshot_id: string | null; total: number; next_cursor: string | null; access_revision: string };
export type CatalogueDetails = { node: CatalogueNode; details: Record<string, JsonValue> };
export type ScientificResponse = QueryResult & { adapter_version: "c13-v1"; offset: number; next_offset: number | null; qualifications: string[] };
export type CatalogueClient = {
  snapshots(request: CatalogueSnapshotsRequest, signal?: AbortSignal): Promise<CatalogueSnapshotPage>;
  overview(request: CatalogueBaseRequest, signal?: AbortSignal): Promise<CatalogueListing>;
  list(request: CatalogueListRequest, signal?: AbortSignal): Promise<CatalogueListing>;
  open(request: CatalogueOpenRequest & { include_details: true }, signal?: AbortSignal): Promise<CatalogueDetails>;
  open(request: CatalogueOpenRequest & { include_details?: false }, signal?: AbortSignal): Promise<CatalogueNode>;
  open(request: CatalogueOpenRequest, signal?: AbortSignal): Promise<CatalogueNode | CatalogueDetails>;
  coverage(request: CatalogueCoverageRequest, signal?: AbortSignal): Promise<ScientificResponse>;
  query(request: CatalogueQueryRequest, signal?: AbortSignal): Promise<ScientificResponse>;
  relationships(request: CatalogueRelationshipsRequest, signal?: AbortSignal): Promise<CatalogueListing>;
  getPublished(request: CataloguePublishedRequest, signal?: AbortSignal): Promise<ScientificResponse>;
};
export class CatalogueClientError extends Error {
  readonly code: string; readonly status_code: number;
  constructor(code: string, message: string, status_code = 503) { super(message); this.name = "CatalogueClientError"; this.code = code; this.status_code = status_code; }
}
export const MAX_CATALOGUE_RESPONSE_BYTES = 40 * 1024 * 1024;
const idPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
const shaPattern = /^[a-f0-9]{64}$/;
function invalid(): never { throw new CatalogueClientError("invalid_response", "Catalogue response is invalid"); }
function badRequest(): never { throw new CatalogueClientError("invalid_request", "Catalogue request is invalid", 422); }
function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value)); }
function shape(value: unknown, allowed: readonly string[], required: readonly string[] = []): Record<string, unknown> {
  if (!object(value) || Object.keys(value).some((key) => !allowed.includes(key)) || required.some((key) => !Object.hasOwn(value, key))) return invalid();
  return value;
}
function identifier(value: unknown): string { if (typeof value !== "string" || !idPattern.test(value)) return invalid(); return value; }
function integer(value: unknown, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number { if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum || value > maximum) return invalid(); return value; }
function cursor(value: unknown): string | null { if (value === null) return null; if (typeof value !== "string" || !value || value.length > 2048) return invalid(); return value; }
function json(value: unknown, stack = new Set<object>(), depth = 0): unknown {
  if (depth > 128) return invalid();
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") { if (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value))) return invalid(); return value; }
  if ((!object(value) && !Array.isArray(value)) || stack.has(value)) return invalid();
  stack.add(value);
  const result = Array.isArray(value) ? value.map((v) => json(v, stack, depth + 1)) : Object.fromEntries(Object.entries(value).map(([k, v]) => [k, json(v, stack, depth + 1)]));
  stack.delete(value); return result;
}
function equal(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) && Array.isArray(right)) return left.length === right.length && left.every((v, i) => equal(v, right[i]));
  if (object(left) && object(right)) return Object.keys(left).length === Object.keys(right).length && Object.keys(left).every((k) => Object.hasOwn(right, k) && equal(left[k], right[k]));
  return false;
}
export function defaultCatalogueScope(): EvidenceScope {
  return { version: 1, sources: { ctd: { enabled: true, filters: {} }, metagenome: { enabled: true, filters: {} }, remote_sensing: { enabled: true, filters: {} }, edna_metabarcoding: { enabled: true, filters: {}, analysis_id: null } } };
}
type Method = "snapshots" | "overview" | "list" | "open" | "coverage" | "query" | "relationships" | "getPublished";
const fields: Record<Method, string[]> = {
  snapshots: ["limit", "cursor"], overview: [], list: ["parent_id", "filters", "ordering", "limit", "cursor"],
  open: ["object_id", "include_details"], coverage: ["object_id", "parameters", "limit", "offset"],
  query: ["operation_id", "operation_version", "input_ids", "parameters"],
  relationships: ["parent_id", "filters", "ordering", "limit", "cursor", "object_id"],
  getPublished: ["analysis_id", "table", "workflow_kind", "protocol_id", "limit", "offset"],
};
async function requestPayload(method: Method, supplied: unknown): Promise<Record<string, unknown>> {
  try {
    const p = shape(json(supplied), ["schema_version", "scope", ...(method === "snapshots" ? [] : ["snapshot_id"]), ...fields[method]], ["scope", ...(method === "snapshots" ? [] : ["snapshot_id"])]);
    if (p.schema_version !== undefined && p.schema_version !== "context-catalogue-v1") return badRequest();
    p.scope = await parseCatalogueContractModel("EvidenceScope", p.scope);
    if (method !== "snapshots") identifier(p.snapshot_id);
    if (["snapshots", "list", "relationships", "coverage", "getPublished"].includes(method)) p.limit = integer(p.limit === undefined ? 100 : p.limit, 1, 500);
    if (["snapshots", "list", "relationships"].includes(method)) p.cursor = cursor(p.cursor ?? null);
    if (["list", "relationships"].includes(method)) {
      p.parent_id = p.parent_id == null ? null : identifier(p.parent_id);
      p.filters = await parseCatalogueContractModel("CatalogueFilters", p.filters === undefined ? {} : p.filters);
      const ordering = p.ordering === undefined ? [{ field: "id", direction: "asc" }] : p.ordering;
      if (!Array.isArray(ordering) || ordering.length < 1 || ordering.length > 2) return badRequest();
      const parsed = await Promise.all(ordering.map((item) => parseCatalogueContractModel("Ordering", item)));
      if (parsed.at(-1)?.field !== "id" || new Set(parsed.map((item) => item.field)).size !== parsed.length) return badRequest();
      p.ordering = parsed;
    }
    if (["open", "coverage"].includes(method)) identifier(p.object_id);
    if (method === "open") { if (p.include_details === undefined) p.include_details = false; if (typeof p.include_details !== "boolean") return badRequest(); }
    if (method === "relationships") { p.object_id = p.object_id == null ? null : identifier(p.object_id); if (p.object_id !== null && p.parent_id !== null) return badRequest(); }
    if (["coverage", "getPublished"].includes(method)) p.offset = integer(p.offset === undefined ? 0 : p.offset);
    if (["query", "coverage"].includes(method)) { if (p.parameters === undefined) p.parameters = {}; if (!object(p.parameters)) return badRequest(); }
    if (method === "query") {
      if (!["c13.table", "c13.inventory", "c13.coverage", "c13.quality", "c13.operation"].includes(p.operation_id as string) || p.operation_version !== "c13-v1" || !Array.isArray(p.input_ids) || p.input_ids.length !== 1) return badRequest();
      p.input_ids.forEach(identifier);
    }
    if (method === "getPublished") { identifier(p.analysis_id); for (const k of ["table", "workflow_kind", "protocol_id"]) if (p[k] != null) identifier(p[k]); }
    return p;
  } catch { return badRequest(); }
}
function context(value: { snapshot_id: string; scope: EvidenceScope }, p: Record<string, unknown>): void { if (value.snapshot_id !== p.snapshot_id || !equal(value.scope, p.scope)) return invalid(); }
async function parseSnapshots(raw: unknown, p: Record<string, unknown>): Promise<CatalogueSnapshotPage> {
  const v = shape(raw, ["version", "scope", "snapshots", "latest_snapshot_id", "total", "next_cursor", "access_revision"], ["version", "scope", "snapshots", "latest_snapshot_id", "total", "access_revision"]);
  if (v.version !== "catalogue-browser-v1") return invalid();
  const scope = await parseCatalogueContractModel("EvidenceScope", v.scope);
  if (!equal(scope, p.scope) || !Array.isArray(v.snapshots) || v.snapshots.length > (p.limit as number)) return invalid();
  const snapshots = await Promise.all(v.snapshots.map(async (item) => { const row = shape(item, ["snapshot_id", "label"], ["snapshot_id", "label"]); if (typeof row.snapshot_id !== "string" || !shaPattern.test(row.snapshot_id)) return invalid(); return { snapshot_id: row.snapshot_id, label: await parseCatalogueContractModel("LocalizedText", row.label) }; }));
  const total = integer(v.total), latest = v.latest_snapshot_id, next = cursor(v.next_cursor ?? null);
  if ((latest === null) !== (total === 0) || (latest !== null && (typeof latest !== "string" || !shaPattern.test(latest))) || new Set(snapshots.map((v) => v.snapshot_id)).size !== snapshots.length || snapshots.length > total || (next !== null && snapshots.length === 0)) return invalid();
  if (p.cursor === null && total > 0 && snapshots[0]?.snapshot_id !== latest) return invalid();
  if (p.cursor === null && (snapshots.length !== Math.min(total, p.limit as number) || (next !== null) !== (snapshots.length < total))) return invalid();
  if (next !== null && next === p.cursor) return invalid();
  return { version: "catalogue-browser-v1", scope, snapshots, latest_snapshot_id: latest as string | null, total, next_cursor: next, access_revision: identifier(v.access_revision) };
}
async function parseListing(raw: unknown, p: Record<string, unknown>, method: Method): Promise<CatalogueListing> {
  const result = await parseCatalogueContractModel("CatalogueListing", raw); context(result.request, p);
  let expected = { parent_id: p.parent_id ?? null, filters: p.filters ?? await parseCatalogueContractModel("CatalogueFilters", {}), ordering: p.ordering ?? [{ field: "id", direction: "asc" }], limit: p.limit ?? 100, cursor: p.cursor ?? null };
  if (method === "overview") expected = { ...expected, filters: await parseCatalogueContractModel("CatalogueFilters", { kinds: ["root"] }) };
  if (method === "relationships") expected = { ...expected, parent_id: p.object_id ?? p.parent_id ?? null, filters: { ...(expected.filters as CatalogueFilters), roots: ["relationships"] } };
  for (const k of Object.keys(expected) as (keyof typeof expected)[]) if (!equal(result.request[k], expected[k])) return invalid();
  for (const node of result.items) context(node, p);
  if (result.items.length > (expected.limit as number) || new Set(result.items.map((node) => node.id)).size !== result.items.length) return invalid();
  return result;
}
async function inputHash(identity: string): Promise<string> { return "c13:input:" + Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(identity))), (b) => b.toString(16).padStart(2, "0")).join(""); }
async function parseScientific(raw: unknown, p: Record<string, unknown>, method: Method): Promise<ScientificResponse> {
  const v = shape(raw, ["schema_version", "snapshot_id", "scope", "columns", "rows", "receipt", "adapter_version", "offset", "next_offset", "qualifications"], ["snapshot_id", "scope", "columns", "rows", "receipt"]);
  const { adapter_version = "c13-v1", offset = 0, next_offset = null, qualifications = [], ...base } = v;
  if (adapter_version !== "c13-v1" || !Array.isArray(qualifications) || qualifications.some((s) => typeof s !== "string" || !s.trim() || Array.from(s).length > 4000)) return invalid();
  const result = await parseCatalogueContractModel("QueryResult", base); context(result, p);
  const operation = method === "query" ? p.operation_id : method === "coverage" ? "c13.coverage" : "c13.table";
  if (result.receipt.operation_id !== operation || result.receipt.operation_version !== "c13-v1") return invalid();
  const parameters = method === "query" ? p.parameters as Record<string, unknown> : method === "coverage" ? { parameters: p.parameters, offset: p.offset, limit: p.limit } : Object.fromEntries(Object.entries(p).filter(([key, value]) => ["table", "workflow_kind", "protocol_id", "limit", "offset"].includes(key) && value !== null));
  if (Object.entries(parameters).some(([key, value]) => !equal(result.receipt.parameters?.[key], value))) return invalid();
  const start = integer(offset), next = next_offset === null ? null : integer(next_offset), expectedOffset = integer(parameters.offset ?? 0), limit = integer(parameters.limit ?? 100, 1, 500);
  if (start !== expectedOffset || result.rows.length > limit || (next !== null && (next !== start + result.rows.length || next <= start))) return invalid();
  const total = result.receipt.total_rows.value;
  // Native aggregates may expose a bounded preview and deliberately disallow offsets.
  // Only the explicitly pageable C13 paths must supply a continuation for known remaining rows.
  const pageable = operation === "c13.table" || (operation === "c13.operation" && ["c10.table", "c10.coverage", "c11.table", "c11.grid_points", "c12.table"].includes(parameters.operation_id as string));
  if (total != null && (start + result.rows.length > total || (next !== null && start + result.rows.length >= total) || (pageable && (next !== null) !== (start + result.rows.length < total)))) return invalid();
  if (result.receipt.availability.status === "available" && ["c13.coverage", "c13.quality", "c13.operation"].includes(operation as string)) {
    const input = method === "coverage" ? p.object_id as string : (p.input_ids as string[])[0];
    const hashed = /^c13:statistics:[a-f0-9]{64}$/.test(input) ? input.replace("c13:statistics:", "c13:input:") : await inputHash(input);
    if (!result.receipt.inputs.some((row) => row.object_id === "scientific:registry") || !result.receipt.inputs.some((row) => row.object_id === input || row.object_id === hashed)) return invalid();
  }
  return { ...result, adapter_version: "c13-v1", offset: start, next_offset: next, qualifications: [...qualifications] as string[] };
}

/** JSON.parse checks syntax; this pass rejects duplicate keys before accepting the value. */
function uniqueJson(text: string): unknown {
  const parsed: unknown = JSON.parse(text); let index = 0;
  const space = () => { while (index < text.length && /\s/.test(text[index])) index++; };
  function string(): string { const start = index++; while (index < text.length) { if (text[index] === "\\") { index += 2; continue; } if (text[index++] === '"') return JSON.parse(text.slice(start, index)) as string; } return invalid(); }
  function scan(depth: number): void {
    if (depth > 128) return invalid(); space(); const token = text[index];
    if (token === "{") { index++; space(); const keys = new Set<string>(); if (text[index] === "}") { index++; return; } while (index < text.length) { space(); const key = string(); if (keys.has(key)) return invalid(); keys.add(key); space(); index++; scan(depth + 1); space(); if (text[index++] === "}") return; } }
    else if (token === "[") { index++; space(); if (text[index] === "]") { index++; return; } while (index < text.length) { scan(depth + 1); space(); if (text[index++] === "]") return; } }
    else if (token === '"') string(); else while (index < text.length && !/[\s,}\]]/.test(text[index])) index++;
  }
  scan(0); return json(parsed);
}
const abort = () => new DOMException("The catalogue request was cancelled", "AbortError");
function aborted(signal?: AbortSignal): void { if (signal?.aborted) throw abort(); }
async function discard(response: Response): Promise<void> { try { await response.body?.cancel(); } catch { /* Original status is authoritative. */ } }
/** Injected transports must obey caller cancellation even when they ignore fetch's signal. */
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
  const cancel = () => { void reader.cancel().catch(() => undefined); };
  signal?.addEventListener("abort", cancel, { once: true });
  try { while (true) { aborted(signal); const part = await reader.read(); aborted(signal); if (part.done) break; total += part.value.byteLength; if (total > maximum) { await reader.cancel(); return invalid(); } chunks.push(part.value); } }
  finally { signal?.removeEventListener("abort", cancel); reader.releaseLock(); }
  const bytes = new Uint8Array(total); let offset = 0; for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return uniqueJson(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
}
const endpoint: Record<Method, string> = { snapshots: "snapshots", overview: "overview", list: "list", open: "open", coverage: "coverage", query: "query", relationships: "relationships", getPublished: "analysis/get-published" };
const statusErrors: Readonly<Record<number, readonly [string, string]>> = {
  401: ["authentication_required", "Authentication is required"], 403: ["access_denied", "Catalogue access is denied"],
  404: ["not_found", "Catalogue object is unavailable"], 409: ["invalid_cursor", "Catalogue cursor is stale or invalid"],
  422: ["invalid_request", "Catalogue request is invalid"], 503: ["catalogue_unavailable", "Catalogue is unavailable"],
};
export function createCatalogueClient(options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; tokenProvider?: () => string | undefined | Promise<string | undefined>; maxResponseBytes?: number } = {}): CatalogueClient {
  const fetcher = options.fetcher ?? ((input: string, init?: RequestInit) => fetch(input, init));
  const maximum = options.maxResponseBytes ?? MAX_CATALOGUE_RESPONSE_BYTES;
  if (!Number.isSafeInteger(maximum) || maximum < 1 || maximum > MAX_CATALOGUE_RESPONSE_BYTES) throw new RangeError("Invalid catalogue response byte budget");
  async function call(method: Method, request: unknown, signal?: AbortSignal): Promise<unknown> {
    aborted(signal); const payload = await requestPayload(method, request); aborted(signal);
    const token = await cancellable(Promise.resolve(options.tokenProvider?.()), signal); aborted(signal);
    if (token !== undefined && (typeof token !== "string" || !token || token.length > 8192 || /\s/.test(token))) throw new CatalogueClientError("authentication_required", "Authentication is required", 401);
    try {
      const response = await cancellable(fetcher(`/catalogue/${endpoint[method]}`, { method: "POST", credentials: "omit", cache: "no-store", redirect: "error", signal, headers: { Accept: "application/json", "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(payload) }), signal, (late) => { void discard(late); });
      if (signal?.aborted) { await discard(response); throw abort(); }
      // Status is authoritative even if a proxy supplies HTML or a forged error code.
      if (!response.ok && statusErrors[response.status]) { void discard(response); const [code, message] = statusErrors[response.status]; throw new CatalogueClientError(code, message, response.status); }
      const raw = await boundedJson(response, response.ok ? maximum : Math.min(maximum, 64 * 1024), signal); aborted(signal);
      if (!response.ok) {
        const envelope = shape(raw, ["error"], ["error"]), error = shape(envelope.error, ["code", "message"], ["code", "message"]);
        const code = identifier(error.code); if (typeof error.message !== "string" || !error.message.trim() || Array.from(error.message).length > 4000) return invalid();
        throw new CatalogueClientError(code, error.message, response.status);
      }
      let parsed: unknown;
      if (method === "snapshots") parsed = await parseSnapshots(raw, payload);
      else if (["overview", "list", "relationships"].includes(method)) parsed = await parseListing(raw, payload, method);
      else if (method === "open") {
        if (payload.include_details) { const detail = shape(raw, ["node", "details"], ["node", "details"]); const node = await parseCatalogueContractModel("CatalogueNode", detail.node); context(node, payload); if (node.id !== payload.object_id || !object(detail.details)) return invalid(); parsed = { node, details: detail.details }; }
        else { const node = await parseCatalogueContractModel("CatalogueNode", raw); context(node, payload); if (node.id !== payload.object_id) return invalid(); parsed = node; }
      } else parsed = await parseScientific(raw, payload, method);
      aborted(signal); return parsed;
    } catch (error) {
      if (signal?.aborted || (error instanceof Error && error.name === "AbortError")) throw abort();
      if (error instanceof CatalogueClientError) throw error;
      throw new CatalogueClientError("invalid_response", "Catalogue response is invalid or unavailable");
    }
  }
  return Object.fromEntries((Object.keys(endpoint) as Method[]).map((method) => [method, (request: unknown, signal?: AbortSignal) => call(method, request, signal)])) as CatalogueClient;
}
