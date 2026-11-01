import { SignJWT } from "jose";
import type { HostSettings } from "./settings.ts";

export type HostIdentity = { subject: string; email: string; provider: "google"; emailVerified: true; name: string | null };
export function hostIdentity(value: unknown): HostIdentity | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (v.provider !== "google" || v.emailVerified !== true || typeof v.subject !== "string"
      || !v.subject || v.subject.length > 255 || /[\s\x00-\x1f]/.test(v.subject)
      || typeof v.email !== "string" || v.email.length > 320 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.email)
      || (v.name !== null && (typeof v.name !== "string" || v.name.length > 255))) return null;
  return { subject: v.subject, email: v.email, provider: "google", emailVerified: true, name: v.name as string | null };
}
export async function mintInternalToken(identity: HostIdentity, settings: HostSettings): Promise<string> {
  if (!hostIdentity(identity)) throw new Error("Incomplete v1 identity");
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ email: identity.email, email_verified: true, provider: identity.provider, name: identity.name ?? undefined })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" }).setSubject(identity.subject)
    .setIssuer(settings.issuer).setAudience(settings.audience).setIssuedAt(now).setExpirationTime(now + 60)
    .sign(new TextEncoder().encode(settings.internalSecret));
}

/** The API resolves current active/invited identity; the encrypted browser session grants no role. */
export async function currentAccount(identity: HostIdentity, settings: HostSettings, fetcher: typeof fetch = fetch): Promise<boolean> {
  try {
    const response = await fetcher(settings.apiOrigin + "/me", {
      method: "GET", redirect: "error", cache: "no-store", signal: AbortSignal.timeout(5000),
      headers: { Accept: "application/json", Authorization: "Bearer " + await mintInternalToken(identity, settings) },
    });
    if (!response.ok) { await response.body?.cancel(); return false; }
    const declared = response.headers.get("content-length");
    if (!response.body || (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > 65536))) { await response.body?.cancel(); return false; }
    const reader = response.body.getReader(); let total = 0, text = "";
    const decoder = new TextDecoder("utf-8", { fatal: true });
    try {
      while (true) { const part = await reader.read(); if (part.done) break;
        total += part.value.byteLength; if (total > 65536) { await reader.cancel(); return false; }
        text += decoder.decode(part.value, { stream: true });
      }
      text += decoder.decode();
    } finally { reader.releaseLock(); }
    const value = JSON.parse(text);
    return value?.status === "active" && value.auth_provider === "google"
      && typeof value.email === "string" && value.email.toLowerCase() === identity.email.toLowerCase()
      && typeof value.id === "string" && /^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(value.id)
      && ["viewer", "researcher", "admin"].includes(value.role)
      && ["research", "commercial", "internal"].includes(value.account_type)
      && Array.isArray(value.permissions) && value.permissions.length <= 256
      && value.permissions.every((p: unknown) => typeof p === "string" && /^[a-zA-Z0-9._:-]{1,128}$/.test(p));
  } catch { return false; }
}
