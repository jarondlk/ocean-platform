# C20 acceptance cases prepared before selection

These are planned interleavings and assertions, not executed tests or acceptance.
Use actual private C17/C14 sealed synthetic fixtures, TEST principals, fake model
outcomes/dispatch and disposable local PostgreSQL for transaction races.

| Boundary | Required observable result |
|---|---|
| Lost submit acknowledgement | Run, event1, immutable input and outbox commit together. Same owner/key/exact payload returns the original run; changed payload conflicts; other owners cannot resolve its identity. |
| Outbox acknowledgement loss | Fake queue accepts then raises. Retried publication may deliver twice under one stable delivery ID. Worker redelivery produces no duplicate committed effect or public event. |
| Concurrent claim | Two PostgreSQL sessions contend for one run. One live lease epoch owns execution; another delivery cannot dispatch until expiry/recovery. |
| Crash after reservation | Pending physical attempt stays charged. Recovery conservatively accounts unresolved active time, fences the old epoch and admits another attempt only within remaining limits. |
| Crash after call before commit | No completed step is invented. A model call may repeat and bill again; new physical attempt is charged. Uncommitted rows/events roll back. |
| Lost commit acknowledgement | Exact raw outcome, private payload, checkpoint and public event already committed. Redelivery replays the same logical step without another provider/tool call or counter charge. |
| Old worker returns late | Expired worker's result cannot commit under a newer epoch. Current owner/policy checks still apply; expiry does not claim that the old RPC stopped. |
| Cancel wins final race | Cancellation and terminal publication share one run lock/version check. If cancellation wins, no completed event escapes; committed prior observations remain retained. |
| Complete wins final race | Later cancel returns the committed completed run. It cannot rewrite terminal history or fabricate a cancellation event. |
| Clarification pause | Waiting hours consumes no active execution budget. Immutable input/clarification ID and exact mutation key prevent stale answers or changed retries from applying twice. |
| Explicit continuation | Child has a new run identity linked to an unchanged terminal parent and the same frozen context. Document its explicitly granted segment separately from automatic retry; retain verified parent observations without replaying a terminal malformed/incomplete/finish decision forever. |
| Exhausted replay | At12 actions/180 seconds, recover permitted committed evidence without another dispatch. Malformed-output replay does not reserve the one repair again. |
| Current authorization | Suspended/changed owner, changed catalogue policy, withdrawal and cross-conversation/context substitution cannot publish or expose protected evidence. Queue service identity never substitutes for the owner. |
| Consecutive events | Atomic per-run cursor allocation; private journal records do not create gaps in public cursors. Duplicate delivery is monotonic. Events carry controlled summaries, not model reasoning or source secrets. |
| Reload and disconnect | List owner/conversation history, recover exact frozen bindings, backfill events and resume polling. Aborting HTTP does not cancel durable work. Same-account uncertain intents retain exact keys; identity/revision changes clear protected memory. |
| Unconfigured execution | Missing capability, disabled API/dispatch, invalid service wiring or network failure cannot select a fixture, legacy Chat or arbitrary host. Disabling dispatch preserves authorized history and cancellation. |
| Synthesis/approval boundary | Ordinary controller completion keeps `result:null` until C21. Awaiting-approval is a typed wait, with no invented experiment approval endpoint or scientific approval claim. |
| Migration/rollback | Additive v1 schema and coherent owner/investigation/conversation/revision constraints preserve existing C17/legacy rows. Actual PostgreSQL exercises locking, rollback, replay and migration idempotence. Rollback flags preserve durable records. |

Cross-runtime wire fixtures should assert the six fixed same-origin POST actions
plus run discovery, strict JSON/request bounds, current principal, safe errors,
opaque scoped cursors, event high-water handling and actual service response parity.
Assembled browser acceptance belongs to the selected C20/C26 scope, not this plan.
