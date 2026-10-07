# Historical SST implementation and operator runbook — #103

Initial preparation 2026-10-06 JST. This branch implements acquisition/comparison foundations
and bounded scientific SST collections. It is not a completed historical archive
or a deployed release. Production remains v0.7.2, schema `20261005_0016`.
No migration, production scientific review, source-corpus replacement, model
invocation, account read/change or Chat history read/change was performed.

Current acquisition strategy: the user-selected [2026-10-07 hybrid plan](HISTORICAL_SST_HYBRID_2026-10-07.md)
uses daily coarse context and multi-day native patches. The interrupted original
bulk worker must not restart; its verified archive remains retained. Provider
recovery, measured live hybrid acceptance and scientific publication are pending.

Update 2026-10-07: NASA context is complete (2,554 retained files; 2,521 final,
33 interim). The [context integration handoff](HISTORICAL_SST_CONTEXT_INTEGRATION_2026-10-07.md)
records exact completion evidence and the new bounded archive-to-review operator.
Full hybrid acquisition and scientific publication remain pending. The original
no-Chat-invocation statement above describes initial preparation; subsequent
production QA exercised existing published evidence, not this historical archive.

## Implemented behavior

| Component | Supported contract |
| --- | --- |
| `inventory_historical_sst.py` | Current ANEMONE scientific metadata in one repeatable-read, read-only PostgreSQL transaction, or a hash-verified retained candidate. All reported locations and sampling years; unresolved records are explicit. |
| `acquire_historical_sst.py preflight` | Compact, deterministic all-location/year manifest. Full calendar years per acquisition tile, partitioned by month and at most 12 days per child. No downloads by default. |
| `acquire_historical_sst.py batch` | Explicit child-ID execution; serial bounded requests, atomic files/journal, checksum resume, provider-scoped HTTPS redirects, bounded retries and Retry-After handling. |
| `acquire_historical_sst.py time-axis` | Public mirror timestamp inventory, with exact absent dates and raw response checksum. Mirror absence does not establish source-archive absence. |
| `acquire_historical_sst.py source-original-check` | Hash-verified retained NASA binary metadata/time inspection; preserves `04.1nrt` interim generations and never silently resolves a final-series gap. At most 1 GiB, with only axes/time loaded. |
| `acquire_historical_sst.py source-gap-check` | Bounded official NASA catalogue metadata check for specified missing dates; validates complete response and exact product/version titles. Never fetches protected binaries. |
| `acquire_historical_sst_cloud.py` | Dry-run default; capped serial private raw archive, CAS writer lease, one-child staging, byte-verified checkpoint resume, explicit exclusions and terminal reconciliation. No scientific publication or DB access. |
| `acquire_hybrid_sst.py` | Current hybrid preflight/private operator: separate context/native identities, daily context, at most 12 consecutive native days per raw file, 8 MiB/file and 32 GiB raw caps, byte-verified resume, retained failure journals and role-specific reconciliation. Dry-run default; no scientific publication. |
| `prepare_historical_sst_context.py` | Final-only integration preflight and one-batch immutable local review staging from verified private NASA context; preserves original provenance and explicit scientific/publication gates. |
| `compare_historical_sst.py` | Reproducible geographical/seasonal probes, optional small MUR downloads and retained Himawari full-disk footprint diagnostics. Scientific comparison/selection stays pending; offsets, native grid and differing statistics remain explicit. |
| `probe_himawari_sst.py` | Explicit historical directory listings or at most four selected files; certificate-verified implicit FTPS, private credential file, provider checksum/local SHA-256, atomic generation files and verified reuse. No bulk downloader or scientific publication. |
| `run_research_sst_collection.py` | Operator preflight/publication of an explicit bounded set of verified child panels and reviewed area IDs, bound to current applied product/sampling reviews. |

The original `prepare_research_sst.py` pilot API, deterministic plan hashes,
fresh-directory behavior and old panel/analysis/export contracts remain supported.
It shares its provider/request contract with the new acquisition tooling.

A collection pins one product definition and one sampling/area review generation,
exact child panel IDs and manifests, and explicit child area ownership. It rejects
mixed reviews/products, duplicate children, nested collections and contradictory
area/day observations. Operators verify every child raw file before publication;
serving validates collection/child metadata and raw references without claiming
to rehash absent NetCDF. Exact duplicate rows can be reused without double counting.

