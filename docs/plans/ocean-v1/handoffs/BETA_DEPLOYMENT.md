# Beta deployment continuation — 2026-11-02 JST

State: **isolated cloud foundation verified; first authenticated host/API software
checkpoint locally accepted; hosted delivery pending. No public beta exists yet.**
Branch `overhaul`; prior planning checkpoint `acf208a`. The original preparation,
C26 and C27 receipts remain historical and immutable. The scheduler stays PAUSED.

## Completed and verified

- Independent `ocean-v1-beta-20261101` project, number534831104543, Tokyo region
  `asia-northeast1`; existing billing linked without modifying legacy resources.
- Saved beta-only gross-cost ¥50,000 monthly all-service alert, thresholds
  50/75/90/100%; separate ¥3,000 Cloud Run monthly cap read back Configured.
  Neither is a whole-project hard spending cap. Notify before exceeding the
  user's initial ¥50,000 beta-only target; the ¥100,000 upper amount does not
  authorize silently raising it. [Cost plan](../beta/live-20261101/COST_PLAN.md).
- Twenty empty foundation operations verified: Docker registry, custom VPC and
  subnet, four dedicated ungranted runtime identities, four private uniform
  buckets, eight Secret Manager containers with no versions, and a PAUSED queue.
  [Applied readbacks](../beta/live-20261101/empty-foundation-execution.json).
- Automatically granted Editor removed from the unused new-project default
  Compute identity; all other then-current bindings preserved. No legacy IAM
  or organization policy changed. [Proof](../beta/live-20261101/iam-reduction-verification.json).
- Independent backend host:35 tests and9 actual disposable PostgreSQL checks,
  native cluster stopped/removed. Explicit prefixed DB/JWT/current-account
  authority, fixed read/cancellation surface, production execution closed.
  [Backend receipt](../beta/bootstrap-20261101/README.md).
- Independent Next host:50 unit cases,1 actual built HTTP lifecycle, typecheck,
  production build and zero-vulnerability production audit. Existing static
  frontend1051tests/typecheck/export pass. [Host receipt](../beta/hosting-20261101/receipt.json).
- Composed source audit:841 accepted paths unchanged,3 intentional supersessions
  (workflow, optional UI fetcher, static tsconfig exclusion),36 additive app
  sources;5368 prior evidence files,90 C27 package artifacts and42 protected
  paths preserved. [Audit](../beta/checkpoint-20261102/source-supersession.json).

## Current deployment work

This first app checkpoint requires fresh source-bound hosted CI, including the
new fifth authenticated-host job; no old CI receipt is attributed to these new
bytes. Container packaging is a separate additive checkpoint in progress. No
Cloud Run service, SQL instance, worker VM, image, load balancer, IP, DNS record,
secret value, real-data transfer or task dispatch has been created by this phase.
The earlier foundation helper's two readback issues remain recorded as failed
attempts; verified resources were resumed, not duplicated.

The public DNS delegation is Google Cloud DNS; a read-only inventory found the
existing `oceaninfobio-com` public zone in the legacy project. There is no beta
record change yet. Only a later explicit beta-only record is in scope; no apex,
www or existing-site update. Ambient gcloud project still points at legacy:
**every operation must specify the beta project explicitly**.

## Next steps and gates

1. Checkpoint/push frozen app source on `overhaul`, retain current five-job CI.
   Package source-only nonroot API/frontend containers, then build immutable
   images only from a qualified source revision and concrete scoped build plan.
2. Obtain actual Tokyo JPY SKU quotes and fit the full expected configuration
   inside the ¥50,000 target before persistent SQL/LB/worker provisioning. Current
   cost envelope is conditional; no always-on worker is budgeted.
3. Configure independent Google OAuth enrollment and enrolled beta accounts,
   secrets, isolated DB/migrations/least-privilege access and the actual reviewed
   read service/provider. The bare API deliberately reports missing scientific
   services unavailable; do not substitute fabricated datasets or legacy users.
4. Apply beta-only TLS/ingress/DNS after exact image/config acceptance; test real
   login/callback/session/current-account revocation and direct URL isolation.
5. Implement real queue/outbox/private invocation and retained worker integrations
   before enabling any research or experiment dispatch. Existing C22/C25 fake or
   non-launching ports are insufficient. All20 original live release gates and
   openP2 D26-07 remain; no scientific approval or release acceptance is inferred.

CLI access was verified at this continuation. The Mac/browser is locked; the user
has been asked to unlock it for eventual OAuth console work. Continue independent
local/CLI preparation without requiring a fresh login while CLI access works.
Do not restart completed stateful checks or create recurring automations.
