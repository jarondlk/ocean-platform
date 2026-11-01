import "server-only";
import NextAuth from "next-auth";
import { authConfiguration } from "./auth-config";
import { hostSettings } from "./settings";

// Runtime-only validation: a build neither needs nor obtains live credentials.
export const { handlers, auth, signIn, signOut } = NextAuth(() => authConfiguration(hostSettings(process.env)));
