# C09 — Immutable catalogue snapshots

**Status:** Complete for local snapshot/capture acceptance (2026-10-15 JST). **Prerequisites:** C03, C08. **Contract:** sealed catalogue snapshot v1.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Make an investigation's data, scientific classifications and operation versions reproducible after publications change. Supply immutable snapshot/export infrastructure for later adapters without holding a database transaction open during model reasoning.

Included: content-addressed manifests, canonical export coordination, verification, snapshot references, retention integration and local store tests. Excluded: per-source query adapters, production publication, cloud writes, legacy-data migration and investigation refresh UI. Real-data sealing and rollout remain later explicitly authorized operations.

## Existing entry points

Verified sources: [artifact storage](../../../../ingestion/artifact_store.py), [immutable provenance snapshots](../../../../ingestion/provenance_snapshot.py), and [catalogue revisions](../../../../orchestration/catalogue_cache.py). Existing suites: `tests/test_artifact_store.py`, `tests/test_provenance_snapshot.py`, `tests/test_immutable_bundle_security.py` and `tests/test_catalogue_cache.py`. Reuse bounded storage, canonical hashing and generation-conditional pointer updates rather than inventing an unverified file store.

## Interface decisions

A sealed manifest binds dataset/object hashes, publication generations, classification and relationship registry versions, operation versions, schema version and source capture metadata. Canonical eDNA exports include rows and classifications required for repeatable queries; source adapters register their export requirements. Snapshot sealing is independent of embedding completion.

Capture database exports in a bounded consistent transaction, record source generations and verify relevant heads before sealing; retry or fail on rollover rather than mix generations. Write immutable bytes, verify hashes, then conditionally advance a latest pointer. Readers use a manifest ID and verify artifacts; they never silently substitute current files for missing historical objects. Reference tracking and C03 hold semantics protect retained snapshots. Current access revocation overrides historical availability; immutable bytes do not grant access. Retain old snapshots on refresh, and expose removed/replaced identities for C17's branch behavior.

## Independent data-copy contract

Snapshots and export/import state belong to v1's independent stores. Add a frozen
transfer manifest and import validation/quarantine boundary for explicitly
approved copies: origin ID, source generation, hashes, schema/method versions,
scientific qualifications, access conditions and authorization reference. Verify
count/hash/eligibility reconciliation with synthetic local transfers, including
rejected/tampered imports and retained origin provenance. Never silently read
legacy storage if an input is absent. Real export/import is separately authorized.
Document the source-withdrawal handling dependency before real transfers.

## Resumable checkpoints and acceptance

1. **Manifest and local storage:** add snapshot schema, content-addressed layout and seal/read operations on a temporary local store. Acceptance: identical inputs yield stable identities, corrupted or incomplete bundles fail verification, and unsafe paths remain rejected.
2. **Consistent capture:** implement export registration and transaction/generation coordination with synthetic data. Acceptance: publication or registry rollover during capture cannot produce a mixed manifest; aborted exports never become latest.
3. **Retention and references:** bind references/holds, revocation checks and idempotent retries. Acceptance: referenced/held snapshots survive cleanup, unreferenced eligibility is auditable, and revoked data cannot be read through a historical snapshot.
4. **Adapter handoff:** supply frozen fixtures and registration examples for C10–C13. Acceptance: old manifests reopen after newer seals and structured-query readiness is demonstrably independent of embeddings.

Implementation baseline: `python -m pytest tests/test_artifact_store.py tests/test_provenance_snapshot.py tests/test_immutable_bundle_security.py tests/test_catalogue_cache.py`. Add proposed `tests/test_catalogue_snapshots.py` and `tests/integration/test_catalogue_snapshot_capture_postgres.py`. Run integration only against a verified disposable local database; skipped isolation checks remain pending. Do not run publication/acquisition CLIs against real stores.

## Compatibility, rollback and handoff

Use additive schema/storage changes and versioned namespaces. Do not overwrite old bundles or advance existing publication pointers. A feature-flag rollback leaves sealed objects and references intact. Record manifest schema, transaction boundaries, local verification, retention behavior and adapter examples in `handoffs/C09.md`; checkpoint `STATUS.md`. Complete after consistency and retention acceptance, with no claim of production sealing.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c09). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Accepted local checkpoint — 2026-10-15 JST

All four checkpoints pass: 206 focused tests; 21 actual disposable PostgreSQL
cases; full backend 2,469 passed/84 gated skips with 82.60% coverage. The new
PostgreSQL suite is executed separately, including head rollover, bounded locks,
read-only exports and interrupted publication. [Handoff](../handoffs/C09.md),
[contract guide](../C09_SNAPSHOT_CONTRACT.md) and [local receipt](../evidence/C09/verification.json)
record exact sources and limitations. Cleanup performs logical retirement with
physical_deleted_count=0; physical GC is deferred. No real sealing, transfer,
cloud or C10 implementation is selected. Hosted delivery is recorded separately.
