# C14 read-only readiness preparation — 2026-10-16 JST

**Local prerequisite checks pass. Final readiness is pending exact amended-source
C13 hosted CI and its delivery confirmation.** No C14 application implementation
or global status change is performed by this audit. The parent agent owns that
remaining gate and subsequent automatic implementation under the user's sequential
continuation authorization.

Source checkpoint: `98c2769402cb83602f515348651aca668f21d0dd` on `overhaul`.
The C13 authoritative final source receipt is
`../C13/method-alias-amendment/verification.json`, whose source aggregate is
`6b51bb15ae88835d1e0c1dc2a08609362969bad27fcf180a606be0e25df355ee`.
The earlier C13 receipt is historical and remains unchanged. Its earlier hosted
run cannot establish acceptance of the amended source.

## Prerequisites and fresh checks

The specification declares C04, C08, C09, C10, C11, C12 and C13. All source and
receipt bindings reconcile across 89 formal prerequisite path entries:

| Component | Paths | Original matches | Accepted supersessions |
| --- | ---: | ---: | ---: |
| C04 | 4 | 4 | 0 |
| C08 | 12 | 6 | 6 through C12 |
| C09 | 14 | 13 | 1 through C12 |
| C10 | 10 | 10 | 0 |
| C11 | 10 | 10 | 0 |
| C12 | 22 | 22 | 0 |
| C13 | 17 | 15 | 2 through final method-alias amendment |

The C13 amendment normalizes existing C02 aliases before eligibility. Its exact
input validator and tests match the authoritative amended hashes. This retains
the original local C13 receipt SHA256
`83a94476d9a5c830142853b5e29fdd38f1710258c09ac1abaa1448be52f810ca`.

Fresh commands run through `verify_readiness.py` with test authentication settings,
mock login/local chat persistence disabled, PostgreSQL integration gated and unused
database/model URLs at loopback port 1:

- C14 baseline (`test_catalogue_cache`, `test_api_security`, `test_api_schemas`,
  `test_auth`): **93 passed**, one existing warning, 1.03 seconds.
- C08 catalogue fixture regressions: **33 passed**, 7.90 seconds.
- All **nine** generated-contract comparisons pass.

Total: **126 passed, zero failures or skips**. No database, provider, model or
persistent service is started. These targeted checks supplement the final C13
local prerequisite/composite and backend results; they do not replace hosted
delivery evidence.

## Scale evidence and honest capacity boundary

`schema/context_catalogue_fixtures.py` provides the explicit in-memory
`SyntheticCatalogue` oracle with `FixtureAccess`; it never discovers configuration,
real data or credentials. `tests/test_context_catalogue_fixtures.py` constructs
100,000 canonical dataset objects and verifies all 200 pages of 500 records visit
them exactly once in deterministic ID order. It verifies direct lookup and name/ID
search at ranks 26, 502 and 100,000, source filters, permission denial, stale
cursor rejection, preview-independent totals and cross-link deduplication.

That evidence proves the existing C08 transport/oracle capacity. It does **not**
prove authenticated HTTP/tool traversal, per-request revocation, production
performance or a 100,000-dataset C13 registry. The C13 registry deliberately caps
bindings at 4,000 and retains 2,000,000 rows/512 MiB source bounds. C14 must expose
the same service contracts to an explicitly injected scale backend in tests and
to the actual frozen C13 adapter in source integration tests. A synthetic backend
must never become a silent runtime fallback. C08's `pages()` helper freezes one
local reference view; the authenticated service must re-evaluate current access
on each real request.

## Implementation decisions required in C14

1. Add an authenticated `/catalogue/*` router and typed wrappers for
   `catalogue.overview`, `list`, `open`, `coverage`, `query`, `relationships` and
   `analysis.get_published`, all delegating to one explicit service boundary.
   Keep legacy source/chat APIs compatible and exposure behind a default-off v1
   catalogue flag. `api/auth.py` currently denies unknown routes by default; new
   routes need deliberate permission mappings without broad administrative access.
2. Derive effective identity/access context from the authenticated request.
   Client-supplied `access_binding`, revision, role or arbitrary callbacks cannot
   authorize a request. Tool calls use the same trusted context and error mapping.
   Source/scientific callbacks still recheck current restrictions for historical
   snapshots before counts, search, facets or returned bytes.
3. Keep synchronous frozen reads/decoding and complete resource lifetimes off the
   event loop, following C04. Add bounded responsiveness/cancellation checks rather
   than claiming throughput from a fast fixture test.
4. `VerifiedCatalogueCache` and its `catalogue_revision()` are legacy references.
   The revision helper discovers configured databases/artifact pointers and uses
   bounded public heads; it is unsuitable as a v1 source of exhaustive inventory
   or permission revisions. Use explicit frozen service dependencies. Any response
   cache must bind current effective access, complete scope, filters, snapshot and
   operation/version; a hit cannot bypass current revocation. Caching may remain
   disabled until those bindings are explicit.
5. Preserve C08 applied scope, stable order, full totals/completeness and cursor
   binding. Defaults are 100 records with a cap of 500. Search remains exhaustive;
   ranking cannot remove members. Aggregate work delegates to fixed C10–C13
   operations over full eligible inputs, retaining known zero versus unknown,
   missing and unavailable. No unrestricted SQL, new scientific computation,
   experiments, planning or answer synthesis is exposed.
6. Test equivalent service/API/tool calls against the same synthetic frozen source
   adapter, then test exhaustive 100,000-object traversal through the new service
   path. Cover forbidden identities absent from counts/search, current revocation
   after previous success, stale context/cursors, snapshot rollover and small
   previews with complete aggregate reference calculations.

## Preservation and remaining gate

All 488 earlier committed evidence files match checkpoint bytes. The 30 unrelated
files, seven real scientific artifacts, two serving files and 36 P00 files retain
their saved hashes. `start-snapshot.json` and `source-verification.json` bind exact
paths and historical receipt supersessions. No older receipt is edited.

No local source or contract blocker was found. **C14 must not be declared ready
or started until the parent confirms final C13 amended-source hosted CI and
delivery.** Actual scientific regeneration/approval, legacy transfer, live
providers, UI integration and cloud deployment retain their separate gates.
