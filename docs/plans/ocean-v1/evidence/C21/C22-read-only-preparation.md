# Conditional C22 preparation

This records read-only preparation while C21 source0ab726a hosted acceptance is
pending. C22 is not selected and no prerequisite readiness verdict or application
implementation is claimed. Two existing delegates inspected the actual contracts;
no sources or services changed during their preparation.

C22's formal prerequisites are C01/C07/C09/C17/C21. Audit their delivered/current
source and receipt chains only after C21's delivery metadata checkpoint is pushed.

## Publication policy is a separate gate

C09 `promote()` verifies current bytes/access and changes a pointer under CAS.
Its audit records revision/action/snapshot, without an approver or eligible cohort
decision. Consistent capture generations likewise do not establish approval.
C13 raw `DatasetBinding` lacks a publication-approval field, and raw catalogue
nodes retain `publication=unpublished`. Neither sealing nor query readiness may
silently establish C22's published-only input eligibility.

The conservative implementation boundary is an explicit trusted host publication
policy witness over exact source/dataset/child-snapshot/publication-generation/
object hashes, with a policy version and retained decision reference. Missing,
withdrawn or mismatched policy must deny export/approval/dispatch. The public
proposal request cannot supply this authority. Synthetic test policy receipts
must be explicitly configured and cannot become real-world approval evidence.
Published scientific analysis eligibility separately requires C13 publication,
availability/C02 and C01 exact-question compatibility. This establishes neither
independent scientific verification nor a new scientific approval.

## Frozen scientific export boundary

Use the verified C13 context/data/bindings/requests and the actual frozen C10
`_scoped`, C11 `_select`, and C12 `_select`/`edna_catalogue_query` predicates.
C01 `publication_compatibility` validates existing published workflows; it is
not a generic row filter. C21 observation previews and retained operation pages
are provenance, not complete experiment cohorts. Avoid the legacy/global database
discovery in `research_analysis_bundle.read_snapshot`.

Define a strict cohort selector and immutable export manifest binding exact
context/scope, datasets/tables/columns, canonical row order/counts/file hashes,
units/entities/denominators, exclusions, relationship proofs and selector version.
Preserve casts versus depth observations, metagenome libraries versus summaries,
SST summaries versus grid observations, and eDNA occurrences/assays/physical
samples. Keep date precision, classification, protocol/method/rank, missing values,
support/calendar constraints and source completeness. Proximity/shared labels
cannot establish physical pairing; unsupported or ambiguous cohorts must remain
unresolved or be explicitly rejected/excluded.

Version a lossless canonical machine encoding. C07 spreadsheet-safe CSV can alter
formula-like strings and must remain a separately hashed human presentation.
Count every input/sidecar byte against256MiB; reject oversized cohorts without
sampling. Presentation page limits are not export cohort limits.

## Additive persistence and execution handoff

Use a proposal head plus immutable revisions; exact Python UTF-8/code and proposal
hashes; frozen export/protection records; immutable owner approvals; operation/
events; a fixed global capacity row, reservations and stable outbox/envelope.
Bind approval to proposal/code/input/environment/resource hashes. New revisions
retain old approval history but invalidate its dispatch authority. Recheck fresh
owner, policy/source eligibility and exact hashes at approval and dispatch.

Reserve one active experiment per user and two globally transactionally, with
reservation/outbox in the same commit. A retry cannot create a fresh reservation;
uncertain delivery or lease expiry cannot release capacity without proof execution
stopped. Extend C17 application/native retirement protection to prepared exports,
proposal records and transitive dependencies before independent artifact writes.
Lost acknowledgements keep protection.

C22 can use an explicitly injected fake executor for its immutable C23 handoff
acceptance. It executes no code and cannot provision/deploy cloud services. Real
execution/environment identity remains gated by C23 containment and C24 concrete
configuration. Resource defaults:2CPU/4GiB/10min; output50MiB. Do not invent an image
digest, publication review or execution approval to fill a missing configuration.
