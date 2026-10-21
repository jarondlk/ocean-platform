# C22 — Experiment proposals and frozen exports

**Status:** In progress; all local gates reconciled on source66b4106, final exact-source hosted delivery pending. **Prerequisites:** C01, C07, C09, C17, C21.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

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

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c22). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
