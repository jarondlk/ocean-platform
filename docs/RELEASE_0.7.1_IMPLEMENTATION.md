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
legacy-history rendering; typecheck and production build passed. The exact-source initial CI run
[333](https://github.com/jarondlk/ocean-platform/actions/runs/37298471710) passed
all four jobs, including production PostgreSQL 16 migration/metadata checks.
The final diagnostic hardening has a separate regression and requires fresh CI/build.

## Remaining acceptance

Final hardening-source CI/container verification and candidate replacement;
actual viewer/researcher checks under #101, including isolated disposable review
transitions and direct API denials; saved-history/admin acceptance; final production
regression/history/anonymous-denial checks and cleanup. Initial source CI, container,
backup/restore, candidate admin sign-in and paired retrieval checks passed below.

The user has confirmed that legitimately invited viewer and researcher accounts
are available. No live role check is marked passed by that confirmation. Issues
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
within the existing section budgets. Each ranker's vector and text branches keep
existing 2*k overfetch bounds. The two-source k=1 case reported incomplete coverage;
k=25 supplied 13 SST and 12 eDNA, retaining the unverified-overlap guard.

Final review additionally bounded linked-expansion errors to a safe code instead
of exposing backend exception text. Its focused regression passed; exact-source
CI/rebuild and live role/history/denial acceptance remain required.

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
