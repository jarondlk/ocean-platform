# Beta cost and capacity plan — 2026-11-01 JST

Scope: new `ocean-v1-beta-20261101` project only. The user selected an initial
¥50,000 target and asked to be notified before exceeding it; ¥100,000 is the
stated upper budget, not permission to silently spend past the initial target.
Existing legacy budgets/resources remain unchanged. **This is a conditional
spend envelope, not a verified Tokyo quotation or a whole-project hard cap.**

## Initial resource choice and sequence

1. Keep the empty project/foundation stage free of paid runtimes while local
   host/API acceptance is being completed. Root owns actual budget readbacks;
   this cost review performs no cloud calls or resource changes.
2. For the first persistent beta, quote a separate **zonal Cloud SQL Enterprise**
   instance, initially up to 2 vCPU/7.5 GiB with 20 GiB SSD and bounded growth,
   in Tokyo. Select the edition explicitly: PostgreSQL16+ defaults to Enterprise
   Plus. Do not accept that more expensive default or HA/replicas implicitly.
   Smaller dedicated capacity is an option only after actual DB latency/race
   acceptance; it must not weaken isolation. [Edition defaults](https://docs.cloud.google.com/sql/docs/postgres/editions-intro),
   [SQL pricing](https://cloud.google.com/sql/pricing?hl=ja).
3. Start the serving frontend/API sidecar and private controller with min0/max1
   per service and request-based billing. Bound aggregate billed CPU/memory time,
   retries and requests; max1 alone does not bound monthly spend. Assume no
   incremental free tier because Cloud Run discounts are shared by billing
   account. [Cloud Run pricing](https://cloud.google.com/run/pricing).
4. Add one global external HTTPS load-balancer path for beta only after the
   host is ready. Budget forwarding-rule/IP/DNS fixed charges even at zero
   traffic; quote processing and internet egress separately. The published global
   first-five forwarding-rule rate is $0.025/hour, or $18.25 at730hours, before
   other network charges. Avoid an unnecessary second HTTP forwarding rule.
   [Network pricing](https://cloud.google.com/vpc/network-pricing).
5. Use an **on-demand e2-standard-8 candidate** for bounded worker acceptance
   windows, never an always-on worker in this initial envelope. It must still
   pass two simultaneous fixed C23 jobs plus measured supervisor/host overhead.
   Do not reduce C23's limits, use a smaller unaccepted host, or substitute Spot
   preemption to make the estimate fit. No commitment/reservation purchase is
   proposed. Compute while RUNNING is charged even when idle; stopped disks and
   stored images retain separate charges. [VM billing](https://cloud.google.com/products/compute/pricing).

## Conditional monthly envelope

These are **procurement ceilings and usage allocations**, not Google unit
prices. An actual regional quote must fit each allocation before its paid
resource is created. The model uses730hours/month for fixed resources and zero
free credits/CUDs. The Bank of Japan's latest business-day observation was
157.55–157.56JPY/USD at17:00JST on2026-10-30. For stress planning use
**200JPY/USD plus10% contingency**, equivalent to220JPY per modeled USD. This
deliberately conservative conversion is not Google's JPY SKU conversion and
does not establish the actual tax treatment. [BOJ observation](https://www.boj.or.jp/en/statistics/market/forex/fxdaily/fxlist/fx261030.pdf).

| Allocation | USD ceiling/month | Stress JPY including10% reserve | Acceptance condition |
|---|---:|---:|---|
| SQL compute | 135 | 29,700 | Exact Tokyo edition/tier quote at730h is≤$135; no HA/replica |
| SQL SSD, retained backups/PITR | 10 | 2,200 | Actual20GiB plus chosen backup/log retention fits; cap growth without deleting held history |
| HTTPS LB, IP, DNS | 25 | 5,500 | Exact forwarding/IP/DNS quote fits; no extra idle network service |
| Cloud Run serving/API/controller | 15 | 3,300 | Aggregate active resources and requests stay within allocation; project service cap/readback plus scale controls |
| Worker compute | 15 | 3,300 | Quote≤$0.40/hour and≤37.5active hours/month, or a lower computed hour bound |
| Worker retained boot/material disk | 5 | 1,100 | Exact stopped/active disk and image storage quote fits |
| Registry, object storage, logs, secrets, tasks, builds and egress | 10 | 2,200 | Small synthetic cohort, explicit byte/request/build/egress allowances and actual quote |
| **Total conditional envelope** | **215** | **47,300** | **¥2,700 remains below initial target; no allocation is an actual quote** |

Example Run sizing arithmetic only: if the accepted Tokyo active-rate quote is
at most$0.000030/vCPU-second and$0.000004/GiB-second, 2vCPU+5GiB costs at most
$0.288 per billed hour. Its$15allocation permits about52aggregate billed hours
across the services, less request/startup/other usage charges. Replace these
proposed rate ceilings with actual JPY SKUs; do not mistake the Iowa-selected
tables rendered by the public page for a Tokyo quote. Any larger memory shape
required by the100k catalogue must be included before hosting.

Always-on worker operation is outside this initial plan: at the illustrative
$0.40/hour ceiling,730hours would consume$292/¥64,240 under the stress model
before SQL, hosting or storage. That is a scenario, not an observed Tokyo price.
Notify the user and revise the plan before promising continuous experiments or
raising the¥50,000 target. On-demand operation means experiment admission is
unavailable while the host is stopped until a supported start/preflight succeeds.

## Controls and stop conditions

- Establish an all-service beta-project alert budget at¥50,000, with early actual
  and forecast thresholds. Use lower service-specific Cloud Run limits consistent
  with its allocation. Record the exact project/scope/currency and readback;
  legacy-project controls provide no beta protection. Alerts-only budgets do not
  stop charges. [Budget behavior](https://docs.cloud.google.com/billing/docs/how-to/budgets).
- Current spend caps cover only a single project and a single eligible API
  service. Cloud Run is eligible; Cloud SQL and Compute Engine are not listed.
  Persistent compute/storage costs continue, enforcement can lag, in-flight work
  finishes and monthly caps reset automatically. Thus even a Cloud Run cap is
  **not** a¥50,000whole-beta hard limit. [Spend-cap limitations](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps).
- Before paid provisioning, retain exact Tokyo JPY SKU/calculator output for
  edition/tier, disks/backups, Run sidecar/controller shapes, load balancer/IP,
  egress, build and worker hours. Apply the whole-project envelope to gross costs
  without relying on credits. Review expected tax/FX treatment against the actual
  billing account. The public pages alone do not verify those live inputs.
- Prefer same-region small images and bounded synthetic objects. Registry free
  storage is shared at account level; model all retained bytes and any scanning,
  transfer or build charges. No unreviewed deletion/TTL of rollback images,
  held evidence or scientific outputs is proposed. [Registry pricing](https://cloud.google.com/artifact-registry/pricing).
- Meter worker active hours with a reviewed stop window, then verify trusted
  drain/physical cleanup/proof before stopping or releasing capacity. A timer,
  VM STOP state or exhausted budget never authorizes a reservation release.
  Retain disk/log/material evidence and account for its continuing cost.
- Stop new admission and review at projected spend approaching the allocations
  or¥40,000gross beta total. Notify before a forecast or required change exceeds
  ¥50,000; do not wait for a delayed billing report or silently use the¥100,000
  ceiling. Never disable legacy billing or delete retained data as cost control.

Unresolved: exact regional JPY quotes, expected traffic/concurrent users, actual
API/catalogue memory, DB load/retention, backup volume, boot/image bytes, egress,
model usage and verified budget/cap readbacks. Consequently, feasibility below
¥50,000 is conditional; paid provisioning is not cleared by this document alone.
