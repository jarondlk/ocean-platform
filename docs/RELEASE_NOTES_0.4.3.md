# OCEAN Platform v0.4.3 release notes

> Draft release notes. Publish only after the combined v0.4.3 gate passes and
> the production operations record has been completed.

## Scope

v0.4.3 hardens the scientific classification and retrieval contracts without
changing the bounded ANEMONE pilot outcome. The pilot remains
`sample_kind=unknown` and `is_control=null`.

## Changes

- Classification review lineage is validated through one strict fail-closed
  contract. `unknown` remains a valid final outcome through apply and rollback;
  later corrections require explicit supersession.
- Operational `applied` and `failed` review events can only be emitted by the
  controlled application ledger path and are bound to the application, review,
  operation, workload actor, stage result, and expected review version.
- Vector and full-text retrieval use independent transaction scopes, shared
  normalized weights and `rrf_k`, and deterministic `doc_id` ordering in both
  PostgreSQL and local modes.
- Data APIs and analysis generation share one pure scientific eligibility
  evaluator with method-level status and stable exclusion reason codes.

## Verification required before publication

- Full backend coverage at the CI threshold and PostgreSQL/pgvector integration.
- Ruff, dependency checks, production-only frontend audit, frontend tests,
  TypeScript, production build, CI, and CodeQL.
- Isolated controlled-application replay and rollback rehearsal.
- Authenticated researcher/admin/viewer acceptance matrix.
- Pre-deployment backup/restore, immutable candidate smoke tests, traffic
  rollout, and post-release monitoring under the JPY 20,000 monthly limit.

## Explicit non-goals

- No inferred ANEMONE classification or automated download/scheduled ingestion.
- No web-to-Cloud-Run execution bridge.
- No claim of taxonomic accuracy, contamination clearance, abundance, or
  environmental association beyond reviewed evidence.
