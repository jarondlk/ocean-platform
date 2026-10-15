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
and its source/evidence receipt. C05 is Complete locally with actual disposable PostgreSQL acceptance; read handoffs/C05.md.
Proceed component
by component with explicit user selection. The current plan revision does not itself authorize
UI/backend implementation, tests, cloud provisioning, data transfer or deployment.
P00 and C01–C05 local application work and appropriate checks are complete.
C05 source hashes, regression results and deferred rebuild instructions are recorded;
C05 is committed/pushed as fd8f520 with passing hosted CI; read
C06_READINESS_AUDIT_2026-10-15.md and its receipt. C06 is ready for explicit
selection, with 99 baseline tests passing and F07 reproduced offline. C06 is Complete locally and delivered as 27d76c9 with passing hosted CI;
read handoffs/C06.md and evidence/C06/delivery.json. C07 is Complete and delivered as 1195796 with passing hosted CI; read handoffs/C07.md and evidence/C07/delivery.json. C08 is Complete and delivered as 6d20a75 with passing hosted CI; read handoffs/C08.md, evidence/C08/delivery.json and C08_CATALOGUE_CONTRACT.md. C09 is Complete for local snapshot/capture acceptance; C10/C11 are Complete locally; C12–C27 remain
unselected; planning/recovery inspection outside
the selected component is read-only unless documentation edits are requested.
Do not create other chats or begin components merely because this hub exists.

Preserve the fully isolated second-site architecture. Use explicit approved-data
copies only under later authorization, never a live legacy-service fallback.
P00 completion is not completion of the later UI/backend integration components.
Use the corresponding canonical planning/implementation/resume prompt in PROMPTS.md.

C09 readiness was verified on 2026-10-15 JST against 3cbf9f0: 51 baseline and
246 prerequisite tests pass; read C09_READINESS_AUDIT_2026-10-15.md and its receipt.
The user subsequently selected C09; it is Complete locally. Read handoffs/C09.md and C09_SNAPSHOT_CONTRACT.md. C10 remains unselected.

C10 readiness is verified on 2026-10-15 JST against ae02e89: 36 baseline and
534 prerequisite tests pass; read C10_READINESS_AUDIT_2026-10-15.md and its receipt.
The user subsequently selected C10; it is Complete locally. Read handoffs/C10.md and C10_ADAPTER_CONTRACT.md. C11 was subsequently selected; see handoffs/C11.md.

C11 readiness is verified on 2026-10-15 JST against 7570345: 55 baseline,
482 prerequisite and 69 SST semantic/calendar tests pass; six generated
contracts are current. Read C11_READINESS_AUDIT_2026-10-15.md and its receipt.
C11 was subsequently selected and is Complete locally. Read handoffs/C11.md,
C11_SST_ADAPTER_CONTRACT.md and evidence/C11/verification.json. Required acceptance
passes 966 cases; full backend passes 2,829/84 gated PostgreSQL skips with 83.29%
coverage. C11 is committed/pushed as 41cd876 with passing exact-source hosted CI:
2,820 backend tests/84.04% coverage, 84 actual PostgreSQL cases and both frontend
gates. Read evidence/C11/delivery.json. C12 remains unselected.

C12 readiness is verified on 2026-10-15 JST against 1d3b7b6: 116 baseline,
677 prerequisite and 83 eDNA semantic tests pass; seven generated contracts are
current. Read C12_READINESS_AUDIT_2026-10-15.md and its receipt, including the
raw-inventory method and retrieval-independence constraints. C12 remains
Not started and requires explicit implementation selection.
