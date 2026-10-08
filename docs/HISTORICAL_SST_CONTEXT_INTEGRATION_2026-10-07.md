# Historical SST context integration preparation — #103

Updated 2026-10-07 JST. The NASA regional-context acquisition completed at
19:49 JST. The new integration operator prepares bounded, immutable **local
review inputs** from that private archive. Historical scientific publication,
native patches, and historical-data Chat acceptance remain pending. Production
is v0.7.3; acquisition/staging tooling from PR #115 is merged and deployed.
The follow-on diagnostic processor described below is a separate implementation
for review; it does not publish historical scientific evidence.

## Completed raw archive

- Requested calendar: full 2017–2023 years, 2,554 requested dates plus two explicit
  exclusions, 2021-02-20 and 2021-02-21.
- Retained raw: 2,554 files / 1,029,809,920 bytes; 2,521 final `04.1` and 33
  separately classified interim `04.1nrt` files. No unexpected requested-date gaps.
- Final-series gaps: 35 dates, including the two excluded February dates. Their
  separately recovered interim originals are not final replacements.
- Completion verification checked 2,554 receipts/checkpoints and 10,216 retained
  constituent file generation/size bindings. The acquisition worker verified raw
  SHA-256 read-back; its writer lease is released.
- Context uses 0.05-degree grid-point subsampling within 17.40–45.60°N,
  123.75–148.75°E. Subsampling is not spatial averaging or native sample-area
  coverage. NOAA native recovery is still pending.

Source plan:
`9764ab4f4bb7890f9f06f3bb395b0e11581bdc5b05543d1af38c51b9a6a272c1`.
Terminal reconciliation:
`bcd49fce7dc7a1abd7ecca0ea8a5e94b2cbaa882674f3d934f17e9ba3fe436e3`.
Private archive:
`gs://data-infra-infobio-ocean-data/research-sst/issue103/hybrid/nasa-context/9764ab4f4bb7890f9f06f3bb395b0e11581bdc5b05543d1af38c51b9a6a272c1`.

The retained ANEMONE acquisition inventory is the 2026-10-06 census, not a fresh
scientific approval. Refresh current publication/review bindings before applying
reviews or constructing a scientific panel.

## Bounded archive-to-review operator

`scripts/prepare_historical_sst_context.py` defaults to an offline preflight. It
validates the exact complete reconciliation and plan, classifies every date, and
selects final files into calendar-month batches with at most 31 days and 16 MiB
of raw data. It preserves all excluded/interim dates and required reviews.
Offline metadata consistency alone does not establish retained raw verification.

```sh
.venv/bin/python scripts/prepare_historical_sst_context.py \
  --context-plan /absolute/path/context-plan.json \
  --reconciliation /absolute/path/context-reconciliation.json \
  --output /absolute/path/integration-preflight.json
```

Execution requires one exact batch ID and the original archive namespace. It
reads the durable terminal report, verifies immutable retained bytes/receipts,
checks each checkpoint, and inspects actual NetCDF product generation, timestamps,
units, fields and grid. Unknown/interim generations cannot masquerade as final
evidence. Existing designated GCS authentication is required; no Earthdata token
or additional provider download is needed.

```sh
.venv/bin/python scripts/prepare_historical_sst_context.py \
  --context-plan /absolute/path/context-plan.json \
  --reconciliation /absolute/path/context-reconciliation.json \
  --archive-uri gs://BUCKET/research-sst/issue103/hybrid/nasa-context/PLAN_SHA256 \
  --batch-id EXACT_PREFLIGHT_BATCH_ID \
  --staging-root /absolute/path/context-review \
  --output /absolute/path/staging-receipt.json \
  --execute
```

The sealed local package retains raw files and per-request original acquisition,
diagnostic and receipt provenance. Its 24 MiB package cap includes metadata.
Non-symlink paths and immutable bundle verification prevent silent replacement;
repeated staging must match the existing sealed package. No database access,
cloud writes, scientific matching, registry approval or corpus publication occurs.

`review-inventory.json` deliberately has
`status=staged_unapproved_context_review_inputs`. It cannot be passed directly to
the existing scientific panel operator, which requires a completed approved-path
input and current applied product/sampling reviews. Do not rename its status to
bypass review or relabel subsampled context as native evidence.

## Integration verification

