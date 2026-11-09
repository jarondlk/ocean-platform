import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../../../deploy/gcp/beta/serving-frontend/wait-api.cjs", import.meta.url), "utf8");

async function startup(mode: string | undefined, execution: boolean) {
  let now = 0, loaded = false;
  const exits: number[] = [];
  const context = {
    process: { env: mode === undefined ? {} : { OCEAN_V1_EXPECT_RESEARCH_API: mode }, exit: (code: number) => exits.push(code) },
    Date: { now: () => now }, console: { info() {}, error() {} },
    setTimeout: (callback: () => void) => { now += 150001; queueMicrotask(callback); },
    require: (name: string) => {
      if (name === "/opt/ocean/hosting/server.js") { loaded = true; return {}; }
      assert.equal(name, "node:http");
      return { get: (url: string, callback: (response: EventEmitter) => void) => {
        assert.equal(url, "http://127.0.0.1:8000/health/live");
        const response = Object.assign(new EventEmitter(), { statusCode: 200, setEncoding() {}, destroy() {} });
        callback(response);
        queueMicrotask(() => { response.emit("data", JSON.stringify({ status: "live", execution_enabled: execution })); response.emit("end"); });
        return { setTimeout() {}, on() {}, destroy() {} };
      } };
    },
  };
  vm.runInNewContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  return { loaded, exits };
}

test("startup preserves read-only mode by default and explicitly accepts Research mode", async () => {
  assert.deepEqual(await startup(undefined, false), { loaded: true, exits: [] });
  assert.deepEqual(await startup("true", true), { loaded: true, exits: [] });
  assert.deepEqual(await startup("true", false), { loaded: false, exits: [1] });
  assert.deepEqual(await startup("false", true), { loaded: false, exits: [1] });
  await assert.rejects(startup("invalid", false), /Explicit beta API startup mode required/);
});
