# Accepted decisions

Recorded 2026-10-12 JST from the originating planning conversation. This file
records choices, not proof of implementation. P00 is selected for local
implementation and accepted; C01–C07 local acceptance is Complete. C08 local acceptance is Complete; C09 is Complete locally; C10 is Complete locally; C11–C27 remain Not started.
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

### C03/C04 hosted delivery and C05 readiness — 2026-10-15 JST

C03 (9a2d225), C04 (6587069), and the narrowly scoped CI fixture identity repair
(276540f) are committed/pushed to overhaul. Hosted CI for 276540f passes: 1,714
backend tests, 82.28% coverage, both frontends, 39 existing PostgreSQL cases and
12 C03 cases plus isolated backup/restore. Initial CI exposed the job-owned Docker
server address mismatch; the repair retains local URL/database isolation and
requires an exact explicitly inspected private container identity in CI.
All 59 C05 baseline tests pass; independent read-only review reproduces its
known targets and verifies P00. C05 is ready to start after explicit selection;
no C05 application work, production index rebuild or deployment occurred.

### C05 selection — 2026-10-15 JST

The user explicitly started C05 and authorized subagents or other services when
needed. Local embedding-identity and metagenome-mapping repairs, synthetic
regressions and verified disposable PostgreSQL acceptance are authorized.
Completed P00/C01–C04 and older unrelated work are preserved. No production
reindex, real scientific regeneration, paid/provider calls, deployment or
automatic repository delivery is selected by this component request.

### C05 local acceptance — 2026-10-15 JST

Both PostgreSQL vector entry points bind the actual query provider/model/dimension.
Unidentified or incompatible vectors cannot rank; scoped independent FTS remains
available. Canonical Kraken/MetaEuk fields and a strict named legacy adapter preserve
method labels. Source, mapping, content and complete generation witnesses give
replacements fresh IDs; old rows/vectors remain traceable and inactive.
142 required tests, 12 C05 PostgreSQL cases (10 fixed-code and two exact baseline
bug probes), 39 existing PostgreSQL regressions, two idempotent corpus upserts
and the full backend (1,806 passed, 63 gated skips, 81.77% coverage) pass.
Independent review has no blockers. All owned servers are stopped; 30 unrelated
files, seven scientific artifacts and prior component sources/receipts are preserved
except the intended C05 API/loader/lineage/orchestration consumers documented in
its receipt. A read-only inventory records 82 legacy documents requiring a later
rebuild. C05 is Complete locally and uncommitted; no hosted C05 CI, provider call,
real-data regeneration, live reindex or deployment is claimed. C06–C27 remain
unselected. See [C05 handoff](handoffs/C05.md) and [runbook](C05_REBUILD_RUNBOOK.md).

### C05 delivery and C06 readiness approval — 2026-10-15 JST

The user explicitly requested commit/push and delivery checks on overhaul before
later C06 work. C05's 63 reviewed files are committed/pushed as fd8f520; 30 older
unrelated files remain preserved and excluded. Hosted run 38602439380 passes:
1,797 backend tests, 82.60% coverage, both frontends, 39 existing PostgreSQL cases,
12 C03 and 12 C05 plus corpus idempotence and backup/isolated restore.
C06 is ready for selection: formal P00 prerequisite and all 36 hashes match,
99 baseline tests pass, and 16 mocked payload probes plus the stubbed actual API
reproduce F07 without provider/DB calls or application changes. C06 remains
Not started/unselected. The real C05 rebuild, scientific/provider acceptance,
production access, main/legacy deployment and C06–C27 implementation remain
outside this delivery. [Audit](C06_READINESS_AUDIT_2026-10-15.md).

### C06 selection after readiness checkpoint — 2026-10-15 JST

The user requested finishing the pending checkpoint and C06 verification, then
starting C06, with subagents when useful. Checkpoint 44c85b9 records delivered
C05/hosted CI and verified C06 readiness. The earlier automatic review failure
was a usage-limit review failure, not an unsafe-action finding; the normal
review path now permits the requested checkpoint. C06 local runtime contract,
strict completion enforcement, compatibility metadata and mocked-provider
consumer acceptance are selected. Existing commit/push authorization persists.
Keep current model/provider configuration, embeddings, controller retry policy,
real artifacts, unrelated work and main/legacy deployment unchanged. No live
provider call, real scientific regeneration, deployment or C07–C27 work is selected.

### C06 local acceptance — 2026-10-15 JST

Immutable generation-result v1 and optional provider usage now normalize both
ordinary/structured adapters. Strict compatibility wrappers reject every incomplete
status, including nonempty Ollama length stops and parseable incomplete JSON.
API completion/failure and planner metadata retain request-local timing/usage
without partial answered receipts or raw provider exception details. Model/provider
configuration, embedding methods and existing retry budgets remain unchanged.
230 required/consumer tests, full backend 1,937 passed/63 explicit PostgreSQL skips
(81.81% coverage), 39 actual PostgreSQL regressions and two idempotent corpus upserts
pass. Independent review has no blockers. The owned server is stopped;30 unrelated
files, 7 scientific artifacts and36 P00 files are preserved. Existing delivery
authorization applies to C06 checkpoint/push and CI verification. No live provider,
real scientific regeneration, production migration, deployment or C07 selection.

