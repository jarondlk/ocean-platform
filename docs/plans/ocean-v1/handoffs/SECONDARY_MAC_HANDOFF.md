# Continue beta deployment on a second Mac

Updated 2026-11-03 JST. The user requested a machine handoff and paused scheduled
deployment. **The three-hour automation is PAUSED.** No agents remain working;
the main Mac's pending SDK login was cancelled. Do not reuse that
session, its browser tab or authorization codes. Do not resume scheduling unless
the user explicitly requests it. A new manual instruction on the second Mac may
resume development/deployment there.

## Checkout and authorization

Repository: `https://github.com/jarondlk/ocean-platform.git`, branch `overhaul`.
Fetch the branch on the second Mac and use its actual local checkout path; do not
assume `/Users/jaronchai/Documents/GitHub/provenance-eco-rag` exists there. Preserve
any local edits; do not reset/clean or overwrite a dirty checkout. The checkpoint
includes the C13 carrier fix, explicit staged cohort preparation, deployment/build
receipts, context operator/native checks, CLI instructions and this handoff.

If the repository is missing on the second Mac, clone it into a new directory:

```sh
git clone --branch overhaul https://github.com/jarondlk/ocean-platform.git
```

If GitHub asks for access, use the GitHub account that can access the repository.
With GitHub CLI installed, `gh auth login` followed by `gh auth setup-git` can
configure HTTPS access. For an existing checkout, inspect status and remotes,
then fetch and fast-forward only when that preserves local work. Open the
checkout as a project in Codex on the second Mac.

Standing authorization covers beta implementation, subagents, GCP/project
scientific-data use, commits and pushes. The new beta target is **¥50,000/month**;
notify before exceeding that target. ¥100,000 is the stated upper budget, not a
waiver of notice. Keep the separate site boundary: no main/legacy deployment,
legacy writes, account/history/backups copying or fabricated scientific approval.
Existing scientific source objects in legacy GCS may be read for the explicitly
authorized import. Original evidence remains immutable; new source supersessions
need new receipts. Broad CI may be deferred when justified; unrun gates stay open.

Read `AGENTS.md`, `BETA_DEPLOYMENT.md` in this directory and the latest entries in
`../STATUS.md` first. The pause/handoff section supersedes older ACTIVE and
in-progress descriptions. Unrelated benchmark/audit files and their root README
edit, plus the legacy job-evaluation template edit, remain on the main Mac and
were not selected for this deployment checkpoint.

## GCP sign-in on this Mac

Use the university account `dilokkalayakul.jaronchai.p8@dc.tohoku.ac.jp` with access
to beta project **`ocean-v1-beta-20261101`** (number534831104543). Region is
**`asia-northeast1`**. If Cloud SDK is installed, begin a fresh local browser flow:

```sh
gcloud auth login --project=ocean-v1-beta-20261101
gcloud projects describe ocean-v1-beta-20261101 --project=ocean-v1-beta-20261101
```

Let the user complete passkey/identity prompts. Do not print tokens, codes,
private keys or DSNs. CLI login normally opens its own browser flow; a separate
Cloud Console login is not required for CLI work. Do not request ADC login unless
a specific SDK operation actually needs it. Explicit token-backed SDK credentials
can be obtained privately from the authorized CLI session instead.

`scripts/gcloud_beta.sh` is now tracked, with the user's CLI access documentation.
It works only when this Mac has its dedicated isolated configuration. That
configuration/key is **not** in Git and is not automatically available on a new
Mac. Follow `AGENTS.md`: use the wrapper within its granted scopes when locally
configured; otherwise use the signed-in personal CLI with explicit project flags.
Do not copy credentials into Git or expand service-account roles merely to make
an inspection pass. Do not blindly copy the main Mac's credential store or create
replacement keys as a prerequisite to an ordinary personal login.

Builds use explicit Tokyo, the existing account
`projects/ocean-v1-beta-20261101/serviceAccounts/ocean-v1-beta-build@ocean-v1-beta-20261101.iam.gserviceaccount.com`,
`CLOUD_LOGGING_ONLY`, and the approved staging bucket. The working staging URI was
`gs://ocean-v1-beta-20261101-build-source/source`; the directory suffix avoids the
earlier bare-bucket CLI preflight error. Images stay in the beta Tokyo repository.

## Actual live state

- URL: `https://beta.oceaninfobio.com`.
- Cloud Run: `ocean-v1-beta-serving`, Ready generation9,
  revision `ocean-v1-beta-serving-00009-rn7` at last readback.
- Frontend source0fc4775, build6b48b628-177b-4926-8a0b-83ef32042e24, immutable
  `context-frontend@sha256:005eda32b803676c17a4cdc72ffda3dedc447f4cf73b7533161b43f55d695ea3`.
  This rollout changed only the frontend image; the exact readback is retained.
