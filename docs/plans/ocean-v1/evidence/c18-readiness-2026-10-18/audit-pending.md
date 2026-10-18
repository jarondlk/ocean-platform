# C18 formal prerequisite and interface audit

Date: 2026-10-18 JST. Branch: overhaul. C18 remains unselected in this audit.
Only this readiness evidence directory was written. No application code, tests,
services, accounts, databases, legacy/P00 storage or cloud resources were changed.

## Readiness result and immutable sources

All98 formal prerequisite entries reconcile: P0036, C1525, C1618 and C1719.
Their original source maps and SHA256 aggregates are checked, and every current
file equals its original or an explicitly accepted later source. The audit keeps
the complete per-entry receipt chain rather than replacing original hashes.

- P00 has13 later-superseded entries: four C07 export/admin changes and nine C15
  shell/preview/documentation changes. The README subsequently changes in C16.
- C15 has seven superseded entries through C16; auth/main/config subsequently
  change in C17. The remaining18 original entries match.
- C16 has three accepted C17 auth/main/config supersessions; its other15 original
  entries match. Its catalogue implementation, client and tests are unchanged.
- All19 C17 accepted files exactly match committed source
  `39bb811d1053c9dfb4b700f8524162800092aa44`, aggregate
  `1a1f3d3ff413c8ba71da1e9a9dbc67823bde23801e5ad1385ae9fe57676d570f`.
  The immutable local verification receipt remains
  `a59bba711e76ad62dd952135e2db374235d3fa7cfdb01cd2cd2d3a76983da3d7`.

The preservation baseline pins11 original/current accepted receipts,683 earlier
evidence files,30 unrelated files,7 scientific artifacts,2 serving files and106
legacy frontend files. All match. The driver also records every currently tracked
earlier evidence file, including committed C17 evidence, without rewriting it.

`verification-pending-corrected.json` is the current pending observation. The
first `verification-pending.json` remains historical: its unique-path count
included supporting C07-only paths, although all98 formal entries and preservation
checks passed. The corrected driver counts only formal prerequisite paths and
verifies the now-committed C17 source directly. No original observation was edited.

## Actual prerequisite contracts

Read the C18 specification, P00/C15/C16/C17 handoffs, accepted P00 UX brief,
C15/C16/C17 integration contracts, current source and separate-site plan.

P00 supplies the accepted research-first layout, private investigation navigation,
separate chats, explicit context versus restriction language, resizable Workspace,
mobile tabs, bilingual themes and activity/evidence patterns. Its local simulation
is UX direction only. Its saved synthetic and admin namespaces must remain separate.

C15 supplies trusted authenticated runtime identity, permission/revision-bound
capabilities, fail-closed mode/bootstrap, shell/dialog/tabs/resizer primitives and
presentation-only storage. Production service failures cannot activate fixtures.

C16 supplies the working catalogue client/browser, explicit eligible snapshot
discovery, embedded supplied scientific scope and pinned snapshot, current-access
clearing and an explicit canonical selection event. Opening, searching and filtering
do not attach data, pin restrictions or change an investigation.

C17 supplies all14 required private persistence operations: investigation
create/list/get/rename/archive, conversation create/list/get/rename, context
get/change, refresh and prepared-operation get/retry. Current context includes
immutable revision/snapshot/hash, canonical C08 scope, distinct attachments/pins
and fresh per-reference resolution. Refresh branches from an exact predecessor,
retains unresolved selections and preserves original evidence; no narrative is
copied. Mutations use explicit idempotency and expected metadata/context versions.

No missing C17 HTTP operation blocks C18. C17's trusted `load_for_submission`
stays internal for C20. It must not become a client-authoritative run admission
claim. Conversation history remains explicitly unavailable until C20/C21.

## Minimal complete C18 implementation boundary

1. Add a strict C17 client and pure Research navigation/state model. Restore
   investigation/conversation/Workspace selection through reload and history.
   Keep account-scoped in-memory drafts through ordinary navigation; clear all
   protected state on account/access changes. Never infer identity from storage.
2. Reuse the existing shell and accepted P00 layout for Chat and Workspace tabs:
   Context, Results, Experiments and Evidence. Integrate C16 using current scope
   and pinned snapshot. Its callback stages a selection; separate Attach and
   Pin actions perform exact C17 mutations. Display scope, attachments, pins,
   snapshot and revision near the composer. Scope edits use canonical C08 values.
3. Revalidate shared context on conversation switches, focus and bounded polling.
   Preserve drafts and submitted bindings; surface stale-version conflicts and
   unresolved references explicitly. Refresh requires an explicit eligible target
   and creates a new branch, exposing unresolved selections before use.
4. Define typed submit/status-event polling/cancel/clarify/continue methods and
   activity/result/evidence presentation. Exercise those controls only through an
   explicitly injected local/test development fixture with visible labels. The
   production runtime must never select that fixture from URL/storage or failure.
   Until C20 integrates, real execution remains unavailable with an explanation.
5. Add guarded Research capability activation and mount the new interface.
   Current runtime configuration explicitly rejects Research-ready state, so this
   is a C18 integration change. Require actual configured C17/C14/C16 wiring and
   v1 identity/site agreement; require both chat:use and data:read. This activates
   persistent context management, not later production run execution.

C20 owns durable run APIs, verified submission binding, history/events and concrete
live transport. C21 owns actual generated answers, retained receipts/artifact
reopening and exports. C18 defines presentation and navigation contracts for
those integrations. Experiment execution and approval remain unavailable until
their owning components integrate. Do not fabricate scientific authority,
progress percentages or private model reasoning.

Uncertain C17 mutations can replay their exact request/idempotency key; the client
does not need to extract an operation UUID from human-readable error text. An
optional future structured error field would be ergonomic, not a readiness gate.

## Verification to reuse and final gate

C15 and C16 exact-source hosted deliveries are already successful and recorded in
the pending JSON. Current C17 local evidence reports4187 backend passes,187 gated
PostgreSQL skips and85.08% coverage;60 actual disposable PostgreSQL cases passed
on the earlier bound source, with later API/service supersessions documented.
The final C17 hosted run must verify all60 PostgreSQL cases against source39bb811.
Completed suites were not repeated for this read-only audit.

**Remaining readiness gates:** C17 exact-source hosted CI acceptance and its
separate committed delivery. Until both are complete this audit does not mark
C18 ready or select/start implementation. After root provides the full delivery
SHA, run:

```sh
.venv/bin/python docs/plans/ocean-v1/evidence/c18-readiness-2026-10-18/verify_readiness.py \
  --c17-source 39bb811d1053c9dfb4b700f8524162800092aa44 \
  --c17-delivery FULL_DELIVERY_SHA --output verification.json
```

The driver requires source/delivery ancestry, exact committed local/delivery
receipts, unchanged19-source map and source-bound hosted success. Explicit output
creation refuses to overwrite any existing observation. The root agent owns
selection and subsequent STATUS/spec/handoff changes.

C18 acceptance must exercise actual C17 persistence, explicit mutations, concurrent
chat updates, refresh/unresolved branches, account clearing and history restoration;
all six fixture run controls and frozen bindings; citation/evidence presentation;
and keyboard/mobile/localized/theme behavior. Production OIDC enrollment, approved
real data/scientific authority, production capacity/retention/migrations and concrete
independent cloud target authorization remain external gates. Local implementation
does not require or authorize those operations or any legacy/main deployment.
