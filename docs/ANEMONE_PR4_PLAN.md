# ANEMONE PR4 — Scientific Analysis and Qualified Environmental Evidence

> Status: implemented locally on `gcp-dev`; follow-up audit fixes implemented in PR5
> Reviewed: 2026-09-02
> Implementation verification: 2026-09-03 JST
> Dependency: local PR1–PR3 implementation on `gcp-dev`
> Scope: reproducible analysis bundles, controls, method comparison,
> environmental context, read APIs, citations, and research exports

The 2026-09-03 follow-up audit found three gaps: result-manifest
verification on direct reads, historical analysis citation indexing, and
cohort/method filtering after top-K retrieval. See
[`ANEMONE_PR5_PLAN.md`](ANEMONE_PR5_PLAN.md) for the now-implemented repairs
and permanent tests. Live pilot validation is still pending; the implementation
record below is not a release-readiness claim.

## 1. PR3 review and entry gate

The three findings below are now fixed and regression-tested. Their original
review evidence is retained for context; references describe the pre-fix code.
The implementation record below supersedes the original proposed file map.

PR3 provides the necessary canonical identities, separate assignment methods,
active lifecycle, structured evidence browser, and source provenance. It
was not yet merge-ready without the following follow-ups. This review superseded
any earlier implication that passing the existing tests alone completed review.

| Priority | Finding | Evidence and required correction |
| --- | --- | --- |
| P1 | Explicit eDNA selection does not constrain supplementary analysis context | `orchestration/unified.py:575–590` selects context from question keywords only; `api/main.py` does not pass request source/filter scope into it. `provider=anemone` with “Compare diversity” and only eDNA results can still inject Kraken/MetaEuk analyses. Pass resolved source families and cohort scope through the prompt/context and audit paths, including zero-result requests; never infer scope only from wording. |
| P2 | Date-only end filters exclude timestamped observations on the end date | `api/edna_service.py:91–102` and its detection equivalent compare text; the local and PostgreSQL retrievers do likewise. A fixture at `2026-09-01T12:00:00+00:00` returns one result without an end filter and zero with `time_to=2026-09-01`. Share a UTC interval contract across API, search, exports, and UI. |
| P2 | Retrieval fallback publication is not coordinated with the committed DB generation | `retrieval/edna_materializer.py:241–259` releases its transaction/advisory lock before writing artifacts, using shared `.tmp` names and separate replacements. Concurrent executions can overwrite a newer generation with an older one; failed writes can leave stale or mismatched fallback artifacts. Publish immutable generation-addressed artifacts through one verified pointer, coordinate the DB generation and readiness state, and add failure/concurrency tests. |

The first two findings were reproduced with isolated in-memory fixtures. The
third is a code-path/concurrency finding, not a reproduced production incident.
The focused PR3 suite passed **62 tests** during this review; those existing
tests do not cover these failures. The prior full-suite/integration results
remain historical verification, not a new full rerun in this planning turn.

Corrections are implemented in the shared UTC interval helper, structured
prompt/audit scope, and immutable retrieval generation publisher with migration
`20260902_0007`. A real PostgreSQL concurrency test verifies that the second
materializer cannot read its snapshot before the first finishes publication.

### Implementation record

- Manual CLI: `scripts/run_edna_analysis.py --recipe <reviewed.json>` validates
  and computes a dry run without publication; `--execute` publishes. The
  optional Admin pipeline stage uses `EDNA_ANALYSIS_RECIPE` and is not default.
- Recipe/models: `preprocessing/edna_recipe.py`; analysis and control reports:
  `preprocessing/edna_analysis.py`, `preprocessing/edna_quality.py`.
- Immutable bundles: `ingestion/edna_analysis_bundle.py`; read routes:
  `api/edna_analysis_routes.py`. Complete canonical input records, source hashes,
  row locators, external observations, recipe, runtime versions and all 14 result
  tables are retained. Same inputs/recipe/runtime reproduce the same identity.
