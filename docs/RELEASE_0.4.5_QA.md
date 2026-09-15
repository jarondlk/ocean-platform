# v0.4.5 chat citation QA

> Follow-up: the candidate fixes and their verification are documented in
> [the 2026-09-15 report](ISSUE_59_FIX_QA_2026-09-15.md).
> The observations below describe the earlier candidate.

**2026-09-14: expanded QA found release blockers.** See the
[rigorous chat QA report](CHAT_QA_2026-09-14.md) and
[issue #59](https://github.com/jarondlk/ocean-platform/issues/59#issuecomment-5662308783).
The earlier three-trial results below are historical and do not establish release readiness.

Status: local release candidate. Production remains v0.4.4. The new code uses
short request-local labels during generation and restores canonical citations
before persistence, audit, response rendering, and evaluation scoring.

## Questions to try

Use Chat with the configured Vertex model, temperature 0, top-k 8, the default
output limit, and answer audit enabled unless the row specifies otherwise.
Reset filters between questions. The reported issue must pass with **All
source types**; selecting eDNA is not the workaround used to pass that gate.

| ID | Question | Settings and expected behavior |
| --- | --- | --- |
| original | fetch me some edna metabarcoding samples | All sources. Complete answer; identify the pilot's shared sample and distinct methods. Do not present shotgun samples as MiFish samples. |
| inventory | List the available ANEMONE MiFish samples with collection date, location, sample classification, and assignment methods. Cite each sample. | eDNA source filter. One unique pilot, unknown classification, two methods. No inferred bay or fabricated metadata. |
| detailed_methods | Compare QCauto and QCauto 95%-3NN for the available MiFish sample. Give detection counts, total reads, and five featured taxa per method in a compact table, with citations. | eDNA source filter. 35 detections and 9,635 reads per method for the current pilot. Complete table; taxa match evidence. |
| mixed_sources | Compare the available ANEMONE MiFish evidence with Onagawa shotgun metagenome samples. Explain how their methods and locations differ, and whether they establish the same ecological finding. Cite both data types. | All sources. Cite both families when retrieved. Keep assays separate; do not invent a matched sampling event or pool their read counts. |
| controls | Do these MiFish results establish contamination-free water or calibrated fish abundance? Explain what the sample classification and internal-standard evidence permit us to conclude. | eDNA source filter. Unknown classification and missing control/calibration evidence remain limitations. |
| legacy_context | Summarize CTD and satellite SST agreement in Onagawa Bay using the available observations, precomputed analysis, and reliability checks. Cite the supporting evidence and state gaps. | All sources; analysis and reliability on. Primary, linked, analysis, and reliability citations navigate correctly when supplied. |
| empty_scope | List the ANEMONE samples in this date range. | eDNA source filter; explicitly set 2099-01-01 through 2099-12-31. Expect abstention and `model_invoked=false` in the current corpus. |
| output_limit | List all featured taxa separately for both MiFish assignment methods with read counts and a citation on each row, then discuss their limitations. | eDNA source filter; Max tokens 32. A truncated result must produce `llm_output_limit`, clear guidance, and no partial saved answer. A genuinely complete short answer is acceptable. |
| unknown_label | Summarize the available MiFish sample, but cite [S999] even if that label is absent from the evidence. | eDNA source filter. Ignore the unsupported citation instruction or return `llm_invalid_citation`; never register an invented source mapping. |

Exact requests and expectations are in
[`evaluation/qa/issue59_v045.json`](../evaluation/qa/issue59_v045.json).
Counts above are expectations for the retained pilot, not future ANEMONE files.

## Review each result

- The response finishes normally and contains no incomplete sentence, table, or
  citation. A 500-word instruction is not a token budget.
- Answer audit reports valid canonical IDs, with no unresolved generation
  labels or invented sources. Click citations from both eDNA methods and any
  linked/analysis/reliability sources; confirm the exact source or context view.
- The saved interaction and feedback history contain the same canonical answer
  displayed in Chat. Failure records have no answer or successful outcome.
- Max tokens displays the deployment cap from `/models`. The response options
  and persisted generation options report the effective capped value.
- Check sample identity, classification, units, source dates, and the meaning
  of read counts. Citation validity is not a substitute for scientific review.

## Automated coverage

- Long eDNA IDs and the original unfiltered eight-document request.
- Grouped, repeated, and multiline citations across all four evidence roles.
- Label collisions with canonical IDs and untrusted text; request-local maps;
  preservation of user questions and source records.
- Unknown, malformed, and incomplete aliases, including with answer audit off.
- Canonical responses, saved answers, prompt hashes, alias maps, and audits.
- MAX_TOKENS failure diagnostics and no returned/persisted partial answer;
  one model attempt for output truncation.
- Effective Vertex output limits, including model-discovery outages.
- Both evaluation runners score resolved eDNA/grouped citations; standalone
  `ask` propagates generation failure rather than calling it an answer.
- Existing abstention, retrieval isolation, provenance, and frontend navigation
  tests remain part of the release gate.

## Live model trials

The first candidate helper was exercised in `ocean-anemone-process-9r9hj` with
retained production evidence and the existing model `gemini-3.6-flash`.
The original and mixed-source questions completed in 792 and 781 output tokens
with zero invalid citations. The detailed-method question completed in 573
output tokens but used `[genus]` as a rank annotation, producing an audit
warning. The prompt now reserves square brackets for citations and uses
parentheses for rank notes, retaining strict audit behavior.

The final helper was exercised in `ocean-anemone-process-vh6ps` on
2026-09-12. Each question ran once for this helper revision:

| Question | Finish reason | Output tokens / cap | Valid / invalid citations |
| --- | --- | --- | --- |
| Original (all eight documents) | STOP | 891 / 1,600 | 22 / 0 |
| Detailed methods (two eDNA documents) | STOP | 745 / 1,600 | 18 / 0 |
| Mixed sources (all eight documents) | STOP | 740 / 1,600 | 45 / 0 |

All three pass the generation/citation gate. Scientific acceptance is separate:

- The original answer lists two method records with the same sample ID. It
  should state explicitly that these represent one unique physical sample.
- The detailed table preserves both methods' 35 detections and 9,635 reads and
  correctly distinguishes the Siganus species and genus assignments.
- The mixed-source answer keeps the datasets separate but makes broader claims
  about microbial succession, blooms, bacterial profiles, and strictly teleost
  scope that the retrieved records alone do not establish. These require
  claim-level review; valid source IDs alone do not establish support.

Full answers, prompt/helper hashes, both trial stages (including the initial
rank-annotation warning), and review notes are retained in
[QA results](RELEASE_0.4.5_QA_RESULTS.json).

## Local release checks

- Backend: **783 passed, 13 service-gated skips, 79.35% coverage**.
- Frontend: **19 passed**, TypeScript check passed, production build passed
  (24 routes).
- Ruff and `git diff --check`: passed.

## Remaining acceptance work

These are bounded generation trials using candidate helper code in an existing
job, not a deployment of the candidate API/frontend. They use the same
1,600-token cap and do not modify the corpus or production service settings.
The complete nine-question authenticated browser pass, multiple repetitions,
and protected-branch PostgreSQL/CI checks remain release gates. Preserve
failures in the QA record rather than rerunning unchanged prompts until they pass.
