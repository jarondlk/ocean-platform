# Accepted decisions

Recorded 2026-10-12 JST from the originating planning conversation. This file
records choices, not proof of implementation. P00 is selected for local
implementation and accepted; C01–C03 local acceptance is Complete. C04 authentication responsiveness is also Complete locally; C05–C27 remain Not started.
Later explicit user instructions override this baseline; record changes here
and identify affected components instead of silently drifting.

| ID | Decision | Origin |
|---|---|---|
| D01 | Catalogue-guided Research is the v1 site default after acceptance. The existing production site retains its legacy architecture and traffic; no main-domain cutover is implied. | Revised by user, 2026-10-13 |
| D02 | Include CTD, SST, metagenome and eDNA; expose only scientifically supported operations. | User selected |
| D03 | Include an experimental analysis workspace in v1. | User selected |
| D04 | Approve each concrete experiment plan; bind code, cohort and method to approval. | User selected |
| D05 | Python on frozen eligible data; no internet, package installation or R. | User selected |
| D06 | Chat plus Workspace, not a notebook-first product. | User selected |
| D07 | Experiments exclude unpublished staging data. | User selected |
| D08 | Dedicated GCP Linux/gVisor worker; no dependency on Cloud Run sandbox preview. | User selected |
| D09 | Ordinary exploration may take up to three minutes, with progress/cancellation. | User selected |
| D10 | Research is the unified home on the separate v1 site; retain relevant specialist workflows there and leave legacy-site links intact. | Revised by user, 2026-10-13 |
| D11 | A named investigation contains multiple conversations and accumulated artifacts. | User selected |
| D12 | Manual browsing does not change agent scope; use explicit attachment/pinning. | User selected |
| D13 | Investigations are private to their owner in v1. | User selected |
| D14 | Pin investigation data; explicit refresh creates an updated branch. | User selected |
| D15 | Full Context Catalog browser is a separate primary tab and an acceptance requirement. | User requested |
| D16 | Major UI overhaul, preserving OCEAN identity and scientific legibility. | User requested |
| D17 | Five roots: Data, Analyses, Statistics, Metadata, Relationships. | Accepted design |
| D18 | Canonical object IDs; directories/facets/cross-links are views, not duplicate data. | Accepted design |
| D19 | Full permitted inventory and scoped aggregate totals; page limits never stand in for corpus counts. | User motivation and accepted design |
| D20 | Query readiness independent of embeddings; keep scientific approval distinct from publication and operational acceptance. | Accepted design |
| D21 | Immutable snapshots and receipts; PyArrow/Pandas adapters with exact-service parity. | Accepted design |
| D22 | Typed provider-independent actions; no unrestricted SQL/admin/publication tools. | Accepted design |
| D23 | Shared deterministic scope validation and completion checklist; partial outcomes are explicit. | Accepted design |
| D24 | Attach supplements context; Pin constraint restricts scope. Context is revisioned per run. | Accepted design |
| D25 | Separate chat transcripts; other chats' narratives are not implicit evidence. | Accepted design |
| D26 | Workspace tabs: Context, Results, Experiments, Evidence. Activity lives in Chat. | Accepted design and UI concept |
| D27 | Cloud Run controller + Cloud Tasks/outbox/leases; dedicated experiment worker. | Accepted design |
| D28 | 12 tool actions, one action repair, 100 default/500 maximum record rows; 180 active seconds. | Initial configurable defaults |
| D29 | Python: 2 CPUs, 4 GiB, 10 min, 256 MiB inputs, 50 MiB outputs; 1 active/user, 2 globally. | Initial configurable defaults |
| D30 | Preserve provider/role semantics and reused-code regressions; the legacy site keeps its endpoints/history/deep links. V1 does not share sessions or automatically import accounts/history. | Revised by user, 2026-10-13 |
| D31 | Existing access rules also apply to catalogue counts, metadata and retained artifacts. | Accepted design |
| D32 | Experimental outputs remain experimental; no automatic scientific publication or authority upgrades. | Accepted design |
| D33 | Contigs, unpublished inputs, external acquisition, R, GPUs and collaborative workspaces are excluded from v1. | Accepted boundary |
| D34 | Repository plan folder plus a dedicated Planning Hub chat; individual component prompts and resumable handoffs. | User selected |
| D35 | P00 is accepted and C01 scope validation was selected/completed locally. C02–C27 require separate component selection. | Revised by user, 2026-10-14 |
| D36 | A second GCP site with fully isolated infrastructure: database, storage, credentials, queues and deployment targets. Copy approved data explicitly when needed; no live connection to legacy data. | User selected, 2026-10-13 |
| D37 | Build and refine a synthetic local UI/UX prototype first (P00), then implement backend/integration components individually. | User selected, 2026-10-13 |
| D38 | Prioritize understandable, forgiving UX: plain language, progressive disclosure, recoverable actions and repeated user review before backend integration. | User selected, 2026-10-13 |

