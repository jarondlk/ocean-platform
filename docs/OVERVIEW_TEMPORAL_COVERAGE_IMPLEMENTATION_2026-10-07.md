# Overview temporal coverage — first version

Implemented and checked locally on 2026-10-07 JST in the managed worktree
`/Users/jaronchai/.codex/worktrees/overview-temporal-coverage/provenance-eco-rag`,
branch `codex/overview-temporal-coverage`, based on
`df1c23622fc81f4b6438899f0df6d0d6c0cc6cde`.

## Behavior

The Overview Interface Register is replaced by an aligned monthly timeline
for CTD casts, metagenome samples, active ANEMONE provider occurrences and
current daily satellite SST. Source selection highlights occupied months
shared by every selected source. Source ranges, count units, missing/undated
records, and eDNA classification categories remain explicit. SST months with
missing days have an underline and exact gap counts/dates in their details.

Unavailable sources remain visible and make selected overlap unknown. Empty
dated coverage and disjoint coverage produce known zero overlap. Refresh reads
new artifact revisions, preserves source selection, and clears stale coverage
if the request fails. Overview statistics and health load independently.

`GET /overview/coverage` requires `overview:read`; viewers can read aggregates
without gaining detailed-data access. Other methods remain denied. The endpoint
reads bounded parquet projections and canonical eDNA metadata in a read-only,
repeatable-read PostgreSQL transaction, with canonical publication bindings and
a five-second statement timeout. It never reads detection joins, private raw
metadata, download storage, credentials, accounts or chat history. Individual
dependency errors are sanitized and do not suppress healthy sources.

Metagenome month precision stays coarse. Date-only values are not assigned a
timezone; timezone-aware instants are converted to Asia/Tokyo. Native parquet
representations of calendar dates as naive midnight timestamps are accepted
losslessly. SST day completeness is measured only inside the observed extent.
Historical raw MUR acquisitions are not treated as published coverage.

## Verification

- Final backend CI-style suite: **1,161 passed, 39 skipped**, **79.93% coverage**,
  exceeding the required 70%. Service/data-dependent skips are explicit;
  PostgreSQL integration and deployed scientific acceptance are not claimed.
- Frontend: **70 tests passed**, TypeScript checking and production build passed.
- Full active-code Ruff, generated chat-scope contract check, dependency
  consistency and Git whitespace checks passed.
- New regressions cover independent units, sparse/disjoint bins, duplicate
  identity conflicts, date precision, JST month boundaries, typed CTD dates,
  replacement artifacts, bounded read retries, nullable/non-finite SST values,
  whole missing months, bounded gap lists, canonical eDNA bindings, sanitized
  failures, anonymous/mutation denial, role permissions, mounted selection
  behavior and refresh failure.
- Browser checks used an isolated localhost API/frontend on ports 8106/3106.
  CTD/metagenome/SST artifacts were read from the original data directory.
  Database and model connections were deliberately directed to an unavailable
  local test destination; no live canonical database was accessed.
- Real local artifacts showed 162 CTD casts, 82 metagenome samples and 79 SST
  days, with three shared months (December 2025–February 2026) and the six-day
  February 14–19 SST gap. eDNA correctly rendered as unavailable in that preview.
- English/light and Japanese/dark rendering, refresh, source selection and
  arrow-key month navigation were checked. At the 390px mobile viewport, the
  document had no horizontal overflow and the chart scrolled within its panel.

## Initial isolation and remaining acceptance

The original checkout stayed on `codex/issue-103-historical-sst` at
`df1c23622fc81f4b6438899f0df6d0d6c0cc6cde`. Its only pre-existing working-file
change was the untracked planning document; its SHA-1 remained
`82cf717ac3730c467cb8178e6557e122bc1bd73d`. Dependencies were copied into the
new worktree instead of symlinking mutable build output to the original.
At this initial implementation checkpoint, no primary-branch checkout,
downloader operation, scientific-data write,
database mutation, cloud action, merge, push or deployment was performed.

Live eDNA database acceptance and authenticated deployed-role QA were still
pending at that checkpoint. Historical MUR rows require verified, review-bound
publication and
will be a separate integration. The chart describes temporal co-presence,
not spatial matching, physical-sample identity or analysis eligibility.

## Subsequent GCP acceptance

The production-based subset and the year-label spacing correction were deployed
on 2026-10-07 JST. Live eDNA and authenticated admin Overview acceptance passed,
with read-only baseline/post-cutover preservation and original jobs/checkout
unchanged. See [the rollout record](OVERVIEW_GCP_ROLLOUT_2026-10-07.md) for exact
source/images, tested role limits, security findings and cleanup.
