# C10 — CTD and metagenome adapters

Status: **Not started**. Prerequisites: **C02, C09**.

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

Existing regression command: `python -m pytest tests/test_ctd.py tests/test_metagenome_loaders.py tests/test_overview_coverage.py`. New checks, to be created during implementation, cover frozen adapters, counting entities, unavailable tables and page-independent aggregates. No checks have been run for this planning document.

Keep legacy normalized artifacts and routes readable. Rollback disables these catalogue registrations while retaining sealed snapshots and receipts. Record supported operations, fixture identities, parity results and limitations in `handoffs/C10.md`; update `STATUS.md` at each checkpoint.

## Copy-and-paste prompts

**Planning-only**

> Review C10 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this component specification and C02/C09 handoffs. Reconcile them with the actual checkout. Refine the plan and identify gaps; do not implement application changes.

**Implementation**

> Implement explicitly requested component C10 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification and C02/C09 handoffs; verify prerequisites in the actual checkout. Follow its checkpoints and checks. Preserve unrelated changes. Update STATUS.md and handoffs/C10.md throughout. Do not start another component, make cloud writes or paid calls, or publish production data.

**Resume**

> Resume C10 only. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this specification, prerequisite handoffs and handoffs/C10.md. Reconcile checkpoint claims with the actual checkout and evidence. Continue the first unfinished checkpoint and update STATUS.md and handoffs/C10.md. Do not repeat completed work, start another component, make cloud writes or paid calls, or publish production data.
