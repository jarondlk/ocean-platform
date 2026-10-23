# C23 temporary GCP test worker

Prepared 2026-10-23 JST on `overhaul`. The user said, “I see, then I approve all
gcp use.” This authorizes GCP setup, runtime installation, image preparation and
synthetic tests needed for C23. Earlier statements that provisioning lacked
authorization describe the older checkpoint and are superseded for this work.
The recurring continuation stays PAUSED. No cloud resource has been created.

The saved CLI login cannot refresh non-interactively; `gcloud auth login` is
required. Project/billing discovery failed before returning targets. Initial
and monthly spending limits have been requested. These are configuration inputs;
no additional general GCP permission is needed.

## Proposed resources

Use an existing isolated OCEAN v1 project if discovery proves its separation,
or create one with an available ID such as `ocean-v1-c23-20261023`. Inspect parent,
billing account, inherited IAM and organization policies. Every command must
specify the chosen project. The default `data-infra-infobio` is the legacy site;
do not use it, change the CLI default or copy legacy resources/credentials/data.
[Separation contract](SITE_SEPARATION.md)

| Setting | Initial session |
|---|---|
| Location | Propose `asia-northeast1`; choose a zone after policy/quota checks |
| VM | One temporary Linux amd64 worker, proposed name `c23-containment-01` |
| Machine | `e2-standard-4`; initially one active sandbox, serial tests |
| OS | Exact official Ubuntu 24.04 image resource/version recorded before creation |
| Disk | One 50 GiB `pd-balanced` boot disk, auto-delete on VM deletion; no snapshots or extra disks |
| Runtime | Exact gVisor release/sidecar hashes, `systrap`, verified flags and cgroup v2 |
| Lifetime | `--max-run-duration=2h --instance-termination-action=STOP --no-restart-on-failure`; stop sooner after tests |
| Identity | No attached service account, SDK login, ADC, service-account keys or copied private credentials |
| Network | Custom VPC/subnet; IAP-only SSH, OS Login; no public service or legacy routes/peering |
| Execution | No external IP/NAT; independent sandbox network denial; synthetic inputs only |

E2 standard 4 has 4 vCPU/16 GB; standard 8 has 8 vCPU/32 GB. For two concurrent
2 CPU/4 GiB sandboxes plus host overhead, record a temporary resize to standard 8
within the configured spending limit. Sizing does not prove enforcement.
[Machine sizes](https://docs.cloud.google.com/compute/docs/general-purpose-machines#e2_standard).
gVisor documents `systrap` for VM environments; installed compatibility still
requires verification. [Platforms](https://gvisor.dev/docs/user_guide/platforms/)

IAP supports access without an external IP. Allow only TCP22 from
`35.235.240.0/20` to this worker; scope operator IAP/OS Login permissions to the
required target and inspect effective firewall policies. Keep the operator SSH
private key and cloud credentials on the Mac; OS Login uses its public key.
Upload approved materials and retrieve evidence over IAP. No attached
identity does not replace a real metadata-denial probe.
[IAP TCP forwarding](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding)

## Provisioning and verification sequence

1. After sign-in, discover projects, billing accounts, parent/folder and policies.
   Resolve an ambiguous billing target with the user; otherwise select the
   isolated target and record actual project ID/number.
2. Fill initial/monthly limits. Record current Tokyo compute, disk, transfer and
   any preparation-network prices in a bounded-session estimate before creating
   billable resources. Historical JPY100,000/month approval was for legacy.
3. Configure the project budget, one-worker capacity and lifetime. Create only
   project/network/IAP/VM resources required here. Retain actual IDs and cleanup
   commands. Read back VM identity, image, firewall, identity and stop deadline.
4. Prepare verified base/wheels/runtime offline where possible. If trusted
   downloads require temporary egress, record that phase and remove it before
   untrusted tests. Pin OS/kernel, runsc/sidecars, Python, complete wheel lock,
   OCI manifest/config/layers and rootfs materialization. Build offline with no
   automatic base pull, using the existing scientific recipe.
5. Implement/review the real adapter and durable journal on `overhaul`. Resolve
   writer-stop/output-extraction/tmpfs-lifetime ordering. Keep C22 production
   dispatch disabled; this VM does not register a serving worker.
6. Run marked real Linux/gVisor tests with synthetic canaries. New immutable
   receipts bind commands, source, installed identities and raw observations.
   Include repeated numerical fixtures with explicit seeds/tolerances.
7. Export/hash evidence and verify local retention. Stop, then delete resources
   no longer needed; verify inventory and remaining billing exposure. Leave no
   continuously running VM.

## Costs and outstanding inputs

Authentication, target/billing selection, spending limits and current regional
prices remain unresolved. A current Tokyo numeric rate was not retrieved from
the official pricing links; this document contains no cost quote.
[Official pricing](https://cloud.google.com/products/compute/pricing)

VM lifetime limits do not prove the sandbox's ten-minute watchdog. Automatic
stop/delete can begin up to30seconds after its deadline. Read back the actual
termination timestamp and `scheduling.automaticRestart=false` at each session.
Disable failure restart explicitly; the default enables it.
[VM runtime limits](https://docs.cloud.google.com/compute/docs/instances/limit-vm-runtime)
[VM creation flags](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/create#--restart-on-failure)

STOP retains disks and other resources can remain billable. Delete unneeded
disks/IPs/snapshots after evidence export. Automatic stop is not complete cleanup
or a monetary cap. [Stopped VM charges](https://docs.cloud.google.com/compute/docs/instances/stop-start-instance)

Alerts-only budgets do not prevent spending. Google's current spend-cap service
list does not include Compute Engine. Combine alerts with fixed capacity,
lifetime, an estimate within the agreed limit and explicit cleanup.
[Budget behavior](https://docs.cloud.google.com/billing/docs/how-to/budgets),
[spend-cap eligibility](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)

A VM supplies an environment prerequisite. C23 still needs actual network/
metadata/host-canary/package-install denial, immutable inputs/rootfs, resource
limits, cancellation/descendant termination, durable recovery, fenced reservation
release and safe output retention. Include positive controls so failed network
probes do not merely show absent host egress. All gates in
[the contract](C23_SANDBOX_CONTRACT.md) still apply. GCP approval supplies no
scientific approval or real-data transfer authority. This temporary setup does
not complete C24's whole-site configuration or C25–C27 acceptance.