- Live API remains original CTD catalogue sourcea4923c4,
  `snapshot-api@sha256:877b1b3f7db703f5a8e9fedc3cca30f4a5aa67d238201cb5e9159482561e7eb9`.
  SHELL/CATALOGUE/CATALOGUE_BROWSER only; investigations/models/dispatch remain off.
- Valid HTTPS login200 and unauthenticated `/v1/runtime`401; authenticated CTD
  tables show162casts and10955depth observations. The new frontend forwards eight
  C17 mutation paths securely, but the current API still denies context writes.
- Preserve the private SQL proxy, identities, secrets, ingress, direct-URL denial,
  startup API-health wait and min0/max1 scale settings. Read the current service
  before any update. Do not substitute an old frontend image that loses context
  proxy paths or the transport/startup adapters.
- SQL migrations are already through `20261027_0021`; one admin/internal Google
  account is enrolled. **Do not rerun bootstrap, enrollment or initial finalize.**
  Cloud Tasks remains paused; no production worker/model execution is enabled.

## What is ready, and what is held

The narrow C13 runtime fix coalesces only exact canonical `c11:sst` and `c12:edna`
family directories across sources. All other source/scientific/cross-family
shadows still fail.197regressions pass, including21new cases. Snapshot packaging
now explicitly supersedes this third API source file; a fresh API build is needed.
No previously built API image contains this final carrier fix.

The cohort driver requires **`--cohort-set meta-sst` or `all-qualified`**;16stage
tests pass. Select `meta-sst` for the next incremental deployment. It preserves
CTD and adds metagenome/SST, without reading eDNA staging. A new private phase1
bundle/image was **not** prepared after the user paused. Use new directories and
the exact new committed source after restoring inputs.

Metagenome has82technical source-column keys,106run/QC records,58712Kraken and
67240MetaEuk cells, including explicit zeros. Abundance units/denominators stay
unknown; numeric abundance summaries remain unavailable. SST has1455MUR regional
observations and six retained gaps, explicitly unreviewed/unpublished; it is not
native station SST. Raw JCOPE requires separate bounded normalization:1837valid
grids,856042missing cells, plus one malformed placeholder repeated11paths. Do not
invent timestamps or reinterpret JCOPE as satellite MUR.

The held full private package has41additional datasets/four total indices,
250immutable files/68844098bytes, activation
`3fee1baeb47d9d4b9df323ba8041aa661574b8f1e5233fc67498c1f6fcae07c6`.
It is **not uploaded/activated**. After the carrier fix, local raw paging takes
15.076610seconds before GCS/network cost, exceeding the existing15-second proxy
gate. Do not deploy that activation or merely raise the deadline. eDNA preserves
3155unknown records and343negative controls; all3498physical identities remain
unresolved. Raw browsing does not establish an environmental scientific cohort.

The local semantic-input cache measurement is promising (14.802scold,
1.891swarm overview,1.582swarm query,~1.15GiBpeak), but it is a **private diagnostic
prototype**, not implemented production caching/security/concurrency acceptance.
Read `../beta/edna-latency-20261103/README.md`; frozen diagnostic source copies are
provided there. Any production cache must retain current payload/hash/generation,
registration/lifecycle/activation/owner/classification and collision checks.

An earlier API candidate, sourceb3db9e9/build896039e7,
`snapshot-api@sha256:799c034a10366ea6ed1e736cc03986c6c979607ff4a77447ac508517e06f87c2`,
passed its image proof but remains UNDEPLOYED and superseded by the carrier fix
and staged activation decision. **Do not deploy it as the new complete beta.**

## Private inputs: Git alone does not transfer them

Scientific rows, private activation/publication manifests, the raw quarantine,
prepared bundles, browser sessions and credentials are outside Git. Main-Mac
locations and hashes are listed in `../beta/cohorts-20261103/private-inputs-handoff.json`.
Do not assume `/private/tmp` contents survive indefinitely or exist on this Mac.
There was no new cloud upload performed for this handoff.

The next `meta-sst` phase can be reconstructed from existing GCS objects without
access to the main Mac. Recover only into new owner-only private directories,
verify exact generations/lengths/SHA256 and preserve original receipts:

1. Raw quarantine: use `../beta/raw-quarantine-20261102/upload-complete.json` for
   the four exact objects/generations under
   `gs://ocean-v1-beta-20261101-quarantine/v1/raw-imports/local-20261102-e62eb0e62ad1/`.
   The tar SHA is `e62eb0e62ad1a1b0b9354944cb46b3b1d818fd12b5076b1e2749fb317cf471cb`.
   Restore the pinned source manifest and approved eleven-path amendment unchanged.
   Inspect/validate every tar member and its declared hash before extracting only
   approved `payload/data/raw/...` and `payload/onagawa_sst_subset/...` paths.
   Refuse symlinks, traversal, unexpected members and existing-file overwrites.
   Restore ignored raw files and `data/provenance/raw_source_manifest_latest.json`
   in the new checkout if needed by the verifier. The private preparation receipt
   itself was not uploaded: regenerate it through the reviewed local verifier in
   a new directory, recording a new recovery receipt rather than inventing an
   original receipt or repeating the completed cloud upload.
