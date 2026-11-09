# Receiving Mac continuation — 2026-11-09 JST

Scientific recovery, checkout reconciliation and sign-in are complete. Research
activation is not yet live. The single failed PostgreSQL job is retrying in
[run42594709784](https://github.com/jarondlk/ocean-platform/actions/runs/42594709784);
actual successful PostgreSQL16 backup/restore is required before activation.
Unchanged backend and all three frontend successes on source `3cdecc0` are reused.

- [Checkout reconciliation](checkout-reconciliation.json): clean `ad0c313`
  fast-forwarded to `4f4b616`; older unrelated work is separately preserved.
- [Scientific recovery](scientific-recovery.json): exact archive/manifest and all
  35 members verified; durable owner-only restoration outside Git; replacement
  activation `4843e61b…` verified without changing scientific qualifications.
- [Cloud preflight](cloud-preflight.json): fresh explicit-project reads preserve
  live revision17, empty PAUSED queue, successful prior setup jobs, private
  encrypted PG16, zero controller credential versions and the full catalogue
  control audit chain. Personal Google and local GitHub CLI sign-ins succeeded.
- [Source and images](source-image.json): qualified immutable effective images
  reused from `handoff-amendment02`; no new build or provider call.
- [Cloud Run validation only](validation-only.json): both scoped job requests
  and the unchanged-traffic serving request received HTTP200 dry-run responses.
  No job, revision, IAM or activation change was persisted.
- [Activation review](activation-review.json) and [cost review](cost-review.json):
  the user authorized the concrete beta-only scope; prerequisite and live gates
  still apply. Current bounded31-day scenario is ¥36,480.84 with10% contingency.
  Reserve ¥450 before each actual model question and reconcile usage before
  another, within20questions/¥500 incremental validation. This is a planning
  reserve, not measured model spend or an enforced provider currency cap.

Only the new serving queue producer grant will be deferred temporarily during
initial acceptance. A zero-model count question must persist with no task;
applying that planned grant and manually invoking the correctly authenticated
private dispatcher must recover the same run. This avoids removing existing
grants. A paused queue alone does not prove pending-outbox recovery. Cloud Tasks
[manual task execution](https://docs.cloud.google.com/tasks/docs/reference/rest/v2/projects.locations.queues.tasks/run)
supports dispatch while a queue is paused, so bounded recovery, duplicate and
cancellation checks can precede normal queue resumption.

The runtime five-minute sweep starts paused and needs measured timing/cost
acceptance before resumption. Scheduler's state is output-only: create with a
verified future cron, pause/read back, then patch to the intended five-minute
cron while paused. The three-hour Codex schedule remains PAUSED. Legacy,
eDNA/ANEMONE, experiments and workers retain separate gates; scientific approval
remains false. Original receipts and scientific bytes are preserved.
