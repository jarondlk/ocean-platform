# C22 experiment contract

Design prepared after C21 delivery. Implementation selection and acceptance are
recorded separately in the C22 handoff and evidence directory.

## Proposal and review

Experiments are private to their owner. Current active researchers and admins
with research/read/export permissions may prepare and approve their own plans.
An admin cannot approve another owner's experiment. Every revision retains the
question, exact C17 context identity and scope, explicit cohort, exclusions,
pairing rules, method, assumptions, exact UTF-8 Python, expected outputs,
limitations, declared seeds, environment identity and resource bounds.

Approval permits execution only; scientific authority remains experimental and
independent scientific verification is not claimed. C22 executes no Python.
Its dispatch acceptance uses an explicitly configured fake executor. Real
execution awaits C23 containment and C24 configuration gates.

Requests bind the expected C17 investigation/conversation/revision, snapshot
and context payload hash. Revision changes create immutable history. Approval
and dispatch additionally bind the exact proposal revision, optimistic head
version, canonical proposal hash, code byte hash, input-manifest hash,
environment descriptor hash and resource hash. Approval history survives a
revision, but its authority does not transfer to the new revision.

## Frozen inputs

The exporter reads the verified C13 context and exact C09 child snapshots under
current C14 access. It applies the actual C10/C11/C12 scientific selectors and
the complete C17 pin restrictions. Unsupported restrictions fail explicitly.
C21 previews and operation pages do not define complete experiment cohorts.
Published analysis tables additionally retain C13/C02 eligibility and C01 exact
question compatibility; publication does not establish independent review.

Raw source export eligibility requires a trusted host publication-policy witness
binding the exact source, dataset, child snapshot, publication generation and
object hashes, plus policy version and decision reference. The request cannot
supply this authority. Missing, withdrawn or mismatched policy denies export,
approval and dispatch. Synthetic policy witnesses remain visibly test-only.

Cohort selections name exact datasets, source table roles and required columns.
Mandatory row identities and scientific qualifications remain in effective
columns and manifest sidecars. Casts/depths, libraries/summaries, SST summary/grid
support and eDNA occurrences/assays/physical samples remain distinct. Preserve
units, method/rank, denominators, date precision, classification, missing values,
source completeness and exclusions. Explicit source-owned entity exclusions
cascade through their actual foreign keys. Reject ambiguous or unsupported
cohorts and incomplete source tables; never silently sample.

Independent inputs assert no physical pairing. Physical pairing requires exact
visible C13 verified physical-identity relationships and retained endpoint proof.
Proximity, matching labels and candidate overlap cannot establish this identity.

Machine inputs use versioned canonical, lossless UTF-8 JSON with exact integer
values, finite float values, nulls and Unicode. Their canonical row order, dtype,
row counts, columns, source identities and file hashes are retained. Browser
number normalization and spreadsheet escaping do not alter machine bytes.
Any separate human CSV uses C07 and has its own identity.

Every staged file and sidecar, including manifest bytes, counts against 256 MiB.
Output allowance is at most 50 MiB; defaults are 2 CPUs, 4 GiB and 600 seconds.
Narrower limits may be approved. Resource estimates do not replace measured
input byte checks. Environment descriptors come from an explicit host registry;
real descriptors must pin image, lockfile, Python and scientific packages.
An opaque request hash cannot invent a configured execution environment.

## Durability and dispatch

Persist immutable revisions, private input blobs/file references, approval
decisions and events alongside a proposal head, prepared operations, reservations
and outbox. Protect the exact C17/C09 dependency closure before independent
reference or artifact writes. A lost acknowledgement retains prepared protection
and retries reconcile deterministic identity. Logical retirement and native SQL
guards must preserve prepared and active experiment dependencies even when
experiments are disabled.

Dispatch rechecks the fresh owner, context, current source/publication policy,
all retained hashes and exact approval. A fixed global capacity lock serializes
reservation plus outbox insertion: at most one active experiment per owner and
two globally. Stable idempotency and unique revision dispatch prevent duplicate
reservations. A missing acknowledgement or expired lease does not prove stopped
execution and cannot release capacity. C23 receives an immutable envelope;
it must revalidate before any real launch.

Disabling dispatch retains owner-scoped history, frozen inputs and approvals.
No proposal action publishes an analysis, discovers a legacy database, acquires
data, installs packages, invokes a real provider or provisions cloud resources.
