# B1 fixed-candidate rollout

This reconstructs the missing operator writer for the already qualified
`0f15bbca` API, image `7889ef20…`. It does not recover the former private writer's
bytes or retarget its receipts. New tooling and evidence have their own source
identity. The runtime application, frontend and source-bound build are unchanged.

[Planner](../../../../scripts/beta_b1_rollout.py) pins both service identities
and their complete input configuration. Only the accepted API image, explicit
revision names, traffic targets and the two Research admission flags can change.
It rejects unknown images, drift in other settings, wrong phase order and
unready/concurrently modified resources. Current source hashes, exact four-step
build configuration, original/diagnostic workflow bytes, successful job identities
and the exact actual PostgreSQL log qualify the existing candidate. The original
normal CI failure is still explicit; the interpreter cause remains unproven.

[Executor](../../../../scripts/beta_b1_apply.py) uses narrow Cloud Run v2 PATCH
field masks plus the fresh service etag. The controller update uses the separately
authorized personal operator; serving updates and granted reads use the dedicated
beta identity. No role expansion, new service, secret value, database/admin write,
catalogue mutation, queue resume or Scheduler mutation is supported. Tokens stay
in memory; redirects are refused. PATCH is sent once and its outcome must be
inspected before any retry. Readbacks must match every preserved input setting.

Before each non-drain apply, the executor checks actual paused/empty task state,
absent Scheduler, private controller IAM, numeric secret metadata, canonical
catalogue authority and an unexpired aggregate-only observer execution/report.
Serving phases also require the qualified private-controller revision Ready.
These checks do not replace the operator's separate budget and old-request
drain-envelope review. `drain` only closes admission on the accepted new image;
it does not roll populated history back to an unqualified older binary.

Sequence:

1. `controller`: replace only the private controller image and revision identity.
2. `stage`: create a new API revision while explicitly retaining 100% traffic
   on the preceding drained serving revision.
3. `promote`: route 100% to the qualified drained API revision, without changing
   its template.
4. Inspect actual signed-in saved history/evidence before admitting new work.
5. `admit-stage`: prepare only the two Research admission flags on a new revision;
   keep traffic on the prior drained API revision.
6. `admit-promote`: route to the accepted admission-enabled revision. Keep the
   queue paused for bounded manual validation until separate sweep acceptance.

Each phase first supports `--validate-only`; no resources are changed by that
request. Cloud Run validated the original controller and stage plans successfully
with both complete service readbacks unchanged on November14.

```sh
.venv/bin/python scripts/beta_b1_apply.py --directory "$PRIVATE_B1_DIRECTORY" \
  --phase controller --validate-only
.venv/bin/python scripts/beta_b1_apply.py --directory "$PRIVATE_B1_DIRECTORY" \
  --phase controller --apply --observer "$FRESH_EXECUTION" \
  --not-before "$CURRENT_POST_DRAIN_BOUND_UTC"
```

The directory is owner-only, outside Git, and contains newly captured build,
GitHub and service inputs. Existing phase directories are never overwritten;
inspect a failed/uncertain attempt and preserve its evidence before preparing
another. A saved observer capture expires after180seconds. Do not replay a
historical phase command as clearance to apply.

The source supports the current predeclared beta target/candidate only. A new
image, source, service identity or relevant configuration needs its own reviewed
contract and acceptance. Broad application CI is reused only for unchanged
runtime bytes; operator-tool tests and live provider validations are separate.

Primary API references checked November14:
[service PATCH/validateOnly](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.services/patch),
[service/traffic/revision fields](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.services).
