# Main-Mac return audit — 2026-11-14 JST

[audit.json](audit.json) records the source/cloud inspection at second-Mac
checkpoint `7002312`, before the progress-plan documentation update. It contains
only selected non-secret metadata; raw service readbacks remain private.
No deployment or gate promotion occurred.

[plan-review.json](plan-review.json) records the documentation checks: all 20
original gate IDs, all 43 formal row IDs, local links, unchanged runtime pins,
exact manifest hashes/platform and credential-pattern/whitespace checks.

The exact registry response bytes are retained as [proxy-index.json](proxy-index.json)
and [proxy-linux-amd64.json](proxy-linux-amd64.json). Their SHA256 values equal
reviewed index `f333a9c59890c3c67b8505166c5dbdcc0b29fca9173a2e09ca0446ab6997a736`
and executed manifest `1d2285ce2ae05129166c2cf2eb9d481570ffd43b4755dab5384ad17ffa1194bb`.
The index names that exact child and declares `linux/amd64`. These were read
from the public `gcr.io/cloud-sql-connectors/cloud-sql-proxy` registry manifests;
anonymous pull credentials were not retained or printed.

This supplies the relationship evidence absent from the earlier observer guard.
It does not amend that guard or make expired quiescence/budget observations
current. The two original failed comparisons remain preserved.

[Completion plan](../BETA_COMPLETION_PLAN.md) and
[deployment handoff](../../handoffs/BETA_DEPLOYMENT.md) carry the next work.
