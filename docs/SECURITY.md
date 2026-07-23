# Application Security Model

## Scope

Onagawa Source Chat is an invite-only research application. It stores user
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

Administrators cannot demote or suspend their own account. Feedback lookup uses
404 for another user's interaction so it does not disclose whether that
interaction exists.

## Invite Lifecycle

- There is no public registration or local password database.
- An invitation is matched to a normalized, verified OIDC email.
- The invitation must be `pending` and unexpired when first accepted.
- Accepted, revoked, and expired invitations cannot create an account.
- An email already linked to a different provider identity is rejected.
- Invite acceptance, invitation creation, user changes, feedback changes, and
  feedback export create audit events.

## Fail-Closed Configuration

`DEPLOYMENT_ENV=staging` and `DEPLOYMENT_ENV=production` enforce:

- `AUTH_MODE=required`;
- `PERSIST_LOCAL_CHAT=false`;
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

## Request and Response Protections

- The frontend proxy rejects cross-origin state-changing requests.
- The proxy rejects request bodies larger than 1 MiB using both declared and
  observed body size.
- Chat queries, model names, filter values, feedback comments, and SQL text have
  schema-level length limits.
- Authenticated API and proxy responses use `Cache-Control: no-store`.
- Browser responses include clickjacking, MIME-sniffing, referrer, permissions,
  opener, and no-index headers.
- Content Security Policy currently runs in report-only mode. Review violations
  before switching it to enforcement.
- Production rate limits are keyed by user:

| Scope | Limit per minute |
| --- | ---: |
| Chat generation | 10 |
| Feedback writes | 30 |
| User/invitation administration | 10 |
| Pipeline starts | 2 |
| Evaluation mutations | 5 |
| Database queries | 30 |

The limiter is intentionally in-memory for the one-process MVP deployment. Do
not run multiple API workers or hosts until this state is moved to a shared
store such as Redis or enforced by the gateway.

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

The MVP does not automatically expire these records. Before handling real
sensitive data, the operator must approve a retention period, document deletion
and legal-hold procedures, and schedule tested cleanup and backup retention.
Ninety days is a reasonable initial chat/feedback proposal, but it is not
enforced by the current code.

Never write tokens, OIDC client secrets, signing secrets, or database passwords
to audit metadata or application logs.

## Known Security Limitations

- No independent penetration test has been completed.
- CSP is report-only.
- Rate-limit state is per API process.
- PostgreSQL backup and point-in-time recovery are operator responsibilities.
- Secret rotation temporarily invalidates sessions/internal tokens and requires
  coordinated service restarts.
- The application does not yet provide an audit-event review UI or automatic
  alerting for repeated authorization failures.
- Python dependencies are not yet represented by a fully transitive,
  cross-platform lock file.

## Authorization MVP Release Checklist

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
- [ ] TLS, backup, restore, log retention, and incident contacts are verified.
- [ ] Viewer, researcher, admin, suspended-user, and uninvited-user behavior is
      manually smoke-tested with real provider accounts.