The actual archive preflight selects 2,521 final days in 84 monthly batches;
the largest batch contains 12,831,662 raw bytes. Integration plan ID:
`4b9044deba44b1afc02362e4d2a43edc23076e3b8377daf39db7d2d58abf0c74`.
One real February 2021 batch was staged with **26 final files / 10,567,854 raw
bytes**. Both excluded February dates remain explicit. The sealed manifest is
`ed927a189b43dafd30badde984567d366822d60858641c2a6eacc52ee2900c74`.
This is technical staging evidence, not a scientific SST panel or Chat publication.
The existing panel CLI was also exercised against this real review inventory;
it rejected the unapproved staging status before accessing registry/database data
and produced no panel output.

The focused integration/acquisition/panel/collection/research-Chat regression
group passed 34 tests. Tests exercise incomplete/tampered reconciliation,
duplicate identities, bounded splitting, durable report mismatch, immutable
staging/reuse and rejection of actual interim raw headers labelled final.

## Verified daily diagnostic processor

`scripts/preview_historical_sst_context.py` consumes the source context plan,
terminal reconciliation and one exact local staging receipt. It independently
verifies the sealed manifest, exact package file contract, original receipts,
request/checkpoint bindings and actual final NetCDF headers/units/timestamps/grid.
It uses the verified retained bytes for diagnostics, with the same 31-day,
16 MiB raw / 24 MiB package limits as staging. It has no database, network,
credential, scientific review or publication operation.

```sh
.venv/bin/python scripts/preview_historical_sst_context.py \
  --context-plan /absolute/path/context-plan.json \
  --reconciliation /absolute/path/context-reconciliation.json \
  --staging-receipt /absolute/path/staging-receipt.json \
  --output /absolute/path/context-diagnostics.json
```

The optional `--bounds /absolute/path/rectangle.json` accepts exactly `south`,
`north`, `west` and `east`, inside the acquired footprint. The default is the
entire acquired rectangle. This is a diagnostic selection, **not an approved
Miyagi boundary or sampling area**. No interpolation supplies points between the
retained 0.05-degree grid points.

Each final date retains source URL, actual generation, raw hash, granule identity,
request hash and original receipt hash. The report gives mask counts, finite and
missing ocean temperature counts, temperature quantiles/mean in degrees Celsius,
analysis-error statistics in Kelvin differences, and missing/invalid error and
ice diagnostics. Temperature summaries use equal weights for finite points with
`mask=1`; uncertainty/ice summaries use their own finite ocean points. No
uncertainty, ice, valid-fraction or scientific quality acceptance threshold is
chosen. Negative error values and out-of-range ice fractions remain visible.
Empty/missing support yields null summaries, never zero temperatures or imputation.

These summaries describe sampled grid points, not an area-weighted SST estimate,
independent satellite observations, sample-time SST or native coastal coverage.
The output is explicitly `unapproved_context_diagnostics` and cannot enter the
scientific panel CLI. It carries all 35 unsupported final-series dates. Monthly
coverage distinguishes archive exclusions/interim generations from final dates
in another bounded batch; partial-month outputs cannot imply archive-wide gaps.
The CLI rejects overwriting inputs, sealed packages and symlink output paths.

### Real retained-byte diagnostic acceptance

The retained February 2021 package produced 26 final daily summaries with exactly
two final-series gaps: February 20 and 21. Diagnostic identity:
`3adcb98225837562421cdd511a4f6aa228c1c0318a2fddcace7c735d64e334e9`.
For February 1, the full acquisition rectangle has 283,065 retained grid points,
240,029 ocean points and 240,029 finite ocean temperatures. This is a technical
numeric/coverage check, not a scientific regional temperature claim. Original
raw/acquisition receipts and sealed hashes were independently rechecked locally;
remote generations were not refreshed by the diagnostic processor.

Implementation verification passed the full backend suite: 1,196 tests passed,
39 PostgreSQL opt-in tests skipped locally, 80.11% total coverage. New regression
tests cover numeric units, independent missing-value denominators, empty support,
partial-month coverage, rejected stale/resealed provenance, unsafe output paths,
and explicit scientific/publication flags. Active Python lint passed. PostgreSQL
integration and other repository CI checks are run separately in GitHub.

### Concrete reviewer inputs before serving

The subsequent [analysis policy](HISTORICAL_SST_ANALYSIS_POLICY_2026-10-07.md)
records the user's answers to all 20 questions and the control/filter clarification.
The user has now accepted the provisional QC, weighting and comparable-cohort
defaults. The policy records those decisions and remaining implementation work. Confirmed controls
stay separate; other records are provisional; two filters count as one collection.

#### User decisions recorded after the diagnostic implementation

The user selected the following handling on 2026-10-07:

