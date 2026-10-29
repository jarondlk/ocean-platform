import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  createExperimentExecutionClient, parseExecutionModel, mergeExecution, decodeArtifactChunk,
  digestBytes, collectArtifact, ExecutionSession, executionRequest,
  type ExecutionResponse, type ExecutionArtifactResponse,
  type ExperimentExecutionClient, type PendingExecutionCancel,
} from "../src/experiment-execution-service.ts";
import { parseExperimentModel, type ExperimentSnapshot } from "../src/experiment-contract.ts";
import { ExperimentClientError } from "../src/experiment-http.ts";
const wire = JSON.parse(readFileSync(new URL("./fixtures/experiment-execution-wire.json", import.meta.url), "utf8"));
const row = (action: string) => structuredClone(wire.actions.find((value: any) => value.action === action));
const status = () => row("status").response as ExecutionResponse;
const complete = () => row("artifact").response as ExecutionArtifactResponse;
const key = "b414e75c-e664-4be4-bf86-cfd944796f01";
function proposal(response = complete()): ExperimentSnapshot {
  assert.equal(response.experiment_id, wire.experiments.completed.id);
  return structuredClone(wire.experiments.completed);
}
function base64(bytes: Uint8Array): string { return Buffer.from(bytes).toString("base64"); }
function page(template: ExecutionArtifactResponse, raw: Uint8Array, offset: number, limit: number): ExecutionArtifactResponse {
  const value = structuredClone(template), end = Math.min(raw.length, offset + limit);
  value.offset = offset; value.next_offset = end; value.eof = end === raw.length;
  value.content_base64 = base64(raw.subarray(offset, end)); if (offset !== 0) value.preview = null;
  return value;
}
async function largeArtifact() {
  const template = complete();
  const text = JSON.stringify({ columns: ["value"], rows: Array.from({ length: 90 }, () => ["x".repeat(4000)]) });
  const raw = new TextEncoder().encode(text), artifact = template.artifact;
  artifact.sha256 = await digestBytes(raw); artifact.size_bytes = raw.length;
  template.execution!.artifacts = [structuredClone(artifact)];
  template.preview = { columns: ["value"], rows: [["x".repeat(4000)]], total_rows: 90, truncated: true, cells_are_display_strings: true };
  return { template, raw, artifact, execution: template.execution!, proposal: proposal(template) };
}

test("all five execution routes preserve actual Python HTTP request/reply bytes with explicit synthetic observations", async () => {
  assert.equal(wire.kind, "actual-local-durable-synthetic-http"); assert.equal(wire.python_executed, false);
  const actions = new Set<string>();
  for (const fixture of wire.actions) {
    const client = createExperimentExecutionClient({ fetcher: async (path, init) => {
      assert.equal(path, `/research/experiment-executions/${fixture.action}`);
      assert.deepEqual(JSON.parse(init!.body as string), fixture.request);
      assert.equal(init!.credentials, "omit"); assert.equal(init!.redirect, "error"); assert.equal(init!.cache, "no-store");
      return new Response(JSON.stringify(fixture.response));
    } });
    const result = await (client[fixture.action as keyof ExperimentExecutionClient] as any)(fixture.request);
    assert.deepEqual(result, fixture.response); assert.equal(Object.isFrozen(result), true);
    if (result.execution) { assert.equal(result.execution.source, "synthetic-fixture"); assert.equal(result.execution.execution_performed, false); assert.equal(result.execution.termination_verified, false); }
    actions.add(fixture.action);
  }
  assert.deepEqual([...actions].sort(), ["artifact", "cancel", "capability", "events", "status"]);
});

test("captured execution addresses bind actual parsed C22 proposals, not fabricated review snapshots", async () => {
  for (const [kind, action] of [["running", "status"], ["completed", "artifact"]]) {
    const review = await parseExperimentModel("ExperimentSnapshot", wire.experiments[kind]) as ExperimentSnapshot;
    const request = row(action).request;
    assert.deepEqual(executionRequest(review), Object.fromEntries(Object.keys(executionRequest(review)).map(key => [key, request[key]])));
    assert.equal(review.execution_performed, false);
  }
});