### C06 hosted delivery — 2026-10-15 JST

C06 is committed/pushed as 27d76c9 under the continuing delivery authorization.
Hosted run 38667543787 passes: 1,928 backend tests, 82.64% coverage, both frontends,
39 existing PostgreSQL cases plus 12 C03 and 12 C05, idempotent corpus upsert and
backup/isolated restore. The local 1,937 count includes 9 unrelated benchmark tests
excluded from delivery. All 16 C06 source/test hashes match the accepted source;
30 unrelated files and real artifacts remain intact. Final delivery evidence is
saved separately from the frozen local receipt. C06 is Complete locally and
delivered; C07–C27 remain unselected. No real provider call or deployment occurred.

### C07 selection — 2026-10-15 JST

The user selected C07 and approved subagents/services. Formal P00 acceptance
matches all 36 source files before changes; delivered C06 matches all 16 accepted
source/test files and its hosted CI passes. Local browser/server CSV safety,
shared fixtures, existing consumer checks and existing commit/push authorization
apply. The intended v1 exports/admin helper and focused tests may change under
C07; preserve the historical P00 receipt and all other prototype behavior.
Use presentation escaping only; preserve numeric signs, canonical/JSON values,
metadata, truncation, permissions, immutable bundle bytes and real data artifacts.
No provider, production access, deployment, real regeneration or C08 selection.

### C07 local acceptance — 2026-10-15 JST

The shared 47-case contract and explicit whitespace union now protect original
string values/headers before CSV quoting. Typed numeric signs remain numeric;
objects/arrays use compact JSON, booleans lowercase and null/undefined empty.
All browser/server consumers share one policy per language. Export filenames,
line endings/BOM, columns/provenance, truncation indicators, access/audit and
source/immutable bundle values remain intact. Compact JSON reason arrays replace
the administrator CSV's semicolon list presentation. No scientific values change.
196 focused backend tests, 132 legacy frontend/76 v1 tests, both typechecks/builds
and full backend 2,121 passed/63 gated skips (81.85%) pass. Independent review and
835-value cross-runtime probe have no blockers/mismatches. Local legacy dependencies
were restored to the unchanged Next 15.5.27 lock and checks repeated. Four intended
P00 CSV consumer/test files are superseded under C07; preserve the historical
receipt and all other P00/unrelated/scientific work. Existing commit/push approval
continues; no C08 selection or deployment.

### C07 hosted delivery — 2026-10-15 JST

C07 is committed/pushed as `119579646919da83a2a53159a599a66c488ff607`. [Hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38670737411) passes
2,112 backend tests (82.67% coverage), 132 legacy/76 v1 tests, both
frontend typechecks/builds and production dependency audits, 63 actual PostgreSQL
cases, idempotent upsert and isolated backup/restore. The nine older unrelated
local benchmark tests are excluded from delivery; dependency review is skipped
on push as configured. [Delivery evidence](evidence/C07/delivery.json) is saved
separately from the frozen local receipt. Source, scientific/serving artifacts,
canonical bundle bytes, historical receipts and all 30 unrelated files remain
preserved. C08 remains unselected; no provider call, regeneration or deployment.

### C08 selection — 2026-10-15 JST

The user selected C08 after readiness verification. Implement versioned shared
catalogue contracts, a frontend-v1 adapter boundary and synthetic catalogue
fixtures/checks; preserve accepted P00 interactions and C01 scientific scope.
No C09, storage, endpoints, UI integration, cloud/provider or real transfers.
Existing subagent and commit/push authorization persists. Preserve all unrelated
work and historical receipts.

### C08 local acceptance — 2026-10-15 JST

`context-catalogue-v1` freezes canonical identities, five roots, source-qualified
scopes, independent lifecycle/completeness, exact whole-scope counts and bound
cursors. Python owns generated JSON Schema and TS types; one opt-in boundary
retains full validated semantics beside P00 projection. Existing UI/runtime
source is unchanged. 274 required tests, 162 v1 tests/typecheck/build, full backend
2,314 passed/63 gated skips (82.28%), 100,000-dataset traversal and
10,398 cross-runtime cases pass. Reviewer-reported privacy/schema/date issues are
fixed; final root signoff records reviewer usage interruption honestly. Cursors
are reference context tokens, not signed authorization; fixture scale does not
prove service performance. All prior artifacts/receipts and unrelated work are
preserved. Existing delivery approval persists; no C09, transfer or deployment.

### C08 hosted delivery — 2026-10-15 JST

C08 is committed/pushed as `6d20a75ef74770346a80c815c234b50348ae650a`. [Hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38695834706) passes
2,305 backend tests (83.09% coverage), 132 legacy/162 v1 tests, both
frontend typechecks/builds and production dependency audits, all 63 actual
PostgreSQL cases, idempotent upsert and isolated backup/restore. Nine older
unrelated local benchmark tests are excluded from delivery; dependency review
is skipped on push as configured. [Delivery evidence](evidence/C08/delivery.json)
is separate from the frozen local receipt. All 12 accepted C08 hashes and
current P00/C01/C07 sources, historical evidence, scientific/serving artifacts
and 30 unrelated files remain preserved. C09 remains unselected; no provider,
transfer, production mutation or deployment occurred.

