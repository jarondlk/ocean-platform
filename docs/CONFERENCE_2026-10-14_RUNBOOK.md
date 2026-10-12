# OCEAN conference demonstration runbook

Code and evidence freeze: **October 13, 2026, 17:00 JST**. Stop optional feature work at 12:00 JST. Rehearse after the freeze for the October 14 press conference.

## Current acceptance state

**The conference patch is deployed and verified; final presentation-device rehearsal and freeze remain.** [October 12 deployment](CONFERENCE_2026-10-12_DEPLOYMENT.md) records the exact source/images, 100% serving revision, restore-tested backup, isolated cloud acceptance, read-only production checks and compatible rollback. On October 11, read-only GCS downloads of all 26 generation-pinned files passed the registered receipt, manifest, recipe and object hash checks. The publication index remained unchanged during download. The sealed production analysis reconciles 104 occurrence proxies in separate 9/56/39 protocol strata, 14 excluded occurrences, and all 2,100 ranking/temporal rates. Japanese/English scientific rows match. Its analysis ID and canonical source digest match the fixed conference manifest. The older local preview remains separately labelled and must not replace this sealed package.

Earlier October 11 local validation: 1,403 backend tests passed; 39 integration tests skipped. 80 frontend tests, type checking and production build passed. Two consecutive fixture rehearsal receipts are retained privately and are labelled offline; they do not satisfy the live rehearsal gate. The initial static Japanese UI artifact could not be inspected through the browser's local-file URL policy. The subsequent authenticated local application rehearsal below supplies actual browser acceptance.

The subsequent receipt/review change passed 137 focused backend regressions and 81 frontend tests, plus type checking and production build. It independently checks SST arithmetic, preserves the retained graph, supplies the explicit sample replacement and exposes the SST support count. A later live browser rehearsal led to compact prose previews while preserving every exact row in interactive cards; its 137 focused backend regressions passed again.

GCP authentication and sealed artifact verification are complete. A read-only Cloud Run check confirmed `ocean-platform-v076-patch1009` serves 100% of traffic; both image digests and source commit match the October 9 release record. The documented `v076-previous` rollback revision still exists and is Ready. These checks establish serving configuration and artifact identity, not fresh production application/database health or acceptance of the new local code. Under the user's delegated judgment, [the factual and interpretation review](CONFERENCE_2026-10-11_REVIEW.md) accepts a descriptive script with explicit sample/SST replacements. Exact organizer originals remain unclaimed; external scientific approval is not asserted.

[October 11 live rehearsal](CONFERENCE_2026-10-11_REHEARSAL.md) completed authenticated HTTP acceptance and two consecutive full manual browser scripts against a disposable restored database, the actual candidate API/frontend, and real read-only sealed GCS artifacts. All 210 requested temporal rows and 20 chart groups were reached in each script. AUTO's three cold requests passed (maximum 34.274 seconds), but one of five warm requests failed the 35-second limit (maximum 36.953 seconds). **Use manual exact selection for the primary script**: all eight rehearsed manual queries rendered in 8.715–12.107 seconds. The catalogue cache remained disabled. This is local candidate acceptance; production acceptance and a later authorized release remain separate. Provider generation was blocked locally, so the rehearsal establishes deterministic outage behavior, not fresh provider reliability.

The October 11 implementation/rehearsal did not deploy. Under the later October 12 authorization, the patch was merged and deployed with scientific publications, canonical records, original histories and both production models preserved. No migration, production restore, new acquisition or paid model call occurred. Existing benchmark/audit work remains separate. Use manual exact selection: the cloud image's first isolated AUTO case also exceeded the cold timing limit; no fresh production browser latency claim is made.

## Fixed primary script

Use the scientific identities in `evaluation/qa/conference_manifest.json`:

