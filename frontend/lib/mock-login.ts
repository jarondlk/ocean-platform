import "server-only";

import { scryptSync, timingSafeEqual } from "node:crypto";

import { mockLoginEnabled } from "@/lib/security-config";


export const MOCK_LOGIN_ROLES = ["viewer", "researcher", "admin"] as const;
export type MockLoginRole = (typeof MOCK_LOGIN_ROLES)[number];

type MockLoginAccount = {
  email: string;
  name: string;
  passwordHashSetting: string;
  role: MockLoginRole;
};

export const MOCK_LOGIN_ACCOUNTS: readonly MockLoginAccount[] = [
  {
    email: "viewer@mock.invalid",
    name: "Mock Viewer",
    passwordHashSetting: "MOCK_VIEWER_PASSWORD_HASH",
    role: "viewer",
  },
  {
    email: "researcher@mock.invalid",
    name: "Mock Researcher",
    passwordHashSetting: "MOCK_RESEARCHER_PASSWORD_HASH",
    role: "researcher",
  },
  {
    email: "admin@mock.invalid",
    name: "Mock Admin",
    passwordHashSetting: "MOCK_ADMIN_PASSWORD_HASH",
    role: "admin",
  },
] as const;

export function isMockLoginRole(value: unknown): value is MockLoginRole {
  return (
    typeof value === "string" &&
    MOCK_LOGIN_ROLES.includes(value as MockLoginRole)
  );
}

function passwordHash(account: MockLoginAccount): string {
  return (process.env[account.passwordHashSetting] || "").trim();
}

function verifyScryptPassword(password: string, encodedHash: string): boolean {
  const [algorithm, saltHex, derivedHex] = encodedHash.split("$");
  if (
    algorithm !== "scrypt" ||
    !saltHex ||
    !derivedHex ||
    !/^[a-f0-9]{32}$/i.test(saltHex) ||
    !/^[a-f0-9]{128}$/i.test(derivedHex)
  ) {
    return false;
  }
  const expected = Buffer.from(derivedHex, "hex");
  const actual = scryptSync(
    password,
    Buffer.from(saltHex, "hex"),
    expected.length,
    {
      N: 16_384,
      r: 8,
      p: 1,
      maxmem: 64 * 1024 * 1024,
    },
  );
  return timingSafeEqual(actual, expected);
}

export function authenticateMockAccount(
  rawEmail: unknown,
  rawPassword: unknown,
): MockLoginAccount | null {
  if (
    !mockLoginEnabled() ||
    typeof rawEmail !== "string" ||
    typeof rawPassword !== "string" ||
    rawEmail.length > 320 ||
    rawPassword.length < 12 ||
    rawPassword.length > 256
  ) {
    return null;
  }

  const email = rawEmail.trim().toLowerCase();
  const account =
    MOCK_LOGIN_ACCOUNTS.find((candidate) => candidate.email === email) || null;
  const comparisonAccount = account || MOCK_LOGIN_ACCOUNTS[0];
  const valid = verifyScryptPassword(
    rawPassword,
    passwordHash(comparisonAccount),
  );
  return account && valid ? account : null;
}
