# v0.6.0 — Chat source settings and evidence scope

Prepared 2026-10-01 JST against `gcp-dev` commit `fecfa7d` and the
[readiness audit](V0.6.0_READINESS_AUDIT_2026-10-01.md).

**Status: adopted; local implementation and local verification complete; live release gates pending.**
The user authorized implementation with the recommended issue #70 fixes and
per-account browser persistence. See [implementation and release gates](RELEASE_0.6.0_IMPLEMENTATION.md).
Merge, source release and production rollout have not begun.

## Intended behavior

A researcher can check or uncheck CTD, metagenome, satellite SST and ANEMONE
eDNA independently, refine each enabled source's filters on the chat page, and
see which settings and evidence actually produced the answer. An unchecked
source contributes no measurements or derived scientific results through
retrieval, linked evidence, analysis, reliability or exact catalogue answers.
The system records the applied scope with each interaction and retains its
existing citation/provenance checks and scientific limitations.

Example: select CTD and SST, restrict CTD to Onagawa station `s1` in 2024 and
SST to a separate date interval, and leave eDNA and metagenome unchecked.
CTD's bay/station settings affect only CTD. No metagenome correlation summary
or eDNA aggregate can enter that answer. Selecting a source makes its records
eligible; it does not guarantee they rank in the global top-K or contain enough
evidence to answer the question.

## Adopted release scope

| Included | Boundary |
| --- | --- |
| Independent source checkboxes | All 16 combinations of four sources, including none |
| Per-source filters | Fields grounded in current metadata and canonical filtering; matrix below |
| Robust settings contract | Typed/versioned scope, strict validation, legacy adapter and effective-settings reporting |
| Full evidence enforcement | PostgreSQL and local retrieval, linked evidence, supplementary context, analyses and aggregation |
| Clear chat controls | Source panels, selected-scope summary, explicit empty/error states, provider-supported generation controls |
| Remembered settings | Accepted: browser storage separately per account, with validated restore/reset behavior |
| Known chat defects | Accepted: include bounded fixes for tracked issue #70 cases, with manual claim-support acceptance |

Deferred: account synchronization across devices, presets/sharing, multi-turn
conversation history, automatic ingestion, new environmental classifications,
per-source ranking weights/quotas, CTD depth/variable slicing, metagenome
classifier/taxon slicing and scientific analysis recipe editing. These require
additional product or evidence contracts. Existing global retrieval/generation
controls remain available under Advanced settings.

The default selection is all four sources with no scientific filters. Raw
eDNA defaults to all recorded classifications. Environmental-only analyses
continue to exclude controls and unknowns through the existing eligibility
contract; user settings cannot override that scientific boundary.

## Source controls

| Source | v0.6.0 controls | Meaning and limits |
| --- | --- | --- |
| CTD | Enabled, bay, station, sample ID, document date range | Filters complete cast-summary documents; does not recompute a depth interval or remove individual measurements |
| Metagenome | Enabled, bay, station, sample ID, document date range | Filters whole sample summaries; existing document dates can use a CTD-associated date or the first day of a recorded month, not necessarily an exact sequencing/collection date |
| Satellite SST | Enabled, document date range, coordinate bounds | Filters daily documents by recorded point metadata; does not spatially clip the regional statistics. Documents currently have no bay/station/sample fields, so those controls are absent |
| ANEMONE eDNA | Enabled, provider, project, run, sample ID, assignment method, taxon, sample kind, control status, collection date range, coordinate bounds | Uses canonical membership and source metadata; assignment methods remain alternative interpretations of the same evidence |

Station is a small new request filter over an existing document column, with
matching local/SQL behavior. Other initial filters reuse supported semantics.
Do not manufacture SST bay membership or translate ANEMONE coordinates into
legacy study bays. Coordinate controls filter recorded document coordinates;
they do not establish exact physical sampling positions or spatial coverage.

Control status is a three-choice UI: All, Known controls, Known non-controls.
Unknown is not equivalent to known non-control. Sample kind exposes the
existing explicit categories, including unknown. Reject incompatible active
filters such as environmental sample kind plus known control status.

The eDNA saved-analysis binding is an advanced, explicit scope overlay. Show
its cohort, method constraints and current/historical status. It cannot enable
an unchecked source or silently replace other selected sources. Catalogue
grouping remains a separate exact-summary control; aggregate-only options must
never be silently discarded for ordinary retrieval.

## Settings and API contract

Introduce a versioned `evidence_scope` in `/chat` and `/retrieve`. The proposed
wire shape is:

```json
{
  "query": "Compare the available temperature evidence",
  "evidence_scope": {
    "version": 1,
    "sources": {
      "ctd": {"enabled": true, "filters": {"bay": "O", "station": "s1"}},
      "metagenome": {"enabled": false, "filters": {}},
      "remote_sensing": {"enabled": true, "filters": {"time_from": "2024-01-01"}},
      "edna_metabarcoding": {"enabled": false, "filters": {}}
    }
  },
  "k": 8,
  "expand_evidence": true,
  "inject_analysis": true,
  "inject_reliability": true
}
```

The new scope requires all four source entries, so omission cannot implicitly
enable a family. Each source has its own typed filter model. Keep global
ranking, context and generation controls separate. The UI can provide an
explicit “Apply dates to enabled sources” action by copying dates into those
source filters; there is no hidden global date/bay intersection or override.

Contract rules:

1. Normalize once into an immutable effective scope shared by every evidence
   path. Use strict source IDs, booleans, ranges, bounded strings and
   `extra="forbid"`. Reject unknown versions, families and unsupported fields.
2. Retain valid filters when a source is unchecked so rechecking restores them.
   Disabled filters contribute no constraints or evidence; structural/value
   validation still applies to submitted entries.
3. All sources unchecked is a valid state. Disable Ask with “Select at least
   one source.” A direct API request returns a recorded deterministic
   `no_sources_selected` abstention, with no retrieval, aggregation, embedding
   or generation call. `/retrieve` returns an empty result with that diagnostic.
4. A legacy request without `evidence_scope` passes through an adapter that
   preserves current `source_type` aliases, flat filters, eDNA-only inference,
   `top_k` alias and analysis-ID behavior. Validate source IDs; reject unknown
   keys rather than silently ignoring them. A request that mixes the new scope
   with legacy scientific-scope fields is rejected with a field-level error.
5. Empty legacy `source_type` retains its historical “all” meaning; it must not
   be confused with the new explicit all-disabled state.
6. Record requested and effective settings separately. Retain existing response
   `options` fields for compatibility and add the canonical evidence scope,
   answer mode and provider-effective controls. Old history remains readable.
   New snapshots must preserve the exact options used at submission even if
   the user edits the next question's controls while waiting.

Define a small authenticated chat-capabilities response, authorized by
`chat:use`, listing source/filter capabilities, defaults, provider-supported
generation fields and limits. It must not require viewer accounts to access
researcher-only Data endpoints. Use a server-owned registry/schema with generated
TypeScript types or a checked deterministic schema export; avoid independent
handwritten contracts. UI translations remain frontend presentation.

## Enforcement across the evidence paths

**Ranked retrieval:** compile the active document/publication constraints with
a parameterized union of enabled source predicates:
`(CTD AND CTD filters) OR (SST AND SST filters) ...`. Apply the same effective
scope before vector/FTS candidate limits and before local BM25/vector ranking.
Preserve normalized global weights, global top-K, deterministic fusion and
existing isolated branch transactions. No query text may re-enable a source.

**Linked evidence:** enforce the target source's own filters inside candidate
selection before the linked limit. A CTD primary hit may link to eligible SST
when SST is enabled; it may not link to unchecked metagenome. Retain a final
scope check before prompt construction. Include all metadata needed to evaluate
the filters, rather than dropping station/coordinates in intermediate rows.

**Analysis and reliability:** require every declared covered source to be
enabled and every contributing cohort to satisfy its own source filters. A
whole-cohort statistic cannot inherit a narrower scope from one featured row.
Omit unknown/unverifiable or mismatched scope with a stable reason; do not
recompute or relabel it through prose. Audit primary narrative dependencies and
derived artifacts as well as their family labels. Preserve ordinary provenance
metadata while excluding scientific measurements/results from disabled sources.

**Saved eDNA analyses:** resolve membership only for the eDNA branch; leave
other enabled source branches intact. Reject incompatible/stale bindings with
the existing controlled conflict behavior. Environmental-link context requires
both eDNA and the referenced environmental source to be enabled and in scope.
Analysis injection controls supplementary analysis; it cannot override sources.

**Exact summaries:** resolve their scope from the enabled eDNA entry and
compatible explicit aggregation options. Never answer from eDNA when it is
unchecked. An eDNA-specific count can intentionally use only eDNA while other
sources remain eligible; show that exact answer scope. A mixed-source count
request must not silently become a global eDNA summary. Exact catalogue
evidence is distinguishable from optional supplementary ecological analysis;
turning off analysis injection does not turn supported exact count questions
into model-generated totals. Taxon/method evidence supplementation follows
the same source boundary.