- QCauto 95%-3NN analysis: `9312a7e12211be66f58f17a1e57f2ce0f581da427d9074cada8787657af6d56b`.
- MiSeq protocol: `91e3ce341d150bdab5bc156775bd9257fa6a2833e3b53194841fc558c1dddfa6`. The full identity includes gene, primer, instrument, layout and PCR metadata. Instrument alone is insufficient.
- Assignment method: `qcauto_95pct_3nn_target`.
- Canonical source SHA-256: `334a1f0ebb84085e5f0f1163a90a085a7e721d0c0202ee2ae69014efd8924458`.
- Regional publication: `d34da58bbb39bb3675d0d0654d56ab13de46b078605df0fe52cb8f8ade698952`.

In an isolated QA identity/database, enable ANEMONE eDNA, select the analysis and MiSeq protocol, choose `fish_frequency`, retain the full publication cohort and clear only operator-reviewed conflicting filters. Disable supplementary reliability/correlation context. Keep any original source/dataset pins when checking an organizer example. Manual source selections remain authoritative; AUTO retains explicit active filters and pins, subject to shared validation. Unpinned AUTO retains the existing first-protocol default and never pools protocols.

Leave AUTO off for the rehearsed primary path. After returning from Data or Provenance, Chat creates fresh controls: reselect the published analysis, workflow and MiSeq protocol before asking. After enabling Satellite SST, wait for the filter choices to finish loading, then pin `mur-miyagi-2020-2023` and select `temperature_comparison`. Use the browser receipt and saved screenshots as the operator reference.

For the local reproduction environment, match the sealed runtime (Python 3.12.14, NumPy 2.5.3, SciPy 1.18.1) and use UTC PostgreSQL sessions (`PGOPTIONS='-c timezone=UTC'`). A different Python patch version or database timestamp representation can mark the publication historical; fix the environment rather than bypassing scientific freshness checks. JST season calculation remains the published convention. The rehearsal retained authentication and real database role checks, using separate local test credentials rather than production OIDC.

Japanese question (including its optional heading):

> よく見つかる魚は何か？
> 2020年から2023年の宮城県沿岸で、環境DNAによる検出頻度が高い魚の上位10種を教えてください。年ごと、季節ごとの変化も示してください。

English parity question:

> Show the top 10 fish by detection frequency, with yearly and seasonal changes

Check the applied analysis, method and complete protocol identity before explaining the result. Sealed-bundle verified MiSeq eligible units are 0 in 2020, 3 in 2021, 26 in 2022 and 10 in 2023. Show all ranking rows, then use the taxon and period selectors to inspect every yearly/seasonal group. The overall top-ten panel stays fixed; fewer resolved species must produce fewer rows. Show numerators, denominators, percentages, sparse-support and partial-period flags. December belongs to the following year's DJF; boundary seasons can extend the displayed year label beyond the source interval.

Explain: occurrence proxies are not confirmed independent water collections. `0/n` is a recorded non-detection under a complete eligible assay, not biological absence. `0/0` has no rate. Unavailable assay evidence is not a negative observation. Detection frequency is not abundance, occupancy or causation. Latin names and actual ranks are authoritative; Japanese common-name mappings remain unverified.

Exact AUTO uses neither planner nor answer model when the bounded catalogue match and shared validation succeed. Its diagnostics must show `deterministic_match=true`, `planner_invoked=false`, `planner_model=null`, and the expected protocol. Changed qualifiers must clarify or abstain, never silently use the fixed panel. Manual mode continues through its existing exact path.

## Question B and optional genus table

> イワシはどこで見つかるか？
> 2023年の宮城県沿岸で、採水地点が最も多かった月はいつですか？その月にマイワシが検出された地域を示してください。

The English counterpart is “Show the best-covered month and sardine detections by area”. Both must state the species-level limitation. Retained evidence has no species-resolved `Sardinops melanostictus` records. Do not substitute unidentified Sardinops, infer absence, show a species map, or substitute another year.

The optional **Sardinops-genus one-cell inspection** is a separately labelled table. It uses the existing published coverage choice, then complete source assay/detection evidence. Retained MiSeq coverage selects March 2023 by distinct areas, eligible units, then earliest month; its three occurrences have no Sardinops assignment rows. Never switch to another month to find positives. Inspect the sample and assay IDs through the existing Data/Provenance routes under the appropriate permissions. The recorded coordinate/worldmesh does not verify its footprint or uncertainty. Keep geometry marked `unverified_no_map`; no regional rectangle, multi-area distribution, or spatial SST comparison is included.