for (const [description, mutate] of [
  ["launch authority", (value: any) => { value.capability.start_enabled = true; }],
  ["coerced launch", (value: any) => { value.capability.start_enabled = 0; }],
  ["unavailable transport with enabled actions", (value: any) => { value.capability.transport = "unavailable"; value.capability.source = "unavailable"; }],
  ["configured unavailable source", (value: any) => { value.capability.source = "unavailable"; }],
  ["synthetic Python execution", (value: any) => { value.execution.execution_performed = true; }],
  ["synthetic physical termination", (value: any) => { value.execution.termination_verified = true; value.execution.termination_proof_sha256 = "a".repeat(64); }],
  ["invented authority", (value: any) => { value.execution.authority = "published"; }],
  ["invented scientific approval", (value: any) => { value.execution.scientific_approval = "approved"; }],
  ["status consuming events", (value: any) => { value.execution.event_cursor = 1; }],
  ["cancelling without request", (value: any) => { value.execution.state = "cancelling"; }],
  ["source substitution", (value: any) => { value.execution.source = "retained-operator"; }],
] as const) test(`execution parser rejects ${description}`, () => {
  const value = status(); mutate(value); assert.throws(() => parseExecutionModel("ExecutionResponse", value), ExperimentClientError);
});

test("retained operator terminal states require a separate termination proof and completed execution observation", () => {
  const value = status(); value.capability.source = "retained-operator"; value.execution!.source = "retained-operator";
  for (const state of ["completed", "failed", "cancelled", "timed_out"] as const) {
    const next = structuredClone(value); next.execution!.state = state;
    assert.throws(() => parseExecutionModel("ExecutionResponse", next));
    next.execution!.termination_verified = true; next.execution!.termination_proof_sha256 = "a".repeat(64);
    if (state === "completed") { assert.throws(() => parseExecutionModel("ExecutionResponse", next)); next.execution!.execution_performed = true; }
    parseExecutionModel("ExecutionResponse", next);
  }
  value.execution!.termination_verified = true; value.execution!.termination_proof_sha256 = "a".repeat(64);
  assert.throws(() => parseExecutionModel("ExecutionResponse", value));
});

test("all response binding fields and explicit execution address must match the request", async () => {
  const fixture = row("status");
  for (const mutate of [
    (value: any) => { value.experiment_id = key; }, (value: any) => { value.proposal_revision_id = key; },
    (value: any) => { value.proposal_version++; }, (value: any) => { value.binding.context_revision_id = key; },
    (value: any) => { value.hashes.input_manifest_sha256 = "f".repeat(64); },
    (value: any) => { value.execution = null; }, (value: any) => { value.execution.id = key; },
  ]) {
    const value = structuredClone(fixture.response); mutate(value);
    const client = createExperimentExecutionClient({ fetcher: async () => new Response(JSON.stringify(value)) });
    await assert.rejects(client.status({ ...fixture.request, execution_id: fixture.response.execution.id }));
  }
  let calls = 0; const client = createExperimentExecutionClient({ fetcher: async () => { calls++; throw new Error(); } });
  await assert.rejects(client.status({ ...fixture.request, owner_id: key })); assert.equal(calls, 0);
});

test("event pages retain requested cursor, count, consecutive history and current projection high-water", async () => {
  const fixture = row("events");
  for (const mutate of [
    (value: any) => { value.after_cursor++; }, (value: any) => { value.items[0].cursor++; },
    (value: any) => { value.has_more = true; }, (value: any) => { value.execution.latest_event_cursor++; },
    (value: any) => { value.execution_id = key; }, (value: any) => { value.latest_event_cursor++; },
  ]) {
    const value = structuredClone(fixture.response); mutate(value);
    await assert.rejects(createExperimentExecutionClient({ fetcher: async () => new Response(JSON.stringify(value)) }).events(fixture.request));
  }
});

