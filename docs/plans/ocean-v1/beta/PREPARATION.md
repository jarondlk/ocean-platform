# Independent beta preparation — 2026-11-01 JST

**Offline preparation complete; runtime integration and cloud setup have not
started. GCP sign-in can wait.** The user selected preparation after C27.
Starting checkpoint `5b5afe7`; accepted runtime remains `afe9cb2`.

The working public origin is `https://beta.oceaninfobio.com`. This package adds
a concrete implementation sequence and operator worksheet without altering the
accepted C01–C27 boundaries or claiming the missing integrations already exist.

| Preparation | Deliverable |
|---|---|
| Actual integration gaps and first coding checkpoint | [Integration plan](INTEGRATION_PLAN.md) |
| Resources, identity boundaries and ordered cloud session | [Cloud plan](CLOUD_PLAN.md) |
| Exact pending C24 inputs plus separate proposed names/region | [Worksheet](cloud-worksheet.json) |
| Inspected source pins and current primary documentation | [Source audit](source-audit.json) |
| Original pending gates | [C27 release inventory](../evidence/C27/release-gates.json) |
| Read-only local check | [Verifier](verify.py) |

The proposed region/names are suggestions, not selected live configuration.
Project IDs/numbers, image/material identities, OAuth/secret references, target
capacity and operations values remain unresolved. The worksheet preserves C24's
pending input, including its deliberately null host-only cookie domain. It is
expected to fail deployment-input validation until actual values are supplied.

The first implementation checkpoint is an independently configured production
v1 host and read-only service bootstrap, with both execution dispatches off.
Cloud Tasks and the retained worker follow their own contract and acceptance
checkpoints. No provider account, GCP CLI, credential or browser sign-in is used
by preparation. Signing in later enables an account/project inventory; it does
not itself satisfy integration, runtime or release acceptance.

All 20 operational gates and P2 D26-07 remain unchanged. Existing C27 receipts
are immutable. No application code, dependency, deployment template, legacy
resource, data, DNS, IAM, billing arrangement or scheduled automation changed.
This is not an apply bundle, a deployment authorization or a new numbered CXX
component.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/verify.py
```

See [handoff](../handoffs/BETA_PREPARATION.md) for the next action and sign-in
boundary.
