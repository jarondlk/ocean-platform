import "server-only";


const PRODUCTION_LIKE = new Set(["staging", "production"]);
const PLACEHOLDER_MARKERS = [
  "replace-with",
  "not-configured",
  "change-me",
  "changeme",
  "invalid.example",
  "identity.example.org",
];

function setting(name: string, fallback = ""): string {
  return (process.env[name] || fallback).trim();
}

function placeholder(value: string): boolean {
  const normalized = value.toLowerCase();
  return PLACEHOLDER_MARKERS.some((marker) => normalized.includes(marker));
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

  const issuer = setting("OIDC_ISSUER");
  const clientId = setting("OIDC_CLIENT_ID");
  const clientSecret = setting("OIDC_CLIENT_SECRET");
  if (
    !issuer.startsWith("https://") ||
    placeholder(issuer) ||
    !clientId ||
    placeholder(clientId) ||
    !clientSecret ||
    placeholder(clientSecret)
  ) {
    throw new Error(
      "Production OIDC settings must use a real HTTPS issuer and " +
        "non-placeholder client credentials",
    );
  }
}

export function localAuthDisabled(): boolean {
  validateFrontendSecurityConfiguration();
  return setting("AUTH_MODE", "required").toLowerCase() === "disabled";
}
