import "server-only";


const PRODUCTION_LIKE = new Set(["staging", "production"]);
const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);
const FALSE_VALUES = new Set(["0", "false", "no", "off", ""]);
const MOCK_PASSWORD_HASH_SETTINGS = [
  "MOCK_VIEWER_PASSWORD_HASH",
  "MOCK_RESEARCHER_PASSWORD_HASH",
  "MOCK_ADMIN_PASSWORD_HASH",
] as const;
const SCRYPT_HASH_PATTERN = /^scrypt\$[a-f0-9]{32}\$[a-f0-9]{128}$/;
const PLACEHOLDER_MARKERS = [
  "replace-with",
  "not-configured",
  "change-me",
  "changeme",
  "placeholder",
  "generate-",
  "invalid.example",
  "identity.example.org",
  "rag.example.org",
];

function setting(name: string, fallback = ""): string {
  return (process.env[name] || fallback).trim();
}

function booleanSetting(name: string, fallback = "false"): boolean {
  const value = setting(name, fallback).toLowerCase();
  if (TRUE_VALUES.has(value)) return true;
  if (FALSE_VALUES.has(value)) return false;
  throw new Error(
    `${name} must be one of true/false, yes/no, on/off, or 1/0`,
  );
}

function placeholder(value: string): boolean {
  const normalized = value.toLowerCase();
  return (
    value.includes("<") ||
    value.includes(">") ||
    PLACEHOLDER_MARKERS.some((marker) => normalized.includes(marker))
  );
}

function secureHttpsUrl(value: string): boolean {
  if (placeholder(value)) return false;
  try {
    const parsed = new URL(value);
    return (
      parsed.protocol === "https:" &&
      Boolean(parsed.hostname) &&
      !parsed.username &&
      !parsed.password
    );
  } catch {
    return false;
  }
}

export function validateFrontendSecurityConfiguration(): void {
  const deploymentEnv = setting("DEPLOYMENT_ENV", "development").toLowerCase();
  if (!["development", "test", "staging", "production"].includes(deploymentEnv)) {
    throw new Error(
      "DEPLOYMENT_ENV must be development, test, staging, or production",
    );
  }

  const authMode = setting("AUTH_MODE", "required").toLowerCase();
  if (!["required", "disabled"].includes(authMode)) {
    throw new Error("AUTH_MODE must be either required or disabled");
  }
  const mockLogin = booleanSetting("ENABLE_MOCK_LOGIN");
  if (mockLogin && PRODUCTION_LIKE.has(deploymentEnv)) {
    throw new Error(
      "ENABLE_MOCK_LOGIN is forbidden in staging and production",
    );
  }
  if (mockLogin && authMode !== "required") {
    throw new Error(
      "ENABLE_MOCK_LOGIN requires AUTH_MODE=required",
    );
  }
  if (mockLogin) {
    for (const name of MOCK_PASSWORD_HASH_SETTINGS) {
      if (!SCRYPT_HASH_PATTERN.test(setting(name))) {
        throw new Error(
          `${name} must be a valid scrypt password hash when mock login is enabled`,
        );
      }
    }
  }
  if (!PRODUCTION_LIKE.has(deploymentEnv)) return;

  if (authMode !== "required") {
    throw new Error("AUTH_MODE=disabled is forbidden in staging and production");
  }

  const authSecret = setting("AUTH_SECRET");
  const internalSecret = setting("INTERNAL_AUTH_SECRET");
  if (
    authSecret.length < 32 ||
    internalSecret.length < 32 ||
    placeholder(authSecret) ||
    placeholder(internalSecret)
  ) {
    throw new Error(
      "AUTH_SECRET and INTERNAL_AUTH_SECRET must be non-placeholder values " +
        "of at least 32 characters",
    );
  }
  if (authSecret === internalSecret) {
    throw new Error("AUTH_SECRET and INTERNAL_AUTH_SECRET must be different");
  }

  const authUrl = setting("AUTH_URL");
  const issuer = setting("OIDC_ISSUER");
  const clientId = setting("OIDC_CLIENT_ID");
  const clientSecret = setting("OIDC_CLIENT_SECRET");
  if (
    !secureHttpsUrl(authUrl) ||
    !secureHttpsUrl(issuer) ||
    !clientId ||
    placeholder(clientId) ||
    !clientSecret ||
    placeholder(clientSecret)
  ) {
    throw new Error(
      "Production authentication settings must use real HTTPS application " +
        "and OIDC URLs with non-placeholder client credentials",
    );
  }
}

export function localAuthDisabled(): boolean {
  validateFrontendSecurityConfiguration();
  return setting("AUTH_MODE", "required").toLowerCase() === "disabled";
}

export function mockLoginEnabled(): boolean {
  validateFrontendSecurityConfiguration();
  return booleanSetting("ENABLE_MOCK_LOGIN");
}
