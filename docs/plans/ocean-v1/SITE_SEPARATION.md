# Separate OCEAN v1 site

Updated: 2026-10-13 JST. Accepted direction: a second site with fully isolated
infrastructure; explicitly copy approved data when needed. This document is a
plan, not authorization to provision, copy production data or deploy.

## Two independent systems

The existing production site keeps its current architecture, data and release
process. OCEAN v1 is developed on the overhaul branch and will have its own
deployment. Do not switch the existing site's default experience, redirect its
traffic or migrate its database as part of this plan. The repository records
the legacy origin as oceaninfobio.com; verify the actual origin before any future
hosting action. The new hostname has not been selected.

Use a separate GCP project as the planned resource boundary for v1. It may remain
under the same organization/billing administration, but receives independent
resource identities, budgets and deployment targets. A project is an isolation
layer; inherited organization/folder permissions still require review. Separate
project names alone do not prove isolation. [Google Cloud project model](https://docs.cloud.google.com/resource-manager/docs/creating-managing-projects).

| Boundary | V1 requirement |
|---|---|
| Serving | Independent frontend, API/controller and worker services, images, hostnames, configuration and release/rollback targets |
| Database | Separate database instance and credentials; application/corpus tables and migrations target v1 only |
| Storage | Separate buckets, snapshot/export namespaces, keys where applicable, lifecycle rules and backups |
| Identity | Separate service accounts, secrets, OAuth client/callback configuration and sessions; preserve intended role semantics without sharing legacy session secrets or cookies |
| Execution | Separate queues, outbox/leases, schedulers, worker fleet, quotas and experiment reservations |
| Delivery | Explicit v1 project/service targets and independent deployment configuration; no fallback to the legacy project, branch or service |
| Operations | Independent logs, alerts, retention/backup procedures, budget controls and capacity measurements |
| Network/access | V1 runtime identities have no access to legacy databases, buckets, secrets or queues; no live read-through or shared writable volume |

The same source repository and reviewed code can be reused. Runtime resources,
deployment state and mutable application/scientific data remain separate.
Changes to backend modules on overhaul do not authorize deploying them to the
legacy site or merging them to main. Do not reuse a legacy environment file.

## Local UI first

[P00](components/P00-local-ui-prototype.md) creates the future v1 frontend in a
separate frontend-v1 directory, leaving the existing frontend directory intact.
P00 implementation has now created that directory; its progress is in the handoff. Use localhost, synthetic fixtures and a
replaceable data/transport adapter. Do not call production APIs, load production
credentials, copy users, connect a database or make model calls during P00.

The fixture app becomes the basis for later integrated UI work. C08 reconciles
its provisional interaction/data contracts with scientific backend contracts.
C15/C16/C18/C25 integrate and validate it in stages; a prototype does not complete
those components. Keep fixture mode visibly identified and unavailable as a
silent production fallback. A missing real backend must yield an unavailable
state rather than a fabricated answer.

## Explicit approved-data transfer

Initially use synthetic data only. Future data transfer is a separately selected
operation with a concrete source, cohort, authority/eligibility decision and
destination. Published does not automatically mean independently scientifically
approved or unrestricted. Resolve the applicable scientific and access rules.

Plan a one-way export/import workflow:

1. Select approved/eligible source objects and define exclusions. Minimize the
   copied data. Legacy accounts, conversations, credentials and private history
   are excluded by default.
2. Produce a frozen transfer manifest containing origin identifiers, source
   snapshot/generation, schema and operation versions, content hashes, scientific
   qualifications, access conditions and transfer authorization reference.
3. Use an explicitly authorized transfer identity with narrowly scoped temporary
   access. It is not the v1 serving identity. Do not alter legacy publication
   heads, classifications or source records.
4. Import into a v1 quarantine/validation area, reconcile counts and hashes,
   verify schema/eligibility and then seal an independent v1 snapshot.
5. Retain provenance and a reproducible receipt; remove temporary transfer access
   when complete. Further updates are new explicit transfers, not automatic sync.

C09 owns transfer manifest/import contracts and local synthetic transfer checks;
C10–C13 own semantic/parity validation; C24 owns target identities/configuration;
C26/C27 own end-to-end evidence and the operator runbook. Actual export/import
and cloud access require separate authorization. A copied snapshot preserves
source provenance without depending on a live legacy service.

A withdrawal or permission change needs an operational process to suspend the
affected v1 copies and revalidate access. Independent copies cannot automatically
know that the source changed. Define the responsible operator, notifications and
expected response before real data transfer; do not imply continuous revocation
propagation when there is no synchronization service.

## Compatibility and rollback

Legacy compatibility means the existing site keeps its behavior and its own
history/deep links, while reused code retains appropriate local regressions.
It does not require v1 to share the legacy database or automatically import
accounts/history. Any legacy-history continuation in v1 is deferred until an
explicitly approved import/link design exists. Preserve API semantics where
useful, but do not build a hidden bridge to production.

V1 rollout, feature flags, rollback and worker drain affect v1 only. Rollback
preserves v1 investigations and evidence and restores a compatible v1 revision
or disables v1 capabilities. It never changes legacy routing or downgrades the
legacy database. Launch of the second site does not authorize a later cutover
of the main domain.

## Acceptance and unresolved operator inputs

C26/C27 must retain an isolation matrix showing that configuration, identities,
storage, database connections, queue targets, session/cookie scopes and CI/CD
targets cannot accidentally resolve to legacy resources. Exercise failed v1
startup/rollback without a production fallback. Local checks do not prove live
IAM/network isolation; record the live gate separately.

Later operator inputs: v1 project/region and budget, hostname, OAuth enrollment,
data-transfer scope/authority, backup/retention policy and withdrawal workflow.
Choose these before provisioning or real data import. None is needed to review
the synthetic local UI. No cloud resources or data copies have been created.
