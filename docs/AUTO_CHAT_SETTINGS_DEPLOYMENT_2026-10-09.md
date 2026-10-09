# AUTO settings deployment record — 2026-10-09 JST

Status: **deployment deferred; production traffic has not been promoted.**
The user authorized deployment while existing GCP CLI authentication remained
usable, including backups and resource creation. Authentication initially worked,
but token refresh subsequently required interactive reauthentication. No login
was initiated. The new build submission and final QA status query failed before
execution because of authentication; an empty submission file is not a build receipt.

Latest application source is `6083225e7d01872b6714c1a619af840b1ee26ce8`
on `auto-setting`. Production was last verified at 100% traffic on
`ocean-platform-v075-patch1008` in project `data-infra-infobio`, region
`asia-northeast1`, serving <https://oceaninfobio.com>. There was no traffic-promotion
command after that verification. Its existing rollback tag remains retained.

## Implemented fixes and validation

AUTO remains an opt-in per-account toolbar toggle. A bounded structured planner
call precedes the main answer flow. Confirmed manual choices remain pins; the
planner can choose supported sources, filters, published workflows, or ask for
clarification. Backend validation still checks scope, catalogue membership,
publication status, protocol identity and quoted constraints. Exact published
workflows and SST coverage answer deterministically; published interpretation
passes verified result packets to the main model.

Deployment preparation found and fixed these real-data issues:

- Missing local SST parquet now uses the existing verified retained-day recovery
  path only for absence (404); other errors still propagate.
- The production catalogue exceeded the 36,000-character planning limit.
  Published membership filtering and compact protocol descriptions reduced it
  from 41,118 to 19,757 characters, retaining identities, recipes and limitations.
- Vertex rejected the full proposal generation grammar. A smaller generation
  grammar works with the provider; strict Python validation remains authoritative.
- Omitted confirmed dataset, analysis and protocol pins are restored on the
  server; explicitly conflicting choices are rejected.
- Planner version `auto-settings-v5` preserves supported literal calendar ranges
  from the question, including inclusive year ranges and explicit ISO dates.
  Conflicting ranges are rejected. Relative, excluded, reversed or ambiguous
  periods are not inferred by this helper and remain subject to planning checks.

The latest commit passes lint, generated-scope freshness, and **99 focused
planner/runtime/source-scope tests**. Its full cloud source/runtime gates and
final live acceptance are still pending. Earlier complete cloud gates passed:

| Source | Cloud Build | Result |
| --- | --- | --- |
| `4f061c5` | `28823e92-9999-43cb-b922-ed513fa65fe4` | Eight gates; 1,293 backend tests passed, 49 optional skips |
| `07eb458` | `da33d0dc-1ff4-4549-b00d-b7d6f4af1fd9` | Eight gates; 1,296 backend tests passed, 49 optional skips; 78 frontend tests passed |
| `346a9ff` | `f62c07a4-18d7-448a-93be-e97590a6aa27` | Seven gates; 1,297 backend tests passed, 49 optional skips; unchanged verified frontend reused |

Gates cover source lint/contracts/tests, image builds, synthetic PostgreSQL 16
bootstrap/readiness/backup/restore, runtime imports and non-root execution,
authentication HTTP checks, and unsuppressed vulnerability report collection.
Skipped optional tests are not counted as passing. The first build failed on
the SST recovery regression and was not accepted; a superseded intermediate
build was cancelled to include the grammar correction.

The most recent Ready **zero-traffic** candidate is
`ocean-platform-auto-settings1009b`, with API source `346a9ff`:

- API: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/api@sha256:080aef65d0866967c946a1d59fc3d6a625e6b078db33890faa6a9eec52fbf046`.
- Frontend: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/frontend@sha256:474ebc02c4d5f8af3a8428a091924d01fade6e5d48e9ab5d1a228bbc9e26cac3`, built from `07eb4588dadbe249a0cfd6822e745f13222ce028`.

Each container retains its actual source pin. Frontend changes between that source
and `6083225` are empty. Candidate anonymous checks passed: login/providers return
200; analysis-options, stats and research-registry-reviews return 401. Google
login remains configured and mock login disabled. Browser sign-in and role flows
were not evaluated.

## Live-model acceptance still required

Bounded real Vertex preflights verified an SST coverage plan and, subsequently,
the pinned exact fish-frequency, exact high/low SST comparison, and published
synthesis plans. These are planning evidence, not complete answer acceptance.
Diagnostic patched-image runs are not final immutable-image acceptance.

The unpatched `346a9ff` five-path run stopped on an omitted 2020–2023 range in the
first question; its isolated database was removed. That failure motivated
`6083225`. Diagnostic execution `ocean-auto-settings-qa1009-f6lpt` was started
with the date fix patched into the prior image. **Its final status and cleanup
receipt could not be retrieved after authentication expired.** Its definition
has one task, no retries, a 900-second limit, and cleanup in `finally`. Verify
the actual outcome and cleanup when authentication returns.

