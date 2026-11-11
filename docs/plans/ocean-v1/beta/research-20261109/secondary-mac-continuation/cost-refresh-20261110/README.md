# Current JPY cost refresh — 2026-11-10 JST

The [refreshed review](cost-review.json) fits the bounded scenario at
**¥36,480.84/month**, including10% contingency, leaving **¥13,519.16** below the
¥50,000 target. Public prices are current readbacks, not a bill or spending cap.
No resources, logging settings, secrets or data were changed by this review.

The initial broad v1 catalogue request timed out without writing a price file.
The replacement [31 exact-SKU public requests](public-selected-jpy-prices.json)
all returned HTTP200 through the official Pricing API. The calculation selects
only Default consumption-model prices, normalizes each quoted quantity, and
ignores credits, free tiers, commitments and account discounts. Current unit
names match the earlier catalogue; fixed-hour month calculations retain its
captured721-hour conversion as a conservative scenario convention.

[Selected prices](selected-default-jpy-prices.json) give Gemini3.8 Flash gross
input ¥237.307499992/million and output ¥1,186.537499962/million tokens.
Preserve the ¥450 model-question reserve plus ¥50 cloud-validation allowance.
Run one model-backed question at a time, within20questions/¥500 total initial
validation. Reconcile complete usage before another paid question; unknown
usage retains the reserve. The reserve is not measured spend or a provider cap.

[Observed usage](observed-usage.json) estimates Cloud Run gross cost at ¥199.20
month-to-date, using public request rates conservatively across all jobs and
services. This is not invoiced currency. Its linear31-day projection is ¥687.37.
Build/registry usage remains within the240-minute/10GiB planning allowances.
The runtime sweep still needs measured duration, including amortized startup,
and must stay within the shared ¥3,000 Run allocation. The conservative gate
remains25average active seconds; this quote alone does not authorize resumption.

The [pre-model baseline](vertex-cost-before-model-20261110.json) has no Vertex
series through2026-11-09T23:36:52UTC (2026-11-10 08:36JST). Token/invocation/
weighted-throughput metrics and their descriptors all returned HTTP200. Native
input/output counters do not explicitly attest thinking-token inclusion;
weighted throughput is not priced as raw tokens. Exact question-window captures
will be recorded separately after the signed-in validation.