## Changes

2026-10-13 JST: the user requested a separate GCP site while keeping the legacy
production architecture in place, then explicitly selected full infrastructure
isolation with approved data copied when needed. The user also requested local
UI/UX iteration before backend implementation. D01/D10/D30 are narrowed to the
separate-site model; D35 retains the planning boundary; D36–D38 add isolation and
UI-first delivery. P00 is added before C01–C27 without renumbering them. Changes
affect all component deployment boundaries, C08/C09, C15–C18, C20/C21 and C24–C27;
acceptance adds local UX review and independent-site isolation/data transfer.
The overhaul branch is the work branch. No implementation, cloud creation or data
copy is started by this amendment. No implementation schedule is retained.

2026-10-13 JST, P00 selection: the user explicitly started the local prototype
and requested legacy OCEAN principles, research-first interaction, human-centered
UX, less copy and sky/baby-blue accents. This authorizes P00 only; user acceptance
of the working direction is still pending. See handoffs/P00.md.

## Adjustable defaults

D28/D29 are starting operational limits, not promised performance or scientifically
meaningful thresholds. A future component may propose a documented change after
measurements; do not silently increase resource access or scientific scope.
Routine internal details that do not change these decisions may be resolved
within a component and recorded in its handoff.

### P00 user review follow-up — 2026-10-13 JST

The initial preview was received positively. Requested local refinements are
wordmark-only branding, account type plus access role, legacy-informed admin
workflows, dedicated About/contact placeholders, catalogue overview/relationship
map, feedback and contextual exports. “Contracts” was clarified as “contacts.”
These are P00 interaction decisions; they do not authorize real authentication,
service integration, backend components, provisioning or deployment. The refined
preview is Ready for review; acceptance of the direction remains pending.

### P00 acceptance — 2026-10-14 JST

The user accepted the preview ("ok looks great"), requested omission of the admin
Pipeline & jobs page for now, and authorized committing and pushing the overhaul
work before backend implementation. The page, overview entry points, queue
settings and demo-jobs database listing are omitted. Other admin workflows and
previously saved local state remain available. P00 is Complete after the final
checks; C01–C27 remain unselected and Not started. Planned backend job execution
is not removed from C20/C24. C01 is the recommended next component.

### C01 selection — 2026-10-14 JST

The user explicitly selected C01. Local shared scientific-scope validation and
offline regression checks on overhaul are authorized. P00 prerequisite hashes
match the checkout. C02–C27, live providers, data transfers, cloud resources,
deployment and automatic repository delivery remain outside this selection.

### C01 completion — 2026-10-14 JST

Shared scope validation and offline acceptance are complete: 319 tests, Ruff and
diff checks pass. The typed versioned decision is used by published planning and
independently by immutable-result execution. Unsupported wording requires
clarification; original settings and exact result rows are retained. Detailed
evidence and limits are in [C01 handoff](handoffs/C01.md). C02–C27 remain unselected.

