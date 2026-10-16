/** C15 v1 bootstrap boundary. No sample data, storage, cookie or legacy discovery. */
export const RUNTIME_VERSION = "ocean-v1-runtime-v1" as const;
export const MODE_VERSION = "ocean-v1-mode-v1" as const;
export const MAX_RUNTIME_BYTES = 64 * 1024;
export const RUNTIME_DESTINATIONS = ["research", "catalogue", "tools", "settings", "administration", "feedback", "about"] as const;
export type RuntimeDestination = typeof RUNTIME_DESTINATIONS[number];
export type ShellDestination = RuntimeDestination | "admin";
export type RuntimeMode = "service" | "synthetic-preview";
export const REQUIRED_PERMISSIONS: Readonly<Record<RuntimeDestination, readonly string[]>> = Object.freeze({
  research: Object.freeze(["chat:use"]), catalogue: Object.freeze(["data:read"]), tools: Object.freeze(["data:read"]),
  settings: Object.freeze(["profile:read"]), administration: Object.freeze(["users:manage"]),
  feedback: Object.freeze(["feedback:write"]), about: Object.freeze(["profile:read"]),
});
export type RuntimeIdentity = {
  id: string; display_name: string | null; role: "viewer" | "researcher" | "admin";
  account_type: "research" | "commercial" | "internal"; status: "active"; permissions: string[];
};
export type RuntimeCapability = {
  status: "ready" | "unavailable" | "disabled" | "forbidden";
  reason: string | null; required_permissions: string[];
};
export type RuntimeBootstrap = {
  version: typeof RUNTIME_VERSION; deployment: "v1"; identity: RuntimeIdentity;
  permission_revision: string; capabilities: Record<RuntimeDestination, RuntimeCapability>;
};
export type RuntimeState = { status: "loading" } | { status: "ready"; bootstrap: RuntimeBootstrap }
  | { status: "unauthorized" | "forbidden" | "unavailable" | "error"; message: string; retryable: boolean };
export type Fetcher = (input: string, init?: RequestInit) => Promise<Response>;
export type RuntimeTransport = { load(signal?: AbortSignal): Promise<RuntimeState> };

export class RuntimeContractError extends Error {
  constructor(message = "The v1 runtime response is invalid") { super(message); this.name = "RuntimeContractError"; }
}
function fail(message?: string): never { throw new RuntimeContractError(message); }
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    && [Object.prototype, null].includes(Object.getPrototypeOf(value));
}
function exact(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (!record(value) || Object.keys(value).length !== keys.length || keys.some((key) => !Object.hasOwn(value, key))) return fail();
  return value;
}
function boundedText(value: unknown, maximum: number, nullable = false): string | null {
  if (nullable && value === null) return null;
  if (typeof value !== "string" || Array.from(value).length > maximum || (!nullable && !value.trim())) return fail();
  return value;
}
const identifier = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
const permission = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
function permissions(value: unknown): string[] {
  if (!Array.isArray(value) || value.length > 256 || value.some((v) => typeof v !== "string" || !permission.test(v)) || new Set(value).size !== value.length) return fail();
  return [...value] as string[];
}

/** Validate then copy every accepted field; identity never comes from preferences. */
export function parseRuntimeBootstrap(value: unknown): RuntimeBootstrap {
  const root = exact(value, ["version", "deployment", "identity", "permission_revision", "capabilities"]);
  if (root.version !== RUNTIME_VERSION || root.deployment !== "v1" || typeof root.permission_revision !== "string" || !identifier.test(root.permission_revision)) return fail();
  const identity = exact(root.identity, ["id", "display_name", "role", "account_type", "status", "permissions"]);
  if (typeof identity.id !== "string" || !/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(identity.id)
    || !["viewer", "researcher", "admin"].includes(identity.role as string)
    || !["research", "commercial", "internal"].includes(identity.account_type as string)
    || identity.status !== "active") return fail();
  const actualPermissions = permissions(identity.permissions);
  const displayName = boundedText(identity.display_name, 255, true);
  const rawCapabilities = exact(root.capabilities, RUNTIME_DESTINATIONS);
  const capabilities = {} as Record<RuntimeDestination, RuntimeCapability>;
  for (const destination of RUNTIME_DESTINATIONS) {
    const capability = exact(rawCapabilities[destination], ["status", "reason", "required_permissions"]);
    if (!["ready", "unavailable", "disabled", "forbidden"].includes(capability.status as string)) return fail();
    const required = permissions(capability.required_permissions);
    const fixed = REQUIRED_PERMISSIONS[destination];
    if (required.length !== fixed.length || fixed.some((p) => !required.includes(p))) return fail();
    if (capability.status === "ready" && required.some((p) => !actualPermissions.includes(p))) return fail();
    const reason = boundedText(capability.reason, 1000, true);
    if (capability.status !== "ready" && (reason === null || !reason.trim())) return fail();
    capabilities[destination] = { status: capability.status as RuntimeCapability["status"], reason, required_permissions: required };
  }
  return {
    version: RUNTIME_VERSION, deployment: "v1", permission_revision: root.permission_revision,
    identity: { id: identity.id, display_name: displayName, role: identity.role as RuntimeIdentity["role"],
      account_type: identity.account_type as RuntimeIdentity["account_type"], status: "active", permissions: actualPermissions },
    capabilities,
  };
}

