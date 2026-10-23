# COP17 sampling-location counts: findings and implementation plan

Status: implemented and verified on the COP17 demo; see
`COP17_DEMO_LOCATION_COUNTS_RECEIPT_2026-10-23.json`.

Original investigation (October 23, 2026 JST): no application code, database,
permissions, running service or production/overhaul checkout was changed by
the initial investigation. The then-current demo was revision
`ocean-cop17-demo-00005-5g5`.

## Live findings

All questions used Free-text search with no source filters or published-analysis
selection. These are observations from the deployed demo, not mocked tests.

| Question | Enabled sources | Observed behavior |
| --- | --- | --- |
| `how many sampling area available` | ANEMONE + SST | Model answered with three coordinate positions among retrieved examples; its closing caveat said a complete database count was unavailable. This does not answer the catalogue-total question. |
| `How many sampling locations are available in ANEMONE eDNA?` | ANEMONE + SST | Abstained: unsupported exact-count wording; no model invocation. |
| `How many sampling areas are available?` | ANEMONE only | Same unsupported-count abstention. |
| `ANEMONEの採水地点はいくつありますか？` | ANEMONE only | Same abstention; the clarification body remains English. |

The existing exact-count implementation supports source occurrences, assays,
assignments, reads and provider namespaces. It has no geographic-location
metric. With multiple sources selected and no explicit eDNA term, its router
can bypass aggregation and fall through to ordinary retrieval. Adding words to
the accepted vocabulary alone would be incorrect: the existing SQL summary
does not count geographic positions.

## Metadata audit and the meaning of location

A read-only audit downloaded the complete active published retrieval artifact
from the isolated demo bucket, pinned to its object generation and verified
against the SHA-256 in the artifact-transfer receipt. It contains 6,996 evidence
documents for 3,498 distinct source-occurrence/sample IDs. Values for coordinates
and classification agree between each sample's two method documents.

- Whole catalogue: 3,174 source occurrences have valid coordinate pairs; 324
  lack them. There are **216 distinct stored coordinate pairs**.
- Excluding explicit controls: 3,155 occurrences remain, of which 3,154 have
  coordinates and one lacks coordinates. The distinct-pair count is still 216.
- Every coordinate-bearing occurrence is marked `provider_grid_unconfirmed`.
  Remaining classifications are `unknown`, not reviewed environmental samples.
- `provider_locus` is a laboratory/marker namespace such as MiFish; it must never
  be interpreted as a geographic location.

Thus 216 is a reproducible count of recorded coordinate positions in published
metadata. It is not a verified number of distinct physical sampling sites or
named sampling areas. A direct SQL comparison against the demo's active
canonical rows is still required during implementation acceptance.

Audit binding:

- Retrieval generation: `a01a472a74ea55ffbd2cee1e69822555af801a00dbcf8956414a942564011716`.
- Object generation: `1792595576770433`.
- SHA-256: `4d1d327f59efc5373ab0f6cf3ad7614faf39d720a7fc0147bacaf79418f20e94`.
- Source: `gs://data-infra-infobio-ocean-cop17/edna-cop17-snapshot/retrieval/objects/a01a472a74ea55ffbd2cee1e69822555af801a00dbcf8956414a942564011716/anemone_retrieval_documents.parquet`.

## Recommended COP17 scope

Support **distinct reported coordinate positions** in free-text search. State
that definition with the number whenever a visitor says sampling area, location
or site. Explicitly say that provider grid positions do not establish distinct
physical sites. Requests for verified physical sites or named areas should
explain that these identities are not yet curated, rather than substitute 216.

Recommended default: exclude explicitly classified controls and retain unknown
classifications, disclosing both choices. Never describe unknown records as
confirmed environmental samples. Respect explicit control/classification
filters; resolve conflicts instead of silently overriding them.

With the default two sources enabled, identify the count as ANEMONE coverage
and keep SST coverage separate. Satellite pixels, SST observation days and
study rectangles must not be added to field sampling positions. If ANEMONE is
unchecked, explain how to enable it. If the question explicitly asks for a
combined cross-source total, request clarification.

