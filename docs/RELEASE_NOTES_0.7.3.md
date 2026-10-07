# v0.7.3 — Overview coverage and historical SST preparation

## Changes

- Overview now shows aligned monthly source coverage for CTD, metagenomics,
  ANEMONE eDNA and current satellite SST, with source selection, date ranges,
  explicit count units, SST gaps, refresh and keyboard navigation. Shared months
  describe temporal co-presence; they do not establish spatial/sample matching.
- Adds bounded hybrid historical MUR acquisition, resumable private archives,
  provider/generation checks, final-only archive-to-review staging and bounded
  collections of scientifically reviewed SST panels. Existing single-panel,
  recipe and export contracts remain supported.
- Includes sharp 0.35.5 for GHSA-wq5f-xc86-pv6w. Residual image OS findings remain
  tracked in #104; this release does not claim vulnerability-free images.

## Historical data and scientific limits

The private NASA regional-context archive covers full 2017–2023 years: 2,554
retained daily files / 1,029,809,920 bytes, comprising 2,521 final and 33 interim
files. The two excluded February 2021 dates plus interim dates leave 35 explicit
final-series gaps. Context is 0.05-degree grid-point subsampling, not native
sample-area evidence. Native patches remain pending provider recovery.

This software release **does not publish historical SST into Chat**, approve
scientific definitions, or complete #89's real-data demonstrations. #102 sample
eligibility/physical identity/area evidence, #103 product/QC/time/weighting review,
controlled normalization/linkage/publication and historical Chat acceptance
remain open. Existing published SST/eDNA Chat safeguards remain in effect.
See [integration handoff](HISTORICAL_SST_CONTEXT_INTEGRATION_2026-10-07.md).

## Compatibility and rollout

No database migration, scientific data republishing, source acquisition execution,
account/role change or IAM change is required by this software rollout. Schema
head remains `20261005_0016`. Existing publication and history preservation are
required acceptance checks. The already deployed Overview feature from #116 is
included; the original superseded SST worker must not restart.

The candidate must pass exact-source CI, image/runtime/security verification,
zero-traffic acceptance and preservation checks before promotion. Record actual
image digests, source, backup/restore evidence, rollout and compatible rollback
in the dated operations record. Release preparation alone is not deployment.
Live mobile workflow QA (#107), sign-out follow-up (#108), OS maintenance (#104)
and scientific demonstrations (#89/#102/#103) retain their existing scopes.