### C09 selection — 2026-10-15 JST

The user selected C09 after the verified readiness checkpoint and permits
subagents/services when necessary. Implement the sealed snapshot contract,
explicit local store, capture coordination, references/holds/current revocation
and synthetic transfer quarantine. Use only injected source exporters, synthetic
files and a newly verified disposable PostgreSQL database; preserve legacy
runtime and real data. Existing commit/push authorization persists. C10 and all
real transfers, publication/cloud/provider/deployment operations remain unselected.

### C09 accepted local boundaries — 2026-10-15 JST

C09 passes sealed byte identity, references/holds/current revocation, bounded
repeatable-read exports and final generation locks, retained old manifests,
computed export changes and synthetic approved-copy quarantine. All enabled
families are captured in full; scientific filters are rejected before DB access
and belong to C10–C13 adapters. Local control state serializes latest/reference/
hold/retirement decisions; cleanup retires logically and reports zero physical
deletions. PostgreSQL and files have separate commit boundaries; uncertain local
CAS or database release requires pointer reconciliation before retry. Transfers
never promote latest and chained origins are rejected pending typed multi-hop
lineage. No authenticated endpoints, real data, production stores, provider/cloud
operations or C10 are selected. See C09_SNAPSHOT_CONTRACT.md and handoffs/C09.md.

### C09 delivery — 2026-10-15 JST

Implementation 9214bbe is committed/pushed with exact-source hosted CI passing:
2,460 backend tests/83.39% coverage, 84 actual PostgreSQL cases, 162 v1/132 legacy
frontend tests, both typechecks/builds, zero-vulnerability production audits,
idempotent upsert and isolated backup/restore. Fourteen accepted source files,
the local receipt and all preserved historical/unrelated/scientific/serving
files remain unchanged. See evidence/C09/delivery.json. No C10 is selected.

### C10 selection — 2026-10-15 JST

The user selected C10 after readiness checkpoint 8eae8eb. Work is limited to
frozen CTD/metagenome inputs, canonical catalogue registration, complete-scope
operations and local synthetic reproducibility acceptance. Existing delivery
approval persists. C11, real copies/publication, UI/API and cloud remain unselected.

### C10 accepted local boundaries — 2026-10-15 JST

C10 passes fixed-generation frozen exports, source-owned primitive Parquet
validation and canonical C08 inventory/section/operation integration. Exact scoped
counts/aggregates use complete retained populations; ranked omission, null cells
and explicit zero remain distinct. Coarse/mixed collection precision and declared
depth sign/units are retained. Current callbacks cover complete datasets; C14
still owns role/session and finer service authorization. Plain value encodings
and explicit decode bounds reject unsupported inputs without truncation. Real
source mappings/copies, scientific approval, APIs/UI, C11 and deployment remain
unselected. See handoffs/C10.md and C10_ADAPTER_CONTRACT.md.

### C10 delivery — 2026-10-15 JST

Implementation c3d5b8b is committed/pushed with exact-source CI passing: 2,570
backend tests/83.68% coverage, 84 actual PostgreSQL cases, 132 legacy/162 v1
frontend tests, both typechecks/builds and production dependency audits, idempotent
upsert and isolated backup/restore. All ten accepted C10 files, fourteen C09 files,
twelve C08 files and historical/unrelated/scientific/serving evidence are preserved.
The local receipt remains unchanged; see evidence/C10/delivery.json. No C11, real
copy/publication, provider service or GCP deployment is selected.

### C11 selection — 2026-10-15 JST

The user selected C11 implementation after readiness checkpoint b73b29b and
authorized subagents as useful. Work covers source-owned frozen SST products,
observations, exact scoped operations, sampling-aware coverage and local synthetic
reproducibility. Prior commit/push approval persists. Separate product generations,
actual spatial support and UTC/JST/date precision must remain explicit. C12,
real acquisition/copying/publication, UI/API integration and cloud remain unselected.

### C11 accepted local boundaries — 2026-10-15 JST

C11 passes source-owned SST metadata and primitive Parquet registration, canonical
product/collection/dataset inventory, exact complete-scope queries and explicit
daily coverage contracts. Product generations, actual resolution/support, units,
quality flags/fractions/pixel counts, UTC/JST/date precision and independent copy
origins are preserved. Grid points and regional means remain distinct. Current
trusted whole-dataset callbacks supply access and scientific eligibility; metadata
cannot self-approve. Local acceptance passes 966 required tests and 2,829 backend
tests/83.29% coverage; 84 PostgreSQL cases remain the separate hosted gate.
No actual source mappings/copies, publication, provider calls, UI/API, C12 or GCP
deployment is selected. Read handoffs/C11.md and C11_SST_ADAPTER_CONTRACT.md.