test("cancellation acknowledgement keeps the same key, retained intent and separate unconfirmed termination", async () => {
  const fixture = row("cancel");
  for (const mutate of [
    (value: any) => { value.cancellation.idempotency_key = key; }, (value: any) => { value.cancellation.termination_confirmed = true; },
    (value: any) => { value.execution = null; }, (value: any) => { value.execution.cancel_requested = false; value.execution.state = "running"; },
    (value: any) => { value.cancellation.status = "already_terminal"; },
  ]) {
    const value = structuredClone(fixture.response); mutate(value);
    await assert.rejects(createExperimentExecutionClient({ fetcher: async () => new Response(JSON.stringify(value)) }).cancel(fixture.request));
  }
});

test("execution merges discard older revisions and reject terminal regression, identity replacement and event loss", () => {
  const running = status(), cancelling = row("cancel").response as ExecutionResponse;
  assert.equal(mergeExecution(running, cancelling), cancelling); assert.equal(mergeExecution(cancelling, running), cancelling);
  for (const mutate of [
    (value: any) => { value.execution = null; }, (value: any) => { value.execution.id = key; },
    (value: any) => { value.proposal_revision_id = key; }, (value: any) => { value.proposal_version++; },
    (value: any) => { value.binding.context_revision_id = key; },
    (value: any) => { value.execution.state_revision++; value.execution.state = "running"; },
    (value: any) => { value.execution.state_revision++; value.execution.latest_event_cursor = 0; },
    (value: any) => { value.execution.state_revision++; value.execution.cancel_requested = false; },
  ]) { const next = structuredClone(cancelling); mutate(next); assert.throws(() => mergeExecution(cancelling, next)); }
  const terminal = complete(), regression = structuredClone(terminal); regression.execution!.state_revision++; regression.execution!.state = "running";
  assert.throws(() => mergeExecution(terminal, regression));
  const changed = structuredClone(terminal); changed.execution!.state_revision++; assert.throws(() => mergeExecution(terminal, changed));
  const contradiction = structuredClone(running); contradiction.execution!.cancel_requested = true; assert.throws(() => mergeExecution(running, contradiction));
});

for (const mutate of [
  (value: any) => { value.media_type = "text/html"; value.name = "result.html"; },
  (value: any) => { value.kind = "raster"; value.media_type = "image/svg+xml"; value.name = "plot.svg"; },
  (value: any) => { value.kind = "raster"; value.name = "summary.json"; },
  (value: any) => { value.size_bytes = 50 * 1024 ** 2 + 1; },
  (value: any) => { value.attachment_reference.kind = "catalogue"; },
]) test("only bounded table/PNG artifacts preserve experimental attachment authority", () => {
  const artifact = complete().artifact; mutate(artifact); assert.throws(() => parseExecutionModel("ExecutionArtifact", artifact));
});

test("total output bytes, duplicate artifact identities, incomplete states and mismatched attachment snapshots fail", () => {
  for (const mutate of [
    (value: any) => { value.execution.artifacts = Array.from({ length: 2 }, (_, index) => ({ ...value.artifact, id: "output:" + index, name: "table" + index + ".json", size_bytes: 26 * 1024 ** 2 })); },
    (value: any) => { value.execution.artifacts.push(value.execution.artifacts[0]); },
    (value: any) => { value.execution.outputs_manifest_sha256 = null; },
    (value: any) => { value.execution.state = "running"; },
    (value: any) => { value.execution.artifacts[0].attachment_reference.snapshot_id = "f".repeat(64); value.artifact.attachment_reference.snapshot_id = "f".repeat(64); },
  ]) { const value = complete(); mutate(value); assert.throws(() => parseExecutionModel("ExecutionArtifactResponse", value)); }
});

