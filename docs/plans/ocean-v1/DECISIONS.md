# Accepted decisions

Recorded 2026-10-12 JST from the originating planning conversation. This file
records choices, not proof of implementation. All C01–C27 start Not started.
Later explicit user instructions override this baseline; record changes here
and identify affected components instead of silently drifting.

| ID | Decision | Origin |
|---|---|---|
| D01 | Catalogue-guided Research becomes default after acceptance; legacy Chat remains available for rollback. | User selected |
| D02 | Include CTD, SST, metagenome and eDNA; expose only scientifically supported operations. | User selected |
| D03 | Include an experimental analysis workspace in v1. | User selected |
| D04 | Approve each concrete experiment plan; bind code, cohort and method to approval. | User selected |
| D05 | Python on frozen eligible data; no internet, package installation or R. | User selected |
| D06 | Chat plus Workspace, not a notebook-first product. | User selected |
| D07 | Experiments exclude unpublished staging data. | User selected |
| D08 | Dedicated GCP Linux/gVisor worker; no dependency on Cloud Run sandbox preview. | User selected |
| D09 | Ordinary exploration may take up to three minutes, with progress/cancellation. | User selected |
| D10 | Research is the unified home; retain specialist pages and direct links. | User selected |
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
| D30 | Preserve existing providers, roles, legacy endpoints, history and deep links. | Accepted design |
| D31 | Existing access rules also apply to catalogue counts, metadata and retained artifacts. | Accepted design |
| D32 | Experimental outputs remain experimental; no automatic scientific publication or authority upgrades. | Accepted design |
| D33 | Contigs, unpublished inputs, external acquisition, R, GPUs and collaborative workspaces are excluded from v1. | Accepted boundary |
| D34 | Repository plan folder plus a dedicated Planning Hub chat; individual component prompts and resumable handoffs. | User selected |
| D35 | Preparation only now: create documentation/hub, no application implementation. | Latest user authorization |

## Changes

None. Record future changes with date, explicit user instruction, superseded
decision IDs, affected components and required acceptance changes.

## Adjustable defaults

D28/D29 are starting operational limits, not promised performance or scientifically
meaningful thresholds. A future component may propose a documented change after
measurements; do not silently increase resource access or scientific scope.
Routine internal details that do not change these decisions may be resolved
within a component and recorded in its handoff.