### C02 selection — 2026-10-14 JST

The user selected C02. Local F02/F04/F05 repairs, synthetic regeneration and
version/eligibility handling are authorized. Existing numerical thresholds remain;
producer success is not scientific approval. C03–C27 remain unselected.

### C02 local acceptance — 2026-10-14 JST

F02/F04/F05 software and synthetic acceptance are complete. Receipts bind frozen
inputs, output hashes and method versions; regenerated candidates require the
existing explicit EvidenceDecision review. Algorithmic tiers, regional SST
context and in-sample predictions do not establish independent scientific approval.
History and supersession are retained; affected legacy artifacts stay ineligible.
Required suites (92 tests), composite consumer/C01 regressions (485 tests), Ruff
and diff checks pass. See [C02 handoff](handoffs/C02.md) for exact receipts and
real-data review still outstanding. C03–C27 remain unselected.

### C03 selection — 2026-10-14 JST

The user selected C03 and permitted subagents where useful. Local transactional
retention/hold repairs, deterministic synthetic races and a fresh disposable
PostgreSQL cluster are authorized. Keep endpoint/report shapes and retention
duration; audit only committed actual changes. Existing production databases,
cloud deletion, destructive migrations and future research stores remain outside
scope. C04–C27 remain unselected; no automatic repository delivery is requested.

### C03 acceptance — 2026-10-14 JST

The retention cleanup DELETE rechecks the complete cutoff/status/unheld predicate
and returns actual removed parent IDs. Hold UPDATE uses the same row's transaction
ordering and returns not found after a committed deletion. Dependent feedback,
parent evidence and success audits commit or roll back together. Report and
endpoint shapes, retention durations and CLI confirmation remain unchanged.
35 required unit/CLI tests, 93 with auth/security, 12 actual PostgreSQL 18.3 cases
and the broader 1,684-test suite pass. The broader run has 51 expected PostgreSQL
gates; C03's separate required PostgreSQL run has zero skips. All fixture schemas
were removed and the owned server was stopped. See [C03 handoff](handoffs/C03.md).
C03 remains uncommitted; C04–C27 remain unselected. No production cleanup,
destructive migration, cloud deletion or automatic repository delivery occurred.

### C03 checkpoint and C04 selection — 2026-10-15 JST

The user requested checkpointing the completed work, immediately starting C04
and using subagents when useful. C03 and the readiness audit are saved in local
overhaul commit `9a2d225`; 30 older unrelated files remain outside the checkpoint.
Automatic approval review rejected remote push because the checkpoint instruction
was considered local authorization; explicit push/CI approval is pending. C04
local implementation, deterministic concurrency/security tests and subagents are
authorized. C05–C27, production access, providers and deployment remain unselected.

### C04 completion — 2026-10-15 JST

Complete synchronous authentication/session and limiter/connection operations
now run through Starlette thread offload. Pending AnyIO cancellation is checked
after worker cleanup before identity assignment or handler dispatch. Roles,
providers, invitations, quotas and shared limiter SQL are unchanged.
87 required tests, 1,705 full backend tests (51 expected PostgreSQL-gated skips),
81.46% coverage, Ruff and preservation checks pass; independent review has no
blocking findings. C04 remains uncommitted on top of the C03 checkpoint. Remote
C03 push approval remains pending; no deployment occurred. See handoffs/C04.md.
C05–C27 remain unselected.

### C03/C04 delivery approval — 2026-10-15 JST

The user explicitly approved all pending commits and pushes, resolving the
remote-push approval gate. Deliver C03/C04 and their reviewed evidence to
origin/overhaul (jarondlk/ocean-platform), preserve the 30 unrelated files, and
verify hosted CI. The user also requested a C05 readiness verdict; that does
not select C05 implementation, production indexing or deployment.
