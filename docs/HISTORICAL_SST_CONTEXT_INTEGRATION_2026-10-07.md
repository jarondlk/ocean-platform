# Historical SST context integration preparation — #103

Updated 2026-10-07 JST. The NASA regional-context acquisition completed at
19:49 JST. The new integration operator prepares bounded, immutable **local
review inputs** from that private archive. Historical scientific publication,
native patches, and historical-data Chat acceptance remain pending. Production
remains v0.7.2; draft PR #115 has not been merged or deployed.

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

## Remaining scientific and serving handoff

1. **#102:** establish environmental eligibility, independent physical sample
   identities and representative assays; resolve empty target tables, worldmesh
   meaning, reviewed area geometry and comparable sampling cohorts. Occurrence
   rows are not independent samples or validated non-detections.
2. **#103:** review exact product generations, masks/uncertainty, valid-pixel rules,
   spatial weighting and sample-time/calendar tolerance. Explicitly review any
   use of subsampled context and its support limitations. Acquire/qualify native
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
#89, #102 and #103 remain open. The parallel Overview branch is outside this
integration change.
