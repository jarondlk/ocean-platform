# Application Security Model

## Scope

OCEAN Platform is an invite-only research application. It stores user
identity metadata, complete chat interactions, evidence snapshots, answer-audit
snapshots, and user feedback. The scientific corpus may be regenerated, but
application metadata is kept in separate tables and must be backed up
independently.

This document describes the controls implemented for the authorization MVP. It
does not claim that the system has completed an independent penetration test or
formal compliance assessment.

## Trust Boundaries

1. The browser authenticates with the configured OpenID Connect provider
   through Auth.js in Next.js.
2. Next.js accepts only identities with a verified provider email and mints a
   short-lived internal HS256 token for FastAPI.
3. FastAPI verifies the signature, issuer, audience, required claims, algorithm,
   and maximum 120-second lifetime.
4. FastAPI resolves the provider subject, current role, and suspension status
   from PostgreSQL on every request.
5. The API denies routes that do not have an explicit permission mapping.
6. PostgreSQL and FastAPI remain private application-network services in the
   production Compose topology. Only Next.js is bound to the host loopback
   interface for a TLS reverse proxy.
7. Ollama is a trusted private service. Prompts can contain retrieved scientific
   evidence and must not be sent to an unapproved external model endpoint.

The `INTERNAL_AUTH_SECRET` is shared only by Next.js and FastAPI.
`AUTH_SECRET` is used only by Auth.js. They must be generated independently and
must never be identical.

## Roles and Permissions

| Capability | Viewer | Researcher | Admin |
| --- | --- | --- | --- |
| Profile and overview | Yes | Yes | Yes |
| Chat and own feedback | Yes | Yes | Yes |
| Evidence search | Yes | Yes | Yes |
| Data, provenance, and evaluation | No | Yes | Yes |
| Run evaluations | No | Yes | Yes |
| Review and export all feedback | No | No | Yes |
| Pipeline controls | No | No | Yes |
| Database inspector and read-only SQL | No | No | Yes |
| System/debug surfaces | No | No | Yes |
| Invite, suspend, and change users | No | No | Yes |

Account type (`research`, `commercial`, or `internal`) is metadata for
segmentation and reporting; it does not grant permissions. Role changes and
suspensions take effect on the next API request.

## Cloud Authentication Decision

Production authentication remains OIDC-backed. The selected managed identity
provider should offer a conventional hosted email/password experience while
owning password hashing, reset and recovery, MFA, lockout, and abuse controls.
This application does not store production passwords.

The application login page intentionally exposes one path at a time:

- local development with `ENABLE_MOCK_LOGIN=true` shows only the guarded mock
  email/password form;
- staging and production show one neutral **Sign in** action that redirects to
  the configured managed provider.

Administrators cannot demote or suspend their own account. Feedback lookup uses
404 for another user's interaction so it does not disclose whether that
interaction exists.

## Invite Lifecycle

- There is no public registration or local password database.
- An invitation is matched to a normalized, verified OIDC email.
- The invitation must be `pending` and unexpired when first accepted.
- Accepted, revoked, and expired invitations cannot create an account.
- Administrators can revoke a pending invitation; repeated revocation is
  idempotent.
- An email already linked to a different provider identity is rejected.
- Invite acceptance, invitation creation/revocation, user changes, feedback
  changes, and feedback export create audit events.

## Fail-Closed Configuration

`DEPLOYMENT_ENV=staging` and `DEPLOYMENT_ENV=production` enforce:

- `AUTH_MODE=required`;
- `PERSIST_LOCAL_CHAT=false`;
- `ENABLE_MOCK_LOGIN=false`;
- non-placeholder internal signing secrets of at least 32 characters;
- explicit HTTPS CORS origins;
- real HTTPS Auth.js and OIDC URLs;
- distinct Auth.js and internal API signing secrets.

The API validates configuration during startup and again before protected
requests. The frontend validates its production authentication configuration
during server module initialization. A bad configuration prevents the
application from serving protected traffic.

`AUTH_MODE=disabled` creates a synthetic administrator and is permitted only for
isolated local development or tests. Never bind a disabled-auth instance to a
shared or public interface.

`ENABLE_MOCK_LOGIN=true` is a separate development/test harness that keeps
`AUTH_MODE=required`. It adds a conventional email/password form for three
fixed Viewer, Researcher, and Admin mock emails. Passwords are supplied only as
scrypt hashes through `MOCK_*_PASSWORD_HASH` environment settings; plaintext
passwords are not stored in the repository. Successful authentication creates
a signed Auth.js session and sends signed short-lived internal tokens through
the normal FastAPI authorization middleware. The API creates each fixed mock
identity once in the local test database, then resolves its current role,
account type, and status from PostgreSQL on every request. This permits real
foreign-key, suspension, chat, feedback, and audit testing but does not replace
the real-provider release smoke test. The API and frontend reject the flag in
staging and production. Use the harness only in an isolated development
environment because its mutations are real within that environment.

## Request and Response Protections

- The frontend proxy rejects cross-origin state-changing requests.
- The proxy rejects request bodies larger than 1 MiB using both declared and
  observed body size.
