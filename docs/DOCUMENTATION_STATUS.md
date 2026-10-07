# Documentation status

Last reviewed: 2026-10-06 (v0.7.2 published/deployed; exact-image acceptance and cleanup passed).

This register separates current operating guidance from completed plans and
point-in-time evidence. Here, **superseded** means obsolete as a current work
queue or execution authority. It does not mean the file is inaccurate for its
recorded date or safe to delete. Historical research, release, migration, and
audit records should remain immutable unless an explicit archival policy is
approved.

## Current operating authority

- [`RELEASE_0.7.2_OPERATIONS.md`](RELEASE_0.7.2_OPERATIONS.md) and
  [`RELEASE_NOTES_0.7.2.md`](RELEASE_NOTES_0.7.2.md) — source security/readiness
  patch; exact-image acceptance, GCP rollout, preservation and cleanup passed.
  Production is v0.7.2; preserve immutable tags and prior rollback records.
- [`V0.7.2_CONTAINER_QA_2026-10-06.md`](V0.7.2_CONTAINER_QA_2026-10-06.md) —
  fresh exact-image bindings, standalone dependency and full OS scan evidence.

- [`RELEASE_0.7.1_OPERATIONS.md`](RELEASE_0.7.1_OPERATIONS.md) — prior published
  release, verified isolated role acceptance and compatible application rollback.
- [`PRE_DEPLOYMENT_AUDIT_2026-10-06.md`](PRE_DEPLOYMENT_AUDIT_2026-10-06.md) —
  fresh repository/docs/script/dependency checks and next deployment gates.
- [`scripts/README.md`](../scripts/README.md) — active, operator-only and legacy
  entrypoints, side effects and supported execution paths.
- [`HISTORICAL_SST_ISSUE_103_PLAN.md`](HISTORICAL_SST_ISSUE_103_PLAN.md) and
  [`HISTORICAL_SST_ISSUE_103_IMPLEMENTATION.md`](HISTORICAL_SST_ISSUE_103_IMPLEMENTATION.md)
  — all-location/year acquisition scope, fresh census, bounded tooling/collection
  contracts and remaining product/scientific decisions; separate from deployed v0.7.2.
- [`HISTORICAL_SST_PRODUCT_COMPARISON_2026-10-06.md`](HISTORICAL_SST_PRODUCT_COMPARISON_2026-10-06.md)
  — authenticated four-file Himawari access, six MUR/twelve Himawari footprint
  diagnostics, native metadata/time issues and preliminary primary-product recommendation.
- [`HISTORICAL_SST_ACQUISITION_PILOT_2026-10-06.md`](HISTORICAL_SST_ACQUISITION_PILOT_2026-10-06.md)
  — 72-file storage/resume proof, protected NASA originals with explicit NRT
  distinction, cloud-worker acceptance and full-run resource/reconciliation limits.
- [`HISTORICAL_SST_HYBRID_2026-10-07.md`](HISTORICAL_SST_HYBRID_2026-10-07.md)
  — current user-selected acquisition strategy, estimated 20.9 GB/48,562 requests,
  coarse/native role separation, superseded-worker preservation and provider recovery gates.
- [`RELEASE_0.7.0_OPERATIONS.md`](RELEASE_0.7.0_OPERATIONS.md) — prior software
  rollout and compatible rollback record; its live-role deferral is historical.
- [`RELEASE_0.6.1_OPERATIONS.md`](RELEASE_0.6.1_OPERATIONS.md) — prior published
  release/rollback record, with its historical live-role and Japanese QA deferrals.
- [`RELEASE_0.6.0_OPERATIONS.md`](RELEASE_0.6.0_OPERATIONS.md) — retained prior
  release/deployment record, security amendment and historical QA deferrals.
- [`RELEASE_0.5.0_OPERATIONS.md`](RELEASE_0.5.0_OPERATIONS.md) — historical
  catalogue rollout and retained compatible application rollback baseline.
- [`ROADMAP.md`](ROADMAP.md) — longer-term engineering priorities.
- [`handoff.md`](../handoff.md) — current repository and production handoff.