**Prompt, audit and history:** run one final eligibility check against the
actual supplied manifest. Diagnostics distinguish user-excluded sources,
eligible sources with no results, publication unavailable/pending, omitted
context and backend failure. Do not count intentionally disabled sources as
retrieval failures. Store source/filter scope, resolved analysis/aggregate
scope, actual citations and omission reasons with the answer.

## Chat interface and lifecycle

Replace the single-source dropdown with four expandable source panels. Each
has an enabled checkbox, relevant filters, active-filter summary and a
source-specific reset. Provide Select all, Clear selection and Reset all.
Unchecked panels retain their valid values but display them as inactive.
Keep filters readily visible; put ranking and generation knobs in Advanced.

Show the draft scope near the question and the server-applied scope beside
the answer. Explain that selected sources are eligible rather than guaranteed
to appear. Source availability is separate from selection: publication failure
does not change a checkbox or silently broaden a query. The response shows
why evidence was excluded or unavailable and whether the model ran.

Proposed persistence: validated browser storage keyed by the authenticated
application user UUID and a settings version, using the identity already
resolved by `AppShell`. Wait for identity and restoration before enabling Ask;
never briefly submit default all-source scope during hydration. Store settings
only, not question text, responses, authentication material or transient saved
analysis links. URL/deep-link overlays apply visibly to the current page and do
not overwrite remembered defaults automatically.

On account change, restore only that account's settings. Handle denied storage,
malformed values, obsolete versions and unavailable models. Invalid scientific
scope blocks submission until the user reviews/resets it; do not silently
replace it with all sources. A storage failure leaves a valid current-page
session usable with a concise unsaved-state indication. Reset writes valid
defaults; all-disabled selections remain all-disabled after reload.

Generation controls follow runtime capabilities. Vertex does not expose
ineffective repetition-penalty/context-window knobs. Legacy unsupported knobs
are explicitly reported as ineffective; new UI requests send only supported
fields. Preserve the existing effective output-token cap. Provide keyboard
operation, native checkbox labels, associated validation messages, mobile
layout and English/Japanese labels for new controls.

## Issue #70 work included in this candidate

- Separate exact record counting from scientific interpretation; support the
  known summary paraphrases and Japanese count request without inventing scope.
- Lead exact answers with the requested metric or unresolved physical-sample
  limitation. Explain environmental/unknown exclusions with correctly scoped
  citations; broader totals require separate evidence.
- For explicit taxon/method scope, supplement abbreviated assay prose with
  bounded, immutable canonical evidence. Prefer the existing exact aggregate
  machinery where it supports the claim; do not change an old document's text
  under an unchanged citation ID. Verify the rare-taxon result of one occurrence,
  one QCauto assignment and 122 reads against the frozen observed catalogue.
- Treat arrival/freshness as unavailable unless verified ingestion/provider
  publication records support it. Collection dates cannot establish arrival.
- Keep claims about controls, paired methods, abundance, calibration and absent
  records within the supplied scope. Repeated live questions and manual review
  are required; syntactically valid citations alone are insufficient.

These are bounded fixes to the tracked reproductions, not a general claim that
all scientific interpretation or Japanese answers are validated.

## Implementation sequence and review gates

| Step | Deliverable | Exit gate |
| --- | --- | --- |
| PR1 — Contract and ranked scope | Source/filter models, capabilities, legacy adapter, effective scope, station filter, SQL/local enforcement, empty selection | All 16 source combinations and scoped candidate selection pass in both backends; malformed/mixed requests fail explicitly; legacy callers retain tested behavior |
| PR2 — Remaining evidence paths | Linked selection, derived-context scope, saved-analysis membership, aggregate routing, supplied-manifest checks, diagnostics/history, provider-effective options | No disabled source enters any evidence path; narrowed contexts are omitted honestly; citations and historical interactions remain readable |
| PR3 — Known chat defects | Proposed issue #70 routing, response focus, canonical taxon evidence and freshness handling | All tracked deterministic cases pass; live/repeated claim-support matrix remains an explicit release gate |
| PR4 — Chat controls and persistence | Source panels, shared types, per-source forms, restore/reset/deep-link handling, provider-aware Advanced controls, translations | Keyboard/mobile/viewer/researcher/admin flows work; drafts and applied settings are distinct; account changes and corrupted storage cannot broaden scope silently |
| PR5 — Release candidate | Combined tests, authenticated QA, performance evidence, version metadata, release notes and operations checklist | All acceptance gates below pass against the exact candidate; unresolved defects have explicit disposition |

