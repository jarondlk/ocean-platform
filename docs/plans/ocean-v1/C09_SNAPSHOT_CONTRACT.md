# Catalogue snapshot v1 contract

C09 adds immutable catalogue export storage for the independent v1 system. It
captures exact bytes and the versions needed to interpret them. It does not
implement scientific query adapters, authenticated APIs, real publication,
approved-data transfer, cloud storage or deployment. The existing site's stores
and publication pointers are unchanged.

## Authoritative files

- [Snapshot models](../../../schema/catalogue_snapshot.py) define
  `catalogue-snapshot-v1`, object bindings, canonical bytes and comparison.
- [Local store](../../../ingestion/catalogue_snapshot.py) implements sealing,
  verification, latest, references, holds, withdrawal and logical retirement.
- [Capture coordinator](../../../ingestion/catalogue_snapshot_capture.py)
  coordinates registered exports and explicitly supplied PostgreSQL generations.
- [Transfer boundary](../../../ingestion/catalogue_snapshot_transfer.py) defines
  `catalogue-transfer-v1` and synthetic local quarantine/import validation.
- [Synthetic examples](../../../ingestion/catalogue_snapshot_fixtures.py) provide
  eight export artifacts and executable registration for all four families.
- [Generated JSON Schema](../../../schema/catalogue_snapshot.v1.schema.json) and
  [wire examples](../../../schema/catalogue_snapshot_examples.json) are exported
  by [export_catalogue_snapshot.py](../../../scripts/export_catalogue_snapshot.py).
  Run `.venv/bin/python scripts/export_catalogue_snapshot.py --check` to detect
  drift. Semantic model validation remains necessary beside JSON Schema.

C08's [catalogue contract](C08_CATALOGUE_CONTRACT.md) continues to own source
families, canonical identities, scientific scope and descriptive origin fields.
C09 adds storage and capture semantics without changing the accepted C08 wire
contract or activating the prototype UI.

## Identity and byte boundaries

A snapshot ID is the lowercase SHA-256 of its canonical manifest bytes. Canonical
serialization sorts JSON object keys, export objects by `object_id` and source
captures by `source_id`. Reordering those lists does not create another snapshot.
Supplied capture metadata is retained; no current timestamp or embedding state
is inserted into the identity. Different bytes, operation versions, registry
generations or retained provenance produce a different identity.

Each export object binds its canonical object/dataset/source identities, role,
hash, byte length, schema version, operation ID/version and provenance. Source
family and generation must agree with its source capture. A dataset identity
cannot acquire conflicting source ownership. The manifest binds each object's
exact operation ID to its version. Classification, relationship and operation
registry generations must each have one consistent value across all captures.
Every eDNA export dataset requires both `canonical_rows` and `classifications`.

`object_id` identifies a retained export artifact or shard. A single artifact may
contain many catalogue dataset rows; a file count is never an inventory total.
The local bounds are 4,000 export objects, 512 MiB of declared object bytes and
4 MiB of manifest bytes. A separate 4 MiB bound applies to the control ledger.
Exceeding a bound fails explicitly without truncating scientific input. The
acceptance fixtures include an intact 100,001-row artifact.

The local layout is an explicitly supplied absolute root and a `v1/...`
namespace, defaulting to `v1/catalogue`. Object paths use content hashes and
manifest paths use snapshot hashes. Reads verify canonical manifest identity,
exact object size and hash, and return the same bytes that were checked. Missing
historical bytes fail; readers never substitute current files. Traversal,
symlink ancestors and nonregular files are rejected. The root is a trusted local
filesystem boundary, not a defense against an attacker controlling that root
while an operation runs.

## Source registration and capture

`SourceExportRequirement` freezes a source-owned exporter, its roles, schemas and
operation identities/versions. `SourceExportRegistry` requires registrations for
all four families. A capture exports only the families enabled in its supplied
scope. It currently captures each selected source as a whole: nonempty row
filters or `analysis_id`, and a scope with no enabled family, fail before a
database connection is opened. C10–C13 must implement scientific filtering over
the retained bytes or explicitly extend the capture contract; C09 never labels
an unfiltered export as a filtered population.

For example, a future C10 adapter can register an injected exporter as follows.
The schema and operation names below illustrate explicit version ownership; they
do not declare that C10's production schemas have already been implemented.