The existing recipe `sst_panel_id` can pin a single panel or a bounded collection
ID. The applied-review checks, sample-time matching, full-month SST context,
analysis history and exports consume the same immutable reference. Existing
single-panel results remain readable. Collections have a 512-child, 96 MiB
metadata and 200,000-observation ceiling; each child retains the existing panel
limits. National raw archives must be selected into bounded reviewed cohorts.
No resource limits were removed and no scientific rows are silently truncated.

## Fresh production evidence

The temporary `ocean-sst103-census` job completed successfully, then was deleted.
It used the existing job identity, production DB secret and immutable v0.7.2
image, with one task, no retries and a five-minute limit. Only active ANEMONE
sample metadata and scientific publication bindings were selected. Its transaction
was READ ONLY; no account/history tables or restore/backup operation were involved.

Inventory ID:
`62e513192cda70d576dd8c8b60713c41830a01b8fcb6ec0e1f0ebff911f9ab3d`.
The private receipt is at
`gs://data-infra-infobio-ocean-data/research-sst/issue103/20261006/inventory-62e513192cda70d576dd8c8b60713c41830a01b8fcb6ec0e1f0ebff911f9ab3d.json`.

- 3,498 active occurrences: 343 source-classified negative controls and 3,155
  unknown classifications; these are not eligible environmental sample counts.
- Sampling calendar years 2017–2023; reported dates 2017-12-18 to 2023-12-16.
- 216 distinct reported coordinate locations and 216 reported worldmesh labels,
  without claiming confirmed physical sites or approved area geometry.
- 324 occurrences with unresolved coordinates, retained in the exclusion report.
- Coordinates span 17.45833333–45.54166667°N and 123.8125–148.6875°E.
- 75 provisional 1-degree acquisition tiles with a 0.02-degree download margin.
  The margin is not a scientific uncertainty estimate.
- Canonical publication remains `a6411a26f46c098769298d11dfcafbf2dd85a141dbe5ccbdfafb581acc8bdc46`,
  manifest `efe00a383cf120128847e0ff251261ec1836c37c407eb7c64aeba14a9d583cf9`.

All 75 tiles across 2,556 dates produce 191,700 requests in 18,900 bounded batches.
The compact preflight is 8,836,699 bytes; ID
`649bd847eea9530a5f0275430d6436505e2ed0415f0449d0dedf0603de3d8372`.
Estimated grid bytes are 54,773,802,000; the deliberately conservative 8 MiB/file
ceiling totals 1,608,096,153,600 bytes. Neither number is an approved cloud budget
or a measured full-archive size. One actual 1.04-degree tile on 2023-07-15 was
285,064 bytes, versus 286,225 estimated grid bytes. More representative measured
tiles/runtime and existing storage/billing review precede bulk execution.

The fresh NOAA timestamp query returned 2,554 of 2,556 dates for 2017–2023, missing
2021-02-20 and 2021-02-21. NASA's official catalogue lists corresponding exact
MUR v4.1 granules `G3068632390-POCLOUD` and `G3068631322-POCLOUD`; their protected
original files were recovered after Earthdata authentication. However, both
NetCDF files explicitly identify **`product_version=04.1nrt`**, with an interim
near-real-time title/history/comment. Their catalogue/filename `fv04.1` label
does not establish a final generation. Both actual 09:00 UTC timestamps and
required fields pass inspection; preserve the two **final-series gaps** pending
scientific generation review. Originals are retained separately in private
storage, without scientific approval. See the [acquisition pilot receipt](HISTORICAL_SST_ACQUISITION_PILOT_2026-10-06.md).

Six small MUR probes across three distinct geographical representatives and two
seasonal dates (2017-12-18 and 2023-07-15) verified product title/version, nominal
09:00 UTC, checksum, variables and finite-ocean pixel counts. Total raw bytes:
70,824. Two geographical selection rules chose the same location, so they were
deduplicated. These are access/grid diagnostics, not reviewed area averages or
a completed MUR/Himawari numeric comparison.

Private local evidence is retained under `/tmp/ocean-issue103-implementation/`:
`production-inventory.json`, `census-receipt.json`, `mur-history-preflight.json`,
`mur-time-axis/`, `nasa-gap-check/`, `comparison/`, `full-tile-sizing/` and QA logs.
The census, six-batch MUR storage pilot and separate NASA original files are
retained in private GCS. Himawari raw probes remain local. Raw acquisition does
not update the Chat corpus or constitute scientific publication.

A six-batch cloud pilot now verifies 72 files / 20,524,608 raw bytes, including
immutable private publication, full byte read-back, and checksum-pinned resume
of four previously completed batches. The final two batches each take about
18 seconds with provider-scoped IPv4, versus about 380 seconds through the
unreachable IPv6 fallback path. Temporary pilot/timing jobs were removed.
This is measured access/storage evidence, not full historical acquisition.

