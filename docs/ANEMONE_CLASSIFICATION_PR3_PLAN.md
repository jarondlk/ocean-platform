# ANEMONE classification PR3 — effect preview

Status: implemented and locally verified on
`codex/mvp-pr3-classification-preview`.
PR1 and PR2 remain uncommitted prerequisites in the same worktree.

## Objective

Show the scientific effect of a classification review before operational
application. The preview must not alter a review, canonical eDNA row, retrieval
document, analysis bundle, embedding, or publication pointer.

## Contract

- Add `POST /classification-reviews/{review_id}/preview` for authenticated
  researchers and admins with `classification:read`.
- Require the caller's expected review version. Reject stale versions, stale
  source snapshots, changed evidence, tampered review history, and terminal
  rejected, superseded, or applied reviews.
- Accept only explicit assignment methods, rank, minimum read count, and a
  bounded top-taxa limit. Use the existing `environmental_only` analysis policy.
- Load the active reviewed sample and same-run non-environmental controls under
  fixed resource caps. Do not retrieve remote files or environmental data.
- Run the existing deterministic eDNA analysis algorithm twice in memory:
  current canonical classification and proposed review classification.
- Return baseline/proposed inclusion, exclusion reasons, assay/method diversity
  and read summaries, top composition, analysis table counts, count deltas,
  source/input identities, and a stable preview SHA-256.
- Keep `unknown` valid. An unknown or control proposal remains excluded and must
  not be rewritten to obtain a non-empty result.
- Present the result in the eDNA sample view with direct labels and tables.

## Scientific boundary

The preview describes assigned sequence-read composition. It does not establish
organism abundance, taxonomic accuracy, contamination clearance, environmental
eligibility, or CTD/SST association. No environment observations or linkage
profiles are used. Only controlled application in a later PR may change the
canonical corpus and republish derived evidence.

## Acceptance tests

- Role and route policy: researcher/admin preview; viewer denied; preview grants
  no scientific-decision or operational-application permission.
- State/version/integrity: draft and approved previews succeed; stale, rejected,
  superseded, applied, and tampered reviews fail closed.
- Scientific scenarios: environmental proposal becomes eligible and produces
  the same metrics as the existing analysis engine; control and unknown remain
  excluded; minimum-read, rank, and method choices are explicit.
- Immutability: review version/events, canonical classification, publication
  records, and filesystem artifacts are unchanged.
- Resource/concurrency: bounded reads, scoped rate limit, and repeatable digest
  for the same review version and canonical inputs.
- Frontend presentation, TypeScript, production build, full backend suite,
  Ruff, migration head, and PostgreSQL PR2 integration remain green.

## Verification — 2026-09-05

- Focused classification, authorization, and rate-limit boundary: 74 passed.
- Full backend: 673 passed, 11 expected PostgreSQL-gated skips, and 77.98%
  aggregate CI-boundary coverage (70% required).
- Fresh PostgreSQL 16/pgvector CI-order integration: 11 passed, including the
  repeatable-read preview and a rolled-back fixture that proves no canonical or
  review state escapes the test transaction.
- Frontend: 18 tests, TypeScript checking, and the 24-route production build
  passed.
- Ruff, dependency consistency, `git diff --check`, and the single Alembic head
  `20260905_0010` passed.

This is local implementation evidence. Production migration, OIDC acceptance,
controlled application, deployment, and live scientific review were not run.
