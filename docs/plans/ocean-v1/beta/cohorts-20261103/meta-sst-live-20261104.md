# Metagenome and MUR SST beta rollout — 2026-11-04 JST

Cloud Run revision `ocean-v1-beta-serving-00011-wrb` serves 100% of beta
traffic in `ocean-v1-beta-20261101`, region `asia-northeast1`. The staged
update changed the API image and preserved the serving template's other
runtime settings. The CTD revision `ocean-v1-beta-serving-00009-rn7` remains
the rollback target.

- Source `4022c1d6f43a28bee29277d965380f1db2d6c104`.
- Build `7e411be2-dfe6-459c-a7c1-24efc2c5c9aa` passed its build and isolated
  Linux image proof.
- Image `snapshot-api@sha256:2d9a1ae220ccd7039702cef0dde7c934d609a0800ce5459d2ddf7501975e787d`.
- Existing activation `464b018099db5975c5ba74ded879e0af5080ad8c4f29541cbaa77397d1af5001`
  and catalogue control generation `1793756318845563` were reused.

The prior candidate's live inspector hit the 15-second proxy deadline. The
replacement builds the inspector and its node inventory from one freshly
verified catalogue context, and reuses verified C10 inputs for coverage
within that request. The change supersedes the pinned runtime copies of
`orchestration/catalogue_service.py`, `orchestration/frozen_catalogue.py`,
and `orchestration/frozen_scientific_catalogue.py`. A later request still
checks access and source integrity. The focused suite and packaging checks
passed, including a regression case for an access change between requests.

The same GCS probe from the operator Mac measured 15.946 seconds serial and
19.102 seconds with overlapping requests before the fix, then 4.932 and
8.619 seconds after it. The SST inspector completed in 3.780 seconds with
overlapping requests. These probes used actual beta GCS transport with a
local test principal. Signed-in browser checks on the live revision then
rendered the following first pages with 100 rows each.

| Table | Retained rows |
| --- | ---: |
| CTD casts | 162 |
| CTD depth observations | 10,955 |
| Metagenome Kraken abundance | 58,712 |
| Metagenome MetaEuk abundance | 67,240 |
| MUR regional SST observations | 1,455 |

Public login returned 200 and unauthenticated runtime returned 401. A
bounded live log sample had 36 catalogue responses with status 200. The
slowest observed inspector was 11.874 seconds. One successful discovery
request measured 15.024 seconds at Cloud Run, so discovery still has little
latency headroom. The matrices retain unknown abundance denominators, and
MUR SST remains a provisional descriptive preview. eDNA awaits its separate
latency gate. Research, model and worker execution, and release acceptance
remain separate.
