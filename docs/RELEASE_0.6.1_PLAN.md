# v0.6.1 — Chat settings patch and acceptance completion

Prepared 2026-10-02 JST against `gcp-dev` / `main` commit
`e6244b7b4dbd0247c00c699078fee394549f51e8`.

**Status: implementation in progress; release pending.**

On 2026-10-02 the user authorized implementation and explicitly deferred
Japanese-specific work and acceptance checks. Existing Japanese support and
regressions remain in place; English acceptance gates below still apply. The user asked
for the remaining v0.6.0 work to be planned under **v0.6.1**. This document is
the patch work queue. Application/package versions and published Git tags stay
at their existing values until the patch candidate is prepared and validated.

## Starting point and retained evidence

The [v0.6.0 operations record](RELEASE_0.6.0_OPERATIONS.md) records the deployed
security amendment `6fd37eb`, revision `ocean-platform-v060-sec1001`, additive
schema head `20261001_0014` and compatible application rollback. The v0.6.0
source tag remains `91d8567`; the runtime amendment is separately recorded.
Those are dated deployment facts, to be refreshed when patch deployment begins.

The [production browser QA](RELEASE_0.6.0_BROWSER_QA_2026-10-01.md) subsequently
verified current-admin sign-in, live source choices, reload/reset, empty
selection, CTD cascading, representative scoped answers, freshness safeguards,
aggregate downloads and provenance. The browser connection worked in a fresh
production tab. It also reproduced two count-question routing failures.

All 16 source combinations and canonical filter/count membership already passed
v0.6.0 runtime checks. Backend, frontend, PostgreSQL integration, dependency and
CodeQL gates passed. These establish the baseline; new changes need relevant
regression checks, and earlier results do not prove the untested account or
scientific acceptance cases.

## Target behavior and scope

A supported exact-count question uses the explicit source filters already
selected, regardless of ordinary phrasing. The answer leads with the requested
metric and cites an immutable aggregate for that same cohort. A genuinely
unsupported qualifier receives a precise explanation without silently widening
scope. Scientific interpretation continues through evidence retrieval rather
than being confused with record counting.

Complete the remaining settings/account/UI/history acceptance checks and the
bounded issue #70 scientific matrix. Fix any reproducible defect exposed by
those checks within this patch; record larger unrelated work separately.

No cross-device settings synchronization, presets, multi-turn conversation UI,
new source acquisition, environmental reclassification, per-source ranking
quotas, corpus reimport or embedding refresh is included. No new schema change
is expected. If a discovered fix needs one, add its migration/compatibility and
backup plan before including it in the candidate.

## Ordered work packages

| ID | Priority | Deliverable | Completion evidence |
| --- | --- | --- | --- |
| V061-01 | First | Repair exact-count phrasing and clarification | Both production reproductions and supported English variants return the scoped aggregate; unsafe/unresolved requests still fail closed |
| V061-02 | Next | Verify settings lifecycle and account boundaries; fix defects found | Reload/navigation/reset, account transitions, storage failures and transient analysis links pass without silent scope expansion |
| V061-03 | Next | Complete UI/access and persisted-history checks | Role-appropriate controls, keyboard/mobile behavior and independent record readback pass; historical citations stay readable |
| V061-04 | After routing fix | Repeat scientific-answer acceptance | Tracked questions have claim-level reviewed outcomes against the frozen catalogue, with repeated model cases and explicit remaining limits |
| V061-05 | Before release | Prepare and validate the patch candidate | Exact candidate passes local/remote gates, version metadata is 0.6.1, QA and release notes agree |
| V061-06 | Last | Publish and deploy the validated patch | v0.6.1 pins the validated source, immutable GCP images are recorded, post-cutover checks pass and operating docs are current |

### V061-01 — Exact-count routing

Start in `orchestration/edna_aggregation.py`, the `/chat` integration in
`api/main.py`, `tests/test_edna_aggregation.py` and
`tests/test_chat_source_scope.py`.

Reproduce with only eDNA enabled and filters
`assignment_method=qcauto_target`, `taxon=Ablabys taenianotus`:

1. “For the selected Ablabys taenianotus and QCauto scope, how many source
   occurrences, assays, assignment rows and sequencing reads are supported?”
2. “How many ANEMONE source occurrences contain Ablabys taenianotus under
   qcauto_target, and how many reads support that assignment?”

Both currently return “Exact count needs explicit filters” despite the applied
filter table confirming that scope. The presence question succeeds with the
same cohort. The bounded parser rejects unfamiliar wording; the patch must
separate unsupported wording from absent/conflicting scope.

- Add the two reproductions as failing route/API regressions before editing.
- Support a bounded set of count/presence paraphrases, literal selected filter
  values and method aliases. Cover case and punctuation. Derive database predicates from validated controls, not arbitrary
  natural-language guesses or an LLM-generated SQL statement.
