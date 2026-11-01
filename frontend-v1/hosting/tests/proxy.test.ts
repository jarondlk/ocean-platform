import assert from "node:assert/strict";
import test from "node:test";
import { jwtVerify } from "jose";
import { boundedBytes, HostBodyTimeout, proxyPath, proxyRequest } from "../lib/proxy.ts";
import { SETTINGS, IDENTITY, request } from "./fixtures.ts";
const session = async () => ({ v1Identity: IDENTITY });
const post = (path: string, body = "{}", headers: Record<string, string> = {}) => request(path, { method: "POST", body, headers: { "Content-Type": "application/json", ...headers } });

test("actual proxy replaces caller auth/cookies and limits outgoing headers to the independent API", async () => {
  let count = 0;
  const response = await proxyRequest(post("/research/investigations/list", "{}", {
    Authorization: "Bearer attacker", Cookie: "legacy-session=do-not-forward", "X-Forwarded-For": "attacker", "X-Owner-Id": "attacker",
  }), SETTINGS, session, (async (url, init) => {
    count++; assert.equal(url, "http://127.0.0.1:8000/research/investigations/list");
    const headers = new Headers(init!.headers);
    assert.deepEqual([...headers.keys()].sort(), ["accept", "authorization", "content-type"]);
    assert.notEqual(headers.get("authorization"), "Bearer attacker");
    const { payload } = await jwtVerify(headers.get("authorization")!.slice(7), new TextEncoder().encode(SETTINGS.internalSecret), { issuer: SETTINGS.issuer, audience: SETTINGS.audience });
    assert.equal(payload.sub, IDENTITY.subject); assert.equal(payload.role, undefined);
    assert.equal(init!.redirect, "error"); assert.equal(init!.cache, "no-store");
    return new Response('{"version":"test-only-response"}', { status: 403, headers: {
      "Content-Type": "application/json", "Set-Cookie": "backend-secret=never-forward", Location: "https://evil.invalid",
      "X-Private-Diagnostic": "hidden", "Content-Disposition": "attachment; filename=test.json",
    } });
  }) as typeof fetch);
  assert.equal(count, 1); assert.equal(response.status, 403);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("set-cookie"), null); assert.equal(response.headers.get("location"), null);
  assert.equal(response.headers.get("x-private-diagnostic"), null); assert.match(response.headers.get("content-disposition")!, /test.json/);
});

for (const path of ["/research/runs/submit", "/research/runs/clarify", "/research/runs/continue", "/research/answers/submit", "/research/experiments/approve", "/research/experiments/dispatch", "/research/investigations/create", "/research/investigations/context/change", "/admin", "/me", "/chat", "/catalogue/list?target=legacy"]) {
  test(`read-only host denies unconfigured write/admin/proxy destination ${path}`, async () => {
    let called = false;
    const response = await proxyRequest(post(path), SETTINGS, session, (async () => { called = true; throw new Error(); }) as typeof fetch);
    assert.equal(response.status, 404); assert.equal(called, false);
  });
}
test("saved read and cancellation endpoints are admitted independently of new dispatch", () => {
  for (const path of ["/research/runs/status", "/research/runs/cancel", "/research/answers/list", "/research/evidence/open", "/research/experiment-executions/cancel", "/research/experiment-executions/artifact"]) assert(proxyPath(path, "POST"));
  assert(proxyPath("/v1/runtime", "GET")); assert.equal(proxyPath("/v1/runtime", "POST"), false); assert.equal(proxyPath("/catalogue/list", "GET"), false);
});
test("authentication and exact-origin failures occur before any upstream call", async () => {
  let count = 0; const fetcher = (async () => { count++; return new Response("{}"); }) as typeof fetch;
  assert.equal((await proxyRequest(post("/catalogue/list"), SETTINGS, async () => null, fetcher)).status, 401);
  assert.equal((await proxyRequest(post("/catalogue/list"), SETTINGS, async () => { throw new Error(); }, fetcher)).status, 401);
  assert.equal((await proxyRequest(post("/catalogue/list", "{}", { Origin: "https://oceaninfobio.com" }), SETTINGS, session, fetcher)).status, 403);
  assert.equal(count, 0);
});
test("body/media/response bounds reject deceptive Content-Length and streaming overflow", async () => {
  let count = 0; const fetcher = (async () => { count++; return new Response("{}"); }) as typeof fetch;
  assert.equal((await proxyRequest(post("/catalogue/list", "{}", { "Content-Type": "text/plain" }), SETTINGS, session, fetcher)).status, 415);
  for (const value of ["-1", "not-a-size", "65537"]) assert.equal((await proxyRequest(post("/catalogue/list", "{}", { "Content-Length": value }), SETTINGS, session, fetcher)).status, 413);
  assert.equal((await proxyRequest(post("/catalogue/list", "x".repeat(65537)), SETTINGS, session, fetcher)).status, 413);
  assert.equal(count, 0);
  const tooLarge = await proxyRequest(post("/catalogue/list"), SETTINGS, session, (async () => new Response("{}", { headers: { "Content-Length": "8388609" } })) as typeof fetch);
  assert.equal(tooLarge.status, 502);
  const redirected = await proxyRequest(post("/catalogue/list"), SETTINGS, session, (async () => new Response(null, { status: 302, headers: { Location: "https://evil.invalid" } })) as typeof fetch);
  assert.equal(redirected.status, 502);
  const unavailable = await proxyRequest(post("/catalogue/list"), SETTINGS, session, (async () => { throw new Error("secret diagnostics"); }) as typeof fetch);
  assert.equal(unavailable.status, 503); assert.doesNotMatch(await unavailable.text(), /secret diagnostics/);
});
test("body reader cancels a stalled request and rejects streamed overflow within its deadline", async () => {
  let cancelled = false;
  const stalled = new ReadableStream<Uint8Array>({ cancel() { cancelled = true; } });
  await assert.rejects(boundedBytes(stalled, 100, 5), HostBodyTimeout); assert(cancelled);
  let overflowCancelled = false;
  const overflow = new ReadableStream<Uint8Array>({ start(c) { c.enqueue(new Uint8Array(101)); }, cancel() { overflowCancelled = true; } });
  await assert.rejects(boundedBytes(overflow, 100), RangeError); assert(overflowCancelled);
});
