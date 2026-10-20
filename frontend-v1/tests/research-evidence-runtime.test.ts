import assert from "node:assert/strict";
import test from "node:test";
import { parseRuntimeBootstrap, REQUIRED_PERMISSIONS, RUNTIME_DESTINATIONS, RUNTIME_VERSION, RuntimeContractError } from "../src/runtime.ts";
function bootstrap() {
  const permissions = ["chat:use", "data:read", "profile:read", "feedback:write"];
  return { version: RUNTIME_VERSION, deployment: "v1", identity: { id: "00000000-0000-0000-0000-000000000001", display_name: null, role: "researcher", account_type: "research", status: "active", permissions }, permission_revision: "policy:one",
    capabilities: Object.fromEntries(RUNTIME_DESTINATIONS.map(key => [key, { status: "unavailable", reason: "Not configured", required_permissions: [...REQUIRED_PERMISSIONS[key]] }])) };
}
const capability = () => ({ version: "research-evidence-v1", transport: "http-v1", synthesis: "http-v1", submit_enabled: true, reason: null as string | null });
test("separate evidence discovery is optional and never changes the C20 synthesis literal", () => {
  assert.equal(parseRuntimeBootstrap(bootstrap()).research_evidence, undefined);
  const input = { ...bootstrap(), research_evidence: capability(), research_runs: { version: "research-runs-v1", transport: "http-v1", submit_enabled: true, dispatch_enabled: true, synthesis: "unavailable", reason: null } };
  const result = parseRuntimeBootstrap(input); assert.deepEqual(result.research_evidence, input.research_evidence); assert.equal(result.research_runs!.synthesis, "unavailable");
  input.research_evidence.submit_enabled = false; assert.equal(result.research_evidence!.submit_enabled, true);
});
test("permitted retained evidence remains discoverable with synthesis dispatch disabled", () => {
  const result = parseRuntimeBootstrap({ ...bootstrap(), research_evidence: { ...capability(), synthesis: "unavailable", submit_enabled: false, reason: "New answers are unavailable" } });
  assert.equal(result.research_evidence!.transport, "http-v1"); assert.equal(result.research_evidence!.submit_enabled, false);
  const unavailable = parseRuntimeBootstrap({ ...bootstrap(), research_evidence: { ...capability(), transport: "unavailable", synthesis: "unavailable", submit_enabled: false, reason: "Evidence is not configured" } });
  assert.equal(unavailable.research_evidence!.transport, "unavailable");
});
for (const [name, mutate] of [
  ["version", (value: any) => { value.version = "old"; }], ["endpoint injection", (value: any) => { value.endpoint = "https://untrusted.invalid"; }],
  ["synthesis transport", (value: any) => { value.synthesis = "ready"; }], ["evidence transport", (value: any) => { value.transport = "fixture"; }],
  ["nonboolean submit", (value: any) => { value.submit_enabled = 1; }], ["submit without synthesis", (value: any) => { value.synthesis = "unavailable"; }],
  ["synthesis without evidence", (value: any) => { value.transport = "unavailable"; value.submit_enabled = false; value.reason = "Unavailable"; }],
  ["unavailable without reason", (value: any) => { value.transport = "unavailable"; value.synthesis = "unavailable"; value.submit_enabled = false; }],
] as const) test(`evidence discovery rejects ${name}`, () => { const value = capability(); mutate(value); assert.throws(() => parseRuntimeBootstrap({ ...bootstrap(), research_evidence: value }), RuntimeContractError); });
for (const permission of ["chat:use", "data:read"]) test(`evidence HTTP discovery cannot bypass missing ${permission}`, () => {
  const input = { ...bootstrap(), research_evidence: capability() }; input.identity.permissions = input.identity.permissions.filter(value => value !== permission);
  assert.throws(() => parseRuntimeBootstrap(input), RuntimeContractError);
});
