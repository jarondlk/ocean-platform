# Historical SST access and initial product comparison — #103

Observed 2026-10-06 JST using the fresh ANEMONE inventory
`62e513192cda70d576dd8c8b60713c41830a01b8fcb6ec0e1f0ebff911f9ab3d`
and comparison plan
`e0cae31637fae0d4e1f60de0d929830a49d2efa3bbfb5ac745d74c717604c1d4`.
This records user product selection, a preliminary recommendation and retained access evidence.
It does not approve a product/QC definition, sampling areas or scientific links.
Production remains v0.7.2; #103 and #102 remain open.

## Authenticated access is established

An existing accepted P-Tree research account was found. Certificate-verified
implicit FTPS on port 990 successfully listed historical SST directories and
downloaded four explicitly selected full-disk NetCDF4 files. Both control and
data connections were encrypted. Passwords and account names are excluded from
code, plans and public receipts. No registration, account change or provider
email was sent.

The files totaled **402,428,224 bytes**. Provider MD5 sidecars matched the bytes;
SHA-256 identities are recorded below. Three geographical footprints reuse the
same full-disk files. This was a four-file probe, not archive acquisition.

| Nominal UTC | Product/file version | Bytes | Raw SHA-256 |
| --- | --- | ---: | --- |
| 2017-12-18 daily | H08 v1.2 daily, fv01.0 | 131,580,634 | `8d775e3df2c1e772371cfa7eb7824331a04f83b7cb502227acb9e15331096efd` |
| 2017-12-18 09:00 hourly | H08 v2.0, fv01.0 | 31,047,250 | `48cd1b9dd7a20ad39a63177881ff1de1e1a69bd69b790e770a68dc21125e412d` |
| 2023-07-15 daily | H09 v2.2 daily, fv01.0 | 187,157,807 | `9f6e53cf34e92dd17b4c31c3cdb986b3367e23958e6e366c7854ac37918a1de5` |
| 2023-07-15 09:00 hourly | H09 v2.1, fv01.0 | 52,642,533 | `25f3fe1e120654bf91ff7437a4b7ac691424457ee5491529bdd7a5ee4ab4f143` |

The 2017 daily file is in `v102_nc4_normal_std_daily`; the 2023 daily v2.2
file is in **`v201_nc4_normal_std_daily`**. Directory names do not establish
the algorithm version. Explicit filename plus NetCDF product metadata must
agree; no version is inferred from the observation year.

A separate 2023-02-15 listing in JAXA's documented reprocessing interval contains
v2.1 daily **fv02.0** and v2.2 daily **fv01.0**. Those files were not downloaded;
listing evidence does not verify binary content or full-interval completeness.

## Native-grid diagnostics

Six retained MUR subsets and twelve Himawari footprint inspections passed their
raw hash, variable, product and bounded-grid diagnostic checks. The footprints
are 0.1-degree coordinate probes, not reviewed sampling areas. Each Himawari
footprint contains 25 native pixel centres. MUR has a different native grid and
land mask; denominators in this table are deliberately separate.

| Coordinate probe | Date | MUR finite ocean pixels / ocean pixels; mean °C | Himawari daily finite pixels / all pixels; mean °C | Himawari 09:00 hourly finite pixels / all pixels; mean °C |
| --- | --- | --- | --- | --- |
| 45.541667°N, 141.9375°E | 2017-12-18 | 97/97; 2.67 | 0/25; unavailable | 0/25; unavailable |
| 45.541667°N, 141.9375°E | 2023-07-15 | 97/97; 18.60 | 0/25; unavailable | 0/25; unavailable |
| 17.458333°N, 148.6875°E | 2017-12-18 | 121/121; 28.72 | 25/25; 28.34 | 0/25; unavailable |
| 17.458333°N, 148.6875°E | 2023-07-15 | 121/121; 29.66 | 25/25; 29.76 | 25/25; 29.88 |
| 38.625°N, 141.4375°E | 2017-12-18 | 22/22; 12.45 | 1/25; 7.93 | 0/25; unavailable |
| 38.625°N, 141.4375°E | 2023-07-15 | 22/22; 23.71 | 0/25; unavailable | 0/25; unavailable |