Implement in this order so the UI exposes only behavior the backend enforces.
Extract settings/scope modules and focused UI components as needed; keep broad
API/authentication rewrites outside the milestone. PR boundaries are review
units, not separate independently deployable feature promises. Bump versions
to `0.6.0` in the release-candidate step.

Under the proposed browser-persistence scope, no user-settings database table
or migration is expected. Query-time taxon evidence should reuse existing
retained evidence/publication facilities where semantically valid. If a new
evidence schema or artifact format is necessary, document it with an additive
compatibility/migration decision before proceeding. Do not assume a full corpus
reimport or embedding rebuild is needed for a filter/settings change.

## Acceptance matrix

| Area | Required cases |
| --- | --- |
| Source sets | Every combination; all-disabled causes no database retrieval/provider work; a question naming an unchecked source never enables it |
| Filters and ranking | Distinct source date intervals, CTD station, eDNA project/method/taxon, false/unknown controls, zero coordinates, missing metadata, invalid ranges, filtered candidates beyond an unfiltered top-K |
| Backend parity/failure | Same membership and stable ordering locally and on PostgreSQL 16; vector/FTS branch recovery and total-failure reporting remain intact |
| Supplemental evidence | Cross-source link targets obey their own filters; mixed-family and unknown-scope analyses omitted; saved-analysis conflicts, empty cohorts and environmental links tested |
| Exact evidence | eDNA disabled, narrowed cohort, mixed-source ambiguity, unsupported qualifiers, empty/missing tables, grouping, retained hashes/downloads and historical citation resolution |
| Provider controls | Vertex/Ollama capabilities, effective token cap, unavailable models, unsupported legacy fields and actual recorded generation config |
| Settings lifecycle | Reload/navigation, hydration, reset, all-disabled persistence, account switch, denied/malformed/obsolete storage and transient analysis links |
| UI/access | English/Japanese labels, keyboard/focus, narrow viewport, validation, applied-scope summary, viewer-safe capabilities, researcher/admin access and anonymous rejection |
| Known defects | All issue #70 reproductions, rare-taxon canonical support, freshness limits and repeated interpretation claim review |
| Operations | Full regression/coverage, PostgreSQL integration, lint, dependency/security checks, frontend tests/typecheck/build, provenance/history preservation and measured request cost/latency/memory |

Use compact cross-layer fixtures containing all four source families and
deliberately tempting excluded evidence. Tests must inspect the actual supplied
prompt/citation manifest and persisted effective scope, not just checkbox state
or a mocked list of retrieval arguments. Keep deterministic regressions in CI;
run bounded real-provider evaluation separately against the complete corpus.

## Release and deployment preparation

The engineering baseline currently passes; private cloud inventory still needs
renewed GCP authentication before rollout planning is executed. Read the actual
revision, images, schema, publication generations, resource limits and recent
errors at that time. Reuse the established manual GitHub review and GCP build/
deployment process; scheduling and automated deployment are separate work.

Prepare a candidate with no production traffic for serving QA. Isolate any
test writes/artifacts that could affect real history or publication; a zero-
traffic revision sharing production storage is not a data-isolated environment.
Record query plans and candidate latency/memory on realistic corpus size.
Bound provider calls and costs, and check the project's existing spending
controls before paid QA or extra capacity.

Take a fresh verified backup before any required schema/data publication
change. Record immutable images, exact source commit, paired artifacts and
compatible recovery path. A query-time-only change can reuse the corpus; an
artifact change requires explicit publication/history checks and a reviewed
recovery path. Preserve v0.5.0 historical citations and application records.
Source-release and production-deployment status must remain distinguishable.
Planning this release does not itself authorize production cutover.

## Choices awaiting feedback

1. **Issue #70:** recommendation is to include the known fixes in v0.6.0 as
   PR3, because the new taxon/filter controls expose the existing evidence gap.
   A settings-only milestone can omit PR3, but must retain those defects in
   release notes and must still fix any new scope-enforcement failure.
2. **Persistence:** recommendation is browser storage per account. Account
   synchronization would replace that persistence portion of PR4 with an
   authenticated settings API, additive application-metadata migration,
   validation/versioning and a policy for concurrent updates. Page-only
   settings would remove persistence work and its corresponding tests.

The user authorized implementation using these recommended defaults. The
implementation record tracks the completed changes and the remaining live
release checks. A small history-constraint migration (`20261001_0014`) is
required for the new abstention reasons; no corpus rebuild is required.
