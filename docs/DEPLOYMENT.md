# Production Deployment

## Supported Topology

The production Compose file is intended for a single application host:

```text
Internet
  -> TLS reverse proxy
  -> 127.0.0.1:3000 (Next.js)
  -> private Compose network
       -> FastAPI:8000
       -> PostgreSQL:5432
       -> approved private Ollama endpoint
```

Do not use `docker-compose.yml` or `docker-compose.next.yml` as production
definitions. They intentionally publish development ports, mount the repository,
and enable reload behavior. `docker-compose.production.yml` publishes only
Next.js to host loopback.

## Required Configuration

Copy `.env.production.example` to a secret-managed location outside the
repository and replace every placeholder. At minimum, set:

```dotenv
DEPLOYMENT_ENV=production
AUTH_MODE=required
PERSIST_LOCAL_CHAT=false

AUTH_URL=https://rag.example.org
AUTH_TRUST_HOST=false
AUTH_SECRET=<independent random value>
INTERNAL_AUTH_SECRET=<different independent random value>
INTERNAL_AUTH_ISSUER=onagawa-source-chat-frontend
INTERNAL_AUTH_AUDIENCE=onagawa-source-chat-api

OIDC_ISSUER=https://identity.example.org
OIDC_CLIENT_ID=<provider client id>
OIDC_CLIENT_SECRET=<provider client secret>
OIDC_PROVIDER_NAME=Organization account

CORS_ORIGINS=https://rag.example.org
POSTGRES_USER=onagawa
POSTGRES_PASSWORD=<random database password>
POSTGRES_DB=onagawa_rag
DATABASE_URL=postgresql://onagawa:<url-encoded-password>@postgres:5432/onagawa_rag
OLLAMA_BASE_URL=http://<private-ollama-host>:11434
```

Generate the two signing secrets independently:

```bash
openssl rand -base64 48
openssl rand -base64 48
```

Do not commit the generated values. Restrict the environment file to the service
account. If the reverse proxy must provide the public host dynamically, enable
`AUTH_TRUST_HOST=true` only when the proxy overwrites untrusted `Host`,
`Forwarded`, and `X-Forwarded-*` headers.

Register this exact provider callback:

```text
https://rag.example.org/api/auth/callback/oidc
```

## Start and Verify

Validate expansion before starting:

```bash
podman compose -f docker-compose.production.yml config --quiet
```

Start the services:

```bash
podman compose -f docker-compose.production.yml up -d --build
```

The API container applies Alembic migrations before starting FastAPI. Bootstrap
the first administrator from an API container:

```bash
podman compose -f docker-compose.production.yml exec api \
  python scripts/invite_user.py admin@example.org \
  --role admin \
  --account-type internal
```

Verify:

- the reverse proxy returns HTTPS only;
- `/health/live` is reachable through internal monitoring;
- unauthenticated access to `/stats` is rejected;
- the API and database host ports are closed;
- viewer, researcher, and admin navigation and API permissions match
  `docs/SECURITY.md`;
- a suspended user is rejected on the next request;
- security headers are present on an application response.

## TLS and Proxy

Terminate TLS at a maintained reverse proxy and forward only to
`127.0.0.1:3000`. Redirect HTTP to HTTPS. Add HSTS only after the HTTPS
configuration and certificate renewal path have been tested; an incorrect
long-lived HSTS policy can lock users out.

Do not route external traffic to FastAPI, PostgreSQL, or Ollama. The frontend
proxy is the browser-to-API boundary and attaches the short-lived internal
identity token.

## Backups and Restore

Back up the complete PostgreSQL database, not only scientific corpus tables.
The application metadata tables contain users, invitations, chat history,
feedback, and audit events.

Before launch:

1. schedule encrypted `pg_dump` or managed PostgreSQL backups;
2. define retention and off-host storage;
3. restore a backup into an isolated database;
4. apply migrations to the restored copy;
5. verify user, chat, feedback, and audit-event counts;
6. record recovery time and recovery point objectives.

Generated data artifacts under `data/` require a separate backup decision.
Corpus data can often be regenerated, while provenance manifests and evaluation
run history may be operationally important.

## Secret Rotation

Rotate secrets after suspected exposure and on the operator's normal schedule:

1. stop new traffic;
2. rotate the OIDC client secret at the provider;
3. generate new, distinct `AUTH_SECRET` and `INTERNAL_AUTH_SECRET` values;
4. rotate the database password and update `DATABASE_URL`;
5. restart the frontend and API together;
6. revoke existing provider sessions when warranted;
7. review audit events and logs for suspicious activity.

Changing signing secrets invalidates active sessions or in-flight internal
tokens. The internal token lifetime is at most 120 seconds.

## Scaling Constraint

The authorization MVP rate limiter is in-process. Run one FastAPI worker.
Before adding workers or hosts, replace it with a shared limiter or enforce
equivalent per-identity limits at the gateway.

## Rollback

Application rollback must not automatically downgrade the database. Keep the
previous image, take a database backup before migrations, and confirm that the
previous code can read the upgraded schema. Use Alembic downgrade only after
reviewing the migration's data-loss behavior.
