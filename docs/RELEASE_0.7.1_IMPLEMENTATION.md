# v0.7.1 source retrieval patch

Implementation in progress on `codex/v071-source-retrieval`, 2026-10-05 JST.
Production remains v0.7.0. This record does not claim candidate, role or release
acceptance. See the [accepted plan](RELEASE_0.7.1_PLAN.md) and
[issue #105](https://github.com/jarondlk/ocean-platform/issues/105).

## Confirmed production regression

Normal Google admin sign-in reproduced the exact question on production:
“Where do ANEMONE sampling dates and locations overlap with available SST
observations”. CTD/metagenome were disabled; SST/eDNA had no filters; no analysis
was selected. Controls were k=8, vector/text weights 0.6/0.4, RRF=60, linked
expansion enabled with a limit of five. PostgreSQL and eDNA publication were ready.

Combined retrieval supplied eight SST documents, zero eDNA, zero linked or
injected documents. The final prompt retained all eight; there were no prompt
omissions. The answer claimed no spatial/temporal overlap and that zero overlapping
records existed. An eDNA-only repeat with identical controls returned eight eDNA
documents with source-local vector ranks 1–8. Thus eDNA was available under the
selected scope and was lost before packing through global ranking competition.
Citation validity did not establish the answer's scientific claim.

Dated local evidence is retained in `/tmp/ocean-v071-release/production-reproduction.txt`,
`production-reproduction.jpg` and `production-edna-only.txt`. These are private QA
artifacts, not uploaded provider credentials or scientific approval evidence.

## Implemented behavior

- Each enabled family is searched independently using the existing scoped
  PostgreSQL/local ranker. Filters and eDNA membership retain their contracts.
  One lazy request-local embedding is shared across family searches, including
  cached failures that permit independently surviving text branches.
- Stable round-robin selection uses source-local ranks; k remains the total
  primary budget, bounded to 1–25. At most four k-sized candidate lists enter
  the merge. Empty sources donate slots. Operational failures and budget
  omissions are distinguished from empty scoped retrieval.
- Primary prompt packing interleaves families and reserves first-document space.
  Existing field/section caps, escaping, exact excerpts and citation aliases
  remain enforced. Coverage is reconciled after final validation/repacking.
- A narrow English guard handles explicit named multi-source comparisons and
  overlap/matching requests. Disabled or missing required evidence yields a
  deterministic abstention. Co-retrieval without a verified matching result
  yields `overlap_unverified`; the model is not invoked. Ordinary summaries and
  single-source questions retain model-backed routing. This is not a general
  semantic intent classifier or a new spatial/temporal matching engine.
- Existing exact catalogue/research routes execute first and retain their
  no-model, provenance-bearing result contracts. This patch approves no physical
  sampling identity, environmental classification, area or historical SST product.
- Chat, evidence workbench and administrator feedback history display per-source
  counts and limitations. Counts distinguish retrieved from final supplied
  evidence and never imply complete database coverage or verified matches.
- Migration `20261005_0016` extends the Chat reason constraint only. Existing
  histories remain intact; downgrade rejects histories using the new reasons.
  Application rollback retains the additive constraint. The previous admin
  history response accepts reasons as strings and snapshots as dictionaries.

## Verification so far

Baseline regression commit `57756e2` captured the pre-fix failures. Focused
regressions cover dominant SST, all 16 selections, original filters, k limits,
shared embeddings, partial/total search failure, fair escaped prompt packing,
final omissions, deterministic API/standalone guards and retained evidence.

The final local backend suite passed 1,034 tests, with 39 integration skips
and 79.24% coverage. Those integration tests run separately against PostgreSQL.
Real isolated PostgreSQL 18.3/pgvector 0.8.2 passed all 38 existing integration
checks. Additional migration preservation/downgrade checks and final history
checks passed afterward. CI must also verify the production PostgreSQL 16 path.
All 64 frontend tests passed, including mounted coverage announcements and
legacy-history rendering; typecheck and production build passed. CI/build
identifiers will be recorded after the source is frozen.

## Remaining acceptance

Exact-source CI/container runtime/security review; paired latency/query/embedding
and prompt-budget measurements; fresh private backup and restore verification;
zero-traffic normal-auth candidate; actual admin/viewer/researcher checks under
#101, including isolated disposable review transitions; final production
regression/history/anonymous-denial checks and cleanup.

The user has confirmed that legitimately invited viewer and researcher accounts
are available. No live role check is marked passed by that confirmation. Issues
#102, #103 and #89 retain their separate scientific dependencies; #104 requires
current full image/security disposition review. No release is published yet.
