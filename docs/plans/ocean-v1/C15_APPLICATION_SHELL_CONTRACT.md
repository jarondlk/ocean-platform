# C15 application shell contract

C15 reuses the accepted P00 visual shell and isolates its synthetic domain state.
The v1 service entry does not import fixture state, infer identity from storage,
share legacy cookies or fall back to preview when a service fails.

## Server bootstrap

`GET /v1/runtime` is the only bootstrap route, requiring current authentication
and `profile:read`. `ENABLE_V1_SHELL` is strictly parsed and defaults false.
An explicit trusted `V1RuntimeConfiguration` binds a `v1:` site ID, permission
revision and immutable capabilities; a trusted callback may resolve it for the
current user. Missing/malformed configuration fails closed. Auth and configuration
work remain in owned workers with cancellation checkpoints.

The exact `ocean-v1-runtime-v1` envelope includes deployment `v1`, current UUID,
optional display name, active status, role, account type, permissions, permission
revision and seven capabilities. Research requires `chat:use`; Catalogue/Tools
require `data:read`; Settings/About require `profile:read`; Administration requires
`users:manage`; Feedback requires `feedback:write`. Missing permissions override
availability. Unintegrated domain capabilities cannot be configured ready.

## Client and navigation

`runtime.ts` verifies exact fields, permissions and bounded JSON. Same-origin
`/v1/runtime` uses no-store, credentials omitted, redirects rejected, bounded64KiB
streaming and optional trusted in-memory token supply. It never reads tokens or
roles from localStorage. Runtime/mode requests have a10-second UI deadline,
AbortController cleanup and stale-response protection. Refresh, focus and visible
page revalidation clear the previous identity while checking current access.

| Destination | v1 URL |
|---|---|
| Research | `/?view=research` |
| Context Catalog | `/?view=catalogue` |
| Tools | `/?view=tools` |
| Settings | `/?view=settings` |
| Administration | `/admin` |
| About | `/about` |
| Feedback | `/feedback` |

Links require permission; direct URLs are checked too. Domain destinations show
honest unavailable states until their owners integrate. Presentation storage
`ocean-v1-presentation-v1` permits only locale, theme, panel width/open state and
mobile pane. Scientific context remains typed C08 input with actual scope/filter,
snapshot and provenance labels; no default scientific selection is invented.

Shared primitives provide desktop splits, keyboard resizing, narrow tabs,
navigation drawers, focus restoration, themes, English/Japanese and status states.
P00 specialist domain components are mounted only in explicit synthetic preview.

## Preview and rollback

`/_ocean/runtime-mode` may explicitly select `synthetic-preview` only on a loopback
host. A missing mode endpoint selects service; a malformed/failed endpoint never
selects preview. `npm run preview` explicitly chooses synthetic mode and
`npm run preview:service` chooses service; both bind loopback and validate Host.
`npm run dev` uses service mode by default. Saved P00 namespaces remain intact.

Rollback disables the default-off shell flag or restores a compatible v1 build.
No schema migration, application-data mutation, legacy routing/cookie change,
provider or cloud operation is part of C15. Real OIDC integration and target
configuration remain deployment gates. Later components may explicitly supersede
unintegrated capability restrictions as their services pass acceptance.

See [handoff](handoffs/C15.md), [browser observations](evidence/C15/browser-qa.md)
and [local receipt](evidence/C15/verification.json) for source-bound evidence.
