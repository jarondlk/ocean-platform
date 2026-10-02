# v0.6.0 production browser QA — 2026-10-01 JST

Checked https://oceaninfobio.com/chat through the Codex in-app browser against the deployed security-amended v0.6.0 runtime. A fresh tab worked; the old localhost tab still failed browser focus initialization. Existing Google sign-in completed as the current admin/internal account. No source, deployment or IAM changes were made.

## Verified

- eDNA dropdowns have both assignment methods, provider `anemone`, project/run/sample choices and canonical taxa. Sample-kind choices reflect negative-control/unknown classifications; no environmental classification was invented. Metagenome bay/station/sample dropdowns also have live choices. Satellite filters appropriately retain coordinate/date ranges.
- eDNA-only selection, `qcauto_target` and `Ablabys taenianotus` survived reload. The draft question did not persist. Reset restored all four sources and cleared filters, verified again after reload.
- All-disabled selection survived reload. Ask and quick-question buttons were disabled with “Select at least one evidence source to ask a question.” Naming CTD in the question did not enable it. No request was submitted in that state.
- CTD station `s1` narrowed sample choices to 27 matching `*-s1` samples. A question naming unchecked ANEMONE still retrieved only CTD; the answer explained eDNA was excluded and did not invent a catalogue total. This question ran the model, rather than returning the explicit-aggregation source-disabled shortcut.
- The rare-taxon question answered one occurrence, one assay, one assignment and 122 reads, qualified unknown control status/calibration and distinguished reads from organism abundance. Ten citation references resolved with zero invalid references/warnings. The raw assay text and injected aggregate supported the reviewed statements.
- Aggregate evidence inspector opened. Its JSON downloaded to the user's Downloads folder. The payload contains the matching filters, counts, canonical publication generation and input fingerprints. The provenance page found the immutable aggregate and its canonical/source-snapshot trace.
- English and Japanese arrival-date questions both returned `Data arrival cannot be verified`, model run No, avoiding inference from collection dates. The English UI displayed the explanation in English for both questions.
- A CTD-only `2024-04-O-s1` question returned surface/bottom temperature 15.70/13.94 °C and salinity 33.24/34.17 PSU, matching the supplied profile. One primary CTD document, zero linked documents and no injected context; seven citations valid. No ecological prediction was added.
- Vertex advanced controls showed supported generation settings and omitted unsupported repetition/context-window controls.
- Admin feedback review loaded nine pre-existing rated interactions and displayed a retained historical answer/evidence controls. Test responses were not rated, and no feedback or other-user account settings were changed.

The user assigned the remaining work to the planned [v0.6.1 patch](RELEASE_0.6.1_PLAN.md) on 2026-10-02. This dated report records checks performed against v0.6.0; it does not claim the patch is implemented.

## Remaining finding: count-question routing

With eDNA enabled alone and applied filters `assignment_method=qcauto_target`, `taxon=Ablabys taenianotus`, both of these ordinary paraphrases returned `Exact count needs explicit filters`, model run No:

1. “For the selected Ablabys taenianotus and QCauto scope, how many source occurrences, assays, assignment rows and sequencing reads are supported?”
2. “How many ANEMONE source occurrences contain Ablabys taenianotus under qcauto_target, and how many reads support that assignment?”

The applied-filter table confirms the filters were present. The original presence question succeeded with the same scope. Source inspection shows the conservative bounded vocabulary in `orchestration/edna_aggregation.py`; unrecognized wording fails closed with a misleading filter instruction. This is a reproducible question-routing/clarification UX problem, not absent eDNA options or evidence leakage. No fix or redeployment was performed by this browser audit. Issue #70 remains open.

## Limits and remaining QA

This check covers the current admin account and representative questions. It does not certify viewer/researcher access, cross-account isolation, suspension/uninvited accounts, corrupted/denied storage, keyboard/mobile layouts, all scientific interpretations or the complete repeated real-provider matrix. The admin review UI lists rated feedback; independent readback of the new unrated interaction records was not verified. Existing retained history was readable. Production requests created normal test interaction records and immutable aggregate evidence, as expected from the chat workflow.

Temporary provenance/admin tabs were closed. Chat controls were restored to their original defaults. Raw text, downloaded aggregate and screenshots are retained in the private operator record and excluded from Git; no credentials were captured.
