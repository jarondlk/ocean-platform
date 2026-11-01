import { hostSettings } from "../lib/settings.ts";
export const ENV = {
  DEPLOYMENT_ENV: "production", AUTH_MODE: "required", ENABLE_MOCK_LOGIN: "false", PERSIST_LOCAL_CHAT: "false",
  V1_PUBLIC_ORIGIN: "https://beta.oceaninfobio.com", AUTH_URL: "https://beta.oceaninfobio.com",
  V1_API_ORIGIN: "http://127.0.0.1:8000", V1_AUTH_SECRET: "a".repeat(64), V1_INTERNAL_AUTH_SECRET: "b".repeat(64),
  V1_INTERNAL_AUTH_ISSUER: "ocean-v1-frontend", V1_INTERNAL_AUTH_AUDIENCE: "ocean-v1-api",
  V1_GOOGLE_CLIENT_ID: "fixture-client.apps.googleusercontent.com", V1_GOOGLE_CLIENT_SECRET: "fixture-oauth-secret-not-live",
};
export const SETTINGS = hostSettings(ENV);
export const IDENTITY = { subject: "google-subject-fixture", email: "researcher@fixture.invalid", provider: "google" as const, emailVerified: true as const, name: "Fixture researcher" };
export const ACCOUNT = { id: "11111111-1111-4111-8111-111111111111", email: IDENTITY.email, display_name: IDENTITY.name,
  role: "researcher", account_type: "research", status: "active", permissions: ["chat:use", "data:read"], auth_provider: "google" };
export function request(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  if (!headers.has("host")) headers.set("host", "beta.oceaninfobio.com");
  if ((options.method ?? "GET") === "POST" && !headers.has("origin")) headers.set("origin", SETTINGS.origin);
  return new Request(SETTINGS.origin + path, { ...options, headers });
}
