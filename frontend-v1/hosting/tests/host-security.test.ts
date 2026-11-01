import assert from "node:assert/strict";
import test from "node:test";
import { jwtVerify } from "jose";
import { hostSettings, requestAllowed, HostConfigurationError } from "../lib/settings.ts";
import { currentAccount, hostIdentity, mintInternalToken } from "../lib/identity.ts";
import { sessionFetcher } from "../lib/session-fetch.ts";
import { ENV, IDENTITY, ACCOUNT, SETTINGS, request } from "./fixtures.ts";

test("only complete independent HTTPS host and explicit loopback sidecar settings are accepted", () => {
  assert.equal(hostSettings(ENV).apiOrigin, "http://127.0.0.1:8000");
  assert(Object.isFrozen(hostSettings(ENV)));
  for (const key of Object.keys(ENV)) { const env: Record<string, string> = { ...ENV }; delete env[key]; assert.throws(() => hostSettings(env), HostConfigurationError, key); }
});
for (const [key, value] of [
  ["DEPLOYMENT_ENV", "development"], ["AUTH_MODE", "disabled"], ["ENABLE_MOCK_LOGIN", "true"],
  ["PERSIST_LOCAL_CHAT", "true"], ["V1_PUBLIC_ORIGIN", "https://oceaninfobio.com"],
  ["V1_PUBLIC_ORIGIN", "https://evil.invalid"], ["AUTH_URL", "https://oceaninfobio.com"],
  ["NEXTAUTH_URL", "https://legacy.invalid"], ["V1_API_ORIGIN", "https://legacy.invalid"],
  ["V1_API_ORIGIN", "http://127.0.0.1:8000/"], ["V1_AUTH_SECRET", "short"],
  ["V1_INTERNAL_AUTH_SECRET", ENV.V1_AUTH_SECRET], ["V1_INTERNAL_AUTH_ISSUER", "ocean-platform-frontend"],
  ["V1_INTERNAL_AUTH_AUDIENCE", "ocean-platform-api"], ["V1_GOOGLE_CLIENT_ID", "not-a-client"],
  ["V1_GOOGLE_CLIENT_SECRET", "tiny"], ["NEXT_PUBLIC_INTERNAL_SECRET", "never-publish"],
  ["AUTH_SECRET", "ambient-legacy-secret"], ["AUTH_GOOGLE_ID", "ambient-client"],
  ["AUTH_REDIRECT_PROXY_URL", "https://legacy.invalid/api/auth"],
] as const) test(`host settings reject ${key}=${value.length > 70 ? "overlong" : value}`, () => {
  assert.throws(() => hostSettings({ ...ENV, [key]: value }), HostConfigurationError);
});

test("request guard permits exact load-balancer headers and rejects spoofed/ambiguous origins", () => {
  assert(requestAllowed(request("/"), SETTINGS));
  assert(requestAllowed(request("/", { headers: { host: "beta.oceaninfobio.com", "x-forwarded-host": "beta.oceaninfobio.com", "x-forwarded-proto": "https", "x-forwarded-port": "443" } }), SETTINGS));
  for (const headers of [
    { host: "oceaninfobio.com" }, { host: "service.run.app", "x-forwarded-host": "beta.oceaninfobio.com" },
    { host: "beta.oceaninfobio.com", "x-forwarded-host": "beta.oceaninfobio.com,evil.invalid" },
    { host: "beta.oceaninfobio.com", "x-forwarded-proto": "http" },
    { host: "beta.oceaninfobio.com", "x-forwarded-port": "8443" },
    { host: "beta.oceaninfobio.com", forwarded: "host=beta.oceaninfobio.com;proto=https" },
  ] as Array<Record<string, string>>) assert.equal(requestAllowed(request("/", { headers }), SETTINGS), false);
  for (const origin of ["https://oceaninfobio.com", "https://other.oceaninfobio.com", "null", "https://beta.oceaninfobio.com.evil.invalid"]) {
    assert.equal(requestAllowed(request("/api/auth/signout", { method: "POST", headers: { origin } }), SETTINGS), false);
  }
  const missing = request("/api/auth/signout", { method: "POST" }); missing.headers.delete("origin");
  assert.equal(requestAllowed(missing, SETTINGS), false);
});

