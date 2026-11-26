# B4 operations acceptance

The signed-in scheduled recovery trial passed. Two Scheduler callbacks
enqueued the exploration and answer while both were pending in SQL, and Cloud
Tasks delivered each to the existing private controller. The restored B2 API
reopened the cited result at generation 73. The queue and the single trial
job are paused, and the queue is empty.
[Scheduled trial receipt](research-sweep-live.json).

Use the [bounded trial receipt](research-trial-live.json) for the successful
automatic exploration, cited answer and restoration. The November 24 provider
readback before the scheduled trial passed the restoration guard. The private
controller is generation 10 and accepts the exact existing task invoker. The Tokyo Research queue was paused
and empty. It permits one concurrent dispatch, ten attempts, an hour of retry
duration, and 30 to 300 seconds of backoff. Scheduler had zero jobs.

## Research recovery

The serving-only trial accepts `sweep_only: true` to commit a normal question
or answer without the immediate enqueue. Use this together with exactly one
exploration and one answer admission in a short UTC window. The controller
already exposes the private `POST /internal/research/dispatch` endpoint. It
authenticates the pinned Google invoker and enqueues at most one pending
exploration and one pending answer per invocation. The SQL records remain the
authority. The client still requests the answer through **Prepare answer**.

1. Qualify the source and image. Confirm restoration material and check the
   current serving template, controller identity and ingress, paused queue and
   empty Scheduler inventory. Stage the bounded serving API revision with an
   opening time that allows the previous request envelope to drain. Run the
   existing counts-only observer once after drain. Require zero active work
   and dispatchable outbox items before the test.
