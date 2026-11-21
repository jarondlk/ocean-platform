# B2 — Data and catalogue completion plan

## November 21 delivery checkpoint

The qualified eDNA catalogue is live for signed-in beta administrators.
The [delivery receipt](b2-20261116/decode-live-20261121.json) binds the exact
39 datasets to the running image, activation and control generation. It records
the passing cold and warm private list, the signed-in list and two raw occurrence
pages, and the reopened B1 Q6 answer and citation. The earlier failed timing
receipts are preserved.

Use that evidence for the initial data release. Prioritize the remaining dataset
dispositions and focused context, export and withdrawal journeys. The repeated
timing matrix and broad CI rerun are deferred. Full B2 acceptance remains open.

## Original preparation checkpoint

Planning checkpoint: 2026-11-16 JST, `overhaul`, after accepted B1 source
`7905aa9aaae4a4af1f8bbd3ceba74d5dda17d544`.

**Ready for preparation and local implementation; not ready to activate eDNA.**
This plan performs no acquisition, upload, publication, deployment, model call,
scientific reclassification or scheduling change. B2 is an integration milestone
for existing C09/C11–C14/C16–C18/C21 contracts, not a new component series.

Implementation began later on November16. The [local checkpoint](b2-20261116/implementation-local-checkpoint.json)
records completed exact input recovery, independent row oracle, full prefix
metadata pagination, C12 optimization and justified bounded semantic-cache
fallback, Research-preserving publisher amendment and702 focused local tests.
The [hosted source qualification](b2-20261116/hosted-verification.json) now passes
702 runtime tests and43 actual PostgreSQL16 parity cases; an additional88 local
costly-path trials pass in their [separate receipt](b2-20261116/costly-paths-local-followup.json).
The historical audit below remains unchanged. Actual GCS/container/browser,
logical dataset dispositions, fresh-base publication and B2 acceptance remain open.

## Outcome

A signed-in beta user can find the intended data across all four source families,
reach every authorized dataset/table beyond previews, understand its scientific
qualifications, save/reopen the exact context, and export retained evidence with
honest bounds and provenance. Every intended dataset is accounted for as active,
held/quarantined, withdrawn, superseded or excluded with a source-backed reason.
Availability for raw browsing does not establish scientific eligibility.

Keep the working CTD/metagenome/MUR data and B1 Research evidence. Bulk imports of
already accepted data, automatic Research delivery, production experiment workers,
backup/restore acceptance and final release remain outside this milestone.

## What the audit established

These are accepted historical measurements and current local/source observations,
not newly executed live data acceptance. See the [planning audit](b2-20261116/planning-audit.json).

| Area | Evidence and present limitation | B2 treatment |
|---|---|---|
| B1 baseline | Serving62/controller7, API `55cef311…`/source `4872d04`, frontend `0bde2554…`/source `6fdf666`; queue PAUSED/empty and no Scheduler jobs at B1 closure | Fresh read before each apply; preserve all settings and source-bound evidence |
| CTD | Accepted 162 casts and 10,955 depth observations; Q6 object identity and citations independently checked | Revalidate current-candidate browsing/count/context/export parity; do not repeat import |
| Metagenome | Accepted Kraken/MetaEuk matrices, 58,712/67,240 retained rows | Preserve method separation and unknown abundance denominators; no organism-abundance claim |
| MUR regional SST | Accepted 1,455 observations; six retained final-series gaps; provisional descriptive preview | Preserve UTC instants, foundation-analysis product, delivered support and grid-point qualifications; no invented native pixels or gap filling |
| eDNA | Prepared 39 datasets: 3,498 occurrences, classifications and assays each; 349,638 detections; 3,155 unknown classifications, 343 negative controls; all physical sample identities unresolved | Verify exact bytes and totals again; raw inventory with explicit eligibility qualifications; no manufactured environmental classifications |
| eDNA request cost | Local raw detection page 15.076610s before GCS/network; unchanged C12 loader still validates every row on every load | Own the performance repair in C12/C14; historical timing is not a current-image benchmark |
| Cache experiment | Private prototype: 14.802s fill, 1.891s warm overview, about 675MiB deep-frame accounting and 1.15GiB process peak | Diagnostic only. No production cache/security/concurrency acceptance exists |
| Private inputs | Documented raw/eDNA input directories are absent. The old held preparation directory exists but contains zero files | Recover exact pinned sources into new private directories; do not treat an empty directory as a usable cohort |
| Old publisher | Preparation is anchored to the old CTD-only base; `publish_append.validate_bundle` requires `research_enabled=False` | Qualify a Research-preserving operator amendment before any append; do not replay old preparation/publication |
| Other SST/JCOPE | Research-SST inventory stopped at a 16,000-object metadata cap. JCOPE audit parsed 1,837 distinct granules; one invalid placeholder occurs at 11 paths | Close inventory with bounded paging; qualify or hold each actual input, never relabel JCOPE as MUR |
| Exports | Production C21 supports permission-checked retained-evidence page CSV/JSON. Catalogue browser has no generic bulk-export control; prototype investigation export is not production integration | Verify the real page export path; never present a page/preview as a complete corpus download |