- Resolve aliases without stripping qualifiers that change the meaning. In
  particular, “QCauto” must not override a selected QCauto+3-NN method, and a
  different free-text taxon/place/date must not be silently ignored.
- Keep exact counts separate from abundance, calibration, freshness and
  physical-sample interpretation. Explain the actual unsupported qualifier or
  conflict when clarification is necessary; do not ask for filters already set.
- Preserve historical aggregate IDs/hashes and citation/download semantics.
  Existing stored response/reason values remain readable. Prefer the existing
  reason contract; any new persisted reason needs explicit migration coverage.

Expected cohort result: **1 source occurrence, 1 assay, 1 assignment row,
122 sequencing reads**. Physical sample identity is unresolved; reads do not
establish organism abundance. Tests must also cover contradictory filters,
unfiltered named places/years, unsupported species richness, empty cohorts,
disabled eDNA, mixed-source ambiguity and interpretation questions containing
“count” or “reads”. No fallback may substitute whole-catalogue totals.

### V061-02 — Settings lifecycle and account isolation

Review `frontend/lib/use-chat-settings.ts`, `chat-settings.ts`,
`ChatIdentityProvider.tsx`, `ChatSourceSettings.tsx` and `ChatFilterSelect.tsx`.
Extend focused component/hook tests where current pure serialization tests
cannot exercise actual hydration or identity transitions.

- Account A's settings never appear or persist under account B. Block submission
  while identity/settings hydration is unresolved, and clear stale notices/state
  during a transition. An inaccessible account cannot reuse an earlier scope.
- Reload, route navigation and reset preserve the intended account-specific
  scope. All-disabled remains all-disabled; question/answer drafts remain out
  of saved settings.
- Denied reads/writes leave a valid session usable with an honest unsaved-state
  notice. Malformed or obsolete scientific settings require review/reset rather
  than silently selecting all sources. Test these with isolated fixtures, not
  by corrupting a real user's stored preferences.
- Transient analysis links stay transient and respect source selection,
  membership/method constraints and conflicting filters.
- Choice search, cascading and rapid changes cannot replace current options
  with a stale response. Unavailable saved choices remain visible for review;
  loading and empty-data states remain distinct.

### V061-03 — UI/access and history

Use existing designated test accounts for viewer, researcher and admin. Do not
change real users' roles, invite users or weaken authentication to manufacture
coverage. If a required account/session is unavailable, record that case as
blocked and arrange user sign-in when that phase executes; an admin pass does
not count as a viewer/researcher pass.

- Verify source/filter and model controls through each role's normal capability
  boundary. Check suspended/uninvited accounts in isolated auth fixtures; live
  cases require an existing suitable test identity.
- Exercise keyboard-only source selection, disclosures, dropdown/search and
  reset; focus and validation messages must be understandable. Check a narrow
  mobile viewport for overflow/usable inputs, and English labels and
  status/error messages. Restore the original preferences after QA.
- Create clearly recorded test interactions using normal authenticated chat.
  Independently read back the stored outcome, abstention reason, applied scope,
  provider-effective settings, evidence snapshot and answer/citation audit.
  Include an answered request, freshness abstention, routing clarification,
  no-evidence result and API-level no-source request.
- The admin Feedback page lists rated responses, so loading old feedback alone
  cannot establish persistence of newly created unrated interactions. Use the
  existing test/API/database access path for bounded readback. Do not submit
  invented feedback merely to make QA records appear in that page.
- Verify retained v0.5.0/v0.6.0 answers, aggregate downloads and provenance after
  the patch. Do not delete earlier history or republish historical evidence.

### V061-04 — Scientific-answer acceptance

Create a v0.6.1 request matrix based on
`evaluation/qa/anemone_v050_questions.json`, the issue #70 question-quality
records and the two browser reproductions. Supply actual `evidence_scope`
settings; do not relabel historical FTS-only results as current hybrid/model QA.

| Case family | Required review |
| --- | --- |
| Scoped rare taxon and paraphrases | Correct one/one/one/122 cohort; canonical support even when the taxon is absent from top-ten assay prose |
| Catalogue/control/unknown/environmental counts | 3,498 source occurrences/assays, 343 explicit controls, 3,155 unknowns, zero explicitly environmental; counts are qualified and scoped |
| Physical samples and requested metric focus | Lead with unresolved physical identity when applicable; lead numeric answers with the requested value |
| Alternative methods, read sums and standards | Do not sum shared sequence evidence as independent abundance; controls/standards do not prove contamination-free or calibrated samples |
| Missing versus zero and empty versus unavailable | State the recorded distinction; absence from selected evidence does not prove biological absence |
| Arrival/freshness in English | Collection dates cannot establish arrival or continuous provider synchronization |
| CTD/metagenome/SST scoped interpretation | Numeric facts match supplied records; ecological predictions need explicit supporting evidence; no excluded-source context/citation enters the answer |
| Unsupported/conflicting scope | Honest clarification, no widened cohort and no unsupported scientific claim |

