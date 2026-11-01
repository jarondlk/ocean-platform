# Approved-data transfer and withdrawal procedure

This procedure prepares a later explicit one-way v1 import. It neither obtains
real source data nor grants access. C09/C26 synthetic transfer checks remain the
software evidence; source scientific/access decisions and real transfer are
separate gates. There is no automatic synchronization with the legacy system.

1. An identified data/scientific authority specifies the exact source cohort,
   snapshot/publication generation, purpose, eligibility, permitted operations,
   access conditions and exclusions. Published does not mean independently
   approved or unrestricted. Record concrete export/copy authorization and
   destination project/stores. Exclude accounts, credentials, private history,
   conversations and staging/unpublished experiment inputs by default. Unclear
   scientific authority stops selection; C27 creates no approval.
2. Freeze the C09 transfer manifest: source/origin identifiers, source snapshot
   and hashes, schema/operation/relationship/classification versions, content
   counts/lengths/digests, qualifications, access restrictions and authorization
   reference. Review canonical inventory and full counts, not a preview. Keep
   physical identity, assay/method/product distinctions and original authority.
3. Under a separate explicit grant, use a temporary transfer identity scoped
   only to that cohort and v1 quarantine destination. Serving/controller/worker
   identities must not read legacy data. Record grant expiration/removal owner;
   keep secret values out of manifests/logs. Do not change source publication
   heads, reviewed classifications or legacy access configuration to export.
4. Import to the independent v1 quarantine namespace. Verify exact manifest,
   eligibility/current authority, every hash/count/schema and scientific contract
   before sealing an independent v1 snapshot. Reject destination mismatch,
   tampering, ineligible inputs and unsupported lineage; never silently sample
   or drop invalid members. Preserve failure receipts and quarantine state.
5. Retain the immutable transfer receipt and origin provenance. Imported data
   cannot become scientifically approved by validation, inference or experiment
   output. Explicitly activate an eligible v1 snapshot only through its accepted
   contract; importing does not automatically promote latest. A later update is
   a new authorized transfer with its own manifest. Remove temporary grants and
   verify removal; no ongoing legacy connection remains.
6. Before real copies, designate a responsible source authority and v1 operator,
   notification channel, response target and verification record for withdrawals
   or permission changes. These inputs remain unassigned in this preparation;
   no response SLA is invented. On notice, suspend affected v1 copies and new
   work, revalidate current access to retained outputs/history and preserve holds,
   provenance and denial records. Apply the explicit destination withdrawal
   contract and verify hidden counts/names/results do not leak. Independent
   copies cannot automatically discover upstream revocation.
7. Reinstatement requires an explicit new authority decision and accepted
   revalidation/transfer, never automatic retry after a withdrawal. Disposal of
   real objects, backup/lifecycle changes and retention exceptions require their
   own reviewed operation; do not delete held investigations or evidence.

Expected receipt fields: operator/time, authorization reference, exact source
and destination IDs, source/config/schema/code hashes, manifest hash, eligible
and rejected counts with reasons, validation/activation/withdrawal observations,
temporary grant removal and unresolved gates. Evidence records may contain
sensitive identifiers; store actual live receipts in the separately approved
private location, with hashes/references in this repository as appropriate.
