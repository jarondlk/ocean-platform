# Production integration implementation plan

Status: prepared, not implemented. Local implementation can begin without GCP
sign-in after selecting the first checkpoint. Each change receives its own
source-bound checks; the original C26/C27 acceptance is retained as historical
evidence and is not retargeted to new runtime source.

## 1. Authenticated v1 host and read-only bootstrap

Current evidence: `frontend-v1/next.config.mjs` exports a static preview. Its
loopback preview server is not an auth server or production proxy. The actual
`/v1` discovery route requires trusted `V1RuntimeConfiguration` plus correctly
bound catalogue/investigation/evidence services; the C26 harness injects synthetic
ones. A live host still needs an explicit service factory and startup checks.

Implement a separate production host/build entry that reuses the v1 UI while
preserving the explicit local preview. Decide the concrete auth library/version
during implementation and audit its then-current official guidance. Legacy
`frontend/auth.ts`, internal-token helper and proxy are behavior references;
do not import their environment defaults, secrets, cookies or deployment.

Required boundaries: independent OAuth/signing material and application identity,
exact beta origin, host-only cookie, CSRF/Origin checks, trusted forwarded-header
handling, bounded allowlisted same-origin proxy, private API target and no fixture
or legacy fallback. Existing legacy user/provider/role semantics remain the
reference; accounts/history are not silently copied. Bootstrap the explicit v1
database/store/snapshot and host services; no migration or model call on ordinary
web startup. Specialist/admin/feedback capabilities remain unavailable until
their actual accepted services are wired; do not enable them by configuration.

Local acceptance before any hosting: real host/session/proxy paths with synthetic
OIDC/identity inputs; login/logout/revocation/role denial, wrong issuer/audience,
parent/sibling cookies, spoofed Host/forwarded headers, cross-origin mutations,
proxy path/header/body bounds, unavailable backend, no private data in cache/logs,
service-binding mismatch and production rejection of preview/fixtures. Repeat
catalogue/history/receipt/experiment-history UI journeys against actual local
service composition. Keep new execution, model synthesis and experiment dispatch
off. Address D26-07 through measurement rather than raising its UI deadline.

Outputs: source checkpoint, dependency/host build, exact config contract,
local acceptance receipts, versioned provider/runbook changes and remaining
live OAuth/session/isolation gates. No public host is claimed from local tests.

## 2. Research Cloud Tasks delivery and outbox consumer

Current entry points: `ResearchRunService` accepts an explicit queue with
`enqueue(run_id, delivery_id)` and a controller factory. `dispatch_outbox`
retains a stable delivery UUID around queue acknowledgement; claim/lease and
committed-step journal logic already exist. There is no real Cloud Tasks client,
authenticated private task HTTP entry or durable outbox polling lifecycle.

Implement a production queue adapter with explicit project/region/queue and
controller URL/audience/task identity. Task bodies carry only bounded typed
run/delivery identifiers; the server reloads canonical owner/context/snapshot
and current authorization. Reject caller-supplied code, private context, identity
or alternate endpoints. Preserve the same delivery identity on uncertain create
ACKs; provider deduplication is additional protection, not the durable authority.

Implement authenticated private invocation and a supervised outbox producer.
Choose and record the actual producer lifecycle; an autoscaled web daemon thread
is not a durable scheduler. Keep the provider service identity distinct from the
research owner and from the browser's internal token. Define precise HTTP/ACK
outcomes for terminal duplicates, active leases, stale generations, revoked
owners and retryable failures; never acknowledge an uncommitted effect as complete.
Preserve the 180-active-second/12-action/one-repair budget and cancellation fences.

Local acceptance: dependency-injected Cloud Tasks transport with exact request
assertions, wrong/missing identity/audience, malformed/oversized tasks, enqueue
ACK loss/duplicate creation, racing deliveries, committed-step replay, stale
epochs/input versions, owner revocation, expiry and shutdown/cancellation.
Provider-emulated tests do not prove actual IAM, ingress or Cloud Tasks delivery.
Use an isolated native database for durability/race acceptance where needed.

Live acceptance later: paused-queue readback, exact task identity/audience and
private ingress, duplicate delivery/ACK loss, actual outbox restart/drain and
bounded run completion. Real model calls remain a separately tracked gate.

## 3. Production retained experiment integration

Current boundary is substantive: `ResearchExperimentService` accepts only
`FakeExperimentExecutor`, and its approval/dispatch preflight is coupled to fake
availability. `ExperimentExecutionPort` provides durable status/events/cancel/
artifact access and explicitly cannot launch or release capacity; its workspace
capability has `start_enabled=false`. A deployment flag cannot supply execution.

Prepare a bounded owning-contract amendment before coding admission/start:
separate review/approval from the production dispatch capability; bind every
explicit start to owner, site, immutable proposal revision, approval, input/code/
environment/material hashes and a stable retry key. Preserve fake-only behavior
for explicitly identified tests. No proposal edit may inherit an older approval.

Use the existing restricted `C23RetainedBridge`, admission store/hooks and
`run_retained` lifecycle as the authority boundaries. Implement the durable
production read/cancel/artifact port and a supervised host process with health,
drain, cancellation intent, current boot/material/lease identity and restart
policy. New status/cancel reads cannot launch a job or release reservations.
Output publication must recheck owner authority and retain experimental labels.

Local acceptance: exact start/approval tamper/revocation, one-use admission,
reservation/global-owner races, cancellation intent idempotency, output hash/
format/access checks, supervisor shutdown, stale boot/material/lease and uncertain
ACK handling. Retain capacity for unsupported queued/reboot/pre-packet recovery.
Never introduce a force-release shortcut. Local physical mocks are not containment
or actual termination proof; preserve original C23 physical receipt qualifications.

Live acceptance later: exact new host/runtime/rootfs/init/source/image identities,
network/credential denial, resource readbacks, two-job measured overhead,
whole-tree cleanup, signed physical termination, independent proof and narrow
release. Do not treat a stopped VM, elapsed lease or an ACK as termination.

## 4. Integrated beta acceptance and release decision

Prepare immutable candidate images/config/material identities after the changes.
Repeat the relevant C26 numerical, inventory, access, UI and durable-history
checks against the integrated candidate; retain original receipts. Run the actual
C24/C27 live isolation/auth/queue/worker/backup/drain matrix on the selected target.
Perform separately selected scientific/real-data/model validation with observed
telemetry. Use the C27 rollback profiles with actual live readbacks and cleanup.

An explicit live release decision names the accepted receipts and exceptions,
target/image/config identities and rollback owner. Until then the beta remains
unavailable or restricted to the specifically accepted internal stage. Preparation
does not remove or relabel any of the original 20 release gates.
