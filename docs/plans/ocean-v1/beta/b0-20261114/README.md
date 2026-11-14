# B0 completion — 2026-11-14 JST

B0 preparation and its dated live preflight passed. B1 can begin its guarded
rollout preparation. No controller/serving image, schema, IAM, catalogue,
queue state or runtime schedule was changed. Research admission remains off.
Full beta/release acceptance and scientific approval remain false.

## Delivered evidence

- [Readiness/source receipt](readiness.json): unchanged 180 API/71 frontend
  runtime pins, qualified image `7889ef20…`, new operator-tool hashes and scope.
- [Portable operator tooling](../../../../../deploy/gcp/beta/b0/README.md): exact
  recovered read-only observer and entry-wrapper bytes, reviewed job contract,
  and the new verifier. The original 15-file private helper set is not recovered;
  the B1 staging/controller helper still needs hash-based recovery or reviewed
  reconstruction before apply. No obsolete one-shot helper was replayed.
- [Authority check](authority-summary.json): enabled numeric secret metadata,
  exact activation `4843e61b…`/generation 1794232040589985, current control
  generation 1794325728054265/hash `94f56925…`, all 22 canonical audits replayed,
  16 references and 6 registered snapshots; selected three-family registry and
  child snapshots are current. Only metadata/control was read, not scientific
  table payloads or secret values. Cloud Run alias names were resolved to their
  real Secret Manager resources before metadata checks.
- [Cloud closing checks](cloud-checks.json): serving generation34/revision21 and
  private controller generation2/revision2 preserved; queue PAUSED/0tasks,
  0Scheduler jobs; exact task subject, private invocation, custom permissions
  and runtime-only secret accessors verified. Full inherited/network/legacy
  isolation and live restore are later acceptance gates.
- [Budget readback](budget-console-readback.json): Console showed beta's
  ¥50,000 all-service monthly alert budget and ¥10,357.58 reported spend, plus
  the existing Cloud Run-only ¥3,000 enforced cap and approximately ¥270.97
  directional spend. Both definitions were preserved. Budgets API access
  returned `SERVICE_DISABLED`; the existing Console supplied the readback
  without enabling an API or expanding IAM. Reporting and enforcement lag and
  billable overages remain qualified.
- [Fresh cost ledger](cost-ledger.json) and [31 selected JPY prices](selected-prices.json):
  all selected public rates unchanged. Metered incremental gross estimate
  ¥95.6567, plus conservative all-storage-sent-bytes internet allowance ¥74.1091
  and ancillary reserve ¥5. With the single observer reserve ¥1.50, the planning
  total is ¥176.2657, leaving ¥323.7343 within the initial ¥500 validation limit.
  These are estimates/reservations, not an invoice. The completed observer's
  reserve remains held for metric-ingestion lag; monthly fixed baseline is
  tracked separately. Only the two original model calls/11,603 tokens remain.

## Actual observer and image guard

[Admission record](observer-admission.json) verified unchanged service generation
and admission flags across more than the full 60-second old-request envelope.
The unchanged observer ran once as `ocean-v1-beta-provider-preflight-20261111-9grc7`,
completed at 07:36:12 UTC in 16.31 seconds, with one succeeded task and no retry.

[Aggregate report](observer-report.json) found 3 terminal runs, 2 terminal answer
jobs, 0 open leases,0pending/dispatchable/orphaned outbox work and 0 prepared/uncertain
model steps. Both fixed question03 predicates were terminal with closed leases.
Read-only transaction identity/isolation and proxy shutdown passed.
[Guard proof](observer-proof.json) accepted the exact Linux/amd64 child of the
reviewed proxy index while comparing every other execution setting to the pinned
job contract. The source remains the original hash `a094ff42…`.

The guard passed 47 focused positive/adversarial tests and Ruff. It rejects
altered images/source/network/secrets/resources, changed execution authority,
duplicate/nonfinite JSON, inconsistent/extra report data, future and stale
observations. Recovered `.source` files retain their original byte identities
and formatting; lint acceptance applies to the new verifier/tests.
No application suite or new hosted runtime CI was repeated: the candidate
application bytes and existing source-bound composed CI are unchanged. The
original normal CI remains failed and its native crash cause unproven.

The proof was verified while fresh at 07:37:48 UTC. Its 180-second freshness limit
does not extend with this document or a commit. It is a dated observation,
**not persistent rollout clearance**. A later apply needs current guards and
fresh post-drain quiescence; `rollout_cleared` remains false.

## Next B1 gates

1. Recover/reconstruct and review the actual controller/stage/promotion helper,
   including exact candidate source/image/build/CI and preserved-setting checks.
   The new B0 verifier supplies the exact observer/index boundary, not a cloud
   writer. Use already granted scopes; do not broaden the unattended identity.
2. Refresh the current service/IAM/control/queue/budget checks and obtain
   quiescence within the guard's freshness bound immediately before apply.
   Then private-controller image readiness precedes API-only stage/promotion.
3. Before a fourth question or a runtime sweep, prepare a defensible model/call
   reserve within remaining allocation or obtain a documented amendment. The
   old ¥370 model reserve plus ¥20 rollout reserve no longer fits the conservative
   initial ¥500 envelope. B0 admits no new paid model work or wider budget.
4. After rollout, actual Gemini cited-answer, persistence/reload,15-second
   history/evidence and new-image cancellation/duplicate/recovery gates remain.

Raw readbacks and the read-only recovery helpers are retained in owner-only
durable private storage; [private evidence index](private-evidence-index.json)
records their hashes/location. No credential store, key or auth code was copied.
Original scientific bytes/receipts and unrelated local work remain preserved.
The three-hour Codex schedule stays PAUSED.
