# v0.7.1 patch plan — Source-aware retrieval and honest coverage

Status: candidate acceptance in progress, 2026-10-05 JST. Source retrieval, prompt
coverage, deterministic guards and UI are implemented. Exact-source CI/image QA
and normal-account role/workflow acceptance passed. Live mobile disposition,
production migration, publication, rollout and cleanup remain pending.

Repository baseline: clean `main` at
`39f50faf2eed8b4da5096a85bfe28c2a04dfbbd9`. Published v0.7.0 runtime source:
`6167949177e437843b3390ca6fbc9ec9ab705bfc`. Production schema is
`20261004_0015`.

## Objective and issue scope

Fix [#105](https://github.com/jarondlk/ocean-platform/issues/105): a Chat request
with SST and ANEMONE eDNA enabled supplied only SST evidence, then claimed no
overlap because eDNA records were missing from the retrieved context. Retrieval
omission is not proof of source absence or temporal/spatial non-overlap.

| Issue | Treatment in this patch |
| --- | --- |
| #105 | Primary implementation and release acceptance; close after candidate/production regression verification. |
| #101 | Live viewer/researcher acceptance work alongside the patch. Close only after its actual role/workflow checklist passes; do not inherit the v0.7.0 deferral. |
| #104 | Review stable fixes and residual OS dispositions during image acceptance. Apply bounded compatible fixes if available; retain explicit maintenance follow-up for unresolved findings. |
| #102 / #103 | Scientific evidence and historical SST preparation remain separate. Provider/product investigations can proceed independently; this patch supplies no scientific approval. |
| #89 | Remains open for six real-data case dispositions and scientific acceptance. Add the fixed retrieval regression to final Chat QA. |

The patch covers model-backed Chat, `/retrieve`, the evidence workbench, prompt
coverage and saved history. Existing exact catalogue aggregates and deterministic
published research answers retain their separate routing and no-model guarantees.
No new historical acquisition, environmental classifications, sampling registries
or research publications are part of the software fix. Japanese acceptance
remains outside the previously agreed English scope.

## Findings from repository inspection

- `api/main.py` calls `retrieve_with_expansion` once with a shared `k`.
- `orchestration/unified.py` performs one pooled primary retrieval. Both
  PostgreSQL and local search fuse vector/text ranks and take a final global
  `[:k]`; competing families can eliminate one another from that subset.
- Source-owned filters already exist in `retrieval/source_scope.py`; reuse them
  rather than create a second scientific-scope implementation.
- Query-expected family inference is explicitly advisory. It is not presently
  an exhaustive intent or proof-of-overlap classifier.
- Prompt packing is sequential with an 8,000-character field cap and
  32,000-character section cap. It records omissions, but can drop a family
  that successfully retrieved documents.
- The current linked expansion explicitly excludes eDNA anchors and linked
  eDNA records. It cannot be assumed to rescue an SST-only retrieval or establish
  an eDNA/SST match.
- The API abstains when all usable evidence is missing, but otherwise invokes
  the model and records `answered`; an incomplete required-source comparison
  is not deterministically blocked.
- Retrieval and prompt diagnostics are already stored in Chat evidence
  snapshots. Extend them and their presentation rather than rebuild history.
- Chat outcomes are `answered` / `abstained`; reason codes are constrained in
  the API and PostgreSQL. New reasons need coordinated schema/UI/history work.

These findings make source competition and later prompt omission plausible.
The screenshot does not identify which stage lost eDNA; live diagnostics must
establish the actual failure before the fix is accepted.

## Planned retrieval contract

### 1. Canonical scope and independent search

Resolve explicit or legacy scope once, including selected-analysis membership,
publication readiness and source-owned filters. Determine the backend once per
request, then run a bounded search for each enabled family through the same
PostgreSQL/local contract. A single-family request retains its existing ranking.
Unchecked families receive no search, context injection or linked expansion.

Pass an isolated source selection with its original filters to each search.
eDNA member/method restrictions apply only to eDNA; no sibling filter may leak
into CTD, metagenome or SST. Preserve active-publication checks and reject stale
source bindings. Do not switch individual failing PostgreSQL families to a local
corpus silently or mix unexplained generations/backends.

Keep vector/FTS weighting and RRF within each family. Reuse a request-local query
embedding when vector search is enabled, with dimension/model checks; an
embedding failure must leave eligible text search available and be diagnosed.
Begin with bounded sequential family searches and independent backend sessions.
Do not add concurrency until latency measurements justify it; any later bounded
parallelism must respect the connection pool and request deadline.

### 2. Top-K allocation and merge

Keep `k` as the **total primary-document budget**, default 8 and maximum 25.
Do not silently reinterpret it as `k` per source or multiply the prompt size.
Each of at most four families may return up to `k` candidates: at most `4*k`
post-fusion candidates before the bounded merge; backend branch over-fetching
remains capped and separately measured.

Use deterministic round-robin selection over source-local ranked lists, with
one first-round slot per nonempty enabled family when the total budget permits.
Continue rounds until `k` is reached, skipping exhausted lists and deduplicating
by stable document identity. Use a stable family order, source-local rank and
document identity for ties. Never globally re-sort the final set by raw
cross-family RRF scores, which are not calibrated relevance probabilities.

For the default SST/eDNA example, two sufficiently populated source lists receive
four primary slots each. For four populated families, each receives two. Empty
families donate unused slots; they remain explicitly empty in diagnostics.
This is representation of ranked scoped evidence, not proof that every returned
document answers the question. Do not fabricate records or add arbitrary RRF
thresholds to satisfy a quota.

If `k` is smaller than the number of represented families, report the budget
limitation and suggest increasing Top-K. Do not alter saved settings silently.
A comparative answer requiring an omitted family cannot proceed as supported.
All enabled families are still queried so budget omission is distinguishable
from no retrieved matches.

Keep linked expansion in its separate configured budget. Only retain real,
scoped links; co-retrieval, nearby coordinates and nearest dates do not create
new scientific links. Exact aggregates and approved published research routes
execute before generic retrieval as they do today.

## Prompt coverage and answer policy

### 3. Preserve coverage during prompt packing

Pack primary evidence with the same source-round discipline and reserve bounded
excerpt space for each represented family before adding extra records. Respect
existing escaping, identifier/provenance formatting, deduplication and field/
section caps. Include title, source/product semantics, relevant time/location
metadata and the exact excerpt actually supplied; never invent a location or
turn an index date into a collection date.

Linked evidence must not consume the reserved primary-family space. Derived
analysis/reliability context remains separately bounded and scope-verified.
Recompute coverage from the final primary, linked and eligible derived documents
after any exact-taxon repacking and before citation preparation/generation.
An omitted family or truncated relevant field must appear in the final coverage
assessment, even if pre-packing retrieval had complete representation.

### 4. Deterministic comparison guards

Separate three concepts: **enabled families**, **families required by a
supported question**, and **evidence actually supplied**. Selecting all sources
does not make every source mandatory for a question about one family. Existing
keyword coverage inference stays advisory; introduce a narrow, tested contract
for supported comparisons/overlap requests, with clarification when required
families or requested scope cannot be resolved reliably.

| Situation | Planned behavior |
| --- | --- |
| Required source is unchecked | Explain which source to enable; do not synthesize the comparison. |
| Required source has no supplied evidence, is unavailable or is omitted by a budget | Deterministic limitation, `abstained`, model not run for that comparison; retain the available evidence and per-source reason. |
| One source fails operationally | Preserve the failure separately from empty matches. No supported comparison; if every enabled source fails, keep the existing service-error contract. |
| General non-comparative summary has some usable evidence | May answer from that evidence with a prominent partial-coverage qualification; missing unrelated enabled sources do not automatically block it. |
| Both sides retrieved, but overlap is unverified | Do not let the model infer an overlap result. Explain that scoped date/location matching has not been established. |
| Exact, provenance-bearing published match/result evidence is available | Route through its existing deterministic contract and retain exact scope/method/citations. |

For the reported overlap question, the expected safe response without a verified
matching result is: **“The supplied evidence does not establish where ANEMONE
sampling events overlap with SST observations.”** Then give the specific missing
coverage/matching evidence and a useful next step. Never conclude non-overlap
solely because no eDNA records reached the model.

v0.7.1 does not add an unreviewed exhaustive spatial/temporal join or make a new
overlap engine. Positive and negative overlap claims require suitable complete,
scoped calculations or exact accepted result evidence. Two sources present in
the prompt, eight SST dates, or zero linked records are insufficient proof.
Keep SST retrieval/foundation-analysis/model semantics explicit. Prompt guidance
supports these rules but is not the enforcement mechanism for overlap decisions.

## Diagnostics, UI and history

### 5. Versioned evidence coverage record

Add a diagnostic version and retrieval strategy identifier. For each family,
record enabled/attempted state, backend, original effective filters, publication
state where verified, returned candidate/merged/linked/final-prompt counts,
source-local ranking provenance and omission/failure reason. Record request
budgets, actual stage timing and any degraded vector/FTS branch.

Use accurate states such as disabled, retrieved, empty-under-scope, publication
unavailable, backend failure, merge-budget omitted and prompt-budget omitted.
If index/eligible-record availability was not measured, record unknown rather
than infer database absence from zero matches. Do not label capped candidate
counts as complete corpus counts, and do not expose raw SQL, secrets or internal
exception details in user-facing diagnostics.

Show a compact per-source coverage summary beside the answer and in the evidence
workbench: for example, “SST: 4 supplied; ANEMONE eDNA: unavailable under these
filters.” Keep technical stage detail in the ledger. Display partial coverage
and unavailable comparisons before the answer body; coverage means supplied
evidence representation, not scientific correctness. Match live/history displays.

Keep `answered` / `abstained` outcome compatibility; use an additive coverage
status for qualified general summaries instead of inventing a third outcome.
Add specific abstention reasons for incomplete required-source coverage and
unverified overlap, with consistent API, generated/frontend types, presentation,
messages and history records. Plan an additive `0016` migration extending only
the history reason constraint; preserve existing rows, evidence and constraints.
Reject downgrade if it would invalidate stored new reasons. Test v0.7.0 history
readback against new records for application rollback compatibility.

Store exact final prompt membership/excerpts, scope, diagnostic version,
strategy, omissions, guard reason and model invocation along with existing
fingerprints/citation audit. Old histories retain their original answers and
evidence; render missing new diagnostics as a legacy record, not fabricated
complete coverage. No database history rewrite or corpus rebuild is planned.

## Implementation sequence

| Work item | Deliverable / principal files |
| --- | --- |
| V071-01 | Reproduce reported query; capture paired single-source/combined diagnostics and source readiness. Add a regression demonstrating the actual loss stage and a dominant-family synthetic fixture. |
| V071-02 | Source-scoped search, bounded fair merge and backend diagnostics: `orchestration/unified.py`, `retrieval/contract.py`, `retrieval/source_scope.py`, PostgreSQL/local rankers. |
| V071-03 | Fair prompt packing and final coverage reconciliation; preserve exact-taxon repacking, context scope checks and citation aliases. |
| V071-04 | Deterministic comparison/overlap guards and available-evidence messages: `api/main.py`, `orchestration/evidence_availability.py`, narrow intent contract and audit integration. |
| V071-05 | Coverage contract, reason-constraint migration, persisted snapshots, Chat/workbench/history UI and accessible warnings. |
| V071-06 | Backend/frontend/PostgreSQL regression matrix, performance comparison, normal-auth live role acceptance and screenshot regression. |
| V071-07 | 0.7.1 metadata/docs, exact-source candidate build/security review, fresh backup/migration, live acceptance, release and controlled GCP rollout. |

Use a `codex/` implementation branch. Commit the confirmed baseline/regression
before changing retrieval, then keep retrieval, packing/guards and UI/migration
changes reviewable. No speculative unrelated refactor is required.

## Verification and acceptance

1. Reproduce the user's exact question with SST + eDNA, then independently with
   each source. Record actual filters, backend, publication state, request ID and
   pre/post-prompt counts. Do not infer configured Top-K from the screenshot's
   eight displayed documents.
2. PostgreSQL and local contracts: all 16 source combinations; independent date,
   region, taxon, method, kind and analysis-membership filters; dominant-source
   ranks; ties/deduplication; `k=1`, defaults and maximum; empty/pending/stale
   evidence; vector/FTS degradation and partial/total family failures.
3. Prompt tests: long/escaped text, source starvation, extra linked context,
   duplicates, exact-taxon repacking, relevant metadata truncation and final
   citation membership. Assert omissions are attributed to the actual stage.
4. API guards: screenshot wording and supported paraphrases; disabled/missing
   required sources; ambiguous wording; both sources without verified matching;
   independently verified positive/negative result fixtures; ordinary one-source
   questions with all boxes enabled. Guarded responses must not call the model
   or label an unsupported comparison as answered.
5. Preserve exact catalogue counts, research intents, source filters, disabled-
   source enforcement, current/historical publications and no-model routing.
6. Real PostgreSQL migration and independent history readback for new reasons,
   final scope, evidence hashes and model state; preservation of old records,
   ownership isolation and application rollback read compatibility.
7. Frontend mounted checks, TypeScript and production build: coverage summary,
   guards, keyboard/mobile readability, ledger, evidence workbench and history.
8. Full relevant regression/CI after the focused checks. Measure same-query
   before/after retrieval latency, request embedding calls, query count, memory,
   prompt size and context family distribution for 1/2/4 enabled families.
   Select and document a measured candidate acceptance envelope; no unsupported
   latency/SLA promise and no unbounded fan-out.
9. Normal-auth admin/viewer/researcher sessions on the candidate. Complete #101's
   actual permission/history/workflow checklist using an appropriately isolated
   disposable review fixture where real research is not yet approved. Record
   role-specific access and direct API denial checks, not just hidden buttons.
10. Live reported-query regression on exact-source candidate and production:
    relevant eDNA evidence is no longer lost to SST dominance when available;
    no-match/unverified cases explain the limitation without claiming absence.
    Neither returned source records nor citations alone count as scientific
    matching acceptance.

## Release and rollback

GCP/browser access is needed for live reproduction, candidate role acceptance,
build and rollout; refresh credentials when that phase requires it. Local
implementation/tests do not depend on cloud login. If account access is missing,
prepare the concrete candidate and identify the exact remaining check. Previous
release waivers do not waive new live acceptance automatically.

For the release build, recheck #104 against stable supported updates and current
primary advisories. Retain full unsuppressed reports and exact per-image
applicability/risk evidence; test runtime imports, non-root/privilege tooling,
NetCDF and isolated PostgreSQL backup/restore after any image changes. Keep
unresolved OS maintenance explicit rather than closing #104 from scan exit code.

Before migration, take a private fresh database backup and restore-test it in
isolation. Apply the reason-only migration with existing history/corpus hash
checks. Deploy exact source/digests at zero traffic with canonical authentication;
use normal invitation/role checks, never an auth bypass. Any required temporary
OAuth callback is prepared for the user's action-time approval and removed after
acceptance, together with task-owned QA routes/jobs/previews.

After candidate acceptance, publish/tag 0.7.1 at the exact tested source, promote
the verified production revision and check actual Chat/history/anonymous denial
and operational health. Align affected shared API/job images without executing
manual ingestion or research batches. Keep v0.7.0 rollback service/job definitions
and retain the additive reason constraint during application rollback; do not
erase new histories or restore production as a routine rollback.

Record source/image/CI/build identifiers, backup/migration receipts, per-role
acceptance, residual security dispositions and final cleanup in the patch
operations/release notes. Close #105 only after its production regression passes.
Close #101 only after its live checklist is complete; retain #102/#103/#89 and
any unresolved #104 work with honest progress and dependencies.
