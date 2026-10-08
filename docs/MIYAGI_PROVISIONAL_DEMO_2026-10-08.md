# Miyagi historical SST / ANEMONE provisional demo

Status: calculated and locally verified; live publication/rollout and Chat
acceptance are pending. Production remains v0.7.3.

The user chose yesterday's retained NASA regional context, Miyagi first in
2020–2023, and explicitly said **“can skip and approve all”** when asked about
recording a separate researcher review. This authorizes a provisional demo.
Its immutable input records the actual user instruction, recording timestamp,
source/region/period hashes and rationale. **ANEMONE is a display label**, not a
claim of provider endorsement or an invented researcher identity. Independent
researcher approval remains false. Formal review permissions and ledgers are
unchanged; canonical unknown classifications and physical IDs are unchanged.

## Processing and source reconciliation

- The NOAA execution `ocean-sst103-native-acquire-8lsm2` was cancelled and
  terminal cancellation verified at 2026-10-08 04:34:07 UTC. Its partial archive
  and checkpoints remain. The old competing full-resolution job is not resumed.
- The acquisition follow-up is paused so it cannot restart downloads. No new
  NASA/NOAA provider downloads are needed for this first demo.
- The retained NASA context plan is
  `9764ab4f4bb7890f9f06f3bb395b0e11581bdc5b05543d1af38c51b9a6a272c1`.
  The local processor re-read and verified the existing private archive bytes,
  processed 48 months and finished at 2026-10-08 05:05:59 UTC.
- Period preview:
  `7333e86cc1dff0bb6ab84b5b7a6f36ad0c500dae7f1c4235ca14d43d7a16a708`.
  All 1,455 final days meet the accepted provisional primary support rules.
  Counts are 366 / 363 / 364 / 362 days for 2020 / 2021 / 2022 / 2023.
- Six final-data gaps remain: 2021-02-20/21 (known acquisition exclusions),
  2022-11-09, 2023-04-22 and 2023-12-01/02 (retained interim generations).
  Interim bytes are never relabelled final or used to fill this series.
- A repeatable, read-only production snapshot refreshed 118 ANEMONE occurrences,
  118 assays and 10,866 detection rows. It reads no account or Chat-history data.
  Source hash:
  `334a1f0ebb84085e5f0f1163a90a085a7e721d0c0202ee2ae69014efd8924458`.
- 104 singleton occurrence proxies are retained across three protocol strata
  (9 / 56 / 39). Fourteen occurrences in seven repeat groups remain excluded:
  no actual sequencing/processing timestamps establish the newest assay.
  These proposals are not persisted as confirmed physical memberships.
- Both QCauto and QCauto+95%-3NN are calculated separately. All 104 eligible
  proxies matched regional SST within 24 hours; the conditional 48-hour extension
  was unnecessary. Complete table availability is checked before a denominator
  is formed. Empty/faulty tables remain exclusions, not sampled zero detections.

## What this first demo can answer

Select the **PROVISIONAL DEMO** analysis, its assignment method and one assay
protocol in Chat. Enable ANEMONE eDNA; additionally enable SST for temperature
comparisons. Existing conflicting source filters require clarification and are
never cleared or widened automatically.

- **“Show the top 10 fish by detection frequency, with yearly and seasonal
  changes”**: returns exact frequency rows, seasonal/yearly plots and separately
  ranked sequencing-read sums. Read counts are not organism abundance.
- **“Compare fish detection frequency in high and low SST conditions and show
  a representative series”**: compares the fixed top-frequency fish list with
  separate all-eDNA and SST-matched denominators. Unsupported contrasts retain
  warnings; representative selection never implies causation.

High/low SST means region/season thirds from supported daily regional SST across
the actual **2020–2023 study period**, independently of which fish samples were
collected. It is not a seven-year or long-term climatology. The explicit rectangle
is 38–39°N, 141–142°E, with unestablished coordinate uncertainty. The source is
0.05-degree grid-point subsampling of MUR 04.1 foundation analysis; values use
cosine-latitude grid-point weighting. This is not native coastal or sample-point
SST. Primary rules are uncertainty ≤1°C, open-sea mask, ice fraction ≤0.15 where
available, ≥80% valid open-ocean support and five valid points. Missing ice
fractions use the accepted open-sea-mask fallback with explicit warnings on all
1,455 retained days. A 0.5°C uncertainty sensitivity is a separate comparison,
not a silently substituted primary result.

## Questions that remain unsupported

There are **no species-resolved Sardinops melanostictus rows** in these 118
occurrences. There are 268 rows labelled **unidentified Sardinops**, split across
the methods. They cannot be relabelled Japanese sardine or taken as evidence
that sardines were absent. Species-specific sardine workflows explicitly explain
this gap. A genus-level exploratory recipe would need its own clear label.

One regional rectangle cannot support within-region spatial redistribution.
Provisional spatial maps/change tables are empty, rather than exporting false
zero maps. Reviewed comparable areas, physical identities and protocol coverage
are still required for the spatial and intermediate-year distribution demos.
Yearly/seasonal frequency and read signals do not establish weather causing fish
abundance changes. #102, #103 and #89 remain open for these remaining objectives.

## Publication and rollback boundary

Schema-three artifacts use the separate `provisional-demos` namespace. Older
production releases do not enumerate this index, so private preparation does not
break their formal analysis catalog. A supporting app release exposes explicitly
labelled choices and exact deterministic result rows; it never feeds arbitrary
frequency snippets to the model. Loaders verify all files, immutable IDs and
recompute results from the full sealed inputs. Source freshness checks include
all selected sample/assay/detection/source-file/snapshot rows and corpus heads in
one bounded read-only transaction. Changed inputs make a demo historical.

Operator: `scripts/run_provisional_research_demo.py`. Preflight is the default;
`--execute` requires current source verification and the hash-bound explicit user
decision. It performs no provider acquisition, classification/review application,
production migration or role/IAM changes. Retain source inputs, manifests and
actual image/source receipts before recording live acceptance. Compatible app
rollback leaves provisional artifacts retained but invisible to older releases.

Validation so far: 1,257 backend tests passed, 39 optional PostgreSQL tests
skipped, 81.04% coverage; active Python lint passed. All 71 frontend tests,
typecheck and production build passed. The package version is prepared as 0.7.4;
GitHub CI and exact-image verification remain required.
Real retained-data processing and both provisional calculations passed. These
results do not yet claim deployed Chat acceptance or completion of #89.
