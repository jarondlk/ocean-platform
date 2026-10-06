# v0.7.2 — Dependency security and deployment readiness

This source patch includes the post-v0.7.1 dependency and repository audit fixes.
GCP rollout is a separate next step; production remains v0.7.1 until exact-image
acceptance and promotion are recorded in [operations](RELEASE_0.7.2_OPERATIONS.md).

- Pin transitive `source-map-js` to **1.2.2**, the patched release for indexed
  source-map event-loop denial of service
  ([GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)).
  The advisory does not establish an exploited OCEAN request path.
- Require all maintained application/corpus tables and the exact Alembic head
  in database readiness checks. Report actual and expected heads; an old or
  incomplete database no longer reports ready.
- Make document building, pre-analysis and reliability CLI help/invalid arguments
  exit before processing or regenerating artifacts.
- Bootstrap the full candidate database and save independent readiness evidence
  before backup/restore. Enforce production npm audit in the ordinary build and
  make candidate report prefixes reusable across releases.
- Update operating docs and inventory all active, operator-only and historical
  scripts. Retain legacy/replay evidence; remove stale local deployment renders
  from the deployment directory.

No new database migration is added. Schema head remains `20261005_0016`; retained
Chat history, corpus, scientific registries and publications are unchanged by this
source patch. Keep the additive schema when rolling back the application.

The preceding audit passed 1,066 backend tests, 39 isolated PostgreSQL integration
checks and a complete 34-table synthetic backup/restore, plus 64 frontend tests,
typecheck/build, lint, scope generation and dependency consistency. Exact-source
release CI is verified before publication; fresh Linux image scans/runtime
checks and normal candidate/production checks remain deployment gates. See
[the dated audit](PRE_DEPLOYMENT_AUDIT_2026-10-06.md).

[#110](https://github.com/jarondlk/ocean-platform/issues/110) remains open until
the patched production image is independently verified and deployed. Prior
container OS findings remain in #104; repository advisory checks do not clear
them. Real ANEMONE physical/classification/area evidence, historical SST and the
six real research demos remain in #102/#103/#89. Live mobile QA is explicitly
deferred (#107); transient sign-out remains under investigation (#108). This
patch does not claim those checks or real scientific approvals passed.
