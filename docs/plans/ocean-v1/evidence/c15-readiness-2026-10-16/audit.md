# C15 readiness preparation — 2026-10-16 JST

Formal prerequisites and the existing local frontend baseline pass. **The
sequential pipeline gate remains pending final C14 source CI and delivery
confirmation from the parent. C15 implementation has not started.** This audit
does not promote the component or edit its application, handoff or global status.

## Inspected boundary and authorization

Read the C15 specification and exact prompts, planning hub, master plan,
decisions, status, acceptance map, site separation, UX brief and P00/C08 handoffs.
Inspected the actual `frontend-v1` application, package scripts, static export,
loopback preview server, provisional model/fixture adapter, research shell,
local state, translations, shared controls and responsive styles. The legacy
AppShell, AppNavigation and preferences were read as references only.

The accepted P00 direction is research first, wordmark only, restrained
`#56b4e9` accents, English/Japanese, light/dark, clear account type versus role,
Research / Context Catalog / Tools, and seven administrative areas with no
Pipeline & jobs page. Its 2026-10-14 acceptance and source receipt remain
historical UX evidence. They do not establish C15 runtime or access acceptance.

The user has authorized sequential readiness and implementation, subagents and
repository delivery. This preparation is deliberately read only except for its
own evidence directory. Scientific approvals, real data transfer, live providers,
cloud targets, provisioning and deployment retain their separate gates.

## Exact prerequisite reconciliation

Source baseline is C13 delivery checkpoint
`b0cac5ef23705852d4420df897db9d1c8f5bd057`. All **48** formal source entries match
accepted current hashes:

| Prerequisite | Current entries | Original matches | Recorded supersessions |
|---|---:|---:|---:|
| P00 | 36 | 32 | 4 accepted C07 CSV/export and associated test changes |
| C08 | 12 | 6 | 6 accepted C12 scientific/browser contract changes |

The original P00 aggregate is
`1b666844066d31d82f915502291b506f45e6e8989612c3b4071af12c08a0bb21`;
the original C08 aggregate is
`6934486ee263d812b6bb28796c6e8f36f1ec42953eb7ef5e4dc294a6be1f3d7c`.
Original receipts are unchanged. `start-snapshot.json` binds every current path,
its original hash, superseding receipt and receipt hash. The 30 unrelated files,
seven real scientific artifacts, two serving files, all 36 P00 current files and
**494 earlier committed evidence files** remain byte-for-byte preserved. Mutable
C14 logs and receipts are deliberately excluded from the preservation baseline.

The separate C14 accepted source map currently binds 14 source paths with
aggregate
`460a215e57aa22290a30dec9373c4e2fdc813ec846e0f8232794fea7f0573b89`.
Its local success does not clear the pending hosted delivery gate in this audit.

## Existing checks retained through interruption

The baseline checks had completed before the account interruption. They were
not repeated after the scheduled resume. `results.json` and the original logs
remain unchanged; the final verification rechecks their hashes and current
source/preservation entries.

| Command | Existing result |
|---|---|
| `npm --prefix frontend-v1 test` | **163 passed**, zero failed/skipped/cancelled |
| `npm --prefix frontend-v1 run typecheck` | Pass, including Next route type generation |
| `npm --prefix frontend-v1 run build` | Pass; static `/`, `/about`, `/admin`, `/feedback` and not-found export |
| Nine existing generated-contract scripts with `--check` | All pass |

The generated comparisons cover chat scope, C08 schema/types/examples, C09
snapshot, C10 adapters, C11 SST, C12 eDNA and C13 scientific index. Exact commands,
exit codes and timings are in `results.json`. Local Node is **22.14.0**, npm
**10.9.2**, using already installed local modules. No dependency installation,
provider/model/database call or persistent service startup was needed. No v1
environment file was present. Build outputs are the ignored `.next` and `out`
directories; no tracked application source changed.

The tests validate existing contracts and prototype behavior. There was no fresh
C15 keyboard, screen-reader, visual viewport or real-service browser acceptance
in this preparation. P00's historical browser walkthroughs remain clearly
separate from the checks C15 must perform.

## Current shell facts and C15 implementation decisions

1. **Reuse the accepted application.** `src/research-app.tsx` already owns the
   navigation, account controls, mobile drawer, Chat/Workspace switch and
   resizable workspace; `src/ui.tsx` supplies modal focus trapping, tabs and
   state panels. Preserve its design tokens, translations and accepted route
   grouping while extracting reusable shell/panel primitives. Do not restart
   from mockup images or import the legacy shell/session implementation.
