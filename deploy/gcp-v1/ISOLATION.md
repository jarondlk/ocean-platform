# C24 isolation and authority matrix

These are validated configuration intentions. Every live observation is pending.
The proposed beta hostname does not establish isolation by itself.

| Boundary | Offline enforcement/configuration | Required live evidence |
| --- | --- | --- |
| Project | Explicit v1 project ID/number, region/zone and names; reject legacy and temporary C23 targets; no ambient environment discovery | Current project/billing/organization/folder inventory and inherited IAM; prove no legacy access |
| Serving | One exact beta origin, load-balancer-only serving ingress, default URL disabled, API sidecar and pinned independent images | Owned beta DNS/TLS/Host forwarding, actual auth gateway, direct URL denial, no main-domain traffic change |
| Identity | Separate serving/controller/task-invoker/supervisor accounts; scoped permission intents; no broad roles | Provider grants, service-agent token creation on exact task identity, negative access tests across projects |
| Sessions | Unique host-only `__Host-ocean-v1-` cookie, Secure/HttpOnly/Path=/, null Domain, exact CSRF/CORS origin, independent OAuth/internal issuer/audience/secret references | Actual cookies, key contents, provider registration, login/logout and sibling/main-origin negative tests; no automatic legacy account/history import |
| Database | Independent instance/database, distinct pinned references for serving/research-controller/sandbox-controller/verifier roles, private network, encrypted TLS and no bootstrap-admin supervisor | Provisioned database/role grants and migration heads, TLS/private connectivity, real narrow C22/C23 roles/functions, backup/restore |
| Storage | Four distinct project-namespaced buckets; snapshots read-only, validated results create/read scoped separately, quarantine/backups isolated, no public grants or automatic destructive result TTL | Actual ownership/IAM, provenance/holds/withdrawal handling, backups/retention and access-denial checks |
| Network | Disjoint RFC1918 subnet/SQL ranges, own VPC/subnet, private Google access intent, no worker external IP or legacy peering/routes; guest network none | Actual routing/firewall/DNS/egress/proxy/metadata tests; parent/folder/VPC inherited access review |
| Research queue | Own project/region queue; exact deterministic controller URL/OIDC audience, distinct task invoker, throttling/retries | Real adapter/outbox consumer, authentication/audience verification, paused-state readback, duplicate-delivery/ACK-loss tests |
| Experiment capacity | C22 PostgreSQL locks remain authoritative: one active per owner, two globally; two fixed C23 sandboxes plus explicit overhead | Simultaneous two-job measurements and global reservation races across deliveries/hosts; queue throttles are additional bounds |
| Worker image/material | Project-owned boot image name plus expected unique ID, application/scientific image digests, complete runtime file hashes, lock/rootfs/init/source hashes | Create/inspect disk without booting, exact `sourceImageId` match before attachment of runtime identity/boot; actual immutable materialization and full host preflight |
| Guest boundary | No cloud/DB/seed credentials, metadata, networking or writable host mounts; fixed C23 resource and descriptor bounds | Real image/runtime/namespace/cgroup/input/output enforcement under the exact new host/source; original C23 receipts are scoped to their tested host |
| Termination/recovery | Held boot/lease/journal and original-cgroup observations; physical signed packet plus independent durable proof before release | Actual supervisor lifecycle and ACK-loss/restart/drain checks; unsupported queued/reboot/prepacket reconstruction retains capacity |
| Delivery/rollback | Explicit independent v1 images/targets, no automatic application/deployment, default-off dispatch and retained data | C26/C27 release decision, rollout health and retained compatible revision; rollback never changes main DNS or legacy data |

The `cloud-platform` OAuth scope on the trusted supervisor instance is a token
scope ceiling, not an IAM grant or guest permission. Only reviewed resource-scoped
IAM may authorize the host. Metadata/credentials must remain inaccessible to the
guest under the real C23 isolation boundary. The provider translation must not
replace narrow permission intents with project-wide Editor/Owner/Admin grants.

Beta and the main host share a registrable domain: SameSite is insufficient as
the sole mutation defense. Exact-origin/CSRF checks, unique host-only names,
independent keys and real browser negative tests remain required.
[Cookie rules](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie),
[OWASP CSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