- Data → eDNA analysis supports method filters, exact result URLs, source links,
  provenance/recipe inspection, historical status, table CSV and complete ZIP.
  Environmental plots show one partition/variable/evidence type at a time and
  explicitly label the displayed-row subset. Full IDs remain in exports/traces.
- Chat accepts an explicit current `analysis_id`; incompatible filters or stale
  inputs fail closed. Bounded context identifies its featured subset and exact
  result IDs. No automatic keyword-based selection of unrelated eDNA analyses.
- A reviewed environmental JSON observation adapter is implemented; existing
  CTD/NetCDF extraction is not automatically converted to qualified observations.
  Supply measured/source-backed metadata, unit mappings, a site registry and a
  reviewed profile. Qualified pairs are available through the selected analysis
  context, not the legacy generic cross-source expansion path. Site-specific
  source extraction/coverage review is a PR5 pilot prerequisite.
- Freshness compares current canonical inputs and algorithm/runtime versions.
  External observations are pinned input snapshots, not monitored live feeds;
  source changes require explicit resupply and a new analysis. Old bundles stay
  verifiable by exact ID. Provenance publication indexes selected recipe runs.
- Row guards remain as specified below; total serialized analysis is also
  limited to 128 MiB. CLI recipe/environment files are capped at 1/16 MiB.
  Oversized analyses fail, never silently truncate. Display/API tables paginate;
  CSV exports cap at 25,000 rows with an explicit header, while ZIP is complete.
- Research answer-review cases are in `evaluation/edna_research_cases.json`.
  Deterministic tests do not establish live model or scientific-study validity.

No commit, push, live download, production migration, GCP change or release is
included in this implementation. See `TESTING.md` for the latest verification.

### Additional environmental prerequisites, not new PR3 regressions

- `retrieval/cross_source_linker.py` accepts `max_distance_km` but does not
  calculate distance; legacy sample/SST links use time alone.
- `schema/anchor_event.py` substitutes approximate bay coordinates for legacy
  samples and has no regional SST footprint. These are not measured CTD
  positions or sample-specific SST observations.
- Local `ctd_summary.parquet` contains 162 rows dated 2024-01-18 through
  2026-03-02 and no coordinate columns. Local `sst_daily_summary.parquet`
  contains 79 regional summaries dated 2025-12-05 through 2026-02-27, without
  footprint or valid-pixel coverage fields. These are local artifacts, not
  verified production inventory or evidence of overlap with an ANEMONE pilot.
- Sample/assay environmental metadata remains raw JSON. Internal-standard
  canonical rows contain sequence/read counts, not a validated calibration
  model. Unit, calibration, site, depth, and control-pairing contracts must
  precede interpretation.

## 2. Outcome and scope

A researcher selects a defined cohort, compares methods without pooling them,
inspects detection history and community composition, checks controls, and
exports the exact inputs/results/recipe used by a cited analysis.

PR4 will deliver descriptive research analyses and a fail-closed environmental
linking capability. It must not promise that suitable live CTD/SST matches
exist. No live download, production migration, GCP job, deployment, or release
is part of this PR.

Scope refinement proposed for this PR: environmental associations are
descriptive effect sizes and inspectable paired rows, not automatic significance
claims. Occupancy models, causal claims, predictive “reliability” scores,
rarefaction/extrapolation, ordination, PERMANOVA, and model-based contamination
removal require a reviewed study/replicate design and remain later research
extensions. This is an explicit refinement of the broad integration roadmap,
not an assertion that these analyses are already supported.

## 3. Analysis recipe and cohort contract

Add a versioned, strictly validated recipe; no free-form SQL or expressions.
The proposed baseline is:

- source family `edna_metabarcoding`, provider `anemone`;
- explicit project/run, sample IDs or geographic/time selection;
- assignment methods explicitly listed; the example recipe lists both, which
  produces independent outputs plus a paired-method report;
- one explicit taxonomic rank per run, initially `genus` or `species`; the
  example recipe uses genus, displayed in every table/export;
