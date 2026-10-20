/** Strict transport shared only by the independent answer/evidence API clients. */
export class ResearchEvidenceClientError extends Error {
  readonly code: string; readonly status_code: number;
  constructor(code: string, message: string, status_code = 503) { super(message); this.name = "ResearchEvidenceClientError"; this.code = code; this.status_code = status_code; }
}
export const MAX_EVIDENCE_RESPONSE_BYTES = 8 * 1024 * 1024;
export const MAX_EVIDENCE_REQUEST_BYTES = 65536;
function invalid(): never { throw new ResearchEvidenceClientError("invalid_response", "The answer or evidence response could not be verified"); }
function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value)); }
export function evidenceJson(value: unknown, stack = new Set<object>(), depth = 0): unknown {
  if (depth > 128) return invalid();
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") { if (!value.isWellFormed()) return invalid(); return value; }
  if (typeof value === "number") { if (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value))) return invalid(); return value; }
  if ((!object(value) && !Array.isArray(value)) || stack.has(value) || Object.getOwnPropertySymbols(value).length || Object.values(Object.getOwnPropertyDescriptors(value)).some(d => d.get || d.set)) return invalid();
  stack.add(value);
  const result = Array.isArray(value) ? Array.from(value, item => evidenceJson(item, stack, depth + 1))
    : Object.fromEntries(Object.entries(value).map(([key, item]) => { if (!key.isWellFormed()) return invalid(); return [key, evidenceJson(item, stack, depth + 1)]; }));
  stack.delete(value); return result;
}
function uniqueJson(input: string): unknown {
  const parsed: unknown = JSON.parse(input); let offset = 0;
  const space = () => { while (offset < input.length && /\s/.test(input[offset])) offset++; };
  function str(): string { const start = offset++; while (offset < input.length) { if (input[offset] === "\\") { offset += 2; continue; } if (input[offset++] === '"') return JSON.parse(input.slice(start, offset)) as string; } return invalid(); }
  function scan(depth: number): void { if (depth > 128) return invalid(); space(); const token = input[offset]; if (token === "{") { offset++; space(); const seen = new Set<string>(); if (input[offset] === "}") { offset++; return; } while (offset < input.length) { space(); const key = str(); if (seen.has(key)) return invalid(); seen.add(key); space(); offset++; scan(depth+1); space(); if (input[offset++] === "}") return; } } else if (token === "[") { offset++; space(); if (input[offset] === "]") { offset++; return; } while (offset < input.length) { scan(depth+1); space(); if (input[offset++] === "]") return; } } else if (token === '"') str(); else while (offset < input.length && !/[\s,}\]]/.test(input[offset])) offset++; }
  scan(0); return evidenceJson(parsed);
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
export type EvidenceHttpAction = "answers/submit" | "answers/status" | "answers/events" | "answers/cancel" | "answers/list" | "evidence/list" | "evidence/open" | "evidence/page" | "evidence/export";
const actions: readonly EvidenceHttpAction[] = ["answers/submit", "answers/status", "answers/events", "answers/cancel", "answers/list", "evidence/list", "evidence/open", "evidence/page", "evidence/export"];
export type EvidenceHttpOptions = { fetcher?: (path: string, init?: RequestInit) => Promise<Response>; tokenProvider?: () => string | undefined | Promise<string | undefined>; maxResponseBytes?: number };
const httpErrors: Readonly<Record<number, readonly [string, string]>> = {401:["authentication_required","Sign in to continue"],403:["access_denied","Answer or evidence access is restricted"],404:["not_found","This answer or evidence is unavailable"],409:["conflict","This view has changed. Check its current state"],422:["invalid_request","Check the request and try again"],503:["unavailable","Answer or evidence services are unavailable"]};
export function createEvidenceHttp(options: EvidenceHttpOptions = {}) {
  const maximum = options.maxResponseBytes ?? MAX_EVIDENCE_RESPONSE_BYTES;
  if (!Number.isSafeInteger(maximum) || maximum < 1 || maximum > MAX_EVIDENCE_RESPONSE_BYTES) throw new RangeError("Invalid evidence response bound");
  const fetcher = options.fetcher ?? ((path: string, init?: RequestInit) => fetch(path, init));
  return async (action: EvidenceHttpAction, supplied: unknown, signal?: AbortSignal): Promise<unknown> => {
    aborted(signal); let body: string;
    try { if (!actions.includes(action)) throw new Error(); body = JSON.stringify(evidenceJson(supplied)); if (new TextEncoder().encode(body).byteLength > MAX_EVIDENCE_REQUEST_BYTES) throw new Error(); }
    catch { throw new ResearchEvidenceClientError("invalid_request", "The answer or evidence request is invalid", 422); }
    try {
      const token = await cancellable(Promise.resolve(options.tokenProvider?.()), signal); aborted(signal);
      if (token !== undefined && (typeof token !== "string" || !token || token.length > 8192 || /\s/.test(token))) throw new ResearchEvidenceClientError("authentication_required", "Sign in to continue", 401);
      const response = await cancellable(fetcher(`/research/${action}`, { method: "POST", credentials: "omit", cache: "no-store", redirect: "error", signal,
        headers: { Accept: "application/json", "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body }), signal, value => { void discard(value); });
      if (!response.ok) { void discard(response); const [code, message] = httpErrors[response.status] ?? ["unavailable", "Answer or evidence services are unavailable"]; throw new ResearchEvidenceClientError(code, message, response.status); }
      const result = await bounded(response, maximum, signal); aborted(signal); return result;
    } catch (error) { if (signal?.aborted || (error instanceof Error && error.name === "AbortError")) throw abortError(); if (error instanceof ResearchEvidenceClientError) throw error; return invalid(); }
  };
}
