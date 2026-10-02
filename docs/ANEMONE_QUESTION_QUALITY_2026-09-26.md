# ANEMONE question and citation quality review — 2026-09-26

**Dated local QA record.** Subsequent staging and production model tests are in
the [v0.5.0 operations record](RELEASE_0.5.0_OPERATIONS.md). Production deployed
on 2026-09-30, and [issue #70](https://github.com/jarondlk/ocean-platform/issues/70)
tracks the remaining scoped answer-quality failures. The local results and
pending statements below reflect the 2026-09-26 test conditions.

Tested the current **local `gcp-dev` candidate**, not the deployed 0.4.5 service. The corpus is the 2026-09-17 ANEMONE observation. Application behavior was not changed during this QA; only the question set, runner and report were added.

## Findings

**The exact-count evidence is sound, but natural-language handling and response focus still need work. Ordinary model-assisted QA is not complete.**

- 30 realistic questions prepared; 22 exercised the aggregate/clarification route.
- 17 returned answers with expected numbers. All 17 had valid citations, no audit warnings, matching provenance/export payloads and verified content hashes (9 distinct aggregate citations).
- 2 appropriately requested scope/capability clarification: an unfiltered place/year and unsupported species richness.
- 1 compound control comparison hit a documented capability limit.
- 2 exposed routing failures, below.
- The other 8 were checked with real full-text retrieval; all returned zero documents. Their full-text-only chat responses abstained rather than inventing answers. This is diagnostic fallback testing, **not** a live-model or full hybrid retrieval pass.
- Candidate embedding coverage is 0/6,996. GCP sign-in also needs renewal before the live Vertex phase. No model-generated answers were graded in this run.

## Confirmed issues

1. **Ordinary paraphrase rejected.** “Can you summarize the ANEMONE database?” returns a scope clarification even though the whole-catalogue scope is clear. “Give a summary of ANEMONE data” works. The literal vocabulary rejects “you”.
2. **Scientific interpretation mistaken for counting.** “Does a higher ANEMONE read count mean there are more fish?” is captured by the word “count” and receives the generic scope refusal. It should explain the interpretation limits using evidence.
3. **Answers are poorly focused.** Most successful questions receive the same complete catalogue template. A request for unknown-control counts leads with 3,498 total occurrences before giving the requested 3,155. Reads, standards and empty-table answers similarly bury their requested value. Physical-sample questions should lead with “unresolved”.
4. **Classification-zero explanation needs context.** The environmental-only response correctly says zero *explicitly classified* occurrences, but its filtered table also says zero unknowns. It should explicitly explain that unclassified records were excluded, with separately scoped evidence for any unfiltered counts.
5. **Ordinary retrieval is not ready locally.** With no embeddings, the eight realistic interpretation/lookup queries found no FTS evidence. Even the explicitly filtered rare-taxon lookup returned no sources, while the exact aggregate and archived source row prove a matching detection exists. Do not treat this as an LLM reasoning failure; retrieval supplied nothing.
6. **Japanese coverage remains unverified.** The Japanese count question does not enter the English-oriented aggregate route without an explicit eDNA scope, and its FTS-only fallback finds nothing. It needs a routing/language regression case and live evaluation.

## Citation assessment

Checks went beyond counting bracket tokens: each cited aggregate resolved through the provenance API; its downloadable JSON had the expected SHA-256 identity; trace metadata equaled the exported payload; scoped numeric metrics matched frozen expectations. Separate SQL reconciled method rows/read totals and classifications. For *Ablabys taenianotus*, the original compressed community TSV hash matched the registered source file, and source row **88** contained the named taxon with **122 reads**, matching the scoped result.

No broken or invented aggregate citations were found. The aggregate citation is a reproducible query-level source, not a direct per-row link for every contributing observation. The JSON retains publication IDs, scope and input fingerprints. Scientific caveats are not independently peer reviewed by the citation audit. Live generated claims and their individual supporting citations remain to be assessed.

## Questions to try and observed behavior

Questions marked with explicit filters must be sent with the corresponding API settings; plain text alone is intentionally not used to infer taxon/date/project scope. The complete requests are in [the question matrix](../evaluation/qa/anemone_v050_questions.json).

| ID | Question | Scope/settings | Result |
| --- | --- | --- | --- |
| catalogue | How many ANEMONE samples and assays are available? | None | Numbers/citations pass; focus needs review |
| physical | How many physical samples are included in ANEMONE? | None | Numbers/citations pass; focus needs review |
| negative_controls | How many ANEMONE negative controls are there? | None | Numbers/citations pass; focus needs review |
| unknown | How many ANEMONE samples have unknown control status? | None | Numbers/citations pass; focus needs review |
| environmental | How many ANEMONE environmental samples are available? | None | Numbers/citations pass; focus needs review |
| method_reads | How many ANEMONE reads are available per method? | None | Numbers/citations pass; focus needs review |
| qc3nn | How many ANEMONE QCauto+3-NN assignment rows are available? | None | Numbers/citations pass; focus needs review |
| empty_tables | How many ANEMONE community tables are empty? | None | Numbers/citations pass; focus needs review |
| standards | How many ANEMONE internal standard reads are available? | None | Numbers/citations pass; focus needs review |
| concentrations | How many ANEMONE concentrations are missing or unavailable? | None | Numbers/citations pass; focus needs review |
| projects | How many ANEMONE samples are available by project? | None | Numbers/citations pass; focus needs review |
| nontarget | How many ANEMONE nontarget reads are available? | None | Numbers/citations pass; focus needs review |
| rare_taxon | How many ANEMONE samples of Ablabys taenianotus are available? | {"taxon": "Ablabys taenianotus", "assignment_method": "qcauto_target"} | Numbers/citations pass; focus needs review |
| future | How many ANEMONE samples are in this date range? | {"time_from": "2099-01-01", "time_to": "2099-12-31"} | Numbers/citations pass; focus needs review |
| missing_project | How many ANEMONE samples are in the selected project? | {"provider_project_id": "QA-NONEXISTENT"} | Numbers/citations pass; focus needs review |
| polite_summary | Can you summarize the ANEMONE database? | None | FAIL: unnecessary clarification |
| polite_count | Please tell me how many ANEMONE samples we currently have. | None | Numbers/citations pass; focus needs review |
| count_paraphrase | What is the ANEMONE sample count? | None | Numbers/citations pass; focus needs review |
| japanese | ANEMONEにはいくつのサンプルがありますか？ | None | FTS: no evidence; live model pending |
| unresolved_place | How many ANEMONE samples were collected in Japan in 2020? | None | Safe clarification |
| unsupported_richness | How many species are detected in ANEMONE? | None | Safe clarification |
| compound_scope | How many ANEMONE negative and positive controls are there? | None | Safe capability limit |
| abundance_count | Does a higher ANEMONE read count mean there are more fish? | None | FAIL: interpretation misrouted |
| sum_reads | Can I add the reads from QCauto and QCauto+3-NN to estimate fish abundance in ANEMONE? | {"source_type": "edna_metabarcoding"} | FTS: no evidence; live model pending |
| controls_interpretation | Do ANEMONE negative controls prove the environmental samples are contamination-free? | {"source_type": "edna_metabarcoding"} | FTS: no evidence; live model pending |
| copies_interpretation | Do ANEMONE copies per mL establish fish abundance without checking internal standards and protocols? | {"source_type": "edna_metabarcoding"} | FTS: no evidence; live model pending |
| rare_lookup | What evidence supports the ANEMONE detection of Ablabys taenianotus? | {"source_type": "edna_metabarcoding", "taxon": "Ablabys taenianotus", "assignment_method": "qcauto_target"} | FTS: no evidence; live model pending |
| missing_vs_zero | Does missing ANEMONE concentration data mean the concentration is zero? | {"source_type": "edna_metabarcoding"} | FTS: no evidence; live model pending |
| method_compare | Compare QCauto and QCauto+3-NN in ANEMONE. Is agreement independent validation? | {"source_type": "edna_metabarcoding"} | FTS: no evidence; live model pending |
| freshness | Has ANEMONE data from last week arrived? | {"source_type": "edna_metabarcoding"} | FTS: no evidence; live model pending |

## Reproduction and evidence

Run the local phase against the retained, task-owned database after starting it with `.cache/anemone-local/README.md`:

```bash
.venv/bin/python evaluation/qa/run_anemone_questions.py \
  --database-url postgresql://jaronchai@127.0.0.1:55459/anemone_candidate \
  --work-dir .cache/anemone-candidate \
  --serving-dir .cache/anemone-serving-test/serving \
  --output .cache/anemone-local/question-quality-local.json
```

The runner restricts the database host to loopback, verifies the candidate generation, retains full responses and writes resumable evidence after each question. It checks numeric/citation contracts; it is not an automatic scientific-quality judge.

The `--phase model` path requires complete candidate embeddings and a configured Vertex runtime. It uses existing gcloud credentials in memory and normal hybrid retrieval, with no fabricated responses. Populate embeddings using the existing pipeline, verify their model identity and refresh local provenance before using it. Compare answer claims manually against the supplied sources. Repeat high-risk interpretation questions to check variability.

Ignored local artifacts: `question-quality-local.json` (all 22 responses and 9 traces), `question-quality-retrieval.json`, `question-quality-fts-chat.json`, and `question-quality-independent-evidence.json`, under `.cache/anemone-local/`. The latter contains the verified original rare-taxon row.

## Recommended next work

Fix intent routing and ordinary paraphrases, make each answer lead with the requested metric, and distinguish unsupported features from missing scope. Preserve the exact-count citation guarantees. Then populate the local candidate embeddings and run the remaining eight questions through real hybrid retrieval plus Vertex, including Japanese and the rare-taxon lookup. Authenticated cloud/staging QA remains separate.
