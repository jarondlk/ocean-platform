/** Explicit test-process external OIDC transport fixture. Never imported by the host. */
const originalFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const url = new URL(typeof input === "string" || input instanceof URL ? input : input.url);
  if (url.origin === "https://accounts.google.com" && url.pathname === "/.well-known/openid-configuration") {
    return Response.json({
      issuer: "https://accounts.google.com", authorization_endpoint: "https://accounts.google.com/o/oauth2/v2/auth",
      token_endpoint: "https://oauth2.googleapis.com/token", jwks_uri: "https://www.googleapis.com/oauth2/v3/certs",
      response_types_supported: ["code"], subject_types_supported: ["public"],
      id_token_signing_alg_values_supported: ["RS256"], token_endpoint_auth_methods_supported: ["client_secret_post", "client_secret_basic"],
    });
  }
  if (url.origin === "http://127.0.0.1:8000") return originalFetch(input, init);
  throw new Error("External provider calls are gated in local host acceptance");
};
