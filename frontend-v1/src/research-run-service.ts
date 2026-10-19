/** Fixed same-origin durable run API. All source/owner authorization stays server-owned. */
import { parseCatalogueContractModel } from "./catalogue-contract.ts";
import {
  freezeRunContext, freezeRunValue, sameRunBinding,
  type ResearchRun, type ResearchRunTransport, type RunContextBinding, type RunEventPage,
  type RunListPage, type RunListRequest, type RunPublicEvent, type RunMutationIntent,
} from "./research-run-contract.ts";

export const RESEARCH_RUNS_VERSION = "research-runs-v1" as const;
export const MAX_RUN_RESPONSE_BYTES = 16 * 1024 * 1024;
export const MAX_RUN_REQUEST_BYTES = 65536;
export type ServiceRunTransport = ResearchRunTransport & { list(request: RunListRequest, signal?: AbortSignal): Promise<RunListPage> };
export class ResearchRunClientError extends Error {
  readonly code: string; readonly status_code: number;
  constructor(code: string, message: string, status_code = 503) { super(message); this.name = "ResearchRunClientError"; this.code = code; this.status_code = status_code; }
}
function invalid(): never { throw new ResearchRunClientError("invalid_response", "The research service response could not be verified"); }
function badRequest(): never { throw new ResearchRunClientError("invalid_request", "The research request is invalid", 422); }
const uuidPattern = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const shaPattern = /^[a-f0-9]{64}$/;
function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value)); }
function shape(value: unknown, allowed: readonly string[], required = allowed): Record<string, unknown> { if (!object(value) || Object.keys(value).some(key => !allowed.includes(key)) || required.some(key => !Object.hasOwn(value, key))) return invalid(); return value; }
function text(value: unknown, maximum = 8000): string { if (typeof value !== "string" || !value.trim() || !value.isWellFormed() || Array.from(value).length > maximum || /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(value)) return invalid(); return value; }
function uuid(value: unknown): string { const s = text(value, 36); if (!uuidPattern.test(s)) return invalid(); return s; }
function integer(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): number { if (typeof value !== "number" || !Number.isSafeInteger(value) || value < min || value > max) return invalid(); return value; }
function nullableUuid(value: unknown): string | null { return value === null ? null : uuid(value); }
function cursor(value: unknown): string | null { if (value === null) return null; if (typeof value !== "string" || !value.length || !value.isWellFormed() || Array.from(value).length > 4096) return invalid(); return value; }
function localized(value: unknown): { en: string; ja: string } { const p = shape(value, ["en", "ja"]); return { en: text(p.en, 2000), ja: text(p.ja, 2000) }; }
function json(value: unknown, stack = new Set<object>(), depth = 0): unknown {
  if (depth > 128) return invalid();
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") { if (!value.isWellFormed()) return invalid(); return value; }
  if (typeof value === "number") { if (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value))) return invalid(); return value; }
  if ((!object(value) && !Array.isArray(value)) || stack.has(value) || Object.getOwnPropertySymbols(value).length || Object.values(Object.getOwnPropertyDescriptors(value)).some(d => d.get || d.set)) return invalid();
  stack.add(value); const result = Array.isArray(value) ? Array.from(value, item => json(item, stack, depth + 1)) : Object.fromEntries(Object.entries(value).map(([key,item]) => [key,json(item, stack, depth + 1)])); stack.delete(value); return result;
}
function binding(value: unknown): RunContextBinding {
  const p = shape(value, ["investigation_id", "conversation_id", "revision_id", "snapshot_id", "payload_sha256"]);
  if (typeof p.snapshot_id !== "string" || !shaPattern.test(p.snapshot_id) || typeof p.payload_sha256 !== "string" || !shaPattern.test(p.payload_sha256)) return invalid();
  return { investigation_id: uuid(p.investigation_id), conversation_id: uuid(p.conversation_id), revision_id: uuid(p.revision_id), snapshot_id: p.snapshot_id, payload_sha256: p.payload_sha256 };
}
const statuses = ["queued", "running", "awaiting_clarification", "awaiting_approval", "completed", "partial", "failed", "cancelled"] as const;
const eventKinds = ["accepted", "started", "progress", "clarification", "approval", "resumed", "completed", "partial", "failed", "cancelled"] as const;
function event(value: unknown, runId: string): RunPublicEvent {
  const p = shape(value, ["cursor", "run_id", "elapsed_ms", "kind", "summary"]);
  if (p.run_id !== runId || !eventKinds.includes(p.kind as typeof eventKinds[number])) return invalid();
  return { cursor: integer(p.cursor, 1), run_id: runId, elapsed_ms: integer(p.elapsed_ms), kind: p.kind as RunPublicEvent["kind"], summary: localized(p.summary) };
}
async function run(value: unknown): Promise<ResearchRun> {
  const p = shape(value, ["id", "context", "question", "status", "active_elapsed_ms", "event_cursor", "latest_event_cursor", "activity", "continuation_of", "clarification", "clarification_id", "result", "error", "synthetic"]);
  if (!statuses.includes(p.status as typeof statuses[number]) || p.synthetic !== false || p.result !== null || !Array.isArray(p.activity) || p.activity.length !== 0 || p.event_cursor !== 0) return invalid();
  const raw = shape(p.context, ["binding", "scope", "attachments", "pins"]), bound = binding(raw.binding);
  await parseCatalogueContractModel("EvidenceScope", raw.scope);
  const context = freezeRunContext({ binding: bound, scope: raw.scope as ResearchRun["context"]["scope"], attachments: raw.attachments as ResearchRun["context"]["attachments"], pins: raw.pins as ResearchRun["context"]["pins"] });
  const id = uuid(p.id), clarification = p.clarification === null ? null : localized(p.clarification), clarificationId = nullableUuid(p.clarification_id);
  if ((p.status === "awaiting_clarification") !== (clarification !== null && clarificationId !== null)) return invalid();
  if (p.status !== "awaiting_clarification" && (clarification !== null || clarificationId !== null)) return invalid();
  return freezeRunValue({ id, context, question: text(p.question), status: p.status as ResearchRun["status"], active_elapsed_ms: integer(p.active_elapsed_ms), event_cursor: 0, latest_event_cursor: integer(p.latest_event_cursor), activity: [], continuation_of: nullableUuid(p.continuation_of), clarification, clarification_id: clarificationId, result: null, error: p.error === null ? null : localized(p.error), synthetic: p.synthetic });
}
type Method = "submit" | "status" | "events" | "cancel" | "clarify" | "continue" | "list";
type Requests = { submit: Parameters<ResearchRunTransport["submit"]>[0]; status: Parameters<ResearchRunTransport["status"]>[0]; events: Parameters<ResearchRunTransport["events"]>[0]; cancel: Parameters<ResearchRunTransport["cancel"]>[0]; clarify: Parameters<ResearchRunTransport["clarify"]>[0]; continue: Parameters<ResearchRunTransport["continue"]>[0]; list: RunListRequest };
async function request(method: Method, supplied: unknown): Promise<Record<string, unknown>> {
  try {
    const raw = json(supplied);
    if (method === "submit") {
      const p = shape(raw, ["idempotency_key", "context", "question"]), c = shape(p.context, ["binding", "scope", "attachments", "pins"]), b = binding(c.binding);
      await parseCatalogueContractModel("EvidenceScope", c.scope); freezeRunContext(c as Requests["submit"]["context"]);
      return { investigation_id: b.investigation_id, conversation_id: b.conversation_id, revision_id: b.revision_id, expected_snapshot_id: b.snapshot_id, expected_payload_sha256: b.payload_sha256, question: text(p.question), idempotency_key: uuid(p.idempotency_key) };
    }
    if (method === "list") {
      const p = shape(raw, ["investigation_id", "conversation_id", "limit", "cursor"], ["investigation_id", "conversation_id"]);
      return { investigation_id: uuid(p.investigation_id), conversation_id: uuid(p.conversation_id), limit: integer(p.limit === undefined ? 25 : p.limit, 1, 500), cursor: cursor(p.cursor ?? null) };
    }
    const keys = ["run_id", "investigation_id", "conversation_id", ...(method === "events" ? ["after_cursor", "limit"] : []), ...(["cancel", "clarify", "continue"].includes(method) ? ["idempotency_key"] : []), ...(method === "clarify" ? ["answer", "clarification_id"] : [])];
    const p = shape(raw, keys, keys.filter(k => k !== "limit"));
    const result: Record<string, unknown> = { run_id: uuid(p.run_id), investigation_id: uuid(p.investigation_id), conversation_id: uuid(p.conversation_id) };
    if (method === "events") { result.after_cursor = integer(p.after_cursor); result.limit = integer(p.limit === undefined ? 100 : p.limit, 1, 500); }
    if (["cancel", "clarify", "continue"].includes(method)) result.idempotency_key = uuid(p.idempotency_key);
    if (method === "clarify") { result.answer = text(p.answer); result.clarification_id = uuid(p.clarification_id); }
    return result;
  } catch { return badRequest(); }
}
function addressMatches(value: ResearchRun, p: Record<string,unknown>): void {
  if (value.context.binding.investigation_id !== p.investigation_id || value.context.binding.conversation_id !== p.conversation_id) return invalid();
  if (p.run_id !== undefined && value.id !== p.run_id) return invalid();
}
async function parse(method: Method, value: unknown, p: Record<string, unknown>, original: unknown): Promise<unknown> {
  if (method === "events") {
    const v = shape(value, ["version", "run_id", "binding", "after_cursor", "next_cursor", "latest_event_cursor", "has_more", "events"]);
    if (v.version !== RESEARCH_RUNS_VERSION || v.run_id !== p.run_id || v.after_cursor !== p.after_cursor || !Array.isArray(v.events) || v.events.length > (p.limit as number) || typeof v.has_more !== "boolean") return invalid();
    const b = binding(v.binding), next = integer(v.next_cursor), latest = integer(v.latest_event_cursor), events = v.events.map(item => event(item, p.run_id as string));
    if (b.investigation_id !== p.investigation_id || b.conversation_id !== p.conversation_id || next !== (p.after_cursor as number) + events.length || latest < next || v.has_more !== (next < latest) || (v.has_more && events.length === 0) || events.some((item, i) => item.cursor !== (p.after_cursor as number) + i + 1 || (i > 0 && item.elapsed_ms < events[i - 1].elapsed_ms))) return invalid();
    return freezeRunValue({ run_id: p.run_id, binding: b, after_cursor: p.after_cursor, next_cursor: next, latest_event_cursor: latest, has_more: v.has_more, events });
  }
  if (method === "list") {
    const v = shape(value, ["version", "items", "next_cursor"]); if (v.version !== RESEARCH_RUNS_VERSION || !Array.isArray(v.items) || v.items.length > (p.limit as number)) return invalid();
    const items = await Promise.all(v.items.map(run)), next = cursor(v.next_cursor);
    if (new Set(items.map(item => item.id)).size !== items.length || (next !== null && (items.length === 0 || next === p.cursor))) return invalid();
    items.forEach(item => addressMatches(item, p)); return freezeRunValue({ items, next_cursor: next });
  }
  const v = shape(value, ["version", "run"]); if (v.version !== RESEARCH_RUNS_VERSION) return invalid(); const result = await run(v.run);
  addressMatches(result, method === "continue" ? { ...p, run_id: undefined } : p);
  if (method === "continue" && result.continuation_of !== p.run_id) return invalid();
  if (method === "submit") {
    const intended = (original as Requests["submit"]).context.binding;
    if (!sameRunBinding(intended, result.context.binding) || result.question !== (original as Requests["submit"]).question) return invalid();
  }
  return result;
}
function uniqueJson(input: string): unknown {
  const parsed: unknown = JSON.parse(input); let offset = 0;
  const space = () => { while (offset < input.length && /\s/.test(input[offset])) offset++; };
  function str(): string { const start = offset++; while (offset < input.length) { if (input[offset] === "\\") { offset += 2; continue; } if (input[offset++] === '"') return JSON.parse(input.slice(start, offset)) as string; } return invalid(); }
  function scan(depth: number): void { if (depth > 128) return invalid(); space(); const token = input[offset]; if (token === "{") { offset++; space(); const seen = new Set<string>(); if (input[offset] === "}") { offset++; return; } while (offset < input.length) { space(); const key = str(); if (seen.has(key)) return invalid(); seen.add(key); space(); offset++; scan(depth+1); space(); if (input[offset++] === "}") return; } } else if (token === "[") { offset++; space(); if (input[offset] === "]") { offset++; return; } while (offset < input.length) { scan(depth+1); space(); if (input[offset++] === "]") return; } } else if (token === '"') str(); else while (offset < input.length && !/[\s,}\]]/.test(input[offset])) offset++; }
  scan(0); return json(parsed);
}
const abortError = () => new DOMException("The research request was cancelled", "AbortError");
function aborted(signal?: AbortSignal): void { if (signal?.aborted) throw abortError(); }
async function discard(response: Response): Promise<void> { try { await response.body?.cancel(); } catch { /* Status remains authoritative. */ } }
async function cancellable<T>(pending: Promise<T>, signal?: AbortSignal, late?: (value: T) => void): Promise<T> {
  if (!signal) return pending;
  if (signal.aborted) { void pending.then(value => late?.(value), () => undefined); throw abortError(); }
  return new Promise<T>((resolve,reject) => { let cancelled = false; const cancel = () => { cancelled = true; reject(abortError()); }; signal.addEventListener("abort",cancel,{once:true}); void pending.then(value => { signal.removeEventListener("abort",cancel); if (cancelled) late?.(value); else resolve(value); },error => { signal.removeEventListener("abort",cancel); if (!cancelled) reject(error); }); });
}
async function bounded(response: Response, maximum: number, signal?: AbortSignal): Promise<unknown> {
  const length = response.headers.get("content-length"); if ((length !== null && (!/^\d+$/.test(length) || Number(length) > maximum)) || !response.body) { await discard(response); return invalid(); }
  const reader = response.body.getReader(), parts: Uint8Array[] = []; let total = 0;
  const cancel = () => { void reader.cancel().catch(() => undefined); }; signal?.addEventListener("abort",cancel,{once:true});
  try { while (true) { aborted(signal); const part = await cancellable(reader.read(),signal); aborted(signal); if (part.done) break; total += part.value.byteLength; if (total > maximum) { await reader.cancel(); return invalid(); } parts.push(part.value); } }
  finally { signal?.removeEventListener("abort",cancel); reader.releaseLock(); }
  const bytes = new Uint8Array(total); let offset = 0; for (const part of parts) { bytes.set(part,offset); offset += part.byteLength; } return uniqueJson(new TextDecoder("utf-8",{fatal:true}).decode(bytes));
}
const statusesByCode: Readonly<Record<number, readonly [string,string]>> = {401:["authentication_required","Sign in to continue"],403:["access_denied","Research access is restricted"],404:["not_found","This activity is unavailable"],409:["conflict","This activity has changed. Review its current state"],422:["invalid_request","Check the request and try again"],503:["runs_unavailable","The research service is unavailable"]};
export function createResearchRunTransport(options: { fetcher?: (path:string,init?:RequestInit)=>Promise<Response>; tokenProvider?:()=>string|undefined|Promise<string|undefined>; maxResponseBytes?:number } = {}): ServiceRunTransport {
  const fetcher = options.fetcher ?? ((path:string,init?:RequestInit)=>fetch(path,init)), maximum = options.maxResponseBytes ?? MAX_RUN_RESPONSE_BYTES;
  if (!Number.isSafeInteger(maximum) || maximum < 1 || maximum > MAX_RUN_RESPONSE_BYTES) throw new RangeError("Invalid research response byte bound");
  async function call(method: Method, supplied: unknown, signal?: AbortSignal): Promise<unknown> {
    aborted(signal); let original: unknown; try { original = json(supplied); } catch { return badRequest(); }
    const payload = await request(method,original); aborted(signal);
    if (new TextEncoder().encode(JSON.stringify(payload)).byteLength > MAX_RUN_REQUEST_BYTES) return badRequest();
    try {
      const token = await cancellable(Promise.resolve(options.tokenProvider?.()),signal); aborted(signal);
      if (token !== undefined && (typeof token !== "string" || !token || token.length > 8192 || /\s/.test(token))) throw new ResearchRunClientError("authentication_required","Sign in to continue",401);
      const response = await cancellable(fetcher(`/research/runs/${method}`,{method:"POST",credentials:"omit",cache:"no-store",redirect:"error",signal,headers:{Accept:"application/json","Content-Type":"application/json",...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify(payload)}),signal,value=>{void discard(value);});
      if (!response.ok) { void discard(response); const [code,message] = statusesByCode[response.status] ?? ["runs_unavailable","The research service is unavailable"]; throw new ResearchRunClientError(code,message,response.status); }
      const raw = await bounded(response,maximum,signal); aborted(signal); const result = await parse(method,raw,payload,original); aborted(signal); return result;
    } catch (error) { if (signal?.aborted || (error instanceof Error && error.name === "AbortError")) throw abortError(); if (error instanceof ResearchRunClientError) throw error; throw new ResearchRunClientError("invalid_response","The research response could not be verified"); }
  }
  return Object.fromEntries((["submit","status","events","cancel","clarify","continue","list"] as Method[]).map(method=>[method,(supplied:unknown,signal?:AbortSignal)=>call(method,supplied,signal)])) as unknown as ServiceRunTransport;
}
/** Client-side replay owns the exact original body/key, including expected context. */
export function runIntentBinding(intent: RunMutationIntent): RunContextBinding { return intent.method === "submit" ? intent.request.context.binding : intent.binding; }
