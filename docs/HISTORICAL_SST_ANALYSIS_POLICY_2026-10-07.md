# Historical SST/ANEMONE analysis policy

Subsequent status: v0.7.4 provisional Miyagi publication and production Chat
acceptance passed on 2026-10-08 JST. The following preparation account retains
its dated evidence; see [current operations](RELEASE_0.7.4_OPERATIONS.md).

User choices recorded 2026-10-07. Reviewer display label: **ANEMONE**. These
choices were supplied by the user; provider endorsement is not asserted. The
user accepted the provisional QC/comparison defaults in this conversation.
Production remains v0.7.3; this packet does not apply scientific registries or
publish historical evidence.

## Selected scope and sample handling

1. Cover all ANEMONE locations and the retained 2017–2023 sampling years.
2. Use larger coastal regions. Prepare a reproducible region map with explicit
   boundaries and unmatched-location warnings; do not invent membership from
   an unverified worldmesh value or call the nationwide bounding box a coastal
   region. Exact regional geometry is still an implementation/review input.
3. Keep the 343 explicitly labeled negative controls separate. Include the other
   records provisionally, preserving their source classification and showing
   `provisional` status; do not rewrite all unknown classifications as confirmed
   environmental samples.
4. Inspect sampling metadata/names and laboratory methods when evaluating repeated
   occurrences. Different methods remain separate analysis strata. Matching methods
   alone cannot establish that two records came from the same water collection.
   Keep unresolved identity groups visible instead of silently merging them.
5. Retain both filters but count one water collection once for detection frequency.
   Preserve filter/assay results for read-count reporting; aggregation across
   filters requires identified relationships and a consistently documented basis.
6. Choose the most recent assay within a confirmed collection and matching method/
   protocol. Use an actual sequencing/processing timestamp. Neither download time,
   a run-number suffix nor the strongest positive result establishes recency.
   Missing/ambiguous recency yields an explicit warning and unresolved selection.
7. Initial assignment method: **QCauto + 3-NN target** (`qcauto_95pct_3nn_target`).
   Preserve QCauto results for separate comparisons; never combine both methods
   into one detection-frequency denominator.
8. Report **detection frequency** and **read counts** separately, with sample counts
   and assigned-target read totals (whole-library totals only when supplied).
   Raw reads are an eDNA sequencing metric, not a direct
   measurement of fish population abundance. Cross-library comparisons need
   relative-read summaries alongside raw totals.
9. Report every nonempty sampling stratum, including one sample; no minimum hides
   descriptive results. Proposed warning tiers: fewer than 3 independent water
   collections = very sparse, fewer than 10 = limited support. Show numerator,
   denominator and uncertainty. No sampled collections means unavailable, not zero.
10. Retain and display `empty` tables. Their biological non-detection/assay-success
    meaning remains unresolved, so they are not zero detections in the frequency
    denominator. Record confirmed faults separately with source evidence; uncertain
    quality remains `needs_review`.

## Selected SST and calendar handling

- Use the downloaded final MUR v4.1 regional context first. Keep all 35 final-series
  gaps explicitly listed; retain interim originals separately.
- Initial sample/SST tolerance: **24 hours**. Accepted provisional extension: retry only
  unmatched records at **48 hours** if more than 20% of otherwise linkable records
  are unmatched. Keep original 24-hour coverage, the actual time difference and
  `extended_window` status. Never silently widen matching or present an adjacent
  day's value as an observation on a missing date. Missing coordinate/time/QC
  support must be counted separately and must not justify unlimited extension.
- A date without a time is interpreted as **12:00 Asia/Tokyo**, with
  `assumed_midday` status and the original date retained. Actual timestamps retain
  their original timezone and are converted for Japan-calendar grouping.
- Seasons use Japan time. Proposed winter convention: December belongs with the
  following January–February. Mark incomplete boundary winters explicitly.
- Warm/cool is relative to the same region and season over the available 2017–2023
  baseline. Proposed categories: lower/middle/upper thirds of **all supported daily
  SST**, independent of which days have fish-positive samples. This is a seven-year
  study baseline, not a long-term climatology. Show cut points and tie handling.

## Accepted defaults for provisional analysis

The user accepted these OCEAN defaults for provisional analysis. They are not
NASA-prescribed universal cutoffs. Formal registry application/publication remains
a separate operation; the local preview contract therefore retains `proposed`
and `scientific_approval=false` fields.

