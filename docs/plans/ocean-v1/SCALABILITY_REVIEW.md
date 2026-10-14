# OCEAN v1 scalability review

Reviewed: 2026-10-13 JST. Planning assessment only; no application or load tests run.
Checkout reviewed: main at a73ea7fa48b88fe91995fda0cc25e481e63a9355, with existing
uncommitted work preserved. No live infrastructure or provider capacity inspected.

## Conclusion

The architecture can support growth without a fundamental rewrite, provided the
gaps below are resolved during component planning and implementation. It is not
yet evidence of a particular data volume, throughput or supported user count.
Stable identities, source adapters, immutable snapshots, typed operations and
separate durable execution are appropriate foundations. Merely using these
patterns, Cloud Run or pagination does not establish capacity.

| Growth dimension | Assessment | Main condition |
|---|---|---|
| More datasets from the four supported families | Structurally supported | Incremental registration/sealing, indexed metadata and bounded scans must replace full-corpus reads on request paths. |
| A genuinely new source family | Extension is feasible, but onboarding is not fully specified | Define an adapter registration contract and compatibility tests; acquisition, normalization and scientific review remain separate work. |
| More published results or new analysis methods | Partly specified | Add a versioned operation/workflow registry, eligibility rules and independent numerical fixtures. A generic Python sandbox alone is insufficient. |
| More concurrent researchers | Horizontal growth is plausible, but capacity is unverified | Coordinate database pools, model quotas, request admission, queue limits and process memory; benchmark the assembled system. |
| More concurrent experiments | Deliberately constrained in v1 | D29 permits one active experiment per user and two globally. More machines alone cannot remove that policy limit. |

This review originally assessed the 27-component plan. The later 2026-10-13
amendment adds P00 and D36–D38 for UI-first delivery and an isolated second site;
read [SITE_SEPARATION.md](SITE_SEPARATION.md) and [UI_UX_BRIEF.md](UI_UX_BRIEF.md).
Its data/analysis/user-scale findings still apply to v1. Legacy serving limits are
historical references, not the new site configuration. The recommendations retain
scientific qualifications and the current implementation boundary. They are
review recommendations, not newly accepted capacity promises or permission to
start components. Resolve the essential refinements within their owning
component plans.

## What the current plan already gets right

- C08/C14 share canonical identities, cursor pagination and access-aware totals
  between humans and agents. C16 plans bounded browser rendering.
- C09 separates immutable data versions from the latest pointer, retaining
  reproducibility while C03 protects references and holds.
- C10–C13 separate source semantics and supported operations. Query readiness
  does not depend on embedding every new record.
- C17/C20 retain investigation state outside a serving process, use transactional
  outbox/leases and recover after interruption.
- C22–C24 separate approved experimental computation from request serving,
  enforce resource limits and retain reproducibility evidence.

These are design commitments in the specifications, not implemented capabilities.

## Findings and required planning refinements

### S01 — Separate catalogue size from data size

The 100,000-object fixture in C08/C14/C16 verifies inventory reachability. It
does not measure underlying row counts, bytes, large individual datasets, update
frequency, skew or simultaneous users. C26 currently has no numeric throughput
or latency target; G3 explicitly leaves performance thresholds to measurement.

In C08 and C26, define a workload manifest containing object count, row counts
per source, compressed and decoded bytes, partition sizes, filter selectivity,
update frequency, retained versions, permission distribution and concurrent work.
Test metadata navigation independently from raw-record aggregation. Use the
proposed profiles below to start discussion; freeze targets before acceptance.

### S02 — Bound memory and work per request

