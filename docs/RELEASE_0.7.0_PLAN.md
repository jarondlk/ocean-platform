# Accepted v0.7.0 plan — ANEMONE detection patterns and SST

Prepared 2026-10-04 against `main` at
`55d41469fb0694444e8c5b2211002179f09a776e`.
Status: accepted plan; implementation candidate in progress. Local synthetic
verification is recorded in [the implementation record](RELEASE_0.7.0_IMPLEMENTATION.md).
Real scientific approvals, release publication and deployment remain pending.

The requirements are [issue #89](https://github.com/jarondlk/ocean-platform/issues/89)
and its [research-reference feedback](https://github.com/jarondlk/ocean-platform/issues/89#issuecomment-5945141912).
The [planning investigation](V0.7.0_DISCOVERY_2026-10-04.md) records the code/data
evidence, reference-reading limits and dated production assumptions.

## Intended outcome

OCEAN should answer the issue's six questions with reproducible calculations,
coverage-aware maps and time series, downloadable tables, and citations to both
ANEMONE and the SST inputs. Chat and the Data analysis view must use the same
published calculation. Users can inspect or change the explicit analysis scope;
unsupported or unavailable scopes receive a precise explanation.

This is a descriptive research release. Detection frequency is observed eDNA
detection under the recorded method and threshold. It does not establish fish
abundance, true occupancy, migration, climate attribution or a causal temperature
effect. Replicating the papers' distribution models is separate future work.

## Requirements translated into outputs

| ID / issue question | Calculation | Required presentation |
| --- | --- | --- |
| Q1: top ten fish in a region, 2020–2023 | Rank taxa by distinct eligible physical samples with detection; calculate year/season frequencies for this fixed list | Ranking with detected/eligible counts, frequencies, protocol/method and coverage; seasonal/yearly series |
| Q2: high/low SST and a representative series | Retain Q1’s fixed top-ten list; apply one declared temperature partition to valid SST-linked members; rank descriptive frequency differences with support thresholds | High/low numerators and denominators, unmatched samples, selection rule, gaps, aligned frequency/SST panels |
| Q3: best-covered month in 2023 and sardine by area | Select month by eligible sampled-area count, independently of sardine detections or SST availability; aggregate every sampled area | Month coverage table, map and per-area detected/eligible counts, including observed zeros |
| Q4: spatial temperature conditions | Compare frequencies in declared SST ranges, retaining sampled non-detection areas and excluding only missing/invalid SST from the temperature comparison | SST map, bin table, sample/area counts, linked coverage and source/product labels |
| Q5: three largest distribution changes, 2020 vs 2023 | Fix comparable area-season strata; rank absolute frequency changes across those strata | Ranking rule, matched/excluded strata, per-area signed changes and sample effort |
| Q6: 2021–2022 follow-through with SST | Retain Q5's taxa/area-season panel and add intermediate-year data plus SST | Comparable year panels/time series, unobserved gaps, temperature context and qualified interpretation |

Region, species and years remain selectable examples. The original examples
must be attempted in preflight. Alternatives may be proposed with their coverage
reason, but never silently substituted in an answer or accepted as the original case.
The spatial workflow's geographic extent is explicit: the regional time-series
selection does not implicitly determine or widen the monthly spatial selection.

## Scientific and data contracts

### Analysis unit and denominator

For taxon `t` in group `g`:

`frequency(t,g) = detected eligible physical samples(t,g) / eligible physical samples(g)`.

The denominator is constructed **before** joining/filtering taxon detections.
It includes eligible samples with complete, valid processed target results but
no qualifying assignment to the taxon. An unavailable/missing method table or
failed protocol/QC does not become a negative detection. A valid empty target
table is separately identifiable; its inclusion needs the declared assay-quality
policy, not an inference that sequencing succeeded or fish were absent.

- Source occurrence IDs and assay IDs remain distinct and immutable. A physical
  sample may map to multiple occurrences/assays only through reviewed evidence.
  Matching names, dates or grid values generate review candidates, not approvals.
  Even a singleton occurrence needs evidence for its declared sampling unit.
- Default to one representative eligible assay per physical sample within a
  comparable protocol stratum. Selection must be fixed independently of taxon
  detections, based on reviewed original/resequencing semantics. Conflicting or
  unreviewed choices block/exclude that unit with a reason. Do not pick the assay
  with the largest positive taxon signal. An any-assay union is a separately
  versioned sensitivity policy, not an invisible default.
- Keep QCauto and QCauto+3-NN separate. They assign the same sequence evidence;
  their detection/read totals must never be added as independent observations.
- Pin taxonomic resolution, fish-lineage inclusion policy, accepted taxon keys,
  aliases, minimum read threshold and whether the threshold applies per sequence
  row or per assay/taxon. Start with the existing minimum-one-read policy,
  explicitly serialized. Unresolved species assignments do not become resolved
  species or genus-level substitutes.
- Require the shared environmental-only eligibility contract and complete
  method/protocol inputs. Controls and unknowns remain visible in exclusions.
  Classification approval and physical identity approval are separate decisions.
- Publish total occurrences, assays, resolved physical samples, eligible samples,
  unknown-identity exclusions, protocol exclusions and SST-linked samples.
  Incomplete identity coverage must be obvious. Do not label an occurrence-based
  diagnostic as the issue's sample detection frequency.

### Areas, calendar and sampling effort

- Use a versioned region/area registry with references, geometry hashes, stable
  IDs, coordinate basis and uncertainty. Confirm provider worldmesh semantics;
  if only coarse cells are supported, present cell footprints rather than exact
  sampling pins. Do not infer a Miyagi coastal membership from a convenient box.
- Proposed analysis calendar: `Asia/Tokyo`, MAM/JJA/SON/DJF, with winter labelled
  by its January year. Include the previous December only when it is actually
  available; mark partial edge seasons. Preserve UTC source times and precision.
  Date-only values need a documented calendar interpretation, not an invented
  timestamp. Existing v1/Chat time-filter semantics remain readable unchanged.
- Build area × period coverage independently of detections. Distinguish
  `sampled_detected`, `sampled_not_detected`, `unsampled`, `ineligible_only`,
  `method_unavailable`, and `sst_unavailable` as separate dimensions/statuses.
  `N=0` produces a null frequency, never zero.
- Show sample-weighted regional frequency and, for comparison, an explicitly
  labelled equal-area/stratum standardized frequency when a valid matched panel
  exists. Use the same matched strata/weights in both endpoint years. Preserve
  raw counts so unequal effort is visible; normalization does not remove all
  sampling bias or protocol/detectability effects.
- Minimum-support rules are part of the recipe. Proposed starting flag: fewer
  than three eligible samples per area-period is low support. Such cells can
  show raw descriptive rates, but enter comparative rankings only under a
  reviewed threshold policy. Final thresholds depend on V070-00's census.

### SST product and matching

The current local files cover December 2025–February 2026; inspected endpoints
identify JCOPE-T model assimilation. Obtain actual historical coverage before
attempting the 2020–2023 comparisons. The
[JAXA product guide](https://www.eorc.jaxa.jp/ptree/userguide.html) distinguishes
Himawari geophysical SST, hourly/daily/monthly aggregation and model products.
Prefer a verified historical Himawari geophysical product for the literal
satellite workflow. Confirm archive access, actual granules, variables and
quality masks in V070-02; the guide alone is not proof that required files are
accessible to this account.

[NASA/JPL MUR v4.1](https://podaac.jpl.nasa.gov/dataset/MUR-JPL-L4-GLOB-v4.1)
is a fallback candidate with historical coverage. It is a Level-4 foundation-SST
analysis combining satellite and in-situ inputs, not a direct skin-temperature
observation. Selecting it changes the disclosed scientific comparison; it needs
a product-specific reviewed recipe. JCOPE-T remains a distinct model product.
Do not silently mix these products, versions or measurement types.

- Record provider/product/version, processing level, measurement type, units,
  calendar, CRS/grid, spatial/temporal resolution, valid interval, quality masks,
  land/coast masks, uncertainty, raw granule hash and exact source pixel/window.
- Decode file time coordinates and compare them with filenames. Validate scale,
  offset, fill values and units before conversion to degrees Celsius. Never use
  thermal-band brightness temperature as a retrieved SST substitute.
- Match SST to the reviewed sample area/footprint and collection interval with
  explicit quality, valid-fraction, uncertainty and time-window rules. For coarse
  ANEMONE locations use qualified area/ocean-pixel aggregation, not precise nearest
  station claims. Reject out-of-footprint nearest-pixel extrapolation.
- Preserve distinct sample-time SST and full-month/season regional context.
  Satellite surface context is not a same-depth CTD/bulk-water measurement.
  Extend the linkage contract for this reviewed comparison; do not globally
  remove current depth/coordinate safety checks to obtain matches.
- For daily/monthly composites, pin weighting, minimum valid ocean pixels and
  valid days, aggregation statistic and whether provider composites or OCEAN
  composites are used. Gaps remain gaps. No hidden interpolation or zero filling.
- Keep all-eDNA and SST-matched denominators separate. Temperature bins include
  only valid linked units but retain detected and non-detected eligible members.
  Report missing SST by area/period and avoid presenting biased matched subsets
  as the complete regional sample population.

### Exact algorithms for the three workflows

1. **Regional series:** rank by distinct detected physical samples over the full
   eligible selected period; break ties by stable taxon key. Freeze that list
   before year/season splitting and return fewer than ten if fewer qualify.
   Provide year, season and calendar-month series with counts, partial periods
   and support flags. Taxon filters must not shrink the sample denominator.
2. **Temperature contrasts:** serialize fixed Celsius ranges or a declared
   cohort-derived partition. A proposed exploratory high/low option is bottom/
   top SST thirds over the eligible matched sample cohort, with deterministic
   percentile/tie handling, middle/excluded counts and the exact cut points.
   Use identical boundaries for all compared taxa. Show pooled and supported
   area/season strata to expose confounding; differences are percentage-point
   contrasts, not significance or causal estimates. Select the representative
   time series by the declared largest supported contrast/tie rule, and state
   that selection; do not search repeated thresholds for the strongest story.
3. **Best month and spatial SST:** maximize the number of distinct reviewed
   areas with at least one eligible sample, then eligible sample count, then
   earliest month. Also show the support-qualified coverage ranking if a minimum
   count is applied. Do not select the month using positive sardine records or
   SST completeness. Publish every sampled area, including detection-zero areas.
   Compare either sample-time temperature bins at sample level or full-month
   area SST bins at area level; expose both as different outputs, with their
   unit/weighting. Never count repeated samples as independent areas.
4. **Matched changes:** define endpoint-comparable area × season × protocol
   strata first. For each candidate species calculate
   `D(t) = mean_s(abs(f(t,s,2023) - f(t,s,2020)))` over the fixed eligible matched
   strata with equal weights. This is a proposed descriptive change score;
   record the score/weights/thresholds in the recipe, break ties by taxon key
   and return up to three supported species. Show signed per-stratum changes
   in percentage points. The endpoint ranking does not depend on SST matches.
   Follow the same taxa/strata through 2021 and 2022; missing intermediate data
   remain null. A complete-four-year panel is an additional explicitly narrower
   sensitivity view. Do not treat read-composition Bray–Curtis as this metric.

Formal significance, occupancy correction, general species-distribution models
and causal inference are outside v0.7.0. Do not draw inferential confidence bands
without a reviewed sampling/replicate model; coverage counts and sensitivity
views remain available for descriptive interpretation.

## Implementation work packages

### V070-00 — Feasibility and accepted demo recipe (first gate)

- Inventory the current canonical publication and retained archive read-only:
  exact source generations, classification, identity, method/protocol completeness,
  date precision and coverage by region/area/month/season/year.
- Produce `V0.7.0_DATA_READINESS.md` and a machine-readable coverage matrix.
  The local investigation's 118 occurrences/111 reported names in a provisional
  box and May's raw coverage lead are leads only, not sample/area conclusions.
- Test all six original examples. Determine which need identity/classification
  evidence, wider SST extent or a different period/taxon. Prepare alternatives
  with explicit coverage tradeoffs. Avoid promising an adequately matched
  2020/2023 regional panel before it is measured.
- Finalize unit, representative-assay policy, geography, calendar, rank, method,
  protocol grouping, support thresholds, SST product and contrast definitions.
  Record unresolved provider questions separately from implementation choices.
- Obtain a small published-version/supplement reading record for the third
  reference before reusing its detailed protocols. Literature is background
  context, not additional evidence silently entering source-scoped answers.

Exit: a versioned demonstrable cohort/recipe, or a precise data-blocked disposition
for each requirement. Missing scientific evidence can block real-data acceptance;
fixture development and contract work can continue.

### V070-01 — Reviewed identity, eligibility and area registry

Primary areas: `db/models.py`, `db/app_models.py`, Alembic migrations,
`preprocessing/anemone.py`, `anemone_classification.py`, `edna_eligibility.py`,
classification review/application services and pipeline commands.

- Add reviewed physical-sample entities/membership decisions with evidence
  references, source hashes, reviewer, rationale, immutable versions and
  representative-assay decisions. Reuse existing optional canonical identity
  fields; retain source occurrence keys, assay rows and raw metadata.
- Add a hashed, versioned region/area registry with uncertainty. Separate spatial
  membership review from classification and identity decisions.
- Candidate persistence layout: physical-sample entities, reviewed occurrence
  memberships/assay choices, versioned area definitions and their decision
  references. Bind active decisions to publication generations rather than
  overwriting raw provider identities or historical input snapshots.
- Reuse the authenticated draft/review/preview/apply workflow for environmental
  classification. If the accepted cohort needs batch reviews, prepare an exact
  member/evidence manifest and preview effects; approval must apply only to its
  verified members. Names/coordinates/non-control status alone are insufficient.
- Ensure future normalization/refresh preserves a matching applied decision;
  changed source evidence becomes pending/stale instead of inheriting approval.
  Extend affected-analysis regeneration dispatch for the new analysis kind.
- Add additive constraints/indexes and migration/restore tests. Keep existing
  reviewed lineage and v1 IDs valid. Confirm permissions remain default-deny:
  researcher decisions and admin application retain their existing separation.

Exit: the accepted analysis cohort has evidence-backed unit/eligibility/area
decisions and exclusions; idempotent publication and stale-decision handling pass.

### V070-02 — Historical, product-aware SST preparation

Primary areas: `preprocessing/remote_sensing.py`, `scripts/ingest.py`, new bounded
SST preparation command/contract, source manifests and `db/models.py`.

- Acquire one reviewed historical product for the necessary extent/period,
  beginning with a small representative pilot. Estimate bytes, requests, storage
  and processing cost before the multi-year batch; use spatial/time subsets
  rather than global hourly downloads. Authentication uses provider-supported
  credentials outside Git. Keep runtime serving independent of provider access.
- Implement validated product adapters and distinct labels for observational SST,
  satellite-derived analyses and model output. Preserve older artifacts rather
  than relabeling their immutable citations without a source check.
- Candidate SST layout: product/version, source granule/checksum, immutable
  area/time observation and quality/membership metadata. Keep the existing
  point/daily tables readable; do not key all new observations by date alone.
- Persist raw inventory and quality/coverage summaries; prepare reusable
  area/day/month SST panels with source/pixel membership and immutable hashes.
  Add normalized product/source keys where existing point/daily tables cannot
  represent multiple products/areas without collisions.
- Test units/time disagreement, descending axes, fill values, masks, corrupt
  files, coastal pixels, missing days, revised granules and idempotent updates.

Exit: a verified historical SST panel overlaps the accepted ANEMONE cohort and
can be traced to actual granules; missing intervals/products are explicit.

### V070-03 — Reviewed sample/area-to-SST linkage

Primary areas: `retrieval/edna_environment_linker.py`, new product-aware recipe
models and environmental provenance helpers.

- Extend linkage profiles with measurement type, aggregation/window semantics,
  area geometry/hash, quality thresholds and the reviewed spatial uncertainty.
- Produce selected links and exclusion rows deterministically, including
  missing/invalid data, unsupported depth comparison and no valid footprint.
- Bound/window candidate searches with SQL/spatial/time indexes or partitioned
  panels. Avoid the current all-samples × all-observations nested comparison.
- Keep one declared environmental value per analysis unit/window; repeated
  observations/composites do not multiply the physical sample denominator.

Exit: independently checked joins for a small real cohort and fixtures, with
complete link provenance and honest missing coverage; legacy strict joins pass.

### V070-04 — Deterministic detection-frequency engine

Primary areas: new `preprocessing/edna_detection_frequency.py` and strict
versioned recipe models, parameterized snapshot/query helpers, and existing
eligibility/taxonomy modules.

- Implement denominator membership, sparse taxon-presence reduction, coverage,
  rankings, time series, temperature bins, matched strata and signed changes.
- Read one consistent published canonical generation and immutable SST panel;
  store all identity/area/decision versions. Never use top-K retrieval prose or
  LLM-generated SQL to calculate these results.
- Keep sample-level reduction and aggregate counts independent of join order.
  Use complete source method tables, deduplicate biological units and preserve
  protocol partitions. Avoid constructing an unbounded dense sample × taxon grid.
- Add query/explain and representative-size benchmarks. The v1 200-assay limit
  stays intact; the new workflow has separate measured ceilings, bounded ordered
  batches and explicit failure. Initial sizing should support the retained
  3,498-occurrence/349,638-assignment catalogue; final row/byte/time/output caps
  follow the benchmark rather than becoming arbitrary user-controlled settings.

Exit: hand-calculated fixture results match every required numerator, denominator,
ranking and gap; the accepted real cohort completes within recorded limits.

### V070-05 — Immutable publication, APIs and history

Primary areas: `ingestion/edna_analysis_bundle.py`, artifact store registration,
`scripts/run_edna_analysis.py` or a new research-analysis CLI,
`api/edna_analysis_routes.py`, schemas, provenance and chat-record handling.

- Introduce an analysis-kind/schema-version dispatcher: existing v1 artifacts
  retain their bytes/hash validation/table set; new detection-frequency bundles
  use their own strict codec. Do not change the global table constant in a way
  that invalidates historical bundles.
- Publish recipe, input generations, membership/exclusions, coverage, frequencies,
  temperature strata, matched changes, source links and result IDs atomically.
  Hash algorithm/runtime/recipe/all input and decision versions. Keep a compact
  provenance index with paged exact membership rather than oversized chat context.
- Expose bounded catalog/preflight/detail/table/series/map/provenance/export
  responses. Paginated tables, total counts and explicit truncation must agree;
  a complete bundle export remains available within server size caps.
- First release uses manual batch preparation/publication and read-only serving,
  matching current operations. Data controls select published recipes/results;
  a recipe change requiring recomputation shows unavailable/pending publication.
  Chat performs no remote downloads, ingestion, embedding or large grid work.
- Persist analysis/result IDs, effective scope, statuses and evidence snapshots
  with each answer. Preserve v0.5/v0.6 history, aggregate downloads and links.
  Add any new persisted outcome values through tested constraints/migrations.
- Preserve the existing role boundary: viewers receive authorized inline Chat
  results; researcher/admin can inspect Data/provenance and export through their
  normal permissions. A Chat result ID must not grant new Data/export access.
  Render restricted navigation honestly instead of presenting broken links.
- Implement honest historical/stale/current-unavailable statuses and cache keys
  covering both data families and decision versions. An integrity/read error
  must not fall back to a broader live cohort. Classification, SST or registry
  changes invalidate only affected analyses, using version-aware regeneration.

Exit: deterministic rebuild produces identical results/IDs; changed inputs produce
new IDs; interrupted publication exposes no partial run; old/new readers pass.

### V070-06 — Coverage-aware Data workspace and Chat result cards

Primary areas: `frontend/components/EdnaAnalysisView.tsx`, Data/Chat components,
`frontend/lib/edna-analysis-navigation.ts`, API contracts and citation navigation.

- Add three workflows: Regional series, Monthly spatial comparison and Matched
  changes. Display region, period, species, method, analysis unit, read threshold,
  calendar, support policy and SST product with actual available choices.
- Offer published analysis selection and explicit preflight coverage. Replace
  the free-text analysis-ID entry with a searchable selection while retaining
  supported deep links and historical unavailable selections for review.
- Present maps/area footprints, aligned frequency/SST panels, year facets,
  coverage matrices, ranking/bin tables and exclusion summaries. Use accessible
  labels and a table alternative; unsampled regions and zero detections need
  visibly different legends. Do not interpolate lines across missing periods.
- Keep axes/colour scales consistent across comparable years, label percentage
  versus percentage-point change, and show `detected / eligible` in tooltips.
  Sampling-time SST and monthly context have distinct legends/units.
- Each chart/card links to the exact result table and input trace. CSV/JSON and
  static figure exports use the same result data; include recipe/hash/caption
  metadata and clear completeness limits for shareable presentation outputs.
- Preserve v0.6 account isolation/hydration and source selections. Selecting an
  analysis does not enable SST/eDNA or widen source filters automatically.
  Keyboard/mobile/loading/stale-response/empty/error behavior receives focused
  mounted-component coverage.

Exit: all three workflows are usable through normal role capabilities, and
numbers/statuses remain identical between Chat, table, chart and download.

### V070-07 — Structured Chat routing and claim support

Primary areas: `orchestration/edna_aggregation.py`, `api/main.py`, new research
query planner/service, `retrieval/source_scope.py`, `orchestration/answer_audit.py`,
citations, API schemas and frontend result-card contracts.

- Add typed intents for the six supported questions and bounded paraphrases.
  Resolve parameters from explicit controls and reviewed aliases; display the
  resolved plan. Conflicting natural-language dates/region/species/methods need
  clarification. Unsupported wording does not erase already-selected filters.
- Route calculations/ranking selection through exact published result queries.
  Deterministic numeric summaries are authoritative; optional model narrative
  receives only the selected results, coverage, source links and limitations.
- An SST comparison requires both eDNA and SST enabled and compatible scopes.
  If either is disabled/mismatched, explain the specific requirement. If a user
  requests only the eDNA component, supply a separately scoped eDNA result when
  available; never hide excluded SST inside analysis-context citations.
- Add exact row/result citations for the new tables and trace both ANEMONE and
  SST contributions. Do not treat citation syntax or a five-row excerpt as
  support for a complete-cohort claim. Guard major numeric statements and
  obvious unsupported causal/abundance claims; retain manual scientific review.
- Preserve the current count/presence and interpretation routes. Verify CTD,
  metagenome and ordinary SST chat retain their chosen source/filter boundaries.
  Keep research-paper discussion distinct from selected database observations.

Exit: the six questions/paraphrases select the correct plan/results; missing or
conflicting scope yields useful abstention/clarification, and repeated narrative
answers have claim-level evidence support.

### V070-08 — Acceptance, security and performance

1. Create independently hand-calculated fixtures covering duplicate occurrences,
   resequencing, method alternatives, read thresholds, empty/missing tables,
   controls/unknowns, unresolved identity/taxonomy, differing protocols, positive
   and zero detections, unsampled strata and missing/invalid SST.
2. Test numerator/denominator invariants, date/season edges and partial winters,
   month/rank tie rules, minimum support, fixed matched panels, unequal effort,
   product/unit/quality differences, geometry uncertainty and no extrapolation.
3. Exercise PostgreSQL 16/pgvector migrations, parameterized queries, repeated
   upserts, decision invalidation, consistent generations, rollback and isolated
   restore. Test all relevant source combinations/filter conflicts and historical
   result/download compatibility. Failure paths do not write partial publications.
4. Require the six real-data case dispositions, independent count/trace checks,
   chart/table/export agreement and live candidate role/history checks. Synthetic
   fixtures cannot satisfy the issue's data demo. Test viewer/researcher/admin
   through existing designated identities; no role changes to manufacture QA.
5. Scientific QA: two paraphrases plus the canonical wording per question, run
   deterministic routing/count checks twice. For optional provider narratives,
   repeat each of the six accepted questions three times, plus six bounded
   interpretation/limitations cases: 24 planned calls, first-batch maximum 30
   including retries. Record actual invocations/cost and stop on unexpected
   failures before expanding. Map consequential claims to supplied rows/citations.
6. Record cold/warm preflight, calculation, publication, result API and Chat
   timings and memory on representative small/regional/catalogue inputs. Establish
   budgets in V070-00/04, distinguish measurements from load/p95 claims, and test
   bounded cancellation/failure. Reuse immutable panels and results for serving.
7. Complete backend/coverage/lint, frontend tests/typecheck/build, schema/contract
   generation, dependency consistency/audits and fresh CI/CodeQL on exact source.
   New endpoints/jobs retain default-deny auth, parameter validation, export
   protection and bounded paths; provider fetches use reviewed endpoints.
8. Before deployment, perform the maintenance container hardening: available OS
   fixes, unused frontend npm/tooling removal, investigation of inherited Perl,
   MiniZip and Python SBOM findings, full scans and startup/auth/backup checks.
   Record fixed findings and evidence-backed residual dispositions. Zero GitHub
   alerts is not a clean-container guarantee. Keep SQLAlchemy 2.0/psycopg2;
   its 2.1 driver migration is a separate project.

English scientific acceptance is the proposed initial scope. Japanese acceptance
was previously deferred and is not silently claimed or added to this release.
Existing name aliases/localization remain compatible. Prior role-QA deferrals
are historical: v0.7.0's changed UI/API gates require their own disposition.

### V070-09 — Release and manual GCP rollout

- Work in reviewable `codex/v070-*` branches. Merge through PRs with current
  required CI/security checks. Do not create a v0.7.0 tag during implementation.
- Prepare readiness/implementation/scientific-QA/operations records, release
  notes, migration/rollback runbook, data recipe manifests and updated screenshots.
  Bump package/API version only for the final candidate, not this planning draft.
- Refresh actual live infrastructure/auth/schema/publications/cost limits before
  execution. Build immutable images from exact merged source and verify fresh
  backup/restore before schema, identity/classification or data mutation.
- Use additive migrations and staged immutable data/analysis publication. Pin
  the compatible API/frontend/job source and manifest generations; verify old
  v0.6.1 application compatibility or prepare a tested rollback image. Traffic
  rollback alone cannot undo classification/SST/publication changes.
- Prepare a zero-traffic authenticated candidate with a concrete supported login
  path before UI QA. Temporary callback/access/job changes are bounded and
  removed afterward; do not repeat the earlier candidate-access ambiguity.
- Pass accepted real-data/UI/history/scientific/security gates before publishing
  the exact-source `v0.7.0` GitHub release and promoting GCP traffic. Any deferral
  must identify the unmet requirement and be newly authorized. A missing sample
  denominator or SST dataset cannot be reported as successful issue acceptance.
- Check production login/source scope, all new analysis links/downloads, prior
  histories, errors and data generations; align changed manual jobs, preserve
  rollback resources, sync branches and close temporary previews/resources.
- Close issue #89 only when its agreed demo cases are demonstrated and recorded.
  If the agreed example set changes, retain both the original and accepted
  alternative dispositions.

## Suggested PR sequence and dependencies

| PR scope | Packages | Dependency / review gate |
| --- | --- | --- |
| 1. Data contract and feasibility | V070-00, strict recipe/fixture scaffolding | Accepted unit/cohort/product decisions; external evidence gaps recorded |
| 2. Reviewed sampling/area foundation | V070-01 | PR1; additive migration, review lineage and regeneration compatibility |
| 3. Historical SST foundation | V070-02 | PR1; can develop beside PR2, but no live join until both data gates pass |
| 4. Linkage and exact analytics | V070-03/04 | PR2/3; independent numerical oracles and representative-size benchmark |
| 5. Publication/API/Chat integration | V070-05/07 | PR4; old/new artifacts, role boundaries, exact result citations/history |
| 6. Data/Chat visual workflows | V070-06 | PR5; mounted UI, coverage legends, exports and candidate acceptance |
| 7. Hardening and release candidate | V070-08/09 | Prior PRs; exact source, real-data demo, image scans and rollback rehearsal |

Keep container changes separately reviewable even if they are part of the final
release gate. Streaming chat, unattended provider refresh, raw FASTQ reprocessing,
paper-model reproduction and SQLAlchemy driver migration are separate follow-ups.
Do not commit a calendar estimate until provider evidence/access and feasible
coverage are known; those external dependencies determine the critical path.

## Completion checklist

- [ ] V070-00: real-data feasibility and demo recipe accepted.
- [ ] V070-01: reviewed sampling/eligibility/area foundation published safely.
- [ ] V070-02: verified historical SST product/panel available.
- [ ] V070-03: qualified, traceable environmental links pass.
- [ ] V070-04: all six deterministic analysis results validated.
- [ ] V070-05: versioned publication/API/history compatibility validated.
- [ ] V070-06: charts/maps/settings/export workflows accepted.
- [ ] V070-07: structured Chat routing and evidence support accepted.
- [ ] V070-08: scientific, role, performance and security gates dispositioned.
- [ ] V070-09: exact-source release, verified rollout and cleanup recorded.