## Product comparison and remaining decisions

MUR is a daily foundation analysis combining satellite and in-situ inputs, on a
0.01-degree global grid. See [NASA](https://podaac.jpl.nasa.gov/MEaSUREs-MUR) and
[the NOAA mirror](https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.html).

The [detailed JAXA FAQ](https://www.eorc.jaxa.jp/ptree/faq.html) states that historical
geophysical products are available as NetCDF. The 30-day retention constraint
applies to raw Himawari Standard Data. An existing P-Tree account is needed to
verify the historical SST files; encrypted access options are documented there.
See also the [geophysical product README](https://www.eorc.jaxa.jp/ptree/documents/README_HimawariGeo_en.txt).
Daily mean and daily minimum must be distinguished, and algorithm/file versions
must be pinned. [JAXA's notices](https://www.eorc.jaxa.jp/ptree/index.html?mode=day&prod=sst)
record reprocessing for 2022-10-03 through 2023-05-21; verify the served generations.
Usage terms and acknowledgement are part of product selection, including the
historical research/education scope described in the FAQ.

Authenticated access has now passed using the existing P-Tree research account.
Four historical files (402,428,224 bytes) passed provider checksums and local
SHA-256; twelve bounded geographical footprint diagnostics were recorded beside
the six MUR subsets. [Dated comparison and recommendation](HISTORICAL_SST_PRODUCT_COMPARISON_2026-10-06.md)
record version/statistic differences, retrieval gaps, minimum-specific uncertainty,
the full-disk longitude wrap and unresolved leap-second time interpretation.
The user selected MUR v4.1 as primary with Himawari as optional comparator.
Scientific product/QC/time review remains pending. No JCOPE substitution or full
archive/publication ran.

## Operator commands

Run from the repository root. Keep receipts/raw files outside Git, with sufficient
local capacity. A production census requires a securely configured existing DB
connection; do not put passwords in command arguments.

```sh
.venv/bin/python scripts/inventory_historical_sst.py \
  --production-read-only --output /tmp/sst103/inventory.json
.venv/bin/python scripts/acquire_historical_sst.py preflight \
  --inventory /tmp/sst103/inventory.json --output /tmp/sst103/preflight.json
.venv/bin/python scripts/acquire_historical_sst.py time-axis \
  --from-date 2017-01-01 --to-date 2023-12-31 --output-dir /tmp/sst103/mirror-axis
.venv/bin/python scripts/acquire_historical_sst.py source-gap-check \
  --day 2021-02-20 --day 2021-02-21 --output-dir /tmp/sst103/source-gaps
.venv/bin/python scripts/compare_historical_sst.py \
  --inventory /tmp/sst103/inventory.json --output-dir /tmp/sst103/comparison
```

`--candidate-root` is the alternative to `--production-read-only`; the provenance
then explicitly identifies a retained candidate rather than current production.
Comparison probes download only when `--execute-mur-probes` is added.

Himawari access uses a separate private JSON file with exactly `username` and
`password`, owned by the operator with mode 0600. Keep it outside Git and never
put credential values in command arguments. Both listing and file transfer are
dry-run by default; add `--execute` for the selected operation:

```sh
.venv/bin/python scripts/probe_himawari_sst.py \
  --credentials-file /private/operator/ptree.json \
  --list-directory /pub/himawari/L3/SST \
  --output-dir /tmp/sst103/himawari-list
```

Select 1–4 exact `.nc` paths from verified archive listings in
`{"remote_paths":["/pub/himawari/L3/SST/.../exact-versioned-file.nc"]}`:

```sh
.venv/bin/python scripts/probe_himawari_sst.py \
  --credentials-file /private/operator/ptree.json \
  --selection /tmp/sst103/himawari-selection.json \
  --output-dir /tmp/sst103/himawari-raw
.venv/bin/python scripts/compare_historical_sst.py \
  --inventory /tmp/sst103/inventory.json --output-dir /tmp/sst103/comparison \
  --execute-mur-probes --himawari-probe /tmp/sst103/himawari-raw/probe.json
```

The Himawari transfer ceiling is 256 MiB per file, four files per invocation;
verify available disk against listing sizes first. No gzip extraction or bulk
automatic queue is implemented. Interrupted temporary files are removed; repeat
the same selection to verify/reuse completed raw files and download outstanding
files. Changed provider checksums create new content-addressed generations;
damaged prior files fail instead of being overwritten. A hard-killed process can
leave `.himawari-probe.lock`; verify no writer runs before removing a stale lock.
The comparison reads at most 100,000 grid values per footprint, preserving
native values/statistic labels and recording leap-second offsets without a
scientific time correction. It never marks scientific comparison/approval complete.

For an individually reviewed child from preflight, replace `CHILD_PLAN_SHA256`
with its exact ID. Without `--execute`, this prints bounded bytes/requests only:

```sh
.venv/bin/python scripts/acquire_historical_sst.py batch \
  --plan /tmp/sst103/preflight.json --batch-id CHILD_PLAN_SHA256 \
  --output-dir /tmp/sst103/selected-batch
```

After product selection and measured resource checks, add `--execute` for that
specific batch. On hosts with an unreachable provider IPv6 route, add
`--ipv4-only`; this uses a provider-scoped IPv4 socket while retaining the original
TLS hostname and certificate verification, without a global DNS override. It
fails if a configured proxy changes the connection target. Resume with the same plan/ID/directory. Every acquired generation
has a content-addressed filename; `--recheck` contacts the provider again and
retains changed bytes. `journal.json` and `reconciliation.json` account for all
requests. Only all-acquired batches get `acquisition.json`; scientific NetCDF
identity/time/QC checks and applied review are still required for panel publication.
The existing `run_research_sst_panel.py --granules .../acquisition.json` accepts
this completed, bounded inventory. It does not accept incomplete reconciliation.

On an ordinary exception/interruption the writer lock is removed in `finally`.
After process termination/power loss, inspect `.acquisition.lock`, verify that no
writer still runs, then remove only the stale lock before resuming. Damaged
immutable raw generations cause `local_integrity_failure`; preserve/quarantine
the affected batch and use a new destination, rather than overwriting evidence.
Retry-After longer than 30 seconds leaves a retryable request for a later operator
run. Missing, denied, invalid, oversized and retryable requests remain explicit;
no older generation or different product silently fills a failed recheck.

Collections use an explicit JSON selection:

```json
{"children":[{"panel_id":"EXACT_CHILD_PANEL_SHA256","area_ids":["reviewed-area-id"]}]}
```

```sh
.venv/bin/python scripts/run_research_sst_collection.py \
  --selection /tmp/sst103/selection.json --output /tmp/sst103/collection-preflight.json
```

This preflight reads current applied product/sampling records. Add `--execute`
only for intended publication, then pin `recipe_sst_panel_id` in the research
recipe. Large national archives are not automatically loaded into web requests.
Uploading raw files alone does not make historical SST available in ordinary
Chat. Controlled product-aware corpus publication and acceptance remain required
if that serving path is selected.

## Verification and open acceptance

Tests cover deterministic full-calendar inventories, unresolved/date-only metadata,
tampered plans, bounded batches, partial resume, revised generations, local
integrity failures, Retry-After, missing/denied/bad/oversized responses, locks,
provider redirects, timestamp/source-catalogue checks, product diagnostics,
collection ownership/review/budget conflicts, old single-panel readability and
collection analysis replay/bundle export. Repository Ruff passes.

The final backend suite passed **1,079 tests**, with 39 service-gated skips and
**79.45% aggregate coverage**; see private `backend-final.log`. Ruff, generated
Chat scope contract and CLI help checks passed. Initial sandbox socket failures were resolved by
running the synthetic localhost fixture servers with the required permission.
Service-gated PostgreSQL tests are separate from the passed production READ ONLY
census; the census is not a production write/migration or real scientific QA test.

The updated backend suite passes **1,103 tests**, with 39 service-gated skips;
the historical SST/panel/collection focused suite passes 50 tests. The earlier
1,079-test/coverage run above records the first implementation stage. Updated
CLI help, generated scope and active Python Ruff checks pass.

Issue #103 remains open for completed scientific comparison, recorded scientific
product/QC decisions, measured/reconciled bulk acquisition, same-product gap recovery,
review of the recovered interim-NRT generations, current applied #102 sampling/area reviews, SST product/QC/time-window reviews,
real normalization/linkage/publication and scientific acceptance. Issue #89's six
demonstrations remain open; the broader acquisition scope does not rescope them.
No new software release/version is assigned or deployed by these operator probes.

Cloud raw execution and source-original inspection are documented in the
[dated pilot/resource packet](HISTORICAL_SST_ACQUISITION_PILOT_2026-10-06.md).
The original full-plan conservative file-byte bound remains a preflight estimate;
the cloud worker imposes a smaller explicit 64 GiB cumulative raw cap.
