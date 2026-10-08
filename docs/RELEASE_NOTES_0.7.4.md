# v0.7.4 — provisional Miyagi historical SST / ANEMONE demo

Published/deployed2026-10-08 JST. Normal candidate/production Chat, verified CSV,
backup/restore and independent preservation acceptance passed.
See [operations](RELEASE_0.7.4_OPERATIONS.md).

This patch adds an explicitly user-approved provisional demo using retained
2020–2023 MUR regional context and available Miyagi ANEMONE records. Chat can
show exact top-fish detection frequencies, seasonal/yearly changes, separate
sequencing-read rankings and high/low regional SST comparisons, with citations
to immutable result tables. Assignment methods and assay protocols stay separate.
The complete tables and their provenance remain available through the Data
workbench and exports.

The first calculation has 104 singleton occurrence proxies, 104 matches within
24 hours and 14 excluded repeat occurrences pending actual latest-assay evidence.
Frequency uses provisional occurrence proxies, not confirmed physical water
collections. Canonical source classifications and physical identities remain
unchanged. The recorded approval comes from the user; ANEMONE is the requested
display label and does not assert provider endorsement or independent researcher
approval. Formal researcher/admin review permissions remain unchanged.

The SST processor verified 48 retained monthly batches and 1,455 final MUR daily
analyses. Six final-series gaps remain explicit. MUR values are 0.05-degree
subsampled regional context, not native coastal or point-sample evidence. Relative
temperature thresholds use supported daily region/season values over 2020–2023,
independently of fish sampling effort. Read sums do not measure fish abundance;
temperature comparisons do not establish weather causation.

This cohort has unidentified Sardinops but no species-resolved Japanese-sardine
records. Species-specific sardine questions explain that limitation. Spatial
redistribution questions remain unsupported by a single regional rectangle;
false zero maps and distribution rankings are not exported. #89, #102 and #103
remain open for the remaining scientific objectives and expansion beyond Miyagi.

Private demo preparation uses a separate artifact namespace, which older app
versions do not enumerate. No production migration, classification change,
account/role/IAM change or additional provider acquisition is included. The
patch also includes the merged PR #119 Next.js 15.5.27 audit correction and the
bounded retained-context processing/normalization tooling.

Candidate browser QA also found and fixed a stale analysis binding: after editing
a source filter, choosing “No analysis selected” now removes the previous
analysis from the request while retaining the explicit source filters.

See [the demo evidence and limits](MIYAGI_PROVISIONAL_DEMO_2026-10-08.md).
All eight GitHub checks and final Cloud Build steps passed; exact source `f73d5fd`
is pinned by the release tag and images. Existing live-role/mobile deferrals remain.
