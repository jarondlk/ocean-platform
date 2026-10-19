import assert from "node:assert/strict";
import test from "node:test";
import {
  MODE_VERSION, RUNTIME_VERSION, MAX_RUNTIME_BYTES, REQUIRED_PERMISSIONS, RUNTIME_DESTINATIONS,
  RuntimeContractError, capabilityReady, capabilityVisible, createRuntimeTransport, destinationFromLocation,
  destinationFromPath, destinationPath, isLoopbackHostname, loadRuntimeMode, parseRuntimeBootstrap,
  parseRuntimeMode, routeAccessible,
} from "../src/runtime.ts";

function bootstrap() {
  const permissions = ["chat:use", "data:read", "profile:read", "feedback:write"];
  return {
    version: RUNTIME_VERSION, deployment: "v1",
    identity: { id: "12345678-1234-1234-1234-123456789abc", display_name: "Synthetic service identity", role: "researcher", account_type: "research", status: "active", permissions },
    permission_revision: "permissions-1",
    capabilities: Object.fromEntries(RUNTIME_DESTINATIONS.map((key) => [key, {
      status: REQUIRED_PERMISSIONS[key].every((p) => permissions.includes(p)) ? "unavailable" : "forbidden",
      reason: "component_pending" as string | null, required_permissions: [...REQUIRED_PERMISSIONS[key]],
    }])),
  };
}
function json(value: unknown, options?: ResponseInit) { return new Response(JSON.stringify(value), options); }

test("bootstrap exact fields are validated and copied without changing input", () => {
  const input = bootstrap(), before = structuredClone(input);
  const parsed = parseRuntimeBootstrap(input);
  assert.deepEqual(parsed, input); assert.deepEqual(input, before);
  parsed.identity.permissions.push("users:manage"); parsed.capabilities.about.required_permissions.length = 0;
  assert.deepEqual(input, before);
});

const runCapability = () => ({ version: "research-runs-v1", transport: "http-v1", submit_enabled: true, dispatch_enabled: true, synthesis: "unavailable", reason: null as string | null });
test("run discovery is optional and copied only from the exact verified runtime block", () => {
  assert.equal(parseRuntimeBootstrap(bootstrap()).research_runs, undefined);
  const input = { ...bootstrap(), research_runs: runCapability() }, parsed = parseRuntimeBootstrap(input);
  assert.deepEqual(parsed.research_runs, input.research_runs); assert.notEqual(parsed.research_runs, input.research_runs);
  input.research_runs.submit_enabled = false; assert.equal(parsed.research_runs!.submit_enabled, true);
  const disabled = { ...bootstrap(), research_runs: { ...runCapability(), transport: "unavailable", submit_enabled: false, dispatch_enabled: false, reason: "Execution is not configured" } };
  assert.equal(parseRuntimeBootstrap(disabled).research_runs!.transport, "unavailable");
  const paused = { ...bootstrap(), research_runs: { ...runCapability(), submit_enabled: false, dispatch_enabled: false, reason: "New work is paused" } };
  assert.equal(parseRuntimeBootstrap(paused).research_runs!.transport, "http-v1");
});
for (const [label, change] of [
  ["old version", (value: any) => { value.version = "old"; }], ["unknown transport", (value: any) => { value.transport = "fixture"; }],
  ["endpoint injection", (value: any) => { value.endpoint = "https://untrusted.invalid"; }], ["synthesis claim", (value: any) => { value.synthesis = "ready"; }],
  ["nonboolean flag", (value: any) => { value.dispatch_enabled = 1; }], ["missing flag", (value: any) => { delete value.submit_enabled; }],
  ["submit without dispatch", (value: any) => { value.dispatch_enabled = false; }], ["unavailable with submit", (value: any) => { value.transport = "unavailable"; value.reason = "Stopped"; }],
  ["unavailable without reason", (value: any) => { value.transport = "unavailable"; value.submit_enabled = false; value.dispatch_enabled = false; }],
] as const) test(`run discovery rejects ${label}`, () => { const capability = runCapability(); change(capability); assert.throws(() => parseRuntimeBootstrap({ ...bootstrap(), research_runs: capability }), RuntimeContractError); });
test("a run HTTP capability cannot restore missing research permissions", () => {
  for (const permission of ["chat:use", "data:read"]) { const input = { ...bootstrap(), research_runs: runCapability() }; input.identity.permissions = input.identity.permissions.filter(value => value !== permission); assert.throws(() => parseRuntimeBootstrap(input), RuntimeContractError); }
});