- `environmental_only`: `sample_kind=environmental` and `is_control=false`;
  controls and unknown classifications remain in the input inventory and
  exclusion report, never silently reclassified;
- positive source reads only for composition (`read_count > 0`); this is not
  a claim that one read establishes a reliable biological detection;
- no additional low-read cutoff or control subtraction by default;
- no pooling of sequencing runs, primer protocols, methods, or replicates;
- no CTD/SST linkage unless a reviewed linkage profile is explicitly supplied.

PR3's raw Data browser still includes controls and both methods by default.
The analysis cohort policy is a separate, visible choice. A control-only
diagnostic view is supported; controls are not pooled with environmental
samples in ecological metrics. An optional explicit minimum-read sensitivity
recipe produces a new result alongside the baseline, never edits source rows,
and records each excluded detection/reason.

Resolve membership from a consistent read of all active canonical DB scopes,
not the latest normalization pointer, retrieved top-K, featured top-ten taxa,
or a paginated browser response. Include every candidate sample and assay in
the membership table, including those excluded or yielding no eligible taxa.

Within a comparison partition, require matching provider/project/run,
assignment method, target gene, primer protocol, sequencing method, and rank.
Retain library/PCR metadata for protocol checks. Missing essential protocol
information or incompatible protocols produce separate/non-comparable
partitions. Cross-project/run pooling and inferred technical-replicate merging
are not part of this baseline. An explicit, source-backed site/replicate map
is needed for repeated-site claims; do not parse a site identity from labels.

### Time semantics

Use one shared typed UTC time representation. Date-only filters include the
whole date: an inclusive end date becomes an exclusive next-day boundary.
Offset-bearing timestamps are normalized to UTC; missing timestamps never
match a bounded interval. Preserve date-only observation precision as an
interval, not a fabricated exact midnight. Browser filters remain dates;
timestamp-capable APIs retain their explicit precision. Test offset-equivalent
timestamps, end-of-month/leap-day boundaries, nulls, and date/datetime mixing.

### Taxonomy and measurement semantics

- Aggregate source reads across sequences only within the same assay, method,
  and exact rank-qualified taxon key. Preserve the ancestor path to avoid
  merging identically named taxa with conflicting classifications.
- Unresolved rank assignments remain an explicit unresolved category in
  coverage reports, but are excluded from rank-specific richness/diversity.
  Do not substitute a genus for a missing species or count each sequence as
  another species. Preserve original names; no synonym or fuzzy matching.
- Export retained/excluded read totals, taxon-assignment coverage, and source
  detection IDs. Aggregate before calculating proportions.
- `copies_per_ml` remains source-supplied, nullable evidence. Do not impute,
  recalculate, sum across records, or use it as the diversity weight in PR4.
- Read-based indices describe assigned sequence-read composition, not organism
  abundance or an unbiased estimate of whole-community biodiversity. Library
  size, primer bias, protocol, and unresolved assignments remain visible.

## 4. Scientific outputs

### A. Detection history and composition

Produce a sample/assay/method/rank/taxon long table with read counts, read
proportions, collection time/precision, coordinates, and provenance. Show
history only over observed sampling events; do not fill unsampled dates or
locations with zero or infer local extinction/arrival.

Distinguish `recorded`, `no qualifying record`, `method unavailable`, and
`sample excluded`. Zeros in a complete comparison matrix mean no qualifying
record under that recipe, not demonstrated biological absence.

### B. Alpha diversity

For eligible aggregated counts `n_i`, `N=sum(n_i)` and `p_i=n_i/N`:

| Output | Definition |
| --- | --- |
| Observed assigned-taxon richness | `S = number of positive-count taxon keys` |
| Read-composition Shannon | `H = -sum(p_i * ln(p_i))`, natural logarithm |
| Read-composition Simpson | `1 - sum(p_i**2)`; explicitly the `1-D` variant |
| Pielou evenness | `H / ln(S)` only for `S > 1` |

