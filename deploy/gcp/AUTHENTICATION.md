# Authentication on GCP

## Recommended prototype path

Keep the application's existing Auth.js OIDC flow and use a Google OAuth 2.0
web client as the first cloud identity provider. This is the smallest secure
change because the application already separates:

1. identity authentication at the OIDC provider;
2. invitation, role, and suspension decisions in PostgreSQL; and
3. frontend-to-API trust through a 60-second internal JWT.

Cloud Run is public at the platform layer so browsers can reach the login and
OIDC callback routes. The Next.js middleware still requires a session for
application pages. FastAPI is a localhost sidecar, has no public ingress of its
own, and accepts only internal JWTs minted by Next.js.

Identity Platform is a future option if the application needs multiple social,
SAML, or tenant-specific providers. IAP is a future perimeter option if access
becomes restricted entirely to internal Google Workspace identities. Enabling
either now would duplicate or replace the working invitation and role flow.

## Google OIDC settings

Create an OAuth 2.0 client with application type **Web application** in project
`data-infra-infobio`. Configure:

- authorized JavaScript origin: `PUBLIC_APP_URL`
- authorized redirect URI:
  `PUBLIC_APP_URL/api/auth/callback/google`

Set the non-secret service values:

```text
OIDC_PROVIDER_ID=google
OIDC_PROVIDER_NAME=Google
OIDC_ISSUER=https://accounts.google.com
OIDC_CLIENT_ID=<oauth-web-client-id>
AUTH_ALLOWED_PROVIDERS=google
```

Store the OAuth client secret in `onagawa-oidc-client-secret`. Store the
Auth.js session secret and internal API signing secret separately in
`onagawa-auth-secret` and `onagawa-internal-auth-secret`. The two signing
secrets must be different random values of at least 32 characters.

The provider ID is part of the durable identity key
`(auth_provider, auth_subject)`. Choose it before inviting cloud users and do
not rename it after users sign in without an explicit database migration.

## Institutional OIDC alternative

The existing institutional provider can be used without Identity Platform if
it supports OIDC discovery, authorization code flow, PKCE, state, nonce, and a
verified email claim. Use a stable provider ID such as `tohoku`, add
`PUBLIC_APP_URL/api/auth/callback/tohoku` at the provider, and set
`AUTH_ALLOWED_PROVIDERS=tohoku`.

## Authorization behavior retained in cloud

- A verified OIDC email must match a pending, unexpired invitation.
- Provider subject and provider ID are stored on first accepted login.
- The same email cannot silently link to another identity.
- Roles and suspensions are resolved from Cloud SQL on every API request.
- Unknown providers and unknown API routes fail closed.
- Mock login and disabled authentication remain forbidden in staging and
  production.

## Deployment validation

Before granting unauthenticated Cloud Run invocation:

1. create the first admin invitation in Cloud SQL;
2. confirm the exact HTTPS callback is registered;
3. deploy a no-traffic or restricted revision;
4. verify login, invitation acceptance, role enforcement, and logout;
5. suspend the test user and confirm the next API request is denied;
6. inspect logs to confirm tokens and secret values are never emitted; and
7. only then allow browser traffic to the service.

Do not enable IAP on the same prototype revision. IAP would add a second login
and requires a deliberate adapter from IAP identity assertions to the
application's invitation and role records.