const malformed: [string, (v: ReturnType<typeof bootstrap>) => void][] = [
  ["foreign mode field", (v) => Object.assign(v, { mode: "preview" })],
  ["old version", (v) => { v.version = "old" as typeof RUNTIME_VERSION; }],
  ["legacy deployment", (v) => { v.deployment = "legacy"; }],
  ["invalid UUID", (v) => { v.identity.id = "admin"; }],
  ["suspended identity", (v) => { v.identity.status = "suspended"; }],
  ["unknown role", (v) => { v.identity.role = "superuser"; }],
  ["unknown account", (v) => { v.identity.account_type = "owner"; }],
  ["foreign identity field", (v) => Object.assign(v.identity, { token: "secret" })],
  ["duplicate permissions", (v) => { v.identity.permissions.push("data:read"); }],
  ["permission whitespace", (v) => { v.identity.permissions.push(" users:manage"); }],
  ["long display name", (v) => { v.identity.display_name = "x".repeat(256); }],
  ["invalid revision", (v) => { v.permission_revision = "with spaces"; }],
  ["extra capability", (v) => Object.assign(v.capabilities, { sql: { status: "ready" } })],
  ["missing capability", (v) => { delete v.capabilities.settings; }],
  ["unknown status", (v) => { v.capabilities.tools.status = "approved"; }],
  ["missing unavailable reason", (v) => { v.capabilities.tools.reason = ""; }],
  ["capability foreign field", (v) => Object.assign(v.capabilities.tools, { executable: true })],
  ["ready without required permission", (v) => { v.capabilities.administration.status = "ready"; }],
];
for (const [label, mutation] of malformed) test(`bootstrap rejects ${label}`, () => {
  const value = bootstrap(); mutation(value); assert.throws(() => parseRuntimeBootstrap(value), RuntimeContractError);
});
for (const destination of RUNTIME_DESTINATIONS) test(`${destination} cannot erase or replace fixed required permissions`, () => {
  for (const required of [[], ["unrelated:read"], [...REQUIRED_PERMISSIONS[destination], "extra:read"]]) {
    const value = bootstrap(); value.capabilities[destination].required_permissions = required;
    assert.throws(() => parseRuntimeBootstrap(value), RuntimeContractError);
  }
});
for (const status of ["unavailable", "disabled", "forbidden"] as const) test(`navigation checks permissions even for ${status} capabilities`, () => {
  const value = bootstrap(); value.capabilities.administration.status = status;
  const parsed = parseRuntimeBootstrap(value);
  assert.equal(capabilityVisible(parsed, "admin"), false);
  assert.equal(routeAccessible(parsed, "administration"), false);
  assert.equal(capabilityReady(parsed, "administration"), false);
  assert.equal(routeAccessible(parsed, "catalogue"), true);
  assert.equal(capabilityReady(parsed, "catalogue"), false);
});
test("account type and role labels never substitute for permissions", () => {
  const value = bootstrap(); value.identity.role = "admin"; value.identity.account_type = "internal";
  const parsed = parseRuntimeBootstrap(value);
  assert.equal(routeAccessible(parsed, "admin"), false);
});
test("Research context readiness requires both chat and data permissions", () => {
  const ready = bootstrap();
  ready.capabilities.research.status = "ready";
  ready.capabilities.research.reason = null;
  assert.deepEqual(REQUIRED_PERMISSIONS.research, ["chat:use", "data:read"]);
  assert.equal(capabilityReady(parseRuntimeBootstrap(ready), "research"), true);
  for (const removed of ["chat:use", "data:read"]) {
    const revoked = structuredClone(ready);
    revoked.identity.role = "admin";
    revoked.identity.account_type = "internal";
    revoked.identity.permissions = revoked.identity.permissions.filter((p) => p !== removed);
    assert.throws(() => parseRuntimeBootstrap(revoked), RuntimeContractError);
    revoked.capabilities.research.status = "forbidden";
    revoked.capabilities.research.reason = "The current identity lacks the required permission.";
    const parsed = parseRuntimeBootstrap(revoked);
    assert.equal(capabilityVisible(parsed, "research"), false);
    assert.equal(routeAccessible(parsed, "research"), false);
    assert.equal(capabilityReady(parsed, "research"), false);
  }
});
test("the C15 single-permission Research contract cannot enable C18 context", () => {
  const value = bootstrap();
  value.capabilities.research.required_permissions = ["chat:use"];
  assert.throws(() => parseRuntimeBootstrap(value), RuntimeContractError);
});
test("display-name limits count Unicode code points as the server does", () => {
  const value = bootstrap(); value.identity.display_name = "🌊".repeat(255);
  assert.equal(parseRuntimeBootstrap(value).identity.display_name, value.identity.display_name);
  value.identity.display_name += "🌊";
  assert.throws(() => parseRuntimeBootstrap(value), RuntimeContractError);
});

