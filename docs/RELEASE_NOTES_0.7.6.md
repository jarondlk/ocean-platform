# v0.7.6 — AUTO chat settings and security maintenance

Chat now offers opt-in AUTO planning beside Select all/Clear. A separate planner
selects supported data sources, filters, published analysis, workflow and assay
before evidence retrieval and the main answer flow. Validated effective settings
appear in the controls and per-user history without overwriting manual defaults.

Fresh Miyagi fish-frequency and high/low SST questions select the verified
same-publication 3NN analysis and matching workflow. An unspecified assay uses
the first eligible published protocol (currently 12S rRNA / NextSeq 500 paired).
Explicit MiSeq requests and user pins take priority. Different cohorts, changed
fixed panels, incompatible periods and unavailable protocols are not silently
substituted. Protocols and assignment methods remain separate.

Supported exact statistics and MUR coverage return deterministic results.
Interpretive questions can use verified published result packets in the main
model, retaining units, denominators, result IDs and scientific limitations.
AUTO remains opt-in. Hybrid routing, reviewed geographic resolution and broader
free-form English/Japanese evaluation remain follow-ups.

Security maintenance removes ambiguous whitespace backtracking, contains local
bundle reads with the existing bounded reader and rejects nonregular files.
Cloud SQL now requires encrypted transport; new-instance bootstrap uses the same
default. Existing non-root, tooling-removal, privilege, auth, IAM and data-mount
protections remain. Unfixed Debian advisories remain visible in #104.

The API/frontend version is 0.7.6. Current operating docs and historical advisory
ID labels are refreshed. The release includes no new acquisition, database
migration, scientific publication/review, role changes or standalone Himawari
download script. Final branches are `main` and `gcp`.

[Operations and validation](RELEASE_0.7.6_OPERATIONS.md) ·
[GCP health/security audit](GCP_HEALTH_SECURITY_2026-10-09.md) ·
[Scientific publication contract](HISTORICAL_REGIONAL_PUBLICATION.md)