test("canonical base64, chunk bounds, retained manifest and full-byte SHA are verified", async () => {
  const fixture = row("artifact");
  for (const mutate of [
    (value: any) => { value.content_base64 += "\n"; }, (value: any) => { value.content_base64 = "AB=="; },
    (value: any) => { value.content_base64 = base64(new Uint8Array(value.artifact.size_bytes).fill(65)); },
    (value: any) => { value.next_offset--; }, (value: any) => { value.offset++; },
    (value: any) => { value.eof = false; }, (value: any) => { value.artifact.id = "output:wrong"; },
    (value: any) => { value.execution.artifacts = []; },
    (value: any) => { value.preview.rows[0][0] = 9223372036854775807; },
    (value: any) => { value.preview.rows[0].push("extra cell"); },
  ]) {
    const value = structuredClone(fixture.response); mutate(value);
    await assert.rejects(createExperimentExecutionClient({ fetcher: async () => new Response(JSON.stringify(value)) }).artifact(fixture.request));
  }
  for (const value of ["AB==", "A===", "AA=", "AA==\n", "-___", "éééé"]) assert.throws(() => decodeArtifactChunk(value));
  assert.deepEqual(decodeArtifactChunk("AA=="), new Uint8Array([0]));
});

test("Python's valid empty EOF page remains supported at the exact retained file length", async () => {
  const fixture = row("artifact"), raw = decodeArtifactChunk(fixture.response.content_base64), eof = page(fixture.response, raw, raw.length, 1);
  const result = await createExperimentExecutionClient({ fetcher: async () => new Response(JSON.stringify(eof)) }).artifact({ ...fixture.request, offset: raw.length, limit: 1 });
  assert.equal(result.eof, true); assert.equal(result.next_offset, result.offset); assert.equal(result.content_base64, "");
});

test("preview is only an initial table display and never parses exact machine int64 bytes into JS numbers", async () => {
  const fixture = row("artifact"), value = fixture.response as ExecutionArtifactResponse;
  assert.equal(value.preview!.rows[0][0], "9223372036854775807"); assert.equal(value.preview!.cells_are_display_strings, true);
  const raw = decodeArtifactChunk(value.content_base64), text = new TextDecoder().decode(raw);
  assert.ok(text.includes("9223372036854775807"));
  const client = createExperimentExecutionClient({ fetcher: async (_path, init) => {
    const request = JSON.parse(init!.body as string); return new Response(JSON.stringify(page(value, raw, request.offset ?? 0, request.limit ?? 256 * 1024)));
  } });
  const assembled = await collectArtifact(client, proposal(value), value.execution!, value.artifact, new AbortController().signal);
  assert.equal(new TextDecoder().decode(assembled.data), text); assert.equal(assembled.preview!.rows[0][0], "9223372036854775807");
  const later = page(value, raw, 1, 1); later.preview = value.preview;
  assert.throws(() => parseExecutionModel("ExecutionArtifactResponse", later));
  const raster = structuredClone(value); raster.artifact.kind = "raster"; raster.artifact.media_type = "image/png"; raster.artifact.name = "plot.png"; raster.execution!.artifacts = [raster.artifact];
  assert.throws(() => parseExecutionModel("ExecutionArtifactResponse", raster));
});

test("large collection uses bounded chunks then a fresh authorized one-byte request before exposure", async () => {
  const { template, raw, execution, artifact, proposal } = await largeArtifact(), calls: any[] = [], progress: number[] = [];
  const client = { artifact: async (request: any) => { calls.push(request); return page(template, raw, request.offset, request.limit); } } as ExperimentExecutionClient;
  const result = await collectArtifact(client, proposal, execution, artifact, new AbortController().signal, bytes => progress.push(bytes));
  assert.deepEqual(result.data, raw); assert.deepEqual(progress, [256 * 1024, raw.length]);
  assert.equal(calls.length, 3); assert.equal(calls[2].offset, 0); assert.equal(calls[2].limit, 1);
  for (const request of calls) { assert.equal(request.expected_sha256, artifact.sha256); assert.deepEqual(request.expected_hashes, proposal.hashes); }
});