test("transport has one fixed v1 URL, no cookies/cache/redirects and optional memory-only token", async () => {
  const calls: [string, RequestInit | undefined][] = [];
  const transport = createRuntimeTransport({ tokenProvider: () => "in-memory-token", fetcher: async (url, init) => { calls.push([url, init]); return json(bootstrap()); } });
  const result = await transport.load(); assert.equal(result.status, "ready");
  assert.equal(calls.length, 1); assert.equal(calls[0][0], "/v1/runtime");
  assert.equal(calls[0][1]?.credentials, "omit"); assert.equal(calls[0][1]?.cache, "no-store");
  assert.equal(calls[0][1]?.redirect, "error");
  assert.equal((calls[0][1]?.headers as Record<string, string>).Authorization, "Bearer in-memory-token");
});
for (const [code, expected] of [[401, "unauthorized"], [403, "forbidden"], [404, "unavailable"], [410, "unavailable"], [503, "unavailable"], [500, "error"]] as const) test(`HTTP ${code} replaces ready identity with ${expected}`, async () => {
  let next = false;
  const transport = createRuntimeTransport({ fetcher: async () => next ? new Response("untrusted secret detail", { status: code }) : json(bootstrap()) });
  assert.equal((await transport.load()).status, "ready"); next = true;
  const state = await transport.load(); assert.equal(state.status, expected);
  assert.equal("bootstrap" in state, false); assert.equal("identity" in state, false);
  assert.equal(JSON.stringify(state).includes("secret"), false);
});
test("malformed successful responses do not fall back to sample identity", async () => {
  for (const value of [{}, bootstrap().identity, "sample", null]) {
    const state = await createRuntimeTransport({ fetcher: async () => json(value) }).load();
    assert.equal(state.status, "unavailable"); assert.equal("bootstrap" in state, false);
  }
});
test("a runtime server cannot overwrite JSON fields through duplicate keys", async () => {
  const text = JSON.stringify(bootstrap()).replace('"deployment":"v1"', '"deployment":"legacy","deployment":"v1"');
  assert.equal((await createRuntimeTransport({ fetcher: async () => new Response(text) }).load()).status, "unavailable");
});
test("actual streaming byte bound rejects a lying length and cancels the reader", async () => {
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({
    start(controller) { controller.enqueue(new Uint8Array(MAX_RUNTIME_BYTES)); controller.enqueue(new Uint8Array(1)); },
    cancel() { cancelled = true; },
  });
  const state = await createRuntimeTransport({ fetcher: async () => new Response(body, { headers: { "Content-Length": "1" } }) }).load();
  assert.equal(state.status, "unavailable"); assert.equal(cancelled, true);
});
test("absent length still enforces bytes and malformed UTF-8 is unavailable", async () => {
  for (const bytes of [new Uint8Array(MAX_RUNTIME_BYTES + 1), new Uint8Array([0xc3, 0x28])]) {
    assert.equal((await createRuntimeTransport({ fetcher: async () => new Response(bytes) }).load()).status, "unavailable");
  }
});
for (const token of ["", "with spaces", "newline\r\nvalue", "x".repeat(8193)]) test("invalid supplied token never causes a request", async () => {
  let called = false;
  const state = await createRuntimeTransport({ tokenProvider: () => token, fetcher: async () => { called = true; return json(bootstrap()); } }).load();
  assert.equal(state.status, "unauthorized"); assert.equal(called, false);
});
test("transport errors are honest and omit raw exception contents", async () => {
  const state = await createRuntimeTransport({ fetcher: async () => { throw Error("secret URL"); } }).load();
  assert.equal(state.status, "error"); assert.equal(JSON.stringify(state).includes("secret"), false);
});
for (const status of [401, 403, 404, 500, 503]) test(`unused HTTP ${status} body is cancelled before retry`, async () => {
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({ cancel() { cancelled = true; } });
  await createRuntimeTransport({ fetcher: async () => new Response(body, { status }) }).load();
  assert.equal(cancelled, true);
});
test("cancelled late ready response cannot return an authorized state", async () => {
  const controller = new AbortController();
  const transport = createRuntimeTransport({ fetcher: async () => { controller.abort(); return json(bootstrap()); } });
  await assert.rejects(() => transport.load(controller.signal));
});

