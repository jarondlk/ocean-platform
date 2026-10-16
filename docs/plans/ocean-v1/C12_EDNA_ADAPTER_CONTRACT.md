# C12 frozen eDNA catalogue contract

`FrozenEDNACatalogueAdapter` exposes explicit C09 immutable bytes through C08
listing, open, distinct dataset counts and all six dataset inspection sections.
The caller supplies a store and `EDNAAccess(binding, revision, eligible)`.
The callback must return literal `True` for current whole-dataset permission and
scientific eligibility. Every request rereads verified snapshot bytes and current
policy. There is no live publication, SQL, retrieval, model or fixture fallback.

## Canonical inputs

`catalogue-edna-dataset-v1` metadata binds provider, locus, team, project,
source-qualified collection/dataset IDs and four independently qualified tables:
occurrences, classifications, assays and detections. Retained tables use fixed
primitive `catalogue-edna-parquet-v1` schemas. C09 metadata has role `canonical_rows`;
classification Parquet or explicit unavailable-state metadata supplies its mandatory
`classifications` role. Unavailable input never becomes a fabricated empty table.

`dataset_exports` freezes explicitly supplied canonical rows. The source exporter
registration requires an exact generation and deadline; it never discovers or
imports data. Missing and retained classification schemas cannot share one source
registration because C09 permits one schema version per role. Register compatible
source exports or retain explicit unavailable state until a supported registration
exists. C12 does not relax the C09 contract.

Validation checks primitive types/nullability, canonical row IDs, ownership, exact
object membership/hashes, one-to-one classifications, classification review lineage,
foreign keys, active flags, protocols, retained date precision, source availability,
resolved assignment versus raw taxonomy and concentration states. Scientific content
hashes are retained source assertions; C09 hashes bind the exact exported bytes.
Rows with missing classifications cannot be exposed as an eligible occurrence cohort.

Canonical source occurrences retain physical identity status. No provider/run/date
or sequence match creates a physical sample. Coarse dates retain their original
month/year labels; exact time predicates on coarse or unresolved dates return
qualified unavailability. Geography is inclusive; precise date/time semantics use
the shared UTC time contract.

Across a complete snapshot, all four tables together are bounded by 2,000,000 rows
and 512 MiB decoded Arrow bytes, as well as C09 object/manifest/capture limits.
Parquet footers are checked before decoding, remaining decoded budgets are passed
to each decoder, and actual decoded totals and global identity ownership are
validated before any dataset access callback. Expanding/dictionary encodings are
rejected. These are bounded local acceptance limits, not production throughput claims.

## Populations and operations

Operation IDs `c12.table`, `c12.count`, `c12.summary`, `c12.coverage` and
`c12.frequency` require version `c12-v1` and exactly one canonical dataset ID.
Parameters are strict: `population` (`eligible` default or `raw`), `table` (one of
the four plural role names, default occurrences), `filters`, optional `target_gene`,
`primer_set`, `sequencing_method`, `frequency_unit`, `limit` 1–500 and `offset`.
Only table operations permit a nonzero offset. Aggregate result rows can be
previewed with a limit, but totals and content hashes cover their complete output.

Raw means active canonical inventory, including controls and unknowns. All four
assignment methods are visible: qcauto target, 95pct/3nn target and their two
nontarget alternatives. C08 raw-inventory descriptors can honestly describe mixed
methods/classifications; scientific descriptors and C01 scopes retain their
existing two-target-method restrictions.

Eligible uses `preprocessing.edna_eligibility.evaluate_analysis_eligibility`:
environmental classification with `is_control=False`, an active assay with all
three protocol fields, and a supported target assignment method. Availability
comes from explicit source-backed method metadata or actual active retained
canonical detections. Missing JSON stays missing; actual detections can prove
their own method but cannot invent an available empty source table. A declared
available zero-row method remains eligible for a frequency denominator.

Filters use the same relational predicate plan as the canonical SQL service:
provider/locus/team/project/run, sample/assay, classification, method/status,
exact case-insensitive taxon across retained ranks, geography and UTC time.
Protocol restriction occurs before correlated assay/method selection. Nontarget
taxon matches cannot qualify target populations. Extra scalar filters cannot
override a shared pinned scope; numeric bounds may intersect to narrow it.
Unknown keys, contradictory ranges and unsupported operations fail explicitly.
Unsupported scientific methods carry `method_not_supported` qualification.

- **Table:** stable identity-sorted full selection, then paging. Occurrence rows
  include their retained classifications; classifications browse the same cohort.
- **Count:** distinct source occurrence and assay counts, explicit null physical
  sample count, controls/unknowns and method/protocol-separated detection counts,
  read sums and method availability. Alternative methods never form one read sum.
- **Summary:** one row per method and protocol, preserving measured zero,
  reported/missing/column-absent concentration and explicit units. Reads describe
  sequencing evidence; they are not organism abundance.
- **Coverage:** matching occurrence counts, retained date labels and precision,
  including unknown dates. Expected/missing sampling dates remain unknown without
  an explicit sampling calendar; no ecological absence is inferred.
- **Frequency:** requires eligible population, one explicit supported target method,
  exact taxon and all three explicit protocol fields. The unit is occurrences
  (default) or assays. Denominator applies every other filter with the taxon
  predicate removed and includes available empty methods. Numerator is distinct
  denominator units with matching retained `read_count > 0`. A zero denominator
  gives null frequency. This is observed detection frequency, not ecological absence.

Exact aggregates require complete relational inputs. Partial table/coverage results
retain unknown totals and partial completion. Missing inputs, unsupported precision
or numeric results beyond the exact C08 browser range return qualified unavailability;
they never return an invented exact zero or silently rounded integer.

## Identity, provenance and compatibility

The hierarchy is source → provider/locus/team → project → collection → dataset →
four tables. Statistics and Metadata references point to canonical dataset IDs;
they never create additional dataset membership. Global ID collision validation
also covers denied metadata, generated groups/references and export artifacts.
Inspection exposes overview, tables, coverage, methods, provenance and related links.

Every response names population and eligibility, operation/version, scope,
input hashes/generations, completeness and qualifications. Receipts hash the full
output before paging. Historical snapshots retain frozen classifications after
newer seals, while current permission and eligibility can revoke access to either.
Synthetic copies retain origins and independent destination policy.

The existing eDNA service only delegates SQL predicate construction to the shared
plan; its public endpoints and scientific definitions remain compatible. C08's
descriptor extension and the C09 workflow's new actual PostgreSQL parity cases are
intentional source supersessions recorded in the C12 receipt. Earlier receipts
remain immutable. C12 adds no service route, production mapping, scientific review,
data acquisition, publication, UI feature or deployment.

Rollback disables C12 adapter exposure and registrations. Preserve sealed exports,
classification lineage, origin records, receipts and current policy enforcement.
The handoff records executed validation and the separate source/delivery checkpoints.
