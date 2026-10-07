# Hybrid historical MUR acquisition — #103

The user selected the hybrid approach on 2026-10-07 JST. This supersedes the
75-tile, native-resolution bulk acquisition strategy, while preserving its
immutable raw files and checkpoints. Production remains v0.7.2. This is an
acquisition choice; #102 sampling/area review and #103 scientific acceptance,
normalization, linkage and publication remain open.

## Two distinct evidence roles

- **Regional context:** daily 0.05-degree MUR grid-point spacing across a bounded
  rectangle covering the reported coordinates (17.40–45.60°N,
  123.75–148.75°E). This requests every fifth native grid point along each axis;
  it is subsampling, not a five-by-five-cell mean. Preserve that distinction in
  any later product definition, map, analysis or Chat publication.
- **Native patches:** the native 0.01-degree grid inside small envelopes around
  all 216 reported coordinates, for the same complete 2017–2023 calendar years.
  The acquisition padding is 0.05 degrees around the enclosing native cells,
  producing approximately 0.10–0.11-degree patches. Neither the coordinates nor
  this padding establish physical sampling areas or uncertainty. Reviewed areas
  extending outside a patch require an additional explicit acquisition plan.
- Keep daily timestamps. Native-patch requests group at most 12 consecutive days
  into one small raw file, reducing request overhead without thinning time.
  Quality/uncertainty and land/sea/ice fields accompany the temperature field.
- Keep the known mirror-gap dates 2021-02-20 and 2021-02-21 excluded from the final-generation archive.
  Additional provider-specific generation gaps can exist and must be checked.
  Native blocks split at these known gaps; timestamps must match the exact requested
  dates. The two separately retained NASA originals declare interim `04.1nrt`
  and remain unapproved.

The retained production census is from 2026-10-06, inventory
`62e513192cda70d576dd8c8b60713c41830a01b8fcb6ec0e1f0ebff911f9ab3d`.
Its 343 controls, 3,155 unknown classifications and 324 unresolved-coordinate
occurrences remain explicit. Acquisition location-days are not physical-sample
or eligible-environmental-sample denominators. Recheck current applied scientific
source/review bindings before preparing any research publication.

## Preflight and resource limits

The NOAA CoastWatch hybrid plan ID is
`f18dd55375e7a9001e0a9f00d55242fde2c5d3313a1c7d428234be188ab0c8b0`.
Its canonical preflight is 20,391,775 bytes, below the existing 64 MiB plan bound.

| Quantity | Hybrid plan |
| --- | ---: |
| Context requests / available context days | 2,554 |
| Native-patch multi-day requests | 46,008 |
| Total raw-file requests | 48,562 |
| Expected native location-days | 551,664 |
| Excluded context days | 2 |
| Excluded native location-days | 432 |
| Estimated raw bytes including per-file allowance | 20,854,384,952 (about 20.9 GB) |
| Hard cumulative raw ceiling for this plan | 32 GiB |

This is roughly 75% fewer requests and 62% fewer estimated raw bytes than the
superseded 191,550-request/~55 GB acquisition. The estimate uses the native grid
and four-field sizing model; actual provider bytes and throughput still need
live acceptance. No completion-time guarantee is inferred. Metadata, the old
5.5 GB archive and the separately retained 1.44 GB NASA originals add storage.

Each hybrid file remains bounded at **8 MiB**; the new context validator allows
at most **300,000 SST grid values** per file. This is a separately versioned
operator contract; the old pilot's two-degree footprint, plan hashes and
100,000-value cloud validator remain unchanged. Only one request is staged at
a time, with a CAS worker lease, private immutable artifacts, complete raw-byte
read-back, exact role/time/stride/footprint checks and sealed reconciliation.
Native multi-day intervals have no skipped or substituted timestamps.

The full retained-plan validation observed 275,251,200 maximum resident bytes
locally; this is a planning measurement, not a Cloud Run memory/load guarantee.
A plan-bound cumulative raw-budget pointer includes prior disjoint pilots.
An incomplete request stops acquisition and now preserves its bounded manifest
and sanitized request journal privately before staging is removed. Re-running
revalidates retained byte generations. Changed or ambiguous generations require
operator review. No DB, corpus, scientific registry, account, history or model
access occurs in the hybrid acquisition operator.

## Operator commands

```bash
python scripts/acquire_hybrid_sst.py preflight \
  --inventory /private/path/inventory.json \
  --provider noaa_coastwatch \
  --output /private/path/hybrid-plan.json

# Read-only preview; destination must end with the exact new hybrid plan hash.
python scripts/acquire_hybrid_sst.py acquire \
  --plan /private/path/hybrid-plan.json \
  --destination gs://PRIVATE_BUCKET/research-sst/issue103/hybrid/PLAN_SHA256 \
  --work-root /private/path/staging \
  --output /private/path/reconciliation.json
```

Explicit `--execute` performs acquisition. For acceptance, select up to 16
existing request hashes using repeated `--request-id`; select both roles and
representative dates/locations. `--max-requests` selects a prefix and cannot be
combined with request IDs. A partial receipt never counts as full coverage.
For the selected recovery, `acquire_hybrid_sst.py acquire --role native_patch`
selects the NOAA native scope without repeating NASA context acquisition. The
role-specific reconciliation still does not complete the combined archive.

