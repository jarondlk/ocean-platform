# Beta integration and cloud preparation

State: **Offline preparation complete; implementation not started**, 2026-11-01
JST. User requested preparation first and will sign in to GCP later. Branch
`overhaul`, reference checkpoint `5b5afe7`; accepted runtime remains `afe9cb2`.

[Preparation](../beta/PREPARATION.md), [implementation sequence](../beta/INTEGRATION_PLAN.md),
[cloud plan](../beta/CLOUD_PLAN.md), [operator worksheet](../beta/cloud-worksheet.json),
[source audit](../beta/source-audit.json), [receipt](../beta/preparation-receipt.json).

Inspected actual host/runtime/proxy, research outbox/lease and experiment
executor/port/admission/runner entry points. Frozen21inspected source paths
match the accepted checkpoint. The 844accepted application/configuration paths
and90C27package artifacts stay unchanged. No application suite is repeated for
this planning-only change. Actual original gates remain20notrun plus P2 D26-07.

The worksheet retains C24's pending values and lists67missing operator fields.
Eight suggested names/region values are separate proposals, never live defaults
or applied inputs. The null cookie domain is intentionally valid host-only
policy. No project/number, image, secret or resource is invented. Legacy and
temporary C23 targets remain excluded. Existing billing is unchanged; no new
budget amount is inferred from the legacy project.

Provider primary documentation was inspected without using account credentials.
The controller must retain its reviewed default run.app task target with IAM and
appropriate internal ingress; serving has a separate load-balancer/default-URL
policy. Project-specific behavior still needs actual later acceptance.

## Next action

First implementation checkpoint: independently configured production v1
host/auth/session/proxy and read-only service bootstrap, with research and
experiment dispatch disabled. Then real Cloud Tasks/private invocation/outbox
lifecycle; then the retained experiment port/supervisor and explicit owning
admission/start contract amendment. C22's current fake-only executor and C25's
non-launching port cannot be enabled into production by a flag. No production
adapter or contract has been implemented during preparation.

GCP sign-in is not needed for this local coding. When the user is ready for the
cloud session, first verify CLI/account access and perform a read-only project/
organization/billing inventory, then resolve actual target inputs and prepare
the concrete resource change set. Do not inspect or mutate GCP before that
session. OAuth/DNS configuration, paid resources, data transfer and actual release
remain governed by their explicit target/authorization/evidence boundaries.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/verify.py
```

The verifier is read-only and uses no GCP SDK, network or credentials. Planning
documents/worksheet/verification source pass local checks; no new hosted runtime
CI is claimed. Commit/push may use `[skip ci]` because no accepted source changed.
Keep unrelated/scientific files, original receipts and scheduler PAUSED. No live
operation or implementation should be inferred from completion of preparation.
