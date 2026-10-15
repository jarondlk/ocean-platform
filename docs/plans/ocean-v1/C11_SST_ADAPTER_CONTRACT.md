# Frozen SST catalogue adapter

C11 provides local SST catalogue operations over explicit C09 immutable exports.
It preserves product/version/generation, actual spatial support and resolution,
units, quality and sampling semantics. No existing publication, normalization,
API or UI path is redirected to this adapter.

## Files and versions

- [Source models](../../../schema/sst_catalogue.py): `catalogue-sst-dataset-v1`
  metadata, `catalogue-sst-parquet-v1` observations and `c11-v1` operations.
- [Input verification and export registration](../../../ingestion/sst_catalogue_inputs.py).
- [Exact frozen adapter](../../../orchestration/frozen_sst_catalogue.py).
- [Synthetic fixtures](../../../schema/sst_catalogue_fixtures.py),
  [JSON Schema](../../../schema/sst_catalogue.v1.schema.json) and
  [portable logical examples](../../../schema/sst_catalogue_examples.json).
- [Generator](../../../scripts/export_sst_catalogue.py): run
  `.venv/bin/python scripts/export_sst_catalogue.py --check`. A backend contract
  test also checks generation in CI; the accepted C09 workflow is unchanged.

[C08](C08_CATALOGUE_CONTRACT.md) remains the shared transport/identity contract;
[C09](C09_SNAPSHOT_CONTRACT.md) owns storage, capture and independent-copy
semantics. C10's listing/open/dataset-count transport is reused through a subclass
whose loading, membership, node, inspection and scientific query hooks are all
SST-specific. No CTD/metagenome model is extended to accept SST rows.

## Source-owned immutable input

Each `SSTDataset` binds source, canonical product node, collection and dataset
identities; localized descriptions; the C08 SST descriptor; processing generation;
measurement type/statistic; calendar and actual time precision; geographic
support; aggregation, quality and uncertainty policies; methods and qualification.
The descriptor retains the actual delivery resolution and spatial role. Unknown
resolution must not be invented to satisfy a registration: such an input requires
a supported source definition before registration.

Products are grouped before collections and datasets under Data/SST. Canonical
product identity hashes source, product ID, exact version and processing
generation. Known MUR `04.1` and `04.1nrt` require final and interim generation,
respectively, and retain satellite/in-situ foundation-analysis meaning. They
cannot be relabelled direct satellite retrievals. Different products never share
one operation input. A final-product gap is not filled from an interim dataset.

`regional_daily_summary` and `grid_observation` are separate dataset entities.
Regional means cannot recreate underlying points or a narrower-area mean.
Retained MUR 0.05-degree grid-point subsampling remains that delivery resolution;
it does not become native-grid or station evidence. All metadata/artifact IDs
are checked together before any query or listing, including denied datasets;
shared collection IDs cannot acquire different product ownership.

One explicit observation-table descriptor has known row count when bytes are
retained. A complete empty table is zero; partial/unknown retained populations
and absent unknown/unavailable products keep those separate states. A metadata
inventory can expose a known dataset with unavailable observations.

Parquet columns are fixed: observation ID, retained time text, temperature value,
status, latitude/longitude, quality flag, uncertainty, valid fraction, valid/ocean
pixel counts, exact raw-source SHA-256 and exclusion reason. Nullable quality
measurements remain unknown when absent. Quality fields do not grant approval.
The valid fraction uses valid/ocean pixel counts when both are supplied;
float32 rounding is preserved within an explicit tolerance, without recomputing
the retained fraction. This is distinct from spatial weighting of temperature.
Invalid/excluded rows retain their reasons and remain inspectable in table pages.
Valid rows with missing values remain explicit missing measurements. Uncertainty
retains the descriptor's temperature interval unit; pixel counts name pixels.

`dataset_exports(metadata, frames, generation=...)` freezes caller-supplied
primitive values to plain-encoded canonical Parquet and C09 descriptors. It
does not discover current source paths or map legacy columns implicitly. Source
owners must explicitly preserve the source's UTC/JST/date basis and QC meaning.
In particular, the legacy regional `daily_rows` helper labels its UTC dates
`date_jst`; its field name does not authorize a calendar conversion.

`frozen_source_requirement(datasets, source_generation=...)` and the single
dataset helper register already frozen bytes. The callback checks its deadline
and exact current head; a changed head requires rebuilding the registration.
C09 still requires explicit registrations for all four families and controls
whole-family capture, generation locking, sealing and promotion. SST registration
alone does not enable the other families or advance latest.

Readers verify exact C09 bytes and current store policy before parsing. They
validate object membership/ownership, operation versions, fixed Arrow types and
nullability, finite primitive values, unique identities/cells, actual date
precision, source hashes and quality/support consistency. Unsupported dictionary
or prefix encodings fail before decoding. The local limits are 2,000,000 rows
and 512 MiB of footer/actual Arrow decoded bytes across all SST inputs in one
snapshot; C09's object/manifest/byte limits also apply. Over-budget inputs fail
explicitly. These are local input/decode bounds, not production throughput or
process-memory guarantees.

