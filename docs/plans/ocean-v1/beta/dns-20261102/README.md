# Separate beta DNS and TLS plan — 2026-11-02 JST

**Prepared only; no DNS, certificate, API, IAM, load balancer or IP resource was
changed by this task.** [plan.json](plan.json) contains the ordered command arrays,
assertions and unresolved live inputs. The installed CLI help is captured under
`cli-help/`; credentials were not used for those local help reads. A separate
read-only catalogue request captured the public JPY certificate prices.

The proposal creates a public `beta.oceaninfobio.com.` child zone in
`ocean-v1-beta-20261101`. Its only proposed change in the existing
`data-infra-infobio` project is a **new NS delegation record named exactly
`beta.oceaninfobio.com.`** in `oceaninfobio-com`. Apex, www, existing records,
legacy deployments and data remain outside the change. The child zone's actual
assigned name servers must be read from Cloud DNS; the parent zone's known
`ns-cloud-a1` through `a4` servers must never be substituted for them.

An NS record delegates the subdomain to its child zone; this does not require
changing the parent domain's name servers. See [Cloud DNS delegation terms](https://docs.cloud.google.com/dns/docs/key-terms)
and [record semantics](https://docs.cloud.google.com/dns/docs/records-overview).

## Required order and checks

1. Capture the actual beta project number, full parent zone and **all record
   types at beta and below**. Earlier empty public A/CNAME lookups do not prove
   the subtree is unused. Delegation would shadow existing descendant records;
   stop if any exist until their intended handling is reviewed. Inspect wildcard
   answers, parent/beta CAA, NS and DS as well. Preserve the complete parent
   baseline for an exact post-change comparison. An existing resource or error
   is never treated as an empty result.
2. Enable `dns.googleapis.com` and `certificatemanager.googleapis.com` only in
   the beta project if missing. Then list actual beta Certificate Manager
   resources and check the certificate cost tier. If the API was disabled,
   its earlier list failure is not evidence of zero certificates.
3. Create `ocean-v1-beta-domain` with DNS name `beta.oceaninfobio.com.` and public
   visibility. Verify the actual child name servers and preserve its generated
   NS/SOA. No parent NS/SOA, DNSSEC or registrar configuration is modified.
   This initial plan adds no DS record and makes no DNSSEC-chain claim.
4. Create global `ocean-v1-beta-domain-auth` for the exact beta domain with
   **per-project DNS authorization**. The installed CLI accepts
   `--type=per-project-record`; the API readback must say `PER_PROJECT_RECORD`.
   Per-project authorization separates certificate management across projects;
   see [Google's authorization guide](https://docs.cloud.google.com/certificate-manager/docs/dns-authorizations).
5. Read the actual authorization's `dnsResourceRecord`. Require CNAME type, a
   name below the beta zone and the expected Certificate Manager authorization
   target suffix. Add that exact record only in the new child zone at TTL300.
   Do not invent its unique name/target or alter a pre-existing record. The
   CNAME authorizes ongoing certificate issuance and renewal for beta in this
   project; retain it for renewal and record its actual value. No wildcard
   certificate is requested.
6. Refresh the full parent inventory immediately before adding the delegation.
   Use a create-only transaction containing exactly one beta NS addition, with
   the actual child servers and TTL300. Verify that every earlier parent record
   is identical and that this is the sole addition. Check the authoritative
   parent referral and each child server, then public recursive resolution.
   Negative caches and delegation TTLs can delay propagation; SDK success alone
   is not public DNS acceptance.
7. Create global `ocean-v1-beta-domain-cert` with exact single domain
   `beta.oceaninfobio.com`, the new DNS authorization and `--scope=DEFAULT`.
   Inspect inherited CAA policy first: per-project authorization uses Google
   Trust Services. Do not edit parent CAA or silently override an incompatible
   policy. The managed certificate must reach actual `ACTIVE`; preserve failed
   authorization details rather than labelling `PROVISIONING` complete.
8. Create `ocean-v1-beta-cert-map` and a single map entry matching exactly
   `beta.oceaninfobio.com`, referencing only the new beta certificate. No PRIMARY
   or wildcard matcher is proposed. Creating a certificate map does not expose
   an application or bind a load balancer.
9. **Later:** after OAuth, independent account enrollment, current-source CI,
   host/API and ingress prerequisites are accepted, attach the certificate map
   only to the newly reviewed beta global HTTPS proxy. Publish the child apex A
   record only after the actual beta IPv4 and backend are verified. No AAAA,
   HTTP redirect forwarding rule, legacy proxy edit or public runtime occurs
   during this preparation stage.

DNS authorization can provision a certificate before a load balancer exists,
as explained in [domain authorization](https://docs.cloud.google.com/certificate-manager/docs/domain-authorization).
The [global DNS-authorized certificate deployment guide](https://docs.cloud.google.com/certificate-manager/docs/deploy-google-managed-dns-auth)
supports both global external and classic Application Load Balancers. Later
proxy binding uses the explicit beta certificate-map resource and `--global`;
regional resources are not substituted. Actual TLS SAN/chain/expiry, Host,
Origin, cookie and direct-URL isolation checks remain live gates.

## Cost and scope qualification

The new managed-zone allocation and modest DNS queries are already included in
the [public JPY beta quote](../quotes-20261102/README.md). No forwarding rule, IP,
load balancer or running service is created by this plan. Those paid resources
remain a later reviewed change within the user's initial new-beta ¥50,000 target.

[certificate-pricing.json](certificate-pricing.json) retains official JPY
Certificate Manager SKU records, fetched read-only. Global certificate SKU
`F08F-F1CD-3492` has a zero unit-price tier starting at0, then ¥31.640999998 per
certificate-month starting at100 and ¥15.820499999 starting at2000. Regional
certificates use a separate SKU/tier. The [pricing policy](https://cloud.google.com/certificate-manager/pricing)
states the tier is per project. Verify the actual beta inventory and tier
eligibility before claiming this certificate adds zero cost. Connection charges
also depend on key type and mTLS; inspect the issued key type and chosen TLS
configuration before claiming no connection charge. No account contract, tax
treatment or free-tier entitlement is inferred from the legacy project.

The user already selected a separate beta subdomain and authorized GCP use under
the stated beta budget. This is a concrete, reviewable plan for that scope.
Application requires the actual names, readbacks and guards above; this document
is not an applied change, operational acceptance or release approval. No new
recurring automation is involved.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/dns-20261102/verify.py
```

The verifier is local and read-only. It checks plan boundaries, explicit command
projects, installed help/pricing artifacts and their hashes; it does not execute
the proposed cloud commands.
