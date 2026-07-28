import type { OIDCConfig } from "next-auth/providers";
import type { Profile } from "next-auth";
import NextAuth, { CredentialsSignin } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import type { Provider } from "next-auth/providers";

import { mintInternalAccessToken } from "@/lib/internal-auth";
import {
  authenticateMockAccount,
  isMockLoginRole,
} from "@/lib/mock-login";
import {
  mockLoginEnabled,
  oidcProviderId,
  validateFrontendSecurityConfiguration,
} from "@/lib/security-config";


const API_BASE_URL = process.env.API_BASE_URL || "http://127.0.0.1:8000";
validateFrontendSecurityConfiguration();

function oidcProvider(): OIDCConfig<Profile> {
  return {
    id: oidcProviderId(),
    name: process.env.OIDC_PROVIDER_NAME || "Managed identity provider",
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

function mockCredentialsProvider(): Provider {
  return Credentials({
    id: "mock-credentials",
    name: "Mock email and password",
    credentials: {
      email: { label: "Email", type: "email" },
      password: { label: "Password", type: "password" },
    },
    authorize(credentials) {
      const account = authenticateMockAccount(
        credentials.email,
        credentials.password,
      );
      if (!account) return null;
      return {
        id: `mock-login:${account.role}`,
        email: account.email,
        name: account.name,
        mockLoginRole: account.role,
      };
    },
  });
}

const providers: Provider[] = [oidcProvider()];
if (mockLoginEnabled()) {
  providers.push(mockCredentialsProvider());
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers,
  logger: {
    error(error) {
      if (error instanceof CredentialsSignin) return;
      console.error(error);
    },
  },
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
      if (account?.provider === "mock-credentials") {
        return (
          mockLoginEnabled() &&
          isMockLoginRole(user.mockLoginRole) &&
          user.id === `mock-login:${user.mockLoginRole}` &&
          user.email === `${user.mockLoginRole}@mock.invalid`
        );
      }
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
    async jwt({ token, account, profile, user }) {
      if (
        account?.provider === "mock-credentials" &&
        isMockLoginRole(user.mockLoginRole)
      ) {
        token.authSubject = `mock-login:${user.mockLoginRole}`;
        token.authProvider = "mock-credentials";
        token.email = `${user.mockLoginRole}@mock.invalid`;
        token.providerEmailVerified = true;
        token.mockLoginRole = user.mockLoginRole;
        return token;
      }
      if (account && profile?.sub && profile.email) {
        token.authSubject = String(profile.sub);
        token.authProvider = account.provider;
        token.email = profile.email;
        token.providerEmailVerified = profile.email_verified === true;
        token.mockLoginRole = undefined;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.authSubject = String(token.authSubject || "");
        session.user.authProvider = String(token.authProvider || "");
        session.user.providerEmailVerified =
          token.providerEmailVerified === true;
        session.user.mockLoginRole =
          typeof token.mockLoginRole === "string"
            ? token.mockLoginRole
            : undefined;
      }
      return session;
    },
  },
});