function destinationKey(destination: RuntimeDestination | ShellDestination): RuntimeDestination {
  return destination === "admin" ? "administration" : destination;
}
export function getCapability(bootstrap: RuntimeBootstrap, destination: RuntimeDestination | ShellDestination): RuntimeCapability | undefined {
  return bootstrap.capabilities[destinationKey(destination)];
}
export function routeAccessible(bootstrap: RuntimeBootstrap, destination: RuntimeDestination | ShellDestination): boolean {
  const key = destinationKey(destination), capability = getCapability(bootstrap, key), required = REQUIRED_PERMISSIONS[key];
  return !!required && !!capability && bootstrap.identity.status === "active"
    && capability.status !== "forbidden" && required.every((p) => bootstrap.identity.permissions.includes(p));
}
export const capabilityVisible = routeAccessible;
export function capabilityReady(bootstrap: RuntimeBootstrap, destination: RuntimeDestination | ShellDestination): boolean {
  return routeAccessible(bootstrap, destination) && getCapability(bootstrap, destination)?.status === "ready";
}
const paths: Record<ShellDestination, string> = {
  research: "/?view=research", catalogue: "/?view=catalogue", tools: "/?view=tools", settings: "/?view=settings",
  administration: "/admin", admin: "/admin", feedback: "/feedback", about: "/about",
};
export function destinationPath(destination: RuntimeDestination | ShellDestination): string {
  return paths[destination === "administration" ? "admin" : destination];
}
export function destinationFromPath(pathname: string, fallback: ShellDestination = "research"): ShellDestination {
  const path = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname;
  return (["administration", "feedback", "about"] as const).find((key) => paths[key] === path) ?? fallback;
}
export function destinationFromLocation(pathname: string, search: string, fallback: ShellDestination = "research"): ShellDestination {
  if (pathname !== "/") return destinationFromPath(pathname, fallback);
  const view = new URLSearchParams(search).get("view");
  return ["research", "catalogue", "tools", "settings"].includes(view ?? "") ? view as ShellDestination : fallback;
}

/** JSON.parse validates syntax; this bounded second pass rejects duplicate keys. */
function uniqueJson(text: string): unknown {
  const value: unknown = JSON.parse(text);
  let offset = 0;
  const space = () => { while (/\s/.test(text[offset] ?? "") && offset < text.length) offset++; };
  function string(): string {
    const start = offset++;
    while (offset < text.length) {
      if (text[offset] === "\\") { offset += 2; continue; }
      if (text[offset++] === '"') return JSON.parse(text.slice(start, offset)) as string;
    }
    return fail();
  }
  function scan(depth: number): void {
    if (depth > 16) return fail();
    space(); const token = text[offset];
    if (token === "{") {
      offset++; space(); const keys = new Set<string>();
      if (text[offset] === "}") { offset++; return; }
      while (offset < text.length) {
        space(); const key = string();
        if (keys.has(key)) return fail("Duplicate v1 runtime JSON key");
        keys.add(key); space(); offset++; scan(depth + 1); space();
        if (text[offset++] === "}") return;
      }
    } else if (token === "[") {
      offset++; space(); if (text[offset] === "]") { offset++; return; }
      while (offset < text.length) { scan(depth + 1); space(); if (text[offset++] === "]") return; }
    } else if (token === '"') { string(); }
    else { while (offset < text.length && !/[\s,}\]]/.test(text[offset])) offset++; }
  }
  scan(0); return value;
}