- Chat queries, model names, filter values, feedback comments, and SQL text have
  schema-level length limits.
- Authenticated API and proxy responses use `Cache-Control: no-store`.
- Browser responses include clickjacking, MIME-sniffing, referrer, permissions,
  opener, and no-index headers.
- Content Security Policy is enforced by the frontend response configuration.
- Production rate limits are keyed by user:

| Scope | Limit per minute |
| --- | ---: |
| Chat generation | 10 |
| Feedback writes | 30 |
| User/invitation administration | 10 |
| Pipeline starts | 2 |
| Evaluation mutations | 5 |

Production and staging use an atomic PostgreSQL-backed fixed-window limiter, so
multiple API workers share counters. Development and tests use an in-memory
backend. A gateway limit is still recommended as an additional denial-of-service
boundary for an internet-facing deployment.

The database query inspector accepts only one `SELECT` or `WITH` statement,
rejects mutation keywords after removing comments and string literals, wraps the
query in a row limit, opens a PostgreSQL read-only transaction, and applies a
five-second statement timeout. Production should additionally use a database
role without write privileges for inspector queries.

## Stored Data and Retention

The metadata database stores:

- provider subject, email, display name, role, account type, and status;
- invitations and expiration/acceptance timestamps;
- complete chat questions and answers;
- retrieved evidence and answer-audit snapshots;
- feedback reason codes and optional comments;
- security and administration audit events.

The approved retention policy is 90 days for completed or failed chat
interactions, their retrieved-evidence and answer-audit snapshots, and
associated feedback/comments. The `CHAT_RETENTION_DAYS` setting may shorten
this window but may not exceed 10 years. `python scripts/retention_cleanup.py`
performs a read-only dry run; deletion requires the explicit confirmation
string `DELETE EXPIRED CHAT DATA` and should only be run after the operator has
verified the backup and recovery window. Cleanup is transactional, excludes
running interactions and legal holds, deletes related feedback through the
relationship cascade, and records a batch audit event. Administrators can set
or clear a hold through `PATCH /admin/retention/interactions/{id}/hold`.

User identities, invitations, security/administration audit events, scientific
corpus records, and evaluation artifacts are outside this 90-day approval and
must not be deleted under it. Their retention needs a separate policy decision.

Never write tokens, OIDC client secrets, signing secrets, or database passwords
to audit metadata or application logs.

## Known Security Limitations

- No independent penetration test has been completed.
- Managed backup encryption, off-host retention, and PostgreSQL point-in-time
  recovery remain operator responsibilities. The repository provides verified
  logical backups and isolated restore tests.
- Secret rotation temporarily invalidates sessions/internal tokens and requires
  coordinated service restarts.
- The application does not yet provide an audit-event review UI or automatic
  alerting for repeated authorization failures.
- Scheduling the reviewed retention cleanup command remains an operator
  responsibility; no new GCP service topology is introduced by this change.
- Auth.js 5 remains a pinned beta dependency; upgrades require authentication
  regression testing.

## Authorization MVP Release Checklist

Current GCP evidence as of 2026-08-25: OCEAN Platform release `v0.2.2` runs with
`DEPLOYMENT_ENV=production`, `AUTH_MODE=required`, Google OIDC, distinct Secret
Manager-backed signing secrets, private FastAPI/Cloud SQL connectivity, and
default-deny API authorization. The administrator and approved researcher have
completed real-provider login; the OCEAN origin and callback are registered
while the former service is private for rollback; all 14 user/Admin routes were
smoke-tested against `ocean-postgres`; all migrated table counts matched; the
four OCEAN jobs passed bounded execution checks; Cloud Run emitted no
unresolved error-level or 5xx entries during final acceptance; CI and CodeQL
are enabled; and dependency alerts were resolved before the release. A
database URL exposed by a failed migration traceback was immediately
invalidated by rotating both affected database users and disabling both old
secret versions before traffic resumed.

The checklist remains reusable for every future release. It is intentionally
not marked permanently complete: secret rotation, dependency state, callback
configuration, role tests, backups, logs, and retention must be re-evaluated
for each deployment. The current unresolved operational items are audited
90-day retention enforcement, posted 24-hour/seven-day billing review,
production-environment approval rules, alerting, and an independent security
assessment.

- [ ] All backend tests and the frontend production build pass.
- [ ] The PostgreSQL migration/invite integration check passes.
- [ ] CI required checks are enabled on the default branch.
- [ ] Dependabot alerts and security updates are enabled.
- [ ] CodeQL default setup is enabled for Python and JavaScript/TypeScript.
- [ ] `DEPLOYMENT_ENV=production` and `AUTH_MODE=required` are set.
- [ ] Auth.js and internal signing secrets are distinct and rotated from test
      values.
- [ ] The production OIDC callback exactly matches the deployed HTTPS URL.
- [ ] FastAPI, PostgreSQL, and Ollama are not exposed publicly.
- [ ] TLS, backup, restore, log retention, retention enforcement, and incident
      contacts are verified.
- [ ] Viewer, researcher, admin, suspended-user, and uninvited-user behavior is
      manually smoke-tested with real provider accounts.
