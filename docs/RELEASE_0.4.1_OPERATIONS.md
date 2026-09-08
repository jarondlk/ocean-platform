# v0.4.1 deployment record

> Historical release record. The current deployment is v0.4.2; see
> [`RELEASE_0.4.2_OPERATIONS.md`](RELEASE_0.4.2_OPERATIONS.md).

Verified 2026-09-06 JST. This records operational deployment evidence, not a
scientific classification decision. The retained ANEMONE pilot remains
`unknown`; no classification review was approved or applied during release.

[GitHub release v0.4.1](https://github.com/jarondlk/ocean-platform/releases/tag/v0.4.1)
was published at 2026-09-06 09:45:22 UTC.

## Source and deployment

- Source: `706348eda354320c24f5a18c9600e3d6341bec8a`, merged through
  [PR #54](https://github.com/jarondlk/ocean-platform/pull/54). The same source
  was pushed to `main` and `gcp-dev` before tagging.
- Build: `97dbe5d3-c464-4e14-9350-72c83b4b7ec1`; all test and image-build
  steps succeeded.
- API digest: `sha256:5155e52191891e553877cfd630646d4fbbada9232ae2fa5f57bc69cd411b365a`.
- Frontend digest: `sha256:639cf7262d6d491f4f9356d3530628b87cf378f709e2dd327b26c9d051f7dce5`.
- Cloud Run: `ocean-platform-v041-706348e`, Ready, 100% traffic.
  The release was initially verified at the default Cloud Run URL.
- Previous revision retained: `ocean-platform-v040-a63885a`. Review schema and
  later user-data compatibility before rollback; do not automatically downgrade
  the database or overwrite later records.
- Migration execution `ocean-migrate-dvs49` applied revisions
  `20260905_0009`, `20260905_0010`, and `20260905_0011`. The final check found
  27 tables, no missing tables or columns, and the vector extension available.
- `ocean-migrate`, `ocean-pipeline`, `ocean-embedding`, `ocean-evaluation`, and
  `ocean-anemone-process` are Ready on the API digest above. Existing manual
  execution, zero-retry, timeout, and bounded/default dry-run controls remain.

## Classification application boundary

- Execution `ocean-anemone-process-4v2xv` registered the fixed workload subject
  `ocean-jobs@data-infra-infobio.iam.gserviceaccount.com` as the internal
  operational admin. The generated application user ID is retained in the
  production audit log.
- The processing job default is an offline `apply-classification` plan with no
  review ID and no `--execute`. The web service cannot launch Cloud Run jobs.
- Scientific approval and operational application remain separate authenticated
  events. Reviewer and operator identities are server-derived, not editable
  client fields.
- The post-migration database contains zero classification reviews,
  classification review events, applications, and application events. The live
  pilot therefore remains `unknown` and excluded from environmental-only
  analyses and linking.

## Backup and preservation

Both archives are stored under
`gs://data-infra-infobio-ocean-data/backups/`. Each archive was restored into a
disposable database, every table count matched, and the disposable database was
removed.

| Check | Execution | Archive | SHA-256 |
| --- | --- | --- | --- |
| Before migration | `ocean-pipeline-5lkl8` | `20260906T094734Z-v0.4.1-pre-migration-ocean_platform.dump` | `005f76875d43eec8116ed8ed85c063ee3ecb1f040021fabd6a49452dca18edf2` |
| After migration | `ocean-pipeline-xsxw9` | `20260906T100839Z-v0.4.1-post-migration-ocean_platform.dump` | `d38cd237507040e3abc989b0ca361576370cd81aef90715d5831f129c5a664da` |

The final archive is 2,830,631 bytes with 27 tables and 256 TOC entries.
Selected counts are 5 users, 22 audit events, 64 chat interactions, 8 feedback
records, 325 retrieval documents, 1 eDNA sample, 1 eDNA assay, 70 detections,
and 4 internal-standard rows. Classification review/application tables contain
zero rows.

## Verification

- Release gate: 688 backend tests passed, 12 expected service-gated skips,
  78.31% aggregate coverage; 12 PostgreSQL integration tests passed through
  schema head `20260905_0011`.
- Frontend: 18 tests, typecheck, and the 24-route production build passed.
  Ruff, dependency consistency, `pip check`, the production npm audit, diff
  checks, GitHub CI, and CodeQL passed.
- Cloud Build produced both immutable images from the merged release commit.
- The new revision became Ready with no error-level startup/runtime log entries.
  Anonymous HTTP checks reached the login page, returned the auth-session
  endpoint successfully, and received 401 from protected health and
  classification-review proxy routes.
- An authenticated visual browser pass was not repeated in this operation
  because the local Mac session was locked. Existing automated auth/role tests
  and the production fail-closed boundary passed; repeat the normal researcher
  and admin UI matrix before claiming scientific workflow acceptance.

## Cost and remaining gates

Minimum zero / maximum one service instance, concurrency 20, existing container
sizes, Cloud SQL `db-f1-micro`, 10 GB SSD, seven retained automated backups,
seven-day point-in-time recovery, identities, and secret references were
preserved. The user-confirmed ceiling remains JPY 20,000 per month. The active
account could confirm billing linkage but lacks permission to read budget
objects, so current alert thresholds and posted spend require billing-console
review by an authorized billing user.

Remaining scientific acceptance work is tracked in
[`ANEMONE_NEXT_PATCH.md`](ANEMONE_NEXT_PATCH.md). Exclusion-reason presentation
was subsequently deployed in v0.4.2; the deferred researcher matrix for
source-only, environmental-only, empty-cohort, citation, controlled application,
and rollback behavior remains. `unknown` is a valid final result.

## Custom domain follow-up — 2026-09-08

This section is the pre-v0.4.2 custom-domain checkpoint. The later v0.4.2
rollout corrected the API origin and supersedes its forward-looking rollout
instructions; see the v0.4.2 operations record.

- [`https://oceaninfobio.com`](https://oceaninfobio.com) is the canonical URL.
- Post-release revision `ocean-platform-00012-ps6` received 100% traffic at this
  checkpoint and reused the v0.4.1 API/frontend image digests. Frontend
  `AUTH_URL` was the canonical domain. API `CORS_ORIGINS` still named the
  fallback Cloud Run origin; render and verify both values from the canonical
  URL in the v0.4.2 deployment.
- The apex domain serves a valid HTTPS login page. Auth.js reports the canonical
  sign-in and `/api/auth/callback/google` URLs, the session endpoint returns
  successfully, and anonymous protected-health access returns 401.
- The default Cloud Run URL redirects authentication to `oceaninfobio.com` and
  remains available for rollback/operations.
- Google OAuth retains both exact origins and callbacks while custom-domain
  login and role acceptance are completed. No wildcard redirect is permitted.
- The existing administrator subsequently completed custom-domain sign-out and
  Google sign-in again, reached the admin-only route, and read the account and
  invitation register on 2026-09-08. Researcher-specific workflow, suspension,
  and uninvited-account denial remain separate acceptance checks.
- The billing console showed the configured JPY 10,000 project alert, JPY 4,000
  Cloud SQL alert, and JPY 2,250 Cloud Run spend cap. Posted September values
  were JPY 0 after savings/credits for the project and SQL views, and JPY 32.95
  for Cloud Run. Billing can lag; no budget or resource limit was changed.