async function boundedJson(response: Response, maximum: number): Promise<unknown> {
  const length = response.headers.get("content-length");
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > maximum)) { await discardBody(response); return fail(); }
  if (!response.body) return fail();
  const reader = response.body.getReader(), chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maximum) { await reader.cancel(); return fail("The v1 runtime response exceeds its byte limit"); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(total); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  try { return uniqueJson(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); }
  catch { return fail("The v1 runtime response is not unambiguous UTF-8 JSON"); }
}

async function discardBody(response: Response): Promise<void> {
  try { await response.body?.cancel(); } catch { /* The status still remains authoritative. */ }
}

const failure = (status: "unauthorized" | "forbidden" | "unavailable" | "error"): RuntimeState => ({
  status, retryable: true, message: status === "unauthorized" ? "Sign in through the v1 identity service."
    : status === "forbidden" ? "The current account cannot access this workspace."
    : status === "unavailable" ? "The v1 service is unavailable." : "The v1 service could not be reached. Retry to continue.",
});
export function createRuntimeTransport(options: { fetcher?: Fetcher; tokenProvider?: () => string | undefined | Promise<string | undefined> } = {}): RuntimeTransport {
  const fetcher: Fetcher = options.fetcher ?? ((input, init) => fetch(input, init));
  return {
    async load(signal) {
      try {
        const token = await options.tokenProvider?.();
        if (signal?.aborted) throw new DOMException("The runtime request was cancelled", "AbortError");
        if (token !== undefined && (typeof token !== "string" || !token || token.length > 8192 || /\s/.test(token))) return failure("unauthorized");
        const response = await fetcher("/v1/runtime", {
          method: "GET", credentials: "omit", cache: "no-store", redirect: "error", signal,
          headers: { Accept: "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        });
        if (signal?.aborted) { await discardBody(response); throw new DOMException("The runtime request was cancelled", "AbortError"); }
        if (!response.ok) await discardBody(response);
        if (response.status === 401) return failure("unauthorized");
        if (response.status === 403) return failure("forbidden");
        if ([404, 409, 410, 501, 503].includes(response.status)) return failure("unavailable");
        if (!response.ok) return failure("error");
        const bootstrap = parseRuntimeBootstrap(await boundedJson(response, MAX_RUNTIME_BYTES));
        if (signal?.aborted) throw new DOMException("The runtime request was cancelled", "AbortError");
        return { status: "ready", bootstrap };
      } catch (error) {
        if (signal?.aborted) throw error;
        return failure(error instanceof RuntimeContractError || error instanceof SyntaxError ? "unavailable" : "error");
      }
    },
  };
}

export function isLoopbackHostname(hostname: string): boolean {
  return ["localhost", "127.0.0.1", "[::1]", "::1"].includes(hostname.toLowerCase());
}
export function parseRuntimeMode(value: unknown, context: { hostname: string; trustedServerSelection: boolean }): RuntimeMode {
  const mode = exact(value, ["version", "mode"]);
  if (mode.version !== MODE_VERSION || !["service", "synthetic-preview"].includes(mode.mode as string)) return fail();
  if (mode.mode === "synthetic-preview" && (!isLoopbackHostname(context.hostname) || context.trustedServerSelection !== true)) return fail("Synthetic preview requires explicit loopback server selection");
  return mode.mode as RuntimeMode;
}
export async function loadRuntimeMode(options: { fetcher?: Fetcher; hostname: string; signal?: AbortSignal }): Promise<RuntimeMode> {
  const fetcher: Fetcher = options.fetcher ?? ((input, init) => fetch(input, init));
  const response = await fetcher("/_ocean/runtime-mode", {
    method: "GET", credentials: "omit", cache: "no-store", redirect: "error", signal: options.signal,
    headers: { Accept: "application/json" },
  });
  if (options.signal?.aborted) { await discardBody(response); throw new DOMException("The runtime mode request was cancelled", "AbortError"); }
  if (!response.ok) await discardBody(response);
  if (response.status === 404) return "service";
  if (!response.ok) return fail("The v1 runtime mode is unavailable");
  return parseRuntimeMode(await boundedJson(response, 2048), { hostname: options.hostname, trustedServerSelection: true });
}
