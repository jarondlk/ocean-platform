# C27 — Release preparation and rollback

**Status:** Not started. **Prerequisites:** C26.

## Objective and boundaries

Prepare a concrete OCEAN v1.0.0 release candidate and operator runbook with explicit acceptance, migration and rollback evidence. Completion means the package is ready for a separately authorized release decision, not that the system has been deployed or catalogue exploration has become the production default.

Include release documentation, feature-flag defaults, migration dry validation, disposable local migration/rollback rehearsals, operator checklists and recovery criteria. Exclude staging/production deployment, traffic changes, production migrations, acquiring/restoring production backups, publication/data changes, provisioning, IAM changes, release publication and paid/live evaluation. Creating this plan grants none of those actions.

## Verified entry points and contracts

Inspect [deployment guide](../../../../docs/DEPLOYMENT.md), [GCP operations guidance](../../../../deploy/gcp/README.md), [migration environment](../../../../migrations/env.py), [migration regression](../../../../tests/test_migration_configuration.py) and [prior release record](../../../../docs/RELEASE_0.7.6_OPERATIONS.md). Historical live identifiers and approvals are evidence for their dated releases only. A future operator must inspect current state before applying changes.

Release gates are C26's exact matrix and C24's live worker checklist, not a single aggregate test count. Keep independent catalogue, research and experiment flags. Promotion requires all applicable scientific, permission, UI and actual runtime gates; any pending gate stays visible. Retain legacy Chat routing and historical evidence links. Rollback disables new entry points/dispatch and restores compatible routing while preserving additive tables, investigations, receipts and experiment artifacts; do not assume database downgrade or data deletion is safe.

## Resumable checkpoints

1. Freeze the candidate code/reference identifiers and collect C26 evidence without making a Git commit/tag or claiming unfinished gates passed. Prepare the release manifest and compatible feature-flag combinations.
2. Inspect migrations and generate offline SQL with synthetic settings; rehearse upgrade and application-routing rollback on an explicitly disposable local database when available. Record preservation and compatibility results, not production backup claims.
3. Write operator preflight, separately authorized staging/live gates, rollout sequence, success/failure criteria and rollback/drain instructions. Identify which concrete actions need later authorization, and leave production unchanged.

## Future verification and acceptance

Existing local check: `python -m pytest tests/test_migration_configuration.py tests/test_render_gcp_templates.py -q`. The migration test demonstrates Alembic `sql=True` use; derive new dry-run commands from the actual candidate revisions and use synthetic configuration. Record exact generated SQL inputs and local rehearsal commands in the handoff; never invent current schema IDs.

Acceptance requires a requirement-to-evidence manifest, migration review, legacy compatibility, retained-history verification, feature-flag rollback and worker drain/recovery instructions. Rehearse partial migration/dispatch failure and cancelled in-flight runs locally where feasible. Live backup acquisition/restore, network/identity validation, live model comparison and traffic promotion remain explicitly pending until separately authorized. The runbook must prevent an operator from treating dry validation as proof of production readiness.

## Compatibility, rollback and handoff

Prefer additive forward-compatible schema changes and preserved artifacts over destructive downgrades. Document the compatible old application version from actual verification, not assumption. Update [status](../STATUS.md) and `handoffs/C27.md` after each checkpoint with candidate identity, runbook links, passed/pending gates, rollback evidence and the next authorized decision. No later component starts automatically.

## Copy-and-paste prompts

**Planning only:** “Review only C27 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C27-release-readiness.md, prerequisite handoff C26 and the checkout. Refine release planning only; preserve unrelated work.”

**Implementation:** “Implement only C27 release-preparation documents and local dry validation. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C27-release-readiness.md and prerequisite handoff C26; reconcile the checkout. Follow checkpoints and update STATUS.md and handoffs/C27.md. Preserve unrelated work. No automatic advance, commits/tags, real backup acquisition, production migrations, provisioning, deployment, publication or paid/live evaluation.”

**Resume:** “Resume only C27 from docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C27-release-readiness.md, handoffs/C27.md and prerequisite handoff C26. Reconcile code/evidence, continue the unfinished preparation checkpoint and update status/handoff. Preserve unrelated work; no automatic advance, commits/tags, real backups, production migrations, cloud changes, deployment, publication or paid/live evaluation.”
