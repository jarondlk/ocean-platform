# OCEAN Platform v0.4.2

Status: release candidate in [PR #56](https://github.com/jarondlk/ocean-platform/pull/56);
not yet merged, deployed, or released.

## Included

- `https://oceaninfobio.com` is the canonical application and Google OAuth
  callback origin. The default Cloud Run URL remains a controlled fallback.
- Data sample lists and details report environmental-analysis eligibility and
  exact exclusion reason codes from the API.
- Analysis exposes Eligibility and Exclusions directly. Empty result tables
  report the recorded exclusion count and link to the exclusion records.
- Repository deployment, authentication, roadmap, testing, and handoff records
  are aligned with the deployed v0.4.1 workflow and custom-domain follow-up.

## Scientific boundary

The retained ANEMONE pilot remains `sample_kind=unknown` and
`is_control=null`. This candidate does not approve or apply a classification and
does not claim contamination clearance, taxonomic accuracy, environmental
biodiversity validation, or CTD/SST overlap. Unknown and control samples remain
excluded from environmental-only analysis.

## Release gates

- Full local backend/frontend, dependency, migration, and production-build
  checks passed. A fresh PG16/pgvector database also passed all 12 focused
  PostgreSQL integration tests through schema head `20260905_0011` and was
  removed afterward.
- Custom-domain administrator logout/re-login, the admin-only route, and the
  active invitation register passed on 2026-09-08. Researcher-specific role
  enforcement, suspension, and uninvited-account denial still require the
  corresponding test identities.
- The researcher acceptance matrix must cover source-only, environmental-only,
  empty-cohort, citation, preview, controlled application, failure recovery, and
  rollback without inventing a scientific decision.
- Billing was reviewed on 2026-09-08: the JPY 10,000 project alert, JPY 4,000
  SQL alert, and JPY 2,250 Cloud Run spend cap remain configured. Posted values
  were JPY 0 after savings/credits for the project and SQL views, and JPY 32.95
  for Cloud Run. Billing can lag; the JPY 20,000 user ceiling remains unchanged.
- Before rollout, verify that the rendered API replaces the current fallback
  `CORS_ORIGINS` value with `https://oceaninfobio.com` while retaining the
  fallback Google OAuth callback for reviewed rollback.
