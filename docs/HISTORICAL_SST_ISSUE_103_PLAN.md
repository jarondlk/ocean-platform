# Historical SST acquisition plan — issue #103

Prepared 2026-10-06 JST against main `05deee7` / deployed v0.7.2. This is a
proposed implementation and acquisition plan, not an approved SST definition
or a completed download/publication. No new application version is assigned yet.

## Scope agreed during planning

- Compare MUR and Himawari geophysical SST before choosing a product.
- Cover all ANEMONE locations and sampling years, rather than limiting acquisition
  to the original Miyagi 2020–2023 examples.
- Refresh the active catalogue before fixing the acquisition manifest. Retained
  source metadata is planning evidence, not a new production census.
- Collect complete daily context for the selected years/areas, with reviewed
  boundary padding for time matching. Fetching only taxon-positive sampling dates
  would not support full-month context or unbiased spatial comparisons.
- This broader acquisition does not itself rescope the six #89 demonstrations or
  approve physical samples, environmental classification or geographic footprints.

## Evidence already checked

The retained ANEMONE census has 3,498 occurrences, dates from 2017-12-18 through
2023-12-16 UTC, 216 distinct reported worldmesh values and 324 occurrences without
worldmesh. Reported grid values are not 216 confirmed sampling sites; missing
worldmesh does not by itself establish missing coordinates. No physical-unit or
environmental classification is inferred here.

The two retained MUR pilot files (2020-05-15 and 2023-05-15) pass their original
SHA-256 checks, totaling 26,208 bytes. This establishes retained-file integrity,
not regional coverage or approval of the pilot's proposed quality thresholds.

A fresh public NOAA mirror time-axis query returned 1,459 unique timestamps at
09:00 UTC for the 1,461 expected dates in 2020–2023. The mirror lacks
**2021-02-20 and 2021-02-21**. This is a mirror inventory finding, not proof those
dates are absent from NASA's source archive. Receipt:
`/tmp/ocean-issue103-plan/mur-time-axis-receipt.json`; response SHA-256
`bf1bc310572def5130b482740255e1b9b36fe930d286dd2812adc4a94af101b9`.
No SST grids were downloaded by that metadata query.

## 1. Refresh the acquisition census

Read the current production source metadata in one consistent, read-only snapshot
and compare canonical generation/hash bindings with the retained candidate.
Record all occurrence dates and their original precision/timezone, location
metadata, coordinate basis/uncertainty, provider projects and control status.
Keep unresolved locations and dates in an exclusion report.

Generate a deduplicated source-location/year inventory without claiming physical
sample identity. Controls and unknown classifications remain visible in the
inventory; they do not become eligible environmental analysis units. Provisional
download tiles must be explicitly labeled acquisition envelopes. Final scientific
areas still require #102's reviewed footprints.

Provisional full-calendar scope is 2017–2023, subject to this refresh. That is
2,556 dates. One hypothetical row for each of 216 reported grids on every date
would be 552,096 rows; this is sizing arithmetic, not a count of observations or
approved area-days. Produce actual request/byte/disk/runtime estimates from the
tile inventory before executing the bulk acquisition.

Deliverables: census receipt, location/year coverage and unresolved-input tables,
tile/date inventory, resource estimate and source hashes.

## 2. Compare products before selection

| Candidate | Known basis | Investigation required |
| --- | --- | --- |
| MUR v4.1 | Daily, 0.01-degree global foundation analysis combining satellite and in-situ inputs; existing bounded downloader and normalization pilot. | Enumerate the full requested time axis, check missing mirror dates against same-product source archives, verify coastal support and revision policy. |
| Himawari AHI geophysical SST | JAXA documents 2 km retrieval products and hourly/daily variants. | Demonstrate access to historical binary data for the actual years; pin processing/file versions, daily mean/minimum choice, quality/error metadata and cloud coverage. |
| JMA HIMSST, optional third comparator | Merged satellite/in-situ regional analysis on a 0.1-degree grid. | Assess its coarser coastal representation, archive completeness and adapter needs if the primary comparison warrants it. |

