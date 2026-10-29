/** Fixed same-origin experiment transports; no execution or fixture fallback. */
export class ExperimentClientError extends Error {
  readonly code: string; readonly status_code: number;
  constructor(code: string, message: string, status_code = 503) { super(message); this.name = "ExperimentClientError"; this.code = code; this.status_code = status_code; }
}
export const MAX_EXPERIMENT_REQUEST_BYTES = 65536;
export const MAX_EXPERIMENT_RESPONSE_BYTES = 8 * 1024 * 1024;
export type ExperimentHttpOptions = {
  fetcher?: (path: string, init?: RequestInit) => Promise<Response>;
  tokenProvider?: () => string | undefined | Promise<string | undefined>;
  maxResponseBytes?: number; deadlineMs?: number;
};
const invalid = (): never => { throw new ExperimentClientError("invalid_response", "The experiment response could not be verified"); };
export const experimentRecord = (value: unknown): value is Record<string, any> => value !== null && typeof value === "object" && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value));
export function experimentJson(value: unknown, stack = new Set<object>(), depth = 0): unknown {
  if (depth > 128) return invalid();
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") { if (!value.isWellFormed()) return invalid(); return value; }
  if (typeof value === "number") { if (!Number.isFinite(value) || Number.isInteger(value) && !Number.isSafeInteger(value)) return invalid(); return value; }
  if ((!experimentRecord(value) && !Array.isArray(value)) || stack.has(value) || Object.getOwnPropertySymbols(value).length || Object.values(Object.getOwnPropertyDescriptors(value)).some(d => d.get || d.set)) return invalid();
  stack.add(value);
  const result = Array.isArray(value) ? Array.from(value, item => experimentJson(item, stack, depth + 1))
    : Object.fromEntries(Object.entries(value).map(([key, item]) => { if (!key.isWellFormed()) return invalid(); return [key, experimentJson(item, stack, depth + 1)]; }));
  stack.delete(value); return result;
}
export function freezeExperimentValue<T>(value: T): T {
  if (value !== null && typeof value === "object") { for (const item of Object.values(value)) freezeExperimentValue(item); Object.freeze(value); } return value;
}
/** Only review protocol objects use this hash; raw machine files remain bytes. */
export function experimentCanonical(value: unknown): string {
  const compare = (a: string, b: string): number => {
    const left = [...a].map(c => c.codePointAt(0)!), right = [...b].map(c => c.codePointAt(0)!);
    for (let i = 0; i < Math.min(left.length, right.length); i++) if (left[i] !== right[i]) return left[i] - right[i];
    return left.length - right.length;
  };
  const encode = (v: any): string => Array.isArray(v) ? `[${v.map(encode).join(",")}]`
    : v !== null && typeof v === "object" ? `{${Object.keys(v).sort(compare).map(key => `${JSON.stringify(key)}:${encode(v[key])}`).join(",")}}`
    : JSON.stringify(v);
  return encode(experimentJson(value));
}
export async function experimentSha256(value: string | Uint8Array): Promise<string> {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : new Uint8Array(value);
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(byte => byte.toString(16).padStart(2, "0")).join("");
}
function uniqueJson(input: string): unknown {
  const parsed: unknown = JSON.parse(input); let offset = 0;
  const space = () => { while (offset < input.length && /\s/.test(input[offset])) offset++; };
  function str(): string { const start = offset++; while (offset < input.length) { if (input[offset] === "\\") { offset += 2; continue; } if (input[offset++] === '"') return JSON.parse(input.slice(start, offset)) as string; } return invalid(); }
  function scan(depth: number): void {
    if (depth > 128) return invalid(); space(); const token = input[offset];
    if (token === "{") { offset++; space(); const seen = new Set<string>(); if (input[offset] === "}") { offset++; return; } while (offset < input.length) { space(); const key = str(); if (seen.has(key)) return invalid(); seen.add(key); space(); offset++; scan(depth + 1); space(); if (input[offset++] === "}") return; } }
    else if (token === "[") { offset++; space(); if (input[offset] === "]") { offset++; return; } while (offset < input.length) { scan(depth + 1); space(); if (input[offset++] === "]") return; } }
    else if (token === '"') str(); else while (offset < input.length && !/[\s,}\]]/.test(input[offset])) offset++;
  }
  scan(0); return experimentJson(parsed);
}
const abortError = () => new DOMException("The experiment request was cancelled", "AbortError");
function aborted(signal: AbortSignal): void { if (signal.aborted) throw abortError(); }
async function discard(response: Response): Promise<void> { try { await response.body?.cancel(); } catch { /* Keep the verified HTTP status. */ } }
async function cancellable<T>(promise: Promise<T>, signal: AbortSignal, late?: (value: T) => void): Promise<T> {
  if (signal.aborted) { void promise.then(v => late?.(v), () => undefined); throw abortError(); }
  return new Promise<T>((resolve, reject) => {
    let cancelled = false; const cancel = () => { cancelled = true; reject(abortError()); }; signal.addEventListener("abort", cancel, { once: true });
    void promise.then(value => { signal.removeEventListener("abort", cancel); if (cancelled) late?.(value); else resolve(value); }, error => { signal.removeEventListener("abort", cancel); if (!cancelled) reject(error); });
  });
}
async function bounded(response: Response, maximum: number, signal: AbortSignal): Promise<unknown> {
  const length = response.headers.get("content-length");
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > maximum) || !response.body) { void discard(response); return invalid(); }
  const reader = response.body.getReader(), parts: Uint8Array[] = []; let total = 0;
  const cancel = () => { void reader.cancel().catch(() => undefined); }; signal.addEventListener("abort", cancel, { once: true });
  try { while (true) { aborted(signal); const part = await cancellable(reader.read(), signal); aborted(signal); if (part.done) break; total += part.value.byteLength; if (total > maximum) { void reader.cancel().catch(() => undefined); return invalid(); } parts.push(part.value); } }
  finally { signal.removeEventListener("abort", cancel); reader.releaseLock(); }
  const bytes = new Uint8Array(total); let offset = 0; for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
  return uniqueJson(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
}
const actions = {
  review: ["create", "revise", "get", "status", "list", "approve", "dispatch", "events", "retry"],
  execution: ["capability", "status", "events", "cancel", "artifact"],
} as const;
const errors: Readonly<Record<number, readonly [string, string]>> = {
  401: ["authentication_required", "Sign in to continue"], 403: ["access_denied", "Experiment access is restricted"],
  404: ["not_found", "This experiment is unavailable"], 409: ["conflict", "The experiment changed; review its current version"],
  422: ["invalid_request", "Check the experiment request"], 429: ["rate_limited", "Wait before trying this action again"],
  503: ["unavailable", "Experiment services are unavailable"],
};
export function createExperimentHttp(options: ExperimentHttpOptions = {}, family: "review" | "execution" = "review") {
  const maximum = options.maxResponseBytes ?? MAX_EXPERIMENT_RESPONSE_BYTES, deadline = options.deadlineMs ?? 8000;
  if (!Number.isSafeInteger(maximum) || maximum < 1 || maximum > MAX_EXPERIMENT_RESPONSE_BYTES || !Number.isSafeInteger(deadline) || deadline < 1 || deadline > 8000) throw new RangeError("Invalid experiment response/deadline bound");
  const fetcher = options.fetcher ?? ((path: string, init?: RequestInit) => fetch(path, init));
  return async (action: string, supplied: unknown, signal?: AbortSignal): Promise<unknown> => {
    if (signal?.aborted) throw abortError(); let body: string;
    try { if (!(actions[family] as readonly string[]).includes(action)) throw new Error(); body = JSON.stringify(experimentJson(supplied)); if (new TextEncoder().encode(body).byteLength > MAX_EXPERIMENT_REQUEST_BYTES) throw new Error(); }
    catch { throw new ExperimentClientError("invalid_request", "The experiment request is invalid", 422); }
    const controller = new AbortController(); let timedOut = false;
    const forward = () => controller.abort(); signal?.addEventListener("abort", forward, { once: true });
    if (signal?.aborted) forward();
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, deadline);
    try {
      const token = await cancellable(Promise.resolve(options.tokenProvider?.()), controller.signal); aborted(controller.signal);
      if (token !== undefined && (typeof token !== "string" || !token || token.length > 8192 || /\s/.test(token))) throw new ExperimentClientError("authentication_required", "Sign in to continue", 401);
      const path = family === "review" ? "/research/experiments/" : "/research/experiment-executions/";
      const response = await cancellable(fetcher(path + action, { method: "POST", credentials: "omit", cache: "no-store", redirect: "error", signal: controller.signal,
        headers: { Accept: "application/json", "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body }), controller.signal, value => { void discard(value); });
      if (!response.ok) { void discard(response); const [code, message] = errors[response.status] ?? ["unavailable", "Experiment services are unavailable"]; throw new ExperimentClientError(code, message, response.status); }
      const result = await bounded(response, maximum, controller.signal); aborted(controller.signal); return result;
    } catch (error) {
      if (timedOut) throw new ExperimentClientError("request_timeout", "The experiment request timed out; its current state is uncertain");
      if (signal?.aborted || error instanceof Error && error.name === "AbortError") throw abortError();
      if (error instanceof ExperimentClientError) throw error; return invalid();
    } finally { clearTimeout(timer); signal?.removeEventListener("abort", forward); }
  };
}