The operator source and preflight must be pinned and live subset/storage
acceptance must pass before starting the new bulk job.

`noaa_upwell` is an explicitly selectable alternate official NOAA hostname for
the same advertised dataset. Choosing it changes both plan and request hashes;
there is no silent automatic fallback or cross-host redirect. Validate actual
MUR generation, fields, units, timestamps and grid before accepting any
alternative delivery path. Coarse artifacts cannot be substituted for native
sample evidence merely because dates or coordinates overlap.

## Provider interruption and recovery

The old execution `ocean-sst103-historical-acquire-p2lkt` stopped on 2026-10-07
at 07:18 JST after 1,902 batches / 19,278 verified files / 5,495,463,792 bytes.
Its lease is released; the execution is terminal. Never restart it following
this strategy change. The archive is retained for provenance, validation and
possible explicit reuse; it is not silently moved into the hybrid namespace.

Both CoastWatch and Upwell metadata requests timed out locally. The bounded GCP
diagnostic `ocean-sst103-hybrid-probe-gpqc8` reproduced `URLError`, with no HTTP
status, after approximately ten seconds per hostname at 2026-10-07 15:08 JST.
The diagnostic job completed, but provider access did not succeed; no hybrid
raw file was downloaded from NOAA or published by that diagnostic. Local receipts are under
`/tmp/ocean-issue103-implementation/hybrid-provider-probe-*.json`.

Recovery order:

1. Retry bounded access/subset checks periodically. A successful website or DDS
   response alone does not qualify the scientific download. Test both coarse
   and multi-day native requests, actual fields/time/generation/grid, private
   upload/read-back and interruption/resume before bulk execution.
2. Qualify NASA PO.DAAC's authenticated MUR OPeNDAP subset service as the
   independent delivery fallback. Authenticated metadata and both evidence-role subsets succeeded on
   2026-10-07. NASA reports `Daily MUR SST, Final product`, version `04.1`,
   Kelvin units, `lat`/`lon` coordinates and compressed NetCDF4 containers.
   These are validated independently from NOAA delivery.
   Keep credentials in a private local file, out of source, receipts, logs and
   public issue text. New credential creation is a user step. Do not extract
   browser sessions or silently persist a credential in GCP.
3. NASA granule subsetting has a different contract and must be independently
   bound and tested. The previous Harmony request for one excluded date failed
   because its source granule lacked an OPeNDAP link; this does not establish
   that all normal final granules fail. Check exact final granules before a
   switch. Do not mix interim originals into the final series.
4. If authenticated subsetting remains unavailable, investigate provider-side
   or cloud-adjacent bounded extraction and prepare a separate measured resource
   plan. Global-original downloads are much larger and are not authorized by
   this 32 GiB hybrid envelope. Existing verified regions can support a bounded
   preparation pilot while acquisition waits, subject to scientific review.

