# ANEMONE classification and research safety — v0.4.1/v0.4.2

> Superseded plan: the work recorded here shipped in `v0.4.1` and `v0.4.2`.
> Retain this file as implementation history. Current work is in
> [`RELEASE_0.4.3_PLAN.md`](RELEASE_0.4.3_PLAN.md).

Decision: on 2026-09-03 the user prioritized `v0.4.0` and explicitly deferred
classification workflow completion. Keep the pilot `sample_kind=unknown` and
`is_control=null`. Its proposed environmental classification is not approved.

Release outcome (2026-09-08): PR1–PR4 and the v0.4.2 exclusion presentation
were merged and deployed as `v0.4.2`.
The database is at schema head `20260905_0011`; the fixed Cloud Run application
identity is registered. No real review was created, approved, or applied.
Authenticated researcher acceptance remains a follow-up gate. Exclusion-reason
presentation is implemented in the v0.4.2 release.

## v0.4.0 boundary

- Preserve source metadata, detections, method labels, hashes and citations.
- Keep unknown samples excluded from environmental-only composition/diversity
  and environmental linking; retain explicit exclusion reasons in exports.
- Do not apply the draft, infer a reviewer or relabel the sample to pass a gate.
- Release the existing integration without claiming completed classification,
  contamination clearance, environmental biodiversity validation or validated
  CTD/SST overlap. Classification approval is not a release gate for this scope.
- Operational gates still apply: CI, backup/restore, compatible migrations,
  authorization, source/provenance integrity, bounded costs and deployment checks.

## Next-patch work

1. Review the implemented operator/CLI flow and identify the remaining gaps
   between its tested primitives and a complete researcher workflow. **Done in
   PR1/PR2 review.**
2. Provide a clear draft/review/approve-or-reject path with exact sample and
   source-row evidence, a real reviewer identity, timestamp and rationale.
   Review permissions and audit attribution must be explicit. **Implemented in
   PR2 and deployed in v0.4.1; authenticated acceptance remains pending.**
3. Preview the effect on inclusion/exclusion and derived results before applying
   a decision. Unknown must remain a valid unresolved outcome. **Implemented in
   PR3 and deployed in v0.4.1; authenticated acceptance remains pending.**
4. Validate and apply approved reviews through the controlled job workflow,
   regenerate retrieval/analysis/provenance, retain prior identities/citations,
   and test replay, failure recovery and explicit rollback. **Implemented in
   PR4 and deployed in v0.4.1; no real approved decision has been applied.**
5. Validate the retained pilot with a qualified researcher. Verify control
   context, scientific outputs and model-answer limitations independently.
6. Complete authenticated end-to-end tests, then document acceptance and ship
   the patch. Do not choose a final classification or approval in advance.

## v0.4.2 exclusion presentation — 2026-09-08

- Data sample lists and details report environmental-analysis eligibility and
  the exact deterministic exclusion reason.
- Analysis navigation exposes Eligibility and Exclusions directly. Empty result
  tables link to the recorded exclusions without running a model or changing
  the analysis.
- Human-readable reason labels retain the underlying stable reason code.
- Eligibility is computed by the API from canonical `sample_kind`, `is_control`,
  and active-assay state using the same policy as the analysis engine. The UI
  does not infer classification.

## PR1 research-safety implementation — 2026-09-05

Status: implemented, merged, and deployed in `v0.4.1`.

- `/chat` and the legacy orchestration entry point now stop before generation
  when no usable primary, linked, analysis, or reliability evidence remains.
- Responses and durable chat records distinguish `answered` from `abstained`,
  record a stable abstention reason, and state whether the model ran.
- Empty analysis cohorts, general no-match retrieval, and pending eDNA
  publication return direct deterministic messages. Missing an expected source
  family does not force abstention when other usable evidence is available;
  the existing citation audit remains responsible for coverage warnings.
- eDNA publication state is explicit in retrieval diagnostics, `/stats`,
  `/health`, Overview, and Chat. A pending generation no longer causes `/stats`
  to fail or removes the readable legacy corpus from local retrieval.
- Chat shows the applied scientific filters and outcome. Administrative
  feedback detail exposes the recorded outcome and abstention reason.
- Migration `20260905_0009` adds nullable outcome fields so historical records
  remain unchanged while new completed interactions are classified.

Verification: 651 backend tests passed with 9 service-gated skips; 16 frontend
tests, TypeScript checking, production build, Ruff, one Alembic head, and diff
checks passed. The initial sandboxed backend run could not bind its localhost
fixture server; the complete rerun with local fixture access passed.

## PR2 authenticated classification domain — 2026-09-05

Status: implemented, merged, migrated, and deployed in `v0.4.1`; production
researcher acceptance remains pending.

- Researchers can create and revise evidence-bound drafts and submit `approved`
  or `rejected` decisions. Admins cannot make scientific decisions; they can
  only record a later operational `applied` or `failed` outcome.
- Reviewer and operator identities, roles, and timestamps come from the active,
  database-backed authenticated user and the server clock. Request bodies reject
  editable identity and time fields.
