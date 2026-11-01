import assert from "node:assert/strict";
import test from "node:test";
import { createServer, request as httpRequest } from "node:http";
import { createServer as tcpServer } from "node:net";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { encode } from "next-auth/jwt";
import { jwtVerify } from "jose";
import { ACCOUNT, ENV, IDENTITY, SETTINGS } from "../tests/fixtures.ts";
import { SESSION_COOKIE } from "../lib/auth-config.ts";

test("built Next host performs guarded login, encrypted session, private proxy, revocation and logout over actual HTTP", { timeout: 45000 }, async () => {
  let active = true, meCalls = 0, runtimeCalls = 0;
  const backend = createServer(async (req, res) => {
    try {
      assert.equal(req.headers.host, "127.0.0.1:8000");
      assert.equal(req.headers.cookie, undefined);
      const { payload } = await jwtVerify(String(req.headers.authorization).slice(7), new TextEncoder().encode(SETTINGS.internalSecret), {
        algorithms: ["HS256"], issuer: SETTINGS.issuer, audience: SETTINGS.audience, maxTokenAge: 60,
      });
      assert.equal(payload.sub, IDENTITY.subject); assert.equal(payload.role, undefined);
      res.setHeader("Content-Type", "application/json");
      if (req.url === "/me") { meCalls++; res.statusCode = active ? 200 : 403; res.end(JSON.stringify(active ? ACCOUNT : { detail: "Suspended" })); }
      else if (req.url === "/v1/runtime") { runtimeCalls++; res.end(JSON.stringify({ fixture: "actual-private-http-boundary-only" })); }
      else { res.statusCode = 404; res.end("{}"); }
    } catch { res.statusCode = 401; res.end("{}"); }
  });
  // Fixed contract port: fail on an existing listener rather than contacting or replacing it.
  await new Promise<void>((resolve, reject) => { backend.once("error", reject); backend.listen(8000, "127.0.0.1", resolve); });
  const portProbe = tcpServer(); await new Promise<void>(resolve => portProbe.listen(0, "127.0.0.1", resolve));
  const address = portProbe.address(); assert(address && typeof address === "object"); const port = address.port;
  await new Promise<void>(resolve => portProbe.close(() => resolve()));
  let diagnostics = "";
  const child = spawn(process.execPath, [new URL("../.next/standalone/hosting/server.js", import.meta.url).pathname], {
    cwd: new URL("..", import.meta.url), env: { ...process.env, ...ENV, NEXT_TELEMETRY_DISABLED: "1",
      HOSTNAME: "127.0.0.1", PORT: String(port),
      NODE_OPTIONS: `--require ${new URL("./provider-fixture.cjs", import.meta.url).pathname}` }, stdio: ["ignore", "pipe", "pipe"],
  });
  const ready = new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Owned Next host did not become ready")), 20000);
    const observe = (chunk: Buffer) => { diagnostics += chunk.toString(); if (diagnostics.includes("Ready in")) { clearTimeout(timer); resolve(); } };
    child.stdout.on("data", observe); child.stderr.on("data", observe);
    child.once("exit", code => { clearTimeout(timer); reject(new Error("Owned Next host exited before readiness: " + code)); });
  });
  const local = `http://127.0.0.1:${port}`;
  const actionBody = (name: string) => {
    const boundary = "ocean-fixture-" + crypto.randomUUID();
    return { contentType: "multipart/form-data; boundary=" + boundary,
      body: `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n\r\n--${boundary}--\r\n` };
  };
  const call = (path: string, init: RequestInit = {}) => {
    const headers = new Headers(init.headers); if (!headers.has("host")) headers.set("host", "beta.oceaninfobio.com");
    headers.set("x-forwarded-proto", "https");
    headers.set("x-forwarded-port", "443");
    // A transport-level test of trusted ingress must preserve Host exactly;
    // browser fetch/Undici rewrites Host to the loopback URL authority.
    return new Promise<Response>((resolve, reject) => {
      const outgoing = httpRequest(local + path, { method: init.method ?? "GET", headers: Object.fromEntries(headers) }, incoming => {
        const chunks: Buffer[] = [];
        incoming.on("data", chunk => chunks.push(Buffer.from(chunk)));
        incoming.on("error", reject);
        incoming.on("end", () => {
          const responseHeaders = new Headers();
          for (let i = 0; i < incoming.rawHeaders.length; i += 2) responseHeaders.append(incoming.rawHeaders[i], incoming.rawHeaders[i + 1]);
          resolve(new Response(Buffer.concat(chunks), { status: incoming.statusCode, headers: responseHeaders }));
        });
      });
      outgoing.on("error", reject); outgoing.setTimeout(15000, () => outgoing.destroy(new Error("Owned HTTP test deadline")));
      if (init.body) outgoing.write(String(init.body)); outgoing.end();
    });
  };
  try {
    await ready;
    const deniedHost = await call("/login", { headers: { host: "evil.invalid" } }); assert.equal(deniedHost.status, 403);
    const login = await call("/login"); assert.equal(login.status, 200);
    assert.match(login.headers.get("content-security-policy")!, /form-action 'self' https:\/\/accounts.google.com/);
    const loginHtml = await login.text(); assert.match(loginHtml, /Sign in with Google/);
    const stylesheet = loginHtml.match(/href="([^\"]+\.css)"/); assert(stylesheet);
    const style = await call(stylesheet[1]); assert.equal(style.status, 200); assert.match(style.headers.get("content-type")!, /text\/css/);
    const action = loginHtml.match(/name="(\$ACTION_ID_[^"]+)"/); assert(action, "Actual Next server action form is rendered");
    const loginAction = actionBody(action[1]);
    const start = await call("/login", { method: "POST", headers: { Origin: SETTINGS.origin, "Content-Type": loginAction.contentType }, body: loginAction.body });
    assert.equal(start.status, 303, JSON.stringify({ location: start.headers.get("location"),
      response: (await start.clone().text()).slice(0, 220), diagnostic: diagnostics.slice(-700) }));
    const target = new URL(start.headers.get("location")!);
    assert.equal(target.origin, "https://accounts.google.com"); assert.equal(target.searchParams.get("redirect_uri"), SETTINGS.origin + "/api/auth/callback/google");
    assert.equal(target.searchParams.get("client_id"), ENV.V1_GOOGLE_CLIENT_ID);
    assert.equal(target.searchParams.get("code_challenge_method"), "S256"); assert(target.searchParams.get("state")); assert(target.searchParams.get("nonce"));
    for (const cookie of start.headers.getSetCookie()) { assert.match(cookie, /^__Host-ocean-v1-/); assert.match(cookie, /Secure/i); assert.match(cookie, /HttpOnly/i); assert.doesNotMatch(cookie, /Domain=/i); }
    // Never follow the Google URL: provider/network acceptance is a separate gate.
    const noSession = await call("/v1/runtime"); assert.equal(noSession.status, 401); assert.equal(runtimeCalls, 0);
    const cookie = await encode({ token: { sub: IDENTITY.subject, v1Identity: IDENTITY }, secret: SETTINGS.authSecret, salt: SESSION_COOKIE, maxAge: 3600 });
    const sessionHeaders = { Cookie: SESSION_COOKIE + "=" + cookie };
    const signedIn = await call("/api/auth/session", { headers: sessionHeaders }); assert.equal(signedIn.status, 200);
    assert.deepEqual((await signedIn.json()).v1Identity, IDENTITY);
    const runtime = await call("/v1/runtime", { headers: sessionHeaders }); assert.equal(runtime.status, 200);
    assert.deepEqual(await runtime.json(), { fixture: "actual-private-http-boundary-only" }); assert.equal(runtimeCalls, 1); assert(meCalls >= 2);
    const page = await call("/", { headers: sessionHeaders }); assert.equal(page.status, 200);
    const html = await page.text(); assert.match(html, /Sign out/); assert.doesNotMatch(html, /Local C26 acceptance|synthetic TEST accounts/);
    const signout = html.match(/name="(\$ACTION_ID_[^"]+)"/); assert(signout);
    const logoutAction = actionBody(signout[1]);
    const rejectedMutation = await call("/", { method: "POST", headers: { ...sessionHeaders, Origin: "https://oceaninfobio.com", "Content-Type": logoutAction.contentType }, body: logoutAction.body });
    assert.equal(rejectedMutation.status, 403);
    const loggedOut = await call("/", { method: "POST", headers: { ...sessionHeaders, Origin: SETTINGS.origin, "Content-Type": logoutAction.contentType }, body: logoutAction.body });
    assert.equal(loggedOut.status, 303); assert.equal(new URL(loggedOut.headers.get("location")!, SETTINGS.origin).pathname, "/login");
    assert(loggedOut.headers.getSetCookie().some(c => c.startsWith(SESSION_COOKIE + "=") && /Max-Age=0/i.test(c)));
    active = false;
    const revoked = await call("/v1/runtime", { headers: sessionHeaders }); assert.equal(revoked.status, 401); assert.equal(runtimeCalls, 1);
    const savedClosed = await call("/research/runs/submit", { method: "POST", headers: { ...sessionHeaders, Origin: SETTINGS.origin, "Content-Type": "application/json" }, body: "{}" }); assert.equal(savedClosed.status, 404);
  } finally {
    child.kill("SIGTERM");
    if (child.exitCode === null && child.signalCode === null) await Promise.race([once(child, "exit"), new Promise(resolve => setTimeout(resolve, 5000))]);
    if (child.exitCode === null && child.signalCode === null) { child.kill("SIGKILL"); await once(child, "exit"); }
    await new Promise<void>(resolve => backend.close(() => resolve()));
    assert(child.exitCode !== null || child.signalCode !== null, "Owned Next process is terminated");
  }
});
