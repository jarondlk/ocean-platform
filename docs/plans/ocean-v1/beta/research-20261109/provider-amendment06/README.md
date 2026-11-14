# Provider amendment 06 — checkpoint November 14, 2026

Later main-Mac audit: [current handoff](../../../handoffs/BETA_DEPLOYMENT.md),
[completion plan](../../BETA_COMPLETION_PLAN.md) and
[exact proxy-index/child proof](../../main-mac-return-20261114/audit.json).
The text below retains the second-Mac checkpoint. Fresh main-Mac reads now
confirm the held images and prove the proxy relationship; rollout guards,
private-tool portability, current preflight and live acceptance remain open.
Original JSON receipts below are unchanged.

The rollout is held. [rollout-hold.json](rollout-hold.json) records the effective
state and resume order. November 14 cloud inspection requires reauthentication;
all successful cloud and cost observations here are dated November 11.

API source `0f15bbcae3ad73ed76ddb32dd57b3a03dbedb49f` is qualified as immutable
image `7889ef206cb34008e5a5806ab8bd0ebff486501e53160862e94bfd12b8d875f8`
by [build.json](build.json), [cloudbuild.json](cloudbuild.json) and the
[production source manifest](production-source-manifest.json). It is not deployed.
Last verified serving is admission drain `00021-mgn`, still using API `4b24ca90…`
and frontend `be709b49…`; private controller `00002-mcw` is unchanged.

[ci.json](ci.json) composes unchanged successful backend/frontend evidence on
`0f15bbca` with all 318 PostgreSQL cases, 16 explicit skips and an actual
PostgreSQL16.15 74-table backup/restore in diagnostic run `43020625782`, whose
checkout is pinned to that same source. Original normal CI `42941802734` remains
failed at native exit139. The focused 120-second dump and timer-zero variants
both passed in the diagnostic run; interpreter root cause is unproven.
[workflow-supersession.json](workflow-supersession.json) proves that the only
workflow change here is this native group's scheduled faulthandler timer
120→0. All tests, fatal handling and the 45-minute job bound are preserved.
The full backend was not repeated for this checkpoint.

[observer-completed.json](observer-completed.json) records both successful
read-only aggregate audits and the exact proxy image mismatch. The controller
dry-run guard rejected reviewed digest `f333a9c5…` versus executed `1d2285ce…`.
Their manifest relationship is unresolved; the guard was not weakened. No
controller intent/PUT/apply or serving API stage/promotion occurred. All
quiescence snapshots are expired and cannot authorize a future rollout.

[verification.json](verification.json) and [preflight.json](preflight.json)
retain earlier offline preparation states. Their unsubmitted/zero-execution
claims describe those earlier captures and are superseded by the build,
completed observer and hold receipts. Pre-drain readbacks in
[images.json](images.json) are explicitly historical. The proposed image and
last verified drain are identified separately there.

The [budget reservation after build](candidate-budget-after-build.json) is
historical planning evidence, not current spend. Cloud usage from the later
drain and two observers is not fully reconciled. Refresh the ledger before
any further model question or recurring sweep. Three manual questions have
been submitted; actual Gemini-backed cited-answer, persistence/reload and
15-second signed-in history/evidence acceptance remain open.

[retained-helpers.json](retained-helpers.json) locates durable private copies
of reviewed helpers/tests by hash. Do not replay saved phase arguments or
the one-shot refresh helper: snapshots and its execution-count assumptions
are obsolete. Inspect uncertain outcomes before any retry. Preserve the
auxiliary `codex/postgres-reopen-20261111` branch for diagnosis.

Three-hour Codex scheduling remains PAUSED. The runtime outbox sweep stays
gated. Scientific approval remains false; original scientific bytes, immutable
receipts and separate legacy/eDNA/ANEMONE/experiments/worker gates are preserved.