These are unweighted means of the finite native values. No research QC cutoff,
uncertainty rule or area weighting was applied. Land/sea eligibility, time
statistics and spatial support differ. Differences between columns are **not
paired bias estimates** or evidence that either product is scientifically more
accurate. A no-data pixel does not establish its cause as cloud, coast or QC.
MUR's interpolation/analysis can supply values where a satellite retrieval cannot.
The small fixed set does not prove complete national/year coverage.

## Semantics and adapter findings

- [NASA describes MUR](https://podaac.jpl.nasa.gov/MEaSUREs-MUR) as a daily
  foundation analysis combining satellite and in-situ inputs. It must be labeled
  as an analysis, including when satellite-source Chat settings make it eligible.
- [JAXA's README](https://www.eorc.jaxa.jp/ptree/documents/README_HimawariGeo_en.txt)
  distinguishes hourly skin retrievals, older daily minima and v2.2 daily means.
  The observed v2.2 file's `sea_surface_temperature` explicitly says **daily mean**;
  it also provides `sst_daily_min`, `sst_daily_max` and `sst_count`. The 2017
  v1.2 file has the older daily statistic. Do not combine these as one daily-mean
  series. A uniform older-year mean would need a reviewed hourly aggregation path
  and separately measured acquisition cost.
- The v2.2 daily file labels `sses_bias`, `sses_standard_deviation` and
  `l2p_flags` as applying **at `sst_daily_min`**. Their applicability to the mean
  requires scientific review; a generic variable-name match is insufficient.
- Full-disk longitude crosses +180/-180. The probe unwraps coordinates only for
  bounded native-index selection and records that operation. The existing
  scientific normalizer requires monotonic axes and has not been represented as
  ready to publish these unmodified Himawari full disks.
- The files' CF `time` comment states leap seconds since 1981. Standard CF decoding
  yields nominal time plus **17 seconds in the 2017 files and 18 in 2023**.
  The advertised UTC coverage agrees with filenames, but the probe preserves the
  decoded offset and flags time interpretation for review. It applies no silent
  correction. Pixel `sst_dtime` and the hourly/daily coverage window must also be
  handled before scientific sample-time matching.
- [P-Tree's registration conditions](https://www.eorc.jaxa.jp/ptree/registration_top.html)
  retain research/education restrictions for these historical years, prohibit
  third-party data redistribution and require contacting the secretariat before
  public research-result release. Raw files remain private local evidence.
  Product selection must record the appropriate distribution/use authority.

## Preliminary recommendation and remaining acceptance

**Recommend MUR v4.1 for the primary historical acquisition**, retaining Himawari
as a separately labeled optional retrieval comparator. This recommendation is
based on uniform foundation-analysis semantics, bounded public regional subsets,
near-complete mirror timestamps and the observed retrieval gaps/version changes.
It does not replace scientific QC or claim that analysis values are direct
satellite observations. The user selected **MUR v4.1 as primary, with Himawari
as optional comparator**, on 2026-10-06. Named scientific product/QC/time review
remains pending; the acquisition choice does not approve those rules.
No bulk acquisition has started.

MUR's NOAA mirror has 2,554/2,556 requested dates. NASA catalogue metadata confirms
the two missing dates exist in v4.1, but binaries remain unacquired.
[NASA's OPeNDAP service](https://podaac.jpl.nasa.gov/OPeNDAP-in-the-Cloud) supports
regional variable subsets with Earthdata login. An authenticated, checksum-pinned
same-product recovery path remains to be implemented and verified.

Before full execution: confirm scientific product/quality/time rules,
measured full-plan runtime/storage and a suitable durable destination.
The estimated MUR raw archive is about 55 GB before other evidence/artifacts;
the local workspace had only about 28 GiB free during this probe. Full acquisition
must use bounded staging and reviewed durable storage. Keep every gap explicit.
Scientific linkage/publication additionally depends on #102's applied sampling/
area evidence and independent acceptance. #89's six original demonstrations are
unchanged.

Private receipts are under `/tmp/ocean-issue103-implementation/`:
`himawari-raw/probe.json`, `himawari-selection.json`, `himawari-listing-2023/`,
`himawari-reprocessing-list/`, `ptree-2017-listings.json` and
`comparison/comparison.json`. Raw NetCDF and credentials are outside Git and have
not been attached to GitHub, uploaded to GCS or published into Chat.
