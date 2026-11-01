# Independent OCEAN v1 host

This Node/Next entry reuses `frontend-v1/src/RuntimeApp` and supplies independent
Google sign-in, encrypted host-only sessions and a bounded same-origin proxy.
The original static preview and legacy frontend are unchanged. This checkpoint
allows configured saved reads and cancellation intent, with new research,
synthesis, experiment decisions/start and investigation editing closed.

## Build and local checks

Install both exact dependency locks because the shared UI source is outside the
host directory. No legacy frontend package, credential or cloud account is used.

```sh
npm --prefix frontend-v1 ci --ignore-scripts
npm --prefix frontend-v1/hosting ci --ignore-scripts
npm --prefix frontend-v1/hosting audit --omit=dev --audit-level=moderate
npm --prefix frontend-v1/hosting test
npm --prefix frontend-v1/hosting run typecheck
npm --prefix frontend-v1/hosting run build
npm --prefix frontend-v1/hosting run test:server
```

`build` packages the standalone server and copies only its generated static
assets. `npm start` runs `.next/standalone/hosting/server.js`, default port3000
(or explicit `PORT`) with `HOSTNAME=0.0.0.0`. It is not a static export and must
not be replaced with the preview server. Container/provider setup is separate.

Build and checks need no real secret or Google request. `test:server` starts a
new owned loopback API fixture on8000 and standalone server on an ephemeral port,
uses explicit synthetic secrets, and blocks external fetches except a test-only
Google discovery response. It exercises actual multipart login→Google303,
encrypted session/current-account check, private API JWT/proxy, Origin denial,
logout and revocation; it never follows the Google URL or executes a live OAuth
callback. It refuses a pre-existing8000listener and closes its own resources.

## Explicit runtime configuration

Supply these only through separately reviewed runtime secret/config references:

| Variable | Required value/boundary |
|---|---|
| `DEPLOYMENT_ENV` | `production` or `staging` |
| `AUTH_MODE` | `required` |
| `ENABLE_MOCK_LOGIN`, `PERSIST_LOCAL_CHAT` | Literal `false` |
| `V1_PUBLIC_ORIGIN`, `AUTH_URL` | Exact `https://beta.oceaninfobio.com` |
| `V1_API_ORIGIN` | Explicit `http://127.0.0.1:8000` API sidecar; no remote/ambient fallback |
| `V1_AUTH_SECRET` | Independent random session secret, at least48non-whitespace characters |
| `V1_INTERNAL_AUTH_SECRET` | Different independent API signing secret, at least48non-whitespace characters; same value supplied only to beta API verification |
| `V1_INTERNAL_AUTH_ISSUER` | `ocean-v1-frontend` |
| `V1_INTERNAL_AUTH_AUDIENCE` | `ocean-v1-api` |
| `V1_GOOGLE_CLIENT_ID`, `V1_GOOGLE_CLIENT_SECRET` | Independent beta Google OAuth enrollment; exact callback `/api/auth/callback/google` |

Do not set `AUTH_REDIRECT_PROXY_URL` or ambient `AUTH_GOOGLE_*`/`AUTH_OIDC_*`
provider variables. Conflicting `AUTH_SECRET`, `NEXTAUTH_SECRET` or `NEXTAUTH_URL`
are rejected. No password, DSN, signing seed or secret value belongs in source.
The host's strict settings are loaded lazily at request time; a missing runtime
configuration returns unavailable rather than using legacy/fixture defaults.

The load balancer must preserve exact `Host: beta.oceaninfobio.com` and overwrite
untrusted forwarding headers. If present, `X-Forwarded-Host` must equal that host,
`X-Forwarded-Proto` must be `https` and `X-Forwarded-Port` must be `443`; the
ambiguous standardized `Forwarded` header is rejected. All state-changing requests,
including POST read RPCs and server actions, require exact beta `Origin`.
Cloud ingress/direct-URL/DNS/TLS behavior is a separate actual-provider gate.

The API must resolve the token's Google subject against explicitly enrolled
independent beta users on every request. Host `/me` checks reject missing,
suspended, mismatched or malformed identities. This host does not copy users,
accept invites automatically, assign roles or trust browser session roles.

## Security and acceptance boundaries

Cookies use only `__Host-ocean-v1-*` names with Secure, HttpOnly, Path=/,
SameSite=Lax and no Domain. Session and internal API secrets are distinct.
The internal HS256JWT expires after60seconds, names beta issuer/audience and
contains no role/permission assertion; roles remain current database authority.
Browser-supplied bearer/cookie/owner/forwarded headers are never sent upstream.

The explicit browser adapter adds same-origin session credentials to existing
typed clients through RuntimeApp's optional fetcher. It rejects absolute or
ambiguous paths and JS-supplied bearer tokens. Default preview/client callers
retain their original credential-free behavior. No global browser fetch patch
or client-readable internal signing token is used.

Proxy methods/paths are fixed. It bounds request bytes at64KiB, response bytes
at8MiB and stalled body/fetch waits at15seconds, denies redirects, returns no-store
responses and strips upstream Set-Cookie/Location/private headers. It never
forwards an alternate destination, provider request or legacy route. Current
backend permission and DTO validation remain authoritative.

Actual Google callback/token exchange, independent secret contents, operator
enrollment, hosted session/ingress/isolation and full integrated UI behavior need
later live evidence. Initial missing snapshot/services remain unavailable.
This host alone does not implement Cloud Tasks or the production experiment
supervisor, clear P2 D26-07, authorize data transfer or make beta deployable.

Implementation references: [Auth.js cookies](https://authjs.dev/reference/core#cookies),
[trusted host](https://authjs.dev/reference/nextjs#trusthost),
[Google provider](https://authjs.dev/getting-started/providers/google). The pinned
installed implementation was inspected for ambient redirect-proxy behavior.
