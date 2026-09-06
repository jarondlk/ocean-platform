# OCEAN Platform v0.4.1

Research-safety and authenticated ANEMONE classification workflow foundation.
The deployed pilot remains unclassified unless a separate authenticated
scientific review and manual controlled application are completed.

## Included

- Deterministic abstention before model generation when no usable evidence
  survives the applied scope, with durable outcome/reason and model-run status.
- Explicit eDNA publication readiness and direct display of scientific filters
  and empty-cohort outcomes.
- Authenticated, evidence-bound classification drafts and scientific decisions.
  Researcher and operational roles remain separate; identity and time are
  server-derived, and review events are append-only.
- Read-only current-versus-proposed classification effect preview using the
  existing deterministic eDNA analysis algorithm.
- Manual controlled application through the existing Cloud Run processing job:
  immutable review registration, exact-snapshot normalization, transactional
  import, retrieval materialization, affected analysis regeneration, scoped
  embedding refresh, provenance publication, and final operational receipt.
- Durable application stages, safe recovery instructions, idempotent replay,
  concurrency rejection, stale/superseded approval checks, and explicit
  superseding-review rollback.

## Scientific boundary

`unknown` remains a valid final review outcome and remains excluded from
environmental-only analyses. This release does not approve or apply the retained
ANEMONE pilot proposal and does not claim contamination clearance, taxonomic
accuracy, environmental biodiversity validation, or live CTD/SST overlap.

The application and browser cannot launch the classification job. Production
application remains a manual operator action against an already authenticated,
approved database review. A direct API request cannot mark a review applied.

## Operations

Apply additive migrations through `20260905_0011`. Register the exact Cloud Run
processing service account with `scripts/register_classification_workload.py`
before any future controlled application. Preserve a verified database backup,
the previous service revision, immutable artifacts, and publication pointers.

The release gate passed 688 backend tests with 12 expected service-gated skips
and 78.31% coverage, 12 PostgreSQL integration tests, 18 frontend tests,
TypeScript, the 24-route production build, Ruff, dependency checks, migration
downgrade/re-upgrade, and diff validation. Live deployment checks are recorded
in the [v0.4.1 operations record](RELEASE_0.4.1_OPERATIONS.md) and must not be
inferred from local verification.
