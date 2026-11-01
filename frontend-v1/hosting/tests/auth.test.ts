import assert from "node:assert/strict";
import test from "node:test";
import { Auth } from "@auth/core";
import { encode } from "next-auth/jwt";
import { authConfiguration, SESSION_COOKIE } from "../lib/auth-config.ts";
import { SETTINGS, IDENTITY, request } from "./fixtures.ts";

test("actual auth provider discovery exposes only independent Google and a canonical callback", async () => {
  const response = await Auth(request("/api/auth/providers"), authConfiguration(SETTINGS, async () => true));
  const providers = await response.json();
  assert.deepEqual(Object.keys(providers), ["google"]);
  assert.equal(providers.google.callbackUrl, SETTINGS.origin + "/api/auth/callback/google");
});
test("actual CSRF endpoint sets only Secure HttpOnly host-only v1 cookies", async () => {
  const response = await Auth(request("/api/auth/csrf"), authConfiguration(SETTINGS, async () => true));
  assert.equal(response.status, 200); assert.equal(typeof (await response.json()).csrfToken, "string");
  const cookies = response.headers.getSetCookie(); assert(cookies.length > 0);
  for (const value of cookies) { assert.match(value, /^__Host-ocean-v1-/); assert.match(value, /; Path=\//i); assert.match(value, /; HttpOnly/i); assert.match(value, /; Secure/i); assert.match(value, /; SameSite=Lax/i); assert.doesNotMatch(value, /Domain=/i); }
});
test("actual encrypted session is revalidated against current API authority on every read", async () => {
  let active = true, calls = 0;
  const config = authConfiguration(SETTINGS, async identity => { calls++; assert.deepEqual(identity, IDENTITY); return active; });
  const value = await encode({ token: { sub: IDENTITY.subject, v1Identity: IDENTITY }, secret: SETTINGS.authSecret, salt: SESSION_COOKIE, maxAge: 3600 });
  const req = () => request("/api/auth/session", { headers: { Cookie: `${SESSION_COOKIE}=${value}` } });
  const accepted = await Auth(req(), config); assert.equal(accepted.status, 200);
  const session = await accepted.json(); assert.deepEqual(session.v1Identity, IDENTITY); assert.equal(session.role, undefined);
  assert.equal(calls, 1); active = false;
  const denied = await Auth(req(), config); const deniedSession = await denied.json();
  assert(!deniedSession?.v1Identity); assert.equal(calls, 2);
  assert(denied.headers.getSetCookie().some(cookie => cookie.startsWith(SESSION_COOKIE + "=") && /Max-Age=0/i.test(cookie)));
});
test("legacy cookie names and wrong independent signing secret cannot authenticate", async () => {
  const config = authConfiguration(SETTINGS, async () => { throw new Error("Should not reach current account"); });
  const good = await encode({ token: { v1Identity: IDENTITY }, secret: SETTINGS.authSecret, salt: SESSION_COOKIE });
  const wrong = await encode({ token: { v1Identity: IDENTITY }, secret: "c".repeat(64), salt: SESSION_COOKIE });
  for (const cookie of [`authjs.session-token=${good}`, `next-auth.session-token=${good}`, `${SESSION_COOKIE}=${wrong}`]) {
    const response = await Auth(request("/api/auth/session", { headers: { Cookie: cookie } }), config);
    assert(!(await response.json())?.v1Identity);
  }
});
test("actual logout requires CSRF and clears the independent session", async () => {
  const config = authConfiguration(SETTINGS, async () => true);
  const csrfResponse = await Auth(request("/api/auth/csrf"), config), csrf = (await csrfResponse.json()).csrfToken;
  const csrfCookies = csrfResponse.headers.getSetCookie().map(c => c.split(";")[0]).join("; ");
  const value = await encode({ token: { sub: IDENTITY.subject, v1Identity: IDENTITY }, secret: SETTINGS.authSecret, salt: SESSION_COOKIE });
  const response = await Auth(request("/api/auth/signout", { method: "POST", headers: {
    Cookie: `${csrfCookies}; ${SESSION_COOKIE}=${value}`, "Content-Type": "application/x-www-form-urlencoded",
  }, body: new URLSearchParams({ csrfToken: csrf, callbackUrl: "https://evil.invalid" }) }), config);
  assert(response.headers.getSetCookie().some(cookie => cookie.startsWith(SESSION_COOKIE + "=") && /Max-Age=0/i.test(cookie)));
  assert.equal(response.headers.get("location"), SETTINGS.origin + "/");
  const noCsrf = await Auth(request("/api/auth/signout", { method: "POST", headers: { Cookie: `${SESSION_COOKIE}=${value}`, "Content-Type": "application/x-www-form-urlencoded" }, body: "callbackUrl=/" }), config);
  assert(!noCsrf.headers.getSetCookie().some(cookie => cookie.startsWith(SESSION_COOKIE + "=") && /Max-Age=0/i.test(cookie)));
});