## Private offline evidence package

Keep raw inputs, recorded responses, sample/assay identities, screenshots and receipts in a private directory outside Git. The committed manifest contains scientific identity expectations and explicit unverified organizer states, not raw source evidence. The verifier refuses existing output directories and repository-local output. It opens no database or model provider.

After a read-only download of the deployed bundle into a directory named by its analysis ID:

```sh
.venv/bin/python -m evaluation.qa.conference_demo \
  --bundle /private/tmp/ocean-conference-20261011/evidence/9312a7e12211be66f58f17a1e57f2ce0f581da427d9074cada8787657af6d56b \
  --artifact-index /private/tmp/ocean-conference-20261011/evidence/provisional-index.json \
  --artifact-receipt /private/tmp/ocean-conference-20261011/evidence/artifact-receipt.json \
  --output /private/tmp/ocean-conference-20261011/sealed-verification
```

The directory must contain the complete original manifest and sealed files. The verifier requires the retained publication index and registry receipt, binds them to the pinned receipt hash in the conference manifest, and checks all registered sizes/hashes plus manifest and recipe digests. Download each object using its receipt generation; retain the download verification receipt. The loader checks identity, file hashes, schema, complete inputs, limitations and recomputed outputs. The separate verifier checks membership/exclusion partitioning, protocol identity, source/JST dates, every numerator/denominator/rate and member ID, fixed ranking/panel, and Japanese/English row parity. It exports answers, Japanese card context, the optional genus table and file hashes. Exit 0 establishes this artifact check only; conference readiness remains false until external gates pass. Use a new output directory for each verification run; the command refuses retained directories.

A local preview is explicitly a non-production fallback preparation:

```sh
.venv/bin/python -m evaluation.qa.conference_demo \
  --local-preview /private/tmp/ocean-issue103-implementation/miyagi-provisional-demo/qcauto_95pct_3nn_target.result.json \
  --output /private/tmp/ocean-conference-20261011/preview-verification
```

Exit 2 is expected for an unsealed or mismatched artifact even if its arithmetic passes. Do not relabel that export as the deployed demonstration. Retain a private, permission-controlled recorded fallback only after its exact production evidence is bound. A static UI preview is a layout check; inactive selectors or recorded screenshots are not a live application rehearsal.

## Preserve the organizer examples

The reviewed script now uses two explicit, reproducible replacements under the user's October 11 instruction to proceed using judgment. The SST slot uses recovered October 9 isolated-QA case 8: the exact MiSeq result rows, citation IDs, settings and selected **Ernogrammus hexagrammus** series reproduce against the sealed bundle. The sample slot uses one complete November 24, 2021 MiSeq assay from the retained Miyagi cohort, illustrating three species and two genus-only labels by highest source read sums. Its full fish assignments include 28 species, 12 genera, five families and one order across 66 method rows. Five illustrations must never be described as the complete community, independent taxa, or the original Otsuchi result. Private fixtures retain source identities and existing Data/Provenance query URLs.

In the live Data view, this sample's source control classification is unknown and its general eligibility label is `excluded / control_or_unknown`. The provisional publication's occurrence-proxy policy includes it. Explain the policy distinction; do not describe the sample as a confirmed non-control water collection or the five labels as independently confirmed biological detections. The source taxonomy/provenance illustration remains usable with this explicit limitation.

For SST, disclose that the representative's aggregate high-minus-low difference is −14.69 percentage points, while its mean supported-stratum difference is +60.00 points over one area-season stratum. These are different descriptive summaries. The interface exposes the support count and explains representative selection; neither quantity establishes a general temperature response. The operational minimum-support rule does not establish statistical significance. The sealed values and graph selection remain unchanged.

