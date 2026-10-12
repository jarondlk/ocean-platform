# Conference patch deployment — October 12, 2026 JST

**Deployed and verified:** `ocean-platform-conference1012` serves 100% at [OCEAN](https://oceaninfobio.com/chat). The conference script continues to use manual exact selection with explicit MiSeq. Freeze remains October 13 at 17:00 JST; stop optional feature work at noon.

## Source and release identity

[PR #130](https://github.com/jarondlk/ocean-platform/pull/130) merged the conference patch after all eight GitHub checks passed. Application source is `37383917024021c912491416b2fba0651381f79a`; merge commit is `554450cb80328070af5874a660c86c03f276317d`. Both containers were built from a clean Git archive of the application commit, SHA-256 `731919ffda08099b728bc36d37fcead79e79bfb2a3ec6d52105ba1dbd8d1539f`. Existing uncommitted README, benchmark and audit work was excluded and preserved.

Cloud Build `d3f5c5e3-b41e-4c55-af91-4a9aa9477238` completed SUCCESS. Application metadata remains 0.7.6; this conference patch is identified by its exact source, digests and serving revision. Existing version tags and dated release receipts remain unchanged.

| Container | Immutable digest |
|---|---|
| API | `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/api@sha256:9085feb47d3ee5e5d84c9172b43f5b544330a8728c2a4659558ee09836aba8e7` |
| Frontend | `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/frontend@sha256:e8cbfd2ea8d8aafd3b82cbbc1073f5981d2485390d2f4d7f129b8aca3f1795cc` |

Fresh service comparison confirmed only images and `SOURCE_COMMIT` changed in the runtime template. Models remain `gemini-3.6-flash` for both configured roles. Authentication, secret bindings, IAM, resource limits, scientific mount, schema and publication identities were retained. No production migration, restore, acquisition, classification or model migration ran. Manual/acquisition jobs remain unchanged.

## Verification

- Clean-source local validation: **1,413 backend tests passed, 39 optional integration skips**, coverage **80.78%**; **81 frontend tests**, typecheck and production build passed. Lint and generated scope-contract freshness passed. An initial sandbox run could not bind local fixture-server ports; the unchanged suite passed with that permission. Required GitHub PostgreSQL integration and security checks passed.
- Cloud Build reran backend/frontend checks, fresh dependency installation/audit, non-root runtime imports, container HTTP/auth boundaries, synthetic PostgreSQL schema/backup/restore and unsuppressed image scans.
- A fresh native production backup passed isolated restore across 34 tables. Size: **211,100,046 bytes**; SHA-256 `f8c031929e3ba31bbd7ffdb224c5f4c04dcc1fe16ef2f8f34a9ecb62f3b1b477`. The restore database was removed; production was not restored.
- Candidate execution `ocean-conf1012-qa-42sl8` passed ten authenticated ASGI HTTP cases on the exact new API image against a disposable cloud restore. Japanese/English/manual rows matched every displayed sealed field; 9/56/39 protocols stayed separate; 2020 MiSeq remained unsampled; citations and interaction ownership passed; SST retained the representative; species/year/source limitations abstained. The source sample's 66 assignment rows and trace resolved. Model generation was blocked before network access, with zero attempts or paid calls. The disposable database was removed.
- The ASGI measurements are not browser/production latency estimates. Its first Japanese AUTO request took **48.899 seconds**, so this release does not establish the AUTO latency gate. Manual fish/SST requests took **8.214/7.598 seconds** in that job. Keep the previously rehearsed manual path and recorded fallback.
- Candidate and canonical production `/login` and provider endpoints returned 200; anonymous analysis-options, stats and review endpoints returned 401. Only Google was exposed as a login provider. Existing institutional Google sign-in succeeded in the production browser with the existing admin role; read-only Data showed all 66 sample rows and source read sums, and the source provenance resolved. No production Chat request was submitted. Researcher/viewer role and ownership checks ran in the isolated acceptance database, not by impersonating production users.
- Post-promotion execution `ocean-conf1012-health-after-dqz4h` passed read-only health/schema/scientific identity checks: schema `20261005_0016`, 34 tables, 8,774 evidence documents and 1,534 total SST days. The historical demonstration subset remains 1,455 final days with six gaps. Real production data also verified unpinned exact selection retains the nine-proxy protocol, without planner generation; the catalogue cache remains disabled.
- Execution `ocean-conf1012-preserve-k79wl` confirmed original accounts/roles, completed history, corpus content/embedding metadata, publication heads, regional publication and retained scientific-file hashes match the fresh baseline. No new accounts appeared. Normal sign-in/session metadata and operational access counters are not immutable scientific/history records.

The [October 11 browser receipt](CONFERENCE_2026-10-11_REHEARSAL.md) retains two full local manual scripts, all 210 requested temporal rows and 20 chart groups. It remains a dated local receipt. This deployment adds exact-image cloud acceptance and read-only production checks; it does not convert prior offline results into fresh provider or independent scientific acceptance.

## Image scan review

API: 44 HIGH, 70 MEDIUM, 82 LOW, one UNKNOWN; frontend: 43 HIGH, 58 MEDIUM, 60 LOW, one UNKNOWN. Both have zero CRITICAL and language-package findings. Frontend findings match the previous scan; API adds eight package-level MEDIUM findings representing two Kerberos CVEs. All four affected library versions match the serving baseline (`1.21.3-5+deb13u1`); these are additional disclosures, not newly introduced package versions.

[Debian's CVE-2026-107708 record](https://security-tracker.debian.org/tracker/CVE-2026-107708) describes a Kerberos KDC denial of service and still lists the stable package as unfixed. The exact image has no KDC/admin-server packages. The second finding concerns malformed forwarded Kerberos credentials; [the upstream correction](https://github.com/krb5/krb5/commit/62196e2b269159a5465f5b8d0ed7cf6f29c3282a) checks the credential-list bounds. OCEAN exposes Google OIDC/JWT authentication and acts as a PostgreSQL client, rather than a Kerberos/GSS-API acceptor. From those application/image roles, the affected server/acceptor paths are not part of the exposed OCEAN authentication flow. This scope assessment is an inference, not general exploitability clearance or a claim that the vulnerable libraries are fixed. Full findings and the dated review are retained; broader OS maintenance remains in #104.

## Preservation, rollback and final rehearsal

Immediate compatible rollback is `ocean-platform-v076-patch1009`, retained under `conference-previous`; `conference-production` identifies the new revision. Existing historical tags were preserved. Rollback changes application traffic/configuration only, never restores a production database or overwrites history.

```sh
gcloud run services update-traffic ocean-platform \
  --project=data-infra-infobio --region=asia-northeast1 \
  --to-revisions=ocean-platform-v076-patch1009=100 \
  --update-tags=conference-production=ocean-platform-v076-patch1009
```

Private cloud receipts are under `releases/conference/qa/37383917024021c912491416b2fba0651381f79a/`; backup/preservation receipts are under `backups/conference-20261012/3738391/`, in the private scientific-data bucket. Build reports are under `conference-qa-20261012/d3f5c5e3-b41e-4c55-af91-4a9aa9477238/` in the private Cloud Build bucket. Raw responses, source identifiers, screenshots and credentials are not committed here.

The [runbook](CONFERENCE_2026-10-14_RUNBOOK.md) remains authoritative for explicit MiSeq settings, source pins, missingness, rank limitations and the labelled sample/SST replacements. The sardine species map remains no-go; independent scientific approval and fresh generation-provider reliability remain unclaimed. Final presentation-device rehearsal and the October 13 freeze are still required.
