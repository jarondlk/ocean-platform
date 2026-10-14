# C27 — Release preparation and rollback

**Status:** Not started. **Prerequisites:** C26.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Prepare a concrete OCEAN v1.0.0 release candidate and operator runbook with explicit acceptance, migration and rollback evidence. Completion means the package is ready for a separately authorized release decision, not that the second site has been deployed or the legacy production default has changed.

Include release documentation, feature-flag defaults, migration dry validation, disposable local migration/rollback rehearsals, operator checklists and recovery criteria. Exclude staging/production deployment, traffic changes, production migrations, acquiring/restoring production backups, publication/data changes, provisioning, IAM changes, release publication and paid/live evaluation. Creating this plan grants none of those actions.

## Verified entry points and contracts

Inspect [deployment guide](../../../../docs/DEPLOYMENT.md), [GCP operations guidance](../../../../deploy/gcp/README.md), [migration environment](../../../../migrations/env.py), [migration regression](../../../../tests/test_migration_configuration.py) and [prior release record](../../../../docs/RELEASE_0.7.6_OPERATIONS.md). Historical live identifiers and approvals are evidence for their dated releases only. A future operator must inspect current state before applying changes.

Release gates are C26's exact matrix and C24's live worker checklist, not a single aggregate test count. Keep independent catalogue, research and experiment flags. Promotion requires all applicable scientific, permission, UI and actual runtime gates; any pending gate stays visible. Legacy Chat routing and historical links remain on the unchanged legacy site. V1 rollback disables v1 entry points/dispatch or restores a compatible v1 revision while preserving its tables, investigations, receipts and experiment artifacts. Do not switch main-domain traffic or touch legacy data as a rollback strategy.

## Independent launch and data-transfer gates

The release manifest identifies only v1 project/services, hostname, identities,
database/storage/queues, CI/CD targets and compatible revisions. Require C26's
isolation matrix and separate live IAM/network/session/backup gates before launch.
No main-domain cutover is included. Rehearse rollback on disposable v1 resources.

Prepare an approved-data transfer runbook with eligibility/authority checks,
source/hash manifest, temporary transfer identity, quarantine/import validation,
origin provenance and withdrawal response. Synthetic rehearsal is local; real
exports/copies and access grants require later explicit authorization. Accounts,
private legacy history and credentials are not copied by default.

## Resumable checkpoints

1. Freeze the candidate code/reference identifiers and collect C26 evidence without making a Git commit/tag or claiming unfinished gates passed. Prepare the release manifest and compatible feature-flag combinations.
2. Inspect migrations and generate offline SQL with synthetic settings; rehearse upgrade and application-routing rollback on an explicitly disposable local database when available. Record preservation and compatibility results, not production backup claims.
3. Write operator preflight, separately authorized staging/live gates, rollout sequence, success/failure criteria and rollback/drain instructions. Identify which concrete actions need later authorization, and leave production unchanged.

## Future verification and acceptance

Existing local check: `python -m pytest tests/test_migration_configuration.py tests/test_render_gcp_templates.py -q`. The migration test demonstrates Alembic `sql=True` use; derive new dry-run commands from the actual candidate revisions and use synthetic configuration. Record exact generated SQL inputs and local rehearsal commands in the handoff; never invent current schema IDs.

Acceptance requires a requirement-to-evidence manifest, migration review, legacy compatibility, retained-history verification, feature-flag rollback and worker drain/recovery instructions. Rehearse partial migration/dispatch failure and cancelled in-flight runs locally where feasible. Live backup acquisition/restore, network/identity validation, live model comparison and traffic promotion remain explicitly pending until separately authorized. The runbook must prevent an operator from treating dry validation as proof of production readiness.

## Compatibility, rollback and handoff

Prefer additive forward-compatible schema changes and preserved artifacts over destructive downgrades. Document the compatible previous v1 application version from actual verification; an initial launch may instead require disabling v1 until repaired. Do not assume the legacy application can read the v1 database. Update [status](../STATUS.md) and `handoffs/C27.md` after each checkpoint with candidate identity, runbook links, passed/pending gates, rollback evidence and the next authorized decision. No later component starts automatically.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c27). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
