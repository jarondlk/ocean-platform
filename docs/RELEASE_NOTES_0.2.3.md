# OCEAN Platform v0.2.3

`v0.2.3` is a focused maintenance release for the managed GCP prototype.

## User-visible correction

- The Pipeline availability summary now reports **Recent derived artifacts**.
  It counts only derived artifacts in the API's `recent` freshness class and
  excludes raw-source rows from the denominator.

## Contract and release hardening

- The frontend freshness type is closed over the five values emitted by the
  backend: `recent`, `aged`, `archival`, `missing`, and `unknown`.
- FastAPI and frontend version metadata now report `0.2.3`.
- Local validation passed 473 backend tests with 3 skipped checks and 74.54%
  aggregate coverage, Ruff, the frontend typecheck and 24-route production
  build, `pip check`, a single Alembic head, and a production npm audit with
  zero vulnerabilities.

## Deployment evidence

The release is tagged only after the exact merged `main` commit passes its
immutable Cloud Build, database migration, Cloud Run rollout, four bounded job
canaries, authenticated application checks, and log review. The GitHub
`production` deployment is the authoritative record for the deployed commit,
build, revision, job executions, and application URL.

The previous `v0.2.2` remediation revision `ocean-platform-00007-2dp` remains
available as the application rollback point. No legacy rollback resource is
deleted by this release.
