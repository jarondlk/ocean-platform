# ANEMONE classification PR4 — controlled application and republication

Status: implemented locally on `codex/mvp-pr4-controlled-application`.
PR1–PR3 remain uncommitted prerequisites in the same worktree.

## Objective

Apply one authenticated, approved classification review through the existing
manually launched Cloud Run processing job. The job must be resumable,
evidence-bound, idempotent, and auditable. It must not add an API or browser
action that launches Cloud Run.

## Execution contract

- Add an explicit `apply-classification` processing stage accepting a database
  review UUID and operator-chosen operation ID. Execution remains opt-in through
  `--execute`; the default is an offline plan.
- Resolve the operational actor from a pre-registered `workload_identity`
  application user matching the job's configured service-account subject. Do
  not accept an editable reviewer, operator name, timestamp, or application
  outcome.
- Revalidate the review state, version, content digest, append-only history,
  active canonical sample, source snapshot, compressed-file hashes, TSV rows,
  and values before every externally visible stage.
- Execute these stages in order: register the database review as an immutable
  artifact; restore and normalize the exact raw snapshot; transactionally
  import; materialize retrieval; regenerate registered analyses affected by the
  sample; refresh only affected missing/stale embeddings; publish provenance;
  then record the review as applied.
- Persist an application run plus append-only stage-attempt records. Store safe
  stage status, immutable artifact/generation IDs, timestamps, error codes, and
  fixed recovery instructions. Never persist arbitrary exception text.
- Replaying a completed operation ID returns its existing result. Replaying an
  interrupted or failed operation resumes after completed stages; immutable
  artifacts and generation identities must agree.

## Rollback and correction

Rollback is a new approved scientific decision, not an unreviewed restoration.
`--rollback-of <application-id>` requires the new review to explicitly
supersede the applied review, refer to the same sample, and pass all normal
evidence checks. `unknown` remains a valid rollback/correction outcome. The
same normalization, import, retrieval, analysis, embedding, and provenance
pipeline is used, and the new application run retains the target application
ID.

Operational failures may be resumed with the same operation ID. A stale,
rejected, applied-by-another-run, or superseded review fails closed. If a stage
may have committed before its completion receipt was written, replay invokes
the stage again and relies on its existing immutable/idempotent contract.

## Acceptance tests

- Approved/failed retry states, workload role, review integrity, stale approval,
  supersession, and competing-run checks.
- Exact stage order, durable status/results, safe failures, restart after a
  started attempt, and completed-operation replay without rerunning stages.
- Database review artifact conversion retains authenticated researcher identity,
  decision time, rationale, evidence hashes/rows/values, and `unknown`.
- Explicit rollback requires a matching applied target and approved superseding
  review.
- Existing normalization/import/materialization/analysis/embedding/provenance
  tests remain green; PostgreSQL verifies append-only stage records and
  concurrency constraints.
- Cloud Run template remains single-task, bounded, manually executable, and has
  no web-to-job execution route.

## Out of scope

No automatic scheduling, browser/API job launch, inferred classification,
provider download, production migration, live model call, deployment, or
scientific acceptance is authorized by this PR.

## Implementation record

- Migration `20260905_0011` adds durable application runs and database-enforced
  append-only stage receipts. The run-start receipt binds the review, version,
  content digest, snapshot, sample, operation, rollback target, workload actor,
  and start time; later reads reconstruct and compare completed stages, results,
  and artifact IDs from those receipts.
- `scripts/run_anemone_job.py --stage apply-classification` runs the ordered
  workflow only with both `--execute` and a database review UUID. It uses a
  PostgreSQL advisory lock plus the per-review running-run constraint. No API or
  browser route starts the job.
- `scripts/register_classification_workload.py` is the dry-run-first one-time
  registration path for the fixed service-account subject. It creates an
  internal operational admin principal and an audit event; it cannot alter or
  adopt a conflicting user.
- A failed or interrupted operation resumes with the same operation ID and does
  not repeat stages that have matching durable receipts. A completed replay is
  read-only. A rollback is a new approved superseding review and therefore
  retains both the prior decision and the correction.

Local verification passed 688 backend tests with 12 expected PostgreSQL-gated
skips and 78.31% coverage; all 12 disposable PostgreSQL integration tests; 18
frontend tests, TypeScript, and the 24-route production build; Ruff, `pip check`,
the production dependency audit, one Alembic head, migration downgrade/
re-upgrade, and `git diff --check`. Full details are in
[`TESTING.md`](TESTING.md).
