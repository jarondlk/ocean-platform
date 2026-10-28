# Isolated retained acceptance transport

Planning record only; no worker, tunnel, server or grant is started by this file.
The existing worker is independently TERMINATED. Root will start it only after
the new retained runner/issuer/bridge source and host-safe gates are frozen.

Use the existing isolated GCP worker and a NEW disposable PostgreSQL18.3 cluster
on the Mac, with a dedicated ocean_c23_* database/schema and random local port.
Do not discover DATABASE_URL or contact another service. Initialize host auth
with SCRAM-SHA-256 and a fresh bootstrap password stored only in a private local
control directory; do not reuse the earlier trust-auth test cluster as a claim
of credential isolation. The private Unix socket and data directory remain0700.
C22 proposal/approval fixture creation and role/bootstrap happen only against
that explicitly owned synthetic database. Verify actual LOGIN roles, database,
schema, current_user/session_user and expected function/column grants.

The worker already has the hash-locked operator dependencies, including
psycopg2-binary2.9.13, SQLAlchemy2.0.52 and cryptography50.0.1. Evidence is the
original operator-packages.txt; the scientific image is a separate environment.
No new PostgreSQL server or cloud database installation is needed on the worker.
A loopback-only reverse SSH forward over the existing explicit-project IAP
connection can expose the owned Mac test port at a fixed private worker loopback
port. Verify its actual listener is127.0.0.1 only and ExitOnForwardFailure is set;
no external listener, firewall rule, NAT, service account or public endpoint is
added. All cloud commands explicitly select ocean-v1-c23-20261024, regardless
of the CLI's legacy default project.

The worker receives only the ephemeral restricted controller/verifier connection
configuration and the synthetic issuer key, stored root-private outside every
job/rootfs/input mount. Keep bootstrap credentials and real GCP account material
off the worker's analysis input paths. Only operator-owned synthetic proposal,
context/export bytes and acceptance artifacts cross this control connection.
No real dataset acquisition/transfer or scientific review is implied.

Renew actual worker deadline/boot/host-positive controls and complete current
network isolation observations after every restart. Remove setup egress before
analysis. Guest network=none and host-UDS=none remain enforced; a control-plane
host loopback database is not a guest route. The prior network-denial causal
qualification remains; do not relabel a host egress failure as gVisor proof.

Run the complete retained synthetic application approval -> current reserve ->
held lease and one fresh start -> native cleanup -> durable terminal -> current
publication/independent close -> actual signed packet -> independent verifier
record -> atomic release. Retain exact source/material/DB/role/packet/chain/output
bindings, with scientific approval unverified. An SSH/database interruption
must deny new starts/publication and retain capacity when proof/release is
unknown; host watchdog and cleanup must remain independent of that connection.

After acceptance: export bounded synthetic evidence, verify empty owned cgroups,
stop/verify the VM, close/verify the tunnel, verify no temporary roles/schemas,
and stop/verify the exact local cluster using privileged process plus endpoint
checks. A sandbox-only missing process is not shutdown proof. Preserve failures
and original receipts. No C24 whole-site deployment is included.