2. **Separate runtime and preview explicitly.** The current application always
   imports `fixtureAdapter` and constructs synthetic investigations. It is a
   static export with no authentication/API routes. C15 needs an explicit v1
   runtime/capability boundary, with loading, error, unauthorized and unavailable
   states. Missing services must never load sample answers or simulation
   controls silently. Keep any retained preview entry visibly local/sample and
   make production configuration fail closed if fixture mode is requested.
3. **Use trusted permissions.** P00 role/account selections live in browser
   preferences and are simulations. Runtime identity, permissions and capability
   availability must come from a trusted v1 dependency, not localStorage or a
   user-selected role. Gate both navigation and direct destination rendering;
   changing route/query parameters must not expose hidden content. C14 requires
   `data:read` for catalogue exposure. Other destinations must use their owning
   permission/capability rather than inferring one blanket researcher rule.
   Account type and role remain independent labels.
4. **Keep C15's ownership bounded.** Supply shell slots and honest unavailable
   destinations for the catalogue, investigations, specialist tools, experiments
   and administration until their owners are integrated. Functional exhaustive
   catalogue browsing belongs to C16; durable investigations to C17; Chat and
   Workspace behavior to C18; execution and experiment UX remain later work.
   P00 administrative mutations and timers must not appear as live behavior.
5. **Adopt C08 without a lossy authority projection.** The runtime shell should
   accept typed snapshot/scope/status labels from the C08 browser boundary and
   leave domain state to later consumers. P00's provisional catalogue node,
   page-number paging and generic `complete` flag cannot substitute for C08
   cursor, total/unknown, source completeness, query completion and authority
   semantics. Shell state must never change scientific scope merely on resize,
   navigation, theme or language changes.
6. **Separate presentational persistence.** Current P00 preferences include role
   and account type beside synthetic investigation state under
   `ocean-p00-synthetic-v1`; administration uses `ocean-p00-admin-v1`. Add a v1
   presentation-only namespace for locale, theme and panel choices. Never treat
   those stores as runtime identity, source scope or durable investigation data,
   and never consume legacy session cookies or legacy preference namespaces.
7. **Preserve accessible navigation and panels.** Reuse the skip link, visible
   focus, modal restore, inert drawer background, escape handling and separator
   keyboard controls. Add shared split-panel/tab/drawer contracts without
   duplicating catalogue or investigation state. Verify narrow and intermediate
   widths as well as desktop; long Japanese labels must not clip essential
   controls. The existing 760/950/1200 px transitions and reduced-motion CSS are
   useful starting points, not acceptance on their own.

## Runtime and UX acceptance gates for implementation

Use independent v1 service configuration and an explicitly supplied trusted
session/capability transport. C15 must choose and document that local boundary;
the current static preview has none. Do not introduce a proxy to the legacy API,
reuse its environment file or share its cookies. Deployed OIDC configuration,
hostnames, credentials and isolation remain later operator/cloud gates. A local
test dependency can exercise real shell runtime states without production
credentials or scientific data.

The existing preview script binds **127.0.0.1:3100** and serves the static `out/`
directory. It requires a successful build, no credentials and no database.
Its CSP restricts connections/assets to the current origin and no external
fonts/media are imported by the inspected shell. No preview process was started
here; ensure the port is free before future browser checks. Do not mistake this
preview's `unsafe-inline`/`unsafe-eval` policy for a deployed runtime security
acceptance decision.

For C15 acceptance, record UI and direct-link permission denial, loading/error/
unavailable recovery, no fixture fallback in runtime mode, separate preferences,
Back/Forward and route changes preserving consumer state, keyboard navigation,
drawer dismissal/focus restoration and separator arrows. Inspect English and
Japanese in both themes at desktop (1440×900), narrow (390×844) and an intermediate
tablet width, with long labels and reduced motion. Automated tests supplement
these walkthroughs; do not claim formal assistive-technology compliance from
tests or screenshots alone. Rollback must disable or replace the v1 shell without
altering legacy routing or clearing v1 application data.

## Exact next action

Preserve these source/log receipts. Await the parent's exact final C14 source CI
and delivery confirmation. After that independent pipeline gate passes, record
a separate readiness confirmation and begin only C15 checkpoint 1 under the
user's existing sequential authorization. This preparation creates no component
implementation, app/global-status edits, commit, push, cloud resource or data copy.
