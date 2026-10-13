# C24 — Dedicated GCP worker configuration

**Status:** Not started. **Prerequisites:** C20, C23.

## Objective and boundaries

Prepare reviewable infrastructure configuration for a dedicated Linux/gVisor experimental worker and its connection to durable research dispatch. Completion means configuration and local validation are ready for an operator; it does not mean any cloud resource exists or has passed live acceptance.

Include infrastructure code/templates, identity and storage access design, private dispatch, runtime configuration, failure recovery, observability and an operator runbook. Exclude provisioning, IAM changes, paid image/cloud builds, secret creation, remote installation, live dispatch and deployment. Existing project resources, budgets and historical approvals do not authorize these activities.

## Verified entry points and contracts

Inspect [GCP deployment guidance](../../../../deploy/gcp/README.md), [template renderer](../../../../scripts/render_gcp_templates.py), [template tests](../../../../tests/test_render_gcp_templates.py) and [deployment guide](../../../../docs/DEPLOYMENT.md). These describe established operator-controlled deployment conventions; old service manifests must not be replayed as current runtime truth.

Keep the C20 Cloud Run controller/Cloud Tasks boundary separate from the dedicated Linux worker. Use a trusted supervisor with minimal permissions to fetch approved job envelopes, stage designated inputs and retain validated outputs. Never forward its credentials, metadata access, database connectivity or network access into the C23 sandbox. Pin worker and scientific image identities; start with experiment dispatch disabled.

Configure enforcement of two CPUs, 4 GiB, ten minutes, 256 MiB inputs and 50 MiB outputs per sandbox, with one active job per user and two globally through C22 reservations. Host capacity must account for supervisor overhead and two simultaneous sandboxes; document the capacity requirement without claiming an unverified price or provisioning a machine. Specify private authenticated dispatch, lease recovery, health reporting, bounded logs and shutdown/drain behavior.

## Resumable checkpoints

1. Describe resource boundaries, supervisor/sandbox identities, storage paths, authenticated dispatch and required capacity using C20/C23 contracts. Record required operator inputs rather than inserting secrets.
2. Add infrastructure templates and local render/schema validation with synthetic project values. Ensure render and test paths cannot apply resources or invoke live APIs.
3. Prepare operator preflight, rollout, drain, failure-recovery and rollback instructions. Clearly separate dry checks from pending cloud/network/containment acceptance and required authorization.

## Future verification and acceptance

Existing local regressions: `python -m pytest tests/test_render_gcp_templates.py tests/test_security_config.py -q`. Add renderer/configuration assertions for the new worker and record the exact offline commands in the handoff. Inspect generated manifests for unresolved values, excessive permissions, writable host mounts, exposed dispatch and unpinned images.

Acceptance for this component is validated code/configuration plus an explicit live-validation checklist. Actual runtime containment must use C23's real Linux/gVisor gate; mocks and dry rendering cannot satisfy it. Unrun provisioning, live IAM, network isolation, restart recovery and concurrency checks remain pending. C25 may consume contracts with fixtures; experiments remain disabled until those gates pass under separate authorization.

## Compatibility, rollback and handoff

Keep current ingestion/publication jobs untouched. Document worker drain and dispatch-disable rollback without deleting approved inputs or results. Update [status](../STATUS.md) and `handoffs/C24.md` after each checkpoint with generated configuration, validation, operator inputs and pending live gates.

## Copy-and-paste prompts

**Planning only:** “Review only C24 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C24-gcp-worker-configuration.md, prerequisite handoffs C20/C23 and the checkout. Refine documentation only; preserve unrelated work.”

**Implementation:** “Implement only C24 infrastructure code and offline validation. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C24-gcp-worker-configuration.md and prerequisite handoffs C20/C23; reconcile the checkout. Follow checkpoints, update STATUS.md and handoffs/C24.md, and preserve unrelated work. No automatic advance, provisioning, IAM/secret changes, paid builds, live experiments or deployment.”

**Resume:** “Resume only C24 from docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C24-gcp-worker-configuration.md, handoffs/C24.md and prerequisite handoffs C20/C23. Reconcile checkout and evidence, continue the unfinished offline checkpoint and update status/handoff. Preserve unrelated work; no automatic advance, cloud changes, paid builds, live experiments or deployment.”
