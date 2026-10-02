# ANEMONE exact chat aggregation

**Dated local QA record.** Exact aggregation was subsequently deployed with
the v0.5.0 catalogue on 2026-09-30. See the
[production operations record](RELEASE_0.5.0_OPERATIONS.md) for live checks and
[issue #70](https://github.com/jarondlk/ocean-platform/issues/70) for remaining
chat answer-quality defects.

Implemented on `gcp-dev`; local QA completed 2026-09-26 JST. This extends the
[v0.5.0 catalogue implementation](ANEMONE_V0.5.0_IMPLEMENTATION.md). It has not
been released or deployed to GCP. The source observation remains 2026-09-17.

## Behavior

`POST /chat` routes supported ANEMONE/eDNA count and summary questions to exact
SQL over the active canonical corpus. Retrieval top-k and model generation do
not participate. The response records `model_invoked=false`, the actual filters,
publication identifiers and a retained aggregate citation. Unmatched cohorts
receive a cited zero result, with no biological-absence claim.

The summary distinguishes source occurrences from unresolved physical samples;
counts assays, classification states and provider namespaces; separates methods,
read totals, concentration availability and internal standards; and reports
valid empty community tables. Grouping supports up to two of locus, team,
project and run. Namespace totals respect parent namespaces. Grouped rows count
source occurrences, not per-group read totals.

A conservative English vocabulary routes ordinary count questions. Fixed enum
terms such as negative controls, environmental samples, QCauto+3-NN and nontarget
can select a scope. Explicit API filters support taxon, project/run, collection
date and coordinate bounds. Conflicting or unresolved qualifiers request an
explicit scope instead of silently substituting global counts. This is not a
general natural-language-to-SQL system. Geographic names, unfiltered years,
thresholds, compound classification comparisons, species richness, percentages,
version differences and complete detection lists are not implemented here.
Existing analysis-ID requests retain their validated recipe path. The standalone
`orchestration.unified.ask` entry point retains retrieval behavior; its prompt
now explicitly prohibits treating retrieved examples as whole-corpus totals.

Examples that work directly in chat:

- How many ANEMONE samples and reads?
- How many ANEMONE negative controls?
- How many ANEMONE environmental samples?
- How many ANEMONE samples by project?
- How many ANEMONE reads per method?
- How many ANEMONE QCauto+3-NN reads?
- How many ANEMONE nontarget reads?

An API example for a rare taxon (the value is an explicit filter, not inferred):

```json
{
  "query": "How many ANEMONE samples of Ablabys taenianotus?",
  "taxon": "Ablabys taenianotus",
  "assignment_method": "qcauto_target",
  "aggregation": {"group_by": ["provider_project_id"]}
}
```

Additional aggregation scope fields are `provider_locus`, `provider_team`,
`target_status` and `assay_id`. Supplying `aggregation` explicitly requests this
route; unsupported text still requires clarification. These extra fields are
available in the API; the chat settings panel does not yet expose every field.

## Evidence and consistency

Migration `20260925_0013` creates `edna_aggregate_evidence` in application-history
metadata, separate from rebuildable corpus tables. Each content-addressed JSON
payload retains the query contract/version, exact summary, filters, publication
IDs/hashes, ordered canonical row-identity/source-hash fingerprints, source
snapshot descriptors and applicable classification review records. It is
committed before the answer is returned. Identical evidence is inserted once.

A read-only repeatable-read transaction pins summary and input fingerprints to
one database snapshot. The publication pointer must be ready and unchanged;
the retrieval publication's `edna-canonical` binding must match the canonical
publication. Canonical-only changes cannot produce a count answer until a
complete retrieval publication is ready. Imports and materialization write the
binding within the same transaction as publication metadata. Existing deployments
must migrate and rematerialize before this route becomes available.

The implementation enforces one million input rows, a 1 MiB evidence payload,
2,048 source snapshots/reviews, 2,000 groups, and a 20-second timeout per SQL
statement. Exceeding a bound or failing persistence produces
`aggregate_unavailable`, with no model/top-k fallback. The answer shows at most
25 groups and explicitly refers to the complete downloadable result when more
exist. Retained normalized bundles plus the recorded source versions, query
contract and reviews are required to reproduce historical inputs; the summary
itself remains readable without the current corpus.

Citations have the form `aggregate_edna_<sha256>`. The existing evidence navigator
opens their provenance page and downloads JSON through the authenticated API
proxy. `/provenance/trace/{doc_id}` resolves the retained evidence without using
the latest corpus provenance snapshot. `/data/edna/aggregates/{id}` verifies the
payload digest before export. A correction produces a new ID; the old citation
continues to resolve. No automatic aggregate-history deletion is implemented.
Downgrade refuses to erase populated aggregate evidence or incompatible chat
history. Database backups must retain this application-history table.

The citation audit explicitly recognizes this deterministic aggregate route as
analysis evidence covering eDNA. Ordinary raw-source requirements are unchanged.
It does not claim to verify ecological conclusions.

## QA results

- **862 Python tests passed**, with 29 environment-gated tests skipped in the
  default run. The relevant PostgreSQL tests were run separately below.
- **23 distinct PostgreSQL tests passed** across the eDNA integration suites:
  21 in the combined run, plus two added retention/concurrency cases. The final
  aggregate-specific suite passed all 13 tests in isolated schemas.
- **40 frontend tests passed**, along with TypeScript, repository Ruff and
  `git diff --check`.
- **16 full-catalogue chat cases passed** using the real imported candidate.
  Answered cases had zero invalid citations and zero audit warnings. Retrieval
  and model calls were made fatal in this test harness; none occurred.
- Browser QA verified the rendered answer, `Answered / Model run: No`, zero audit
  warnings, applied filters, citation inspector, actual JSON download event and
  the immutable provenance page. The test used loopback-only development
  services; no cloud model or authentication was required. Local model discovery
  reported Ollama unavailable, but aggregate answering worked.

| Full-catalogue check | Result |
| --- | --- |
| Whole catalogue, top-k 1 versus 25 | Same evidence ID; 3,498 occurrences / assays |
| Negative controls | 343 |
| Unknown sample-kind filter | 3,155 |
| Explicit environmental classification | 0; unknowns are not reclassified |
| QCauto and QCauto+3-NN | Each 174,819 rows / 157,426,611 reads; never summed |
| Available / empty community tables | Each method 3,498 / 83 |
| Internal standards | 13,932 rows / 442,404,272 reads |
| Projects / runs | 10 / 19 |
| `Ablabys taenianotus`, QCauto | One occurrence and one assignment |
| Nontarget / nonexistent project | Cited zero matching cohort; not biological absence |
| Japan / free-text year / richness / conflicting control scope | Explicit clarification, no aggregate or model call |

PostgreSQL fixtures also exercised source corrections, retained historical
citations, corpus rebuild isolation, migration rollback/re-upgrade and downgrade
refusal, valid empty tables, wrong-assay sibling matches, taxon/method/namespace
filters, corrupt evidence, incomplete/mismatched publication, concurrent writes
under MVCC, pointer changes, and row/byte budgets. The complete retrieval refresh
retained all 6,996 documents with zero updates or embedding invalidations.

Local ignored evidence is in `.cache/anemone-local/`: `aggregate-full-catalogue-qa.json`,
`aggregate-full-catalogue.log`, `aggregate-full-regression.log`,
`aggregate-postgres-tests.log`, `aggregate-retention-concurrency-tests.log`,
`aggregate-frontend-tests.log`, `aggregate-frontend-typecheck.log`, and browser
service logs. The local API test harness is `qa-aggregate.py` in that directory.
These artifacts contain no download credentials. Temporary local QA services
were stopped after verification; candidate databases and source archives remain.
On this Mac, complete-catalogue answers took about 2.2 seconds and the rare-taxon
case 3.8 seconds, including evidence export/trace checks. These are local
measurements, not cloud latency guarantees.

## Remaining rollout work

Cloud staging still needs the migration, canonical/retrieval publication binding,
application-history backup/restore verification, actual runtime database
permissions, deployed PostgreSQL-version tests, artifact registration and
embeddings/provenance publication. Test authenticated browser behavior and
ordinary model-assisted chat alongside deterministic aggregates in staging.
No GCP services, IAM policies, schedules or release versions changed in this task.

## Subsequent natural-language acceptance review

The [2026-09-26 question-quality review](ANEMONE_QUESTION_QUALITY_2026-09-26.md)
uses 30 realistic questions and separates numeric/citation correctness from
answer usefulness. It found two intent/paraphrase routing failures and response
focus problems despite the exact-count regression passes above. Ordinary
model-assisted QA is pending candidate embeddings and renewed GCP authentication.
