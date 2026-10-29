import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parseExperimentModel, type ExperimentResponse, type ExperimentSnapshot } from "../src/experiment-contract.ts";
import { createExperimentClient, type ExperimentClient, experimentAddress } from "../src/experiment-service.ts";
import { experimentDecision } from "../src/experiment-state.ts";
import { ExperimentClientError, experimentJson } from "../src/experiment-http.ts";
const wire = JSON.parse(readFileSync(new URL("../../docs/plans/ocean-v1/evidence/C22/http-wire-current-source.json", import.meta.url), "utf8")) as { kind: string; python_executed: boolean; actions: { action: keyof ExperimentClient; request: Record<string, any>; response: Record<string, any> }[] };
const captured = (action: keyof ExperimentClient) => wire.actions.find(row => row.action === action)!;
const snapshot = () => structuredClone(captured("approve").response.experiment) as ExperimentSnapshot;
const key = "b414e75c-e664-4be4-bf86-cfd944796f01";

test("all nine review clients accept actual local Python HTTP envelopes with original request bytes and false execution semantics", async () => {
  assert.equal(wire.kind, "actual-local-synthetic-http"); assert.equal(wire.python_executed, false);
  const actions = new Set<string>();
  for (const row of wire.actions) {
    let calls = 0;
    const client = createExperimentClient({ fetcher: async (path, init) => {
      calls++; assert.equal(path, `/research/experiments/${row.action}`); assert.deepEqual(JSON.parse(init!.body as string), row.request);
      assert.equal(init!.credentials, "omit"); assert.equal(init!.redirect, "error"); assert.equal(init!.cache, "no-store");
      return new Response(JSON.stringify(row.response));
    } });
    const response = await (client[row.action] as any)(row.request);
    assert.deepEqual(response, row.response); assert.equal(calls, 1); assert.equal(Object.isFrozen(response), true);
    if (response.experiment) { assert.equal(response.experiment.execution_performed, false); assert.equal(Object.isFrozen(response.experiment.proposal), true); }
    actions.add(row.action);
  }
  assert.deepEqual([...actions].sort(), ["approve", "create", "dispatch", "events", "get", "list", "retry", "revise", "status"]);
});

for (const [name, mutate] of [
  ["invented execution", (v: any) => { v.execution_performed = true; }],
  ["coerced execution", (v: any) => { v.execution_performed = 0; }],
  ["new authority", (v: any) => { v.authority = "published"; }],
  ["scientific approval", (v: any) => { v.scientific_approval = "verified"; }],
  ["extra owner field", (v: any) => { v.owner_id = key; }],
  ["changed code", (v: any) => { v.proposal.python_code += "\nprint('different')"; }],
  ["changed question", (v: any) => { v.proposal.question = "Different question"; }],
  ["changed limits", (v: any) => { v.proposal.resources.cpus = 1; }],
  ["changed packages", (v: any) => { v.environment.description = "Different environment"; }],
  ["mismatched environment identity", (v: any) => { v.proposal.environment_id = "a".repeat(64); }],
  ["wrong current approval", (v: any) => { v.approval.proposal_revision_id = key; }],
  ["dispatch without approval", (v: any) => { v.approval = null; }],
  ["unsafe integer", (v: any) => { v.manifest.value = Number.MAX_SAFE_INTEGER + 1; }],
  ["nonfinite metadata", (v: any) => { v.manifest.value = NaN; }],
  ["bad unicode", (v: any) => { v.proposal.question = "\ud800"; }],
  ["wrong manifest binding", (v: any) => { v.manifest.binding.investigation_id = key; }],
  ["false manifest authority", (v: any) => { v.manifest.independent_scientific_approval = true; }],
  ["missing serialized execution field", (v: any) => { delete v.execution_performed; }],
  ["regressed event head", (v: any) => { v.event_cursor = v.latest_event_cursor + 1; }],
] as const) test(`review parser rejects ${name}`, async () => {
  const value = snapshot(); mutate(value); await assert.rejects(parseExperimentModel("ExperimentSnapshot", value), ExperimentClientError);
});