2. CTD base: use all eight pinned objects in
   `../beta/snapshot-activation-20261103/data-upload-complete.json` from beta's
   snapshots bucket. Reconstruct the private `store/v1/catalogue/...` layout and
   activation. A local base-input publication manifest may be reconstructed from
   those verified objects and their accepted sourcea4923c4, explicitly labelled
   recovered metadata; do not claim it is the original private manifest.
   The last accepted base control is generation1793637712460705/hash276e0190…,
   revision4. Always inspect CURRENT control before a real publication. If it
   differs, rebase the append and retain all current references/audits; never
   force the old blob over newer state.
3. SST: five generation/SHA-pinned source objects are listed in
   `../beta/raw-quarantine-20261102/regional-publication-source-readback.json`.
   They are in legacy bucket `data-infra-infobio-ocean-data` under
   `edna/regional-publications/`; this old namespace contains MUR SST, not eDNA.
   Download read-only at the recorded generations into the expected five local
   filenames. Preserve unreviewed regional-preview/science-false qualifications.
4. eDNA can wait for its performance work. Its old metadata index is
   `gs://data-infra-infobio-ocean-data/edna/normalized/index.json`, generation
   1790740062783615, SHA
   `76d89bc641b739f3b5648287f24e947bdd6b6a7f3f8bbbf31020f7d516fd4d86`.
   It binds41registry receipts. Verify each registry SHA against its index entry;
   registry file descriptors bind eight object generations/sizes/SHA values.
   Select only the39source-packagee3eb67bc… current-v3 bundles for C12; retain the
   two older bundles as excluded. Stage index as `0-index.json`, registries as
   unique `<number>-<registry-id>.json`, and normalized objects by registry-id.
   `prepare_edna.verified_bundles` verifies complete membership and projections.
   Do not copy retrieval caches, operations, user history or database backups.

If a recorded generation is no longer available, stop that input and request a
private copy from the main Mac or record an explicit new source supersession.
Do not silently substitute newer bytes. Do not upload private manifests/data to
Git or put scientific payloads/credentials in application images/build contexts.

## Next deployment sequence after fresh sign-in

1. Inspect beta's live revision, jobs, storage control and existing grants;
   reuse successful immutable builds and receipts. Restore/verify missing inputs.
2. Prepare a NEW `meta-sst` append using exact committed source; retain CTD.
   Perform local catalogue/latency checks and build a source-bound API image
   containing the carrier fix and its new opaque activation binding.
3. Publish immutable objects/manifests/activation create-only; verify readbacks.
   `publish_append.py` rechecks fresh base bytes/generation, disables SDK mutation
   retries and CAS-publishes control LAST. Persist an exclusive attempt receipt
   before apply. Uncertain outcomes require inspection, not automatic retry.
4. For durable C17 context, grant the serving identity conditional create/delete
   only on `v1/catalogue/control.json` (existing prefix read remains), preserving
   unrelated IAM. Do not grant writes to scientific payloads or a whole project.
5. Use the prepared one-shot context grant operator, source
   `1d20cf2f8ae625b1fdcf79a3be896a16c5d1560b`, existing migrator identity/secret,
   no retries and the private proxy. Its accepted immutable image is
   `context-operator@sha256:a9be3b94b156c9d1260c609fb5958c4e503772d3564b95c097fa9f3d47bb1340`
   from build6b0cba18-ecf3-4a7c-ba5b-572b26b76c25.35unit/28nativePG18 checks pass;
   actual CloudSQL16 acceptance is pending. Grant only the documented C17
   table/column rights, including `SELECT(created_at)` for audit INSERT RETURNING;
   no full audit read, revision UPDATE, DELETE, account write or grant option.
   This job has not been created/executed. Do not rerun original DB initialization.
6. Activate the explicitly bound context mode/INVESTIGATIONS only after the real
   GCS/SQL grants pass. Verify actual Google login, saved investigation/conversation,
   dataset attachment, retained history, current denial and restart behavior.
   Keep models, research/experiment dispatch, queue and workers disabled here.
7. Continue eDNA latency/cache acceptance and later Research/provider/outbox/
   queue/worker/recovery/release work incrementally. P2 D26-07 and original live
   release gates remain. Never label a prepared/local/mock gate as production pass.

Keep scheduling paused. No new recurring automation or new chat is requested by
this handoff; the user will paste a manual continuation prompt on the second Mac.
