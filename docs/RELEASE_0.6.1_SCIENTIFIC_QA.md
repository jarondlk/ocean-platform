# v0.6.1 scientific acceptance

Updated 2026-10-02 JST. **Acceptance is incomplete; no scientific quality pass
or release promotion is claimed.** Japanese-specific work/acceptance is deferred
by the user. Issue [#70](https://github.com/jarondlk/ocean-platform/issues/70)
remains open.

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

A fresh English matrix remains pending explicit authorization for another
batch capped at 33 actual provider attempts. It must capture complete evidence,
actual retries/usage and case timings, then receive manual claim-to-citation
review. The previous batch's structural results, partial captures and corrected
instructions cannot be relabelled as that pass.

Live authenticated candidate role/UI/history and mobile checks remain separate
gates. Local role fixtures and independent PostgreSQL record tests passed, but
the candidate tag redirects to canonical production login, live viewer/researcher
sessions are unavailable, and the in-app mobile viewport control timed out.

Private raw captures/operator outputs remain outside Git under
`/tmp/ocean-v061-release`. Dollar cost and load percentiles are unavailable;
single-job/case timings do not establish production p95 or load performance.