test("collection refuses mid-chunk revocation, stale final authorization and a changed final execution", async () => {
  const { template, raw, execution, artifact, proposal } = await largeArtifact();
  for (const kind of ["midchunk", "fresh-denied", "fresh-identity", "fresh-manifest"] as const) {
    let calls = 0;
    const client = { artifact: async (request: any) => {
      calls++;
      if (kind === "midchunk" && calls === 2 || kind === "fresh-denied" && request.limit === 1) throw new ExperimentClientError("access_denied", "Restricted", 403);
      const next = page(template, raw, request.offset, request.limit);
      if (request.limit === 1 && kind === "fresh-identity") next.execution!.id = key;
      if (request.limit === 1 && kind === "fresh-manifest") next.execution!.outputs_manifest_sha256 = "f".repeat(64);
      return next;
    } } as ExperimentExecutionClient;
    await assert.rejects(collectArtifact(client, proposal, execution, artifact, new AbortController().signal));
  }
});

test("a late or callback-aborted chunk cannot publish progress or an assembled artifact", async () => {
  const { template, raw, execution, artifact, proposal } = await largeArtifact();
  const controller = new AbortController(); let progress = 0, calls = 0;
  const late = { artifact: async (request: any) => { calls++; controller.abort(); return page(template, raw, request.offset, request.limit); } } as ExperimentExecutionClient;
  await assert.rejects(collectArtifact(late, proposal, execution, artifact, controller.signal, () => { progress++; }), { name: "AbortError" });
  assert.equal(progress, 0); assert.equal(calls, 1);
  const callbackAbort = new AbortController(); calls = 0;
  const client = { artifact: async (request: any) => { calls++; return page(template, raw, request.offset, request.limit); } } as ExperimentExecutionClient;
  await assert.rejects(collectArtifact(client, proposal, execution, artifact, callbackAbort.signal, () => callbackAbort.abort()), { name: "AbortError" });
  assert.equal(calls, 1);
});

test("pending cancellation is exact, immutable, non-overwritable and cleared by account/permission generation changes", () => {
  const fixture = row("cancel"), pending: PendingExecutionCancel = { request: fixture.request, binding: fixture.response.binding }, session = new ExecutionSession();
  assert.throws(() => session.remember(pending)); session.bind("account:permission1"); const epoch = session.generation;
  session.remember(pending); assert.equal(session.isCurrent("account:permission1", epoch), true);
  session.bind("account:permission1"); assert.deepEqual(session.get(pending.binding), pending); assert.equal(Object.isFrozen(session.get(pending.binding)!.request), true);
  const changed: PendingExecutionCancel = { ...pending, request: { ...pending.request, idempotency_key: key } };
  assert.throws(() => session.remember(changed)); session.forget(changed); assert.deepEqual(session.get(pending.binding), pending);
  const mismatched = { ...pending, request: { ...pending.request, context_revision_id: key } };
  assert.throws(() => session.remember(mismatched));
  session.bind("account:permission2"); assert.equal(session.get(pending.binding), null); assert.equal(session.isCurrent("account:permission1", epoch), false);
  session.remember(pending); session.bind("different:permission2"); assert.equal(session.get(pending.binding), null);
  session.remember(pending); const active = session.generation; session.clear(); assert.equal(session.isCurrent("different:permission2", active), false); assert.throws(() => session.get(pending.binding));
  const reload = new ExecutionSession(); reload.bind("different:permission2"); assert.equal(reload.get(pending.binding), null);
});

test("cancellation slots are bounded without evicting an uncertain request, and original contexts remain distinguishable", () => {
  const fixture = row("cancel"), session = new ExecutionSession(); session.bind("account");
  for (let n = 1; n <= 64; n++) {
    const id = `00000000-0000-4000-8000-${n.toString(16).padStart(12, "0")}`;
    session.remember({ binding: { ...fixture.response.binding, conversation_id: id }, request: { ...fixture.request, conversation_id: id } });
  }
  assert.throws(() => session.remember({ binding: fixture.response.binding, request: fixture.request }));
  const first = { ...fixture.response.binding, conversation_id: "00000000-0000-4000-8000-000000000001", context_revision_id: key };
  assert.equal(session.get(first)!.request.context_revision_id, fixture.request.context_revision_id);
});
