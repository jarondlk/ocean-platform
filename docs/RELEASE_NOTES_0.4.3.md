# OCEAN Platform v0.4.3 release notes

Released from merged PR #58 commit
`26094fc2c1f1f9cad094c484aff4522ba738240f` and deployed to Cloud Run revision
`ocean-platform-v043-26094fc` on 2026-09-10. See the
[v0.4.3 operations record](RELEASE_0.4.3_OPERATIONS.md).

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

## Verification

- 732 backend tests passed with 13 expected skips and 78.16% coverage; all 13
  fresh PostgreSQL 16/pgvector integration tests passed.
- Ruff, dependency checks, the production-only frontend audit, 19 frontend
  tests, TypeScript, the 24-route production build, CI, and CodeQL passed.
- The controlled-application replay/rollback and fail-closed lineage contracts
  passed without changing the real pilot classification.
- A verified backup/isolated restore, immutable build, zero-traffic candidate,
  job canaries, migration check, production smoke tests, and traffic rollout
  completed. Initial monitoring found no HTTP 5xx, Cloud Run errors, or Cloud
  SQL errors.

Researcher-specific role acceptance, suspension, uninvited-account denial, and
owner-only Billing-console confirmation remain explicit post-release checks.

## Explicit non-goals

- No inferred ANEMONE classification or automated download/scheduled ingestion.
- No web-to-Cloud-Run execution bridge.
- No claim of taxonomic accuracy, contamination clearance, abundance, or
  environmental association beyond reviewed evidence.