The user's acceptance of 17.671s full cold navigation is retained in its own
[B1 disposition](b1-20261114/cold-navigation-ux-disposition-20261116.json).
It does not change the separate 15s catalogue request deadline or waive eDNA
integrity, scientific eligibility, memory or source-coverage requirements.

## Ordered delivery increments

### B2.1 — Recover and reconcile the source inventory

1. Open the current beta control/activation by exact generation and hash. Record
   descriptors, registrations, references, C17/C21 dependencies, holds, revocations,
   audit/control size and remaining ledger capacity. The B1 acceptance is a
   baseline, not fresh authority for a later write.
2. Recover the accepted scientific inputs using the finite generation/size/SHA
   selections in [the private-input handoff](cohorts-20261103/private-inputs-handoff.json)
   and [secondary-Mac recovery procedure](../handoffs/SECONDARY_MAC_HANDOFF.md).
   Prefer existing beta quarantine/snapshot objects for accepted copies. Use
   separately authorized read-only origin access for eDNA source generations.
   Do not repeat completed uploads or copy accounts, history, caches or backups.
3. For eDNA, recover the pinned normalized index, all 41 registry receipts and
   their bound objects; select the 39 current-v3 source bundles and record the two
   older bundles as excluded/superseded. The retained index generation is
   `1790740062783615`, SHA `76d89bc641b739f3b5648287f24e947bdd6b6a7f3f8bbbf31020f7d516fd4d86`.
   Revalidate registry/object membership and source-to-export projection with
   `prepare_edna.verified_bundles`. Missing generations stop that input; newer
   bytes require an explicit source supersession, not silent substitution.
4. Close scientific-source inventory using bounded metadata pages and resumable
   checkpoints. A response-byte cap is a partial inventory, not completion.
   Reconcile logical datasets separately from files, granules, duplicate paths,
   generated caches and derived publications. Keep source payloads/manifests private.
5. Produce a dataset disposition ledger and independent expected-result manifest
   before changing code: exact membership, table totals, hashes, method/protocol
   populations, known zeros, missing/unknown values and current eligibility.

**Exit:** recoverable inputs verified or individually gated with reasons; complete
selected-cohort oracle; no unexplained missing or duplicate intended datasets.
Synthetic unit work can proceed while a specific real input is unavailable.

### B2.2 — Repair eDNA cold-path performance without changing its meaning

Start with bounded per-load reuse of validated taxonomy/assignment results and a
precompiled primitive-validation plan in `ingestion/edna_catalogue_inputs.py`.
Preserve every row's primitive/nullability, ownership, identity, foreign-key,
classification-lineage, protocol, count and concentration checks. Repeated JSON
can share validation within a load; malformed/oversized/duplicate-key JSON must
retain its exact rejection semantics. Measure before choosing another mechanism.