for (const hostname of ["localhost", "127.0.0.1", "::1", "[::1]"]) test(`trusted loopback ${hostname} may select explicit sample preview`, () => {
  assert.equal(parseRuntimeMode({ version: MODE_VERSION, mode: "synthetic-preview" }, { hostname, trustedServerSelection: true }), "synthetic-preview");
});
for (const hostname of ["example.com", "localhost.example.com", "127.0.0.1.example.com", "localhost:3100", "0.0.0.0"]) test(`preview rejects host ${hostname}`, () => {
  assert.equal(isLoopbackHostname(hostname), false);
  assert.throws(() => parseRuntimeMode({ version: MODE_VERSION, mode: "synthetic-preview" }, { hostname, trustedServerSelection: true }));
});
test("local hostname alone cannot select preview", () => {
  assert.throws(() => parseRuntimeMode({ version: MODE_VERSION, mode: "synthetic-preview" }, { hostname: "localhost", trustedServerSelection: false }));
});
test("mode endpoint 404 means service, never sample fallback", async () => {
  assert.equal(await loadRuntimeMode({ hostname: "localhost", fetcher: async (url, init) => {
    assert.equal(url, "/_ocean/runtime-mode"); assert.equal(init?.credentials, "omit");
    assert.equal(init?.cache, "no-store"); assert.equal(init?.redirect, "error");
    return new Response("not found", { status: 404 });
  } }), "service");
});
test("mode fallback cancels an unused streaming 404 body", async () => {
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({ cancel() { cancelled = true; } });
  assert.equal(await loadRuntimeMode({ hostname: "localhost", fetcher: async () => new Response(body, { status: 404 }) }), "service");
  assert.equal(cancelled, true);
});
test("mode payload extras and non-loopback preview fail closed", async () => {
  for (const value of [{ version: MODE_VERSION, mode: "synthetic-preview", role: "admin" }, { version: "old", mode: "service" }, { version: MODE_VERSION, mode: "synthetic-preview" }]) {
    await assert.rejects(() => loadRuntimeMode({ hostname: "example.com", fetcher: async () => json(value) }));
  }
});
test("navigation URL helpers ignore forged authorization and preview queries", () => {
  assert.equal(destinationPath("catalogue"), "/?view=catalogue"); assert.equal(destinationPath("administration"), "/admin");
  assert.equal(destinationFromLocation("/", "?view=tools&role=admin&preview=1"), "tools");
  assert.equal(destinationFromLocation("/", "?role=admin&view=unknown&mode=synthetic-preview"), "research");
  assert.equal(destinationFromLocation("/admin", "?view=research"), "administration");
  assert.equal(destinationFromPath("/legacy/admin"), "research");
});
