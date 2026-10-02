# v0.6.1 scientific acceptance

Updated 2026-10-02 JST. **The bounded English scientific matrix is accepted.
Live viewer/researcher checks were explicitly user-deferred before publication
and production promotion.** Japanese-specific work/acceptance is separately
user-deferred. Issue [#70](https://github.com/jarondlk/ocean-platform/issues/70)
is closed after its agreed English cases passed. The earlier candidate sections
below preserve rejected attempts and their dated deployment states.

## First candidate and frozen data

Source `7e2d31235a75ecd79cdebb7b54c8cb75fd948811`, Cloud Build
`bc71a737-d1a4-4906-955f-448331cd79de`, revision
`ocean-platform-v061-patch1002` at zero traffic. Production retains v0.6.0.
Provider/model: Vertex / `gemini-3.6-flash`.

The operator checked schema head `20261001_0014` and retained publication IDs:

- eDNA: `a01a472a74ea55ffbd2cee1e69822555af801a00dbcf8956414a942564011716`.
- Canonical eDNA: `a6411a26f46c098769298d11dfcafbf2dd85a141dbe5ccbdfafb581acc8bdc46`.

QA used real validated `evidence_scope` envelopes. It changed no identities,
authentication settings, corpus publications or chat history. Exact aggregation
can retain immutable aggregate evidence in the production database.

## Deterministic phase

Execution `ocean-v061-acceptance-667ks` completed in 6m42s. All **48 runs**
(24 cases twice) passed route/outcome, citation and hash-verified numeric checks.
Manual review found one classification-boundary wording gap, addressed in the
follow-up. These results are attributed to the first candidate; the changed
path needs replacement-candidate verification.

| Cases | Reviewed disposition |
| --- | --- |
| Catalogue, physical identity | 3,498 source occurrences/assays; physical identity explicitly unresolved |
| Negative controls, unknown status | Requested 343 controls / 3,155 unknowns lead their answers; unknown is not environmental |
| Environmental-only | Zero recorded environmental occurrences is correct; initial answer needed an explicit explanation that unclassified records are excluded |
| Method reads, QC3NN assignments | 157,426,611 reads per alternative method / 174,819 QC3NN rows; methods remain separate |
| Empty tables, standards, concentrations | 83 valid empty tables per method; 13,932 standard rows / 442,404,272 reads; 3,246 missing concentrations / 323 absent source columns remain distinct |
| Projects | Ten project groups and 3,498 scoped occurrences; group counts match the immutable aggregate |
| Nontarget, future dates, nonexistent project | Zero matching records, no biological-absence inference or substituted global totals |
| Rare taxon and both production paraphrases | One occurrence, one assay, one assignment and 122 reads in the selected QCauto cohort |
| Polite summary/count, count paraphrase | Supported aggregate routes with the correct catalogue scope |
| Place/year, richness, compound control scope | Clarification without invented filters or widened counts |
| Arrival/freshness | Abstains with `freshness_unavailable`; collection dates do not establish arrival |

The clarification cases do not assert that every unsupported operation is now
supported. Exact aggregates remain catalogue records, not estimates of fish
abundance or distinct physical samples.

## Replacement deterministic phase

Source `5f68c34017827e042749ef87432022c750fd6b91`, successful Cloud Build
`a36d7ad7-5f0a-4ebb-ad5b-af9223a9dc7e`, revision
`ocean-platform-v061-patch1002b` at zero traffic. Execution
`ocean-v061-acceptance-nrcrz` completed successfully in 6m8s.

All **48 final runs** passed with the corrected runtime meter reporting **zero
actual generation calls**. Complete records were decoded and checked; both
environmental repeats now explain the exclusion of unclassified occurrences
without supplying a global unknown total under the filtered citation. These
are the only changed answer strings versus the first deterministic batch.
The other reviewed numeric/scope/wording results above are retained.

Individual case latencies ranged from 0 to 15,947 ms; these are operator-run
timings, not load-test percentiles. Schema and publication IDs remained the
frozen baseline. Anonymous candidate frontend-proxy requests to chat,
capabilities and filter choices returned 401. The final tagged chat URL again
ended at canonical production login; positive candidate UI/history acceptance
remains unverified.

## First model phase — stopped, not accepted

Execution `ocean-v061-acceptance-52k8d` stopped on the 14th answer, rare-taxon
lookup repeat 2, because it invented a `Scope` citation. Thirteen earlier
responses passed the runner's structural checks, which do not establish
claim-level correctness.

The first runner's generation meter wrapped a runtime instance that the API
did not use. Its reported zero calls is **invalid**. Fourteen model answers are
observed; no Vertex chat retry warning was found in the execution logs, but
actual attempt/token/cost accounting was not reliably captured. No additional
model run is authorized by treating that erroneous zero as remaining budget.

Six of the fourteen full evidence exports were truncated at 102,400 characters
in Cloud Run stdout entries. Their complete answer prefixes and available
documents were retained privately, but incomplete captures are not graded as
full evidence passes.

| Case | Completed / planned | Disposition |
| --- | --- | --- |
| Read count versus abundance | 3 / 3 | All full evidence exports truncated; core caution is visible, full review not accepted |
| Sum alternative method reads | 3 / 3 | Two exports truncated; complete repeat 2 incorrectly calls an explicitly unknown sample a field sample |
| Negative-control interpretation | 3 / 3 | One export truncated; core contamination caution is supported, but zero records/missing concentration and scope-citation wording need correction/review |
| Copies/mL and calibration | 3 / 3 | Captures complete; recorded calibration limitations are present; full acceptance requires review on revised prompt, including setting citations and missing-value distinctions |
| Rare-taxon evidence lookup | 2 / 3 | First answer has supported one/one/122 aggregate and recorded assay facts; second invents two `Scope` citations and fails the audit |
| Missing versus zero, method comparison, rare presence | 0 / 3 each | Not run after stop |
| CTD single sample | 0 / 3 | Not run after stop |
| Metagenome, satellite SST | 0 / 2 each | Not run after stop |

## Follow-up and remaining gate

[PR #87](https://github.com/jarondlk/ocean-platform/pull/87) adds the explicit
environmental filter boundary, preserves unknown sample classification and
empty-versus-missing distinctions in the prompt, and clarifies that source
selection settings do not need invented scientific citations.

The operator now binds `api.chat` generation to its metered concrete Vertex
runtime. An actual API regression checks that SDK invocations consume budget
and the next invocation is blocked at the cap. Large evidence is emitted in
bounded chunks with a compact result record and SHA-256 validation; tests
reject missing or corrupted chunks.

## Fresh model phase — complete captures, manual failures

The user authorized resolving QA and candidate access before publishing. Execution
`ocean-v061-acceptance-sw88n` on source `5f68c34017827e042749ef87432022c750fd6b91`
completed all 31 planned English generations in 4m44s. The corrected concrete
SDK meter recorded **31 actual attempts**, no retries or failed requests, 148,315
prompt tokens and 12,187 output tokens. All 31 full evidence captures passed
chunk/SHA-256 validation and the runner's structural checks.

Manual review nevertheless rejected the batch: abundance repeat 1 invented two
`[Scope Settings]` references that the old canonical-token audit did not recognize;
abundance repeat 3 called a source explicitly classified as unknown an environmental
sample. Numeric examples do not cure the incorrect classification. This batch is
**not a scientific acceptance pass**.

[PR #90](https://github.com/jarondlk/ocean-platform/pull/90) now rejects every
unrecognized generated citation token before returning or persisting an answer,
including multiword labels and mixed citation groups. Historical rendering/audit
semantics remain readable. A regression also checks that disabling the audit does
not bypass rejection and that a rejected answer is recorded as failed without a
saved answer. eDNA prompt headers now expose recorded classification/control status
literally, and methodological questions are instructed to lead with the direct
answer without incidental sample examples. These instructions require model QA;
they do not establish scientific correctness by themselves.

The corrective source merged as `26739772d2bebd9fcdaeccef440b382aa4632e34` after
all eight required CI checks passed. Cloud Build
`28706155-20bc-4f7c-90ce-b805fff0b5ce` succeeded. A new bounded English model batch
on these images remains pending, with 31 planned generations and a cap of 33 actual
SDK attempts. Manual claim-to-evidence review remains required.

## Citation-guard model phase — further manual findings

Execution `ocean-v061-acceptance-n9vfp` on source `2673977` completed 31 actual
SDK attempts in 4m22s, with no retries/failures and all complete hash-verified
captures/structural checks passing. Usage: 152,182 prompt tokens and 8,283 output
tokens. Individual request timings were 2,732–27,102 ms. Publication IDs/hashes
matched the frozen baseline. This batch is **not accepted** as a whole.

Manual review found abundance repeat 1 treating unknown calibration as absent
calibrated concentrations; method-comparison repeat 2 inferred algorithm and
shared extraction/PCR procedures not described by its citations. Metagenome
repeat 1 upgraded a month-only record/index placeholder to a precise collection
day. These are claim-support failures despite valid reference syntax.

[PR #91](https://github.com/jarondlk/ocean-platform/pull/91) merged as
`27e821cf7a0634aab1d744708788ff8f6efa8584` after all eight required checks passed.
It adds eDNA response bounds outside untrusted evidence, distinguishes labels
from algorithm/protocol descriptions, separates supplied copies/mL from verified
calibration, limits methodological answers to necessary supported caveats and
avoids treating citation aliases as sample IDs. Metagenome headers label index/
association dates and require the collection resolution actually recorded in the
evidence text. A month-only regression passes. Full local validation: 946 passed,
36 integration skips; required PostgreSQL CI passed separately.

All three CTD repetitions and two SST repetitions were reviewed against their
full selected source text: profile temperature/salinity/sigma-T and SST station/
regional values match, excluded sources stay excluded, and biological inference
is bounded. Their generation prompts are byte-identical across PR #91, so these
five results are retained. CTD gradient descriptions are interpretations of the
measured profile, not biological predictions. SST limits are general observation
limits, not evidence of species absence. The 26 affected eDNA/metagenome runs
will be repeated on the new immutable images, capped at 33 actual attempts.

## Candidate access and live acceptance progress

Candidate access is resolved with a separate zero-traffic QA revision using the
same immutable images/security configuration and the candidate origin as `AUTH_URL`.
The existing Google OAuth client received one exact, temporary callback after
explicit user approval. Normal Google sign-in and invitation/role checks remain
active; no roles, identities, IAM permissions or authentication bypass were added.
The temporary callback and QA route must be removed after acceptance.

On source `5f68c34017827e042749ef87432022c750fd6b91`, the real admin session passed
both count reproductions (one occurrence/assay/row and 122 reads), freshness
abstention, routing clarification and CTD future-date no-evidence abstention.
Two interpretation requests also produced ordinary persisted answers; one used an
empty eDNA aggregate, which is supplied evidence and is distinct from no evidence.
The independent read-only job `ocean-v061-acceptance-9kgtq` checked these seven
explicit interaction IDs: completed status, expected outcomes/reasons, same admin
ownership, scope/generation options, evidence fingerprint, prompt version/hash,
audit and timestamps. All passed; no history was written by the verification job.

Mobile testing at 390×844 found no root horizontal overflow, including the count
answer and long identifiers. Keyboard clear-selection/reset worked; all-disabled
survived reload, drafts did not, and reset restored all four sources/no filters.
Provider controls showed Vertex/model availability and omitted unsupported Ollama
controls. A native keyboard date edit confirmed the applied future date; browser
fill alone did not update the controlled date input.

Live viewer/researcher sign-ins remain pending account availability or explicit
user disposition. Existing isolated role/account/PostgreSQL fixtures are retained,
but they are not relabelled as live role acceptance. A normal CTD answer on `2673977` matched its source values and had three valid
citations; citation inspection loaded the correct source, sample and provenance
trace, and Escape dismissed it. Read-only execution
`ocean-v061-acceptance-jlkz7` verified all eight new IDs and one retained same-owner
answer from each v0.5.0/v0.6.0 date window. Both old snapshot hashes passed, and
the retained v0.5.0 aggregate payload still matches its immutable ID. Retained
aggregate UI/download checks and final scientific review remain pending.

Private raw captures/operator outputs remain outside Git under
`/tmp/ocean-v061-release`. Dollar cost and load percentiles are unavailable;
single-job/case timings do not establish production p95 or load performance.

## Response-bounds batch — completed, not accepted

Execution `ocean-v061-acceptance-hzjd5` on source `27e821c` completed all 26
affected eDNA/metagenome repetitions in 3m52s. Actual SDK calls: 26, with no
retries/failures; usage: 147,748 prompt tokens and 5,063 output tokens. All
26 complete captures passed chunk/hash validation and structural checks.

Manual review rejected these consequential claims:

| Case | Finding |
| --- | --- |
| Sum alternative reads, repeat 1 | Asserted records represented the same physical sample; physical linkage remains unresolved |
| Copies/mL, repeat 3 | Grouped copies/mL with sequencing output and said they were not concentration; reported DNA concentration and sequencing counts are distinct |
| Method comparison, repeat 2 | Inferred algorithm/database behavior and identical sample-run relationships not described in citations |
| Missing versus zero, repeat 2 | Treated a conditional missing-value warning as a causal explanation of unknown calibration for empty tables |
| Metagenome, repeat 1 | Called unsupplied pre-computed diversity analyses deliberately excluded by settings; the request did not disable them |

Rare-taxon lookup/presence repetitions retained the correct one occurrence, one
assignment and 122 reads; assay-level totals remained separate, with unknown
classification/control and calibration caveats. The month-only metagenome
collection date was correctly preserved in both repetitions. These successes
do not accept the failed batch.

[PR #92](https://github.com/jarondlk/ocean-platform/pull/92) merged as
`009ab8e97052f5d5bb2e958630d0371561792c5c` after all eight required checks passed.
Trusted eDNA bounds now distinguish concentration/read metrics, unresolved
physical linkage and conditional missing-value statements; explanations of
method agreement cannot invent procedural relationships. Metagenome bounds
distinguish unsupplied analyses from disabled settings. Local suite: 946 passed,
36 integration skips; PostgreSQL CI passed. All five retained CTD/SST prompts
remain byte-identical. A new immutable build and 26 affected repetitions remain
pending. No scientific quality pass or release promotion is claimed.

The final `27e821c` candidate also passed a normal authenticated admin eDNA
interpretation request with valid citations and unknown calibration preserved.
Its specified interaction passed independent read-only readback in
`ocean-v061-acceptance-rtjt5`: completed answer, expected eDNA-only scope,
provider-effective controls, evidence fingerprint, prompt hash and valid audit.
Nine candidate UI interactions have now passed this verification. Preferences
were restored to all four sources/no filters. A retained v0.5.0 aggregate was
downloaded through the ordinary chat citation panel; its JSON payload still
hashes to `50d5f2a1545e8e5a789bcfc691ca2ffe5b34a105e1e405d89ebade9982319606`.

## Metric/identity batch and final citation-role correction

Source `009ab8e` execution `ocean-v061-acceptance-ftbrz` retained 23 complete
hash-verified cases, then stopped after its 24th actual SDK call: rare-presence
repeat 3 contained an unrecognized citation. The API rejected it with
`llm_invalid_citation`; no answer or chat history was persisted by this operator.
The rejected raw answer was not captured and its exact token is unknown.

Execution `ocean-v061-acceptance-9qs95` used the remaining batch allowance for
one rare-presence retry and two unrun metagenome repetitions. It completed
three actual calls in 52 seconds with complete captures. Combined calls: 27,
including the rejected generation, within the original 33-attempt cap. The
rejection remains part of the outcome record; the successful retry does not
make the original execution a clean pass or guarantee error-free generation.

Manual review accepted the 18 methodological answers: reads versus abundance,
separate alternative assignments, controls, DNA concentration/calibration,
missing versus zero and method agreement. Answers retained unknown statuses
and avoided unsupported algorithm/protocol definitions. General references to
alternative outputs for the same provider sample describe assignment reuse,
not verified linkage of distinct physical samples. The two metagenome answers
match all supplied values and monthly resolution; unavailable diversity indices
remain unavailable. Their taxonomic summaries describe assigned reads, not
absolute organisms or ecological dynamics.

Rare-lookup repeat 2 cited the aggregate for 12S rRNA/MiSeq details present only
in its assay evidence. The facts are present in the prompt, but that attached
citation does not support them, so rare-taxon acceptance remains incomplete.
[PR #93](https://github.com/jarondlk/ocean-platform/pull/93) merged as
`fd7dd4175eebb87b20450fe67d2bfac1cff3f8a2` after all eight required CI checks
passed. Its conditional prompt section separates aggregate counts from assay
metadata and requires both citations for combined claims. Local tests: 947
passed, 36 integration skips; PostgreSQL CI passed. Prompt comparisons confirm
25 reviewed results remain byte-identical (18 methods, two metagenome, three
CTD, two SST); only six rare-taxon repetitions need another run. That exact
source build and six-case manual review remain pending.

The final `009ab8e` browser concentration answer preserved DNA concentration
versus sequencing counts and unknown calibration, with valid citations. Its
specified saved record passed read-only verification in
`ocean-v061-acceptance-g2tdc`; ten live candidate interactions now passed
independent scope/generation/fingerprint/prompt/audit readback. All-source
default preferences were restored afterward.

## Final English scientific disposition

Source `fd7dd4175eebb87b20450fe67d2bfac1cff3f8a2`, successful Cloud Build
`2415f393-6608-4f91-988a-324ce2640d1c`, Ready zero-traffic canonical revision
`ocean-platform-v061-assay1002` and equivalent QA-origin revision
`ocean-platform-v061-assayqa1002`. Execution `ocean-v061-acceptance-5mtgn`
completed all six changed rare-taxon repetitions in 2m42s: six actual SDK calls,
no retries/failures, 21,294 prompt tokens and 1,069 output tokens. Every complete
capture passed chunk/hash validation; all structural checks and manual
claim-to-evidence reviews passed. Case timings: 22,367–28,019 ms, principally
retrieval/aggregate work; these are individual operator timings, not load-test
percentiles. Actual billed cost is unavailable.

| Family | Successful reviewed repetitions | Final disposition |
| --- | --- | --- |
| Read counts versus abundance | 3 retained | Sequencing counts do not establish fish/organism abundance; calibration remains unknown |
| Alternative method read sums | 3 retained | Separate assignment outputs are not summed as independent abundance |
| Negative controls | 3 retained | Control/standard presence does not prove contamination-free samples |
| Copies/mL | 3 retained | Reported DNA concentration differs from read/organism counts and verified calibration |
| Missing versus zero | 3 retained | Missing/empty records do not establish zero concentration or biological absence |
| Method comparison | 3 retained | Agreement is not independent validation; no invented algorithms/protocols |
| Rare-taxon lookup | 3 final-source | One occurrence/assignment and 122 reads; aggregate supports counts, assay supports gene/platform/time, combined claims cite both |
| Rare-taxon presence | 3 final-source | Correct scoped detection counts and sequencing-versus-abundance distinction |
| CTD single sample | 3 retained | Selected measured profile values match; no unsupported biological prediction |
| Metagenome sample | 2 retained | Supplied percentages/yield and month precision match; unsupplied diversity indices stay unavailable |
| SST narrow scope | 2 retained | Station/regional source values match; observation limits stay explicit |

Total: **31 manually reviewed successful model responses**, six rerun on final
source and 25 retained after byte-identical prompt comparisons. The 48 reviewed
deterministic runs are retained; aggregation/parser behavior and frozen
publication generations/hashes are unchanged by these prompt-only corrections.
Earlier failed captures/claim dispositions and the one correctly rejected
citation remain recorded above. This bounded acceptance does not guarantee
scientific correctness for arbitrary questions or eliminate guarded generation
errors that require the user to retry.

Normal final-source browser QA also confirmed the original selected QCauto/
Ablabys count reproduction: one source occurrence, one assay, one assignment
row and 122 reads, model not invoked, seven valid citations/no warnings.
Candidate authentication remains required (anonymous chat/capabilities/filter
requests return 401). Admin settings/preferences were restored afterward.
Live viewer/researcher account availability or an explicit user deferral remains
the release gate; isolated role/account/storage and API-level no-source history
fixtures passed. Japanese work/acceptance remains user-deferred.
