# Documentation status

Last reviewed: 2026-09-11.

This register separates current operating guidance from completed plans and
point-in-time evidence. Here, **superseded** means obsolete as a current work
queue or execution authority. It does not mean the file is inaccurate for its
recorded date or safe to delete. Historical research, release, migration, and
audit records should remain immutable unless an explicit archival policy is
approved.

## Current operating authority

- [`RELEASE_0.4.4_OPERATIONS.md`](RELEASE_0.4.4_OPERATIONS.md) — current release,
  deployment, and remaining-acceptance record.
- [`ROADMAP.md`](ROADMAP.md) — longer-term engineering priorities.
- [`handoff.md`](../handoff.md) — current repository and production handoff.

## Superseded plans

The following documents describe work that has already shipped or a gate that
has already closed. Retain them as historical design and verification records,
but do not use them to decide the next implementation or deployment:

| Document | Superseded by / present status |
| --- | --- |
| [`RELEASE_0.4.3_PLAN.md`](RELEASE_0.4.3_PLAN.md) | PR1–PR4 and the combined release gate completed in `v0.4.3`; use the operations record for current state. |
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

The root `README.md`, root `SECURITY.md`, `docs/BRANDING.md`,
`docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `deploy/README.md`,
`deploy/gcp/AUTHENTICATION.md`, `deploy/gcp/README.md`, and
`requirements/README.md` remain current reference material. The draft
[`ANEMONE_PILOT_CLASSIFICATION_PROPOSAL.md`](ANEMONE_PILOT_CLASSIFICATION_PROPOSAL.md)
is unresolved scientific input, not an obsolete plan; it remains unapproved and
must not be treated as canonical classification.