Sources: [NASA MUR description](https://podaac.jpl.nasa.gov/MEaSUREs-MUR),
[NOAA mirror metadata](https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.html),
[JAXA SST guide](https://www.eorc.jaxa.jp/ptree/userguide.html),
[JAXA GHRSST portal](https://ghrsst.jaxa.jp/),
[JMA HIMSST format](https://www.data.jma.go.jp/goos/data/pub/JMA-product/him_sst_pac_D/Readme_him_sst_pac_D).

The [detailed P-Tree FAQ](https://www.eorc.jaxa.jp/ptree/faq.html) clarifies that
historical geophysical products are archived in NetCDF. Its 30-day retention
limit applies to raw Himawari Standard Data, not the geophysical archive. The
broader overview was insufficient to resolve this distinction during planning.
Authenticated historical SST file access still needs a representative probe. Existing
JCOPE-T files are assimilative model outputs and do not qualify as Himawari
geophysical retrievals.

Choose a small, fixed comparison set from the fresh inventory: earliest/latest
years, winter/summer, geographically separated regions and coastal/offshore
support. Compare available dates, valid ocean coverage, quality rules, temporal
basis, spatial support, SST differences and operational requirements. Different
measurement/time statistics must be explicit. Record inaccessible products as
unverified, without filling their gaps from another product.

Deliverables: product/access comparison, representative provenance-linked plots
and tables, proposed primary/secondary product recommendation. A named scientific
reviewer records the selected product/version, rationale and quality/matching
rules. Product choice remains pending this comparison.

## 3. Implement resumable, bounded acquisition

Extend the operator-only tooling; retain `prepare_research_sst.py`'s supported
pilot contract. Add range/tile manifests with deterministic IDs and bounded child
batches, initially at most one month per tile. Download only required variables
and footprints where the provider supports subsetting. Document full-file download
requirements separately for providers without a subset endpoint.

Use temporary files and atomic completion, checksum verification, provider-scoped
redirect rules, timeouts, byte ceilings, conservative concurrency, bounded retries
and Retry-After/backoff. Resume verified files after interruption. Preserve prior
bytes when a provider revises a file; changes create new source generations.

Maintain explicit outcomes for acquired, provider-missing, corrupt, retryable,
oversized, out-of-coverage and unresolved requests. A terminal reconciliation
report must account for every planned request; partial downloads never advertise
complete coverage. Distinguish complete inventory from a scientifically sufficient
panel. Pin URLs, dates, actual timestamps, variables, product/file versions,
download time, byte count, SHA-256 and reuse provenance.

Deliverable: downloader/preflight CLI, journal, immutable acquisition manifests
and failure/resume tests. No automatic production ingest or scheduled downloads.

## 4. Support historical partitions before full publication

Current boundaries are 32 days per pilot request plan, 1,600 granules per SST
panel, 128 MiB per complete panel including raw files, and 200,000 normalized
observations. Research recipes pin one `sst_panel_id`; simply downloading several
monthly panels does not make them a usable multi-year analysis input.

Implement a versioned collection of bounded immutable panels, partitioned by
geographic tile/group and time. A collection pins exact child IDs/manifests,
one product definition and compatible sampling/area review versions. Preserve
the existing single-panel reader and old result/history/export formats. Use
explicit bounded scientific subsets for a requested region/year recipe instead
of loading the whole national archive into a web request.

Reject mixed product/review generations and conflicting duplicate area/days;
handle legitimate tile overlap without double counting. Keep aggregate request,
grid, observation, byte and memory budgets. Verify raw provenance in the operator
pipeline and maintain an auditable path through collection, child panel and raw
file. Metadata-only serving must not claim it independently reverified absent
raw bytes. Broader scope requires this design and measured sizing, not removing
limits or silently truncating records.

Deliverable: compatible collection reader/publication/provenance/export support,
boundary and integrity tests, measured multi-region/multi-year resource behavior.

## 5. Acquire and validate the historical archive

After product selection and a concrete bounded manifest, run representative
batches first; use measured bytes/runtime to confirm the full plan. Then acquire
every planned date/tile for all catalogue sampling years. Reuse only files whose
product, footprint, timestamps and checksums match; existing tiny pilot files
cannot substitute for larger requested footprints.

Validate each granule's product identity, CF/GDS metadata, units, axes, actual
time, fill values, land/sea/ice masks, quality/uncertainty fields and spatial
coverage. Record valid/missing/quality-rejected area-days and preserve gaps.
Check MUR mirror gaps against a verified source of the same product/version;
retain any unresolved gaps. No cross-product substitution inside a product panel.

Keep raw data and operational receipts outside Git. Stage local data first;
use the existing private scientific-data bucket for reviewed durable storage.
Refresh GCP authentication only when cloud storage or operator execution needs
it. Any provider-specific sign-in is a separate access requirement. Recheck
actual storage/billing limits against the measured acquisition manifest.

## 6. Complete reviewed linkage/publication and #103 acceptance

Acquisition/access comparison can proceed while #102 is unresolved. Scientific
panel publication requires the current researcher-approved/admin-applied SST
definition and #102's sampling/area records. Do not automatically accept the
pilot's 1°C uncertainty, 80% pixel support, 24-hour matching or monthly
support defaults as scientific decisions. Review units, thresholds, mask rules,
minimum pixel support, weighting, time tolerance and day/season calendar explicitly.

Prepare sample-time links separately from full-month daily context. Preserve
all-eDNA versus SST-matched denominators, spatial uncertainty, missing dates and
quality exclusions. Independently check selected source-to-area calculations and
time links before publishing immutable results. A broader acquisition archive
must remain selectable as bounded reviewed cohorts for the six #89 workflows.

Verify analysis options, exact panel/collection scope, provenance/history,
maps/time series and CSV/ZIP/SVG consistency on real inputs. If raw historical
data is intended to appear in ordinary SST retrieval before research-result
publication, implement and qualify an explicit product-aware corpus publication;
bucket upload alone does not make it available in Chat. Preserve the existing
SST corpus until that controlled publication is accepted.

Close #103 only with reviewed product/area versions, reconciled acquisition and
coverage reports, validated linkage, published immutable identifiers and a dated
acceptance packet. Download completion alone can finish an acquisition milestone,
but cannot satisfy the still-open scientific registry/linkage requirements.

## Proposed implementation order

1. Census and product comparison; establish historical binary access and recommend
   a product, with selection recorded before bulk acquisition.
2. Resumable acquisition tooling plus bounded partition/collection support.
3. Measured pilot, full acquisition and durable private archive reconciliation.
4. Reviewed #102/#103 definitions, real normalization/linkage/publication and
   end-to-end scientific acceptance.

Keep tooling and collection compatibility independently reviewable, followed by
a data execution/acceptance record. Any software rollout is a new immutable
version; do not retag deployed v0.7.2. No new migration is presumed until the
collection design establishes whether schema changes are necessary.

## Implementation progress — 2026-10-06 JST

The refreshed production census, compact preflight, resumable MUR acquisition,
representative probe tooling and bounded SST collection compatibility are
implemented in the #103 branch. The production census resolves the provisional
scope to 216 reported coordinate locations in 75 acquisition tiles, 2017–2023;
324 occurrences lack resolved coordinates. No scientific eligibility is inferred.
The two NOAA mirror gaps have corresponding NASA catalogue granules; their raw
source files have not been acquired. The Himawari file comparison and scientific
selection remain pending. See the [implementation and operator runbook](HISTORICAL_SST_ISSUE_103_IMPLEMENTATION.md)
for exact evidence, commands and remaining acceptance gates. Production remains v0.7.2.
