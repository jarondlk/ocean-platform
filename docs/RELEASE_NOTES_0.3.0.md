# OCEAN Platform v0.3.0

`v0.3.0` completes the evidence-navigation loop in the managed academic
research platform.

## Evidence navigation

- Chat citations now expose validated links to exact provenance traces and,
  when available, sample, CTD, taxa, or SST records.
- Analysis and reliability citations open the published workspace and restore
  the cited context through bookmarkable URL state.
- `/data`, `/explore`, and `/provenance` validate URL identifiers and show
  explicit errors for malformed or unpublished destinations.
- Cross-bay CTD comparison is available as an exact derived-analysis target.

## Academic interface

- Evidence panels use direct scientific titles, source metadata, and actions.
- Redundant context banners, product prose, helper blurbs, and marketing-style
  copy were removed from Evidence, Settings, and Admin surfaces.
- The handoff now records concise academic copy as a maintained interface rule.

## Validation and deployment

- FastAPI and frontend package metadata report `0.3.0`.
- Local validation passed 473 backend tests with 3 skipped checks, Ruff, 8
  frontend tests, the frontend typecheck and 24-route production build,
  `pip check`, a single Alembic head, and a production npm audit with zero
  vulnerabilities.
- The release does not change the database schema, corpus, model configuration,
  identity policy, Cloud Run Jobs, quota, scaling, or budget limits.
- The GitHub release record identifies the immutable Cloud Build, deployed
  Cloud Run revision, source commit, and production verification results.

The preceding `v0.2.3` revision remains the immediate application rollback
point.