## v0.7.1 completed and retained role acceptance

v0.7.1 is published and deployed. Normal Google role/workflow acceptance passed
using approved isolated candidate role changes, and temporary resources were
removed. #101/#105 are closed. Live mobile QA remains explicitly deferred (#107),
with transient sign-out tracked in #108. The six real demonstrations remain
blocked on scientific evidence/product decisions (#89/#102/#103).

- [`RELEASE_0.7.1_PLAN.md`](RELEASE_0.7.1_PLAN.md) — completed patch design and
  acceptance sequence; retained historical plan, not the next work queue.
- [`RELEASE_0.7.1_IMPLEMENTATION.md`](RELEASE_0.7.1_IMPLEMENTATION.md) and
  [`RELEASE_NOTES_0.7.1.md`](RELEASE_NOTES_0.7.1.md) — shipped implementation.
- [`V0.7.1_LIVE_QA.md`](V0.7.1_LIVE_QA.md) and
  [`V0.7.1_CONTAINER_QA_2026-10-05.md`](V0.7.1_CONTAINER_QA_2026-10-05.md) —
  dated candidate/live acceptance and exact image/security evidence.

Source-map-js 1.2.2 is merged in #111 and independently verified in the deployed
v0.7.2 standalone frontend. #110 is resolved. Fresh cloud inventory, image/runtime
acceptance, backup/restore, normal admin/history and all 16 source-combination
checks passed; cleanup is complete. The v0.7.1 tag and rollback remain immutable.
OS findings are unchanged and tracked separately in #104. Scientific/mobile
and transient sign-out work remains open as described in v0.7.2 operations.

## v0.7.0 historical rollout and deferred research work

On 2026-10-05 JST the user authorized the v0.7.0 software release/deployment and
explicitly deferred the six original real-data demonstrations and, separately,
live viewer/researcher sign-in QA. Software publication/deployment and cleanup
are complete; issue #89 stays open. v0.7.1 supersedes the live-role deferral and
production revision; real-data demos remain deferred. [Release notes](RELEASE_NOTES_0.7.0.md) and
[operations](RELEASE_0.7.0_OPERATIONS.md) record the scope and execution state.

- [`RELEASE_0.7.0_PLAN.md`](RELEASE_0.7.0_PLAN.md) — accepted
  implementation/acceptance sequence for issue #89's detection-frequency and SST
  demo. Planning does not approve scientific data decisions or claim a release.
- [`RELEASE_0.7.0_IMPLEMENTATION.md`](RELEASE_0.7.0_IMPLEMENTATION.md) — implemented
  software scope, verification, operational procedure and deferred scientific gates.
- [`V0.7.0_CONTAINER_QA_2026-10-05.md`](V0.7.0_CONTAINER_QA_2026-10-05.md) —
  isolated image/runtime verification, exact build bindings and residual advisory review.
- [`V0.7.0_SCIENTIFIC_REVIEW.md`](V0.7.0_SCIENTIFIC_REVIEW.md) — precise provider/
  researcher decisions needed before publishing a real research cohort.
- [`V0.7.0_DISCOVERY_2026-10-04.md`](V0.7.0_DISCOVERY_2026-10-04.md) — dated
  issue/reference/code investigation and local archive/SST coverage probes;
  not a fresh production census or approved scientific cohort.

## Completed patch and retained QA records

- [`RELEASE_0.6.1_PLAN.md`](RELEASE_0.6.1_PLAN.md) — user-requested v0.6.1
  routing fix, remaining settings/access/history/scientific QA and patch release
  sequence. Implementation, exact-source tag publication and verified deployment are complete; live viewer/researcher and Japanese acceptance are explicitly user-deferred.
- [`RELEASE_0.6.0_BROWSER_QA_2026-10-01.md`](RELEASE_0.6.0_BROWSER_QA_2026-10-01.md)
  — subsequent production browser checks, count-routing reproductions and
  precise remaining acceptance limits.

## Retained predecessor implementation

- [`RELEASE_0.7.0_IMPLEMENTATION.md`](RELEASE_0.7.0_IMPLEMENTATION.md) and
  [`RELEASE_NOTES_0.7.0.md`](RELEASE_NOTES_0.7.0.md) — published research software
  and explicitly deferred real-demo/live-role checks; use its operations record.

- [`RELEASE_0.6.1_IMPLEMENTATION.md`](RELEASE_0.6.1_IMPLEMENTATION.md) and
  [`RELEASE_NOTES_0.6.1.md`](RELEASE_NOTES_0.6.1.md) — prior published patch
  implementation and source changes; use its operations record for deployment.
- [`RELEASE_0.6.0_OPERATIONS.md`](RELEASE_0.6.0_OPERATIONS.md) — published GitHub
  predecessor release and verified historical production traffic switch;
  deferred acceptance is recorded separately from completed checks.
- [`RELEASE_NOTES_0.6.0.md`](RELEASE_NOTES_0.6.0.md) — source changes, migration,
  compatibility and limits for the predecessor v0.6.0 source release.

- [`RELEASE_0.6.0_PLAN.md`](RELEASE_0.6.0_PLAN.md) — adopted chat source-settings
  contract, implementation sequence and acceptance gates.
- [`RELEASE_0.6.0_IMPLEMENTATION.md`](RELEASE_0.6.0_IMPLEMENTATION.md) — local
  candidate changes, migration, verification and remaining live release gates.
- [`V0.6.0_READINESS_AUDIT_2026-10-01.md`](V0.6.0_READINESS_AUDIT_2026-10-01.md)
  — verified repository baseline and stated limits of current system inspection.

## Superseded plans

The following documents describe work that has already shipped or a gate that
has already closed. Retain them as historical design and verification records,
but do not use them to decide the next implementation or deployment:

| Document | Superseded by / present status |
| --- | --- |
| [`RELEASE_0.4.3_PLAN.md`](RELEASE_0.4.3_PLAN.md) | PR1–PR4 and the combined release gate completed in `v0.4.3`; use the operations record for current state. |
| [`RELEASE_0.5.0_PLAN.md`](RELEASE_0.5.0_PLAN.md) | Catalogue import and production rollout completed on 2026-09-30; use the v0.5.0 operations record for current state. |
| [`ANEMONE_V0.5.0_PLAN.md`](ANEMONE_V0.5.0_PLAN.md) | The accessible 2026-09-17 catalogue was imported; future provider refresh and API negotiation remain separate work. |
| [`ANEMONE_INTEGRATION_PLAN.md`](ANEMONE_INTEGRATION_PLAN.md) | PR1–PR5 shipped in `v0.4.0`; classification follow-up shipped in `v0.4.1`/`v0.4.2`. |
| [`ANEMONE_PR2_PLAN.md`](ANEMONE_PR2_PLAN.md) | Canonical schema and ingestion shipped in `v0.4.0`. |
| [`ANEMONE_PR3_PLAN.md`](ANEMONE_PR3_PLAN.md) | Retrieval and evidence navigation shipped in `v0.4.0`. |
| [`ANEMONE_PR4_PLAN.md`](ANEMONE_PR4_PLAN.md) | Scientific analysis scope shipped in `v0.4.0`. |
| [`ANEMONE_PR5_PLAN.md`](ANEMONE_PR5_PLAN.md) | Pilot, publication, and `v0.4.0` rollout completed. |
| [`ANEMONE_NEXT_PATCH.md`](ANEMONE_NEXT_PATCH.md) | Its `v0.4.1` classification/no-evidence work and `v0.4.2` presentation work shipped. |
| [`ANEMONE_CLASSIFICATION_PR3_PLAN.md`](ANEMONE_CLASSIFICATION_PR3_PLAN.md) | Effect preview shipped in `v0.4.1`. |
| [`ANEMONE_CLASSIFICATION_PR4_PLAN.md`](ANEMONE_CLASSIFICATION_PR4_PLAN.md) | Controlled application/republication shipped in `v0.4.1`. |
| [`PRE_MILESTONE_VALIDATION_PLAN.md`](PRE_MILESTONE_VALIDATION_PLAN.md) | The 2026-07 pre-cloud gate closed; later GCP release evidence supersedes it. |
| [`PHASE7_RELEASE_RUNBOOK.md`](PHASE7_RELEASE_RUNBOOK.md) | The `v0.1.0` Phase 7 release completed. |
| [`deploy/gcp/MIGRATION_PLAN.md`](../deploy/gcp/MIGRATION_PLAN.md) | The 2026-08 initial GCP migration completed; current deployment guidance is in [`DEPLOYMENT.md`](DEPLOYMENT.md) and [`deploy/gcp/README.md`](../deploy/gcp/README.md). |

## Historical evidence, not obsolete documentation

These are deliberately dated records and should not be rewritten into current
instructions:

- `RELEASE_NOTES_*.md` and `RELEASE_*_OPERATIONS.md`;
- [`ANEMONE_PILOT_2026-09-03.md`](ANEMONE_PILOT_2026-09-03.md);
- [`GCP_RESOURCE_AUDIT.md`](GCP_RESOURCE_AUDIT.md);
- the deployment-record sections in
  [`PROVENANCE_SNAPSHOT_RUNBOOK.md`](PROVENANCE_SNAPSHOT_RUNBOOK.md);
- [`archive/README.md`](../archive/README.md) and
  [`archive/legacy-streamlit/README.md`](../archive/legacy-streamlit/README.md),
  which correctly label retired application code.

## Active documents with historical sections

These remain useful, but their dated sections must not be mistaken for current
state:

- [`ANEMONE_CLASSIFICATION_REVIEW.md`](ANEMONE_CLASSIFICATION_REVIEW.md) — active
  review/runbook contract with `v0.4.0`–`v0.4.3` history at the top.
- [`deploy/gcp/ANEMONE_PILOT.md`](../deploy/gcp/ANEMONE_PILOT.md) — active bounded
  pilot runbook with completed rollout language and old-plan links.
- [`TESTING.md`](TESTING.md) — active test instructions followed by dated release
  evidence.
- [`PROVENANCE_SNAPSHOT_RUNBOOK.md`](PROVENANCE_SNAPSHOT_RUNBOOK.md) — active
  publication runbook followed by historical deployments.
- [`handoff.md`](../handoff.md) — current status plus a large, clearly labelled
  completed-work appendix.
- [`ROADMAP.md`](ROADMAP.md) — current priorities plus completed milestone
  checklists.

## Current reference and operating documents

- [Repository maintenance audit](REPOSITORY_MAINTENANCE_AUDIT_2026-10-02.md) —
  dated pre-maintenance branch, PR and alert snapshot.
- [Repository maintenance execution](REPOSITORY_MAINTENANCE_2026-10-02.md) —
  dependency/branch/alert dispositions, container verification and outstanding
  hardening work; distinct from the deployed v0.6.1 release.

The root `README.md`, root `SECURITY.md`, `docs/BRANDING.md`,
`docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `deploy/README.md`,
`deploy/gcp/AUTHENTICATION.md`, `deploy/gcp/README.md`, and
`requirements/README.md` remain current reference material. The draft
[`ANEMONE_PILOT_CLASSIFICATION_PROPOSAL.md`](ANEMONE_PILOT_CLASSIFICATION_PROPOSAL.md)
is unresolved scientific input, not an obsolete plan; it remains unapproved and
must not be treated as canonical classification.

### v0.6.1 implementation records (2026-10-02)

- [Implementation and QA](RELEASE_0.6.1_IMPLEMENTATION.md) — patch/CI evidence; current-admin, mobile and history checks passed; bounded English scientific acceptance passed; live viewer/researcher checks explicitly user-deferred.
- [Published release notes](RELEASE_NOTES_0.6.1.md) — v0.6.1 published and deployed with recorded deferrals.
- [Operations](RELEASE_0.6.1_OPERATIONS.md) — exact-source release, verified GCP traffic, cleanup, rollback and explicit deferrals.
- [Scientific QA dispositions](RELEASE_0.6.1_SCIENTIFIC_QA.md) — deterministic results, complete rejected model batches, claim-level findings and final bounded English acceptance.
