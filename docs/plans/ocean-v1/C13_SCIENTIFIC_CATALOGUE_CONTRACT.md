# C13 frozen scientific catalogue

`FrozenScientificCatalogueAdapter(store, adapters, access)` exposes the five C08
roots over an explicit sealed scientific index and exact C10–C12 child snapshots.
Construction uses keyword arguments. No runtime configuration, registry database,
current publication pointer, provider, model or scientific file is discovered.

## Frozen ownership and access

`catalogue-scientific-registry-v1` binds each canonical dataset ID to its source
ID, source family and exact child snapshot hash. Published analyses, workflow
descriptions, metadata definitions, qualified relationships and retained C02
tombstones are immutable index records. Complete result tables use separate
`catalogue-scientific-table-v1` canonical JSON objects with declared columns,
units, row counts, availability and completeness. Results retain exact source
rows; they are never reconstructed from ten-row answer packets or option lists.

The index is an ordinary C09 snapshot with explicit `scientific_registry` and
`result_table` roles. Its dedicated source ID is `scientific:registry`. CTD is
only its storage carrier, as the registry's mandatory qualification states.
It contributes no CTD measurement, raw dataset, scientific source selection or
eligibility. Actual scientific membership comes exclusively from child bindings.
Existing strict C08/C09/C10/C11/C12 source contracts remain unchanged.

The source adapters supply current whole-dataset access/eligibility using their
existing policies. `ScientificAccess(binding, revision, eligible)` independently
requires literal `True` for an analysis, workflow, definition or relationship;
it does not revoke or grant raw dataset access. Policies receive detached models.
All declared inputs must remain permitted. Partial permission cannot substitute
a smaller input set for a finding or relationship. Every read verifies the index,
child bytes and current policies; no cached or live fallback exists.

Canonical dataset, source artifact, collection/product/directory, scientific
record and generated reference IDs are reserved before access filtering.
Source metadata validates even when its dataset or a colliding scientific record
would be denied. Repeated child snapshots are loaded once per request; mixed
CTD/metagenome Data hierarchies use their proper source scope.

Retirement or revocation of a child makes dependent work unavailable. C13 does
not create cross-snapshot retention holds or copy missing dependencies. C14's
service integration must register required child holds and import bindings.
An approved transfer must explicitly preserve or revalidate dependency/receipt
bindings; rewriting a dataset binding never silently approves old result bytes.

## Scientific membership and authority

- **Data** reuses the canonical source hierarchies and all six dataset inspection
  sections. IDs retain their source ownership; index envelopes name the bound
  child snapshot in inspection and receipts.
- **Analyses** includes eligible published findings and separate descriptive
  workflows. Unpublished/private experimental results do not join this global
  catalogue. Workflows have no execution capability. Publication is not scientific
  approval: both independent approval and provider endorsement are strictly false
  for the current operational-publication contract.
- **Statistics** links the same dataset IDs to C13-routable inventory, coverage,
  quality and explicitly selected source operations. Ad hoc scoped receipts never
  create global catalogue folders.
- **Metadata** retains descriptors, variables/units, protocols, temporal precision,
  sampling/completeness, quality policies, source operations/documentation,
  provenance/origins and publication history. Historical/ineligible C02 results
  stay qualified metadata rather than active published findings.
- **Relationships** separates verified physical identity, reviewed matching,
  environmental proximity and unresolved associations. Identity needs the exact
  retained applied registry and three-event review/application chain, occurrence
  and representative-assay scientific hashes, reviewed area and decision versions.
  Candidate or qualified context never establishes physical identity. Every
  category retains `comparison_authorized=False`.

C02 eligibility reuses its existing method allowlist, input/output/generation
hashes and bound review decision with explicitly supplied frozen tombstones.
The optional injection preserves legacy configured behavior for existing callers.
Affected unversioned, legacy, unavailable, invalidated, superseded, changed or
unreviewed artifacts remain ineligible. No real artifact was regenerated or
reviewed by C13. Seven existing deferred scientific files remain unchanged.

## Operations and complete counts

All C13 operations require `c13-v1`, one input identity and the current binding
and revision. Strict parameters are `table`, `limit` 1–500, `offset`,
`operation_id`, `operation_version`, `parameters`, `workflow_kind`, `protocol_id`.

`c13.table` selects an eligible analysis or its table ID. Multiple result tables
require an explicit name. Scope must exactly equal the retained published scope;
smaller cohorts cannot inherit fixed published findings. Retained C01 publication
options additionally require a registered workflow/protocol, its required frozen
source families, and the existing shared compatibility decision. That exact
field-level C01 receipt is retained. Rows and full content hashes are fixed before
paging. All published rows remain accessible beyond ten-row and 500-row previews.
Missing/partial tables preserve unknown totals and unavailable/partial completion.

`c13.inventory` and `dataset_count` deduplicate canonical dataset IDs across all
matching descendants and scientific links, independently of listing previews.
Every count names its entity and denominator. Object listing counts reference
objects; scientific inventory counts distinct input datasets, never link copies.

`c13.coverage` delegates to the registered source coverage operation.
`c13.quality` exposes SST status counts or eDNA raw control/method-availability
inventory, preserving their descriptive meaning. CTD/metagenome have no registered
quality operation and return qualified unavailability; retained quality metadata
remains inspectable. Neither missing support nor an unavailable operation is zero.

`c13.operation` requires an explicit native operation ID/version and native
`parameters`; C13 `limit`/`offset` govern paging. Native parameters cannot override
those bounds. The native adapter alone computes science, denominators, scope,
full output hash and completeness. C13 preserves those values and binds the index,
child snapshot and native receipt identity. Aggregate previews do not advertise
a continuation the source operation cannot execute. No new experiment executes.

Only selected dependencies enter a receipt: the index object, actual child hashes
and the selected published table. Denied finding IDs/table hashes and denied
workflow result links are not disclosed. Inspection exposes native operation
versions separately from C13's routable action descriptors.

## Bounds and recovery

The index is at most 4 MiB; each result JSON object at most 32 MiB. Strict JSON
rejects duplicate keys, nonfinite/unsafe browser numbers, mismatched columns,
duplicate result IDs, unknown object membership and changed hashes. Across the
index and unique child source objects, encoded bytes remain within C09's 512 MiB,
and total retained rows/decoded buffers are bounded by 2,000,000/512 MiB.
Footers validate before source decode; actual decoded size validates afterward.
These are bounded software checks, not a resident-memory/throughput certification.

Current authenticated service integration and finer access, dependency holds,
approved legacy mapping/transfer, real scientific review and cloud isolation
remain later gates. Rollback disables additive C13 exposure while preserving
sealed snapshots, eligibility/history, review provenance and receipts.