For `N=0`, return richness zero only when input/method completeness is known;
return null diversity/evenness with a reason. For one eligible taxon, Shannon
and Simpson are zero and Pielou is null (`single_taxon`), not an arbitrary
zero. A missing method/file is never represented as an empty successful
community. Preserve full precision in artifacts and round only for display.

Use the [Shannon definition](https://scikit.bio/docs/latest/generated/skbio.diversity.alpha.shannon.html)
and [Pielou definition](https://scikit.bio/docs/latest/generated/skbio.diversity.alpha.pielou_e.html)
as references; the explicit null conventions above are this application's
reporting policy. No new heavyweight scientific dependency is required merely
to compute these formulas.

### C. Community similarity and turnover

- Jaccard similarity: intersection/union of qualifying assigned-taxon sets.
  Also export `1-similarity` as a separately named dissimilarity, not an
  ambiguous “Jaccard” column.
- Bray–Curtis dissimilarity on per-assay read proportions:
  `sum(abs(p_i-q_i)) / sum(p_i+q_i)`. Record the relative-read transformation;
  do not silently switch between raw counts and proportions.
- One empty and one nonempty eligible set has Jaccard similarity zero.
  Two empty sets return null (`empty_union`), deliberately overriding library
  conventions that could imply evidence of matching communities. Bray–Curtis
  requires both nonempty compositions; otherwise return null with a reason.
- Export paired assay IDs, method/rank, sample times/precision, distance when
  coordinates are valid, and comparability/exclusion reasons. Keep same-site
  temporal pairs and different-site pairs distinct; no turnover attribution
  without a reviewed site map and repeated sampling support.

Reference formulas: [SciPy Jaccard](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jaccard.html)
and [SciPy Bray–Curtis](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.braycurtis.html).
These metrics do not correct sequencing-depth or detection-probability bias.

### D. QCauto versus QCauto/95%-3NN

Full-outer-join on `(assay_id, sequence_sha256)`, not taxon labels. Retain both
detection IDs, reads, assignments, and full lineages. Classify rows as exact
rank agreement, compatible coarser/finer resolution, conflicting assignment,
unassigned, or method-only sequence. Report matched/unmatched denominators,
resolution counts, and read-count discrepancies. Comparability cannot be
inferred merely from equal sample-level species totals.

Rank-level set overlap is a supplementary summary, not the matching key.
Neither method is treated as ground truth; agreement is not accuracy or
independent corroboration. Do not assume equal read totals or identical
sequence sets. Both branches originate from the same assay evidence.

### E. Controls and internal standards

- Inventory controls by source classification and provider/project/run/assay
  protocol. Preserve blank type and original metadata when supplied.
- Report shared sequences and assigned taxa between environmental records and
  negative controls, with both read counts and method. Same-run controls are
  contextual unless an explicit field/extraction/PCR pairing map is supplied.
- Do not label every shared taxon contamination, subtract reads, or apply a
  global maximum-blank threshold. Missing controls mean `not_assessed`, not
  `passed`; unknown sample classifications never become negative controls.
- Positive/mock controls require an explicit expected-composition record
  before sensitivity, specificity, or pass/fail can be calculated. Otherwise
  show observed records and missing expectations only.
- Internal-standard output lists observed standards, source read counts,
  declared standards when unambiguously recorded, missing/zero records, and
  source-supplied copies/mL coverage. Do not invent expected concentrations,
  fitted slopes, recovery percentages, or calibration quality scores.

The [qMiSeq study](https://www.nature.com/articles/s41598-022-25274-3) derives
copy estimates using known internal-standard inputs and sample-specific
calibration. Its design supports keeping read counts separate from supplied
copy estimates; it does not supply a universal calibration or control policy
for this corpus.

### F. Environment and qualified CTD/SST context

First produce an ANEMONE metadata coverage/unit report. Parse temperature,
salinity, sampling depth, and volume only through a versioned allowlist of
reviewed source keys and units; preserve raw values and source-row locators.
Unknown or ambiguous units remain unavailable, not heuristically coerced.

Provide paired rows/scatterplots and optional descriptive Spearman rho within
eligible method/protocol partitions. Require at least three finite paired
observations with variation, report pair/sample/site counts and exclusions,
and identify repeated sampling. This minimum is a computational guard, not
statistical adequacy. No p-values, “significant” badges, predictive scores,
or causal text in this baseline. Study-specific inferential testing requires
an independent-unit/replicate design and multiple-testing plan later.

Qualified linking must satisfy **both** space and time constraints:

1. CTD positions must be measured/source-backed or supplied by a reviewed
   station registry with provenance and uncertainty. Never use `BAY_COORDS`
   as an observation position or label reused names as the same sample.
2. Compute great-circle distance; require an explicit maximum distance and
   time window in a versioned, reviewed profile. No global 50 km/7-day default
   is accepted as a scientific matching rule.
3. Account for timestamp/date precision. Store the possible time-separation
   range; qualification uses the conservative upper bound. SST daily periods
   use their actual JST aggregation interval converted to UTC.
4. SST regional summaries require the actual footprint and valid-data
   coverage from their contributing files. They remain `regional_context`,
   not point observations. Point extractions require in-footprint sampling,
   actual pixel coordinates/distance, valid finite values, and available
   quality metadata. Nearest-edge extrapolation outside a tile is rejected.
5. Preserve measurement type and depth. A shallowest CTD value is not
   automatically surface water, satellite skin SST is not CTD bulk water,
   and a brightness-temperature proxy is not a validated SST product.
6. Export all qualified candidate pairs plus the selected pair and exclusion
   reasons. Deterministic selection orders by maximum time separation,
   distance, then immutable target ID. Do not duplicate an assay's diversity
   value across many environmental matches and treat those as replicates.
7. No coastal barrier/current model is claimed by great-circle distance.
   Profiles must delimit an appropriate waterbody/domain and acknowledge
   unresolved transport/connectivity. Unknown compatibility is not evidence
   of a biological relationship.

Record source/target IDs and hashes, observed coordinates and coordinate
basis, distance, temporal intervals, depth/type, footprint/coverage, profile
ID/hash, thresholds, and qualification reason with every link. Empty matched
sets are a valid result; do not widen thresholds automatically.

Only these typed, published eDNA links may enter evidence expansion. Keep
legacy time-only links excluded for eDNA as origin and target. A qualified
environmental observation is context, not independent validation that an
assigned organism was present. CTD/SST limitations do not block diversity,
method comparison, or control reports.

## 5. Reproducibility and publication

Add a manual CLI, `scripts/run_edna_analysis.py`:

```bash
python scripts/run_edna_analysis.py --recipe path/to/recipe.json --dry-run
python scripts/run_edna_analysis.py --recipe path/to/recipe.json --execute
```

Dry-run is the default: validate recipe, resolve cohort, report counts,
partitions, exclusions, input availability, and resource limits without
publishing analyses or mutating canonical rows. Browser requests read completed
runs; they do not execute analyses or accept arbitrary server filesystem paths.

Compute from one consistent canonical snapshot, retain the complete referenced
input rows/immutable bundle identities, then release the DB transaction before
long computations. IDs combine canonical recipe, input hashes, and algorithm
version; execution timestamps are metadata, not scientific identity. A changed
source, control map, rank, method, threshold, or algorithm creates a new run.

Publish under `data/analysis/edna/<analysis_id>/` with:

- canonical recipe and input manifest;
- cohort membership/exclusions and protocol partitions;
- full supporting row identities/hashes, not just displayed detections;
- composition, diversity, pairwise, method-comparison, controls, standards,
  metadata coverage, and environmental-link tables;
- source-qualified bounded context documents;
- output hashes, schema/algorithm/library versions, status and limitations.

Use isolated staging, immutable completed directories, and one verified atomic
pointer/index update. Do not claim atomicity across PostgreSQL and files:
coordinate the ready DB generation and pointer explicitly, detect incomplete
publication, and recover idempotently. Stale/incomplete generations must not
be injected as current evidence. Old analyses remain accessible by exact ID
with their original inputs and a historical status.

Initial engineering limits: 200 selected environmental assays, 250,000 input
detection rows, 5,000 rank-level taxon keys, and 50,000 comparison rows per run.
These are configurable resource guards, not scientific thresholds. Preflight
fails with counts when exceeded; never truncate an analysis. Pairwise outputs
are partitioned by method/protocol, keeping each 200-assay partition at or
below 19,900 unique pairs. Sequence-control comparisons use bounded keyed joins,
not unbounded sample-by-sequence Cartesian products.

The optional analysis pipeline stage runs **after canonical loading and eDNA
materialization** and before provenance publication. It requires a validated
recipe and is not silently enabled in every existing pipeline run. Existing
metagenome pre-analysis artifacts remain separate.

## 6. API, UI, citations, and export

Proposed read-only routes under existing permissions:

- `GET /data/edna/analysis/catalog`
- `GET /data/edna/analysis/runs/{analysis_id}`
- `GET /data/edna/analysis/runs/{analysis_id}/tables/{table}`
- `GET /data/edna/analysis/runs/{analysis_id}/export`

Validate IDs, table/partition/sort allowlists, bounded pagination, and verified
artifact paths. Requests cannot name arbitrary files. Exports include exact
recipe/input/result IDs, method/rank/control policies and lineage. CSV formula
escaping and explicit truncation behavior remain mandatory; downloadable
complete partition artifacts carry their hashes and manifest. A filtered table
export is labeled as such and does not imply metrics were recomputed.

Add a compact eDNA analysis destination:

```text
/data?view=edna_analysis&analysis_id=<sha256>&table=diversity&result_id=<id>
```

Sections: `Composition`, `Diversity`, `Turnover`, `Methods`, `Controls`,
`Environment`. Show cohort, method, rank, control policy, sample count, and
units; use small plots only where they explain the data. No marketing copy,
duplicate evidence headings, decorative summaries, or unexplained trust scores.
Method/control distinctions must not rely on color alone.

The UI selects completed analysis runs; changing display filters does not
create a new scientific cohort. A missing matching analysis has a direct
unavailable state, not a substituted run. Restore exact analysis/table/result
state on cold load, refresh, Back, and Forward.

Context IDs use `analysis_edna_<analysis_id>_<kind>` (and distinct reliability
IDs if that context channel is used), with metadata containing source family,
input generation, recipe, method, rank, cohort, result IDs, and limitations.
Prompt selection must honor structured request scope and only use compatible
complete runs. An unavailable exact cohort stays unavailable; do not inject
every analysis file because the question contains “diversity.” Audit reports
citation/source consistency separately from scientific validity.

Extend published provenance so each cited result opens its exact table row,
recipe, contributing and excluded canonical records, source file hashes/row
locators, and any environmental-link profile. A digest without the recoverable
supporting membership is insufficient for research reproduction.

## 7. Implementation sequence

| Package | Work | Primary files |
| --- | --- | --- |
| 0 | Fix the three PR3 review findings and add regression tests | `api/schemas.py`, `api/edna_service.py`, `api/main.py`, `orchestration/unified.py`, both retrievers, `retrieval/edna_materializer.py` |
| 1 | Recipe, snapshot, cohort, taxonomy aggregation, membership and resource guards | new `analysis_contracts/edna_v1.json`, `preprocessing/edna_analysis.py`, `scripts/run_edna_analysis.py` |
| 2 | Detection history, diversity, similarities, paired-method report | `preprocessing/edna_analysis.py`, new deterministic scientific fixtures/tests |
| 3 | Control/standard reports and environmental metadata unit contract | new `preprocessing/edna_quality.py`, recipe validation and tests |
| 4 | Verified spatial/temporal/coverage linking and descriptive environment outputs | new `retrieval/edna_environment_linker.py`, `preprocessing/remote_sensing.py`, explicit observation metadata adapters |
| 5 | Immutable publication, source-qualified context and provenance | `ingestion/lineage.py`, `ingestion/provenance_snapshot.py`, `orchestration/unified.py`, `orchestration/answer_audit.py`, pipeline registration |
| 6 | Read APIs, exports, compact analysis view and exact navigation | new `api/edna_analysis_service.py`, `api/main.py`, schemas/types/clients, new `frontend/components/EdnaAnalysisView.tsx`, navigation modules |
| 7 | Full verification, evaluation fixtures, docs and handoff | backend/frontend/integration tests, `evaluation/`, `docs/TESTING.md`, `docs/SECURITY.md`, roadmap/handoff |

Do not extend legacy metagenome functions by merely admitting another source
string: their inputs and reliability assumptions differ. Analysis results are
regenerable artifacts, not new per-detection embeddings. A small additive
migration may be needed for publication-generation coordination in package 0;
do not alter scientific canonical identities or overwrite PR1/PR2 tables.

## 8. Acceptance gates

- Reproduce and fix the three review failures; test both query wording and
  structured source filters, including empty and mixed-source results.
- PostgreSQL/local/API/export date selection agree on UTC intervals and nulls.
- Concurrent materializers, interrupted file writes, pointer corruption, and
  stale generations fail safely; empty-corpus publication is valid.
- Analytic fixtures: `[1,1]` gives richness 2, Shannon `ln(2)`, Simpson 0.5,
  evenness 1; `[1]`, zeros, unresolved ranks, duplicate taxon sequences,
  conflicting lineages, missing methods and unequal libraries are explicit.
- Jaccard/Bray–Curtis identity/disjoint/empty cases and raw-versus-relative
  behavior are tested against hand-computed results/reference functions.
- Paired methods join exact sequence hashes, retain one-sided rows and count
  discrepancies, and never label agreement accuracy.
- Unknown/unpaired/absent controls and unknown expected standards cannot
  yield a pass badge; filtered outputs never change canonical rows.
- Missing CTD position, bay centroid, distant samples, out-of-footprint SST,
  invalid pixels, date precision, depth mismatch, reversed coordinate axes,
  JST/UTC boundaries, and non-overlapping eras are negative linking fixtures.
- Input/order permutations reproduce the same logical result and identity;
  changed source rows/recipes invalidate current context while old runs remain
  verifiable. Test all active scopes, not only the latest import.
- Every output row traces to recoverable source inputs and exclusions; API,
  CSV, citation, and browser state resolve the same result/recipe.
- Full backend coverage gate, isolated PostgreSQL tests, Ruff, dependency
  checks, frontend tests/typecheck/build, browser/accessibility checks, and
  secret/diff checks pass. No live ANEMONE/GCP requests in test fixtures.

Evaluation prompts must cover: method-dependent assignments, unknown controls,
read counts versus abundance, unresolved species richness, zero versus missing
sampling, and an eDNA sample outside SST coverage. Expected answers must cite
the precise analysis and state when the result cannot support the requested
claim. A deterministic citation audit is not scientific validation.

## 9. Decisions and later work

Implementation can begin with package 0 and the explicit descriptive baseline
without a download credential. The proposed genus baseline, environmental-only
cohort, no extra low-read cutoff, and no automatic control subtraction are
visible recipe choices, not unreviewable defaults.

Before enabling optional scientific interpretations, obtain:

- reviewed control-pairing and expected mock/standard metadata where needed;
- source-backed site/replicate identity and environmental units;
- approved distance/time/depth/domain thresholds and trustworthy CTD/SST
  observation metadata for each enabled linkage profile;
- a study/replicate and multiple-testing design for future inferential claims.

PR5 remains: approve the bounded pilot cohort and current provider use/citation
conditions, regenerate credentials, inventory/download, back up/migrate/load
Cloud SQL, execute analyses and embedding refresh, evaluate, verify provenance
and exports, configure manual Cloud Run Jobs, deploy and release `v0.4.0`.
Successful engineering tests do not replace the live-cohort scientific review.