If that is insufficient, qualify a separate immutable semantic-input cache owned
by the trusted resolver/store instance. It must bind the canonical manifest,
metadata, complete object membership, operation/schema identities and verified
bytes/generations; recheck current authority, payload integrity and closing fences
on every request. Never cache users, current permission/eligibility decisions,
filtered responses or catalogue views. Keep actual-backend view caching disabled.
Detached return objects must resist mutation. Bound retained bytes and entries,
evict before growth, coalesce concurrent fills and exclude failed/partial loads.
Do not copy the private diagnostic cache into production as accepted code.

Measure four different budgets separately: sealed bytes, decoded Arrow bytes,
retained cache bytes and whole-process memory. Preserve existing 2,000,000-row /
512MiB decoded snapshot limits, C09 bounds, namespace checks and C26 view-memory
behavior. The accepted API has 1CPU/4GiB with request concurrency4; initially keep
that shape and use a **proposed B2 process-peak budget of 3GiB**, leaving 1GiB margin.
Record RSS and container memory and use the larger applicable observation.

Predeclare the performance protocol before running it:

- Test the complete 39-dataset cohort, not one convenient small dataset: discovery,
  list/open/inspector, raw occurrence/detection paging, inventory/count/coverage.
- Separate process-cold, semantic-cache-cold, warm and optional startup-warmed
  cases. At least three cold trials and ten warm trials for the costly paths;
  record every attempt and failure, hardware/image/resources and data identities.
- Exercise independent requests and shared-source fills at concurrency1,2,4,
  including cancellation and failed fills. Check memory recovery after eviction.
- Final actual-GCS/signed-in request trials must complete within the unchanged15s
  deadline including applicable queue/verification/serialization/transport work.
  Aim for API headroom rather than a 14.99s local result. Full-page startup time
  is a separately reported metric covered by the user's current UX disposition.
- If concurrency4 cannot meet bounded memory/latency, qualify explicit admission
  or a documented resource/configuration change before rollout. Do not silently
  raise deadlines, memory, instances or cache limits. Warmup before Ready is an
  option only if measured cold work still requires it; retain min0 billing.

Security/parity cases cover warm-byte or metadata tamper, generation/activation/
registration changes, removal/revocation/retirement, classification/owner changes,
hidden-source ID collisions, returned-frame/attrs mutation, decoded/retained bounds,
eviction, concurrent successful/failed fills, and complete raw/eligible results.
A complete zero eligible count can be honest; it must never imply ecological
absence. Physical sample counts remain unknown without resolved source identities.

**Exit:** exact oracle/response/hash parity, fail-closed current authority, bounded
concurrency/memory and measured candidate performance; no scientific relabeling.

### B2.3 — Qualify an append against the working Research catalogue

The old all-qualified package added metagenome/SST/eDNA to a CTD-only base. The
working beta already has metagenome/SST. Compute the new set from the current
canonical inventory: **39 eDNA datasets are the expected increment**, subject to
that reconciliation, rather than replaying all 41 old additions.

Amend the owning prepare/append/publish validation to consume an exact fresh base
and preserve the current Research-enabled mode. Preserve access policy, scientific
mode/approval, existing descriptor order, registrations, source hashes, latest
pointer semantics, every C17/C21 reference/hold and audit. An enabled baseline may
stay enabled; the operator cannot expand user/scientific/execution authority.
Add rejection cases for old CTD bases, authority drift and stale/missing references.
Record intentional contract/source supersessions; retain the old operator receipts.

Write immutable objects create-only and read back exact sizes/hashes/generations.
Make the lifecycle replacement a final exact-generation CAS. A concurrent C17/C21
write makes the candidate stale: rebase after inspection, never overwrite its
references or force an old blob. Lost acknowledgements need exact current outcome
reconciliation; do not retry an uncertain control write blindly.

C09 registration and public exposure are different steps. New immutable objects,
registrations and a proposed activation may be retained while the public host
continues using the old pinned activation. This permits bounded private probes
using the proposed binding without advertising eDNA early. Qualify the concrete
probe target/identity/configuration and current store boundaries; no fixture
principal may be represented as signed-in browser acceptance.