## Scope, access and inventory

Construct `FrozenSSTCatalogueAdapter(store=explicit_v1_store, access=SSTAccess(
binding, revision, eligible_callback))`. The callback receives the requested
snapshot ID and a detached metadata copy. Only literal `True` grants current
whole-dataset access and scientific eligibility. Metadata cannot self-approve.
Every operation rereads verified bytes and rechecks current policy; old snapshots
remain subject to revocation. Authenticated roles, row-level authorization and
service error sanitization belong to C14 and later integration.

Use C08 `ListingRequest`, `OperationRequest` and the validated shared
`EvidenceScope`, with only `remote_sensing` enabled. The snapshot itself must
contain whole-source exports. Other source families, unsupported source schemas,
scoped capture inputs, unknown operations or malformed parameters fail explicitly.
No embeddings, model, ranked search, current publication pointer or fixture data
is consulted as a fallback.

`list`, `open`, `dataset_count` and `inspect` expose stable canonical nodes and
all six dataset sections: Overview, Tables, Coverage, Methods, Provenance and
Related. Statistics and Metadata references target the same canonical dataset;
they do not add dataset inventory membership. Current denied links are omitted.
Counts and cursor context bind the complete permitted matching inventory, not
the displayed page. Dataset-ID selection preserves known empty metadata. A
scientific filter over incomplete data cannot prove absent dataset membership;
that scoped inventory operation fails explicitly when absence is unresolved.

Spatial filters require all four nonwrapping bounds. A requested region must fit
within retained support. Grid observations can be filtered to contained points;
a regional summary supports only its declared complete region. Wider requests
or attempts to recompute another region's mean are unavailable.

Shared temporal bounds compare actual UTC instants. Day-only source labels stay
day-only in their declared UTC/Asia-Tokyo calendar. For filtering, their whole-day
interval must be contained in the requested interval; partial overlap is
unavailable instead of inventing an hourly measurement. Offset-bearing instants
retain their original text and precision. A timestamp's calendar day for coverage
is derived only in the dataset's declared calendar.

## Operations and receipts

Each request uses version `c11-v1` and exactly one dataset ID. Parameters are only
`limit` (1–500, default 100) and `offset` (default zero). Aggregate offsets must
be zero. Unsupported parameters fail rather than being ignored.

| Operation | Complete-scope behavior |
|---|---|
| `c11.table` | Stable observation-ID pages of all matching retained rows, including quality exclusions and missing values |
| `c11.grid_points` | The same retained grid-point table; unavailable for regional-summary datasets |
| `c11.count` | Usable nonnull valid measurements with entity/denominator, invalid/excluded counts and valid missing-value count; requires complete inputs |
| `c11.summary` | Actual unit, observed/missing/zero counts and min/max/mean over usable values; requires complete inputs |
| `c11.coverage` | Distinct usable dates and observation count, plus expected/missing dates only when a daily sampling contract applies |

Expected daily sampling is an explicit inclusive bounded calendar for the
dataset's declared spatial support. It is never inferred from observed extent,
product name or retrieval rank. Leap days remain calendar days. Expected coverage
is unknown when the contract is absent, observations are incomplete, a spatial
subset is requested, time bounds cut calendar days, or the requested period
extends outside the contract. A complete in-contract empty date range can report
known zero observed days and actual expected gaps. Missing/invalid/excluded
measurements never become zero temperatures.

For grid data, an observed day means at least one usable retained point on that
date. It does not establish complete spatial grid-cell coverage. Expected grid
cell counts and finer spatial completeness are not inferred.

Receipts retain snapshot, validated scope, operation/version, exact metadata/table
hashes and generations, normalized parameters, qualifications and full-result
content hashes. Computation precedes pagination, so page size does not change
counts, means, coverage or content identity. Aggregate receipt `total_rows` counts
aggregate output rows; source observation counts remain explicitly named in the
row. Preview truncation, source completeness and query completion stay separate.
Inspection retains C09 copy origins without resolving or opening origin paths.

## Acceptance and recovery

Read [the handoff](handoffs/C11.md) and [verification receipt](evidence/C11/verification.json)
for final source bindings and acceptance results. Independent reference checks
cover populations beyond 500 rows, quality states, product isolation, calendars,
unsupported geography, exact synthetic legacy parity, old-snapshot replay,
current revocation, corruption and independent local-copy parity.

Rollback disables the additive SST registrations/adapter exposure while retaining
sealed bytes and receipts. Existing legacy workflows and publication heads stay
independent. Actual approved source mapping/copying, scientific regeneration or
publication, authenticated service/UI integration, C12 and GCP deployment require
their separately selected work.
