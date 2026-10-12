# October 11 live conference rehearsal

**Two consecutive complete manual browser scripts passed against the local candidate. Use manual exact selection for the primary demonstration.** AUTO's scientific results passed, but one warm request exceeded the agreed latency limit. The freeze remains October 13, 2026, at 17:00 JST; production release and acceptance remain a later authorized stage.

## Environment and evidence boundary

The rehearsal used the actual FastAPI backend and built Next.js frontend on loopback, with authentication required and database role/interaction ownership checks enabled. A dedicated local researcher logged in through the credential flow. This did not test production OIDC. The October 9 retained database backup was restored into `ocean_conference_qa_20261011`; copied application accounts/history were cleared there before creating rehearsal identities. Production databases and history were untouched.

The API read the real sealed GCS publications. Scientific loaders, routing, permission checks and execution-time validation were active. Python 3.12.14, NumPy 2.5.3 and SciPy 1.18.1 matched the sealed runtime; PostgreSQL sessions used UTC to match canonical timestamp serialization. Initial environment mismatches were corrected without disabling freshness validation. The publication's JST seasonal convention remained unchanged. The scientific cohort rows and three publication heads matched the sealed inputs after the rehearsals and disposable stale-head probe.

Model generation and embedding calls were blocked locally before network transmission. Exact AUTO and manual scripts made no generation attempts. A separate ambiguous-query outage probe made one deliberately blocked planner attempt and returned a clear abstention. Model discovery reported unavailable as expected. No paid calls, deployment, scientific publication changes or production model changes occurred. The optional catalogue cache stayed disabled.

## Browser timings

Measurements ran from clicking Ask to the completed rendered control/result state, with the result card and outcome checked. Each cold request used a fresh API worker; the browser session and explicit analysis/MiSeq pins persisted. Warm requests used the third worker. These are a small local sample, not production performance estimates or a p95.

| Sample | Individual seconds | Maximum | Median | Required limit | Result |
|---|---|---:|---:|---:|---|
| Exact AUTO, cold | 34.274, 33.373, 32.567 | 34.274 | 33.373 | ≤45 | Pass |
| Exact AUTO, warm | 36.953, 32.169, 31.911, 33.962, 33.922 | 36.953 | 33.922 | ≤35 | Fail |

The failed warm request still returned the correct verified rows. Select the rehearsed manual path rather than asserting that AUTO meets the latency gate.

| Manual script step | Rehearsal 1 seconds | Rehearsal 2 seconds | Outcome |
|---|---:|---:|---|
| Full Japanese Question A | 8.734 | 9.147 | Answered |
| English Question A | 9.891 | 10.156 | Answered; same scientific rows |
| Labelled SST replacement | 9.674 | 9.170 | Answered; retained representative graph |
| Japanese species-specific Question B | 8.715 | 12.107 | Abstained; explicit species limitation |

These timings cover submitted questions. Source navigation, catalogue choice loading, chart/citation inspection and sample provenance are separate script steps and are not included in those query timings. Full provenance loading is slower than the manual answer path; retain the recorded fallback and allow the source view to finish loading before presenting it.

## Completed checks

- Each manual script reached all ten ranking rows, all 210 requested temporal rows across ten taxa and both period types, and all 20 chart groups. Unsampled 2020 and partial JST boundary seasons remained visible.
- Japanese, English and manual scientific rows matched the authenticated HTTP results and the retained publication. Complete paginated provenance tables matched every displayed field/result identity. The researcher opened all three frequency citations and four SST citations in each browser script.
- SST retained the 69-row *Ernogrammus hexagrammus* series and year/season/month graphs. Support counts and the distinction between aggregate and supported-stratum differences were visible. No correlation, reliability tier or causal claim was used as validation.
- Both sample inspections displayed all 66 selected-method assignment rows. The same assay supplied three species and two genus-only illustrations; names, ranks and summed reads matched the review receipt. Its source-level provenance resolved. It remains a labelled Miyagi replacement, not the unrecovered organizer Otsuchi example.
- The sample's source control classification is unknown. General Data eligibility excludes it as `control_or_unknown`; the sealed provisional publication includes it under its occurrence-proxy policy. Explain this distinction and present the sample only as source taxonomy/provenance evidence.
- Both species-specific Japanese questions abstained without a map or genus substitution. The optional one-cell genus table remains a separately labelled recorded inspection with unverified geometry.
- Authenticated HTTP checks passed for missing/expired authentication, denied viewer Data access, interaction ownership, disabled SST, unsupported year and a stale disposable publication head. The original head was restored and rechecked. Separate actual-loader corrupt-catalogue AUTO/manual requests abstained; the production catalogue was untouched. Exact requests remained usable while the provider was unavailable.
- A refreshed sealed recorded fallback passed receipt binding, all 2,100 independently reconciled rate rows and Japanese/English parity. The private package retains browser screenshots, timings, settings, isolated interaction evidence, source/runtime hashes, review receipts and fallback exports.

## Operator and remaining gates

Leave AUTO off. Pin the QCauto 95%-3NN publication and complete MiSeq protocol. Returning from Data or Provenance creates fresh Chat controls: reselect the analysis, workflow and protocol. After enabling Satellite SST, wait for choices to load and pin `mur-miyagi-2020-2023` before selecting the comparison workflow. Compact prose is a preview; use the interactive exact tables and selectors for the complete result.

The [runbook](CONFERENCE_2026-10-14_RUNBOOK.md) and [interpretation review](CONFERENCE_2026-10-11_REVIEW.md) define the descriptive script and limitations. Independent scientific approval, original organizer receipt recovery, fresh model-provider reliability and acceptance of a deployed candidate remain unclaimed. The species-level sardine map remains no-go. Retained rollback images/configuration and scientific artifacts are preserved; deployment requires the later release authorization.

Private receipts are retained outside Git in `~/Documents/OCEAN Conference 2026/live-rehearsal-20261011`. Credentials and the database dump are excluded from that deliverable. Earlier offline receipts remain immutable and do not retrospectively become live acceptance receipts.
