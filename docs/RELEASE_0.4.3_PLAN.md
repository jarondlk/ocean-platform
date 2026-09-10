# OCEAN Platform v0.4.3 plan

> Status: PR1–PR4 were reviewed and merged through
> [PR #58](https://github.com/jarondlk/ocean-platform/pull/58), then built,
> migrated, canary-tested, and deployed on 2026-09-10. The completed gate and
> remaining acceptance items are recorded in
> [`RELEASE_0.4.3_OPERATIONS.md`](RELEASE_0.4.3_OPERATIONS.md). Retain this file
> as the implementation and release-gate design record, not as a current work
> queue.

Outcome: the four scopes were frozen in candidate `545366d`, merged as
`26094fc2c1f1f9cad094c484aff4522ba738240f`, and deployed in immutable Cloud
Build `a8cac0c6-9ac2-49b4-bdc8-82c82089a0d2`.

## Objective

Harden classification integrity, controlled application, hybrid retrieval, and
scientific eligibility before the next release. The bounded ANEMONE pilot
remains `sample_kind=unknown` and `is_control=null`; this plan does not authorize
or imply a scientific reclassification.

Development starts on `gcp-dev`. Keep the four changes below independently
reviewable as four logical sections in one combined `gcp-dev` → `main` release
PR. This preserves the repository policy of retaining only `main` and
`gcp-dev` while keeping the dependency order auditable. Release and deploy only
after the combined gate passes.

## PR1 — Classification integrity and fail-closed lineage

Status: implemented, reviewed, merged, and deployed in v0.4.3.

- Define one canonical tri-state mapping:
  `environmental -> false`, every recognized control kind `-> true`, and
  `unknown -> null`.
- Validate reviewed values without coercing `null` to `false`; an applied or
  rollback decision to `unknown` must remain valid.
- Parse `classification_review_json` through one strict shared validator.
- Reject malformed JSON, wrong shapes, missing required fields, invalid
  classification values, and content-digest mismatches. Never treat corrupt
  review lineage as though no review exists.
- Preserve `unknown` as a valid final scientific outcome and require explicit
  supersession for later corrections.
- Add regressions for applied unknown, rollback to unknown, supersession,
  malformed lineage variants, and digest tampering.

Exit gate: normalization, controlled application, rollback, and existing
unknown-sample behavior agree on the same tri-state contract.

Verification evidence:

- full backend: 711 passed, 12 expected service-gated skips;
- fresh PostgreSQL 16/pgvector integration through migration head
  `20260905_0011`: 12 passed;
- Ruff and `git diff --check`: passed;
- regressions cover reviewed/applied unknown, rollback to unknown, explicit
  supersession, malformed and incomplete lineage, invalid sample kinds,
  inconsistent tri-state values, and original/rehashed digest tampering.

## PR2 — Controlled operational outcomes

Status: implemented, reviewed, merged, and deployed in v0.4.3.

- Remove or disable the public mutation path that can record classification
  application failure outside the application ledger.
- Permit `applied` and `failed` review events only from the controlled
  application service after it has resolved a real `ClassificationApplication`.
- Bind each operational event to the application, review, operation ID,
  workload actor, stage result, and expected review version.
- Replace caller-provided success/failure flags with an internal verified
  transition function.
- Keep scientific approval and operational application as separate events.
- Preserve the manual operator-run Cloud Run boundary; do not add a browser or
  API bridge that launches the job.
- Add authorization, fabricated-event, identity mismatch, stale version,
  replay, competing-run, and safe-failure tests.

Exit gate: neither a researcher nor an administrator can fabricate an
operational receipt through a public API call, and every terminal operational
event has a matching ledger record.

Verification evidence:

- the public application-outcome route and request schema are removed, and the
  deny-by-default authorization map returns no permission for the old path;
- the internal transition resolves and locks the application and review,
  verifies actor identity, stage/order, immutable history, expected review
  version, and the terminal event before appending the review event;
- operational review events contain a strict, digested ledger binding that is
  revalidated whenever review history is read;
- focused classification/application/auth tests: 88 passed; Ruff passed;
- regressions cover public fabrication attempts, exact receipt binding,
  identity mismatch, stale/superseded approval, competing runs, terminal replay,
  resumed failure-to-success, forged bindings, and failure before a valid stage;
- combined PR1/PR2 backend gate: 713 passed with 12 expected service-gated
  skips; the complete six-module integration selection passed 12 tests against
  a fresh database migrated through head `20260905_0011`; repository-wide Ruff
  and diff checks passed. The disposable database was removed.

## PR3 — Hybrid retrieval isolation and contract consistency

Status: implemented, reviewed, merged, and deployed in v0.4.3.

- Run vector and full-text retrieval in independent transaction scopes so one
  backend failure cannot poison the fallback query.
- Reject a request when both retrieval weights are zero. Normalize accepted
  weights once and use the same values in every backend.
- Make local retrieval honor the requested vector weight, text weight, and
  `rrf_k` instead of fixed constants.
- Add `doc_id` as the final deterministic tie-breaker.
- Resolve backend availability once per request and reuse the configured
  database engine rather than creating redundant probes or engines.
- Add tests for vector failure with FTS recovery, FTS failure with vector
  recovery, total backend failure, zero weights, non-default weights and
  `rrf_k`, local/PostgreSQL contract parity, and deterministic ordering.

Exit gate: a failed retrieval branch does not invalidate a healthy branch, and
the API request contract has identical meaning in local and PostgreSQL modes.

Verification evidence:

- PostgreSQL vector and FTS branches use separate sessions and transactions;
- both API request models and direct retriever calls reject an all-zero pair,
  and accepted weights plus `rrf_k` reach both implementations;
- local and PostgreSQL RRF use the same absent-rank treatment and final
  `doc_id` tie-breaker;
- a total enabled-backend outage raises a controlled retrieval error and the
  HTTP retrieval surface returns `503 retrieval_backends_failed`;
- unit regressions cover both one-branch failures, total failure, normalized
  non-default weights, non-default `rrf_k`, parity, deterministic order, and
  one availability probe per request;
- fresh PostgreSQL regressions induce a real vector dimension error and a real
  invalid FTS parameter in separate runs; the healthy branch recovers in both
  directions.

## PR4 — Shared scientific eligibility

Status: implemented, reviewed, merged, and deployed in v0.4.3.

- Introduce one pure eligibility evaluator shared by Data APIs and analysis
  generation.
- Evaluate sample/control classification, assay presence, protocol metadata,
  and assignment-method availability together.
- Return method-level eligibility and reason codes while retaining a compatible
  top-level sample summary.
- Make Data and analysis surfaces present the same inclusion/exclusion result
  for the same sample, assay, method, and snapshot.
- Add policy-matrix tests for environmental, control, and unknown samples;
  missing assay/protocol/method inputs; mixed method availability; and exact
  API-to-analysis parity.

Exit gate: no sample is shown as analysis-eligible unless the selected analysis
can consume it, and every exclusion is explained by the same stable reason
contract.

Verification evidence:

- one pure evaluator now owns classification, active-assay, required protocol,
  and method-availability decisions;
- sample list/detail, assay detail, detection list/detail, and analysis
  membership expose the same method-level status and ordered reason codes;
- the compatible sample summary remains `included` when at least one method is
  consumable, while unavailable methods remain explicitly excluded;
- Data presents method-level decisions directly instead of deriving them in
  the browser;
- policy-matrix regressions cover environmental, control, unknown, missing
  assay, incomplete protocol, missing and mixed methods, accumulated reasons,
  and exact evaluator-to-analysis membership parity.

## Combined local implementation evidence — 2026-09-09

- backend: 732 passed, 13 expected service-gated skips, 78.16% aggregate
  coverage;
- fresh PostgreSQL 16/pgvector database migrated through head
  `20260905_0011`: 13 integration tests passed, including real retrieval
  transaction-abort recovery in both directions;
- frontend: 19 tests, TypeScript checking, and the 24-route production build
  passed;
- repository-wide Ruff, dependency consistency, zero production frontend audit
  vulnerabilities, and diff checks passed;
- the disposable PostgreSQL container was removed after verification.

This evidence validated candidate commit `545366d`. PR review, CI/CodeQL,
production build, backup/restore, deployment, and immediate monitoring later
passed as recorded in `RELEASE_0.4.3_OPERATIONS.md`. Researcher-specific
authenticated acceptance remains a follow-up.

## Combined release gate (completed 2026-09-10)

Before tagging `v0.4.3`:

1. Update API/frontend version metadata to `0.4.3`, prepare release notes, and
   freeze the four logical sections in one combined release PR.
2. Review and merge the release PR in dependency order, then confirm exactly
   one Alembic head (`20260905_0011`). This release introduces no migration;
   the deployment gate must verify and apply the existing head only.
3. Run focused classification, application, retrieval, and eligibility suites.
4. Run the full backend suite with coverage, PostgreSQL/pgvector integration,
   Ruff, dependency checks, production-only `npm audit`, frontend tests,
   TypeScript checking, the production frontend build, and repository CI/CodeQL
   checks.
5. Rehearse idempotent controlled-application replay and explicit rollback
   without changing the real pilot classification.
6. Verify deterministic no-evidence behavior, citation integrity, provenance
   publication, and the deferred authenticated researcher acceptance matrix.
7. Create a pre-deployment backup and isolated restore, verify the current head,
   deploy an immutable candidate revision, and run authenticated smoke checks
   before moving traffic.
8. Publish release notes and the production operations record, then monitor
   errors, latency, Cloud SQL connections, backups, and billing under the
   existing limits.

## Explicit non-goals

- No inferred ANEMONE sample classification.
- No automated ANEMONE download or scheduled ingestion.
- No web-to-Cloud-Run execution bridge.
- No claim of taxonomic accuracy, contamination clearance, organism abundance,
  or environmental association beyond the reviewed evidence.
- No deletion of historical plans, releases, audit records, or provenance.
