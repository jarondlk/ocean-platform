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

The initial implementation local backend suite passed 1,034 tests, with 39 integration skips
and 79.24% coverage. Those integration tests run separately against PostgreSQL.
Real isolated PostgreSQL 18.3/pgvector 0.8.2 passed all 38 existing integration
checks. Additional migration preservation/downgrade checks and final history
checks passed afterward. CI must also verify the production PostgreSQL 16 path.
All 64 frontend tests passed, including mounted coverage announcements and
legacy-history rendering; typecheck and production build passed. The exact-source initial CI run
[333](https://github.com/jarondlk/ocean-platform/actions/runs/37298471710) passed
all four jobs, including production PostgreSQL 16 migration/metadata checks.
The final hardening and routing fixes passed fresh exact-source CI/build, recorded
in [container verification](V0.7.1_CONTAINER_QA_2026-10-05.md).

## Remaining acceptance

Normal viewer/researcher permission, synthetic-review and saved-history checks
passed, with all QA identities/roles restored. The user explicitly deferred live
mobile layout acceptance. Remaining work is production backup/migration, exact-source publication and
canonical rollout, production regression/history/anonymous-denial checks and
temporary-resource cleanup. CI, container checks, initial backup/restore, candidate
normal sign-in and paired retrieval checks passed below.

The user clarified that separate viewer/researcher accounts are unavailable. A
reviewable alternative temporarily changes the existing principal’s role only in
the isolated QA database, using ordinary Google sign-in and restoring its original
role afterward. The user approved that additional scope; the role checks and complete restoration
passed as recorded in [live acceptance](V0.7.1_LIVE_QA.md). Issues
#102, #103 and #89 retain their separate scientific dependencies; #104 requires
current full image/security disposition review. No release is published yet.

## Isolated candidate verification

The user explicitly approved a private full backup, isolated restore test and
QA database copy on the existing Cloud SQL instance. The 208,268,759-byte backup
SHA-256 is `16763f7711b01598b4739d1c513aa3858867dabf5fee31890990cfa85db70890`.
Restore verification passed and removed its disposable restore-test database.
The separate role-QA copy retained every corpus, completed-history and identity/role
hash. Migrating only that copy to 0016 preserved all row counts and hashes, while
production remained on 0015. No account roles or IAM permissions were changed.
Private backup/receipts are under `backups/v071/source-aware-20261005` in the existing
private data bucket; QA account records and history are not public artifacts.

Initial zero-traffic revision `ocean-platform-v071-sourceqa1005` uses the QA copy
and the exact-source initial images above. The canonical service continues to
send 100% of traffic to `ocean-platform-v070-software1005`. Normal Google admin
sign-in passed with invitation/role checks unchanged. The temporary candidate
callback was saved with explicit user approval and must be removed after QA.

The exact reported question supplied four SST and four eDNA documents in the
final prompt, publication ready, no prompt omissions. Outcome was `abstained`,
reason `overlap_unverified`, model not run. The UI prominently showed both counts
and the unverified matching limitation. This fixes the observed competition
regression without claiming a spatial/temporal match or biological absence.

Read-only QA execution `ocean-v071-retrieval-qa-2x67j` passed all 16 source selections,
18 paired retrieval samples, k=1/25 limits, final packing and an impossible future
scope. It wrote no Chat history or generated answers. Both pooled and independent
retrieval used one embedding call per nonempty vector request.

| Enabled families | Pooled median ms | Independent median ms | SELECT count pooled / independent | Independent primary counts |
| --- | ---: | ---: | --- | --- |
| SST | 1233.4 | 1416.5 | 2 / 3 | SST 8 |
| SST + eDNA | 1191.8 | 1640.8 | 2 / 5 | SST 4, eDNA 4 |
| All four | 1277.4 | 1965.7 | 2 / 9 | 2 per family |

These are only three paired samples per case, including cold/warm execution, not
an SLA or load test. Peak Python allocations after cold initialization were below
1.1 MB for independent retrieval; this is not process RSS. Primary count remained
8. Candidate prompt lengths were 8,068 / 18,699 / 15,918 characters respectively,
within the existing section budgets. The candidate acceptance envelope for these
bounded paired samples is an independent median below twice the corresponding
pooled median (observed 1.15x / 1.38x / 1.54x), one embedding per request, at most
four families, total k <= 25 and at most 4*k post-fusion candidates. This accepts
the measured representation/latency tradeoff for this patch, not an SLA, peak RSS
guarantee or representative cohort/load qualification. Each ranker's vector and text branches keep
existing 2*k overfetch bounds. The two-source k=1 case reported incomplete coverage;
k=25 supplied 13 SST and 12 eDNA, retaining the unverified-overlap guard.

Final review additionally bounded linked-expansion errors to a safe code instead
of exposing backend exception text. Its focused regression and fresh exact-source CI/rebuild passed; live
role/history/denial acceptance subsequently passed below.

## Additional live routing regression

Normal-auth candidate QA found that ordinary “Summarize ANEMONE eDNA and SST
evidence” wording was intercepted by the existing exact-catalogue router and
returned `aggregate_scope_required` before retrieval. The patch now routes soft
summary requests naming multiple families to ordinary retrieval. Explicit counts,
forced aggregation and eDNA-only catalogue summaries keep their conservative
contracts. Planner and full API regressions verify model invocation and both
final evidence families. This defect was fixed before final candidate acceptance;
the superseded intermediate build is not release evidence.

An initial ordinary generated explanation also attributed a station SST NaN to
cloud cover/data loss although the supplied document did not give a cause. Prompt
guidance now explicitly treats missing/non-finite numbers as unavailable and
forbids invented gap causes or interpreting raw counts as valid observations.
This is model guidance, not deterministic claim verification; repeated final
ordinary-answer review is required and citation validity alone is insufficient.

## Final candidate and repeated answer checks

Final runtime source `e157fb004871083df25d5d094852fed417a9c8c6` is deployed
at zero traffic as `ocean-platform-v071-sourceqa1005b`. Exact-source CI and
Cloud Build `edac2319-6969-4553-9505-182e25a0b017` passed; image digests and
complete security disposition are recorded in the container QA document.
Production remains on v0.7.0 and schema 0015.

Read-only execution `ocean-v071-retrieval-qa-zkz5m` ran three ordinary summaries
against final-source retrieval and prompt code, using both eDNA and SST with SST
restricted to 2026-02-07. Each run supplied one SST and seven eDNA documents.
The multi-source query bypassed the catalogue-count router and invoked the model.
All citation audits reported zero invalid citations; citation counts were 46, 48
and 55. Private results include the exact supplied texts and generated answers.
No Chat histories or provider records were written by the job.

A bounded manual review compared numeric values, dates and locations with those
supplied texts. All three answers treated the station NaN as unavailable, avoided
invented cloud/data-loss causes and did not claim verified overlap, non-overlap or
database absence. Read counts were qualified as sequencing evidence rather than
organism abundance. Provider labels do not establish approved physical identity.
This verifies those three answers only: automated claim verification was not
performed, and these checks do not replace real-data demonstrations or role QA.

Final-candidate normal Google admin sign-in repeated the exact reported question:
four SST and four eDNA documents supplied, `overlap_unverified`, abstained,
model not run, and all eight evidence rows retained. Anonymous protected health,
admin feedback and review proxy requests returned 401. This verifies the current
candidate regression; normal viewer/researcher permission checks subsequently
passed as recorded below.

The final-candidate normal-auth UI also answered “Summarize ANEMONE eDNA and
SST evidence. Include dates, locations and scientific limitations.” through
ordinary model routing, supplying four documents from each family. All eight were
cited; 45 citations were valid, zero invalid, zero warnings. The response treated
the station NaN as missing and retained unknown classification/calibration and
provider-grid limitations. This is an additional bounded UI sample, not automated
scientific claim verification or a substitute for the role checklist.


## Normal-account role acceptance

The approved isolated-role alternative completed actual Google viewer/researcher
sessions, source/card/feedback/history checks, cross-user 404s, direct privilege
403s and stale-version 409 enforcement. Cached UI controls submitted ordinary
same-origin requests after a QA role change; the backend used the current database
role and rejected the operation. Synthetic approve/reject/application transitions
and immutable chains passed. All original QA identities/roles were restored;
production permissions, scientific content and histories were preserved, and no
synthetic review existed in production. Full outcomes and observed transient
errors are recorded in the live QA document. Temporary-resource cleanup and
production release acceptance remain outstanding.
