# v0.4.3 deployment record

Verified 2026-09-10 JST. This records the immutable release candidate, database
gate, Cloud Run rollout, and immediate monitoring. It did not create, approve,
apply, roll back, or supersede a scientific classification decision. The
bounded ANEMONE pilot remains `sample_kind=unknown` and `is_control=null`.

## Source and review

- GitHub PR [#58](https://github.com/jarondlk/ocean-platform/pull/58) was
  reviewed and merged into `main` as
  `26094fc2c1f1f9cad094c484aff4522ba738240f` after all 15 required checks
  passed.
- Post-merge CI run
  [34438505149](https://github.com/jarondlk/ocean-platform/actions/runs/34438505149)
  and CodeQL run
  [34438504785](https://github.com/jarondlk/ocean-platform/actions/runs/34438504785)
  completed successfully.
- The merged source has one Alembic head, `20260905_0011`. v0.4.3 adds no
  migration revision.

## Verification

- The merged source passed 732 backend tests with 13 expected service-gated
  skips and 78.16% aggregate coverage.
- All 13 PostgreSQL 16/pgvector integration tests passed against a fresh
  migrated database, including independent retrieval-branch failure recovery,
  application replay/rollback, and eligibility parity.
- Ruff, `pip check`, the production-only npm audit, 19 frontend tests,
  TypeScript checking, the 24-route production build, and the clean-diff gate
  passed.
- Classification application replay, competing-run rejection, stale approval,
  explicit rollback, rollback to `unknown`, corrupt-lineage rejection,
  deterministic no-evidence behavior, citation integrity, and provenance
  publication are covered by the merged test suites. No production review was
  used for this rehearsal.

## Backup and database gate

- Pre-deployment dry-run execution `ocean-pipeline-4w6d5` planned only the
  database-backup stage.
- Backup/restore execution `ocean-pipeline-qwtpj` completed successfully and
  created
  `gs://data-infra-infobio-ocean-data/backups/20260910T045744Z-v0.4.3-pre-deploy-ocean_platform.dump`.
- The 2,863,495-byte archive has SHA-256
  `e8179e2c66246e8e8eeaab9d09483effef9f17d24feb4f15f73e6c1231599713`.
  Its manifest records 27 tables and 256 PostgreSQL TOC entries. An isolated
  restore into `ocean_restore_verify_0745ed82429a` had exact row-count parity;
  the disposable database was removed.
- Migration execution `ocean-migrate-cklpd` completed successfully. Runtime
  verification reported 27 tables, no missing tables or columns, and the
  `vector` extension available.
- Cloud SQL `ocean-postgres` was `RUNNABLE`, with PostgreSQL 16, deletion
  protection, automatic backups, seven retained backups, and seven-day PITR.
  The latest seven scheduled backups were successful.

## Immutable build and jobs

Cloud Build `a8cac0c6-9ac2-49b4-bdc8-82c82089a0d2` completed successfully from
05:01:04 to 05:10:05 UTC. Its remote backend and frontend verification steps
passed before it published:

- API digest
  `sha256:cc32e45e81b91ef2d6e67fdfe3878453adca3e1a7f725a6d4707432f08c53537`;
- frontend digest
  `sha256:b846855db52c65d9c0899d1f673190257736d6b97eaa05a73147da6d05762b7f`.

The `ocean-migrate`, `ocean-pipeline`, `ocean-embedding`,
`ocean-evaluation`, and `ocean-anemone-process` jobs use the v0.4.3 API image
and record `SOURCE_COMMIT=26094fc2c1f1f9cad094c484aff4522ba738240f`.
Canary results were:

| Job | Execution | Result |
| --- | --- | --- |
| Pipeline | `ocean-pipeline-z5nc8` | Nine-stage dry-run plan completed; no command was executed. |
| Embedding | `ocean-embedding-stw2r` | Dry-run over the bounded 16-document limit completed. |
| ANEMONE application | `ocean-anemone-process-ns8ff` | Plan-only application boundary completed with no review ID and no mutation. |
| Evaluation | `ocean-evaluation-qgvjn` | One `ctd_01` Full-mode evaluation passed against pgvector and Vertex AI. |

The evaluation used 325 embedded documents and reported 100% retrieval
precision, source coverage, citation accuracy, and context utilization, with
6.1-second average generation latency. Its artifacts are under
`/mnt/ocean-data/evaluation/eval_2026-09-10T05-17_gemini-3.6-flash*`.

## Service rollout

- Candidate revision `ocean-platform-v043-26094fc` was created with zero
  traffic and the tag `v043-candidate`.
- Before cutover, `/login`, `/api/auth/session`, and
  `/manifest.webmanifest` returned HTTP 200; `/` redirected to the canonical
  login; protected API routes returned HTTP 401; and no ERROR-level revision
  logs were present.
- After those checks, 100% traffic moved from `ocean-platform-00013-djj` to
  `ocean-platform-v043-26094fc`. The prior revision remains an immediate
  reviewed rollback target.
- The canonical URL is
  [`https://oceaninfobio.com`](https://oceaninfobio.com). The frontend retains
  `AUTH_URL=https://oceaninfobio.com`; the API retains
  `CORS_ORIGINS=https://oceaninfobio.com`.

## Immediate monitoring

- Initial production requests returned the expected 200, 307, and fail-closed
  401 statuses. Successful request latency in the Cloud Run logs was
  approximately 8–26 ms after startup.
- No HTTP 5xx or ERROR-level new-revision entries were observed in the initial
  post-cutover smoke window.
- No Cloud SQL ERROR-level entries were observed after rollout. Successful
  migration and evaluation executions independently confirmed database and
  pgvector connectivity.
- GCSFuse returned transient HTTP 429 retries during the pipeline dry-run and
  the pre-deployment backup. Both executions recovered automatically and
  completed successfully; monitor recurrence before expanding batch work.
- Billing remained enabled on account `019B3B-2B8BBA-42E4B2`, and no billing
  controls were changed. This CLI identity cannot list billing budgets, while
  the Billing console requires the account owner's passkey. The user-confirmed
  JPY 20,000 monthly ceiling therefore remains the governing limit, with a
  current-spend and budget-alert confirmation still required from the Billing
  console.

A broader same-day sweep then covered 115 requests: 56 HTTP 200, 24 HTTP 302,
29 HTTP 307, two expected anonymous HTTP 401 responses, three HTTP 404
responses, and one HTTP 502. Mixed-route latency was 17.18 ms at p50, 10.70 s
at p95, and 17.43 s maximum; this includes authenticated generation and
redirect/cold-start traffic rather than only application handlers. The single
502 was an authenticated `POST /api/backend/chat`: Vertex AI returned finish
reason `MAX_TOKENS`, the API mapped it to the controlled
`llm_request_failed` response, and the interaction was safely marked failed.
The successful evaluation canary and absence of Cloud SQL errors rule out a
general model or database outage. This does not require release rollback, but
output-budget/partial-answer handling should be reviewed before treating long
answers as fully reliable.

## Remaining acceptance

The deployment gate is complete. The following do not invalidate the rollout,
but must not be represented as completed:

- researcher-specific authenticated classification review and read-only
  preview acceptance;
- suspension and uninvited-account denial using corresponding test identities;
- owner confirmation of current Billing-console spend and active alert
  thresholds; and
- a longer 24-hour/seven-day production observation window.

The manual operator-run Cloud Run boundary remains in force. There is no web or
API bridge that starts acquisition, classification application, migration,
pipeline, embedding, or evaluation jobs.
