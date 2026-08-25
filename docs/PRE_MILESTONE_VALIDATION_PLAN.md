# Pre-Milestone Validation Plan

> **Historical gate:** This plan records the repository-local validation state
> from 2026-07-26. Its provider-deployment blockers were subsequently exercised
> through the GCP migration and Phase 7 runbooks. The stable `v0.1.0` GCP
> prototype is live as of 2026-08-25. Keep this document as evidence of the
> pre-cloud safety work; use `docs/PHASE7_RELEASE_RUNBOOK.md` and
> `deploy/gcp/MIGRATION_PLAN.md` for current release status.

This is the final validation gate for the authorization, feedback, evaluation,
and manual-pipeline iteration. It separates checks that can run safely in the
local repository from destructive drills and deployment-provider controls.

## Latest Local Evidence

Validated on 2026-07-26:

- Python: 383 passed, 3 skipped, 73.10% aggregate coverage.
- Ruff: active Python boundary passed.
- Frontend: TypeScript check and production build passed.
- PostgreSQL: Alembic is at `20260726_0002` (head).
- PostgreSQL integration: three real-database checks passed, including
  migration/invite persistence, database-backed mock suspension, audited
  invitation mutation foreign keys, and shared rate limiting.
- Recovery: a fresh custom-format database backup restored into a disposable
  database, matched all 16 recorded table counts, and the temporary database
  was removed.
- Browser mutation checks passed against a restored disposable database with
  independent Admin and Viewer/Researcher sessions: invitation create/revoke,
  suspend/deny/reactivate, chat feedback create/revise/admin review, and a
  one-work-unit Standard evaluation.
- Destructive browser drill passed in a temporary source/artifact copy:
  preflight required the verified backup and exact `RESET DATABASE` phrase,
  backup completed, `load_db.py --reset --embed` completed, all 323 document
  embeddings were rebuilt, and application metadata survived.
- The command preview was corrected to show the selected reset/upsert, embed,
  skip-SST, and batch-size options before preflight.

These results closed the repository-local implementation and validation gates
at that date. Real OIDC and provider-operated deployment gates were still open
then and are retained below as the historical handoff into the GCP phases.

## Local Blockers Implemented

### 1. Make development mock identities database-backed

Status: implemented and covered by unit, PostgreSQL integration, and isolated
browser suspension tests.

Before this patch, the three development email/password identities received
signed role claims but were not stored in `app_user`. That was sufficient for
read-only authorization tests, but prevented realistic audited mutations:

- invitation and user-admin audit events reference the acting user's
  `app_user` primary key;
- persisted chat interactions reference the user's `app_user` primary key;
- suspension could not take effect because the mock identity was reconstructed
  as active from its signed role claim on every request.

The development/test-only resolver now creates each fixed mock subject once in
`app_user`, then resolves role, account type, and status from PostgreSQL on
every request. It never recreates or resets an existing mock user's
role/status at login, and all production/staging prohibitions on
`ENABLE_MOCK_LOGIN` remain in force.

Automated coverage confirms:

- first login creates exactly one fixed mock user and repeated login is
  idempotent;
- mock role/account changes are reflected on the next request;
- a suspended mock user receives 403 on the next API request;
- mock chat persistence, feedback creation/revision, and admin audit events
  satisfy their foreign keys;
- staging and production still reject mock login.

### 2. Add invitation cleanup

Status: implemented with an Admin-only, audited, idempotent revoke endpoint and
browser control.

Invitation state already supported `revoked`, but the application had no
revoke API or browser control. The new Admin-only action revokes a pending
invitation, records an audit event, and treats repeated revoke requests as
idempotent. This lets browser checks clean up a tagged invitation without
deleting audit history.

### 3. Add a destructive reset confirmation

Status: implemented in both API validation and browser UI, with exact-phrase
regression tests and a completed disposable reset drill.

The pipeline already defaulted to dry-run and required `backup_database` before
a real `load_db`. It now additionally requires the exact `RESET DATABASE`
confirmation phrase in both API validation and the browser UI when:

```text
dry_run=false AND reset_database=true AND load_db is selected
```

The server rejects a missing or incorrect phrase even if a client bypasses the
UI.

## Browser Mutation Matrix

Run this matrix only against a disposable migrated database restored from a
verified backup. Use a unique `browser-smoke-<commit>-<timestamp>` tag in every
test record.

| Check | Browser procedure | Pass evidence | Cleanup |
| --- | --- | --- | --- |
| Invite | Admin creates a Viewer invitation for a unique `.invalid` email, refreshes, and revokes it | Pending then revoked state; create and revoke audit events | Keep the revoked audit record in the disposable database |
| Suspension | Viewer signs in once; Admin suspends Viewer; Viewer refreshes an authenticated page; Admin reactivates Viewer | Next Viewer request is 403 while suspended; login works after reactivation; two user-change audit events | Viewer restored to active |
| Feedback mutation | Viewer asks one small tagged question, submits positive feedback, then revises it to negative with a valid reason and comment | One completed chat; feedback PUT creates then updates the same row; revised rating/reason/comment visible to Admin; audit events persisted | Dispose of the entire test database after evidence capture |
| Evaluation execution | Researcher starts Standard with `question_ids=ctd_01`, Baseline only, quality off, judge off, and a unique tag | Job moves queued → running → completed; exactly one answer work unit; CSV/meta/report can be reopened from Runs | Retain the tagged evaluation artifact as release evidence or delete the disposable artifact volume |
| Role boundaries | Use isolated Viewer, Researcher, and Admin browser contexts | Viewer cannot access Evaluation/Admin/Pipeline; Researcher can run Evaluation but not Admin/Pipeline; Admin can access all | Close all contexts |