test("empty top response and missing serialized fields cannot fabricate a valid service reply", async () => {
  await assert.rejects(parseExperimentModel("ExperimentResponse", { version: "research-experiments-v1", experiment: null, operation: null }));
  const value = structuredClone(captured("status").response); delete value.version; await assert.rejects(parseExperimentModel("ExperimentResponse", value));
});

test("approval helpers freeze the exact displayed revision, context and all five hashes", async () => {
  const displayed = await parseExperimentModel("ExperimentSnapshot", snapshot()) as ExperimentSnapshot;
  const request = experimentDecision(displayed, key);
  assert.deepEqual(request.expected_hashes, displayed.hashes); assert.equal(request.expected_version, displayed.version);
  assert.equal(request.expected_proposal_revision_id, displayed.proposal_revision_id); assert.equal(request.idempotency_key, key);
  assert.equal(Object.isFrozen(request.expected_hashes), true); assert.deepEqual(experimentAddress(displayed), { experiment_id: displayed.id });
});

for (const action of ["approve", "dispatch", "get", "status"] as const) test(`${action} rejects substituted review identity`, async () => {
  const row = captured(action), response = structuredClone(row.response); response.experiment.id = key;
  const client = createExperimentClient({ fetcher: async () => new Response(JSON.stringify(response)) });
  await assert.rejects((client[action] as any)(row.request), ExperimentClientError);
});

test("approval hashes and requested historical revision cannot be rebound by a response", async () => {
  const approve = captured("approve"), request = structuredClone(approve.request); request.expected_hashes.input_manifest_sha256 = "f".repeat(64);
  await assert.rejects(createExperimentClient({ fetcher: async () => new Response(JSON.stringify(approve.response)) }).approve(request as any));
  const get = captured("get"), wrong = structuredClone(get.request); wrong.proposal_revision_id = key;
  await assert.rejects(createExperimentClient({ fetcher: async () => new Response(JSON.stringify(get.response)) }).get(wrong as any));
});

test("ready create/revise responses must preserve the normalized typed proposal and operation revision", async () => {
  const create = captured("create"), wrong = structuredClone(create.response); wrong.operation.result_revision_id = key;
  await assert.rejects(createExperimentClient({ fetcher: async () => new Response(JSON.stringify(wrong)) }).create(create.request as any));
  const request = structuredClone(create.request); request.proposal.method = "Changed submitted method";
  await assert.rejects(createExperimentClient({ fetcher: async () => new Response(JSON.stringify(create.response)) }).create(request as any));
});

test("prepared operation responses may retain the prior context without presenting a new proposal as ready", async () => {
  const create = captured("create"), response = structuredClone(create.response), request = structuredClone(create.request);
  response.operation.state = "prepared"; response.operation.result_revision_id = null;
  request.context_revision_id = key;
  const result = await createExperimentClient({ fetcher: async () => new Response(JSON.stringify(response)) }).create(request as any);
  assert.equal(result.operation!.state, "prepared"); assert.notEqual(result.experiment!.binding.context_revision_id, request.context_revision_id);
});

test("list pages bind the owner conversation and reject duplicate/non-progressing cursor pages", async () => {
  const row = captured("list");
  for (const mutate of [(v: any) => v.items.push(v.items[0]), (v: any) => { v.next_cursor = key; }, (v: any) => { v.items[0].binding.investigation_id = key; }]) {
    const value = structuredClone(row.response); mutate(value);
    await assert.rejects(createExperimentClient({ fetcher: async () => new Response(JSON.stringify(value)) }).list(row.request as any));
  }
});

