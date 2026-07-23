import type { OIDCConfig } from "next-auth/providers";
import type { Profile } from "next-auth";
import NextAuth from "next-auth";

import { mintInternalAccessToken } from "@/lib/internal-auth";
import { validateFrontendSecurityConfiguration } from "@/lib/security-config";


const API_BASE_URL = process.env.API_BASE_URL || "http://127.0.0.1:8000";
validateFrontendSecurityConfiguration();

function oidcProvider(): OIDCConfig<Profile> {
  return {
    id: "oidc",
    name: process.env.OIDC_PROVIDER_NAME || "Organization account",
    type: "oidc",
    issuer: process.env.OIDC_ISSUER || "https://invalid.example",
    clientId: process.env.OIDC_CLIENT_ID || "not-configured",
    clientSecret: process.env.OIDC_CLIENT_SECRET || "not-configured",
    authorization: {
      params: {
        scope: "openid email profile",
      },
    },
    checks: ["pkce", "state", "nonce"],
    profile(profile) {
      return {
        id: String(profile.sub || ""),
        email: profile.email,
        name: profile.name,
        image: typeof profile.picture === "string" ? profile.picture : null,
      };
    },
  };
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [oidcProvider()],
  pages: {
    signIn: "/login",
    error: "/login",
  },
  session: {
    strategy: "jwt",
    maxAge: 8 * 60 * 60,
  },
  callbacks: {
    async signIn({ account, profile, user }) {
      if (
        !account ||
        !profile?.sub ||
        !profile.email ||
        profile.email_verified !== true
      ) {
        return false;
      }
      try {
        const internalToken = await mintInternalAccessToken({
          subject: String(profile.sub),
          provider: account.provider,
          email: profile.email,
          emailVerified: true,
          name: profile.name || user.name || null,
        });
        const response = await fetch(`${API_BASE_URL}/me`, {
          headers: {
            Authorization: `Bearer ${internalToken}`,
            Accept: "application/json",
          },
          cache: "no-store",
        });
        return response.ok;
      } catch {
        return false;
      }
    },
    async jwt({ token, account, profile }) {
      if (account && profile?.sub && profile.email) {
        token.authSubject = String(profile.sub);
        token.authProvider = account.provider;
        token.email = profile.email;
        token.providerEmailVerified = profile.email_verified === true;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.authSubject = String(token.authSubject || "");
        session.user.authProvider = String(token.authProvider || "");
        session.user.providerEmailVerified =
          token.providerEmailVerified === true;
      }
      return session;
    },
  },
});