Required acceptance on the newly built, unpatched image:

1. MUR v4.1 · Miyagi · 2020–2023: final SST coverage, missing dates, spatial
   resolution and limitations (`sst_coverage`, main model uninvoked).
2. Published Miyagi analysis, MiSeq paired protocol: top 10 fish by detection
   frequency with yearly and seasonal changes (`published_exact`).
3. Same pins: high/low SST detection-frequency comparison and representative
   series (`published_exact`).
4. Interpretation of those published comparisons with qualified limitations
   (`published_synthesis`, main model invoked).
5. CTD salinity in Onagawa during 2024 (`rag`, main model invoked).

Also verify valid citations, completed per-user history, requested/effective
settings, fingerprints, pin preservation, and manual all-off abstention. The QA
operator restores the backup into a disposable database before application
imports and calls the actual chat handler there. It does not write production
chat history. This does not substitute for browser acceptance or broad English/
Japanese, paraphrase, negative and qualifier evaluations. AUTO must remain opt-in.

## Backup, preservation and scans

A fresh full private PostgreSQL 16 backup was restored into a temporary database,
verified and removed by execution `ocean-auto-settings-backup1009-wkxf9`.
The archive is 209,773,369 bytes; SHA256
`89033b38ad568dd6ce4c452cdf10a31fd8b510c7ee0b2c40d5d5a072bde7aab0`.
Backup, manifest, baseline and receipts remain under the private prefix
`gs://data-infra-infobio-ocean-data/backups/auto-settings/deploy-20261009-0b4a33f/`.
No production migration or restore occurred. Schema remains `20261005_0016`,
34 tables. The initial backup attempt failed before mutation on an omitted
artifact environment variable; the corrected attempt passed.

Baseline preservation checks cover identities/roles, original terminal chat
history, published scientific state, retrieval/embedding provenance, retained
artifacts and regional publication. The post-promotion preservation job has
**not run**. Data mounts, secrets, IAM, Cloud SQL bindings, canonical auth/CORS
settings and existing serving capacity were preserved in candidate configuration.
Temporary operator resources remain to be checked and cleaned up. Existing
manual jobs have not been repinned or executed for this rollout.

The last reviewed scans contain no CRITICAL or reported language-package
findings. Existing tracked OS findings remain: API HIGH44/MEDIUM60/LOW82/UNKNOWN3;
frontend HIGH43/MEDIUM58/LOW60/UNKNOWN1. Compared with the older scan database,
an old liblzma temporary finding disappeared and `CVE-2026-107161` appeared on
two unchanged SASL packages. Findings remain unsuppressed for the existing #104
runtime follow-up. No corresponding application authentication path was found;
the QA operator checks plugin absence. Final-image scan and runtime review are
still required; no independent exploitability guarantee is asserted.

Billing metadata was captured, but budget read permission returned 403, so budget
headroom was not verified. No permanent capacity increase was made.

## Resume procedure

Private operational scripts, configurations and receipts are retained at
`/private/tmp/ocean-auto-setting-deploy-20261009` (restricted permissions).
They contain configuration references and must not be committed. This temporary
directory is not durable storage; the private cloud backup and this record are
the durable recovery references.

After CLI reauthentication:

1. Refresh the service and job inventories. Confirm production traffic, inspect
   `f6lpt` and its private acceptance/cleanup receipt, and remove any remaining
   disposable QA databases before continuing. Retain the private backup.
2. Build a clean frozen archive of application commit `6083225`; reuse the
   verified unchanged frontend. Require full source/runtime gates and reviewed
   scans on the actual images. The failed submission created no verified new
   build or image.
3. Prepare a new zero-traffic revision, preserving live configuration and all
   existing production/rollback tags. Update scripts' source/revision assertions
   and immutable image pins from fresh receipts. Recheck anonymous authentication.
4. Replace the temporary QA job with its canonical unpatched operator, pin the
   new API image/source, and require all five answer cases and cleanup to pass.
5. Promote traffic only after those checks. Check the canonical URL and served
   images, then run the baseline-preservation comparison. On application failure,
   return traffic to `ocean-platform-v075-patch1008`; do not restore production
   data as an application rollback.
6. Align the five existing manual runtime jobs' image/source pins without
   executing their commands. Preserve superseded acquisition jobs and paused
   follow-up. Remove only this rollout's temporary jobs, unused zero-traffic
   candidates and candidate tag after successful verification. Retain production,
   rollback, private backup and acceptance reports. Update this record with
   actual outcomes.

No automatic retry or scheduled deployment was created.