Use independent browser contexts for the role matrix. Sequential sign-out and
sign-in in one cookie jar is useful UI coverage but does not prove simultaneous
session isolation.

Executed on 2026-07-26 with host-isolated cookie jars and separate frontend
instances for the Admin and Viewer/Researcher sessions. Every matrix row passed;
the disposable database and temporary artifact copy were removed afterward.

## Destructive Pipeline Drill

Never run the reset drill against the active development database or the
working repository's only artifact tree.

1. Commit or snapshot the exact source under test.
2. Create an ephemeral application stack with:
   - a separate PostgreSQL database/volume;
   - a writable copy of `data/` and the raw SST tree;
   - a separate pipeline-run and backup directory;
   - the same application commit and locked dependencies.
3. Restore the latest verified logical backup into the disposable database.
4. Record pre-run application-metadata and corpus table counts.
5. In the browser, select Full rebuild, disable Dry run, select Reset database,
   enter the required confirmation phrase, and run Preflight.
6. Confirm Preflight shows the verified backup stage before `load_db`, then
   start the job.
7. Require every stage to complete and verify:
   - the backup manifest and SHA-256 verification;
   - no loss of users, invitations, chat, feedback, or audit events;
   - expected corpus keys and row counts;
   - retrieval search-vector refresh;
   - 323 retrieval documents and 323 embeddings for the current fixture;
   - a usable chat response and a reopenable pipeline manifest/log.
8. Restore the pre-run backup into a second disposable database and compare
   all recorded table counts.
9. Destroy both disposable databases and artifact copies.

The normal scheduled-update path remains transactional `--upsert`; a reset is
a recovery/rebuild drill, not the default update procedure.

The 2026-07-26 drill used only `backup_database` plus `load_db`, because its
purpose was to exercise the destructive boundary using already validated
artifacts. It completed in the disposable database and temporary artifact
copy; the full log confirmed `--reset --embed`, 323 regenerated embeddings,
and preserved application-metadata records.

## Deployment-Provider Gates

These controls cannot be completed or truthfully verified from the repository
alone. Record provider screenshots, command output, or exported configuration
with the release evidence.

### TLS and network exposure

- Deploy a maintained reverse proxy in front of `127.0.0.1:3000`.
- Issue a certificate for the real hostname and test automatic renewal.
- Redirect HTTP to HTTPS; enable HSTS only after renewal and rollback are
  proven.
- Verify FastAPI, PostgreSQL, and Ollama are unreachable from the public
  network.
- Verify the production OIDC callback and CORS origin exactly match the HTTPS
  hostname.

### Off-host backups and point-in-time recovery

- Send verified encrypted backups to storage outside the application host and
  restrict restore/delete permissions.
- Define retention plus measured RPO and RTO.
- For managed PostgreSQL, enable continuous WAL/PITR and retention appropriate
  to the approved RPO.
- Perform both a logical-backup restore and a point-in-time restore into new
  infrastructure; validate users, audit events, chats, feedback, corpus rows,
  and application startup.

The repository proves logical backup creation and isolated restore. It does not
currently provide off-host retention or PITR.

### Secret rotation

- Rotate the OIDC client secret at the identity provider.
- Generate distinct new `AUTH_SECRET` and `INTERNAL_AUTH_SECRET` values.
- Rotate the database password and update `DATABASE_URL`.
- Because the current signing configuration has no overlap window, use a
  controlled maintenance/restart window for the frontend and API.
- Verify old sessions are invalid, a new OIDC login succeeds, internal tokens
  are accepted for no more than 120 seconds, and no secret appears in logs.

### Remote CI and repository protection

Require these default-branch checks:

- Backend tests and security boundary
- Frontend typecheck and build
- PostgreSQL migration and metadata integration
- Dependency review, when available

Also require pull requests, dismiss stale approvals, block force pushes and
branch deletion, restrict bypasses, enable Dependabot/security updates, CodeQL,
secret scanning, and push protection where the repository plan supports them.

The local workflow has read-only token permissions, full-SHA-pinned official
actions, locked dependency installation, PostgreSQL integration, repeated
upserts, and backup restore testing. Remote enforcement still needs to be
enabled and exported from the Git hosting service; it cannot be inferred from
workflow YAML.

## Release Decision

- **Historical decision on 2026-07-26:** safe to commit and push the
  repository-local production-readiness implementation after the final
  validation commands remained green.
- **Locally proven:** role-aware mock sessions, immediate suspension,
  invitation revocation, feedback mutation, one-unit evaluation execution,
  verified logical backup, and destructive corpus reset/re-embedding.
- **Closed after this document:** Google OIDC, Cloud Run/Cloud SQL deployment,
  invited administrator/researcher login, immutable build and rollback,
  bounded Vertex evaluation, and repository security checks passed during the
  GCP and Phase 7 releases.
- **Still operational follow-up:** retention enforcement, time-delayed cost
  reviews, secret-rotation drills, alerting, and broader-cohort approval remain
  live operational work; they do not invalidate the bounded `v0.1.0`
  prototype release.
