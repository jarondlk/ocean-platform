# C10 — CTD and metagenome adapters

**Status:** Complete for local frozen-adapter acceptance (2026-10-15 JST). **Prerequisites:** C02, C09.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Expose CTD and metagenome collections through frozen-data catalogue adapters. Researchers and the agent must discover every eligible dataset and run supported operations over complete matching records, independently of document ranking.

Include dataset registration, schema descriptions, coverage, table pages, counts and descriptive summaries using PyArrow/Pandas snapshots. Exclude new acquisition, contig ingestion, cross-source causal inference, UI construction and publication changes.

Verified entry points: [CTD preprocessing](../../../../preprocessing/ctd.py), [metagenome preprocessing](../../../../preprocessing/metagenome.py), [overview coverage](../../../../api/overview_coverage.py), and [corpus models](../../../../db/models.py). These define current normalization and counting semantics; inspect C02 corrections before reusing derived results.

## Interfaces and decisions

Implement the C09 adapter contract using C08 node identities. Dataset nodes expose Overview, Tables, Coverage, Methods, Provenance and Related sections. Return snapshot and operation versions, explicit units and counting entities with each observation.

For CTD, distinguish casts from depth measurements and preserve campaign sampling. Do not infer missing expected casts without a sampling contract. For metagenome, preserve collection dates at their actual precision, sequencing/QC distinctions, assignment methods and normalized abundance tables. A taxon absent from a top-ten summary is unknown from that summary, not a demonstrated zero. Expose unavailable operations explicitly when full normalized inputs are absent. Contig-level capabilities remain unavailable.

Record pages have bounded previews; count and summary operations process the entire validated scope. Cross-links reuse canonical identities and never increase inventory totals. Do not invent unified physical samples from shared labels alone.

## Resumable checkpoints

1. **Register inputs and semantics.** Map frozen artifacts to collection/dataset/table nodes. Acceptance: every eligible fixture dataset has stable identity, units, temporal precision and source provenance; incomplete inputs are visibly qualified.
2. **Implement exact operations.** Apply shared eligibility and scope filters before pagination. Acceptance: counts and summaries match independent reference calculations, including more than 500 matching records and taxa omitted from ranked summaries.
3. **Verify reproducibility and integration.** Acceptance: reopening a snapshot after an input update reproduces original results; malformed scopes fail explicitly; the adapter supplies all catalogue sections without requiring embeddings.

## Validation, compatibility and handoff

Existing regression command: `python -m pytest tests/test_ctd.py tests/test_metagenome_loaders.py tests/test_overview_coverage.py`. New checks, to be created during implementation, cover frozen adapters, counting entities, unavailable tables and page-independent aggregates. The readiness baseline and prerequisite checks are recorded below; C10 implementation acceptance remains pending.

Keep legacy normalized artifacts and routes readable. Rollback disables these catalogue registrations while retaining sealed snapshots and receipts. Record supported operations, fixture identities, parity results and limitations in `handoffs/C10.md`; update `STATUS.md` at each checkpoint.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c10). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Readiness checkpoint — 2026-10-15 JST

Ready for explicit selection at `ae02e89`: C02/C09 source evidence reconciles,
36 baseline and 534 prerequisite regressions pass, and all five generated
contracts are current. C09 exact-source hosted CI passes, including 21 snapshot
PostgreSQL cases. [Audit](../C10_READINESS_AUDIT_2026-10-15.md) and
[receipt](../evidence/c10-readiness-2026-10-15/verification.json) identify frozen
inputs, units/denominators, temporal precision and complete-scope acceptance work.
C10 remains Not started; no adapters, real transfers or services are selected.

## Accepted local implementation — 2026-10-15 JST

All three checkpoints pass: versioned source metadata/Parquet exports, C08
canonical inventory and six sections, complete-scope operations, current access
and reproducible old/imported snapshots. Required suites pass 680 cases, including
110 new adapter cases; full backend passes 2,579/84 expected PostgreSQL skips at
82.90% coverage. Six generated-contract checks and Ruff pass. No existing C08/C09
source/workflow, normalized producer, UI or real scientific/serving artifact changed.
[Handoff](../handoffs/C10.md), [contract](../C10_ADAPTER_CONTRACT.md) and
[local receipt](../evidence/C10/verification.json) record exact sources, semantic
bounds and later real-data/service/deployment gates. C11 remains unselected.
