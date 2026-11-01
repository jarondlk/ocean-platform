/** Strict non-discovering host configuration. Never import legacy environment defaults. */
export type HostSettings = Readonly<{
  origin: string; apiOrigin: string; authSecret: string; internalSecret: string;
  issuer: "ocean-v1-frontend"; audience: "ocean-v1-api"; googleClientId: string; googleClientSecret: string;
}>;
export class HostConfigurationError extends Error {
  constructor() { super("The independent v1 host configuration is incomplete or invalid"); }
}
const invalid = (): never => { throw new HostConfigurationError(); };

export function hostSettings(env: Record<string, string | undefined>): HostSettings {
  if (!["production", "staging"].includes(env.DEPLOYMENT_ENV ?? "") || env.AUTH_MODE !== "required"
      || env.ENABLE_MOCK_LOGIN !== "false" || env.PERSIST_LOCAL_CHAT !== "false") return invalid();
  const origin = env.V1_PUBLIC_ORIGIN;
  if (origin !== "https://beta.oceaninfobio.com" || env.AUTH_URL !== origin
      || (env.NEXTAUTH_URL !== undefined && env.NEXTAUTH_URL !== origin)
      || env.AUTH_REDIRECT_PROXY_URL !== undefined) return invalid();
  // This host and FastAPI are colocated sidecars, not a user-selected remote proxy.
  const apiOrigin = env.V1_API_ORIGIN;
  if (apiOrigin !== "http://127.0.0.1:8000") return invalid();
  const authSecret = env.V1_AUTH_SECRET ?? "", internalSecret = env.V1_INTERNAL_AUTH_SECRET ?? "";
  if (authSecret.length < 48 || internalSecret.length < 48 || authSecret === internalSecret
      || /\s/.test(authSecret) || /\s/.test(internalSecret)
      || (env.AUTH_SECRET !== undefined && env.AUTH_SECRET !== authSecret)
      || (env.NEXTAUTH_SECRET !== undefined && env.NEXTAUTH_SECRET !== authSecret)) return invalid();
  if (env.V1_INTERNAL_AUTH_ISSUER !== "ocean-v1-frontend" || env.V1_INTERNAL_AUTH_AUDIENCE !== "ocean-v1-api") return invalid();
  const googleClientId = env.V1_GOOGLE_CLIENT_ID ?? "", googleClientSecret = env.V1_GOOGLE_CLIENT_SECRET ?? "";
  if (!/^[A-Za-z0-9-]+\.apps\.googleusercontent\.com$/.test(googleClientId)
      || googleClientSecret.length < 16 || googleClientSecret.length > 4096 || /\s/.test(googleClientSecret)) return invalid();
  if (Object.entries(env).some(([name, value]) => /^(NEXT_PUBLIC_.*(?:SECRET|TOKEN)|AUTH_(?:GOOGLE|OIDC)_)/.test(name) && value)) return invalid();
  return Object.freeze({ origin, apiOrigin, authSecret, internalSecret,
    issuer: "ocean-v1-frontend", audience: "ocean-v1-api", googleClientId, googleClientSecret });
}

/** Exact public host is required even behind an explicitly configured load balancer. */
export function requestAllowed(request: Request, settings: Pick<HostSettings, "origin">): boolean {
  const expected = new URL(settings.origin), headers = request.headers;
  if (headers.get("host") !== expected.host || headers.has("forwarded")) return false;
  for (const [name, value] of [["x-forwarded-host", expected.host], ["x-forwarded-proto", "https"], ["x-forwarded-port", "443"]]) {
    if (headers.has(name) && headers.get(name) !== value) return false;
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(request.method) && headers.get("origin") !== settings.origin) return false;
  return true;
}
