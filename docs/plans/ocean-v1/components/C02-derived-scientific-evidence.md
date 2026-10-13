# C02 — Derived scientific evidence

**Status:** Not started. **Prerequisites:** C01. **Contract:** versioned derived-method eligibility.

## Objective and boundaries

Repair the three distinct scientific-processing findings before derived outputs enter the new catalogue. Correct execution does not establish scientific approval. Existing affected artifacts must remain identifiable and ineligible for scientific corroboration until regeneration and the established eligibility process succeed.

Included: F02 reliability decisions, F04 abundance missingness and F05 spatial corroboration, plus invalidation/provenance handling. Excluded: production regeneration, publication, independent scientific approval, new source acquisition and changes to reviewed thresholds without scientific justification. Regeneration during this component uses synthetic local fixtures only.

## Existing entry points

Verified sources: [reliability calculation](../../../../preprocessing/reliability_ensurance.py), [correlation calculation](../../../../preprocessing/pre_analysis.py), and [statistical context discovery](../../../../orchestration/statistics_catalog.py). Existing suites: `tests/test_reliability.py`, `tests/test_pre_analysis.py`, `tests/test_statistical_analysis.py`. Inspect normalized abundance loaders before replacing top-ten input; incomplete source data is an unavailable operation, not a zero-filled table.

## Interface decisions

Retain explicit per-check pass/fail/unavailable status, scientific applicability and input provenance. Availability of CTD and metagenome is not an independent passed check. A `verified` algorithmic tier must identify passed independent checks and must never be presented as independent scientific approval. Missing spatial support cannot qualify as SST corroboration. Bind outputs to input hashes and method versions; retain superseded evidence while marking its current eligibility.

## Resumable checkpoints and acceptance

1. **F02 — pass/fail:** base tiers on passed independent checks, retaining failures and unavailable checks explicitly. Acceptance: +8°C disagreement and +5σ anomaly cannot produce `verified`; presence of two modalities supplies no artificial passing check.
2. **F04 — omitted abundance:** use complete normalized abundance data and documented absence semantics. Acceptance: top-ten rank displacement of constant abundance creates neither false zeros nor a false correlation; missing measurements remain missing and method distinctions survive.
3. **F05 — spatial support:** validate coordinates against the SST product's reviewed spatial support before comparison. Acceptance: same-day CTD at 40.9°N does not receive corroboration from the 38–39°N regional series; unknown support is unavailable.
4. **Invalidation and regeneration:** add machine-readable version/eligibility handling and a local synthetic regeneration receipt. Acceptance: affected old artifacts cannot be selected as current validated evidence; retained history remains traceable. List real artifacts requiring later review without changing or republishing them.

Implementation validation: `python -m pytest tests/test_reliability.py tests/test_pre_analysis.py tests/test_statistical_analysis.py`. Extend those suites for each finding and propose `tests/test_derived_artifact_eligibility.py` for invalidation. Run the latter only after creating it. No fresh validation is claimed by this plan.

## Compatibility, rollback and handoff

Preserve old receipt interpretation and distinguish legacy method versions. Rollback must keep invalidated outputs ineligible. Record each finding's fix, synthetic regeneration hashes, validation results and outstanding real-data review in `handoffs/C02.md`; checkpoint `STATUS.md`. Completion concerns software and synthetic acceptance, not scientific approval or production regeneration.

## Exact prompts

**Planning-only**
> Review C02 without implementation. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C02-derived-scientific-evidence.md and handoffs/C01.md plus any C02 handoff. Inspect the checkout and prerequisite evidence. Report planning changes only; do not edit application code, regenerate real data or begin implementation without an explicit implementation request.

**Implementation**
> Implement only C02. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, this C02 specification and C01/C02 handoffs. Verify C01 and the checkout; preserve unrelated work. Complete bounded checkpoints, updating STATUS.md and handoffs/C02.md after each. Run required tests before completion. Only synthetic local regeneration is allowed. Do not fabricate scientific approval, start another component, publish, make cloud writes, provision, deploy or run paid model evaluation.

**Resume**
> Resume C02 only after reading the planning README, MASTER_PLAN, DECISIONS, STATUS, components/C02-derived-scientific-evidence.md and handoffs/C01.md and C02.md under docs/plans/ocean-v1. Reconcile the checkout and tests with the handoff, then finish the next checkpoint. Preserve unrelated work; update status/handoff and test before completion. Keep real-data regeneration pending. Do not publish, fabricate approval, start another component, make cloud writes, provision, deploy or run paid model evaluation.
