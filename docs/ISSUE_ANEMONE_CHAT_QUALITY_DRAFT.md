# Draft GitHub issue — ANEMONE chat answer quality

**Prepared for GitHub-first release on 2026-09-27.** File before GCP deployment, explicitly retaining local-only reproduction status below. Proposed labels: `bug`, `logic`. Suggested follow-up release: v0.5.1; no milestone has been assigned.

## Proposed title

Chat: distinguish ANEMONE count and interpretation questions and lead with the requested metric

## Proposed issue body

ANEMONE chat sometimes asks for scope that is already clear or routes an interpretation question to the exact-count handler. Successful count answers often bury the requested metric in a generic catalogue summary. These are confirmed routing/presentation logic problems in the local v0.5.0 candidate; the observed exact-count values and aggregate citation integrity checks passed.

### Environment and evidence

- Reproduced on local `gcp-dev` on 2026-09-26 against the accessible ANEMONE catalogue observed on 2026-09-17.
- Production release/commit and post-deployment reproduction: **pending; GCP deployment follows the GitHub source release**.
- [QA report](ANEMONE_QUESTION_QUALITY_2026-09-26.md) and [exact question requests](../evaluation/qa/anemone_v050_questions.json). Replace these relative links with repository permalinks at the verified release commit when posting.
- Of 22 aggregate/clarification cases, 17 returned expected numbers with valid citations and verified exports; two exposed routing failures, two correctly requested clarification and one reached a documented capability limit. This was not a live-model quality pass.

### Reproduction

Send each question in a fresh chat without explicit filters unless specified:

| Question | Actual result in local candidate | Expected behavior |
| --- | --- | --- |
| Can you summarize the ANEMONE database? | Generic request for explicit scope. The simpler “Give a summary of ANEMONE data” works. | Recognize the whole-catalogue summary request; answer from the exact aggregate with a citation. |
| Does a higher ANEMONE read count mean there are more fish? | The word “count” sends an interpretation question to a generic scope clarification. | Route to interpretation/retrieval; explain only what the supplied evidence supports and state limits when necessary. |
| How many ANEMONE samples have unknown control status? | Leads with 3,498 total source occurrences and only later gives the requested 3,155 unknown classifications. | Lead with the requested scoped metric and its unit/citation; keep other totals secondary. |
| How many physical samples are included in ANEMONE? | Unresolved identity is buried in a full catalogue template. | Lead with physical sample identity being unresolved; distinguish reported names, occurrences and assays. |

For an environmental-only query, the response correctly reports zero explicitly classified environmental occurrences, but zero unknowns within the filtered set can obscure the excluded unclassified records. Explain the filtering boundary. Cite separately scoped evidence if including the unfiltered unknown count; never attribute it to an environmental-only aggregate.

### Scope of the fix

1. Accept ordinary paraphrases and polite wording for supported aggregate questions without widening numeric scope silently.
2. Separate scientific interpretation from requests to count records, even when both contain words such as “count” or “reads”.
3. Make each answer lead with the requested metric or the relevant unresolved limitation. Distinguish missing scope from unsupported operations.
4. Explain classification/filter exclusions clearly while retaining citations with the correct scope.
5. Add a Japanese routing regression case, including “ANEMONEにはいくつのサンプルがありますか？”. Full Japanese answer quality still requires live evaluation.

### Acceptance criteria

- Supported summary/count paraphrases reach the intended route. Interpretation questions do not become generic aggregate-scope refusals.
- Unknown-control, method-read, internal-standard and empty-table questions lead with their requested result. Physical-sample answers lead with unresolved identity.
- Unsupported richness and compound comparisons remain honest about capability; text mentioning place/year does not silently discard or invent filters.
- Empty scope, missing concentration, zero measured value, absent source column and unavailable nontarget evidence remain distinct.
- Alternative assignment methods are never added as independent fish/sample/read observations; read counts are not asserted to establish organism abundance.
- All previously passing exact-number cases retain their values, source scope, valid citations and reproducible hash-verified exports. Any broader contextual total has separately scoped supporting evidence.
- Evaluate affected ordinary questions with complete matching embeddings and actual hybrid/model execution. Record manual claim-to-citation checks and repeated high-risk questions; citation syntax alone is insufficient.

### Separate deployment prerequisite

The local QA corpus had 0/6,996 embeddings. Eight FTS-only diagnostic questions retrieved no evidence and abstained without a model call, including a rare-taxon lookup whose source row exists. This does **not** demonstrate an LLM reasoning defect. Complete indexing and live retrieval validation are v0.5.0 deployment gates tracked in the release plan. Update these results after deployment; file any persisting retrieval defect separately if it has a different cause.

Related context: [#59](https://github.com/jarondlk/ocean-platform/issues/59), already closed after the earlier reliability work. This issue concerns new confirmed routing and presentation behavior, not a request to reopen that incident.
