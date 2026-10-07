# Next release — unreleased changes

## Overview: data coverage over time

The Overview page replaces Interface Register with an aligned monthly timeline
for CTD, metagenomics, ANEMONE eDNA and current satellite SST. Selecting sources
highlights months containing records in every selected source. Date ranges,
count units, source details and SST gaps are visible, with refresh and keyboard
navigation. The panel supports English/Japanese, existing themes and mobile
scrolling.

Coverage comes from source observations and active canonical eDNA metadata.
Month-only dates retain their precision, and unavailable sources make overlap
unknown. Shared months describe temporal co-presence; they do not establish
matching locations, physical samples or scientific eligibility. Historical MUR
downloads become coverage only through their separate validated publication.

The new read-only `/overview/coverage` endpoint uses existing Overview
permissions. Detailed-data permissions are unchanged. No database migration,
data republishing, acquisition-job change or new chart dependency is required.

Implementation: `1c77f9b` on `codex/overview-temporal-coverage`. Local verification
passed 1,161 backend tests (79.93% coverage; 39 service/data-dependent skips),
70 frontend tests, TypeScript, Ruff and production build. Desktop/mobile,
English/light, Japanese/dark and keyboard behavior were checked. These counts
refer to that feature branch, which also contains separate SST operator work.

## Deployment before the next tagged release

A GCP application-only rollout was authorized on 2026-10-07 JST, conditional on
preserving other work. Its deployment source is prepared from the existing
v0.7.2 production commit with the Overview changes and the isolated sharp
dependency fix. The newer SST acquisition tooling is excluded. Serving
configuration and existing jobs remain unchanged except for the reviewed app
images, source identity and serving revision/traffic. The v0.7.2 tag remains
immutable; this entry is not a new version announcement.

Deployed on 2026-10-07 JST at 100% traffic on
`ocean-platform-overview1007b`, exact source `ad60f2e`. The final patch also
avoids crowded first-year axis labels. All four live sources and authenticated
admin UI checks passed; original data/history/roles, serving settings, rollback
tags and all six batch job definitions were preserved. The SST working branch
and download operations were untouched. Exact build/digests, QA, cleanup and
rollback are in [the rollout record](OVERVIEW_GCP_ROLLOUT_2026-10-07.md).

Refer to [implementation QA](OVERVIEW_TEMPORAL_COVERAGE_IMPLEMENTATION_2026-10-07.md)
for the initial source/browser checks. Live scientific approval remains separate.
