# C02 — Derived scientific evidence

**Status:** Complete for local software and synthetic acceptance. **Prerequisites:** C01. **Contract:** versioned derived-method eligibility.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

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

Implementation validation: `python -m pytest tests/test_reliability.py tests/test_pre_analysis.py tests/test_statistical_analysis.py`.
The invalidation suite `tests/test_derived_artifact_eligibility.py` now exists and
passes. Exact commands, source hashes, synthetic regeneration and compatibility
results are recorded in [the handoff](../handoffs/C02.md) and
[verification receipt](../evidence/C02/verification.json). This is local software
acceptance, not scientific approval or permission to regenerate real artifacts.

## Compatibility, rollback and handoff

Preserve old receipt interpretation and distinguish legacy method versions. Rollback must keep invalidated outputs ineligible. Record each finding's fix, synthetic regeneration hashes, validation results and outstanding real-data review in `handoffs/C02.md`; checkpoint `STATUS.md`. Completion concerns software and synthetic acceptance, not scientific approval or production regeneration.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c02). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
