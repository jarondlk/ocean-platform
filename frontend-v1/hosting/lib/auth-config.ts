import type { NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";
import { currentAccount, hostIdentity, type HostIdentity } from "./identity.ts";
import type { HostSettings } from "./settings.ts";

export const SESSION_COOKIE = "__Host-ocean-v1-session";
const cookie = (name: string, maxAge?: number) => ({ name,
  options: { httpOnly: true, secure: true, sameSite: "lax" as const, path: "/", ...(maxAge ? { maxAge } : {}) } });

export function authConfiguration(settings: HostSettings,
    accountCheck: (identity: HostIdentity) => Promise<boolean> = (identity) => currentAccount(identity, settings)): NextAuthConfig {
  return {
    secret: settings.authSecret, trustHost: true, useSecureCookies: true, basePath: "/api/auth",
    providers: [Google({ clientId: settings.googleClientId, clientSecret: settings.googleClientSecret,
      authorization: { params: { scope: "openid email profile" } }, checks: ["pkce", "state", "nonce"] })],
    pages: { signIn: "/login", error: "/login" },
    session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
    cookies: {
      sessionToken: cookie(SESSION_COOKIE), csrfToken: cookie("__Host-ocean-v1-csrf"),
      callbackUrl: cookie("__Host-ocean-v1-callback"),
      pkceCodeVerifier: cookie("__Host-ocean-v1-pkce", 900), state: cookie("__Host-ocean-v1-state", 900),
      nonce: cookie("__Host-ocean-v1-nonce", 900),
    },
    // Log only a fixed category; errors may contain OAuth URLs or private profile data.
    logger: { error() { console.error("V1 authentication unavailable"); }, warn() {}, debug() {} },
    callbacks: {
      async signIn({ account, profile }) {
        const identity = hostIdentity({ subject: profile?.sub, email: profile?.email,
          provider: account?.provider, emailVerified: profile?.email_verified, name: profile?.name ?? null });
        return !!identity && await accountCheck(identity);
      },
      async jwt({ token, account, profile }) {
        if (account) {
          const identity = hostIdentity({ subject: profile?.sub, email: profile?.email,
            provider: account.provider, emailVerified: profile?.email_verified, name: profile?.name ?? null });
          if (!identity) return null;
          token.v1Identity = identity;
        }
        const identity = hostIdentity(token.v1Identity);
        if (!identity || !await accountCheck(identity)) return null;
        return { ...token, v1Identity: identity };
      },
      async session({ session, token }) {
        const identity = hostIdentity(token.v1Identity);
        if (!identity) throw new Error("V1 session unavailable");
        return { expires: session.expires, user: { name: identity.name, email: identity.email }, v1Identity: identity };
      },
      async redirect({ url }) {
        // No caller-supplied post-auth destination; v1 always returns to its own root.
        return url === "/login" || url === settings.origin + "/login" ? settings.origin + "/login" : settings.origin + "/";
      },
    },
  };
}
