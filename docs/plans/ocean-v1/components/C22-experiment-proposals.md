# C22 — Experiment proposals and frozen exports

**Status:** Not started. **Prerequisites:** C01, C07, C09, C17, C21.

## Objective and boundaries

Prepare a concrete, reviewable analysis before any generated Python executes. Researchers and admins may approve their own proposed experiments using data already eligible for their access. Approval permits execution; it does not validate scientific conclusions.

Include proposal persistence, frozen cohort exports, scientific scope/relationship qualifications, approval binding and dispatch eligibility. Exclude executing code, network data acquisition, unpublished inputs, R, GPUs and promotion into published analyses. C23 implements execution; C25 supplies the user interface.

## Verified entry points and contracts

Inspect [research recipes](../../../../preprocessing/research_recipe.py), [analysis bundles](../../../../ingestion/research_analysis_bundle.py), [registry service](../../../../api/research_registry_service.py), [auth permissions](../../../../api/auth.py) and [chat hashing conventions](../../../../api/chat_records.py). Existing publication workflows are reference contracts, not a route for private experiments to publish automatically.

Expose proposal/review/approval under `/research/experiments/*`. Each proposal includes the question, frozen snapshot/cohort, exclusions, pairing rules, method, assumptions, generated Python, expected outputs, environment identity, limitations and resource estimate. Bind approval to canonical proposal, code and input-manifest hashes. Any change invalidates approval and creates a new reviewable revision. Recheck current permission and dataset eligibility at approval and dispatch.

Export only required columns/rows from C09 artifacts using shared C01 scientific filtering. Record units, counting entities, relationships and source hashes. Limit inputs to 256 MiB and outputs to 50 MiB; execution defaults are two CPUs, 4 GiB memory and ten minutes. Oversized inputs require a narrower proposal, never silent sampling. Permit one active experiment per user and two globally; enforce reservations transactionally at dispatch, not just in the UI.

## Resumable checkpoints

1. Add proposal/revision/approval records and owner-scoped APIs. Define canonical hash inputs and explicit stale-approval responses.
2. Build deterministic frozen exports with count/hash validation, provenance manifests, scientific exclusions and preflight size checks.
3. Implement approval and dispatch-eligibility checks using a fake executor; provide C23 the immutable execution envelope without running it.

## Future verification and acceptance

Existing regressions: `python -m pytest tests/test_research_analysis_bundle.py tests/test_research_registry.py tests/test_auth.py -q`. Add focused proposal/export/approval tests during implementation and record commands in the handoff.

Acceptance covers mismatched code/input hashes, tampered artifacts, changed scope after approval, revocation, cross-user approval attempts, export-size rejection, transactional concurrent reservations, deterministic exports, invalid pairing rules and scientifically ambiguous cohorts. Verify no proposal endpoint executes code or publishes results. Fixtures and fake execution are sufficient for this component; no live data export or paid evaluation is authorized by its prompt.

## Compatibility, rollback and handoff

Use additive private records; preserve current published recipes and registries. Disabling experiments prevents new dispatch without deleting proposals, approvals or frozen artifacts. Update [status](../STATUS.md) and `handoffs/C22.md` after each checkpoint with hash contract, eligibility rules, reservation behavior and checks.

## Copy-and-paste prompts

**Planning only:** “Review only C22 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C22-experiment-proposals.md, prerequisite handoffs C01/C07/C09/C17/C21 and the current checkout. Refine documentation only; preserve unrelated work.”

**Implementation:** “Implement only C22. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C22-experiment-proposals.md and prerequisite handoffs C01/C07/C09/C17/C21; reconcile the checkout. Follow checkpoints, verify locally with synthetic inputs/fake execution, and update STATUS.md and handoffs/C22.md throughout. Preserve unrelated work; no automatic advance, real experiments, cloud provisioning, deployment or paid/live evaluations.”

**Resume:** “Resume only C22 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C22-experiment-proposals.md, handoffs/C22.md and prerequisite handoffs C01/C07/C09/C17/C21. Reconcile code/evidence and continue the next unfinished checkpoint; update status/handoff. Preserve unrelated work; no automatic advance, real experiments, provisioning, deployment or paid/live evaluations.”
