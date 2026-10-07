# Historical MUR acquisition evidence and execution — #103

Observed 2026-10-06 UTC/JST. Production serving remains v0.7.2. This work
acquires and verifies private raw scientific data; it does not approve scientific
registries, normalize/publish an SST research panel or update the Chat corpus.
The user selected MUR v4.1 as primary, with Himawari as optional comparator.

Subsequent status: the full worker stopped on 2026-10-07 at 07:18 JST after
19,278 verified files. The user then selected a [hybrid strategy](HISTORICAL_SST_HYBRID_2026-10-07.md).
The startup and resource evidence below is retained history; the old bulk
execution must not be restarted. Its raw files/checkpoints remain preserved.

## Completed access/storage evidence

The six-batch storage pilot covers three provisional acquisition tiles and two
seasonal intervals, with 12 dates per child. All **72 files / 20,524,608 bytes**
passed product-title/version, actual 09:00 UTC time, required-variable, raw SHA-256,
immutable private upload and full byte read-back checks. Four completed batches
were subsequently re-read and verified rather than downloaded again.

Final pilot receipt ID:
`cf5832fa30318609cfb2e75c281eebc88223324aa18cb0e1ed6b01848e7f2c42`.
Private receipt:
`gs://data-infra-infobio-ocean-data/research-sst/issue103/mur-v4.1/649bd847eea9530a5f0275430d6436505e2ed0415f0449d0dedf0603de3d8372/pilot-receipts/cf5832fa30318609cfb2e75c281eebc88223324aa18cb0e1ed6b01848e7f2c42.json`.
The receipt checksum was independently verified after retrieval.

The initial worker took about 380 seconds per 12-file batch. A separate TLS-verified
probe of the same provider/file returned identical bytes and SHA-256 in **40.86
seconds with default address selection, versus 0.83 seconds over IPv4**. Provider
DNS advertises IPv6 and IPv4; the observed default delay is consistent with an
unreachable IPv6 route before IPv4 fallback. This is an access diagnostic, not a
scientific difference in the data.

The implementation's optional `--ipv4-only` uses a provider-scoped TCP connection
inside the standard HTTPS connection, preserving certificate/hostname validation.
It does not monkeypatch process-wide DNS, permit cross-provider redirects or disable
TLS checks. The resumed pilot's final two batches took **18.00 and 18.15 seconds**,
including validation, upload and byte read-back. Re-verifying the four saved
batches plus finishing the two outstanding ones took 42.06 seconds.

The subsequent cloud-worker acceptance check acquired **24 additional files /
6,841,536 bytes** from the first two full-history batches, including immutable
checkpoints and terminal partial reconciliation. Execution
`ocean-sst103-acquisition-check-bfw8b` succeeded. Processing the two batches took
44.52 seconds, excluding startup/full-plan validation; partial report ID:
`606cf303ac6d563492f3bb84cabed23a54d8dab3a137bd6bfd46829c143a1c21`.
The temporary timing, six-batch pilot and acceptance jobs are removed after their
receipts are retained. The deliberately cancelled slow pilot is superseded by the
successful resume; its four completed immutable batches were preserved.

## NASA source originals: generation distinction is mandatory

Earthdata registration/email verification and token-authenticated source access
succeeded. NASA Harmony subsetting failed for the first missing granule with a
provider-side missing OPeNDAP-link error. The two exact catalogue originals were
then downloaded using NASA-signed CloudFront redirects. The bearer credential was
sent only to NASA's protected archive, never forwarded to CloudFront, included
in a receipt, uploaded to GCS or committed. The temporary local token file is removed.

| Date at 09:00 UTC | Original bytes | Original SHA-256 |
| --- | ---: | --- |
| 2021-02-20 | 720,062,450 | `1296030dcba970463a7ff3f4f0f9229b02b7278996f98b056917ce8ef80a9070` |
| 2021-02-21 | 722,174,778 | `5a91f15ff4e12ea24476d055d304052ee151d5a146c735a9e61ec3a7ed4027a1` |

Both original files passed declared-size, NetCDF4, actual timestamp, required-field,
axes and product metadata inspection. Their exact private GCS generations
`1791287021035082` and `1791287019402072` also passed full streamed SHA-256 read-back.
Combined originals: **1,442,237,228 bytes**. Retained under
`gs://data-infra-infobio-ocean-data/research-sst/issue103/mur-v4.1/source-originals/`,
with credential-free inspection/storage evidence in `recovery-20261006.json`.

