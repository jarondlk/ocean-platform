# COP17 ordinary sample search restored

Status: deployed and verified on `cop17-demo`, revision `ocean-cop17-demo-00010-dq6`.
Runtime source `f7d033ffcdf980180eec12b7f51557f3c34e25c8`, API-only build `1ebb1c55-96a5-4f4d-88fd-5760acef2765`.
The accompanying receipt is `COP17_DEMO_SAMPLE_SEARCH_RECEIPT_2026-10-24.json`.

## Problem and correction

The geographic handler previously interpreted any mention of “Bay” or “湾” as
geographic intent, so an ordinary Otsuchi Bay sample request was intercepted
before retrieval and displayed “Exact count needs clarification.” Broad “one”
and “where” tests could also confuse an individual sample with collective coverage.
The handler now recognizes a requested count/list of areas or an explicit
collective geographic relationship. Mere place mentions and individual sample
lookups proceed through normal evidence retrieval and the real model. Recognized
geographic questions retain their source, filter, publication and scope guards;
unsupported geographic restrictions do not silently broaden the cohort.

The original question's names and ranks were correct in the initial routing
release, but one live response added an unsupported, unrequested read count.
The final source adds generic eDNA answer instructions to provide the requested
names/ranks from one sample and method, omit unsolicited quantities, and
distinguish source-row values from verified full-label totals when quantities
are explicitly requested. It does not hardcode an Otsuchi answer or taxa.
These prompt bounds reduce the observed failure; a successful rehearsal is not
a guarantee that a language model can never make another unsupported claim.

## Replication

1. Open https://demo.oceaninfobio.com/chat and sign in with an invited account.
2. Select **Free-text search**. Keep ANEMONE eDNA enabled and clear restrictive
   sample/project/date/protocol filters. The default free-text sources are suitable;
   the fixed advanced analysis must not be selected.
3. Ask the professor's exact question:

   > Find one ANEMONE eDNA sample from Otsuchi Bay in 2020 and list five fish taxa detected in it. Distinguish species-level and genus-level identifications, and cite the source.

4. Confirm an **Answered** response using the model, one recorded sample/date,
   five supported fish labels, recorded species/genus ranks and a source citation.
   Wording and the choice of five supported examples can vary. They are examples,
   not the complete community, species-richness estimate or fish abundance.
5. Open the source citation, then its authenticated provenance link. Compare
   the recorded sample, assignment method and source-file trace.
6. Recheck “How many sampling locations are available in ANEMONE eDNA?”,
   “How many named areas are available?” and “Are all the sampling data from
   around the same area?”. The first still reports **216 distinct recorded
   coordinate positions**; named-area membership remains unestablished.
   Japanese geographic questions and both advanced examples remain separate
   acceptance cases.

## Reference source and scientific limits

The retained source contains sample `11b44f8f51558719453f222a15bff316111c78b8f29e864235f533aa6749af80` with provider
label `2020KibanSRUN01__20200817T0400-UTO-OtsuchiBay__MiFish`, collection date **2020-08-17**,
assay `cb9ab028b14e7875ad94bd7d014c208e6d06ea612dcc47db4b94ea065d8de05b` and method `qcauto_95pct_3nn_target`.
The corresponding source citation is `edna_cb9ab028b14e7875ad94bd7d014c208e6d06ea612dcc47db4b94ea065d8de05b_qcauto_95pct_3nn_target`.

“OtsuchiBay” is present in the **provider's sample label**. The structured bay
field is null, so this is a labelled individual record, not independent proof
of curated bay boundaries or membership. Coordinates are provider-grid values
with `provider_grid_unconfirmed` precision; control classification is unknown.
These limits remain consistent with the geographic answer's unknown named-area count.

A verified reference set from the same 3NN output is:

| Fish label | Recorded identification level |
| --- | --- |
| Engraulis japonicus | Species |
| Hexagrammos otakii | Species |
| Seriola quinqueradiata | Species |
| Scomber | Genus |
| Thunnus | Genus |

The method has 57 assignment rows. Repeated assigned labels are not distinct
organisms or independent taxa. The retained ordinary QCauto output assigns
`Hexagrammos` at genus level; it must not be merged with the 3NN species-level
`Hexagrammos otakii` claim. Source-row read values and full same-method label
sums differ where a label has multiple rows. The canonical audit verified the
underlying rows and retrieval-set hash without changing scientific data.

This record uses **NextSeq 500 / 12S rRNA**, as supplied by the source. The
advanced buttons remain fixed to the published **Miyagi 2020–2023 / 3NN /
MiSeq paired-end12S rRNA** setup. Free-text record exploration must not force
that MiSeq protocol onto this NextSeq record.

## Verification boundaries

- Backend suite: **1,637 passed**, 122 optional integration skips. Focused
  routing/answer-prompt checks: **167 passed**. Synthetic API tests use controlled
  retrieval/model fixtures to prove dispatch and prompt/evidence handling.
- Independent read-only source audit: verified the retained original sample,
  source label/date, ranks, canonical method rows, source manifest hash and
  published retrieval detection-set hash. This is real scientific evidence,
  not the synthetic API fixture.
- Accepted image: container runtime/authentication and schema/backup/restore
  gates passed. Reviewed scan has zero CRITICAL and zero language-package
  findings; inherited OS findings remain in the receipt.
- Restricted demo QA job `ocean-cop17-sample-routing-qa-kjlq7`: independent canonical SQL still
  reports 216 coordinate positions, historical receipts remain usable and the
  geography guards/reuse checks pass. Scientific rows and users were not changed.
  The completed job definition is sealed without secret/Cloud SQL references.
- Actual signed-in final browser acceptance is separate from all of the above:
  10 recorded cases passed, including 3 repetition(s)
  of the exact professor question. Per-case evidence and response hashes are in
  the receipt; private full answers remain in the operations directory.

- `original-exact-default`: answered, model invoked=True.
- `original-exact-edna-only`: answered, model invoked=True.
- `japanese-sample-search`: answered, model invoked=True.
- `location-count`: answered, model invoked=False.
- `named-area-count`: answered, model invoked=False.
- `geographic-extent`: answered, model invoked=False.
- `japanese-geography`: answered, model invoked=False.
- `fish-frequency`: answered, model invoked=False.
- `fish-sst`: answered, model invoked=False.
- `original-exact-after-advanced`: answered, model invoked=True.

The frontend, production service/traffic, scientific snapshot, IAM and overhaul
checkout remain outside this API-only correction. Historical location/geography
releases remain documented in the main runbook. Existing latency measurements
are observations, not a promise that every free-text model request takes under
10 seconds.
