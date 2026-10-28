# C24 operator runbook and live gates

Status: configuration-only. This runbook does not authorize or perform cloud
changes. All gates in a rendered manifest start `not_run`; there is no CLI
option which marks them passed or enables dispatch. Scheduled messages remain
paused. The C23 test worker is a stopped, separately scoped test environment.

## 1. Preflight a concrete beta target

Use the pending operator worksheet to collect the independent v1 project ID and
number, region/zone, canonical beta origin and DNS operator access, registry and
exact image digests, VPC/subnet and SQL ranges, database/buckets, runtime
identities, numeric secret versions, OAuth client/callback, queue/controller
binding, boot image unique ID, complete C23 material hashes and explicit
capacity/log/retention/recovery/budget inputs. Do not borrow the legacy environment
or promote the temporary C23 project implicitly. Review current inherited IAM
and resource ownership; project separation alone does not prove access isolation.

Validate a private non-secret input copy and inspect the complete rendered
bundle/hash manifest. The operator must translate policy contracts into concrete
reviewed provider definitions and validate those exact definitions against current
provider/API schemas. No Terraform/provider validation is claimed by C24. Never
send an artifact wrapper to an API or apply old rendered files blindly.

Obtain concrete authorization for the reviewed live actions/targets. Existing
C23 test permissions do not establish target configuration or whole-site release
readiness. No new billing arrangement is needed for offline development. Budget
fields are explicit operator inputs, not live prices or hard spend enforcement;
budgets/alerts must be read back and actual quotas/scale/pause controls rehearsed.
No cost estimate has been invented.

## 2. Establish isolation before activation

1. Under the separate approved live operation, create only v1 resources and
   retain their actual IDs/ownership. Check inherited IAM, private SQL/TLS,
   bucket public-access prevention, exact secrets/role functions, private queue
   invocation, network routes/egress and absence of legacy access.
2. Verify boot-image unique ID before any trusted worker starts. Create a disk
   without booting or attaching the runtime service identity, then compare the
   disk's actual `sourceImageId` to the configured expected ID. A named image
   can be recreated; a name readback is insufficient. Stop on mismatch. The
   worker body is a review artifact, not a safe single-step creation command.
3. Verify material provenance and protected source/rootfs/runtime/init/lock hashes
   on the actual worker. Install/configure only the reviewed production supervisor
   after that separate implementation is accepted. No startup script is emitted
   by C24. The guest receives no credential, private config, host mount or socket.
4. Configure only the reviewed beta DNS record, load balancer and certificate.
   Preserve apex/main/www records and existing legacy bindings. Verify exact Host
   forwarding, TLS, direct-serving URL denial and same-origin API behavior. Do not
   attach controller or experimental worker paths to the public load balancer.
5. Enroll independent OAuth and session/internal signing material. Require exact
   callback, v1-only issuer/audience, host-only Secure/HttpOnly cookies and CSRF
   origin policy. Read actual legacy cookie scope and prove beta never accepts
   its cookies. Test sibling/main-origin mutations, login/logout, role revocation
   and independent sessions without modifying legacy identity configuration.

## 3. Staged availability and health

The current static frontend and fake C20 queue are unavailable production
implementations. Before enabling any capability, accept the actual v1 auth/proxy/
bootstrap host, real authenticated Cloud Tasks adapter/outbox consumer and private
controller endpoint, and the experiment supervisor lifecycle in their owning
components. Never substitute a preview, local fake or synthetic operator harness.

Bring up read-only catalogue/investigation/evidence access first using synthetic
data and current authorization. Missing wiring returns unavailable; no legacy or
fixture fallback is permitted. Keep research and experiment dispatch off. Queue
creation does not pause dispatch: explicitly pause it and verify state before
producer setup; retain producer/consumer flags off even if the queue is empty.

Before research activation, test exact task audience/identity, duplicate delivery,
outbox ACK uncertainty, current owner authorization, epoch fencing and shared
180-second/12-action/one-repair budgets. Before experiment activation, test genuine
C22 approval/reservation, one-use start, resource readbacks, signed physical
termination, independent proof and release on the new host. Queue concurrency
does not replace the global database reservation. Two concurrent sandboxes require
measured CPU/memory/PID/descriptor/scratch/log/output overhead acceptance; advertised
machine shape and capacity arithmetic are not measurements.

Health reports bounded operational identifiers: boot ID, accepted source/material
digest, held lease epoch/journal head, active reservations and drain state. Logs
must obey configured byte and retention limits and exclude secrets, code/input
bytes and private questions/results. Missing health or stale material stops new
claims; it must not rewrite terminal rows or release uncertain capacity.

## 4. Drain, uncertainty and recovery

Disable new experiment and research dispatch in the actual host and producer;
pause/read back the queue. Preserve authorized status/history/cancel/download
access as allowed by current permissions. Do not delete outbox rows, reservations,
approved inputs, evidence, retained artifacts or pending work to make health green.

For each active experiment, request cancellation through the retained contract,
retain the original boot/lease and cgroup identity, and wait for trusted complete
subtree cleanup. Retain durable terminal state, full wrapper/journal references,
the physical signed packet and independent proof before the narrow atomic release.
Owner revocation must deny publication while allowing verified cleanup/release.
Elapsed timeout, stopped VM, absent process, lease expiry or unacknowledged delete
alone never authorizes release. Lost commit/start/signing ACKs are not retry permits.

Queued/pre-start cancellation, reboot/power loss, loss before packet retention and
terminal observation reconstruction retain C23's unsupported capacity-held
qualification. Isolate a failed host, disable claims and preserve its state for
the explicitly supported reconciliation path. No force-release or reconstruction
command is supplied. A replacement host cannot assume old boot authority.

## 5. Backup, retention and v1 rollback

Rehearse private backup and isolated restore with synthetic v1 data, retained
investigations/approvals/reservations/evidence/results and exact migration/source
versions. Measure the chosen RPO/RTO; configured minute values are objectives.
Keep holds and provenance/withdrawal decisions effective across object lifecycle
and access changes. No destructive result TTL or production restore is emitted.
Any real approved-data transfer needs its separate source/cohort/authority and
quarantine manifest procedure; no accounts, credentials or history are copied.

Rollback disables v1 dispatch/entry points or restores an actually verified
compatible v1 revision while retaining data and terminal evidence. Use additive
migration compatibility; do not downgrade populated tables. If no compatible
revision exists, keep v1 unavailable until repaired. Preserve the previous v1
image/config manifest for recovery. Never use legacy DNS, storage or database as
a fallback/rollback target. C26/C27 must record integrated acceptance and a separate
release decision before public beta promotion.

## Gate receipt requirements

For each rendered gate, record exact input/config hash, source/image/material IDs,
actual target/project/boot, operator authorization, command/tool and timestamp,
raw observation hashes, outcome and cleanup. Missing/failed/not-run evidence is
not a pass. Preserve C23's original accepted receipts and failed qualifications.
C24's local completion is independent of these later live deployment gates.
