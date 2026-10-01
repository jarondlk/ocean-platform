# v0.6.0 release and deployment record

Started 2026-10-01 JST. The user authorized closing local previews, updating
documentation, publishing a new GitHub release and deploying through GCP.

**Status: source preparation in progress; GCP deployment pending.** No v0.6.0
production rollout is claimed by this initial record. The last verified
production deployment remains v0.5.0 at `ocean-platform-v050-prod0930`.

## Scope and source

Development branch: `gcp-dev`; integration branch: `main`.
The release includes independent chat source settings, available-data selection
controls, validated per-account browser persistence, scope enforcement,
provider-effective controls and bounded issue #70 fixes. See
[release notes](RELEASE_NOTES_0.6.0.md), [implementation](RELEASE_0.6.0_IMPLEMENTATION.md)
and the [adopted plan](RELEASE_0.6.0_PLAN.md).

An existing deployment pitfall is also repaired: Alembic's interpolating parser
now preserves percent-encoded Cloud SQL socket/password URLs. The standard
`python -m alembic upgrade head` no longer needs the v0.5.0 operator's raw-parser
workaround. The regression checks URL round-trip and absence from SQL output.

## Verified preparation

- Local API and frontend preview processes were stopped. The browser preview
  panel close operation encountered a browser-control timeout; closure remains
  to be confirmed separately.
- Final backend regression: 914 passed, 35 PostgreSQL-gated skips, 79.25%
  coverage (70% gate). Frontend: 48 tests, typecheck and production build
  passed. The source-contract export, Python lint, dependency consistency and
  single Alembic head `20261001_0014` passed.
- Initial candidate PostgreSQL integration: 34 passed in CI order. Selection
  refinement: the additional PostgreSQL test passed in a fresh disposable
  database, including local/SQL agreement, full canonical taxa, inactive rows,
  false controls, bound search, cascading choices and pinned membership.
- Local browser selection/cascade/search checks passed. The local preview has
  no ANEMONE corpus; this does not establish live production availability.
- GitHub credentials were verified for repository owner `jarondlk`. GCP
  authentication was renewed through the user-requested browser login.
- Live configuration confirms v0.5.0 still receives 100% traffic. Serving limits
  are unchanged: API 2 CPU/2 GiB, frontend 1 CPU/512 MiB, concurrency 20,
  minimum zero/maximum one instance. Cloud SQL is RUNNABLE on PostgreSQL 16,
  `db-custom-1-4096`, 10 GiB, with backups and PITR enabled. No v0.6.0 image or
  migration has been applied at this preparation step.

## Security and production precheck

PR [#78](https://github.com/jarondlk/ocean-platform/pull/78) initially exposed
CodeQL alert 27 (`py/polynomial-redos`) in the eDNA unknown-status answer
selection. The regular expression was replaced by a linear per-line scan.
Regression cases cover case-insensitive matching, line boundaries, Japanese
queries and 100,000 repeated `unknown` tokens, with and without a following
control label. The updated remote security result remains a release gate.

The user explicitly approved the bounded temporary `ocean-v060-readcheck` job
after automatic review requested specific approval for its identity/database
access. Execution `ocean-v060-readcheck-qm5mn` completed successfully, and the
job was deleted afterward. It made no database mutations. The live schema is
`20260925_0013`; active documents and matching embeddings are CTD 162,
metagenome 82, remote sensing 79 and eDNA 6,996. Canonical records are 3,498
source occurrences/assays, 349,638 assignment rows and 13,932 internal standards.
The ready eDNA publication matches the database generation/digest, and the
provenance snapshot remains `v050-production-provenance`. The database is about
1.21 GB. Production traffic remains on v0.5.0.

## Deployment order

1. Commit and review the exact candidate; pass required remote CI/security
   checks, merge to `main` and publish the immutable v0.6.0 source release.
2. Verify current service/job configuration, database schema, publication
   generations, budget/resource limits and recent errors after authentication.
3. Build immutable API/frontend images from an archive of the release commit.
4. Take a fresh production backup and verify an isolated restore before applying
   migration `20261001_0014` with the candidate image.
5. Prepare a zero-traffic candidate using existing production configuration and
   resource limits. Sharing production storage does not isolate test writes.
6. Verify active source choices, scoped retrieval/answers/history, known issue
   #70 cases, citations/downloads/provenance and authenticated UI before routing
   production traffic. Record measured latency and remaining limitations.
7. Switch traffic only after the applicable gates pass, verify the live revision
   and update this record, release status and current operating documentation.

No ingestion/reimport, embedding refresh, publication replacement, new IAM grant,
schedule or capacity increase is part of this settings release.

## Recovery

Record the previous compatible revision and immutable image digests before
mutation. The history constraint expansion is compatible with old application
writes and can remain during an application rollback. Never remove retained
new-reason history to force downgrade, overwrite later user activity with the
pre-release backup, or route an incompatible v0.4.x reader to the v0.5.0 corpus.
