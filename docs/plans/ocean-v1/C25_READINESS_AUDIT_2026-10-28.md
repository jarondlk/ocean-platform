# C25 readiness audit

Audited 2026-10-28 JST on `overhaul` at
`3661882bd9634ff4372e35e697606382e1168270`, matching the read-back remote branch.
**Ready to begin C25's local proposal-review/approval checkpoint. Full execution
and results service acceptance has an explicit backend-contract prerequisite.**
C25 implementation remains Not started; this audit does not select implementation.

## Accepted prerequisites and checkout

| Prerequisite | Accepted source | Source entries reconciled | Intentional later supersessions |
| --- | --- | --- | --- |
| P00 accepted UX/prototype | `c7ea5f4` and original user-acceptance receipt | 36 | 14 accepted shell/catalogue/security/export changes |
| C18 Chat + Workspace | `596d871` and hosted delivery | 23 | 10 accepted durable-run/evidence integrations |
| C22 proposals/approvals | `66b4106` and hosted delivery | 25 | 6 accepted CI/native-test changes; public experiment API/schema/service remain exact |
| C23 isolated execution | `f6f823b` plus actual retained Linux receipts | 236 | None |
| C24 configuration/operator preparation | `eeec2e1` and hosted delivery | 15 | None |

All **335 receipt entries / 322 distinct current source paths** match the
accepted hosted implementation `eeec2e1`. Every historical source pin matches
its original accepted commit. The machine receipt names each later supersession
and its actual implementation commit; original receipts and the accepted P00
screenshot remain unchanged. All 42 protected unrelated paths are preserved.
[Verification](evidence/C25/readiness-20261028/verification.json).

Current source-bound CI is [40663077852](https://github.com/jarondlk/ocean-platform/actions/runs/40663077852):
all four required jobs pass, including 6,601 backend cases, 315 actual PostgreSQL,
930 v1/132 legacy frontend cases and builds/typechecks/audits/backup-restore.
Those are predecessor/current implementation results, not C25 acceptance.

## Fresh local baseline

| Check | Result |
| --- | --- |
| C22 contracts, real synthetic HTTP actions, exposure/security, retained proposal service and C23 inspection | **234 passed**, one existing TestClient deprecation warning |
| `npm --prefix frontend-v1 test` | **930 passed**, no skips/failures |
| `npm --prefix frontend-v1 run typecheck` | Pass |
| `npm --prefix frontend-v1 run build` | Pass; existing static export |
| Source/receipt/remote reconciliation and audit Ruff | Pass |

Exact commands/stdout/stderr are retained under
`evidence/C25/readiness-20261028/`. No full/native backend suite was repeated:
its source is unchanged and the accepted hosted results remain available.
No GCP, DNS, provider/model, real-data or production operation occurred.

## What is ready now

Reuse `frontend-v1/src/research-workspace.tsx`, the accepted Chat/Workspace layout,
account/permission invalidation, current investigation/context binding and URL
navigation. The current Experiments tab deliberately reports unavailable.
Do not restart from the P00 mockup or expose synthetic prototype behavior as
service availability. Keep the accepted concise blue styling and EN/JA,
responsive, keyboard and screen-reader requirements.

The actual `/research/experiments/*` family has nine actions:
`create`, `revise`, `get`, `status`, `list`, `approve`, `dispatch`, `events`, `retry`.
They provide owner-authorized proposal history, exact revision/context/content
hash binding, stale-approval rejection, retained uncertain mutations and explicit
dispatch unavailability. This is enough to begin a strict TypeScript client,
wire-parity tests, proposal review and revision-aware approval UI using the
existing synthetic service fixtures and actual local HTTP handlers.

## Backend contract gap for later C25 checkpoints

`ExperimentSnapshot.execution_performed` is explicitly `Literal[False]`, with
validation rejecting true/coercible alternatives. Dispatch states describe
reservation/fake-delivery acknowledgement, not actual execution. The public
action registry has **no cancellation, execution-status/results or artifact
retrieval action**. Current trusted v1 runtime discovery also has no experiment
execution capability. C23's actual retained operator path writes private execution
and publication records; it does not expose an owner-scoped browser service for
reopening them. A successful operator run is not that public API.

Before checkpoints 2/3 claim real-service parity, prepare and accept a bounded
C22/C23 contract amendment covering:

- Server-derived experiment availability and execution identity bound to the
  exact owner, investigation/context, approved revision and retained hashes.
- Durable queued/running/cancelling/terminal progress, cursor recovery and
  idempotent cancellation. A cancel request is not physical termination or
  capacity-release authority.
- Currently authorized result/artifact metadata, validated table/raster previews,
  safe downloads and evidence attachment, with manifest/byte identities and
  experimental/scientific-approval qualifications retained.

Keep `research-experiments-v1`'s accepted non-execution semantics intact; do not
silently loosen its false field or invent frontend routes/states. Name and version
the additional public contracts when that backend amendment is designed. Do not
expose private signing material, worker paths or arbitrary HTML/notebooks.
Fixture-only progress/result panels may be developed visibly as fixtures, but
cannot satisfy actual service parity or full C25 completion by themselves.

## Separate live integration and next action

Authenticated beta hosting/proxy, the real Cloud Tasks/outbox adapter and the
production experiment supervisor remain unavailable. C24's DNS/TLS/IAM/network/
session/two-job/recovery/backup gates remain not_run. The proposed integration
checkpoint after C25 and before C26 live acceptance still needs explicit scope
and delivery evidence. This is separate from the public-contract work needed
early enough for C25's local real-service acceptance. No live beta date or
deployment is implied by this readiness result.

**Next action when C25 is selected:** start checkpoint 1's exact C22 transport,
review/approval UI and wire tests; define the bounded C22/C23 public-contract
amendment before implementing real execution/result controls. No GCP sign-in is
needed for that local work. Keep unavailable states honest, use synthetic inputs,
preserve predecessor evidence and leave dispatch/scheduled messages disabled.
