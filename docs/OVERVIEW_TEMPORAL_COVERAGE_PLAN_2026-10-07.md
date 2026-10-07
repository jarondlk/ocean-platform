# Overview data-source timeline — implementation plan

Status: first version implemented in the isolated `codex/overview-temporal-coverage`
worktree, 2026-10-07 JST. See `OVERVIEW_TEMPORAL_COVERAGE_IMPLEMENTATION_2026-10-07.md`
for scope and validation. No deployment or scientific publication made.

## Purpose and placement

Replace the `Interface Register` table at the bottom of `frontend/app/page.tsx`
with **Data coverage over time**. Keep the existing metrics, architecture,
source balance, runtime signals and Operational Surface route rail.

The panel answers: when does each source have records, which calendar months
contain records from several sources, and where are the gaps? Temporal
co-presence is useful for selecting a study window but does not establish a
spatial match, matched sample, scientific eligibility or validated association.

## Findings that determine the design

Read-only profiling of this checkout found:

| Source | Basis | Local coverage | Unit |
| --- | --- | --- | --- |
| CTD | `data/normalized/ctd_summary.parquet`, `ctd_date` | 2024-01-18–2026-03-02; 162 casts on 27 distinct dates | Unique casts |
| Metagenome | `data/serving/sample_registry.parquet`, `sample_year_month`, restricted to `has_kraken OR has_metaeuk` | 2024-04–2026-02; 82 samples in 21 months | Unique registered samples |
| Current satellite SST | `data/normalized/sst_daily_summary.parquet`, `date_jst`, finite `mean_sst` | 2025-12-05–2026-02-27; 79 observed days | Unique usable daily summaries |
| ANEMONE eDNA | Active canonical `edna_sample` rows in PostgreSQL | Retained 2026-10-06 census reports 2017-12-18–2023-12-16; current range must be queried at runtime | Provider source occurrences |

The eDNA date range above is dated documentary evidence, not a fresh database
query. Local artifacts are not proof of the deployed dataset or its freshness.
All displayed ranges and counts must be calculated by the running API.

CTD, metagenome and current SST have records in the same three months:
December 2025, January 2026 and February 2026. Current SST has no daily rows
for February 14–19 inside its extent. Start/end bars alone would hide that gap.

Metagenome `first_run_date` and `last_run_date` are processing dates from run
QC. Use `sample_year_month` for this sampling timeline; do not substitute run
dates or invent an exact collection day from a monthly sample identifier.
Kraken and MetaEuk are treatments of samples, not two independent source rows.

Historical MUR acquisition targets 2017–2023 and has separate regional-context
and native-patch roles. Raw download completion is separate from scientific
acceptance, normalization and publication. Its acquisition dates must not be
merged into current SST coverage.

## First version: a compact aligned timeline

- Four labeled rows on one horizontal calendar axis: CTD, metagenome,
  ANEMONE eDNA and current satellite SST. Add product/provider detail where
  known from existing metadata; never infer a product version from a filename.
- Show a faint extent guide and stronger cells only for populated months.
  Label each row with its observed range, count and count unit. Monthly cells
  indicate presence, not complete sampling throughout that month.
- Hover or keyboard-focus a month to show its count, precision and, where
  applicable, observed-day count. For daily SST, include day completeness and
  missing dates within the observed extent in the detail view. Dates outside
  that extent are not assumed missing downloads.
- Allow selecting at least two source rows. Highlight months with records in
  every selected source and label this **Months with records in all selected
  sources**. Compute intersections from populated bins, not min/max envelopes.
  Default to all available rows; no shared months is a valid result.
- An unavailable selected source makes the intersection unknown, not zero.
  Never silently remove a selected source from the calculation. Keep an
  unavailable row visible, with a retry action; healthy rows remain usable.
- Keep the initial controls limited to source selection and refresh. Use a
  stable full-data extent so selection does not shift the axis. Years label
  the full span; month detail is available through selection/focus. Defer
  free-form zoom, bay/station filters and cohort selection until needed.
- Provide an accessible textual summary and a small expandable coverage table.
  Use labels/patterns as well as color. Match the existing themes, density,
  reduced-motion preferences, and English/Japanese strings. On narrow screens,
  scroll the timeline within its panel and keep the table readable.

One visible explanatory sentence is sufficient: “Shared months describe time
coverage; locations and samples may differ.” Do not label these months as
matched samples or eligible comparison windows.

## API and source semantics

Add `GET /overview/coverage`, leaving `/stats` backward compatible. Return only
aggregate information needed by the panel, through the existing Next.js
`/api/backend` proxy and `request<T>` client. Suggested response:

```text
calendar: Asia/Tokyo
resolution: month
generated_at: timestamp
sources[]:
  id, label, count_unit, scope, status, date_basis, temporal_precision
  observed_start, observed_end, total_count, undated_count
  source_binding, bins[{month, count, observed_days?}]
  missing_dates_within_extent? (daily SST only)
```

