# C09 — Immutable catalogue snapshots

**Status:** Not started. **Prerequisites:** C03, C08. **Contract:** sealed catalogue snapshot v1.

## Objective and boundaries

Make an investigation's data, scientific classifications and operation versions reproducible after publications change. Supply immutable snapshot/export infrastructure for later adapters without holding a database transaction open during model reasoning.

Included: content-addressed manifests, canonical export coordination, verification, snapshot references, retention integration and local store tests. Excluded: per-source query adapters, production publication, cloud writes, legacy-data migration and investigation refresh UI. Real-data sealing and rollout remain later explicitly authorized operations.

## Existing entry points

Verified sources: [artifact storage](../../../../ingestion/artifact_store.py), [immutable provenance snapshots](../../../../ingestion/provenance_snapshot.py), and [catalogue revisions](../../../../orchestration/catalogue_cache.py). Existing suites: `tests/test_artifact_store.py`, `tests/test_provenance_snapshot.py`, `tests/test_immutable_bundle_security.py` and `tests/test_catalogue_cache.py`. Reuse bounded storage, canonical hashing and generation-conditional pointer updates rather than inventing an unverified file store.

## Interface decisions

A sealed manifest binds dataset/object hashes, publication generations, classification and relationship registry versions, operation versions, schema version and source capture metadata. Canonical eDNA exports include rows and classifications required for repeatable queries; source adapters register their export requirements. Snapshot sealing is independent of embedding completion.

Capture database exports in a bounded consistent transaction, record source generations and verify relevant heads before sealing; retry or fail on rollover rather than mix generations. Write immutable bytes, verify hashes, then conditionally advance a latest pointer. Readers use a manifest ID and verify artifacts; they never silently substitute current files for missing historical objects. Reference tracking and C03 hold semantics protect retained snapshots. Current access revocation overrides historical availability; immutable bytes do not grant access. Retain old snapshots on refresh, and expose removed/replaced identities for C17's branch behavior.

## Resumable checkpoints and acceptance

1. **Manifest and local storage:** add snapshot schema, content-addressed layout and seal/read operations on a temporary local store. Acceptance: identical inputs yield stable identities, corrupted or incomplete bundles fail verification, and unsafe paths remain rejected.
2. **Consistent capture:** implement export registration and transaction/generation coordination with synthetic data. Acceptance: publication or registry rollover during capture cannot produce a mixed manifest; aborted exports never become latest.
3. **Retention and references:** bind references/holds, revocation checks and idempotent retries. Acceptance: referenced/held snapshots survive cleanup, unreferenced eligibility is auditable, and revoked data cannot be read through a historical snapshot.
4. **Adapter handoff:** supply frozen fixtures and registration examples for C10–C13. Acceptance: old manifests reopen after newer seals and structured-query readiness is demonstrably independent of embeddings.

Implementation baseline: `python -m pytest tests/test_artifact_store.py tests/test_provenance_snapshot.py tests/test_immutable_bundle_security.py tests/test_catalogue_cache.py`. Add proposed `tests/test_catalogue_snapshots.py` and `tests/integration/test_catalogue_snapshot_capture_postgres.py`. Run integration only against a verified disposable local database; skipped isolation checks remain pending. Do not run publication/acquisition CLIs against real stores.

## Compatibility, rollback and handoff

Use additive schema/storage changes and versioned namespaces. Do not overwrite old bundles or advance existing publication pointers. A feature-flag rollback leaves sealed objects and references intact. Record manifest schema, transaction boundaries, local verification, retention behavior and adapter examples in `handoffs/C09.md`; checkpoint `STATUS.md`. Complete after consistency and retention acceptance, with no claim of production sealing.

## Exact prompts

**Planning-only**
> Review C09 without implementing. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C09-catalogue-snapshots.md and handoffs/C03.md and C08.md plus any C09 handoff. Inspect checkout and prerequisite evidence. Report refinements only; do not edit application code, seal real data or begin implementation without an explicit implementation request.

**Implementation**
> Implement only C09. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this C09 specification and C03/C08/C09 handoffs under docs/plans/ocean-v1. Verify prerequisites and checkout; preserve unrelated work. Complete checkpoints, updating STATUS.md and handoffs/C09.md after each. Run required local tests before completion. Do not seal real data, start another component, publish, make cloud writes, provision, deploy or run paid model evaluation.

**Resume**
> Resume C09 only. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C09-catalogue-snapshots.md and handoffs/C03.md, C08.md and C09.md. Reconcile prerequisites, checkout and test evidence, then continue the next unfinished checkpoint. Preserve unrelated work and update status/handoff after tested checkpoints. Do not seal real data, start another component, publish, make cloud writes, provision, deploy or run paid model evaluation.
