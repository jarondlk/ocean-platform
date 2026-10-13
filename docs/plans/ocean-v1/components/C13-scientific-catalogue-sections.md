# C13 — Scientific catalogue sections

Status: **Not started**. Prerequisites: **C01, C02, C10, C11, C12**.

## Objective and boundaries

Populate Analyses, Statistics, Metadata and Relationships alongside the Data hierarchy, creating one coherent scientific map. The agent and researcher should understand available findings, descriptive operations, scientific definitions and qualified connections before selecting evidence.

Include existing published results, available workflow descriptions, full-scope inventory statistics, sampling/quality metadata, provenance and qualified relationships. Exclude executing new experiments, promoting unpublished results, new ingestion, changing scientific approvals and browser implementation. Private experimental results belong to investigations, not global Analyses.

Verified entry points: [statistics catalogue](../../../../orchestration/statistics_catalog.py), [published results](../../../../orchestration/published_results.py), [research registry](../../../../api/research_registry_service.py), [eDNA environment linking](../../../../retrieval/edna_environment_linker.py), and [immutable bundles](../../../../ingestion/immutable_bundle.py). Existing bounded option lists are inputs to replace or adapt, not a completeness guarantee.

## Interfaces and decisions

Use the shared C08 node and listing contracts. Analyses distinguishes published findings from descriptions of available workflows. Each result exposes its frozen inputs, method, complete result tables, scope and actual authority. Publication status does not imply independent scientific approval.

Statistics exposes named operations and snapshot-bound summaries. Every count declares its entity and denominator. Directory totals deduplicate canonical identities across links and aggregate the full permitted descendant set; previews never substitute for underlying totals. Ad hoc scoped receipts remain investigation evidence instead of spawning unlimited global folders.

Metadata links variables, units, temporal precision, sampling, assays, methods, source documentation and publication manifests. Relationships distinguish verified physical identity, reviewed matching, proximity and unresolved associations. Candidate matches cannot silently authorize scientific comparison. Shared objects keep stable IDs wherever linked.

## Resumable checkpoints

1. **Register scientific objects.** Map published analyses, workflows, definitions and relationship registries into the four roots. Acceptance: all eligible fixture objects are reachable, linked to input datasets, and qualified by source and authority.
2. **Implement summaries and operations.** Calculate inventory/coverage/quality results through source adapters. Acceptance: descendant counts reconcile without double-counting, full tables remain accessible beyond previews, and unknown/missing/zero outcomes stay distinct.
3. **Validate cross-root semantics.** Acceptance: linking one dataset into multiple sections preserves identity and counts; incompatible analysis scopes are rejected; unavailable workflows and experimental relationships cannot appear as published results.

## Validation, compatibility and handoff

Existing regression command: `python -m pytest tests/test_research_registry.py tests/test_research_chat.py tests/test_edna_environment.py tests/test_regional_publication.py`. Planned new tests cover all root memberships, authority labels, summary reconciliation and published-table pagination. No execution evidence is implied by this plan.

Maintain existing registry, published-result and statistics consumers during migration. Rollback removes new catalogue exposure while retaining canonical objects and historical receipts. Record root mappings, workflow eligibility, relationship semantics and validation results in `handoffs/C13.md`; update `STATUS.md` at each checkpoint.

## Copy-and-paste prompts

**Planning-only**

> Review C13 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification and C01/C02/C10/C11/C12 handoffs. Reconcile them with the actual checkout. Refine the plan; do not implement application changes.

**Implementation**

> Implement explicitly requested component C13 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification and C01/C02/C10/C11/C12 handoffs; verify prerequisites in the actual checkout. Complete its checkpoints and checks, preserving unrelated changes. Update STATUS.md and handoffs/C13.md throughout. Do not start another component, make cloud writes or paid calls, or publish production data.

**Resume**

> Resume C13 only. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this specification, prerequisite handoffs and handoffs/C13.md. Reconcile recorded progress with the actual checkout and evidence. Continue the first unfinished checkpoint; update STATUS.md and handoffs/C13.md. Do not repeat completed work, start another component, make cloud writes or paid calls, or publish production data.