Existing [Parquet helpers](../../../api/main.py#L1018) load full DataFrames and
cache them by entry count. This is a legacy implementation reference, not a
scalable default for the new adapters. A 500-row response can still require
reading gigabytes, and multiple instances each duplicate an in-process cache.

C09–C14 should specify partitioned immutable files, projection of needed columns,
predicate filtering, batch scanning, cancellation, scan/time/memory budgets and
byte-bounded caches. Use Pandas only after a bounded selection or for algorithms
whose working set fits the declared envelope. Some exact aggregates can stream;
joins, sorts and high-cardinality groups may need a separately budgeted execution
path. Refuse or return an explicit partial/unavailable outcome when an operation
cannot finish; do not silently sample or label an incomplete result exact.

Keep a queryable metadata index for IDs, parents, names, facets, snapshot membership
and eligibility, so opening a directory does not scan every raw file. Define
stable cursor ordering and the indexes that support it. Cache aggregate results
by snapshot, operation version, scope and current effective access; avoid an
expensive new full scan for every tree click. Do not introduce a warehouse or
distributed compute engine until measurements justify it.

This approach fits the pinned PyArrow 23.0.1 dependency: its Dataset API supports
multi-file data, filtered/column-selective reads and batch iteration. Materializing
an entire table can still exceed memory. [Apache Arrow 23 documentation](https://arrow.apache.org/docs/23.0/python/dataset.html).

### S03 — Make additions incremental and schema changes explicit

C09 already has content-addressed objects, export registration and generation
checks. It does not yet define the cost of frequent additions or schema evolution.
Do not recopy every unchanged byte or recompute every summary for each new dataset.

Specify reusable immutable partitions, a changed-input manifest, generation-bound
metadata/summary updates, atomic activation and reference-aware garbage collection.
Document how a large consistent export avoids an unbounded database transaction;
any incremental capture must retain the same no-mixed-generations guarantee.
Test append, correction, withdrawal, interrupted sealing, mixed schema versions,
and old investigation reopening. Old snapshots keep their original schema and
operation identities. Measure capture duration, bytes rewritten and retention
growth, including held snapshots that are intentionally ineligible for deletion.

In C08/C09/C14, define a source adapter descriptor: source/schema versions,
canonical identity, export requirements, eligibility, units/counting entities,
supported operations and compatibility checks. Demonstrate registration with a
synthetic extension fixture without modifying the browser or controller dispatch.
That fixture does not add a real fifth source to v1. New acquisition pipelines,
large backfills and production scientific approval remain separate work.

### S04 — Make analysis extension a versioned interface

C13 describes workflows and published results; C22/C23 describe approved Python.
Neither currently spells out a general registration lifecycle for new methods.
The existing [statistics catalogue](../../../orchestration/statistics_catalog.py#L5)
uses a fixed capability mapping and rejects more than 100 analysis choices.
C08/C13/C14 already intend to replace bounded discovery; preserve that intent
without simply deleting protective limits from the legacy path.

Define an operation/workflow descriptor in C08/C13, dispatched through C14/C19:

- Stable method ID and version; parameter and input/output schemas.
- Supported source/schema versions, scope/eligibility rules, units, missingness,
  sample pairing and scientific limitations.
- Execution class: deterministic query, published result or approved experiment.
- Resource estimate, cancellation behavior, environment identity, provenance
  receipt fields, independent numerical fixtures and deprecation behavior.

The generic browser should render supported table/plot outputs from these
contracts; specialized interactions can still require UI work. Pin method and
environment versions in receipts. A new pinned scientific image goes through
build/review/containment checks; installing packages inside a running experiment
remains disallowed. Unsupported R, GPU, external-network or unpublished-data
methods remain outside v1.

Extension acceptance should add one synthetic operation through registration,
exercise it through API/tool/UI contracts, reject incompatible inputs and reopen
an old result after a new method version exists. This is a local fixture, not
scientific approval of a new real-world method.

### S05 — Reconcile full inventory with bounded agent actions

At 500 objects per listing page, 100,000 objects require 200 calls; at 100 per
page, they require 1,000. C19 permits only 12 tool actions. Even a perfectly
paginated catalogue cannot support a broad question by making the model visit
every leaf within that budget.

C08/C14/C19 must define server-side full-scope queries, hierarchical summaries
and retained coverage receipts. Keep large membership/disposition sets on the
server, with bounded references in model context. A receipt must show which
population and operation were completed; a summary cannot prove that every
possible scientific question was answered. Questions requiring individual
inspection beyond the budget return explicit partial results or a linked
continuation. Navigation must remain exhaustive even when a run is partial.

Test a whole-inventory count and a late-page target within the existing action
budget, plus an intentionally unfinishable question that correctly stays partial.
Do not solve this by silently raising the budget or restoring a top-k cutoff.

### S06 — Coordinate user concurrency across every bottleneck

The checked-in [service template](../../../deploy/gcp/service.template.yaml)
and [dated deployment guide](../../../deploy/gcp/README.md) retain maximum one
instance and concurrency 20. These are not freshly verified live settings and
do not mean 20 people or 20 research runs are supported.

[Database configuration](../../../config.py#L154) defaults to a pool of five plus
two overflow connections per engine. Autoscaling duplicates those pools. Inventory
all engines, processes, controllers and background clients and budget approximately:

    sum(instances × processes × engines × (pool_size + overflow))
      + other database clients + operational reserve
      <= verified database connection capacity

Leave headroom for deployment overlap, failures and platform behavior. No serving
request should retain a database connection while waiting for a model response.
Test pool exhaustion and recovery, statement timeouts, bounded thread offloading,
event-table indexes and polling load. The existing PostgreSQL-backed limiter is
shared already, but its [route policies](../../../api/rate_limit.py#L27) do not yet
cover the proposed catalogue/research endpoints.

C14/C20/C22 need explicit admission limits per identity and globally, bounded
queue backlogs, fair scheduling, expiry/cancellation, retry budgets and protection
for short catalogue requests while expensive work is running. Keep control actions
such as cancel responsive under overload. Coordinate dispatch with provider
request/token quotas and approved operating budgets; registered user count alone
cannot determine capacity. C24/C27 should record these configuration inputs and
capacity calculations without applying cloud changes.

Cloud Run concurrency must match the application's parallelism and memory use;
Cloud SQL requires bounded pools; Cloud Tasks provides rate/concurrency controls
and may redeliver tasks. These support the planned architecture but do not remove
its bottlenecks. [Cloud Run concurrency](https://docs.cloud.google.com/run/docs/about-concurrency),
[Cloud SQL pools](https://docs.cloud.google.com/sql/docs/postgres/manage-connections),
[Cloud Tasks limits](https://docs.cloud.google.com/tasks/docs/configuring-queues),
[duplicate execution](https://docs.cloud.google.com/tasks/docs/common-pitfalls).

### S07 — Treat experiment capacity as an explicit product limit

With two slots and jobs taking the full ten minutes, ideal throughput is about
12 jobs/hour before input staging, output validation, failures or other overhead.
For 20 simultaneous ten-minute jobs on an initially idle worker, the last pair
starts after about 90 minutes and finishes after about 100 minutes, even with
perfect scheduling. Shorter jobs can yield higher throughput; this is a scenario,
not a measured capacity result or universal upper bound.

C22/C24/C25 should expose queue state, capacity rejection and cancellation,
bound pending jobs and prevent one user monopolizing the queue. Two 4-GiB sandbox
limits require host memory above 8 GiB once the supervisor/OS and headroom are
included; storage staging and CPU contention also need measurement. Worker drain,
restart and recovery are planned, but multi-host availability is not established.

Future worker-pool expansion is possible through the supervisor/executor contract,
but requires an explicit D29 capacity decision, measured resource/budget changes
and preserved transactional reservations. Large cohorts above 256 MiB, jobs above
ten minutes and GPU/R workloads are not supported simply because more users join.

## Proposed validation profiles

These are starting workload proposals, not user-approved SLOs or achieved results.
Catalogue objects, data rows, simultaneous browsers, active research runs and
executing experiments are different measures. Establish actual data bytes,
hardware, provider quotas and arrival rates before freezing acceptance targets.

| Profile | Catalogue/data fixture | Browser/research/experiment load | Purpose |
|---|---|---|---|
| Pilot | Existing 100,000-object gate plus representative wide/narrow tables and a dataset whose decoded size exceeds the per-query memory budget | 25 browsing sessions, 5 active research runs, 2 experiment slots | Candidate v1 sizing exercise; verify bounded memory, isolation and completion semantics. |
| Growth | Same object count with 10× rows/bytes and skew; a separate 1,000,000-object metadata stress fixture | 100 browsing sessions, 20 active research runs; experiment slots remain 2 | Find the next bottleneck; larger profile is not a new v1 commitment. |
| Overload/recovery | Pilot data with cold caches, provider throttling, restart and database pressure | Twice the pilot arrival rate, bounded backlog and cancellation | Verify graceful admission/rejection, recovery and fair access. |

For an illustrative browser workload, use one action per session per ten seconds,
with 60% list/search, 20% node open and 20% metadata/coverage. Poll each active run
every two seconds with jitter/backoff: pilot browsing plus polling alone is about
5 requests/second; growth is about 20, before tool execution and other traffic.
Specify research/experiment arrival rates and service-time distributions separately.
Five active runs is not five run submissions per second. Use fake providers for
local load work; live provider latency and quotas require separate evidence.

Candidate pilot targets to refine: p95 warm metadata API latency at most one
second; p95 durable run-admission latency at most two seconds excluding execution;
memory below 70% of configured instance capacity at sustained target load;
fewer than 1% unexpected server errors. Report cold-start latency, queue wait,
execution duration and expected capacity rejections separately. Exact queries
need operation-specific latency/scan budgets, not a blanket one-second promise.
No lost committed work, cross-owner leaks, incorrect totals or false completeness
is acceptable regardless of latency. Measure cold/warm caches, a 30-minute steady
run and a longer soak before making a sustained-capacity claim.

Track request p50/p95/p99, database connections/wait time, bytes scanned, peak
memory, cache bytes/hit rate, oldest queue age, model throttling/tokens, retries,
cost per completed run, snapshot bytes rewritten and retained storage growth.
If pilot targets require a different storage/query engine or major redesign,
revise the affected component plans before implementation.

## Ownership and decision gates

| Refinement | Primary components | Evidence required before a scale claim |
|---|---|---|
| Workload contract and extension descriptors | C08, C13 | Frozen workload manifest, synthetic source/method registration and compatibility fixtures |
| Incremental snapshots and bounded data access | C09–C14 | Append/schema/withdrawal parity; memory and bytes-scanned measurements |
| Inventory completion within run budgets | C14, C19, C21 | Full-scope receipt and partial-answer cases at 100,000 objects |
| Admission, database/provider budgets and fairness | C14, C17, C20, C22 | Multi-process concurrency, quota/retry/pool exhaustion and queue recovery evidence |
| Experiment capacity and usable queue states | C22–C25 | Real containment plus bounded admission, cancellation, drain and concurrency evidence |
| Combined load and operating envelope | C26, C27 | Recorded hardware/settings, results, bottlenecks, supported envelope and pending live gates |

Before C08 implementation, agree the pilot workload and extension contracts.
Before C14/C20 implementation, choose scan/admission/pool budgets from those
targets. Before C26 acceptance, freeze the measurement protocol and thresholds.
Production capacity remains unverified until the intended environment is tested.
P00 was later explicitly selected for local prototype implementation; C01–C27
remain Not started. This review neither satisfies their gates nor changes the
accepted limits. Planning may proceed with the documented conditions.
