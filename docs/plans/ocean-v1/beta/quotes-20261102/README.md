# Public JPY beta price qualification — 2026-11-02 JST

The official Google Cloud Catalogue API returned current public **JPY** prices
for Tokyo (`asia-northeast1`) and the relevant global services. CLI authentication
was used only in memory; no access token, credential or secret was printed or
saved. These are public list on-demand/default prices, **not** negotiated account
prices, a bill, measured usage, or a whole-project spending cap. No paid runtime
or other cloud resource was created by this pricing task.

The selected 28 original SKU records, region, unit, exact money components and
effective time are retained in [selected-prices.json](selected-prices.json).
The quote's effective prices are `2026-11-01T07:00:00Z`; request capture times are
separate in the candidate receipts. Capture used the documented
[services.skus.list API](https://docs.cloud.google.com/billing/docs/reference/rest/v1/services.skus/list)
with `currencyCode=JPY`, rather than translating Iowa USD tables or relying on
account-wide free credits. The candidate receipts retain only relevant candidate
records from the fetched services, not the full catalogues.

## Conditional beta estimate

| Calendar scenario | Gross estimate | With 10% cost contingency | Headroom below ¥50,000 |
|---|---:|---:|---:|
| 730 fixed-resource hours | ¥31,871.84 | ¥35,059.03 | ¥14,940.97 |
| 31 days / 744 fixed-resource hours | ¥32,367.31 | ¥35,604.05 | ¥14,395.95 |

The contingency is a planning reserve; the account's actual tax treatment has
not been verified. All free tiers/credits and negotiated discounts are ignored.
Tiered SKUs use their highest captured unit price. Month-based SKUs report
`baseUnitConversionFactor` equivalent to **721 hours**; the calculation preserves
that reported conversion and prorates 730/744 hours accordingly. It does not
silently assume a 730-hour divisor for storage, zones or secret versions.

The estimate includes:

- A separate zonal PostgreSQL **Enterprise** instance with 2 vCPU / 7.5 GiB,
  20 GiB SSD, 20 GiB retained backup allocation and a separate 10 GiB log-storage
  allowance at the quoted SSD rate. That allowance is not a claim that every
  PITR implementation bills its logs as SSD. Actual configuration and retained
  bytes still need verification. No HA, replica, Enterprise Plus or extended
  support is selected.
- One global HTTPS forwarding-rule minimum, modest Tokyo processing, a DNS-zone
  allocation, 100,000 DNS queries and a ¥100 unused-address transition allowance.
  The latter is a procurement allowance, not an exact global-unused-IP SKU.
  Static external addresses assigned to forwarding rules have no separate
  address charge under [official network pricing](https://cloud.google.com/vpc/network-pricing#ipaddress).
  Reserve only when immediately binding the rule; verify its actual state.
- A ¥3,000 aggregate Cloud Run allocation, min0/max1 serving assumptions, and
  100,000 request-scale operation assumptions elsewhere. Run's service cap can
  lag and does not stop SQL, VM or storage charges. The estimate is conditional
  on observing usage and stopping new admission before allocations are exceeded.
- At most 37.5 active hours for an on-demand e2-standard-8 worker and a 50 GiB
  balanced disk. This is a disk scenario pending C23 image/staging/capacity
  qualification, not a decision to provision a worker or reduce accepted limits.
  A small ephemeral standard-VM IPv4 allowance is included if used.
- Two 20-minute e2-standard-2 builds, 5 GiB registry storage, 10 GiB object
  storage across live and retained/soft-deleted versions, 5 GiB log ingestion,
  8 single-region secret versions, modest storage/secret/task operations and
  10 GiB internet transfer at the highest selected Japan destination rate.

[cost-qualification.json](cost-qualification.json) contains the exact per-line
arithmetic for both scenarios and the complete conditions. Key rates include
SQL vCPU ¥8.495608499/hour, SQL RAM ¥1.439665499/GiB-hour, worker e2-standard-8
¥54.400826904/hour, global forwarding minimum ¥3.955124999/hour and Tokyo
global-application-LB processing ¥1.898459999/GiB in each direction. The
regional/global distinctions are preserved; a Tokyo regional rule is not priced
as a global rule.

This establishes price feasibility for the bounded usage scenario. It does not
establish actual catalogue memory, worker capacity, session/network isolation,
traffic, backup growth or release readiness. Models and real-data acquisition
or transfer are not selected or included. Re-quote before larger usage, machine
shapes, HA, always-on workers or paid add-ons; notify before a forecast exceeds
the user's initial ¥50,000 target. Keep the earlier conditional cost plan and
receipts immutable.

## Read-only verification

```sh
.venv/bin/python docs/plans/ocean-v1/beta/quotes-20261102/verify.py
```

The verifier checks captured artifact hashes and reproduces the deterministic
Decimal arithmetic without network access or credentials. Fetch scripts are
separate, require network/CLI access and refuse overwriting captured receipts.
