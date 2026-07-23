import "server-only";

import { SignJWT } from "jose/jwt/sign";
import type { Session } from "next-auth";


type Identity = {
  subject: string;
  provider: string;
  email: string;
  emailVerified: boolean;
  name?: string | null;
};

function signingSecret(): Uint8Array {
  const secret = process.env.INTERNAL_AUTH_SECRET || "";
  if (secret.length < 32) {
    throw new Error(
      "INTERNAL_AUTH_SECRET must be configured with at least 32 characters",
    );
  }
  return new TextEncoder().encode(secret);
}

export async function mintInternalAccessToken(identity: Identity): Promise<string> {
  if (
    !identity.subject ||
    !identity.provider ||
    !identity.email ||
    identity.emailVerified !== true
  ) {
    throw new Error("Cannot mint an internal token for an incomplete identity");
  }
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({
    email: identity.email,
    email_verified: true,
    name: identity.name || undefined,
    provider: identity.provider,
  })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setSubject(identity.subject)
    .setIssuer(
      process.env.INTERNAL_AUTH_ISSUER || "onagawa-source-chat-frontend",
    )
    .setAudience(
      process.env.INTERNAL_AUTH_AUDIENCE || "onagawa-source-chat-api",
    )
    .setIssuedAt(now)
    .setExpirationTime(now + 60)
    .sign(signingSecret());
}

export async function tokenForSession(session: Session): Promise<string> {
  const user = session.user;
  if (!user?.email) {
    throw new Error("Authenticated session has no email");
  }
  return mintInternalAccessToken({
    subject: user.authSubject,
    provider: user.authProvider,
    email: user.email,
    emailVerified: user.providerEmailVerified,
    name: user.name,
  });
}
