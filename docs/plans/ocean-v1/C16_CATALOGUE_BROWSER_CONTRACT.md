# C16 catalogue browser contract

The service Context Catalog uses the unchanged C14 read API and an explicit,
authenticated C16 discovery registry. All feature flags default off. A host must
configure the same `CatalogueService` instance on the app and `CatalogueBrowser`;
only that matching configuration may advertise the catalogue as ready in C15.
Research and other unfinished destinations retain their existing capability gates.

## Snapshot discovery

`POST /catalogue/snapshots` requires `data:read` and accepts scientific scope,
limit (1–500) and an optional cursor. The trusted host supplies at most128
newest-first snapshot descriptors, an eligibility predicate and policy revision.
Discovery checks current user permissions, C14 source registration, lifecycle,
integrity and current source policy. It skips revoked snapshots, fails on corrupt
eligible sources and keeps eligible zero-match snapshots visible. Latest means
the first currently eligible descriptor in this explicit order. No C09 global
latest lookup, filesystem scanning or hash ordering supplies discovery authority.

HMAC cursors bind identity, scientific scope, page size, registry order and current
visibility/revisions. Callback mutation cannot change detached descriptors.
Authentication, discovery and serialization remain in the owned worker boundary;
cancellation cannot dispatch work after its checkpoint. Errors use C14's safe
status/message boundary. The schema version is `catalogue-browser-v1`.

## Transport and restoration

`createCatalogueClient` uses eight fixed same-origin POST paths, credentials omit,
no-store and redirect rejection. An optional trusted in-memory bearer supplier is
supported. Response streams have a40MiB bound; error bodies have a64KiB bound.
Strict UTF-8, duplicate-key, depth and actual wire-shape checks run before views
receive data. Known HTTP denial/error statuses remain authoritative even if an
intermediary sends HTML. Aborted requests and late transports cannot publish data.

Response checks bind snapshot, scope, operation/version, query parameters and
paging where the unchanged C13 receipt exposes them. Canonical hashed source IDs
and statistic aliases are checked. C13 root inventory and published-analysis
receipts do not echo every direct input ID; C14 enforces those input identities.
Aggregate previews may be explicitly truncated without a cursor. Native pageable
tables with known remaining rows require a progressing continuation. Any supplied
continuation must advance by the actual row count and stay within the known total.

URL state contains canonical snapshot/object/parent IDs, filters, cursor, page
size and inspector section. Malformed state fails visibly with a reset action.
Back/Forward/reload restore the same selection; changing snapshots clears stale
object/parent/cursor state. URL state never supplies identity, roles or scientific
authorization. The standalone browser uses the latest eligible snapshot; embedded
use accepts a supplied scope and optional pinned snapshot.

## Views and scientific boundaries

The tree, exhaustive listing and inspector use C14 totals/completeness directly.
Every node supports browsing contents, including dataset/analysis/table parents.
Five roots, lazy directory paging, search/source/kind/authority filters and full
active-filter chips preserve canonical IDs. The six inspector sections expose
native source tables, units, coverage, methods, provenance and relationships.
Unknown availability, unavailable operations, zero matches, empty child listings
and request failures remain distinct states.

Native table execution uses the actual operation registry and current scope.
eDNA browser tables explicitly request the raw population and keep the controls/
unknown-not-eligible qualification visible. Retained metadata row counts are
labelled retained rows; actual query totals come from the query receipt. Published
tables use their retained publication scope, displayed separately from catalogue
browsing scope. No workflow result or scientific authority is inferred or invented.

Browsing does not attach data, pin constraints, refresh an investigation or write
scientific state. Optional `onSelect(CatalogueSelectionEvent)` only reports a
canonical selection and snapshot for C18 to handle. Presentation preferences and
the P00 synthetic preview remain separate from service/scientific state.

## Current access and usability

Identity/revision changes, access denials, policy changes and discovery failures
clear protected tree/list/inspector/cache state. Every tree page and parent lookup
participates in revision validation. Reset clears invalid node/parent/cursor state
and may rediscover latest; embedded pins remain pinned. No prior protected result
survives as a stale fallback after invalidation.

English/Japanese and light/dark views support desktop/tablet/narrow layouts. The
mobile directory modal exposes dialog semantics, traps current tabbable elements,
closes on Escape and restores its opener. Tree items expose level/expanded/
selected state and roving keyboard navigation. Native result tables scroll within
their pane. Acceptance records manual keyboard/accessibility-tree observations;
it does not claim a spoken VoiceOver/NVDA or independent assistive-user assessment.

Disable `ENABLE_V1_CATALOGUE_BROWSER` to roll back this destination. Frozen
snapshots and saved evidence are unchanged. Synthetic local acceptance is separate
from real OIDC enrollment, scientific review, production capacity and deployment.