```python
from ingestion.catalogue_snapshot_capture import SourceExportRequirement


def register_ctd(ctd_exporter):
    return SourceExportRequirement(
        source_id="ctd",
        source_family="ctd",
        schema_versions={
            "casts": "ctd-casts-v1",
            "depth_observations": "ctd-depth-observations-v1",
        },
        operation_ids={
            "casts": "ctd:export:casts",
            "depth_observations": "ctd:export:depth-observations",
        },
        operation_versions={"casts": "v1", "depth_observations": "v1"},
        exporter=ctd_exporter,
        capture_method="postgresql-repeatable-read-v1",
        qualifiers=("Descriptive capture; scientific approval is independent",),
    )
```

The exporter receives `(connection, heads, deadline)` and returns
`CapturedSource(tuple_of_snapshot_objects, content_bytes_by_object_id)`. It must
use the supplied transaction, preserve complete canonical inputs, honor the
monotonic deadline for non-SQL work, and match the registered source, role,
schema and operation for every object. It reads its frozen source generation
with `heads.source_generation(source_id)`. Content membership must exactly match
the descriptors; duplicates, extra objects and missing required roles fail.
Descriptors are detached before another exporter runs, and bytes must be
immutable `bytes` rather than mutable buffers.

An executable synthetic registration is available without a database or source
discovery:

```python
from ingestion.catalogue_snapshot_fixtures import fixture_registry

registry = fixture_registry()
assert {item.source_family for item in registry.requirements} == {
    "ctd", "metagenome", "remote_sensing", "edna_metabarcoding"
}
```

These exporters illustrate registration and frozen outputs. They do not prove
real-source acquisition or scientific parity. Production adapters must replace
the synthetic exporters explicitly; missing inputs have no fixture or legacy
fallback.

For actual consistent capture, the engine, dedicated v1 generation table,
registry, local store, scope and expected latest generation are all injected.
No application database URL is discovered. The generation table contains unique
`name`/`generation` rows for `publication`, `classification`, `relationship`,
`operation` and `source:<source_id>` for every registration. The coordinator
observes the complete head set, including additional rows. Every publisher must
update the relevant generation rows in the same transaction as its source or
registry changes; writers outside that protocol cannot receive this guarantee.

Capture proceeds in two database transactions:

1. A read-only `REPEATABLE READ` transaction reads the heads and exports bytes.
   It then closes; no database transaction remains open for model reasoning.
2. A `READ COMMITTED` transaction takes a `SHARE` table lock on the dedicated
   generation table and compares the complete head set. The lock blocks head
   insertion, update and deletion through local sealing and promotion. A final
   check runs immediately before the local pointer CAS. Rollover retries within
   the attempt/time budget or fails without promoting the aborted capture.

The defaults are 30 seconds, 64 MiB of exported bytes, 4,000 export artifacts and
two attempts. SQL statement, lock and idle transaction timeouts are set from the
remaining budget. Callback work outside SQL must cooperate with its deadline.
This is a protected capture/publication interval across two systems. It is not
an atomic PostgreSQL/filesystem transaction. Loss of a database connection can
release its locks; publication disposition must be reconciled after an uncertain
failure. Embedding completion is not a precondition for sealing or promotion.

## Sealing, references and current access

`seal(manifest, contents)` verifies immutable bytes before registering a snapshot.
It does not advance latest. `promote(id, expected_generation=...)` verifies the
registered snapshot and current access, then advances latest conditionally.
`latest()` returns its ID and pointer generation after current verification.
Pointer generation is separate from the control/audit revision, so sealing,
holding or referencing a snapshot does not invalidate an unchanged latest CAS.
An actual competing promotion is not silently adopted.

One file lock and atomic bounded control document serialize latest, references,
holds, persistent revocations, logical retirement and their audit entries.
Idempotent retries do not duplicate successful state transitions. An interrupted
registration can leave immutable orphan bytes, but those bytes are not readable
through the registered-snapshot interface. A confirmed failed state write does
not emit a successful transition audit.

Every normal snapshot read, latest lookup, promotion and new reference evaluates
the supplied trusted current access gate. Only literal `True` permits access;
the callback receives an isolated manifest copy. Persistent `revoke(id)` overrides
that gate, including access to old snapshots and latest. Retained bytes and
descriptive origin/authorization strings never grant access. The library is a
trusted local primitive: authenticated caller policy and operator authorization
belong to later services. `lifecycle()` exposes trusted operator audit state and
must not become a public catalogue listing.