November16 implementation qualification found a required ordering constraint:
the old B1 image lacks C14's unrelated-seal compatibility proof, so a lifecycle
append could strand its retained Q6 evidence even under the old activation.
**Stage the qualified compatible API/controller against the original activation
before replacing control.** Preserve and actually read the existing B1 evidence;
then publish the exact append, privately probe the proposed binding, deliberately
expose it and rearm. A proposed single-image package may contain separate old/new
opaque binding files selected by trusted configuration; that package/probe/rollout
contract is still to be implemented and source/image-qualified. Do not replay old
B1 helpers, regenerate Q6 or restore an obsolete lifecycle control for rollback.
[Accepted source and real private candidate](b2-20261116/qualified-private-candidate.json).

**Exit:** source-bound operator tests and immutable publication candidate, fresh
CAS basis, preserved B1 authority/retention, and a reviewed uncertain-outcome and
rollback procedure. There is no production publication pass merely from preparation.

### B2.4 — Stage, deploy and qualify the data increment

1. Quote incremental recovery/storage/network/build/probe costs against the
   existing beta-only JPY50,000/month target. The B1 JPY873.80 planning figure and
   specific validation reserve are historical inputs, not a fresh B2 budget.
   Plan **zero new model calls**; use deterministic data oracles. Retain notice
   before any change would exceed the monthly target.
2. Run changed-source focused checks and hosted Linux/source-bound CI. Build with
   the AGENTS.md Tokyo build identity, source bucket and `CLOUD_LOGGING_ONLY`;
   verify nonroot image/source/package proofs. Scientific payloads stay out of images.
3. Stage the compatible API/controller with the old activation before a lifecycle
   append, then use actual beta GCS transport for bounded private candidate probes. Retain
   original failed/qualified attempts; a local transport or warm-only proof does
   not establish the live gate. Existing public activation remains pinned until
   the deliberate rollout step.
4. Generate a new rollout contract from the actual current serving/controller
   state. Catalogue code is shared with Research tools, so qualify both services'
   compatible image/configuration identities. Preserve frontend unless UI code
   changed, identities, numeric secret refs, proxy, ingress, scaling and timeouts.
   Do not replay B1's fixed phase helpers or observer executions. If fresh global
   quiescence is required, use a separately qualified B2 observer and budget;
   preserve the original observer's generation1/count20 receipt and guards.
5. Drain/stage/promote/rearm under fresh guards. Keep queue/Scheduler/sweeps paused
   and worker/experiment execution disabled. Confirm old-source reachability and
   retained Q6 evidence after the new activation. Do not regenerate Q6.
6. Perform the real signed-in data journeys immediately after bounded promotion.
   A failed required latency/integrity check leaves B2 unaccepted and invokes the
   compatible image/activation rollback. Preserve new immutable bytes/references
   and reconcile current control; never restore an obsolete control blob.

**Exit:** actual new-image/configuration readback and live signed-in data gates,
with compatible rollback observed and preserved three-family/B1 behavior.

### B2.5 — Finish catalogue, context and export journeys

For CTD, metagenome, MUR and eDNA on the selected deployed candidate:

- Browse collections and every permitted directory/leaf, search and filter,
  inspect all six sections, and page beyond the first preview. Compare canonical
  membership, totals, units, qualifiers and full-result hashes with the oracle.
  Changing preview/page size must not change whole-scope totals or counting units.
- Restore snapshot/object/filter/inspector selection through deep links,
  Back/Forward and reload. Switching snapshots clears incompatible state and
  invalidates stale cursors rather than reusing protected results.
- Browse without a context write; explicitly Attach to supplement and Pin to
  restrict. Verify shared context across conversations, saved/reopened immutable
  revisions and exact submission binding. Refresh creates a new branch, preserves
  original evidence and surfaces unresolved references without guessing replacements.
