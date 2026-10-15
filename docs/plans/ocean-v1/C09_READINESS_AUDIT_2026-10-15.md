# C09 readiness audit

Updated: 2026-10-15 JST. Branch: `overhaul`.
Source checkpoint: `3cbf9f08fd623bf3c186cb2faf7652f803829170`.

**C09 is ready for explicit implementation selection. No prerequisite blocker was
found. C09 remains Not started and unselected.** This audit verifies readiness;
it does not implement snapshots, publish data or start services.

## Prerequisites and delivered source

The specification and component manifest both require **C03 and C08**.

- C03 retention application/routes and unit suites match accepted hashes. Its
  original workflow and PostgreSQL fixture hashes were intentionally superseded
  by recorded CI identity and subsequent integration changes. All six current
  accepted paths match. The C03 handoff and C05/C06 readiness records explain
  that history; the historical receipt has not been rewritten.
- C08 is complete and delivered as `6d20a75`; all 12 source/test/schema hashes and
  its frozen local receipt checksum match. Current HEAD adds only the 12 C08
  delivery documentation/evidence paths after that implementation.
- [C08 hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38695834706)
  passed 2,305 backend tests with 83.09% coverage, both frontends (132 legacy/162
  v1 tests, typechecks/builds and production dependency audits), all 63 actual
  PostgreSQL cases, idempotent upsert and isolated backup/restore. These include
  all 12 C03 retention ordering cases. No SQL/application drift has occurred since.
- GitHub origin/overhaul and local HEAD matched at the audited checkpoint.
  All 36 current accepted P00 files, 30 older unrelated files, 7 scientific
  artifacts and 2 serving files remain unchanged.

[Verification receipt](evidence/c09-readiness-2026-10-15/verification.json) binds
current sources, prerequisite history, command/results, preserved hashes and
this audit. Earlier component receipts remain historical.

## Fresh offline verification

| Check | Result |
|---|---|
| Exact C09 baseline: artifact store, provenance snapshot, immutable bundle security, catalogue cache | 51 passed, zero skips |
| C03 retention/cleanup/guard and C08 contract/fixture suites | 246 passed, zero skips; one existing deprecation warning |
| Generated JSON Schema, browser types and shared examples | Current |
| Generated scientific source-scope contract | Current |
| Readiness runner lint, document links and diff | Pass |

The baseline command is:

```sh
.venv/bin/python -m pytest tests/test_artifact_store.py tests/test_provenance_snapshot.py tests/test_immutable_bundle_security.py tests/test_catalogue_cache.py -q --tb=short
```

The runner uses explicit test settings, unused loopback database/model URLs,
mocked providers and temporary fixture storage. It starts no service and runs no
publication/acquisition command against actual stores. PostgreSQL 18.3 initdb and
pg_ctl binaries are available locally; a future capture integration test must
create and verify its own disposable database. This audit does not rerun live
PostgreSQL: unchanged C03/C08 source is already covered by the accepted hosted run.

## Implementation starting points

Existing artifact storage supplies bounded verified reads, immutable create,
retained registration and generation-conditional pointer updates. Provenance
snapshots supply canonical bytes, hashes, local/GCS store abstractions and
compare-and-swap conflict handling. Tests already cover interrupted registration,
stale generations, corruption, path traversal/symlinks and revision rollover.
C08 supplies canonical identities, source scopes, origin qualifications and
reference fixtures; its cursor is not a production authorization token.

These foundations do not implement the future C09 contract. Preserve these
specific requirements when C09 is selected:

1. Define a versioned sealed catalogue manifest, content-addressed local layout
   and verification operations using the accepted C08 fields. Use explicit v1
   temporary namespaces and never advance legacy publication pointers. Respect
   existing byte/file/index bounds when choosing a scalable manifest layout.
2. Register canonical source exports, including eDNA rows/classifications;
   capture consistent data and registry/publication versions in a bounded
   transaction, then recheck generations before sealing. The legacy bounded
   catalogue revision helper is a reference, not an exhaustive inventory or an
   atomic cross-registry capture. Embedding completion must remain independent.
3. Extend reference/hold semantics to snapshots. C03 currently protects chat
   records; it does not already protect future snapshot references. Test cleanup,
   access revocation, retry and capture races against explicit synthetic and
   disposable database fixtures. Historical bytes alone never grant access.
4. Define synthetic transfer manifests and quarantine/import verification with
   origin provenance. Preserve old manifests after rollover; never read through
   to legacy storage when an input is missing. Supply frozen examples for C10–C13.

No real-data regeneration, approved-data transfer or cloud provisioning is needed
to begin those local checkpoints. Real sealing, publication, live isolation and
production acceptance remain later operations. Deferred scientific artifact and
C05 serving rebuilds remain untouched and do not block C09's synthetic work.

## Exact next action

When the user selects C09, read its specification/prompt, the C03 and C08 handoffs,
[C08 contract guide](C08_CATALOGUE_CONTRACT.md), site separation and this receipt.
Begin checkpoint 1 with manifest/local-store contracts and corruption/conflict
fixtures. Create the C09 handoff and change its state to In progress only after
selection. No C09 handoff, implementation acceptance or cloud deployment is
claimed by this readiness audit.
