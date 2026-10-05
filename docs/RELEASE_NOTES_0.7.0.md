# v0.7.0 — Reviewed research workflows

This software release adds evidence-reviewed analysis preparation and exact
published research results shared by Chat, Data, charts and exports.

## Changes

- Sampling/area and SST-product reviews retain evidence hashes, rationale,
  version history and separate researcher approval / administrator application.
- Detection frequencies use reviewed physical samples and a fixed eligible
  denominator. Controls and unresolved evidence are excluded explicitly;
  sampled non-detection is zero and unsampled groups remain unavailable.
- Six deterministic workflows cover top-ten time series, temperature contrasts,
  best-month spatial coverage, spatial SST conditions, endpoint changes and
  intermediate-year follow-through. Q2 retains Q1's fixed top-ten candidates.
- Published recipes, exact rows, source generations and review versions support
  reproducible results and current/historical status. Chat preserves source
  checkboxes and filters and abstains when compatible published evidence is absent.
- Data and Chat share maps, frequency/SST series, exact-row selection and
  provenance-aware CSV, bundle and SVG exports.
- Runtime images use updated Debian packages, remove installation tools and
  unused affected CLI paths, strip setuid/setgid bits and run as non-root.

## Explicitly deferred real-data demonstrations

On 2026-10-05 JST, the user authorized shipping the implemented software while
deferring all six original ANEMONE/SST examples in
[issue #89](https://github.com/jarondlk/ocean-platform/issues/89). The issue stays
open. Synthetic verification does not establish the original real-data results.

Provider/researcher evidence is still required for environmental classifications,
physical sampling units, repeated-run representative assays, approved area
geometry and historical SST product/coverage. Valid empty assays require an
evidence-backed quality policy before inclusion. The third reference's full
methods review and real-cohort coverage/performance qualification belong to that
deferred preparation. No synthetic registry, classification or research
publication is installed into production to substitute for this evidence.

The six workflows require an approved, explicitly published analysis. Without
one, their controls have no real run to select and Chat reports unavailable
research evidence. Existing v0.6.1 source-scoped Chat and data paths remain usable.
Read the [scientific review packet](V0.7.0_SCIENTIFIC_REVIEW.md) before preparing
real inputs.

## Compatibility and deployment

Migration `20261004_0015` adds six registry tables. Existing histories and corpus
data are retained. Applied review evidence is immutable; rollback uses the prior
application revision with the additive schema retained, rather than erasing
review history. Existing v1 analysis files remain readable; older research
algorithm versions remain historical.

Final release source, image digests, backup/restore, security dispositions and
candidate/production acceptance are recorded in
[operations](RELEASE_0.7.0_OPERATIONS.md). The full scan reports are retained;
zero critical findings does not imply zero remaining OS advisories.
