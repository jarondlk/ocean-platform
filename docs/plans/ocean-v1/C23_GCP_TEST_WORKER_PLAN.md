# C23 temporary GCP test worker

Prepared 2026-10-23 JST on `overhaul`. The user said, “I see, then I approve all
gcp use.” This authorizes GCP setup, runtime installation, image preparation and
synthetic tests needed for C23. Earlier statements that provisioning lacked
authorization describe the older checkpoint and are superseded for this work.
The recurring continuation stays PAUSED. The plan was executed on2026-10-24;
the actual worker record below supersedes historical unresolved inputs.

The user authorized using existing billing for required C23 work without a new
budget decision. Authentication succeeded onOct24. OnOct25 the CLI again
required reauthentication and browser sign-in was opened at the user's request.
At18:04 JST authentication worked; actual stopped-state readback preceded a
restart of the same worker. Its new read-back STOP deadline is20:04 JST
(`2026-10-25T11:04:14.331914Z`). No duplicate was provisioned. Original24 evidence
files were exported before trusted offline amendment preparation resumed.

## Actual preparation record — 2026-10-24/25 JST

Project `ocean-v1-c23-20261024` (number1010914377085) is isolated under the
existing organization and billing account. No billing arrangement was changed.
Every cloud command names this project explicitly. One worker
`c23-containment-01` (id7275994259687337942) was created in `asia-northeast1-a`
with `e2-standard-4`, a50GiB auto-delete balanced boot disk and exact official
image `ubuntu-os-cloud/ubuntu-2404-noble-amd64-v20261021`. Kernel observed was
7.0.0-1014-gcp. Secure Boot/vTPM/integrity monitoring are enabled, with no
attached service account. The new project's automatically created compute
service account had its Editor binding removed.

Custom network `c23-private`, subnet `c23-tokyo` (`10.77.23.0/24`) and firewall
`c23-iap-ssh` allow only IAP-source TCP22. No NAT/peering or legacy link was
created. Temporary external IPv4 was used for trusted preparation downloads;
remove its `external-nat` access config before untrusted tests. OS Login and
project SSH-key blocking are enabled; the authorized operator has project-local
OS Admin Login. Private credentials remain on the Mac.

gVisor `release-20261019.0`, all eight release binaries and its archive hash
were installed and recorded. The offline initial image uses Python3.12.15 and
22 complete hash-locked wheels. Its OCI manifest is
`sha256:08d4f39e199c3e88d1d47db914e61aba4f1a0477f0ee8a160239655e2469d938`.
The initial image contains the earlier wrapper; preserve it and its receipt
when building the separately reviewed quota amendment. The operator interpreter
uses a private verified SQLite3.54.1 library, without replacing the OS library.

The VM had automaticRestart=false, maximum duration7200seconds and STOP deadline
`2026-10-24T08:33:32.313532Z`. That deadline elapsed during interruption; it is
not a current-state observation. No restart or new worker has been made onOct25.
After authentication, inspect before restarting; retain a new deadline on each
session. Export evidence before deleting the VM/disk. Stopped disks still cost
money. Actual containment and numerical fixtures have not yet been accepted.

The Oct24 authenticated official catalog gave Tokyo rates USD0.028026420 per
E2 core-hour, USD0.003739110 per GiB RAM-hour and USD0.13 per balanced-disk
GiB-month. Four cores/16GiB cost USD0.17193144 per hour. Two hours plus50GiB
disk prorated over744hours is approximately USD0.36, excluding temporary IPv4,
transfer and tax; a retained disk is USD6.50/month. This is an estimate, not a
cap. [Exact pricing/preflight record](evidence/C23/cloud-worker-2026-10-24/pricing-preflight.json).

## Original resource plan

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
within the authorized C23 scope. Sizing does not prove enforcement.
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
2. Record the authorized existing-billing scope and current Tokyo compute, disk, transfer and
   any preparation-network prices in a bounded-session estimate before creating
   billable resources. Historical JPY100,000/month approval was for legacy.
3. Configure one-worker capacity and lifetime. Do not invent a budget amount. Create only
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

The actual record above resolves the historical target/billing/pricing inputs.
Oct25 reauthentication and real runtime acceptance remain pending.
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
