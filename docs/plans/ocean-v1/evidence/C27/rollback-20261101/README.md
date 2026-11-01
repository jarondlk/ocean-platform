# C27 local flag rollback and drain — 2026-11-01 JST

**Passed for the recorded local synthetic boundary. Release acceptance remains false.**

`accepted/result.json` records actual C17/C20/C21/C22/C25 service and public API
worker-response checks on a new disposable SQLite store. It is bound to 119
executed/helper source paths and the accepted `afe9cb2` runtime. Its 11 targeted
existing regressions pass without failures or skips. Runtime source was not
changed. The local fixture stores were disposed and removed.

## Profiles and retained history

The dispatch-drain profile keeps `ENABLE_V1_CATALOGUE`, `CATALOGUE_BROWSER`,
`SHELL`, `INVESTIGATIONS`, `RESEARCH_RUNS`, `EVIDENCE`, `EXPERIMENTS` and
`EXPERIMENT_WORKSPACE` true. It sets `RESEARCH_CONTROLLER`, `RESEARCH_DISPATCH`,
`SYNTHESIS` and `EXPERIMENT_DISPATCH` false. All names here have the
`ENABLE_V1_` prefix. Exact maps are retained in the result.

This is a dispatch drain, not a global read-only switch: context/proposal editing
may still be possible. New execution/synthesis is denied. C22's current approval
closing preflight also requires dispatch availability; the profile grants no
new approval capability. Each flag has an independent strict boolean parser;
availability additionally requires actual bound services, same-site identities,
current authority and the corresponding dependency flags. There is no blanket
startup dependency validator which makes arbitrary combinations safe.

All 58 application/synthetic-port table hashes match exactly before and after
dispatch disable and the read/denial checks. These include retained investigation,
context, run/input/step/event, receipt/blob/protection, answer, proposal/approval,
input/file and experimental output records. Actual API workers reopen the finished
run, consecutive events, scientific receipt, prepared answer, exact proposal and
hash-validated experimental artifact while preserving its `authority=experimental`
label. No service or legacy fallback is added.

Disabling all 12 flags closes the tested runtime, C20 history, C21 evidence and
C25 artifact entry points while preserving all persisted rows. It is an emergency
unavailable profile, not the profile for keeping those reads online. Restoring
the same accepted code with the drain profile reopens exact saved run/answer
history without rewriting tables. No previous v1 binary was shown compatible;
the safe initial-release rollback is to disable v1 and retain its data.

## Cancellation, ACK uncertainty and replay

- An accepted queued C20 run and an actually claimed running C20 run are
  cancelled under dispatch disable. The old live lease is fenced and terminal
  duplicate deliveries return the same cancelled state without new execution.
- A synthetic queue accepts work then loses its ACK. Retry uses the identical
  delivery identity; two deliveries produce one committed controller step, and
  terminal redelivery invokes no new controller.
- A C22 fake executor accepts dispatch then loses its ACK. Reservation/outbox
  become uncertain and remain held, with identical table hashes when dispatch
  is disabled. Explicit same-candidate reconciliation uses the same delivery ID;
  the reservation remains accepted rather than released. No Python is executed.
- The existing retained-runner software checks preserve capacity under
  pre-start cancellation, missing original cgroup identity, changed boot,
  post-finish close/proof failures, uncertain release ACK and missing retained
  start. These tests explicitly mock Linux, DB admission and physical observations.
  They do not repeat or replace C23's actual Linux evidence.
- The actual legacy `/chat` regression uses synthetic retrieval/model responses
  and a real retained `ChatInteraction`. It passes with all v1 flags initially
  false, preserving the bounded answer/history/audit evidence contract.

Real authenticated hosting, Cloud Tasks pause/readback and outbox adapter,
supervisor cancellation/drain, physical termination/release, live backup/restore,
IAM/network isolation and traffic rollback remain unrun gates. A stopped process,
expired lease, timeout or retry is not physical termination proof or release
authority.

## Reproduction and preserved evidence

```sh
.venv/bin/python docs/plans/ocean-v1/evidence/C27/rollback-20261101/rehearse.py --output /private/tmp/ocean-c27-rollback-new
.venv/bin/python docs/plans/ocean-v1/evidence/C27/rollback-20261101/verify.py
```

Choose a new output directory; the harness refuses to overwrite an existing run.
`accepted/regressions.log.gz` preserves the raw subprocess log exactly and is
verified against the original logical log SHA in `accepted/result.json`.
`accepted/regressions.xml` retains the exact 11 testcase identities and outcomes.
The source manifest is the actual application/helper bytes, not a retargeted
historical receipt. `accepted.console.log.gz` preserves the final outer run and
the host's harmless Arrow `sysctlbyname` sandbox notices.

Two failed harness-only attempts remain qualified separately: attempt01 checked
a nonexistent artifact field instead of `authority`; attempt02 used the wrong
location when formatting a context hash after the shared assertions passed.
Their source snapshots/results remain failed, not acceptance. Neither caused
an application change. Only the final accepted result is a passing receipt.