test("internal identity token is server-bound, short-lived and excludes authorization roles", async () => {
  const token = await mintInternalToken(IDENTITY, SETTINGS);
  const { payload, protectedHeader } = await jwtVerify(token, new TextEncoder().encode(SETTINGS.internalSecret), {
    algorithms: ["HS256"], issuer: SETTINGS.issuer, audience: SETTINGS.audience, maxTokenAge: 60,
  });
  assert.equal(protectedHeader.alg, "HS256"); assert.equal(payload.sub, IDENTITY.subject);
  assert.equal(payload.email_verified, true); assert.equal(payload.provider, "google");
  assert.equal(payload.exp! - payload.iat!, 60); assert.equal(payload.role, undefined); assert.equal(payload.permissions, undefined);
  await assert.rejects(jwtVerify(token, new TextEncoder().encode(SETTINGS.authSecret)));
  await assert.rejects(jwtVerify(token, new TextEncoder().encode(SETTINGS.internalSecret), { issuer: "ocean-platform-frontend" }));
  await assert.rejects(jwtVerify(token, new TextEncoder().encode(SETTINGS.internalSecret), { audience: "ocean-platform-api" }));
});

test("current account check resolves the private API and rejects revocation, malformed/current-other identity and redirects", async () => {
  let calls = 0;
  const fetcher = (async (url, init) => { calls++; assert.equal(url, SETTINGS.apiOrigin + "/me"); assert.equal(init?.redirect, "error");
    assert.equal(init?.cache, "no-store"); assert.equal(new Headers(init?.headers).has("cookie"), false);
    await jwtVerify(new Headers(init?.headers).get("authorization")!.slice(7), new TextEncoder().encode(SETTINGS.internalSecret), { issuer: SETTINGS.issuer, audience: SETTINGS.audience });
    return Response.json(ACCOUNT); }) as typeof fetch;
  assert.equal(await currentAccount(IDENTITY, SETTINGS, fetcher), true); assert.equal(calls, 1);
  for (const value of [{ ...ACCOUNT, status: "suspended" }, { ...ACCOUNT, email: "other@fixture.invalid" },
    { ...ACCOUNT, auth_provider: "mock-credentials" }, { ...ACCOUNT, id: "admin" }, { ...ACCOUNT, permissions: [" data:read"] }, {}]) {
    assert.equal(await currentAccount(IDENTITY, SETTINGS, (async () => Response.json(value)) as typeof fetch), false);
  }
  assert.equal(await currentAccount(IDENTITY, SETTINGS, (async () => new Response("", { status: 403 })) as typeof fetch), false);
  assert.equal(await currentAccount(IDENTITY, SETTINGS, (async () => { throw new Error("private diagnostic"); }) as typeof fetch), false);
  assert.equal(await currentAccount(IDENTITY, SETTINGS, (async () => new Response("x".repeat(65537))) as typeof fetch), false);
});

test("incomplete provider identity cannot mint a trusted user token", async () => {
  for (const value of [{ ...IDENTITY, provider: "mock-credentials" }, { ...IDENTITY, emailVerified: false }, { ...IDENTITY, subject: "" }, { ...IDENTITY, email: "not-an-email" }]) {
    assert.equal(hostIdentity(value), null); await assert.rejects(mintInternalToken(value as typeof IDENTITY, SETTINGS));
  }
});

test("explicit host fetcher sends same-origin cookies only on fixed relative v1 paths", async () => {
  const calls: Array<[string, RequestInit]> = [];
  const fetcher = sessionFetcher((async (input, init) => { calls.push([String(input), init!]); return new Response("{}", { status: 503 }); }) as typeof fetch);
  for (const path of ["/v1/runtime", "/catalogue/list", "/research/investigations/list"]) await fetcher(path, { method: path === "/v1/runtime" ? "GET" : "POST", credentials: "omit" });
  assert.equal(calls.length, 3); assert(calls.every(([, init]) => init.credentials === "same-origin" && init.cache === "no-store" && init.redirect === "error"));
  for (const path of ["https://evil.invalid/catalogue/list", "//evil.invalid/research/list", "/v1/runtimeevil", "/catalogue/../admin", "/research/%2e%2e/admin", "/research/runs/list?target=evil", "/catalogue/list#fragment", "/catalogue\\list"]) await assert.rejects(fetcher(path));
  await assert.rejects(fetcher("/v1/runtime", { headers: { Authorization: "Bearer caller" } }));
  assert.equal(calls.length, 3);
});