References and holds survive restart. Cleanup checks current eligibility under
the same lock: latest, referenced and held snapshots are protected. A hold or
reference committed first protects the snapshot; logical retirement committed
first makes a subsequent hold/reference fail. Dry runs are observations and
create no reservation or success audit.

Cleanup implements **logical retirement only**. Its report/audit states
`retired_count` and `physical_deleted_count=0`; immutable files remain present.
A retired snapshot cannot be read, held, referenced or resurrected by resealing.
Physical garbage collection, age/cohort policy and distributed retention storage
are separate future work. Withdrawal may deny access while a hold still requires
the underlying bytes to be retained.

Two error types preserve uncertain outcomes:

- `SnapshotCommitUncertain` means a local state-write error could not be
  reconciled as committed or unchanged. It carries the action/details and
  proposed control revision/latest generation. Reopen trusted state and inspect
  the exact proposed transition before retrying.
- `CapturePublicationUncertain` means a local promotion or subsequent database
  transaction release has an uncertain outcome. Its snapshot ID and pointer
  generation identify the proposed publication, which may already exist. It is
  not a rollback or success assertion. Uncertain sealing that cannot itself
  advance latest retains `SnapshotCommitUncertain` instead.

Neither case performs an automatic compensating pointer write. Old immutable
snapshots remain independently verifiable. `changes(old_id, new_id)` derives
added, removed and replaced export-object identities; C17 and source adapters
must interpret row-level membership changes and explicit investigation branches.

## Independent transfer and quarantine

The transfer manifest binds the independent destination, authorization reference,
source snapshot identity and exact object set. Each object retains origin
system/object/snapshot/generation, hash, schema and operation versions,
scientific qualifications, access conditions and authorization reference.
`live_dependency` is strictly false. A transfer ID canonicalizes nested snapshot
ordering as well as its own object ordering.

`build_transfer` constructs descriptive provenance from explicitly supplied
bytes. `import_quarantined` requires current trusted authorization, per-object
eligibility and destination access gates; reference text alone is insufficient.
It checks the destination and complete membership, hashes, sizes, schema/version
bindings and counts, stages bounded local bytes in an explicit quarantine root,
verifies them again, and rechecks the current gates before sealing an independent
snapshot. It never promotes latest. Shared content hashes are staged once.

`json-rows-v1` requires an array of objects with an exact row count. Duplicate
JSON keys, nonfinite/unsafe numbers and malformed row encodings are rejected.
An empty array has known count zero. `opaque-bytes-v1` preserves bytes with no
invented row count. Scientific content validity and eligibility remain the
source adapter/current policy's responsibility; a matching hash does not prove
scientific approval.

Successful copies retain origin provenance. Chained copies whose source already
has `Provenance.origin` are rejected explicitly: the initial one-way contract
does not overwrite earlier provenance. A future multi-hop transfer requires a
typed lineage extension. Rejected staging is removed. A late seal/read failure
may leave verified immutable bytes or registration, but it never advances latest;
uncertain state errors require the reconciliation described above.

No origin identifier is opened as a URL/path, and missing source inputs never
trigger a legacy read. Real export/import remains separately authorized. Before
any real transfer, operators must assign a withdrawal owner, notification route,
response expectations and a process to suspend/revalidate independent copies.
Independent stores do not automatically learn source permission changes. See
[site separation](SITE_SEPARATION.md#explicit-approved-data-transfer).

## Adapter and service handoff

C10–C13 own real source schemas, complete canonical exports, semantic validation
and parity. They must preserve CTD cast/depth sampling and units; metagenome
assignment method, denominator and omitted-taxon meaning; SST product/resolution,
regional role and coverage gaps; and eDNA protocol/assignment, sample/control
classification and applicable scientific scope. Registry or proximity evidence
must not become an unverified physical-identity claim. Published status,
scientific approval, structured-query readiness and embeddings remain independent.

C14 must supply authenticated current policy and registered permitted operations;
C17 must persist investigation references and explicit refresh/branch behavior.
Later cloud configuration must retain the independent resource boundary. These
components do not acquire acceptance through the synthetic C09 examples.

The [C09 handoff](handoffs/C09.md) records exact source revision, completed checks,
remaining live gates and delivery. The [component specification](components/C09-catalogue-snapshots.md)
defines the selected scope. No actual data sealing, transfer, production access
or deployment is authorized by this contract guide.
