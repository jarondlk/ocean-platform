import assert from "node:assert/strict";
import test from "node:test";
// Local host script has no DOM, application state, data, credentials or provider.
// @ts-expect-error The bounded local preview helper is intentionally native ESM.
import { loopbackHost, modeEnvelope, previewMode } from "../scripts/preview-mode.mjs";

test("preview host requires an explicit process selection", () => {
  assert.equal(previewMode(["--mode", "synthetic-preview"]), "synthetic-preview");
  assert.equal(previewMode(["--mode", "service"]), "service");
  for (const args of [[], ["--mode"], ["?preview=1"], ["--mode", "auto"], ["--mode", "service", "--role=admin"]]) {
    assert.throws(() => previewMode(args));
  }
});

test("synthetic host rejects remote, deceptive and absent host headers", () => {
  for (const host of ["localhost:3100", "127.0.0.1:3100", "[::1]:3100"]) assert.equal(loopbackHost(host), true);
  for (const host of [undefined, "oceaninfobio.com", "oceaninfobio.com:3100", "localhost.evil:3100", "localhost@evil:3100", "127.0.0.1:80", "localhost:3100.evil"]) assert.equal(loopbackHost(host), false);
});

test("mode envelope contains no synthetic identity or credentials", () => {
  assert.deepEqual(modeEnvelope("service"), { version: "ocean-v1-mode-v1", mode: "service" });
  assert.throws(() => modeEnvelope("production-fallback"));
});
