import assert from "node:assert/strict";
import test from "node:test";
import { createExperimentHttp, ExperimentClientError, MAX_EXPERIMENT_RESPONSE_BYTES, experimentJson } from "../src/experiment-http.ts";
const response = () => new Response('{"value":true}');
test("both protocol families permit only their exact fixed same-origin routes", async () => {
  const paths: string[] = [];
  const options = { fetcher: async (path: string) => { paths.push(path); return response(); } };
  const review = createExperimentHttp(options), execution = createExperimentHttp(options, "execution");
  await review("get", {}); await execution("capability", {});
  await assert.rejects(review("cancel", {})); await assert.rejects(execution("approve", {})); await assert.rejects(review("https://evil.invalid", {}));
  assert.deepEqual(paths, ["/research/experiments/get", "/research/experiment-executions/capability"]);
});

for (const status of [401, 403, 404, 409, 422, 429, 500, 503]) test(`HTTP ${status} maps to a safe status without leaking server bodies`, async () => {
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({ cancel() { cancelled = true; } });
  const http = createExperimentHttp({ fetcher: async () => new Response(body, { status }) });
  await assert.rejects(http("status", {}), (error: any) => error instanceof ExperimentClientError && error.status_code === status && !error.message.includes("private"));
  assert.equal(cancelled, true);
});

for (const raw of ['{"value":1,"value":2}', '{"value":NaN}', '{"value":9223372036854775807}', '{"value":"\\ud800"}', '<html>private</html>']) test("ambiguous/nonfinite/unsafe/malformed response is rejected: " + raw.slice(0, 35), async () => {
  await assert.rejects(createExperimentHttp({ fetcher: async () => new Response(raw) })("status", {}), ExperimentClientError);
});

test("stream bytes are bounded even when Content-Length is absent or lies", async () => {
  let cancelled = 0;
  const stream = () => new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(new TextEncoder().encode("x".repeat(100))); }, cancel() { cancelled++; } });
  await assert.rejects(createExperimentHttp({ maxResponseBytes: 30, fetcher: async () => new Response(stream()) })("status", {}));
  await assert.rejects(createExperimentHttp({ maxResponseBytes: 30, fetcher: async () => new Response(stream(), { headers: { "Content-Length": "1" } }) })("status", {}));
  assert.equal(cancelled, 2);
});

test("oversized declared responses and requests fail before parsing/untrusted work", async () => {
  let fetches = 0;
  const http = createExperimentHttp({ fetcher: async () => { fetches++; return new Response("{}", { headers: { "Content-Length": String(MAX_EXPERIMENT_RESPONSE_BYTES + 1) } }); } });
  await assert.rejects(http("status", {})); await assert.rejects(http("status", { value: "x".repeat(65536) })); assert.equal(fetches, 1);
});

test("invalid UTF-8, getter/prototype/cycle/unsafe numeric inputs never become requests", async () => {
  await assert.rejects(createExperimentHttp({ fetcher: async () => new Response(new Uint8Array([255])) })("status", {}));
  const cycle: any = {}; cycle.self = cycle;
  let getter = false; const accessor = Object.defineProperty({}, "value", { get() { getter = true; return "secret"; }, enumerable: true });
  for (const value of [cycle, new Date(), accessor, { n: Infinity }, { n: Number.MAX_SAFE_INTEGER + 1 }, { [Symbol("unsafe")]: true }]) assert.throws(() => experimentJson(value));
  assert.equal(getter, false);
});

test("abort while a token or fetch is unresolved stops waiting and discards a late response", async () => {
  const beforeToken = new AbortController(); let resolveToken!: (value: string) => void, fetches = 0;
  const token = new Promise<string>(resolve => { resolveToken = resolve; });
  const pending = createExperimentHttp({ tokenProvider: () => token, fetcher: async () => { fetches++; return response(); } })("status", {}, beforeToken.signal);
  beforeToken.abort(); await assert.rejects(pending, { name: "AbortError" }); resolveToken("later"); await Promise.resolve(); assert.equal(fetches, 0);
  const beforeFetch = new AbortController(); let resolveFetch!: (value: Response) => void, cancelled = false;
  const fetch = new Promise<Response>(resolve => { resolveFetch = resolve; });
  let fetching!: () => void; const started = new Promise<void>(resolve => { fetching = resolve; });
  const waiting = createExperimentHttp({ fetcher: () => { fetching(); return fetch; } })("status", {}, beforeFetch.signal);
  await started; beforeFetch.abort(); await assert.rejects(waiting, { name: "AbortError" });
  resolveFetch(new Response(new ReadableStream({ cancel() { cancelled = true; } }))); await new Promise(resolve => setTimeout(resolve, 0)); assert.equal(cancelled, true);
});

test("bounded deadline ends stalled token/fetch/body waits and reports mutation uncertainty", async () => {
  const never = new Promise<string>(() => undefined);
  await assert.rejects(createExperimentHttp({ deadlineMs: 20, tokenProvider: () => never })("approve", {}), (error: any) => error.code === "request_timeout");
  await assert.rejects(createExperimentHttp({ deadlineMs: 20, fetcher: async () => new Response(new ReadableStream()) })("status", {}), (error: any) => error.code === "request_timeout");
});

test("tokens are explicit and malformed tokens do not reach fetch", async () => {
  let calls = 0;
  await assert.rejects(createExperimentHttp({ tokenProvider: () => "bad\nvalue", fetcher: async () => { calls++; return response(); } })("status", {})); assert.equal(calls, 0);
  await createExperimentHttp({ tokenProvider: () => "explicit-token", fetcher: async (_path, init) => { assert.equal((init!.headers as any).Authorization, "Bearer explicit-token"); return response(); } })("status", {});
});

test("response/deadline bound options cannot silently widen limits", () => {
  for (const options of [{ maxResponseBytes: 0 }, { maxResponseBytes: MAX_EXPERIMENT_RESPONSE_BYTES + 1 }, { deadlineMs: 0 }, { deadlineMs: 8001 }]) assert.throws(() => createExperimentHttp(options));
});

test("malicious or stalled body cancellation cannot hold an invalid oversized reply open", { timeout: 200 }, async () => {
  for (const declared of [false, true]) {
    const stream = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(new TextEncoder().encode("x".repeat(100))); }, cancel() { return new Promise(() => undefined); } });
    const http = createExperimentHttp({ maxResponseBytes: 30, fetcher: async () => new Response(stream, { headers: declared ? { "Content-Length": "100" } : {} }) });
    await assert.rejects(http("status", {}), ExperimentClientError);
  }
});
