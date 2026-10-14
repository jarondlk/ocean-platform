# Planning Hub instructions

Work in the existing checkout on overhaul. The legacy production site and main
remain unchanged. The initial setup receipt is historical; the current plan has
28 specifications (P00 plus C01–C27) and 84 prompts.

For a fresh planning/recovery session, read README.md, MASTER_PLAN.md,
DECISIONS.md, SITE_SEPARATION.md, UI_UX_BRIEF.md, COMPONENTS.md, STATUS.md,
ACCEPTANCE_MAP.md, components.json, PROMPTS.md and the handoff convention, all
under docs/plans/ocean-v1. Inspect the actual checkout and selected component's
prerequisite evidence. Never assume this chat is the only source of state.

The user also authorized C01/C02 audit and repository delivery on 2026-10-14 JST.
Read DELIVERY_AUDIT_2026-10-14.md and its final verification receipt for current
source hashes; original component receipts remain historical after audit fixes.

P00, the synthetic local UI/UX prototype, is accepted and Complete as of
2026-10-14 JST. C01 scope validation is also Complete with a verified offline
receipt. C02 derived-evidence software and synthetic acceptance are Complete;
read handoffs/C02.md. C03 retention integrity is also Complete with actual
disposable PostgreSQL acceptance; read handoffs/C03.md. C04 authentication responsiveness is Complete locally;
read handoffs/C04.md. C03 is checkpointed locally as 9a2d225; remote
delivery is explicitly approved by the user on 2026-10-15 JST and completed.
Hosted CI for source 276540f passes; read C05_READINESS_AUDIT_2026-10-15.md
and its source/evidence receipt. C05 is ready but remains unselected.
Proceed component
by component with explicit user selection. The current plan revision does not itself authorize
UI/backend implementation, tests, cloud provisioning, data transfer or deployment.
P00 and C01–C03 local application work and appropriate checks are complete.
C04 local implementation and subagents are authorized; local acceptance is complete. C05–C27 remain
unselected; planning/recovery inspection outside
the selected component is read-only unless documentation edits are requested.
Do not create other chats or begin components merely because this hub exists.

Preserve the fully isolated second-site architecture. Use explicit approved-data
copies only under later authorization, never a live legacy-service fallback.
P00 completion is not completion of the later UI/backend integration components.
Use the corresponding canonical planning/implementation/resume prompt in PROMPTS.md.
