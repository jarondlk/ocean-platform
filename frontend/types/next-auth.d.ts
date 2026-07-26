import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      authSubject: string;
      authProvider: string;
      providerEmailVerified: boolean;
      mockLoginRole?: string;
    } & DefaultSession["user"];
  }

  interface User {
    mockLoginRole?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    authSubject?: string;
    authProvider?: string;
    providerEmailVerified?: boolean;
    mockLoginRole?: string;
  }
}
