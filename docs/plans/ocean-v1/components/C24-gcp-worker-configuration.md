# C24 — Isolated GCP site and worker configuration

**Status:** Not started. **Prerequisites:** C20, C23.

Development preparation completed 2026-10-28 JST: C20/C23 accepted receipts and
current source reconcile. The user proposed `https://beta.oceaninfobio.com` as
the working v1 origin. [Readiness and implementation plan](../C24_READINESS_AUDIT_2026-10-28.md)
records its independent session/origin boundary, checkpoints and pending live
inputs. No application implementation, DNS change or beta deployment has begun.
[Preparation handoff](../handoffs/C24.md).

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Prepare reviewable infrastructure configuration for the fully isolated second v1 site, including frontend/API/controller, data stores, identity, queues and a dedicated Linux/gVisor experimental worker. Completion means configuration and local validation are ready for an operator; it does not mean any cloud resource exists or has passed live acceptance.

Include independent v1 infrastructure code/templates, database/bucket boundaries, identity/OAuth/session separation, queues, serving/worker targets, private dispatch, runtime configuration, failure recovery, observability and an operator runbook. Exclude provisioning, IAM changes, paid image/cloud builds, secret creation, remote installation, live dispatch and deployment. Existing project resources, budgets and historical approvals do not authorize these activities.

## Verified entry points and contracts

Inspect [GCP deployment guidance](../../../../deploy/gcp/README.md), [template renderer](../../../../scripts/render_gcp_templates.py), [template tests](../../../../tests/test_render_gcp_templates.py) and [deployment guide](../../../../docs/DEPLOYMENT.md). These describe established operator-controlled deployment conventions; old service manifests must not be replayed as current runtime truth.

Keep the C20 Cloud Run controller/Cloud Tasks boundary separate from the dedicated Linux worker. Use a trusted supervisor with minimal permissions to fetch approved job envelopes, stage designated inputs and retain validated outputs. Never forward its credentials, metadata access, database connectivity or network access into the C23 sandbox. Pin worker and scientific image identities; start with experiment dispatch disabled.

Configure enforcement of two CPUs, 4 GiB, ten minutes, 256 MiB inputs and 50 MiB outputs per sandbox, with one active job per user and two globally through C22 reservations. Host capacity must account for supervisor overhead and two simultaneous sandboxes; document the capacity requirement without claiming an unverified price or provisioning a machine. Specify private authenticated dispatch, lease recovery, health reporting, bounded logs and shutdown/drain behavior.

## Whole-site isolation configuration

Prepare templates in a distinct deploy/gcp-v1 area, with explicit v1 project,
service, storage, database, OAuth/cookie, secret and queue targets. Never inherit
legacy environment files or insert legacy resource identifiers as defaults.
Document separate capacity, budget, backup/retention, deployment and rollback
inputs. A missing v1 target fails closed. No v1 runtime identity receives legacy
resource access; a later approved transfer uses a separate temporary identity.

Bind the proposed beta hostname explicitly. Use independent OAuth credentials,
host-only v1 sessions, exact-origin/CSRF checks and no parent-domain cookie or
wildcard CORS scope. The static frontend preview and fake C20 queue are not a
production host or Cloud Tasks adapter; preserve those runtime integration gates
in configuration/runbooks rather than implying templates implement them.

Offline acceptance must reject legacy targets and accidental shared sessions or
mutable stores, and identify inherited IAM review and real network checks still
pending. No templates are applied here. The older deployment references are
patterns to inspect, not infrastructure to update or replay.

## Resumable checkpoints

1. Describe the separate v1 site/project, database, buckets, identities/sessions, queues, frontend/API/controller and worker boundaries using SITE_SEPARATION and C20/C23 contracts. Record capacity/budget/operator inputs rather than secrets or legacy defaults.
2. Add infrastructure templates and local render/schema validation with synthetic project values. Ensure render and test paths cannot apply resources or invoke live APIs.
3. Prepare operator preflight, rollout, drain, failure-recovery and rollback instructions. Clearly separate dry checks from pending cloud/network/containment acceptance and required authorization.

## Future verification and acceptance

Existing local regressions: `python -m pytest tests/test_render_gcp_templates.py tests/test_security_config.py -q`. Add renderer/configuration assertions for the new worker and record the exact offline commands in the handoff. Inspect generated manifests for unresolved values, excessive permissions, writable host mounts, exposed dispatch and unpinned images.

Acceptance for this component is validated code/configuration plus an explicit live-validation checklist. Actual runtime containment must use C23's real Linux/gVisor gate; mocks and dry rendering cannot satisfy it. Unrun provisioning, live IAM, network isolation, restart recovery and concurrency checks remain pending. C25 may consume contracts with fixtures; experiments remain disabled until those gates pass under separate authorization.

## Compatibility, rollback and handoff

Keep current ingestion/publication jobs untouched. Document worker drain and dispatch-disable rollback without deleting approved inputs or results. Update [status](../STATUS.md) and `handoffs/C24.md` after each checkpoint with generated configuration, validation, operator inputs and pending live gates.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c24). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
