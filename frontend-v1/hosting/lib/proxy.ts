import { hostIdentity, mintInternalToken } from "./identity.ts";
import { requestAllowed, type HostSettings } from "./settings.ts";

const MAX_BODY = 65536, MAX_RESPONSE = 8 * 1024 * 1024;
const READ_PATHS = new Set([
  "/v1/runtime", "/catalogue/snapshots", "/catalogue/overview", "/catalogue/list", "/catalogue/open",
  "/catalogue/coverage", "/catalogue/query", "/catalogue/relationships", "/catalogue/analysis/get-published",
  ...["list", "get", "conversations/list", "conversations/get", "context/get", "operations/get"].map(p => "/research/investigations/" + p),
  ...["status", "events", "list", "cancel"].map(p => "/research/runs/" + p),
  ...["status", "events", "list", "cancel"].map(p => "/research/answers/" + p),
  ...["list", "open", "page", "export"].map(p => "/research/evidence/" + p),
  ...["get", "status", "list", "events"].map(p => "/research/experiments/" + p),
  ...["capability", "status", "events", "cancel", "artifact"].map(p => "/research/experiment-executions/" + p),
]);
export function proxyPath(path: string, method: string): boolean {
  return READ_PATHS.has(path) && (path === "/v1/runtime" ? method === "GET" : method === "POST");
}
function error(status: number, code: string) {
  return Response.json({ error: { code, message: "The independent v1 service is unavailable" } }, {
    status, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
  });
}
export class HostBodyTimeout extends Error {}
export async function boundedBytes(body: ReadableStream<Uint8Array> | null, maximum: number, milliseconds = 15000): Promise<Uint8Array> {
  if (!body) return new Uint8Array();
  const reader = body.getReader(), parts: Uint8Array[] = []; let total = 0;
  let timedOut = false;
  const deadline = setTimeout(() => { timedOut = true; void reader.cancel().catch(() => undefined); }, milliseconds);
  try {
    while (true) {
      const part = await reader.read(); if (timedOut) throw new HostBodyTimeout(); if (part.done) break;
      total += part.value.byteLength;
      if (total > maximum) { await reader.cancel(); throw new RangeError("Body limit"); }
      parts.push(part.value);
    }
  } finally { clearTimeout(deadline); reader.releaseLock(); }
  const result = new Uint8Array(total); let offset = 0;
  for (const part of parts) { result.set(part, offset); offset += part.byteLength; }
  return result;
}
export async function proxyRequest(request: Request, settings: HostSettings,
    session: () => Promise<unknown>, fetcher: typeof fetch = fetch): Promise<Response> {
  if (!requestAllowed(request, settings)) return error(403, "origin_denied");
  const url = new URL(request.url);
  if (url.search || !proxyPath(url.pathname, request.method)) return error(404, "route_unavailable");
  let identity;
  try { const value = await session(); identity = hostIdentity((value as { v1Identity?: unknown } | null)?.v1Identity); }
  catch { return error(401, "authentication_required"); }
  if (!identity) return error(401, "authentication_required");
  let body: Uint8Array | undefined;
  if (request.method === "POST") {
    if (request.headers.get("content-type")?.split(";")[0].trim() !== "application/json") return error(415, "invalid_media_type");
    const length = request.headers.get("content-length");
    if (length !== null && (!/^\d+$/.test(length) || Number(length) > MAX_BODY)) return error(413, "request_too_large");
    try { body = await boundedBytes(request.body, MAX_BODY); }
    catch (failure) { return failure instanceof HostBodyTimeout ? error(408, "request_deadline") : error(413, "request_too_large"); }
  }
  try {
    const upstream = await fetcher(settings.apiOrigin + url.pathname, {
      method: request.method, redirect: "error", cache: "no-store", signal: AbortSignal.timeout(15000),
      headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}),
        Authorization: "Bearer " + await mintInternalToken(identity, settings) },
      ...(body ? { body: body as BodyInit } : {}),
    });
    if (upstream.status >= 300 && upstream.status < 400) { await upstream.body?.cancel(); return error(502, "upstream_redirect_denied"); }
    const length = upstream.headers.get("content-length");
    if (length !== null && (!/^\d+$/.test(length) || Number(length) > MAX_RESPONSE)) { await upstream.body?.cancel(); return error(502, "upstream_too_large"); }
    let responseBody;
    try { responseBody = await boundedBytes(upstream.body, MAX_RESPONSE); }
    catch { return error(502, "upstream_body_unavailable"); }
    const headers = new Headers({ "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
    for (const name of ["content-type", "content-disposition", "x-export-truncated"]) {
      const value = upstream.headers.get(name); if (value !== null) headers.set(name, value);
    }
    return new Response(responseBody as BodyInit, { status: upstream.status, headers });
  } catch { return error(503, "backend_unavailable"); }
}
