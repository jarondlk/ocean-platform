# C12 independent input and adapter review

Date: 2026-10-16 JST. Delegate: `c12_inputs`.

Verdict: no unresolved blocking findings in the reviewed frozen input and
adapter paths. This is a code and isolated synthetic-fixture review, not an
independent scientific review or authorization of a real source export.

## Reviewed boundaries

- `ingestion/edna_catalogue_inputs.py`: exact schemas and primitive types,
  source-owned hashes and identifiers, provider/project ownership, relational
  keys, one-to-one classifications, shared classification/review-lineage rules,
  date precision, taxonomy interpretation, concentration states, declared
  method availability, immutable C09 registrations and source-generation checks.
- `orchestration/frozen_edna_catalogue.py`: scientific versus raw populations,
  correlated method/taxon/protocol predicates, denominators, current access,
  detached callback metadata, snapshot-wide resource bounds and browser output
  precision. The shared selector and canonical service were inspected as
  semantic references.

## Findings resolved during implementation

1. **Legacy canonical availability.** Canonical assay availability JSON can be
   null, while actual active detection rows independently establish method
   availability in the canonical service. The loader now preserves null and
   empty JSON without inventing available empty files. The adapter combines
   actual active detection evidence with explicit source declarations. Only an
   explicit declared row count of zero supports an available-empty claim.
2. **Specific descriptors hiding mixed raw data.** The input validator now
   rejects a specific method or classification descriptor contradicted by
   retained rows or source-backed method declarations. Conservative mixed
   descriptors remain valid for smaller filtered or empty fixture populations.
3. **Callback ordering and cumulative decode bounds.** The adapter now
   validates all dataset identities and actual decoded sizes before invoking
   any dataset access callback. Each loader receives the remaining snapshot
   decode allowance. Footer and row bounds are checked before decoding; actual
   Arrow buffer bounds are checked after decoding. Adversarial tests cover both
   stages without allocating large buffers.
4. **Exact integer browser output.** Canonical Parquet can retain nonnegative
   int64 read counts beyond the C08 exact browser integer range. The adapter
   returns a qualified unavailable result for an output containing such a value
   rather than rounding or failing with an unqualified serialization error.
   Source int64 bytes and values remain exact. This check also covers nested
   method counts inside count responses.

## Independent adversarial checks

`tests/test_edna_catalogue_adversarial.py` contains 27 cases. They verify that:

- A taxon present only in a nontarget sibling cannot qualify an eligible target
  population, including when the caller leaves the assignment method implicit.
- Default eligible tables and summaries contain only the two supported target
  methods; alternative methods remain separate.
- Null/empty legacy availability can support eligible method queries through
  actual detections, but never creates an available-empty declaration.
- Two different assays cannot jointly satisfy one requested protocol or lend
  complete-protocol eligibility to an incomplete assay.
- Current access requires literal `True` for every operation, including
  frequency; a later denial overrides a previously successful archived query.
- A callback cannot mutate the detached metadata to relabel frozen records.
- Complete snapshot footer and actual decode bounds precede callbacks, and
  remaining actual capacity reaches each dataset decoder.
- Exact int64 reads at `2**53` and int64 maximum survive input loading while
  unsafe table/count/summary outputs return typed unavailability.
- Read, concentration and frequency outputs declare `reads`, `copies/mL` and
  `proportion` units.

## Verification executed by this delegate

```text
.venv/bin/ruff check ingestion/edna_catalogue_inputs.py tests/test_edna_catalogue_inputs.py tests/test_edna_catalogue_adversarial.py
All checks passed!

.venv/bin/python -m pytest tests/test_edna_catalogue_contract.py tests/test_edna_catalogue_inputs.py tests/test_edna_catalogue_adversarial.py -q --tb=short
267 passed in 2.37s
```

The combined run consists of 46 contract, 194 frozen input and 27 independent
adapter adversarial cases. Real PostgreSQL parity, the full backend suite and
hosted gates belong to the parent delivery verification; this delegate does not
claim those executions.

## Remaining explicit limits

- Input hashes bind supplied frozen bytes and retained provenance; they do not
  authenticate the scientific truth of source classifications or reviewer
  identity. A current trusted policy still grants dataset access/eligibility.
- Resource limits bound canonical row counts, encoded bytes and decoded Arrow
  buffers. They are not a process resident-memory or performance guarantee.
- Absent classifications use an explicit frozen qualification object rather
  than a fabricated zero-row classification table. C09 permits one schema
  version per role in a source registration, so a registration mixing this
  state with retained classification Parquet fails explicitly and requires
  separate registration ownership; it is never silently relabeled.
- Exact time filtering on coarse or unresolved canonical dates remains
  unavailable where the shared policy cannot establish the predicate. Raw date
  labels and their precision stay visible.
- Empty filtered results and zero positive reads do not establish ecological
  absence. Source occurrences are not resolved physical samples; assignment
  alternatives and sequence reads are not independent organism observations.
- No provider, model, production store, cloud service, source acquisition,
  publication or scientific regeneration was invoked by this review.