2. Use one Tokyo Scheduler job with the existing pinned invoker and exact
   controller `run.app` audience. Use HTTPS POST, content type
   `application/json` and body `{"version":"research-cloud-dispatch-v1"}`.
   Configure zero Scheduler retries and a finite set of cron slots within the
   trial window. The job's deadlines must fit within the controller timeout.
   The private Cloud Run ingress and IAM must stay intact.
   [Cloud Scheduler private invocation](https://docs.cloud.google.com/scheduler/docs/creating#invoke-target-services-that-are-restricted-to-internal-ingress).
3. Submit one deterministic count question in the signed-in beta. Confirm its
   accepted queued status and zero task deliveries before the applicable cron
   slot. Observe the Scheduler sweep and automatic canonical task delivery
   without a manual task run. Repeat at answer preparation. Verify the
   independent expected count and citation after reload. Record Scheduler,
   queue and controller outcomes with aggregate status and latency.
4. Pause the schedule and queue after the test. Verify zero remaining tasks
   before restoring the earlier API configuration. Reopen the saved answer
   on the restored revision and pin the restoration receipt. If outcomes
   are uncertain, close admission and retain the original work and evidence
   for reconciliation.

The disposable application test injects a lost create acknowledgement for
both task kinds and recovers each with an exact Cloud Tasks FULL readback
after a conflict. It repeats the scheduled sweep and both deliveries against
the original identities. The test uses a synthetic transport and zero model
calls. The earlier B1 receipt records the scoped live lost-ACK and duplicate
cases. [B1 recovery result](../b1-20261114/current-image-recovery-result.json).

The existing sweep handles pending outbox rows. If Cloud Tasks exhausts
retries after an outbox row is sent, the row needs operator reconciliation.
Treat a task name tombstone without a matching durable terminal outcome as
unresolved. Preserve the original work and model-attempt journal. Alert and
verify the operator recovery path for this case before sustained operation.
[Cloud Tasks retry behavior](https://docs.cloud.google.com/tasks/docs/configuring-queues).

Use `python -m scripts.beta_b4_delivery_diagnostic --kind run|answer --work-id UUID`
in the separately authorized beta observer environment for one affected work
item. The tool needs the existing beta PostgreSQL diagnostic binding and a
principal with FULL read access to the canonical task. It reads the current
outbox delivery and lease in SQL before and after a single Cloud Tasks GET.
The report contains delivery state, the count of prepared model steps and a
hash of the task name. Exit 3 means review the disposition. Exit 2 means the
readback failed.

For a missing sent task with unfinished SQL, leave admission closed, verify
queue and Scheduler state, and correlate the retained delivery and provider
attempt history. Lease expiry fences durable publication. Physical provider
termination still needs its own evidence. An authorized owner can cancel the
original work through its existing Research action once the operator has
reconciled the outcome. Preserve the original outbox and model journal. Use
current source authorization and the normal admission and budget checks for
any separately authorized continuation. The diagnostic runs no replacement
task. The live exhausted-retry case still needs a bounded trial.

## Alerts and hosted restore

The November 26 alert delivery test passed. The three operational policies
are enabled and the dedicated test policy is disabled. The counts-only outbox
signal and the integrated recovery checks remain open.
[Live Monitoring receipt](../b4-20261126/monitoring-live.json).

### Counts-only outbox observer

The observer reads one PostgreSQL repeatable-read snapshot and emits counts
for explorations and answers. It counts active work with no current outbox,
inconsistent outbox timestamps, and unleased work with a pending outbox at
least 10 minutes old or a sent outbox at least 65 minutes old. The sent
threshold covers the observed one-hour retry duration and the four-minute
task deadline, with a minute of margin. It reports age only. Use the exact
delivery diagnostic and provider history to investigate retry exhaustion.
Waiting and terminal work, superseded exploration inputs, and valid active
leases do not contribute aged counts. A failed query emits a fixed failure
state without details from the driver.

For a separately authorized live check, render the exact source with
`python -m scripts.beta_b4_outbox_trial --revision FULL_COMMIT --output PRIVATE_PLAN`.
Verify the existing generation-1 observer before launching. The plan replaces
the diagnostics arguments for one execution and leaves its image, SQL binding,
proxy, network, timeout and retries intact. The operator records the intent
before the provider request, then compares the execution's complete configuration
and its aggregate log with the source-bound plan. An uncertain launch requires
readback before any retry. [Cloud Run execution overrides](https://docs.cloud.google.com/run/docs/execute/jobs#override_job_configuration_for_a_specific_execution).

Review the [disabled alert definition](../../../../../deploy/gcp/beta/b4/outbox-health-alert.json)
against actual observer logs before binding the verified channel. A healthy
one-off sample verifies only the sampler and its log shape. It does not verify
incident delivery, detect a sampler that never ran, or qualify a periodic
production sampler. Those checks and their separate deployment scope remain
open before unattended delivery.

The November 24 beta metadata readback found zero Monitoring alert policies
and zero notification channels. Configure an owned, monitored project channel
and verify delivery of a test incident. Cover repeated private dispatch errors,
a sustained Research queue backlog, and backup/recovery failures. A queue
depth alert alone cannot detect an outbox item that never reached Cloud Tasks.
Verify the counts-only SQL outbox check and escalation alongside those alerts.
Record measured load and the beta-only cost readback before leaving sustained
delivery enabled. Use the existing ¥50,000 monthly beta target.
[Cloud Tasks monitoring](https://docs.cloud.google.com/tasks/docs/monitor).

The November 24 metrics readback returned time series for the exact Tokyo
queue depth, task attempts and private controller requests. The seven Cloud
SQL backup audit records reported `STATUS_SUCCEEDED`. Start with the following
policy scopes and verify their behavior on the selected notification channel.

| Signal | Draft policy |
| --- | --- |
| Queue backlog | `cloudtasks.googleapis.com/queue/depth` for the beta project, Tokyo location and `ocean-v1-beta-research` queue, above zero continuously for ten minutes during normal delivery. Review planned queue pauses separately. |
| Research delivery error | Cloud Run request logs for HTTP 5xx on the private controller's `/internal/research/dispatch`, `/internal/research/run` and `/internal/research/answer` POST routes. Repeat notifications are limited to one per 30 minutes. |
| Backup failure | Cloud SQL system events for `ocean-v1-beta-sql`, method `cloudsql.instances.automatedBackup`, and window status `STATUS_FAILED` or `STATUS_SKIPPED`. Check through the successful backup audit signal as well. |

[Cloud SQL automated backup audit fields](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/view-audit-logs-for-automated-backups).

The three staged policy definitions are in
[`alert-policies.json`](../../../../../deploy/gcp/beta/b4/alert-policies.json).
The operator selected their existing university inbox. After operator sign-in,
list channels and policies in the beta project, reuse an exact channel if it
exists and verify its service-side state. Bind each definition to the exact
channel resource and read it back disabled before activation. Compare metric
and log filters against the existing signals. Verify notification by emitting
one synthetic log under a dedicated test log name with a separate, rate-limited
test policy. Record receipt of the test message and disable the test policy.
Then enable and read back the three scoped policies. Keep the recipient and
any message content in the operator's private records.
[Cloud Monitoring policies and notification channels](https://docs.cloud.google.com/monitoring/alerts/using-alerting-api).
[Log-based alert testing](https://docs.cloud.google.com/logging/docs/alerting/log-based-alerts).

The same readback found seven successful automated beta Cloud SQL backups,
seven days of retained point-in-time logs and a private PostgreSQL 16 instance.
The isolated B3 worker network has no service peering. The live beta network
has service peering. A hosted restore needs its own approved, isolated
destination, with no access from the live serving or worker identities and no
public IP. Confirm private networking and an operator verifier before starting
the restore. The live instance and catalogue control stay read-only throughout
the drill. Prefer a synthetic Cloud SQL rehearsal if the safe destination or
scope for a real beta backup has yet to be confirmed.

Use an approved backup or PITR timestamp and the exact source instance. Record
the latest verified durable marker recovered and its gap from the selected
failure timestamp. Measure time from restore initiation to application-level
verification. Reconcile the current catalogue control before exposing restored
reads. Check retained evidence and denial of a source withdrawn after the
recovery point, using a disposable fixture where the source mutation is needed.
Capture aggregate evidence and retire the isolated resources after acceptance.
[Cloud SQL PostgreSQL restore](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/restore).

### November 26 restore readiness

The operator readback found seven successful automated backups. The latest
completed at `2026-11-25T18:52:26Z`. The sole beta instance runs PostgreSQL 16
in Tokyo on `db-custom-2-7680`, with a 20 GiB disk and a private address. The
serving network has Private Services Access. The separate B3 network has no
service peering and its worker is stopped. The restore drill still needs a
target isolated from both networks and its own cost and teardown scope.

The next hosted rehearsal can use a disposable synthetic PostgreSQL 16 source
and restore target on a dedicated network in Tokyo. Use separate verifier
credentials, explicit private networking and encrypted connections. Seed a
retained receipt plus a recovery marker, take a provider backup, then add a
newer withdrawal in the fixture. After restoring, compare the recovered
marker to the backup point and apply the fixture's current withdrawal before
opening evidence. Record the latest recovered marker, restore duration,
access-denial checks and retirement of each temporary resource. That trial
would qualify the hosted procedure with synthetic data. Actual beta-backup
recovery requires its own approved source and target scope.

B4 also depends on recovery and drain on the integrated B3 production worker.
Reuse the accepted private synthetic lifecycle and local restore receipts.
The hosted restore, live alert test and integrated worker checks remain open.
