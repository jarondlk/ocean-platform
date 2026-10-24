# C23 frontend dependency security amendment

On 2026-10-24 JST, both retained Next.js 15.5.27 lockfiles reproduced one
critical production audit finding. This explains the two frontend audit failures
in hosted run39883701375 for checkpoint5531f48; backend and PostgreSQL acceptance
from that run are separate.

Both official advisories list15.5.28 as the patched15.x release, and the
[15.5.28 release](https://github.com/vercel/next.js/releases/tag/v15.5.28) identifies
both fixes. We apply that single patch release, preserving the legacy caret and
v1 exact dependency styles. Only Next.js, its `@next/env` and matching platform
SWC packages change in either lockfile. All other package entries and the
existing `sharp:0.35.5` override remain unchanged. No major upgrade or automatic
`npm audit fix` was used.

- [GHSA-2464-fhr4-w9xw](https://github.com/advisories/GHSA-2464-fhr4-w9xw): the existing sharp override already meets its workaround, but the package identity remains audit-flagged until the Next.js patch.
- [GHSA-p3m5-59mp-jv5r](https://github.com/advisories/GHSA-p3m5-59mp-jv5r): the documented remediation is upgrading; deployment exposure is not inferred from an audit finding.

All eight acceptance commands pass on the final four dependency files:
production audits have zero vulnerabilities; legacy132/v1930 tests pass with no
failures/skips; both typechecks and builds pass. All201 tracked frontend source
paths remain byte-identical during acceptance. Raw stdout/stderr and per-command
timing/exit records are retained; the initial audit failures remain immutable.
The only informational stderr output is npm's new-version notice. npm itself
was not upgraded.

`verification.json` binds the baseline, final source supersessions, recorder and
all evidence. The four dependency files intentionally supersede their earlier
accepted hashes, without rewriting any original component receipts. Exact-source
hosted acceptance must be checked after root commits/pushes this amendment.

This work performs no deployment, cloud operation, data mutation or actual
sandbox execution and does not mark C23 Complete. Root owns STATUS/spec/handoff
integration and the eventual source checkpoint.
