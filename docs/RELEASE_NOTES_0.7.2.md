# v0.7.2 — Dependency security and deployment readiness

This source patch includes the post-v0.7.1 dependency and repository audit fixes.
Published and deployed on 2026-10-06 from exact runtime source `03638e6`.
Revision `ocean-platform-v072-patch1006` serves 100% of production traffic.
Exact images, backup/restore, browser/history acceptance, cleanup and rollback
are recorded in [operations](RELEASE_0.7.2_OPERATIONS.md).

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
release CI passed before publication. Fresh Linux image/runtime checks and
normal candidate/production admin checks passed; no fresh viewer/researcher QA
is claimed for this dependency patch. See
[the dated audit](PRE_DEPLOYMENT_AUDIT_2026-10-06.md).

[#110](https://github.com/jarondlk/ocean-platform/issues/110) is resolved: the
installed standalone frontend independently reports source-map-js 1.2.2 and the
accepted digest is deployed. Full OS findings are unchanged and remain in #104;
repository advisory checks do not clear them. See [image QA](V0.7.2_CONTAINER_QA_2026-10-06.md).

Real ANEMONE physical/classification/area evidence, historical SST and the
six real research demos remain in #102/#103/#89. Live mobile QA is explicitly
deferred (#107); transient sign-out remains under investigation (#108). This
patch does not claim those checks or real scientific approvals passed.
