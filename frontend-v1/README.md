# OCEAN v1 shell and explicit P00 preview

C15 adds a separate service shell using the authenticated, default-off
`GET /v1/runtime` bootstrap. Service identity, permissions and capability state
come from the server. Presentation preferences use `ocean-v1-presentation-v1`;
saved P00 roles, investigations and scientific selections never supply service
state. Functional destinations become available only through their owning
components. See the [C15 handoff](../docs/plans/ocean-v1/handoffs/C15.md).

C16 integrates the service catalogue through the actual C14 read-only API and
explicit C16 snapshot discovery. The host must configure a `CatalogueService`
and matching `CatalogueBrowser`, and enable `ENABLE_V1_SHELL`,
`ENABLE_V1_CATALOGUE` and `ENABLE_V1_CATALOGUE_BROWSER`; all default off. An
unconfigured host reports the catalogue unavailable. Discovery checks current
access and frozen source integrity, using an explicit newest-first registry.
Snapshot and canonical object IDs, filters and paging are restored from the URL.
Browsing never changes investigation scope or attaches data. Server totals,
query scope, completeness, scientific qualifications and native table units stay
visible; retained publication scope is distinguished from browsing scope.
Current access/revision changes clear protected views before retry. EN/JA,
light/dark, desktop/tablet/mobile and keyboard directory navigation are supported.
The service client/state live in `src/catalogue-service.ts` and
`src/catalogue-browser-state.ts`; `src/catalogue-browser.tsx` renders the tree,
listing and inspector. C18 may consume its typed selection notification later.
See the [C16 handoff](../docs/plans/ocean-v1/handoffs/C16.md).

`npm run preview` explicitly selects the synthetic P00 preview below.
`npm run preview:service` serves the built service shell without a configured
bootstrap and therefore shows an honest unavailable state. Both static preview
commands are loopback-only. `npm run dev` defaults to service mode because it
does not expose the explicit preview-mode endpoint. Neither command supplies real
authentication, catalogue data or a production deployment. A v1 deployment must
provide its own same-origin authenticated bootstrap and trusted target config.

The following review journeys describe the accepted synthetic prototype only.

Research-first OCEAN v1 UI with sky/baby-blue accents, concise language and a
replaceable typed synthetic adapter. The legacy frontend and backend are intact.

## Run locally

Node 22 and npm are required. No environment file, credentials, database, model
or cloud resource is needed.

```sh
cd frontend-v1
npm ci --ignore-scripts --no-audit --no-fund
npm run typecheck
npm test
npm run build
npm run preview
```

Open http://127.0.0.1:3100. The preview server binds only to loopback; Ctrl-C stops
it. `npm run dev` serves the source with hot reload on the same address/port;
stop the static server first. The static server reads `out/` after a build; reload
the browser after rebuilding. No request is made to the legacy site or a provider.
The preview CSP limits connections and assets to the current origin. Dependency
installation accesses the npm registry when packages are not already cached.

## Review journeys

- Start a question on Research, or reopen a recent investigation.
- Open the catalogue overview and inspect its six-record relationship map.
  Candidate links and analysis references are separate; physical pairing is not
  verified. The map has equivalent keyboard-accessible record/link lists.
- Browse all five catalogue roots and four source families. Search is exhaustive
  across this small sample inventory, with five entries per page and full totals.
- “Use this data” supplements context. “Limit investigation” asks for review,
  then pins a restriction. Browsing does neither. Remove/undo are reversible.
- Ask a sample question, inspect simulated activity, open its receipt and results.
  Drafts, conversations, original scope and evidence survive navigation/reload.
- Open Experiments, inspect code/cohort/limits, approve a specific preview version
  and simulate a result. Editing invalidates approval. **No Python executes.**
- Reopen Summer field observations and refresh: a new snapshot branch flags the
  removed selection while the original stays available.
- Preview controls (top-right) select loading, empty, zero, unknown coverage,
  error, unavailable, revoked, partial, clarification and interrupted scenarios.
  These controls are separate from research. Reset affects only local sample data.
- The top account badge shows account type and access role independently.
  Preview controls can simulate Research/Commercial/Internal accounts and
  Viewer/Researcher/Admin roles. Viewer metadata access, row/export restrictions
  and Admin navigation are UI simulations, never authorization proof.
- Open Administration with the Admin preview role: users/invitations, feedback
  triage, database paging, retention/authority, settings
  and audit/debug are local simulations. No invite is sent and no worker runs.
- About, Feedback and Administration have dedicated `/about`, `/feedback` and
  `/admin` routes. Creator/affiliation and nonfunctional contact emails are
  explicit placeholders. Feedback, including answer ratings, saves locally.
- Export investigations (JSON/Markdown), complete tables (CSV with units and
  synthetic/snapshot/record labels), plots (SVG), receipts and proposals (JSON).
  Table text neutralizes spreadsheet formula prefixes; numeric negatives survive.
- Use the language/theme buttons, keyboard controls and narrow-screen Chat/
  Workspace tabs. The Workspace divider also accepts Left/Right arrow keys.

Synthetic state is stored under `ocean-p00-synthetic-v1` in browser localStorage.
Admin state uses `ocean-p00-admin-v1` and loads only when the Admin simulation
mounts. Reset sample data also clears that state. Storage failure is explicit. Every generated-looking output is labelled sample
or simulated. This is deliberately a local-only prototype, never a fallback for
an unavailable real service. There is no authentication or authorization proof.

## Contract and integration boundaries

`src/model.ts` contains provisional interaction types. `src/adapter.ts` is the
only fixture transport/data-access boundary; `src/fixtures.ts` owns sample records.
`src/state.ts` owns local conversations, context revisions, frozen simulations,
snapshot branching and version-bound proposal approval. No database schema or
real execution protocol is implied by those models.

| Later component | Replaces or integrates |
|---|---|
| C08/C09 | Provisional catalogue contracts and synthetic snapshots |
| C14/C16 | Catalogue list/open/query adapter and complete authorized inventory |
| C15/C17/C18 | Shell, roles, durable investigations and Chat/Workspace |
| C19/C20/C21 | Simulated exploration, live run transport and evidence |
| C22–C25 | Proposal eligibility/approval, real isolated execution and experimental UI |

The prototype tests exercise scope, paging, drafts, continuations, evidence links,
snapshot refresh, approval invalidation, feedback, safe exports, admin guards,
invites, retained job-model contracts, configuration and validated browser-state restoration. They prove only local
prototype behavior. Screenshots and observed browser checks are recorded in
`docs/plans/ocean-v1/handoffs/P00.md`. The user accepted the P00 direction on 2026-10-14 JST after requesting the
Pipeline & jobs page be omitted. P00 acceptance is preserved; current component
status is maintained in [`STATUS.md`](../docs/plans/ocean-v1/STATUS.md).

The industry-guidance UX review and scoped results are recorded in
[UX verification](../docs/plans/ocean-v1/UX_VERIFICATION_2026-10-13.md).

Pipeline & jobs and its queue controls are omitted from the accepted admin UI.
The previous versioned browser-state shape and job-model tests remain compatible
with earlier saved previews; no job page or queue action is exposed. Backend job
execution remains planned under C20/C24 and is not implemented by this prototype.
