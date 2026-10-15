# C11 independent source review and reference acceptance

Date: 2026-10-15 JST. Reviewer: `/root/c11_acceptance`.
Outcome: **No blocking findings remain in the reviewed local implementation.**

The reviewer authored `tests/test_frozen_sst_catalogue.py` and this report, and
read the adapter, immutable input loader/exporter, source metadata and synthetic
fixtures. Application fixes were made by the owning root/input agents. Final
source hashes, full-suite results and hosted delivery belong to the root receipt.

## Independent acceptance

The focused command `.venv/bin/python -m pytest
tests/test_frozen_sst_catalogue.py -q --tb=short` passed **73 tests**, with zero
failures/skips and one existing Starlette/httpx deprecation warning. It ran with
explicit test authentication settings, disabled PostgreSQL tests and unused
loopback database/model URLs. Ruff check and formatting passed.

- A 1,205-row frozen population is paged completely without duplicate identities.
  Preview sizes 1, 25, 100 and 500 preserve total rows and content hashes. Exact
  count/summary calculations independently expect 1,202 valid nonnull values,
  one measured zero, one valid missing value, one invalid observation and one
  excluded observation. Retained tables preserve all quality states.
- The explicit daily calendar spans 1,206 days, including leap day. Coverage
  independently expects four missing usable days: the retained leap-day gap,
  null value, invalid observation and excluded observation. No sampling contract,
  partial inputs, spatial subsets and requests extending beyond the contract
  yield unknown expected coverage instead of fabricated gaps.
- Final/interim products remain separate even when interim contains a value on
  the final product's missing day. Multiple product input IDs are rejected.
  Celsius and Kelvin fixtures retain their actual units and values.
- Regional means cannot recreate grid points or answer wider/different regions.
  Retained grid observations support exact subset and zero-width point filters;
  those filters do not imply complete area sampling. Actual UTC/Tokyo intervals
  and offset-bearing timestamps are compared without inventing hourly precision
  from day labels. A partial-day request against a day summary is unavailable.
- Independent legacy parity uses only the existing synthetic 2020–2023 regional
  period fixture and pure `daily_rows` projection. Removing 2021-02-20 produces
  1,460 retained observations, 1,461 expected days, exactly that missing date,
  and the same reference mean/minimum/maximum. The old `date_jst` label does not
  change the fixture's actual UTC basis. No real publication function is called.
- All six dataset sections, the Data/SST/product/collection/dataset hierarchy,
  Statistics/Metadata links to the same canonical dataset, late inventory pages,
  current denied-link removal and page-independent dataset counts are checked.
  Known empty metadata remains discoverable by its dataset ID; unknown and
  unavailable product inputs remain distinguishable from measured zero.
- Old sealed results reopen identically after a second publication generation.
  Store revocation, changed current access, scientific eligibility and stale
  access bindings override previously read historical bytes. A truthy value
  other than literal `True` is denied; policy mutation cannot alter frozen data.
  Corrupted bytes, unsupported C09 example SST inputs, scoped captures and
  malformed request parameters fail explicitly without a live fallback.
- An explicit C09 local opaque-byte copy reproduces SST values and content hashes
  after source revocation. It retains origin information, does not promote latest,
  and remains subject to the destination's current access/revocation checks.
- Cross-dataset table/dataset identity collisions and collections shared across
  incompatible products fail through both query and listing, including when
  current policy denies the other dataset. Cumulative row and footer-byte limits
  reject before scientific dataset loading. A separate test uses actual Arrow
  byte sizes exceeding plain-Parquet footer accounting to exercise the cumulative
  post-decode bound without constructing a large payload or mocking table sizes.

## Reviewed implementation boundaries

The new SST model owns product/version/generation, spatial support and actual
resolution basis, calendar/precision, unit, quality/uncertainty policies and
sampling contracts without extending C10's CTD/metagenome models. Immutable
objects bind exact metadata/table bytes to C09 source and operation generations.
The input loader verifies ownership, declared object membership, primitive
Parquet schema, hashes, quality states, observation identities and retained
precision. Plain Parquet encodings and cumulative decode/row limits bound this
local contract; no production throughput or process-memory bound is inferred.

The adapter reuses C08 listing/cursor transport through the C10 base class while
replacing every scientific loading, membership, node and query hook. It loads
verified snapshot bytes and invokes the current detached whole-dataset eligibility
callback on every request. Aggregation and coverage run over the complete matching
population before result pagination. Inventory metadata and observation counts
remain separate; cross-links do not add dataset membership.

Review confirmed C09 `CapturedSource.__post_init__` already revalidates/detaches
returned object descriptors and protects its copied byte mapping. An initial
export-detachment concern therefore required no application change.

## Findings resolved during implementation review

1. Coverage initially clipped an out-of-contract request to a known empty
   reference calendar. It now reports expected coverage as unknown for requests
   wholly or partly outside the declared sampling interval. Three independent
   regression cases cover past, leading-overrun and trailing-overrun scopes.
2. Dataset-ID selection initially removed known empty datasets because there
   were no observation rows. Metadata inventory now retains the selected dataset;
   its observation count remains a distinct known zero.
3. Incomplete retained observations initially allowed a filtered empty result to
   imply known absent dataset membership. Scoped inventory now fails explicitly
   when incomplete inputs cannot establish absence.
4. A dataset-ID mismatch is applied before unrelated geographic validation, so an
   empty dataset intersection does not claim a different product's incompatibility.
5. Root source review found that canonical identity collisions were validated
   while constructing inventory nodes but could otherwise pass a query. The
   loader now registers product, collection, dataset, table, metadata artifact,
   generated reference and reserved identities before eligibility filtering.
   Eight independent regressions cover both collision types, entry paths and
   current eligibility outcomes.

## Deliberate limits

This is local software/synthetic acceptance. Trusted callers supply current
whole-dataset authorization and scientific eligibility; metadata does not grant
its own approval. Authenticated service/row-level access, real source acquisition,
publication promotion, scientific artifact regeneration, production import,
provider calls, UI integration and GCP deployment are outside this review. The
synthetic copy proves local contract parity only. The reviewer accessed no
existing database, cloud service, scientific store or mutable publication pointer.
