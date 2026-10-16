# C14 — Authenticated catalogue service and tools

Work is additive on overhaul for the independent v1 system. No production source
discovery, data transfer, model call, approval change or deployment is performed.
The legacy site retains its existing endpoints and behavior.

## Exposure and trusted dependencies

`ENABLE_V1_CATALOGUE` defaults to false. An enabled API also requires an explicit
`app.state.catalogue_service`; missing configuration returns typed unavailable.
The application never constructs a synthetic or legacy-configured fallback.
All seven POST routes require existing `data:read` authorization. Researcher and
admin roles have it; viewer does not. Unknown catalogue paths/methods stay denied.
The existing request middleware resolves the current identity before dispatch.

Construct `CatalogueService(resolver=FrozenCatalogueResolver(store=...,
policy_resolver=..., registrations=...))` with an explicit isolated C09 store.
The trusted resolver returns `CataloguePolicy(revision, dataset_eligible,
scientific_eligible)` freshly on every invocation. The policy revision must change
with effective dataset/scientific membership decisions. Callbacks keep their
existing literal-True semantics. Public inputs cannot supply roles, policies,
callbacks, access bindings or permission revisions.

Effective bindings hash the authenticated subject and current account/permission
attributes. Cursor revisions combine the trusted policy revision and explicit
C09 lifecycle revision. Even unrelated lifecycle changes conservatively invalidate
old cursors. Access to historical snapshots still uses current local policy.
No propagation of changes from a disconnected legacy system is implied.

## Dependency registration

The trusted operator helper `register_scientific_snapshot(store=...,
snapshot_id=..., registration_id=...)` verifies one existing scientific index and
registers retention references for that exact index and each distinct bound child.
The resolver accepts only explicitly registered indexes and verifies all reference
bindings and withdrawals on each call. Public routes and tools cannot register,
promote, revoke, hold, remove references, import or approve anything.

Registration is idempotent. On partial failure, earlier pins remain conservative
retention protection. Retrying the same registration resumes safely. An operator
must reconcile an abandoned partial registration before explicitly releasing
its references; automatic rollback could remove another retry's protection.
Pinned snapshots remain subject to current revocation. C09 cleanup cannot retire
referenced dependencies. This registration does not copy missing source objects
or rewrite approved transfer, input hash, publication or scientific eligibility
bindings. Actual imports need their existing separate authority and validation.

## Public requests and operations

Every request carries an explicit `snapshot_id` and C08 `scope`. Strict public
models in schema/catalogue_service.py reject extra fields and unsafe JSON numbers.
The service injects authorization fields into the existing C08 internal models.

| POST endpoint | Typed tool | Behavior |
| --- | --- | --- |
| /catalogue/overview | catalogue.overview | Five permitted roots as a C08 listing |
| /catalogue/list | catalogue.list | Complete permitted inventory, filters, search and paging |
| /catalogue/open | catalogue.open | One C08 node; optional include_details returns node plus verified source/scientific inspection |
| /catalogue/coverage | catalogue.coverage | Fixed c13.coverage delegation with explicit object and parameters |
| /catalogue/query | catalogue.query | Allowlisted versioned C13 operation over one explicit input |
| /catalogue/relationships | catalogue.relationships | Qualified relationship listing, optionally linked to an explicit permitted object |
| /catalogue/analysis/get-published | analysis.get_published | Frozen published table with exact publication scope and complete result receipt |

Listings default to 100 records and cap at 500. They preserve applied scope,
deterministic order, exact matching canonical-object count, returned count,
cursor, preview truncation, source completeness, query completion and availability.
Unknown/unavailable source results retain C08/C10–C13 qualification and totals;
they never become known zero. Descriptive workflows cannot execute experiments.
Published operational results never imply independent approval or endorsement.

Name, canonical identity and logical path search use the complete permitted view
before filtering, sorting and paging. English, Japanese and canonical-ID ancestry
paths support slash-separated queries. Paths never interpret a filesystem path.
Search under a parent includes its descendants; an ordinary parent listing returns
direct children. Related IDs are pruned to the permitted view. Incomplete/cyclic
ancestry fails closed. Relevance/documentary ranks never determine membership.

Cursor reuse requires the same snapshot, scope, filters, parent/link context,
ordering, page size, subject and current revision. Supply the original public
payload plus next_cursor on the next call; response.request includes server-owned
context that must not be copied into a public payload. C08 cursors are context
bindings, not authorization credentials. Current authorization always runs again.

Query supports c13.table/inventory/coverage/quality/operation at c13-v1 only.
Source operations remain the fixed validated native C10–C12 operations. Full
eligible populations determine aggregates and result hashes before preview limits.
Response snapshot, scope and operation/version bindings are verified. There is no
SQL, model, administrative, planning, synthesis or experiment capability.

## Errors, workers and caches

HTTP and typed tools share the same request validation and service executor.
Errors use `{error: {code, message}}`: authentication_required (401), access_denied
(403), not_found (404), invalid_cursor (409), invalid_request (422), and
catalogue_disabled/catalogue_unavailable (503). Missing and denied identities have
the same non-disclosing outcome. Frozen byte/semantic corruption returns 503;
malformed operation parameters return 422. Internal paths and exception text stay
out of responses. Catalogue auth responses use the same sanitized error shape;
legacy auth errors keep their existing form. HTTP responses retain no-store.

Routes offload the entire synchronous invocation, including identity provider,
policy/store reads, verification, decoding, queries and JSON serialization. An
explicit AnyIO cancellation checkpoint follows worker completion. Native task
cancellation cannot terminate a worker already executing; the worker still closes
its resources. Independent requests can proceed while a catalogue worker blocks.
The cache lock never covers backend reads or full materialization.

Actual frozen backends disable view/response caching and verify bytes/access on
every call. A trusted immutable backend may explicitly opt into bounded in-memory
views, with fresh resolver/access validation on every page. Base keys bind token,
subject, policy/lifecycle revision, snapshot and full scope; selected-view keys
also bind the full query context. Returned values cannot mutate cached nodes.
The legacy VerifiedCatalogueCache/catalogue_revision discovery is never used.

## Capacity, verification and rollback

The service bounds a complete navigation view at 150,000 nodes and ancestry at
128 levels. Exceeding the bound returns unavailable, never a truncated inventory.
C13 retains its separate 4,000-dataset-binding and source byte/row bounds. An
explicit test-only C08 backend proves authenticated service/API/tool behavior for
100,000 canonical datasets; it does not certify a 100,000-dataset C13 registry,
live IAM, production latency, memory capacity or throughput.

Acceptance covers 200 real service pages, late documentary ranks 26/502/100,000,
exact counts and input receipts despite small previews, permissions/revocation,
interleaved subjects, paths, cursor changes, snapshot rollover, resource offload,
and actual frozen C10–C13 parity/corruption/dependency retention. Final commands,
results, resource observations, hashes and remaining gates are in the C14 handoff
and evidence directory. Disable the flag to roll back exposure; preserve sealed
snapshots, dependency references and scientific evidence. C15/C16 and later stages
own UI adoption; live provider, transfer and cloud work retain separate gates.