Recover each original query, source selections/filters, sample or analysis ID, method, full protocol, model/generation settings, selected graphs, evidence/result snapshots, output and citation traces. Store immutable file hashes and the originating receipt/date. For Otsuchi, independently verify exactly three species and two genera from the same sample evidence; unresolved names stay unresolved. For SST, preserve the original cohort, contrast definitions and graph selection. Retained related receipts are insufficient to claim exact reproduction. If an exact receipt cannot be recovered, explicitly mark the example unverified and use a separately approved, verified fallback in the script; never silently reconstruct the organizer example.

Historical SST has 1,455 final days and six retained gaps. It is regional, subsampled foundation SST, not native coastal or sample-point temperature. Retain actual match timestamps, SST-matched versus all-eDNA denominators, support flags and the relative-baseline limitation. Do not use disputed reliability tiers, correlations derived from a retrieved top-ten subset, or unsupported SST/CTD pairings as scientific validation. Remove such claims from the script if encountered; do not regenerate the scientific corpus under this deadline.

## Acceptance and timings

Run backend tests, frontend tests/typecheck/build, and offline evidence verification. Local fixture tests use temporary bundles and synthetic actors/history stubs; they do not substitute for isolated authenticated end-to-end acceptance. Verify denied permissions, disabled sources, retained conflicting filters, unsupported years/places/top-N/exclusions, instrument conflicts, stale publications, corrupt artifacts and unavailable providers. Exact paths must remain usable with provider outage. Citation resolution and scientific review are separate: independently inspect names/ranks, units, counts, denominator/missingness definitions and interpretations even when all citation IDs resolve.

Measure **browser submission to final rendered results**, including authorization, catalogue, scientific-input checks and rendering. Record each of three cold and five warm exact requests, selected identities, route, model invocation flags, and maximum/median. Do not report an unsupported p95. Require at most 45 seconds cold and 35 seconds warm in the rehearsal sample; 15 seconds warm is a target. If limits fail, use the rehearsed manual deterministic route or bound recorded fallback. A model-dependent example needs separate paid-call authorization for fresh provider validation.

Complete two consecutive full rehearsals using an isolated QA database/test identity. Original accounts/history/publications remain untouched. The operator must reach every taxon/period, open every citation permitted to the conference role, exercise the manual fallback, and verify the recorded package. Record browser timings, screenshots, settings and source/release identities. The agent's factual/interpretation review is recorded under delegated user judgment. Disclose the absence of external scientific approval; any later advisor decision is a separate receipt and must not be fabricated or implied by software tests.

## Flags, rollback and freeze

`AUTO_EXACT_WORKFLOWS_ENABLED=true` enables planner bypass; set false independently to restore the existing planner-assisted selection. `AUTO_CATALOG_CACHE_ENABLED=false` is the default. The optional process-local cache has a 60-second TTL, at most four revision entries, deep copies, single-flight refresh and revision checks. Failed checks take a fresh verified miss or abstain; execution always validates current scientific inputs. It stores public catalogue metadata only. Admit it only after core acceptance and measured benefit. Complete narrative evidence packing remains deferred: exact tables/cards are authoritative; model narratives still have bounded evidence. Use the deterministic primary script.

Application rollback restores the preceding serving revision and retained configuration from the release receipts. Current serving revision is `ocean-platform-conference1012`, application source `3738391`, schema `20261005_0016`; immediate rollback is `ocean-platform-v076-patch1009`, source `784cd5c`, retained as `conference-previous`. The [deployment receipt](CONFERENCE_2026-10-12_DEPLOYMENT.md) records exact digests and rollback command. Disable cache/bypass separately if needed. Rollback must retain scientific artifacts and never restore databases or overwrite histories.

At October 13, 12:00 JST, remove any unvalidated secondary example. At 17:00 JST, freeze code, scientific IDs, protocols, fixtures, exports, timings, configuration and this runbook. Declare the primary demo ready only after sealed identity/parity, complete presentation, scientific/citation checks, recovered examples or explicit verified fallback, authenticated failure checks, two timed rehearsals, recorded fallback and compatible rollback all pass. Species-level Question B remains no-go on retained evidence. The optional genus table does not block Question A.
