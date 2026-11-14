# Beta cost readback — 2026-11-11 evening JST

Fresh read-only capture: **2026-11-11T12:27:31.991663Z** (21:27 JST). All 31 selected public JPY prices and 12 aggregate metric reads returned HTTP200; all telemetry pages were read. Prices match the Nov10 capture. Queue PAUSED, tasks 0, Scheduler absent. Vertex remains exactly 2 calls, 10,599 input and 1,004 output tokens including thoughts; no new model usage occurred.

[Validation ledger](validation-ledger.json) keeps the initial **20 questions / ¥500** limit unchanged:

| Component | JPY |
| --- | ---: |
| Conservative observed cloud, including job minimums and rounded finished builds | 86.304266060 |
| Closed question03 model usage | 3.706505842 |
| Existing ancillary reserve | 5.000000000 |
| Candidate 600-second API build | 9.492299990 |
| Candidate shared 14-call question reserve | 370.000000000 |
| Candidate read-only observer execution reserve | 1.500000000 |
| Candidate UI, rollout and cloud margin | 20.000000000 |
| Combined observed and reserved | **496.003071892** |
| Remaining outside these reserves | **3.996928108** |

The observed-plus-ancillary subtotal is **¥95.010771902**; the candidate build, question, observer and cloud margins are future planning reserves, not charges. The exact retained 14-call planning estimate is ¥365.885449638; ¥370 is its rounded reserve. A 120-second observer compute envelope at higher request rates is ¥0.946856640; ¥1.50 also allows startup and cleanup. [Fresh observer metadata](observer-job-metadata.json) confirms generation1 and no executions. The narrow residual requires another budget check after build/rollout and before Q4; no question or resource change is admitted by this receipt.

[Monthly scenario](monthly-scenario.json) remains **¥36,810.841691313** including 10% contingency, with **¥13,189.158308687** below the ¥50,000 target. It retains the ¥100,000 upper budget, a bounded ¥3,300 aggregate Run allocation and ¥1,100 non-sweep envelope. Fresh whole-project Run projection is ¥749.523751420 per31days; a 25-second mean idle sweep scenario is ¥2,070.692306496. These are bounded planning assumptions, not guaranteed spend. A new-image live idle measurement and actual Gemini cited-answer/persistence gates remain required before recurring dispatch. No ongoing unbounded model volume is included.

[Public prices](public-selected-jpy-prices.json), [normalized rates](selected-default-jpy-prices.json) and [aggregate usage](observed-usage.json) contain no credential values, prompts, generated content or public request URLs. No resource mutations, job executions, CI actions or model calls were performed. The [earlier authentication failure](readback-auth-attempt.json) is retained; the successful fresh capture followed the operator's new sign-in. All earlier cost receipts remain unchanged.