Despite `fv04.1` in the catalogue filenames, both binaries explicitly declare
**`product_version=04.1nrt`** and **“Daily MUR SST, Interim near-real-time (nrt)
product”**. History/comment distinguish interim processing from MUR-Final. They
must not silently fill a final-generation time series. The two final-series gaps
remain explicit pending scientific generation review or verified final originals.
A small retained Miyagi-footprint inspection verifies native values can be read;
its unfiltered means are diagnostics, not accepted scientific area averages.

`acquire_historical_sst.py source-original-check` hashes a retained original before
and after bounded metadata inspection, preserves its generation, loads only axes/
time and emits an unapproved receipt. Its 1 GiB original-file ceiling does not
raise the existing 256 MiB scientific normalizer or panel limits. An original
must be prepared into separately proven bounded inputs before scientific use.

## Full-history worker and resource envelope

The pinned full preflight covers 75 provisional tiles and complete calendar years
2017–2023, with 18,900 child batches. Its exact private GCS generation is
`1791287844055282`; history plan ID:
`649bd847eea9530a5f0275430d6436505e2ed0415f0449d0dedf0603de3d8372`.
The two known mirror-missing/NRT dates are explicitly excluded at each of 75 tiles:
**191,550 NOAA requests and 150 excluded tile/date requests**, with separate NASA
originals. No nearest available timestamp may substitute for a requested date.

`scripts/acquire_historical_sst_cloud.py` is dry-run by default. Execution stages
one child at a time, validates actual source fields/time/footprint, verifies every
published byte and seals an immutable checkpoint. The per-child store layout
avoids a national-sized flat registry index. Existing pilot/worker bytes are
verified and reused. A CAS writer lease prevents a second active worker; ordinary
failure releases it, while hard termination leaves an operator-reviewable stale
lease. Never release a stale lease before verifying the owning execution stopped.
An incomplete batch, ambiguous retained generations, changed bytes or a reached
raw cap stops the run, preserving prior completed checkpoints.

Prepared full-run envelope: one task, parallelism one, no task retries, **1 CPU /
1 GiB**, **64 GiB cumulative retained raw-byte cap**, and **168-hour hard task
limit**. Existing `ocean-jobs` identity and immutable v0.7.2 API image are used with
checksum-pinned reviewed operator modules and preflight. No database, secret,
scientific-data volume, IAM change, serving deployment or model call is involved.
[Cloud Run documents the seven-day task ceiling](https://docs.cloud.google.com/run/docs/configuring/task-timeout).

Measured two-batch throughput extrapolates to approximately **four to five days
serially**; this is an inference from a small pilot, not an ETA guarantee. At the
observed 285,064 bytes per tile/day, raw files would total about 54.6 GB; manifests,
checkpoints, original files and other evidence add storage. The raw cap is an
execution limit, not an approved scientific spatial/QC rule or a guaranteed bill.
[Cloud Run pricing](https://cloud.google.com/run/pricing) and
[Storage pricing](https://cloud.google.com/storage/pricing) apply to actual usage;
shared free-tier availability is not assumed. The existing regional Standard bucket
has uniform access, enforced public-access prevention and versioning. Its current
seven-day live-file lifecycle rule applies only to `tmp/`, not this archive prefix.

Full raw execution **started at 2026-10-06 12:11 UTC**, after all required CI,
CodeQL and migration/dependency checks passed for operator-code commit
`1878b057cd3dcef596c61234230b0d2e2f130ba2`. Job
`ocean-sst103-historical-acquire`, execution
`ocean-sst103-historical-acquire-p2lkt`, is acquiring new historical batches
after verifying and reusing the two acceptance checkpoints. The operator
bundle SHA-256 is `66387a87b6ce8b463ce110ba091976f5ad84c5f34bf6e5fe5292675fac9b956c`.
Live progress and final disposition are tracked in
[issue #103](https://github.com/jarondlk/ocean-platform/issues/103).
This dated note is startup evidence, not a claim of full-run completion. Completion must reconcile all requested
and excluded tile/date pairs, verify preserved originals/checkpoints, and undergo
scientific acceptance before issue #103 or #89 can close.

## Validation and remaining scientific work

The complete backend/coverage run passes **1,113 tests**, with 39 service-gated
skips and **79.70% coverage**. An additional terminal reconciliation test passes
in the six-test cloud-worker suite. Active Python Ruff, generated scope and CLI
help checks pass. Cloud pilot and two-batch acceptance provide actual GCP evidence.

Current applied #102 environmental/physical-sample/area evidence, scientific
product/QC/uncertainty/time/weighting rules, NRT/final treatment, bounded
normalization/linkage/publication, independent scientific acceptance and #89's
six real demonstrations remain open. Raw acquisition does not confer approval.
