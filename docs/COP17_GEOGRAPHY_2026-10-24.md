# COP17 catalogue geography answers

Status: deployed and verified on `cop17-demo` at revision `ocean-cop17-demo-00008-wd9`.
Live release evidence: `COP17_DEMO_GEOGRAPHY_RECEIPT_2026-10-24.json`. Production and the overhaul
checkout are outside this change.

## Visitor questions

- How many named areas are available?
- Which sampling areas have names?
- Which bays have sampling data?
- Are all the sampling data from around the same area?
- Where are the sampling locations?
- 名前のある採水エリアはいくつありますか？
- 採水データはすべて同じ地域のものですか？

These free-text questions produce an answered, cited coverage summary using the
complete matching canonical cohort. They do not estimate totals from retrieval
examples. Exact statistics and the availability of named-area membership are
rendered deterministically; no language model invents names or counts.

## Scientific meaning

The complete default ANEMONE scope excludes explicitly classified controls and
contains 3,155 source occurrences. Of these, 3,154 have valid stored coordinates,
one has missing coordinates and none has invalid coordinates. The coordinate
bearing records represent **216 distinct exact stored positions**.

The latitude extent is 17.45833333–45.54166667 degrees and the longitude extent
is 123.8125–148.6875 degrees. The actual northernmost and southernmost recorded
positions are approximately **3,184.838 km apart**, using a spherical great-circle
calculation with radius 6,371.0088 km. This distance describes those two actual
positions; it is not advertised as the global maximum pairwise distance, a
surveyed path or continuous sampling coverage. Equal-latitude or rounded-zero
distance cases do not imply a compact area; the extent and distinct positions
remain visible.

All coordinate-bearing records have `provider_grid_unconfirmed` precision.
Physical sampling identities remain unverified, and the unknown control status
of the retained source records is disclosed. Coordinate precision is not improved
by displaying more decimal places.

**Named bays/coastal-area count is unknown, not zero.** This source-catalogue
aggregate has no reviewed area-membership relation. Provider sample names,
project labels, the MiFish marker namespace and worldmesh identifiers are not
converted into named bays. The read-only live metadata audit confirmed that the
3,155 matching raw metadata dictionaries have no structured bay/region-name
field; correspondence and other metadata values were not exported to logs.
This does not establish that upstream sources or separate research registries
could never supply names. A future named-area count needs explicit area
boundaries/membership and its own versioned evidence binding.

The fixed Miyagi 2020–2023 fish/SST examples retain their own scope. Their
regional diagnostic rectangle is not used as whole-catalogue membership.
Pinned-analysis geography questions ask visitors to return to free text rather
than silently replace a published cohort with all ANEMONE records.

## Evidence and scope

New metric `catalogue_geography` uses immutable algorithm
`edna-catalogue-aggregate-v3`. It retains the exact source filters, publication
heads, source snapshots and ordered scientific input fingerprints. Historical
v1 catalogue and v2 coordinate-count receipts remain unchanged and readable.

Geography reuse is demo-only, bound to the exact effective filters, v3 metric,
verified payload hash and all three canonical/retrieval publication heads.
Publication heads and the ready GCS pointer are rechecked before serving a
retained result. Its named-area status is expressly restricted to the canonical
aggregate; it does not query mutable application research registries. No
independent registry-head state is therefore represented as a cached fact.
The scientific-table immutability assumption is the same documented SELECT-only
demo contract as location-v2; unpublished manual edits require republishing.

Project, run, date, taxon and coordinate filters remain in force. Unresolved
place names, cardinal directions, ecological restrictions, classifications,
thresholds and mixed ANEMONE/SST area totals require clarification. Explicit
control filters remain distinct from the default control exclusion. Empty and
single-position scopes receive their own answers without inheriting global
extent or distances.

## Verification

- Full backend: 1,595 passed; 122 optional integration skips.
- Disposable PostgreSQL: 117 passed, including geometry, scoped SQL, historical
  receipts, integrity checks, publication changes and guarded reuse.
- Geography plus existing location routing: 125 passed.
- Independent review: no remaining blockers after directional-scope,
  rounded-distance and Japanese-clarification regressions were fixed.
- Source lint and whitespace checks passed.

Live release acceptance also verified the accepted API image against
independent demo SQL, signed-in English/Japanese questions, filtered counts,
provenance navigation and the existing free-text/fish/SST workflows. The frontend
image remains unchanged. The temporary QA definition is sealed after execution.

## Live acceptance

The accepted API-only build `74aaca41-1f3a-4c61-aa5f-a380a51eab1d` passed runtime, authentication,
schema/backup/restore and reviewed image-scan gates. Independent demo SQL matched
the count, coordinate extent and actual-endpoint distance. Scoped and historical
evidence checks passed. Signed-in English/Japanese geography answers, source
guards, filtered coverage, citation provenance and existing free-text/fish/SST
workflows passed. The frontend image, production service and scientific snapshot
remain unchanged. The QA definition is sealed without database secret or Cloud
SQL references. All request timings are retained in the release receipt.
