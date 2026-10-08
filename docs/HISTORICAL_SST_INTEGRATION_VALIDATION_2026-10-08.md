# Historical SST integration validation — 2026-10-08

Subsequent status: v0.7.4 provisional Miyagi publication and production Chat
acceptance passed on 2026-10-08 JST. The following preparation account retains
its dated evidence; see [current operations](RELEASE_0.7.4_OPERATIONS.md).

Draft PR #119 extends verified local context diagnostics with the user-accepted
provisional QC, weighting, calendar, matching and relative-temperature rules.
Production remains v0.7.3; historical scientific evidence is not published.

## Local verification

- Full backend/security suite: 1,230 passed, 39 opt-in PostgreSQL tests skipped,
  80.23% coverage. Active Python lint and generated Chat scope contract passed.
- Real February 2021 mask-with-warning quality preview: 26 supported final days,
  284 retained open-sea grid points per day; two final-series gaps preserved.
- Two retained ANEMONE occurrences matched within 7.33/7.42 hours. Unresolved
  physical identities, reported coordinates and diagnostic rectangle membership
  remain flagged. The short 26-day baseline produces 9 low/8 middle/9 high days.
  This exercises mechanics, not full-period coastal or historical Chat acceptance.
- Exact diagnostics and matching preview hashes, accepted choices and remaining
  engineering are in [the analysis policy](HISTORICAL_SST_ANALYSIS_POLICY_2026-10-07.md).

## Dependency audit correction

The frontend job on implementation commit `3e71fcd086829f9b73baa580be37afbc466ea549`
stopped at its production dependency audit. The npm audit identified the locked
Next.js 15.5.26 package against two moderate cache-poisoning advisories:
[GHSA-4jqv-mc3x-m676](https://github.com/vercel/next.js/security/advisories/GHSA-4jqv-mc3x-m676)
and [GHSA-mcj8-r9mp-w47p](https://github.com/vercel/next.js/security/advisories/GHSA-mcj8-r9mp-w47p).
The audit failure occurred before frontend tests/typecheck/build; those checks
were not successful on that CI attempt. Dependency findings do not establish
that a particular OCEAN route is exploitable.

Update the Next.js minimum and lockfile to **15.5.27**, including its matching
environment and platform compiler packages. A clean local installation, production
dependency audit (**zero vulnerabilities**), frontend tests, TypeScript check and
production build all passed afterward. No audit threshold was weakened. This
source fix is part of PR #119; deploying it requires the normal release workflow.

GitHub CI on the final PR head supplies the PostgreSQL integration and exact-
commit frontend/backend/CodeQL/dependency results. Keep this preparation separate
from scientific registry application/publication and historical Chat QA. #102,
#103 and #89 remain open; OS/container maintenance in #104 remains separate.
