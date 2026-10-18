# C18 ready for isolated local implementation

Date: 2026-10-18 JST. Branch: overhaul. This audit does not select C18; the root
agent owns selection and implementation. [Final verification](verification.json)
SHA256: `ab21dfd0401820f4908ded19b728aef64a22e8970768d24afb1df43806744a43`.

The [pending contract audit](audit-pending.md) remains immutable historical
evidence. Its two remaining gates are now satisfied. C17 source
`39bb811d1053c9dfb4b700f8524162800092aa44` passed
[exact-source hosted CI39101652175](https://github.com/jarondlk/ocean-platform/actions/runs/39101652175),
and its delivery is committed at
`78a10a0c17cc29d1fa46498bf7df3c0d1be6e882`. The driver verifies source-to-delivery
ancestry, delivery-to-checkout ancestry, all19 committed source blobs, committed
local/delivery receipts, complete hosted success and all four required passing
jobs. The C17 delivery receipt remains
`bafa0d83dd7ebacf399cfbb9fb8f445967bdd9aeba5bbbbe1821e3758cfcae5b`;
its original local receipt remains
`a59bba711e76ad62dd952135e2db374235d3fa7cfdb01cd2cd2d3a76983da3d7`.

Hosted C17 evidence establishes4178 backend passes,187 separately gated skips,
85.76% coverage and187 actual PostgreSQL passes (82+12+12+21+60). All60 C17
PostgreSQL cases ran against final source. V1 frontend510 and legacy frontend132
pass, both typechecks/builds pass, both production dependency audits report zero
vulnerabilities, and migrations/idempotence/isolated backup-restore pass. The nine
local-only backend cases are unrelated preserved benchmark work. No completed
test suite was repeated for this readiness audit.

All98 formal entries reconcile across P0036/C1525/C1618/C1719, representing79
unique formal paths. Per-entry original-to-current receipt chains retain the four
C07 P00 supersessions and later C15/C16/C17 integrations explicitly. All pinned
original receipts remain unchanged. All30 unrelated files,7 scientific artifacts,
2 serving files,106 legacy frontend files and683 pinned earlier evidence files
match the preserved baseline. The final observation also hashes all736 currently
tracked earlier evidence files, including C17 delivery evidence. Eleven actual
prerequisite/specification/interface/site-boundary documents have recorded hashes.

Current C17 handoff confirms completed source and hosted delivery. No missing C17
HTTP capability blocks C18: its14 operations support persistent investigation/chat
navigation, explicit attach/detach/pin/unpin/scope changes, immutable context reads,
refresh branching and exact prepared-operation recovery. C18 must add its own
guarded Research runtime activation and real frontend integration; current C15
configuration deliberately keeps Research unavailable. The detailed recommended
client/state/UI/run-boundary split remains in the pending contract audit.

Implement C18 using actual C17 persistence and the embedded C16 browser, preserve
P00's accepted UX and separate storage, and keep production execution unavailable
until C20 supplies the real transport. Development activity fixtures require
explicit local/test injection and visible labels, with no production fallback.
C20/C21 own durable run history, generated answers and retained artifact service
integration; later experiment actions remain unavailable until their owners
integrate. Actual account enrollment, scientific/data approvals, production
capacity/retention/migrations, and concrete independent cloud target authorization
remain separate gates. Readiness authorizes no legacy/main deployment, real-data
transfer, scientific approval, provider call or cloud operation.

Only this readiness evidence directory was written. No application source, tests,
services, accounts or mutable data stores were changed. Root may now select C18
and begin the already authorized isolated local implementation.
