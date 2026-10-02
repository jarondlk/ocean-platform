# ANEMONE integration plan for OCEAN v0.5.0

**Historical implementation plan.** The accessible 2026-09-17 catalogue was
deployed on 2026-09-30. Use the [v0.5.0 operations record](RELEASE_0.5.0_OPERATIONS.md)
for current production state and [issue #70](https://github.com/jarondlk/ocean-platform/issues/70)
for remaining chat answer-quality work. The planning baseline and proposed
steps below are retained as dated design evidence.

Planning baseline: 2026-09-17 JST, repository commit `059d289`.
Status: implementation underway on `gcp-dev`; see [implementation and local QA](ANEMONE_V0.5.0_IMPLEMENTATION.md) for completed work and remaining release gates. Full catalogue discovery and processed-table
investigation and the complete source archive are finished; see the
[measured discovery report](ANEMONE_V0.5.0_DISCOVERY.md) for verification scope
and the evidence that now informs this plan.

## Intended outcome

Make all accessible ANEMONE processed data discoverable, queryable and traceable
in OCEAN, with repeatable incremental ingestion. Preserve the provider's raw
assignments and protocols, and distinguish data coverage from eligibility for
scientific analysis. A record with unknown control status may be incorporated
without becoming eligible for environmental-only conclusions.

The proposed v0.5.0 scope is every discoverable locus, team, project, run and
sample directory under the ANEMONE distribution root. Actual availability must
be established by inventory: the current public homepage describes MiFish and
does not prove that other loci are available. “Complete” will refer to an
identified catalogue observation and its access scope, not to all data ever
produced by ANEMONE or its collaborators.

This document proposes integration work; it does not enable scheduling or change
production. The user subsequently authorized full archive acquisition on external
storage, recorded in the discovery report. The cancelled GitHub release deployment
automation remains cancelled.

## Evidence and remaining uncertainty

| Evidence | Finding | Consequence |
| --- | --- | --- |
| [v0.4.5 operations record](RELEASE_0.4.5_OPERATIONS.md), verified 2026-09-16 | One sample, one assay, 70 detections, four standards; two methods each describe 35 detections and 9,635 reads | This is a working pilot, not a database-scale validation. Production was not re-audited during this planning task. |
| [Current acquisition contract](../data_contracts/anemone_mifish.json) | MiFish/ANEMONE only; sample and run scopes; five selected TSVs; nontarget and FASTQ metadata only | Broader discovery and interpreted nontarget ingestion need implementation. |
| Supplied format/download documentation and subsequent full inventory | Documentation describes seven interpreted TSV types; this accessible catalogue contains five, paired FASTQ, images and control README notices | Support the observed schemas and account explicitly for absent nontarget files. |
| [ANEMONE public homepage](https://db.anemone.bio/), checked 2026-09-17 | Public MiFish distribution section and CC0 notice | Retain provider attribution and the observed notice in acquisition provenance. No current inventory count was obtained. |
| Authenticated HTTP inspection | The recovered pilot download account successfully enumerated the complete accessible tree; all 17,490 processed TSVs were acquired and profiled | Access is resolved; use the measured discovery report for current counts and archive verification status. |
| Retained user reference TSV, rechecked locally | 49,101 bytes, 40 columns, 56 sequence rows, 38,260 reads, one sample identifier; SHA-256 matches the recorded reference | Confirms the regression fixture, not the size or variability of ANEMONE as a whole. |

The [taxonomy reference policy](ANEMONE_TAXONOMY_REFERENCE.md) remains applicable:
the supplied TSV is a format and interpretation reference, not a species
whitelist or an independently verified taxonomy database. It has not been
ingested as a complete sample.

The subsequent full inventory found one locus/team, ten projects, 19 runs,
3,498 source occurrences and 45,144 files totaling 35.56 GB. All 17,490 interpreted
TSVs have been profiled and tested against the existing validator. Observed
headers include both 39- and 40-column communities; 168 provider README notices
also need an explicit contract role. Nontarget tables are not present in this
accessible snapshot. The linked discovery report supersedes the preliminary
inventory uncertainty above.

Still unresolved: provider identity guarantees for repeated sample names,
coordinate precision semantics, update/withdrawal behavior, conditional-request
support (ETag and Last-Modified are present on downloaded files), calibration
acceptance, source pipeline/reference versions, and unattended credential renewal.
The older observations in [the pilot integration plan](ANEMONE_INTEGRATION_PLAN.md)
remain historical and must not be used as current totals or cost estimates.

## What “fully incorporated” should include

| Source family | Proposed v0.5.0 treatment | Interpretation |
| --- | --- | --- |
| `sample.tsv.xz` | Retain exact bytes; normalize known fields; preserve all key/value rows | Sample identity, collection context and explicit classification evidence |
| `experiment.tsv.xz` | Retain and normalize protocols, linked to assay/run | Primer, locus, laboratory and sequencing context |
| Both target community TSVs | Retain and query all rows, with separate method identities | Alternative assignments of sequence evidence, not independent biological replicates |
| Both nontarget community TSVs | Retain and query all rows, explicitly distinguished from target rows | Target status is relative to the assay; nontarget does not automatically mean contamination |
| `community_standard.tsv.xz` | Retain and expose separately | Technical evidence; never silently added to biological totals |
| Provider `README.txt` | Retain bounded source text and explicit evidence markers | The discovered notices identify negative controls, including names without an `NC` suffix; they are source evidence, not executable instructions |
| Paired FASTQ | Preserve the completed local mirror and source manifest; decide ongoing cloud retention separately | Raw-read archive and future reprocessing input; no new denoising pipeline proposed for v0.5.0 |
| Wordcloud PNGs | Preserve the completed local mirror; inventory and link in OCEAN | Presentation derivatives; OCEAN computes its own views from tables |

This release scope is complete processed-data integration. The separately
authorized source acquisition has now retained every exposed file, including
FASTQ and PNG, in a verified 35.56 GB external archive. Ongoing raw-file mirroring
and cloud retention remain operational decisions for recurring ingestion.

The pasted sample/experiment metadata descriptions appear interchanged.
Inspect real keys and provider semantics before mapping them. Preserve duplicate
metadata keys and their row locators rather than collapsing them into a dict.
Missing coordinates, dates or standard files should have explicit handling;
do not fabricate values to make a row pass validation. Required versus optional
fields and valid empty tables must be decided from real examples.

## Changes required in OCEAN

| Area | Verified current constraint | Proposed change |
| --- | --- | --- |
| Discovery | [Scope validator](../ingestion/anemone.py) accepts sample/run beneath one MiFish team | Add catalogue traversal with an allowlisted origin, hierarchy-aware manifests, request budgets and resumable checkpoints. Keep acquisition units bounded. |
| Contracts | Five mandatory selected roles, strict headers, minimum one row, 512 MiB download and 2,000-file cap | Version contracts by observed layout/locus; incorporate nontarget roles and valid empty/missing cases. Keep per-unit limits and quarantine unknown formats. |
| Identity | [Normalizer](../preprocessing/anemone.py) derives sample identity from provider + sample name and one assay from that name | Introduce explicit namespace, locus, team, run and assay relationships; verify uniqueness before deciding canonical keys. |
| Detection schema | [Detection model](../db/models.py) permits two target-only method values; uniqueness is assay + method + sequence hash | Separate assignment method from target status; preserve source-specific rows and pipeline/reference version where supplied. |
| Import | [Importer](../scripts/load_db.py) inactivates missing records within its sample or run scope | Make complete-scope replacement distinct from partial upsert. Include namespace dimensions in reconciliation boundaries. |
| Retrieval | [Materializer](../retrieval/edna_materializer.py) reads the active corpus into memory and rejects more than 2,000 samples/assays or 250,000 detections | Process partitions; publish an explicitly complete generation or perform properly scoped changes. Do not simply remove limits. |
| Publication | Materializer inactivates source-family documents absent from the supplied frame | Never feed a partial batch to the current global merge. Stage and validate a full generation before promotion. |
| Historical lineage | [Job runner](../scripts/run_anemone_job.py) restores all retained normalized bundles, capped at 20 and 512 MiB | Index and load immutable lineage by artifact/document; partition provenance and preserve historical citation lookup without loading all history. |
| Analysis | [Analysis selector](../preprocessing/edna_analysis.py) has row, assay, pairwise and output limits, including 1,000 control-inclusive assays | Push cohort selection/aggregation into the database; retain explicit limits for expensive comparisons and report exclusions. |
| API and chat | Existing [eDNA service](../api/edna_service.py) has database filters and pagination; pilot QA covers a tiny population | Extend filters, measure query plans and answer whole-corpus counts through structured queries with coverage evidence. |

A catalogue need not become one giant `ExternalSourceSnapshot`: retain bounded
sample/run source snapshots and introduce a catalogue/publication manifest that
references them. If snapshot scope values are expanded, migrate the database
constraint as well as Python validation. Keep historical contract hashes readable.

### Identity and migration decisions

Use separate concepts for a provider record, physical sampling event, laboratory
assay, sequencing occurrence, sequence, and taxonomic assignment. A directory
count is not a count of independent physical samples. Do not merge samples on
matching coordinates/date alone; retain an unresolved relationship when upstream
identifiers cannot establish equivalence.

Candidate provider namespace is `(provider, locus, team, project, run, sample)`
for source occurrence, pending collision and rename checks. Stable provider IDs,
if available, should take precedence over a mutable path. Keep the full source
path as provenance regardless. Link multiple occurrences to one physical event
only using explicit evidence.

Migrate the existing pilot through an explicit ID mapping/alias layer so saved
links, reviews, analyses and citations continue to resolve. Preserve classification
reviews when their evidence still matches; changed evidence makes a review stale,
not silently reusable. Version normalization, taxonomy policy and derived outputs.

### Scientific interpretation

- Keep QCauto and QCauto+3-NN separate. Comparing their assignments is valid;
  adding their counts as independent observations is not the default.
- Preserve raw taxonomy and all ranks. A changed provider assignment is a new
  version of evidence, not permission to rewrite the old source file.
- Preserve explicit zero, missing, unresolved and unavailable as distinct states.
  A missing row does not alone establish absence of a species.
- Import controls and unknown classifications. Environmental-only results must
  disclose how many records were excluded and why. Names such as “blank” can
  flag a review candidate, but cannot establish control status alone.
- Keep reads, copies/mL, standards and biological abundance separate. Report
  provider concentrations with their assay/calibration context; standards alone
  do not establish calibration validity or comparability across protocols.
- Do not force global samples into OCEAN's existing local monitoring geography.
  Environmental joins need explicit distance, time and variable criteria with
  unmatched records retained. No nearest unrelated site should be substituted.

## Implementation sequence and exit gates

### 1. Catalogue and representative-file discovery

Obtain working download access, then enumerate the distribution hierarchy with
one worker initially, a conservative request pace, bounded retry/backoff and
checkpoints. Record failed/forbidden paths rather than treating them as empty.
Pause credential-dependent work on 401. Respect provider limits and `Retry-After`.

Produce a credential-free manifest of source URLs, hierarchy, roles, observed
sizes, validators and observation times. Inventory FASTQ without downloading it.
Separate directory, provider-record, assay and physical-sample counts. Record
unknown sizes instead of assuming zero; use HEAD only if supported.

Profile examples across every discovered locus and layout, teams/projects,
early/recent runs, control candidates, empty/sparse/high-read samples, missing
metadata and calibration variants. Start with 10–20 sample directories and
expand until each distinct format is covered; this is a starting budget, not
a statistical guarantee. Inspect all seven interpreted TSV types where present.

Deliverables: catalogue manifest, coverage report, representative schema/key
profile, identity collision report, compressed/expanded size estimates by stratum,
and a download budget. No global totals are final until enumeration is complete.

**Gate:** every observed branch is accounted for; all unvisited or inaccessible
branches are explicit; contracts and capacity assumptions have real-file evidence.

### 2. Schema, contracts and backward compatibility

Implement namespace/assay identities, method versus target-status dimensions,
raw metadata preservation and evidence-based missing/empty rules. Add immutable
catalogue observations and per-unit processing state. Implement pilot ID aliases
and a reversible migration strategy. Extend UI/API selectors together with schema.

**Gate:** representative files normalize reproducibly; collisions are detected;
the existing pilot's source data, method totals and historical citations are
preserved. Unsupported records are visible with reasons.

### 3. Resumable acquisition and isolated candidate import

Use a durable work ledger for discover, download, verify, normalize and stage
states, keyed by source version and contract version. Retain compressed source
bytes and SHA-256. Download to temporary files, verify before marking complete,
and resume only when remote-version consistency can be established. Otherwise
restart that file; `wget --continue` alone does not prove integrity.

Treat ETag/Last-Modified as discovery hints; hash downloaded content. Detect
changes to old runs, not just new directories. Recheck listings/validators around
acquisition; retry changed units. Without an immutable provider export, report
the observation window rather than claiming a perfectly simultaneous snapshot.

Import into candidate tables or a staging database. Distinguish partial batches
from complete reconciliation units. Validate duplicates, foreign keys, read sums,
file counts and row accounting. Failed download/validation must never inactivate
the last good production records.

**Gate:** interruption and re-execution are safe; unchanged reruns create no
duplicate canonical rows; each input row is retained or explicitly quarantined.

### 4. Publication, retrieval and capacity

Partition derived artifacts and provenance; avoid copying all history per run.
Choose indexes from measured filtered queries. Use deterministic summaries and
embed only changed text, not every sequence row. Build coverage summaries and
taxon lookup/aggregate support so rare detections are not hidden by top-k excerpts.

Bind API data, search documents, embeddings, analysis inputs and provenance to
one publication identifier. Build and check a candidate publication, then promote
its pointer with a concurrency check. All readers must pin that identifier so a
pointer switch cannot expose a mixture of old data and new citations. Serialize
overlapping ingestion/publication attempts with a lease and recoverable checkpoints.

Measure representative small, medium and large batches before extrapolating.
Include normalized data, indexes, embeddings, source retention, old generations,
temporary disk, database load, compute and provider request load. Compare ongoing
incremental and initial backfill costs against the existing JPY 20,000/month
whole-project budget; current billing and prices need refreshing before execution.
No credible total cost or completion date is available yet.

**Gate:** full-scale candidate load fits the measured resource budget; every
published citation resolves; readers stay consistent during promotion and rollback.

### 5. Full backfill and release QA

Acquire and process all agreed interpreted-data scopes in bounded batches.
Reconcile each scope against its catalogue manifest and perform a final discovery
pass for changes during the backfill. Show counts for discovered, downloaded,
validated, imported, quarantined, excluded-from-analysis and published records.

An accounted-for but quarantined record is not successfully integrated. Report
that distinction and resolve all supported in-scope failures before declaring
complete processed-data integration. Any accepted source exception must appear
in the release's coverage statement.

Run the matrix below plus the v0.4.5 chat/citation regression baseline. Validate
backup restoration and publication rollback without overwriting later user/chat
records. Promote only the accepted candidate. Retain source bytes and mappings
needed for previous citations; define retention costs before any pruning.

**Gate:** the coverage ledger reconciles, scientific and software QA pass, and
the release states exactly which catalogue observation and files it incorporates.

### 6. Recurring ingestion

Proposed starting cadence after the backfill:

| Operation | Starting frequency | Reason |
| --- | --- | --- |
| Catalogue/validator check | Weekly | Detect new directories and changed older data without repeatedly downloading everything |
| Changed TSV acquisition and staging | Following a successful check, within byte/request budgets | Preserve discovered versions and identify errors before publication |
| Validated publication | Monthly initially | Gives time to review real update patterns and scientific exceptions |
| Full catalogue reconciliation | Monthly | Revisit older runs and detect removals or changed hierarchy |
| Content reconciliation when validators are unreliable | Rotating bounded checks, schedule based on measured volume | Detect content changes that timestamps miss; disclose the resulting detection lag |

Move publication to weekly once observed changes, job cost and QA results justify
it. Source freshness, acquisition time and publication time should be displayed
separately. A no-change check should not create another scientific generation.

A scheduler invokes a job asynchronously: record its execution ID and verify
the job's terminal outcome. Scheduler acceptance alone is not ingestion success.
Monitor stale data, credential failures, failed scopes, quarantine growth, budget
overruns, stalled leases and publication failures. Retain the last good publication.
Treat a disappeared path as a withdrawal candidate; require repeated successful
complete listings or explicit provider withdrawal evidence before inactivation.

[Cloud Scheduler can invoke Cloud Run jobs](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule).
The proposed runtime uses a service identity for GCP access and a restricted
ANEMONE secret reference for downloads. Human GCP sign-in and provider download
authentication are separate. Plan exact permissions during implementation;
do not recreate GitHub release deployment federation for this purpose.

The supplied password was described as valid for the last ten days. Its exact
rotation semantics are unverified, but neither a weekly nor monthly schedule
guarantees permanent access with a fixed credential. Initially use an explicit
credential refresh procedure and pause/alert on failure. Reliable unattended
operation needs a provider-supported renewable credential or durable read-only
token. Never automate website login by guessing or scraping around authentication.

## QA matrix and chat questions

These are proposed acceptance tests, not results of tests executed in this task.
Numeric expected answers must come from frozen source fixtures and independent
SQL/source reconciliation, not from another generated answer.

| Test family | Required cases and expected behavior |
| --- | --- |
| Format and preservation | Empty valid tables; absent standards; repeated metadata keys; unknown columns; alternate missing markers; sequence alphabet variants; corrupt/truncated XZ. Preserve supported inputs, quarantine unsupported ones with explicit reasons. |
| Identity | Same name across namespaces; repeated sequencing of one sample; multiple loci/primers; renamed path; same sequence in both methods/classes. No accidental merge or double count. |
| Incremental behavior | No-change rerun, old-file correction, crash mid-download/import/publish, overlapping triggers, 401, 429 and 5xx. No partial publication, duplicate canonical rows or unrelated inactivation. |
| Withdrawal | Incomplete crawl, transient 404, confirmed withdrawal and later reappearance. Keep history and distinguish unknown availability from deletion. |
| Scientific scope | Unknown/control classifications, explicit zero versus missing, unresolved taxonomy, differing protocols, missing calibration. Preserve exclusions, units and limits of interpretation. |
| Compatibility | Existing taxonomy reference, pilot totals, saved classification reviews, old citations and v0.4.5 chat failures. Historical evidence remains resolvable and baseline behavior is preserved. |
| Serving at scale | Stable pagination, large filtered totals, rare taxon lookup, date boundaries, global geography, publication switch and rollback. No truncated totals or mixed-generation answers. |
| Performance | Full measured inventory, projected growth and retained history; representative queries and expensive comparisons. Establish measured latency/memory/cost targets before release, with bounded failure for unsupported requests. |

Suggested user-facing QA questions:

1. “How many ANEMONE physical samples and assays are available, by locus and
   project, and what proportion of the discovered catalogue is included?”
   Require distinct count definitions, publication ID and any unresolved identities.
2. “What changed since the previous ingestion, including corrections to older
   samples?” Require a version diff, not just samples collected recently.
3. “Compare QCauto and QCauto+3-NN for the same sample. Can I add their reads?”
   Show methods separately and explain the shared evidence.
4. “Show all detections of [a rare taxon in the frozen dataset] in [region/time].”
   Reconcile a complete filtered result/export with SQL; top-k retrieval is insufficient.
5. “Which samples have no target detections, and which have missing target data?”
   Separate valid empty/zero cases from absent or unprocessed files.
6. “Include blanks and other controls, then show the environmental-only result.”
   Match explicit classification and explain exclusions and unknowns.
7. “Do more reads or higher copies/mL here prove there are more fish?”
   Avoid unsupported abundance claims and disclose protocol/calibration limits.
8. “Is a nontarget detection evidence of contamination?” Require context and
   control evidence; do not equate target status with contamination.
9. “Compare the same location across different primers and sequencing runs.”
   Identify compatibility limits and biological versus technical replication.
10. “Show the original file and exact rows supporting this result, including
    the version before the provider corrected it.” Resolve both historical and
    current provenance.
11. “Compare a sample outside Japan with OCEAN's local water-quality stations.”
    State when no qualified environmental match exists.
12. “Has ANEMONE data from last week arrived?” Distinguish collection date,
    provider availability, acquisition, publication and unknown freshness.

## Provider requests after the first full ingestion

The first ingestion can use the documented hierarchy if access works. A complex
API is not a prerequisite. Retain an evidence-based list of friction points for
the user's later discussion with the ANEMONE developer; no outreach is initiated.

Most useful requests, in order:

1. A versioned downloadable manifest/export listing stable IDs, paths, file sizes,
   checksums and an export/release identifier. This may remove most crawler work.
2. Clear identity semantics across physical samples, primers, runs and renamed
   paths; documented control and calibration metadata.
3. A change feed or manifest diff covering updates to old data and withdrawals,
   with a durable cursor, stable pagination and consistent snapshot semantics.
4. Renewable read-only machine access and documented rate/concurrency limits.
5. Pipeline, taxonomic reference and assignment-method versions, plus schema
   change notices and conventions for missing or empty tables.
6. Bulk archive options and a raw-read retention/mirroring recommendation,
   informed by the measured 28.78 GB compressed FASTQ payload.

## Current next step

The catalogue implementation and full local candidate QA are documented in
[ANEMONE_V0.5.0_IMPLEMENTATION.md](ANEMONE_V0.5.0_IMPLEMENTATION.md). All archived
occurrences normalize; the former pilot limits have been replaced by bounded
catalogue processing. The main-device archive is the working copy, with the
external original retained as backup.

Exact chat aggregation and immutable citations are now implemented and locally
verified; see [ANEMONE_CHAT_AGGREGATION_QA.md](ANEMONE_CHAT_AGGREGATION_QA.md).
Next are the documented release gates: cloud staging and artifact registration,
authenticated chat QA, cross-process publication/rollback QA, and scheduling
with durable provider credentials. Production backfill and recurring execution
have not been enabled.