- **Reviewer label: `ANEMONE`.** Use this organization label in prepared review
  metadata. The selection came from the user; it does not establish that the
  ANEMONE provider supplied or endorsed an SST method. Actual approval/application
  actors and evidence references remain separately recorded by the registry
  workflow. A separate personal reviewer name is not required for this label.
- **Empty target tables: display `empty`.** Preserve the raw table and sample/
  assay/source identities, and defer interpretation of assay success. An empty
  table alone establishes neither fish absence nor a faulty assay. Pending that
  distinction, the existing frequency pipeline excludes unresolved empty tables
  from both positive and non-detection denominators; it does not insert zeros.
- **Faults: retain an evidence-backed review list.** Record confirmed parsing,
  file-integrity or provider-reported assay faults separately from empty tables.
  Include the affected sample/assay/method, source binding, reason and review
  status. Missing metadata or uncertain assay quality is `needs_review`, not a
  confirmed biological fault. The retained census reports 83 empty tables per
  target method; it is not a census of 83 faulty samples. No confirmed biological
  fault list was supplied with this decision.

The downloaded context is sufficient input to begin regional historical SST
processing: 2,521 final daily files across 2017–2023, with 35 explicit final-series
gaps. Native-resolution patches provide additional coastal/sample-area support
where the chosen analysis requires it. Software normalization/publication and
the product/QC/area/time definitions below are still required before historical
Chat acceptance. The download's completeness is separate from those steps.

Retain evidence references when implementing and applying the selected definitions;
do not treat the chosen display label as provider endorsement.

| Decision | Required recorded input |
| --- | --- |
| ANEMONE denominator (#102) | Environmental eligibility, physical sample IDs, replicate/resequencing relationships, representative assays, and valid empty target tables. |
| Comparable areas/cohort (#102) | Worldmesh meaning, geographic footprints including Miyagi, and comparable season/area sampling across 2020–2023. |
| SST scope (#103) | Whether coarse regional context is sufficient for a particular analysis, and which comparisons require native patches. |
| Product/generation (#103) | MUR daily foundation analysis semantics and final-only policy; explicit handling of 33 interim dates and two additional exclusions. |
| QC/weighting (#103) | Accepted provisional defaults: open-sea mask, uncertainty ≤1 K (0.5 K sensitivity), ice ≤0.15 where available with missing-ice warnings, 80%/five-point support, cosine-latitude grid-point weighting. Bind exact product/area definitions and coastal support limitations. |
| Temporal matching (#103) | Accepted provisional Japan calendar/midday assumption and 24-hour matching; 48-hour retry only above 20% temporal misses. Local preview implementation passed; record exact registry/recipe versions for serving. |

Apply the resulting reviews through the existing researcher/admin registry
workflow against fresh publication bindings. A download choice or software
implementation instruction does not substitute for these scientific records.
After approval, normalize bounded panels/collections under the approved delivery
semantics, link reviewed samples, publish controlled evidence, and run historical
Chat acceptance. Do not infer fish abundance or a causal weather effect directly
from eDNA detection frequency or SST association.

## Remaining scientific and serving handoff

1. **#102:** establish environmental eligibility, independent physical sample
   identities and representative assays; resolve empty target tables, worldmesh
   meaning, reviewed area geometry and comparable sampling cohorts. Occurrence
   rows are not independent samples or validated non-detections.
2. **#103:** apply the user-accepted provisional product/QC/weighting/calendar
   choices to exact versioned definitions and verify full-period coverage,
   sensitivities and subsampled-context support limitations. Acquire/qualify native
   patches where the approved scientific scope requires them.
3. Bind actual researcher approval and admin application to current source
   publications and exact registry definitions. Normalize/link only reviewed
   inputs into bounded immutable panels/collections; retain excluded dates and
   provenance throughout. Do not invent review records from test fixtures.
4. Run deterministic analysis and controlled scientific publication. Record the
   resulting panel/collection and publication IDs before claiming historical
   evidence is available in Chat; follow the authorized software release workflow.
5. Repeat historical Chat acceptance with source/filter coverage, citations and
   explicit gaps, then assess the six real-data demonstrations in #89.

Six production Chat checks already exercised the existing published SST/eDNA
integration, including strict date filters and missing-source abstention. They
did not test newly published historical data. Unfiltered retrieval returned
2025–2026 SST; asking about a historical year in natural language alone does not
replace explicit date filters or prove archive-wide absence. Missing retrieved
eDNA was not treated as proof that real sampling overlap is absent.

The completion monitor is paused after reconciliation and this QA handoff.
#89, #102 and #103 remain open. The Overview change is already shipped in v0.7.3;
this follow-on integration work does not change its page or serving state.