Run deterministic count/clarification cases twice. Repeat seven existing
model-interpretation/lookup cases and an English rare-taxon presence case three
times each, add three single-sample CTD runs and two narrow-scope runs each for
metagenome and SST: **31 planned generations, with a first-batch cap of 33** including
retries. Count actual provider invocations, not merely submitted questions.
Reuse earlier valid evidence until a changed path warrants retesting. Stop and
record an unexpected failure or cost increase before widening the batch.

Manually map each consequential claim to its supplied citation/evidence. Grade
numeric support, scope, methods, units, scientific caveats and answer focus;
valid citation syntax alone is insufficient. Capture candidate/source/model,
publication generations, outcomes, request latency, retrieval/aggregate latency
and token/cost information where exposed. Report unavailable measurements as
unavailable and individual timings as individual timings, not p95/load claims.

A tracked claim-support failure must be fixed and rerun or given an explicit
open disposition. Close issue #70 only when its agreed cases pass; do not infer
general scientific correctness from this bounded matrix.

### V061-05 — Candidate and documentation

- Use a `codex/v061-…` implementation branch based on refreshed `main`; retain
  `gcp-dev` as the development branch and avoid unrelated source changes.
- Run focused routing/settings/history tests while implementing. For the final
  exact candidate, run full backend/coverage and lint, PostgreSQL 16 migration
  and integration, generated-contract checks, frontend tests/typecheck/build,
  dependency consistency/audit and remote CodeQL/CI. Broaden testing only for
  new changes, failures or unresolved concerns.
- Bump API and frontend package/lock metadata to `0.6.1` when preparing the
  candidate. Check the retained schema head and migration compatibility.
- Produce `RELEASE_0.6.1_IMPLEMENTATION.md`, `RELEASE_NOTES_0.6.1.md` and
  `RELEASE_0.6.1_OPERATIONS.md`, including a case-by-case QA disposition and
  exact source/images. Keep private account details, raw browser captures and
  credentials outside Git. Update README, roadmap, handoff and doc register.

### V061-06 — GitHub release and manual GCP rollout

1. Refresh live revisions, schema/publication generations, serving/job images,
   authentication, resource/spend settings and recent errors. Use recorded
   v0.6.0 resources as a baseline, not stale rendered templates.
2. Review and merge the patch through a PR after all required source/CI checks
   pass. Record the exact merged source for the candidate build; keep the release
   tag pending until candidate acceptance below is complete.
3. Build immutable API/frontend images from the exact source archive. Prepare a
   zero-traffic candidate with existing identities, authentication, secrets,
   read-only serving mounts and resource limits. Review any additional job/access
   requirement as a concrete bounded operation when needed.
4. Perform candidate UI/history/source and bounded scientific QA. A zero-traffic
   candidate sharing production storage still writes real chat history and
   aggregate artifacts; record those effects. Use isolated fixtures for destructive
   failure/storage/account tests. Take/verify a fresh backup before any schema
   or publication mutation; this patch is expected to need neither.
5. After candidate acceptance passes, create immutable Git tag **`v0.6.1`** on
   the exact merged/built source and publish its GitHub release. Distinguish source
   publication from GCP deployment until traffic changes. A fix after acceptance
   requires a new source/build and relevant revalidation before tagging.
6. Promote the verified revision, retain the compatible v0.6.0 rollback route
   and existing expanded history constraint, verify production routing/login/
   access protections and error logs, and record immutable digests. Align the
   five manual job images only where their runtime code changed, preserving
   commands/identities/limits; do not execute ingestion or embedding jobs for QA.
7. Update the release/deployment record and operating docs with actual results,
   synchronize development/integration branches, remove temporary QA resources
   and preview routes, restore test preferences and leave the workspace clean.

The v0.6.0 decision to defer QA was specific to that rollout. The v0.6.1 plan
requires its listed acceptance gates to pass; any new deferral must be explicitly
recorded and authorized, rather than inherited silently. Planning this patch
does not itself claim implementation, a Git release tag or a production update.

## Patch completion checklist

- [x] V061-01: both count reproductions fixed with scoped regression coverage.
- [ ] V061-02: settings/account/storage lifecycle verified; defects resolved.
- [ ] V061-03: role/UI and new-history readback checks completed.
- [ ] V061-04: bounded scientific matrix reviewed with every failure disposed.
- [ ] V061-05: 0.6.1 exact candidate and required CI/security checks passed.
- [ ] V061-06: GitHub tag/release, verified GCP rollout and records completed.
