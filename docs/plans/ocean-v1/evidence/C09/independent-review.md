# C09 independent review

Date: 2026-10-15 JST. Outcome: **No blocking findings remain.**
Reviewer: `/root/c09_review`. Implementation files were reviewed read-only.
The reviewer authored only the requested contract guide and this report.
Root owns the final source hashes, full-suite results and hosted delivery.

## Reviewed boundaries

- Snapshot schema, canonical hashing, exact object/source/operation bindings,
  consistent global registries and eDNA rows/classifications per export dataset.
- Local verified byte storage, separate pointer/control generations, conditional
  promotion, current access and withdrawal, references, holds, retirement,
  idempotency and confirmed/uncertain state-write outcomes.
- Frozen source registration, whole selected-family capture, rejected row
  filters, read-only repeatable export, exact generation reconciliation and final
  PostgreSQL SHARE table lock through local publication.
- Transfer origin, authorization/eligibility checks, bounded quarantine,
  hash/count reconciliation, shared blobs and explicit chained-copy rejection.
- Executable four-family registration, generated schema/portable byte examples,
  fixture replay tests and the CI changes for generation checks and a dedicated
  disposable C09 database. Existing PostgreSQL/frontend gates remain present.

## Independent probes

1. A combined four-family/five-object manifest produced the same identity under
   all 120 export-object permutations and all 24 source-capture permutations.
   Five individual object-byte changes were rejected: **149 probes passed**.
   Seal/promotion from pointer generation zero succeeded, verified shared blobs
   reopened correctly, and the caller's inputs were unchanged.
2. A valid two-object eDNA copy with one shared content hash imported, retained
   exact bytes and origin, and left latest untouched. Transfer identity survived
   simultaneous nested snapshot/object reordering. **Seven negative cases**
   rejected wrong destination, current authorization, current eligibility,
   tampered bytes, row count, origin hash and chained-copy provenance. Temporary
   quarantine had zero remnants; no latest promotion occurred.
3. The generated snapshot schema/examples passed their `--check` exporter.
   Every local link in `C09_SNAPSHOT_CONTRACT.md` resolved. Both Python guide
   examples parsed/executed, including the explicit CTD operation registration
   and the all-four-family synthetic registry.

The reviewer inspected the recorded focused acceptance (**206 passed**) and
actual disposable PostgreSQL acceptance (**21 passed**, zero fixture schemas
remaining and owned server stopped). These observations supplement the root's
acceptance receipt; they do not stand in for full-suite or hosted CI evidence.

## Findings resolved during review

Pointer generation no longer changes when sealing or updating retention state.
Source/operation identities and global registry versions are bound explicitly;
eDNA roles cannot be split across unrelated datasets. Unsupported scientific
filters fail before connecting. Earlier exporter descriptors are detached before
another callback runs. Content-addressed quarantine deduplicates identical bytes,
transfer identity canonicalizes nested snapshots, and previous origins cannot
be silently overwritten. Local write uncertainty and database-release uncertainty
carry reconciliation information without claiming rollback or success.

## Deliberate limits

C09 is an independent local contract, not an authenticated service or a real
scientific adapter. Current policy must be supplied by trusted callers. Physical
garbage collection is deferred; cleanup reports logical retirement and zero
physical deletions. PostgreSQL and local files do not share an atomic commit.
Multi-hop transfers, source-withdrawal operations, real sealing/copying and cloud
deployment remain separately selected work. No reviewer probe accessed an
existing database, provider, legacy store or cloud service.