Suggested answer shape, after SQL verification:

> The demo's ANEMONE catalogue contains **216 distinct reported coordinate
> positions**, excluding explicitly classified controls. These are provider
> grid coordinates, so they do not establish 216 distinct physical sampling
> sites. The count includes records whose environmental/control classification
> is unknown; one non-control-status record lacks coordinates and is excluded.
> [Retained aggregate citation]

The first sentence must identify the source and scope. Put the definition,
missing-coordinate/classification counts, publication identity and citation
behind the existing details interface where appropriate. Provide deterministic
English and Japanese text. No new top-level button is needed.

## Implementation sequence

1. **Add a typed location-count route.** Extend
   `orchestration/edna_aggregation.py` with a distinct metric and bounded EN/JA
   aliases: sampling area(s), location(s), sampling site(s), 採水地点,
   採取地点 and 調査地点, with common count phrases such as how many, number of,
   いくつ, 何地点 and 何か所. Detect these requests even when SST is also
   selected and ANEMONE is not named. Unresolved place/date/taxon qualifiers
   must produce a useful clarification, never a total over a wider cohort or a
   numeric answer from a retrieval subset. Keep existing published-workflow
   routing and scientific constraints intact.
2. **Count active canonical rows with SQL.** Extend `api/edna_service.py` using
   the existing `_sample_conditions` predicates. Count distinct finite,
   in-range `(lat, lon)` pairs before assay/detection joins. Do not round,
   cluster, infer station names from sample IDs or count one location per
   assay/method. Preserve existing project/run/date/coordinate/taxon/method
   filters, and return coordinate exclusions, classification breakdown,
   precision status and the explicit location-definition/control policy.
   Repeated sampling dates at the same recorded position count once.
3. **Retain exact evidence and render it directly.** Extend
   `ingestion/edna_aggregate.py`, `api/main.py` and the deterministic renderer.
   Reuse repeatable-read transactions, publication consistency checks, input
   fingerprints, immutable aggregate storage and citation/provenance support.
   Version the added metric contract and continue accepting historical v1
   aggregate receipts in `load_aggregate`; old citations must remain readable.
   Generate the answer from verified aggregate values without model counting.
   No scientific schema migration or new scientific publication is expected.
4. **Validate and release only the demo.** Run the tests below and the existing
   COP17 regression suite, then build/scan the changed API and frontend if
   frontend localization/types require it. Release to `ocean-cop17-demo`, verify
   signed-in EN/JA queries and provenance, and update its runbook/receipt.
   Production and `overhaul` remain outside this change.

## Required acceptance checks

- All four live questions above return the same defined position count for the
  same cohort, with an aggregate citation and `model_invoked=false`.
- Repeated dates, multiple assays and both assignment methods do not inflate
  a position count; no arbitrary coordinate rounding merges positions.
- Missing, non-finite and out-of-range coordinates are excluded and reported;
  known controls and unknown classifications follow the disclosed policy.
- The metadata reference count of 216 matches an independent SQL query over
  the unchanged demo snapshot; filtered subsets reconcile separately.
- All sources selected, ANEMONE only and ANEMONE disabled behave explicitly;
  SST pixels/days are never treated as field sampling locations.
- Named-area, physical-site and unsupported place/time/taxon requests clarify
  appropriately. “Only reviewed environmental samples” can yield an empty
  classified cohort without claiming no sampling took place.
- Existing counts and fish/SST presets retain their results and guards.
  Old/new aggregate citations load, tampering/stale publication fails closed,
  and unauthenticated access remains rejected.

## Later work

A defensible count of physical stations or named sampling areas needs reviewed
site identities or area definitions and a mapping from source occurrences to
those identities. Keep that work separate from the COP17 coordinate-coverage
answer. Do not relabel provider grid points as physical stations to satisfy a
natural-language question.