[NOAA grid subsetting](https://coastwatch.pfeg.noaa.gov/erddap/griddap/documentation.html),
[official alternate NOAA dataset](https://upwell.pfeg.noaa.gov/erddap/griddap/jplMURSST41.html)
and [NASA's MUR OPeNDAP tutorial](https://podaac.github.io/tutorials/notebooks/opendap/MUR-OPeNDAP.html)
describe the provider paths. Endpoint reachability and scientific generation
must be checked live; documentation is not download acceptance.

## NASA fallback qualification

`qualify_nasa_hybrid_sst.py` selects exact child hashes from the retained hybrid
preflight and expands them into at most 16 one-day NASA subset requests. It is
read-only/dry-run by default. Explicit execution reads an owned, mode-0600 local
bearer file; credentials are sent only to the fixed NASA OPeNDAP HTTPS origin.
All redirects are rejected. Credentials and provider exception text are absent
from plans, receipts and journals. Expired/denied access stops with an explicit
sanitized status. No credential is persisted in GCP by this operator.

The NASA validator checks actual bytes/SHA, collection-bound request identity,
final product version, Kelvin units, all four fields, timestamp, dimensions and
every requested coordinate/stride. The compressed container uses a private
file-backed reader. A bounded receipt never constitutes the full hybrid archive.

Initial 2019-01-01 checks returned HTTP 200 and passed both role contracts:

| Role | SST shape | Raw bytes | Observed request duration |
| --- | --- | ---: | ---: |
| Context | 1 × 565 × 501 | 407,204 | 5.74 s |
| Native patch | 1 × 12 × 12 | 57,719 | 1.81 s |

These two measurements are not a completion forecast or scientific QC approval.
NASA has one daily granule per request, so the full same-scope equivalent would
require **554,218 requests** (2,554 context plus 551,664 native location-days),
rather than NOAA's 48,562 multi-day-capable requests. Applying the two observed
file sizes uniformly gives an illustrative **32,881,493,432 bytes**; metadata and
file overhead make the NOAA 20.9 GB estimate inapplicable to NASA. File sizes and
latency vary, and retry/load limits need a separate bounded bulk plan. The
16-request qualification operator cannot silently launch this full acquisition.
A staged NASA context-first / NOAA-native recovery can make progress without
committing to hundreds of thousands of NASA requests; the selected recovery
sequence must be recorded before a new bulk worker starts.

## Selected NASA context-first recovery

After the live fallback checks, the user selected **NASA daily regional context
first, followed by NOAA native patches when access returns**. This does not
launch the 554,218-request NASA equivalent.

The independent context plan is
`9764ab4f4bb7890f9f06f3bb395b0e11581bdc5b05543d1af38c51b9a6a272c1`.
It binds the retained source inventory and NOAA hybrid identity, requests 2,554
context days over 2017–2023, and keeps the two known February 2021 dates excluded.
Its conservative preflight allowance is 2,678,063,104 bytes (1 MiB/day); its hard
cumulative raw cap is **4 GiB**, including prior disjoint pilots. This is an
acquisition ceiling, not a measured total size. Daily files remain ≤8 MiB.

```bash
python scripts/acquire_nasa_sst_context.py preflight \
  --inventory /private/path/inventory.json \
  --output /private/path/nasa-context-plan.json

python scripts/acquire_nasa_sst_context.py acquire \
  --plan /private/path/nasa-context-plan.json \
  --destination gs://PRIVATE_BUCKET/research-sst/issue103/hybrid/nasa-context/PLAN_SHA256 \
  --work-root /private/path/staging \
  --credential-file /private/path/earthdata-token.txt \
  --output /private/path/context-reconciliation.json
```

Execution requires `--execute`; bounded pilots use exact `--request-id` values
or a prefix `--max-requests`. Use physical paths without symlink ancestors.
Credentials stay private and local. The context archive classifies every actual
product generation. Exact interim `04.1nrt` containers can be retained as
**separate unapproved raw provenance**, with `eligible_for_final_series=false`;
the strict final-series qualification validator still rejects them. Unknown
versions, invalid fields/grids/timestamps, or incomplete downloads stop the run.

The broader NASA qualification acquired 14 files / 1,504,194 bytes. Thirteen
passed the strict final-generation contracts; **2017-01-01 declared interim
`04.1nrt`**, so the complete pilot was correctly rejected as a final series.
Eight further metadata probes found final `04.1` for 2017-01-02, 2017-01-03,
2017-12-18 and the sampled 2018/2020/2021/2022/2023 year boundaries. These samples
do not establish final coverage on all other dates. Retain the added 2017 gap
and any later interim/missing dates explicitly in reconciliation and review.

The private three-date context storage pilot passed full byte read-back and
resume without re-downloading. Resume after budget compaction also passed
(reconciliation `522d5f5318315b3dba49ebf23e91857f590684bb11750a227069a4ebd4f041da`).
Initial storage evidence:
**3 files / 1,217,933 bytes**, comprising two final products and one separately
classified interim product. Its immutable reconciliation ID is
`f69d811b26886818285e40a56f61da4df1f60c15640f63a85e3b15ef5d5151b9`.
The private destination is
`gs://data-infra-infobio-ocean-data/research-sst/issue103/hybrid/nasa-context/9764ab4f4bb7890f9f06f3bb395b0e11581bdc5b05543d1af38c51b9a6a272c1`.

`complete_unapproved_context_acquisition` means only that the requested regional
raw context was reconciled. Its report has `full_hybrid_acquisition_complete=false`
and `native_patch_acquisition_pending=true`, and reports final/interim counts
separately. It never establishes native sampling-area coverage or Chat readiness.
Local operation avoids copying the Earthdata credential into GCP, but progress
depends on the workstation remaining awake, connected and normally authenticated.
Cloud credential persistence or a different resource plan requires explicit
preparation/authorization. The old 75-tile bulk job must not restart.

## Verification and completion

The full backend/security suite passes **1,128 tests**, with 39 service-gated
skips and **79.78% coverage**. The 31-test hybrid/NASA/previous-acquisition group
passes. Active Python Ruff and the generated Chat-scope check pass. Tests cover
multi-day journal binding, exact calendar/exclusions, role and stride separation,
NRT rejection, private byte-verified resume/tamper detection, provider redirect
boundaries, retained failure journals and full terminal reconciliation.

CI also surfaced the newly published [sharp advisory GHSA-wq5f-xc86-pv6w](https://github.com/advisories/GHSA-wq5f-xc86-pv6w).
The existing override is patched from 0.35.4 to 0.35.5 and its lockfile refreshed.
The patched production audit reports zero vulnerabilities; all 64 frontend
tests, typecheck and production build pass locally. This fixes the blocked branch audit; production remains v0.7.2 until a separately
authorized software release/deployment. Acquisition does not deploy this patch.

The completion follow-up must track the new hybrid plan/qualified execution,
never restart the old worker, and reconcile both evidence roles separately.
Scientific approval/publication remain prerequisite to historical-data Chat QA.
The requested SST-only and SST+eDNA Chat questions must distinguish published
evidence from raw acquisition and report any remaining scientific gate. #103,
#102 and #89 remain open.