test("event pages reject gaps, cursor regression, unbounded pages and wrong experiment addresses", async () => {
  const row = captured("events");
  for (const mutate of [(v: any) => { v.items[0].cursor++; }, (v: any) => { v.has_more = !v.has_more; }, (v: any) => { v.experiment_id = key; }, (v: any) => { v.after_cursor++; }]) {
    const value = structuredClone(row.response); mutate(value);
    await assert.rejects(createExperimentClient({ fetcher: async () => new Response(JSON.stringify(value)) }).events(row.request as any));
  }
});

test("retry cannot recover a different operation and unsafe requests never reach fetch", async () => {
  const row = captured("retry"), value = structuredClone(row.response); value.operation.id = key;
  await assert.rejects(createExperimentClient({ fetcher: async () => new Response(JSON.stringify(value)) }).retry(row.request as any));
  let calls = 0; const client = createExperimentClient({ fetcher: async () => { calls++; throw new Error(); } });
  await assert.rejects(client.status({ experiment_id: key, owner_id: key } as any));
  assert.equal(calls, 0);
});

test("opaque machine int64 strings stay exact; unsafe integer conversion is rejected", () => {
  assert.deepEqual(experimentJson({ value: "9223372036854775807" }), { value: "9223372036854775807" });
  assert.throws(() => experimentJson({ value: Number("9223372036854775807") }));
});

test("generated identifier anchors reject trailing newlines and dictionary keys retain Python identifier restrictions", async () => {
  await assert.rejects(parseExperimentModel("ExperimentAddressRequest", { experiment_id: key + "\n" }));
  for (const identifier of ["bad key", "x\n", "a".repeat(257)]) {
    const value = structuredClone(captured("create").request); value.proposal.seeds = { [identifier]: 0 };
    await assert.rejects(parseExperimentModel("ExperimentCreateRequest", value));
  }
});

test("proposal canonical bytes and Python source UTF-8 bytes retain independent review bounds", async () => {
  const longProposal = structuredClone(captured("create").request); longProposal.proposal.assumptions = Array.from({ length: 64 }, () => "a".repeat(1000));
  await assert.rejects(parseExperimentModel("ExperimentCreateRequest", longProposal));
  const longSource = structuredClone(captured("create").request); longSource.proposal.python_code = "# " + "漢".repeat(12000);
  await assert.rejects(parseExperimentModel("ExperimentCreateRequest", longSource));
});

test("real package identities accept exact PEP 440 forms and reject version expressions and malformed keys", async () => {
  const environment = { kind: "linux-gvisor", test_only: false, python_version: "3.12.1", image_digest: "sha256:" + "a".repeat(64), lockfile_sha256: "a".repeat(64),
    description: "Concrete test descriptor", packages: { numpy: "1.0", pandas: "2.0", pyarrow: "1.0", scipy: "1.0", statsmodels: "1.0", matplotlib: "1.0" } };
  for (const version of ["1", "1.0.0", "2!1.2rc3.post4.dev5+build.2", "v1.0-1", "1.0a", " 1.2 ", "1.0REV2", "1.0_preview_2"]) {
    await parseExperimentModel("EnvironmentDescriptor", { ...environment, packages: { ...environment.packages, numpy: version } });
  }
  for (const version of [">=1.0", "1.*", "latest", "1.0+", "1.0+bad space", "1.0\ufeff"]) {
    await assert.rejects(parseExperimentModel("EnvironmentDescriptor", { ...environment, packages: { ...environment.packages, numpy: version } }));
  }
  await assert.rejects(parseExperimentModel("EnvironmentDescriptor", { ...environment, packages: { ...environment.packages, "bad key": "1.0" } }));
});

test("ready mutations must retain a result revision and snapshot before uncertainty can clear", async () => {
  const row = captured("approve");
  for (const mutate of [(value: any) => { value.experiment = null; }, (value: any) => { value.operation = null; }, (value: any) => { value.operation.result_revision_id = key; }]) {
    const value = structuredClone(row.response); mutate(value);
    await assert.rejects(createExperimentClient({ fetcher: async () => new Response(JSON.stringify(value)) }).approve(row.request as any));
  }
});
