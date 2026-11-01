# C27 readiness audit — 2026-11-01 JST

**Ready to implement C27's local release preparation. Not ready to deploy.**
The user selected preparation followed by implementation once prerequisites pass.
This audit verifies that prerequisite C26 is delivered within its documented
local deterministic and hosted software boundary. It grants no live release,
cloud provisioning, production migration, traffic change or real-data transfer.
Work remains on `overhaul`; scheduling remains paused.

## Accepted prerequisite and source

The selection checkpoint is `a69eb575ab9f11135778de052d27fa070ac3898e`.
Accepted software and workflow source is
`afe9cb2d1a6d2c28a834daab1a342de4563dc3a3`, verified by
[CI 41175282249](https://github.com/jarondlk/ocean-platform/actions/runs/41175282249).
The C26 evidence-only closure does not claim a separate tested application build.

Original functional source `e0874e0` and its report identity
`sha256:0345bb271e4510877a89169fc824afa4232a5333ba4b64c36ace689f33a828ca`
remain immutable. The explicit workflow-only amendment composes effective source
`sha256:b2107ecc0ac41f01cc9d3d8c694429b58094cd45f26b2522aa4fa7aa0d359d97`.
All 844 source pins match the accepted checkout; all 843 non-workflow source
paths match the original functional source. Browser and original C23 physical
source identities retain their original qualifications.

The independently rerun C26 read-only verifier passes. It binds hosted totals to
the retained raw logs and required job readback: 1 isolated scale case, 17 covered
integration cases and 6,694 remaining backend cases pass, with 626 explicit skips
and 83.64% combined coverage. PostgreSQL passes 318 actual cases with 16 expected
host-capability skips and isolated backup/restore. V1 and legacy frontends pass
1,051 and 132 tests, typechecks, builds and production dependency audits. The
existing local C26 report retains 1,604 passes, all 43 preparation rows, complete
100,000-object traversal and the qualified functional browser observations.
No unchanged application suite was repeated for this source audit.

All 18 C26 delivery proof hashes match. The new start record freezes the entire
prior evidence tree at the selection checkpoint:
`62f99a10e58023575eb1f8dd4404a762c3efe982`. All **5,368 tracked evidence files**
are verified by exact Git blob identity and mode; all **42 protected unrelated
and scientific files** retain their recorded hashes. This expanded baseline
includes C26's final delivery without replacing C26's earlier 5,141-file baseline.

## Actual migration and configuration state

AST inspection finds one linear Alembic history with 21 revisions, rooted at
`20260723_0001` and headed by `20261027_0021`. V1 additions `0017`–`0021` follow
`20261005_0016`. C27 must derive offline SQL and local rehearsals from these
actual revisions, preserve retained rows and prefer disabling v1 over destructive
downgrades. A compatible earlier v1 application revision may be named only after
actual verification; legacy application/database compatibility is not assumed.

The pending operator input is explicitly incomplete. Project/region, service and
image identities, credentials, stores, queue, worker material and operational
targets still need concrete configuration before live action. The working origin
is `https://beta.oceaninfobio.com`; it has no accepted DNS/TLS or hosting evidence.
`browser.cookie_domain=null` is the **required host-only cookie policy**, not a
missing value. Research and experiment dispatch remain false in the C24 input.
The temporary C23 project is not a whole-site default or rollback destination.

## C27 implementation checkpoints and acceptance

| Checkpoint | Required local evidence | Boundary |
|---|---|---|
| Candidate and requirement manifest | Freeze accepted code/workflow, exact C26 requirement/evidence references, independent v1 targets, feature-flag defaults and remaining gates | A local candidate package, no tag, published release or deployable-target claim |
| Migration review and rehearsal | Offline SQL from actual revisions; fresh and additive upgrades on an explicitly disposable local database; retained-history checks and partial-failure/retry evidence | Synthetic local resources only; no real backup or production migration |
| Rollback and recovery | Actual v1 flags, durable cancellation/retry and preservation of investigations, evidence and experiment history; unsupported physical recovery remains capacity-held | Local application semantics do not prove live Cloud Tasks or supervisor behavior |
| Operator package and verification | Preflight, rollout prerequisites, independent v1 rollback/drain, transfer/provenance/withdrawal procedure and source-bound evidence manifest | A separately authorized release decision remains required |

Drain and emergency unavailability must be distinguished. A drain disables new
dispatch and synthesis while preserving the actual flags/services required for
authorized retained reads and cancellation. Disabling all v1 flags makes those
entry points unavailable; it does not erase data and must not be described as a
working read-only mode. C22's existing approval preflight also depends on its
dispatch contract, so continued approval availability requires actual evidence.

Approved-data transfer instructions must require concrete eligibility/authority,
source/hash manifest, temporary transfer identity, quarantine/import validation,
origin provenance and withdrawal response. Accounts, credentials and private
legacy history remain excluded. Any actual copy is a later authorized operation.

## Gates retained without alteration

All 20 original C26 release results remain `not_run`: authenticated beta;
cloud queue; production worker port; IAM/network isolation; backup/recovery;
DNS/TLS; real-data/scientific validation; live model evaluation; release rehearsal;
and the following exact C24 gates:

- `whole_site_target_and_live_action_authorization`
- `authenticated_v1_host_proxy_and_bootstrap`
- `real_cloud_tasks_adapter_outbox_and_private_invocation`
- `production_experiment_supervisor_health_and_drain`
- `worker_boot_image_unique_id_and_disk_sourceImageId`
- `DNS_TLS_Host_OAuth_cookie_and_cross_origin_validation`
- `inherited_IAM_and_network_legacy_access_denials`
- `two_simultaneous_sandboxes_and_measured_host_capacity`
- `crash_reboot_uncertain_ACK_recovery_and_physical_proof_release`
- `independent_backup_restore_retention_budget_and_alert_readbacks`
- `C26_C27_integrated_acceptance_and_release_promotion`

C27 local rehearsal evidence is recorded separately from the immutable C26
release results. It cannot establish full live/operator acceptance of the
`release-rehearsal` gate. Open P2 **D26-07** remains: concurrent worker activity
can exceed the unchanged 15-second first automatic history deadline; explicit
Reload answers recovers. Automatic first-read latency and hosted concurrent
capacity are not accepted. Earlier native Python crashes retain an unknown cause.

These gates do not block authorized local C27 preparation. They prevent a release
or deployment claim. No predecessor repair, cloud sign-in, new live test or
scientific approval is required merely to start this bounded component.

## Reproducible read-only verification

```sh
.venv/bin/python docs/plans/ocean-v1/evidence/C27/readiness-20261101/audit.py --verify-only
```

The command checks the frozen evidence tree, protected files, C26 proof hashes
and verifier, exact source composition, pending gates, migration AST and C24
operator policy. It writes nothing and performs no cloud or application test
operation. [Start record](evidence/C27/readiness-20261101/start.json),
[verification](evidence/C27/readiness-20261101/verification.json),
[audit source](evidence/C27/readiness-20261101/audit.py).

Next authorized action: implement the local C27 manifest, migration and rollback
rehearsals and operator package; update the component status and handoff after
each checkpoint. Complete C27 only after its actual local acceptance passes,
with live release gates and preserved original evidence still explicit.