- Verify actual C21 retained-evidence **page** CSV/JSON downloads, export permission,
  spreadsheet safety, legitimate numeric values, scope/snapshot/hash provenance,
  bounds/completeness and page-versus-total labels. No bulk catalogue export or
  production transcript export is assumed from prototype buttons. If a required
  page-export integration is missing, repair its C07/C16/C21 owner and contract
  before claiming the journey; a client-only permission check is insufficient.
- Exercise current access, source withdrawal and historical retention using fresh
  disposable beta fixture copies/contexts. Never revoke the real CTD/Q6 source,
  change real classifications or reopen B1's closed fixture account. Holds retain
  bytes; current withdrawal must still deny reads/exports without private leakage.
  Physical purge and backup/restore acceptance remain B4.
- Cover EN/JA, light/dark, narrow-screen layout and keyboard actions on these data
  paths. Record actual accessibility observations without inventing an independent
  assessor or spoken screen-reader assessment.

JCOPE requires product-faithful `model_assimilation`/`model_instant` mapping,
embedded UTC instants, valid/missing cells and bounded snapshot partitions: its
2,380,752 audited grid cells exceed the C11 per-snapshot2,000,000-row bound if
combined. Declare source-owned bounded partitions and a complete partition manifest
before capture; do not label an arbitrary slice a complete source. Cross-partition
aggregates need a qualified complete-input operation or explicit unavailability,
not an average of previews. Preserve duplicate-path lineage and quarantine the
invalid placeholder rather than fabricating timestamps or observations. Distinct MUR products,
processing generations and regional/grid support must remain distinct. Every
remaining SST input receives a disposition; a reasoned hold is not an active
scientific publication or a claim of complete ecological coverage.

**Exit:** current-candidate journey evidence plus a complete intended-dataset
ledger; all four families accounted for and the qualified raw eDNA cohort usable.
Required integrity/authority/numerical failures remain blockers. Missing external
scientific review remains explicit without blocking honest raw inventory.

### B2.6 — Accept and checkpoint

Create a B2 receipt bound to source, API/controller/frontend images, activation,
control generations, cohort/operation versions and actual resource configuration.
Include the dataset ledger, independent oracle, parity/latency/memory results,
current access/withdrawal/export observations, compatible rollback, costs and
remaining scientific limitations. Reference unchanged B1 evidence rather than
repeating model calls or successful Jobs/imports.

Update STATUS, this plan and the deployment handoff, preserve new private inputs/
receipts in an owner-only indexed archive, then commit and push `overhaul`.
Documentation-only checkpoints may skip broad CI; changed runtime/operator source
needs its applicable hosted checks. B2 acceptance supplies data evidence to B5;
it does not mark the complete C26 matrix, scientific review or beta release passed.

## Verification ownership

| Change or gate | Focused owning verification |
|---|---|
| C12 loading/semantics | `test_edna_catalogue_inputs`, `test_edna_catalogue_contract`, `test_edna_catalogue_adversarial`, `test_frozen_edna_catalogue`, SQL relational parity on disposable PostgreSQL16 |
| Multi-source/C14 authority and memory | `test_beta_multisource_edna_catalogue`, `test_frozen_scientific_catalogue`, catalogue service/materialization/reference-epoch and GCS snapshot tests; repeat C26 scale checks only when that owning behavior changes |
| Preparation/publication/CAS | Beta eDNA/cohort/append/publish tests, uncertain ACK/concurrent C17/C21 control writes, fresh-base Research-enabled authority preservation and staged GCS probes |
| Context/retention | C17/PostgreSQL role/guard and beta retention/context tests; focused B1 read/evidence regression for any shared-path change |
| Browser and exports | C16/C18 state/client tests, actual retained-evidence/C07 export checks, then signed-in current-candidate journeys; fixture UI is not live acceptance |
| Final data scope | Complete intended-dataset ledger, source-backed classifications/units/product/protocol qualifiers, all-page membership and independent whole-scope oracle |

B2's likely critical path is input recovery → cold-path validation/parity →
Research-safe append → live GCS/concurrency qualification → guarded rollout →
signed-in journeys/withdrawal/export → acceptance. Inventory and UI test design
can proceed alongside performance work; publication depends on their actual gates.