Use explicit source states (`available`, `empty`, `unavailable`), null bounds
when unavailable/empty, and sanitized reasons. Invalid or unsupported dates
contribute to `undated_count`, not fake timeline cells. Bindings expose safe
generation/hash identifiers or artifact revision tokens, never private paths,
bucket names, source metadata, account data or download credentials.

Build a small dedicated aggregation service rather than adding substantial
logic to the already large `api/main.py`. Read only required parquet columns
via `config.NORMALIZED_DIR` and `config.SERVING_DIR`. Do not reuse the current
path-only `lru_cache` readers for refreshable coverage; they retain changed
artifacts until process restart. Start with uncached small-file reads and a
bounded database read. Capture/check file revision tokens around each read;
retry once or report unavailable if a file changes during the read. The
response identifies each source independently and does not claim a single
atomic generation across files and PostgreSQL.

For eDNA, use the existing active canonical database and repeatable-read,
read-only transaction pattern in `api/edna_service.py`. Read only occurrence
identity, date/precision, classification and safe publication bindings; avoid
joins to detections that would multiply occurrence counts. Keep canonical
coverage distinct from retrieval publication readiness. Missing/conflicting
canonical bindings are unavailable; absent retrieval materialization alone
must not erase canonical source coverage. Do not fall back to a stale local
ANEMONE export if the database cannot be read.

The eDNA row describes all active provider occurrences, including controls
and unknown classifications. Its details report those categories explicitly;
they are not counted as environmental or analysis-eligible samples. The
existing physical-sample identity remains unresolved. An environmental or
analysis-eligible mode, if later requested, must use the existing shared
eligibility policy with its assay/method requirements.

Use the temporal conversion semantics already demonstrated in
`ingestion/sst_inventory.py`: retain date-only provider calendar dates as dates;
convert timezone-aware instants to Asia/Tokyo; retain month-only sample labels
as months. Do not assign midnight/timezones to date-only records. Preserve
source precision in the response; monthly overlap never implies same-day
overlap. Keep existing endpoint date-filter behavior unchanged.

Map **GET only** on the new endpoint to `overview:read` in `api/auth.py`.
Viewers already have this permission but lack `data:read`, which protects
existing `/data/*` and `/explore/*` endpoints. This aggregate endpoint therefore
avoids a page that works for researchers but breaks for viewers. Detailed-data
links must be permission-gated; use existing routes/query parameters where
supported, without promising filters that the destination does not consume.

## Historical SST integration after acquisition

The first version can be developed and validated while the raw download runs.
It does not scan raw NetCDF directories or contact acquisition providers.

Later add separate historical MUR context/native rows only from the verified,
review-bound published research panel/collection metadata. Their dates, valid
coverage, product roles and immutable identities remain distinct from the
current SST row. Respect the existing research SST publication gates in
`docs/HISTORICAL_SST_ISSUE_103_PLAN.md`; raw archives or partial receipts are
insufficient. If download progress is desired, make it a separate operator
feature using a sanitized status summary, not an observed-coverage bar.

## Implementation sequence and acceptance

1. Implement date/count aggregation and the typed API contract; add the route
   and its authorization rule. Fixture tests cover sparse/disjoint ranges,
   duplicate sample/assay records, invalid dates, timezone month boundaries,
   one-month datasets, source failures and file replacement on refresh.
2. Add frontend types/client and a new `TemporalCoverageTimeline` component
   using React and native SVG/CSS. The repo already renders charts this way
   and has no plotting dependency. Put geometry/intersection helpers in a
   distinct `temporal-coverage` module; existing `SourceCoverage` describes
   retrieved Chat evidence and should retain its current purpose.
3. Replace the register table and remove its obsolete local `interfaceTabs`
   data/import. Load coverage independently from statistics and health so a
   coverage failure cannot blank the other Overview panels. Add refresh,
   localization, responsive styling and the accessible detail view.
4. Verify intersections and missing-source behavior with frontend unit/mounted
   tests, and viewer/researcher/admin access plus anonymous/mutation denial
   with backend tests. Check real local artifacts, then desktop/mobile,
   keyboard use, both languages and light/dark themes. For implementation,
   run focused pytest/Ruff checks, frontend tests/typecheck/build, and the
   repository's required CI checks. Update the README Overview description.

Acceptance: source counts use declared independent units; holes remain visible;
the six-day local SST gap is reported; no common months and unknown overlap
are distinct; month-only dates remain coarse; refresh observes a replacement
artifact; partial failures preserve other sources and metrics; viewers receive
only authorized aggregates; historical download targets never appear as
published observations. No database migration, plotting package, new service,
or downloader modification is required for this scope.
