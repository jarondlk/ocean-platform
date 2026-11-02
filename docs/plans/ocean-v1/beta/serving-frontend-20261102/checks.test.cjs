"use strict";
const assert = require("node:assert/strict");
const { spawn, spawnSync } = require("node:child_process");
const http = require("node:http");
const { once } = require("node:events");
const { resolve } = require("node:path");
const test = require("node:test");

const adapter = resolve(__dirname, "../../../../../deploy/gcp/beta/serving-frontend/forwarded-adapter.cjs");
const context = {
  K_SERVICE: "ocean-v1-beta-serving", DEPLOYMENT_ENV: "production", AUTH_MODE: "required",
  V1_PUBLIC_ORIGIN: "https://beta.oceaninfobio.com",
};
test("deployment guard refuses every noncanonical context before application startup", () => {
  for (const env of [{}, { ...context, K_SERVICE: "other-service" },
    { ...context, DEPLOYMENT_ENV: "staging" }, { ...context, AUTH_MODE: "disabled" },
    { ...context, V1_PUBLIC_ORIGIN: "https://other.invalid" }]) {
    const result = spawnSync(process.execPath, ["--require", adapter, "-e", "process.stdout.write('application-started')"], {
      env, encoding: "utf8", timeout: 3000,
    });
    assert.notEqual(result.status, 0);
    assert.equal(result.stdout, "");
    assert.match(result.stderr, /Independent beta transport configuration rejected/);
  }
});

test("actual loopback HTTP preserves request semantics and removes only canonical RFC Forwarded", { timeout: 15000 }, async t => {
  const serverSource = `
    const http=require('node:http');
    const server=http.createServer((req,res)=>{
      const chunks=[];req.on('data',chunk=>chunks.push(chunk));req.on('end',()=>{
        res.setHeader('Content-Type','application/json');res.end(JSON.stringify({
          headers:req.headers,rawHeaders:req.rawHeaders,distinct:req.headersDistinct,
          method:req.method,path:req.url,body:Buffer.concat(chunks).toString()
        }));
      });
    });
    server.listen(0,'127.0.0.1',()=>process.stdout.write(JSON.stringify({port:server.address().port})+'\\n'));
    process.on('SIGTERM',()=>server.close(()=>process.exit(0)));
  `;
  const child = spawn(process.execPath, ["--require", adapter, "-e", serverSource], {
    env: context, stdio: ["ignore", "pipe", "pipe"],
  });
  let diagnostics = "";
  child.stderr.on("data", value => { diagnostics += value.toString(); });
  try {
    const port = await new Promise((resolvePort, reject) => {
      const deadline = setTimeout(() => reject(new Error("Owned HTTP fixture startup deadline")), 3000);
      let output = "";
      child.stdout.on("data", value => {
        output += value.toString();
        if (output.includes("\n")) {
          clearTimeout(deadline); resolvePort(JSON.parse(output.trim()).port);
        }
      });
      child.once("exit", code => { clearTimeout(deadline); reject(new Error("Owned fixture exited: " + code + " " + diagnostics)); });
    });
    const body = "synthetic-body-unchanged";
    const base = ["Host", "beta.oceaninfobio.com", "X-Forwarded-Host", "beta.oceaninfobio.com",
      "X-Forwarded-Proto", "https", "X-Forwarded-Port", "443",
      "Forwarded", "for=192.0.2.1;proto=http;host=provider.invalid",
      "Cookie", "synthetic-cookie=untouched", "Origin", "https://sibling.invalid",
      "Authorization", "Bearer synthetic-fixture", "Content-Type", "text/plain",
      "Content-Length", String(Buffer.byteLength(body)), "Connection", "close"];
    const remove = (headers, name) => headers.filter((_, index) => headers[index - index % 2].toLowerCase() !== name.toLowerCase());
    const replace = (headers, name, value) => headers.map((item, index) =>
      index % 2 === 1 && headers[index - 1].toLowerCase() === name.toLowerCase() ? value : item);
    const call = headers => new Promise((resolveResponse, reject) => {
      const request = http.request({ hostname: "127.0.0.1", port, method: "POST",
        path: "/fixture/path?literal=kept", headers }, response => {
        const chunks = [];
        response.on("data", chunk => chunks.push(chunk)); response.on("error", reject);
        response.on("end", () => resolveResponse({ status: response.statusCode,
          value: response.statusCode === 200 ? JSON.parse(Buffer.concat(chunks).toString()) : null }));
      });
      request.setTimeout(2000, () => request.destroy(new Error("Owned request deadline")));
      request.on("error", reject); request.end(body);
    });
    const unchangedBusiness = value => {
      assert.equal(value.method, "POST"); assert.equal(value.path, "/fixture/path?literal=kept");
      assert.equal(value.body, body); assert.equal(value.headers.cookie, "synthetic-cookie=untouched");
      assert.equal(value.headers.origin, "https://sibling.invalid");
      assert.equal(value.headers.authorization, "Bearer synthetic-fixture");
    };
    await t.test("canonical transport removes Forwarded and preserves every other raw field, cookie, Origin, bearer, method, path and body", async () => {
      const { status, value } = await call(base); assert.equal(status, 200);
      assert.equal(value.headers.forwarded, undefined); assert.equal(value.distinct.forwarded, undefined);
      assert.deepEqual(value.rawHeaders, remove(base, "forwarded")); unchangedBusiness(value);
    });
    await t.test("all case variants and duplicate Forwarded fields are removed only under the canonical transport", async () => {
      const headers = [...base, "fOrWaRdEd", "for=192.0.2.2"];
      const { value } = await call(headers);
      assert.equal(value.headers.forwarded, undefined); assert.deepEqual(value.rawHeaders, remove(headers, "forwarded"));
      unchangedBusiness(value);
    });
    const variants = [
      ["wrong Host", replace(base, "Host", "wrong.invalid")],
      ["wrong forwarded Host", replace(base, "X-Forwarded-Host", "wrong.invalid")],
      ["wrong forwarded protocol", replace(base, "X-Forwarded-Proto", "http")],
      ["wrong forwarded port", replace(base, "X-Forwarded-Port", "80")],
      ["missing forwarded Host", remove(base, "X-Forwarded-Host")],
      ["duplicate raw Host", [...base, "Host", "beta.oceaninfobio.com"]],
      ["duplicate forwarded protocol", [...base, "X-Forwarded-Proto", "https"]],
      ["comma ambiguity", replace(base, "X-Forwarded-Host", "beta.oceaninfobio.com, wrong.invalid")],
      ["bounded raw-header inventory", [...base, ...Array.from({ length: 260 }, (_, index) => ["X-Extra-" + index, "v"]).flat()]],
    ];
    for (const [name, headers] of variants) {
      await t.test(name + " is never normalized", async () => {
        const { status, value } = await call(headers);
        if (status === 400) return; // Native parser refusal occurs before a request handler.
        assert.equal(status, 200); assert.equal(value.headers.forwarded, base[9]);
        assert.deepEqual(value.rawHeaders, headers); unchangedBusiness(value);
      });
    }
    await t.test("absence of Forwarded leaves canonical request intact", async () => {
      const headers = remove(base, "Forwarded"), { value } = await call(headers);
      assert.deepEqual(value.rawHeaders, headers); unchangedBusiness(value);
    });
  } finally {
    if (child.exitCode === null && child.signalCode === null) {
      const exited = once(child, "exit"); child.kill("SIGTERM"); await exited;
    }
  }
  assert.equal(child.exitCode, 0, diagnostics); assert.equal(diagnostics, "");
});