| Choice | Proposal | Reporting |
| --- | --- | --- |
| SST uncertainty | Use finite, nonnegative `analysis_error` up to **1.0 K**; compare against **0.5 K** as a sensitivity check. | Record retained/excluded point counts and how regional temperatures change. Kelvin uncertainty is a temperature difference, with no 273.15 offset. |
| Ocean and ice | Use `mask=1` open sea. When ice fraction is reported, accept **0–0.15**; when missing, retain open-sea points with an explicit warning. | Keep land/lake/ice/missing-support counts distinct. Do not replace missing ice with zero. Compare strict missing-ice exclusion as a sensitivity check. |
| Regional support | Aim for **80%** valid open-ocean grid points and at least **5** valid retained points. | Keep sparse summaries visible with warnings. These criteria assess a coarse regional estimate, not five independent satellite observations. |
| Spatial weighting | **Cosine-latitude weighting** of retained regular grid points. | Label as an approximation using subsampled context; compare equal weights in sensitivity checks. It does not recover native coastal detail or exact coastal-cell ocean fractions. |
| Year-to-year comparisons | Show all sampled regions descriptively; use only shared **region × season × method/protocol** strata for the main change comparison. | Also show unmatched strata and effort changes. Never infer a distribution shift from newly sampled areas alone. |

The SST quality/weighting rules can be exercised offline with
`preview_historical_sst_context.py --proposed-quality` and explicit local JSON.
Outputs remain `unapproved_context_diagnostics`. Proposed-rule support flags are
separate from scientific approval and do not create panel/publication records.

```json
{
  "max_analysis_error_k": 1.0,
  "max_sea_ice_fraction": 0.15,
  "min_valid_ocean_fraction": 0.8,
  "min_valid_ocean_points": 5,
  "weighting": "cosine_latitude_grid_point_approximation",
  "missing_ice_policy": "use_open_sea_mask_with_warning"
}
```

## Documentation basis and remaining implementation

NASA describes MUR as a daily SST analysis combining observations, with per-point
uncertainty, masks and ice fields. The product metadata identifies `analysis_error`
as an estimated error standard deviation and distinguishes open sea, land, lakes
and ice flags. These support the field interpretation above; they do not prescribe
the proposed 1 K/80%/five-point acceptance rules.

The real February 2021 diagnostic test rectangle (38–39°N, 141–142°E; **not an
approved coastal boundary**) has 284 open-sea retained points on February 1 and
no reported ice fraction on those points, despite the explicit open-sea mask.
The initial strict-ice proposal rejected every tested day. This motivates the
explicit mask-with-warning proposal above; it does not establish zero ice.

- [NASA MUR product](https://podaac.jpl.nasa.gov/dataset/MUR-JPL-L4-GLOB-v4.1)
- [NASA MUR documentation](https://podaac.jpl.nasa.gov/MEaSUREs-MUR)
- [NOAA/JPL metadata](https://coastwatch.pfeg.noaa.gov/erddap/info/jplMURSST41/index.html)

## Implemented local checks

`preview_historical_sst_matching.py` accepts explicit collection members and
content-addressed daily observations, or a hash-bound context diagnostic with
explicit QC rules. It records Japan-midday assumptions, primary 24-hour coverage,
the bounded 48-hour fallback, actual source dates, source/member warnings and
separate unsupported-time/area results. Region/season thirds use all supported
SST days, independent of fish detections. Ties remain unpartitioned; fewer than
30 supported days produces a short-baseline warning. Existing approved recipe
hashes and matching semantics are unchanged.

Real retained-data mechanics check: two February 2021 occurrences from the Miyagi
review packet matched the diagnostic rectangle's SST within 24 hours (7.33 and
7.42 hours); no extension was needed. Both retained provisional environmental,
identity/coordinate and missing-ice warnings. The 26-day baseline split into
9 low, 8 middle and 9 high days, with a short-baseline warning. February 20–21
remain explicit final-data gaps. These are occurrence proxies in an unreviewed
rectangle, not confirmed independent water collections or an approved Miyagi
coastal panel; this is neither full-period acceptance nor Chat publication.

Retained proof: diagnostic ID
`0b0c4ecf729661ee2c7af1b1b6912a9730944939fa90618b7438c4b0f70ab190`;
matching preview ID
`965fd5a6f8c72e9b06a602e1b64ed1f1367e3afec7d03c91da2be206eeff9e09`.

Full local backend verification passed: **1,230 tests passed, 39 PostgreSQL
opt-in tests skipped, 80.23% coverage**. Active Python lint and the generated
Chat scope contract check passed. PostgreSQL integration and other repository
checks run separately on the exact PR commit in GitHub.

Remaining engineering: explicit coastal region geometry; provisional collection/
filter identities and newest-assay resolution; separate read-count summaries and
shared region/season/method/protocol year panels; full 2017–2023 processing and
coverage checks. The retained 118-assay review packet has laboratory-method fields
but no sequencing/processing timestamps, so latest-run selection remains unresolved
where assays repeat. Bind actual evidence and user decisions through the existing
registry workflow, then normalize/link/publish bounded artifacts and perform
historical Chat QA. Settings are accepted; these implementation and publication
steps remain. #102/#103/#89 stay open.