- Reviews retain the source snapshot, canonical sample, provider sample, target
  classification (including `unknown`), rationale, compressed-file ID and
  SHA-256, TSV row locator, key/value evidence, supersession link, and a stable
  content digest.
- Every state change writes a separate append-only event with an actor snapshot,
  review snapshot, transition details, and event digest. PostgreSQL blocks event
  updates and deletes; database constraints enforce event roles and transitions.
- Optimistic versions, row locks, and a partial unique index prevent stale or
  competing current approvals. Evidence is rechecked against the active snapshot
  before scientific approval and before a successful application outcome.
- `applied` is currently an operational receipt with a required external job
  reference. This PR does not rewrite `edna_sample`, normalize data, republish
  retrieval, or regenerate analyses. Those actions remain controlled-application
  work; do not record `applied` before that job exists and succeeds.

The legacy JSON/operator attestation remains available only for the existing
normalization path. It is not an authenticated scientific decision and must not
be substituted for a PR2 review.

## PR3 classification effect preview — 2026-09-05

Status: implemented, merged, and deployed in `v0.4.1`; production researcher
acceptance remains pending.

- Researchers and admins can preview a draft, approved, or failed review through
  `POST /classification-reviews/{review_id}/preview`. Preview uses read permission
  and grants no decision or application authority.
- The request pins the expected review version, assignment methods, genus/species
  rank, minimum read count, and top-taxa limit. Duplicate or unbounded settings
  are rejected.
- The service holds the review row and, on PostgreSQL, uses a repeatable-read
  transaction. It loads a bounded active canonical sample plus same-run control
  context and rejects incomplete or unverified provenance.
- The existing deterministic eDNA analysis algorithm runs twice in memory:
  current canonical classification and the proposed review classification. The
  response contains inclusion state, exclusion reasons, assay/method read and
  diversity metrics, top composition, changed table counts, canonical input
  identity, and a stable preview digest.
- Unknown and control outcomes remain excluded. The preview does not infer a
  classification or weaken the environmental-only control policy.
- The Data eDNA sample view lists reviews and shows the current/proposed result
  tables. It performs no write when loading or calculating a preview.

PR3 does not change the canonical sample, publish analysis/retrieval artifacts,
create embeddings, or update a publication pointer. Controlled application and
rollback remain PR4 work. Full contract: [PR3 plan](ANEMONE_CLASSIFICATION_PR3_PLAN.md).

## PR4 controlled application and republication — 2026-09-06

Status: implemented, merged, migrated, and deployed in `v0.4.1`; it has not run
against a real approved decision.

- The existing manually launched Cloud Run processing job accepts an approved
  database review UUID and runs immutable review registration, exact-snapshot
  normalization, transactional import, retrieval materialization, affected
  analysis regeneration, sample-scoped embedding refresh, provenance
  publication, and final operational receipt in a fixed order.
- A durable application ledger and database-enforced append-only events retain
  review/snapshot identity, completed stages, artifact and generation IDs, safe
  failure codes, and fixed recovery instructions. Event history is verified
  against mutable run state on every resume.
- Operation IDs are idempotency keys. Completed runs return their receipt;
  failed or interrupted runs resume after the last completed stage. PostgreSQL
  advisory and uniqueness locks reject concurrent execution.
- Rollback is explicit and compensating: a new authenticated, approved review
  must supersede the applied review for the same sample. It follows the same
  publication pipeline and retains the previous application ID. `unknown`
  remains a valid correction.
- The Cloud Run actor is resolved from a pre-registered workload identity, not
  a CLI field. Production execution must report the Cloud Run job environment.
  No web-to-job bridge was added.

Full contract: [PR4 plan](ANEMONE_CLASSIFICATION_PR4_PLAN.md).

## Operational follow-up from the v0.4.0 rollout

- During the import-to-materialization interval, the ready-pointer guard
  correctly rejected incomplete eDNA publication, but `v0.4.0` returned HTTP
  500 from `/stats`. PR1 now reports `pending`, retains legacy metrics, and
  covers the interval with a regression test.
- For subsequent rollouts, finish publication before switching traffic or use
  an explicit maintenance/readiness gate to avoid exposing that interval.
- A live v0.4.0 smoke
  test used the environmental-only analysis filter with context injection
  disabled. The unknown pilot was correctly excluded, leaving zero evidence;
  the model nevertheless invented a negative-control sample and agreement
  counts. The audit marked all five citation occurrences invalid, but did not
  prevent the answer. Do not present that response as accepted research. PR1
  now blocks generation for that no-evidence state and displays the applied
  filters. Authenticated live acceptance remains required before scientific
  workflow acceptance.

Inputs: [operator implementation](ANEMONE_CLASSIFICATION_REVIEW.md),
[unapproved pilot proposal](ANEMONE_PILOT_CLASSIFICATION_PROPOSAL.md), and
[retained canary evidence](ANEMONE_PILOT_2026-09-03.md).
