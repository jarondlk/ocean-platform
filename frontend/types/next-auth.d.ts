import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      authSubject: string;
      authProvider: string;
      providerEmailVerified: boolean;
    } & DefaultSession["user"];
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    authSubject?: string;
    authProvider?: string;
    providerEmailVerified?: boolean;
  }
}
