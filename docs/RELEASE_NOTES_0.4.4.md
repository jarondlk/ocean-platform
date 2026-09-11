# OCEAN Platform v0.4.4 release notes

v0.4.4 corrects ANEMONE taxonomy interpretation so unresolved provider labels
do not inflate named genus/species richness or appear as isolate assignments.
The user-supplied TSV is retained unchanged as a checksum-verified regression
reference for existing and future eDNA files.

## Changes

- Shared taxonomy interpretation excludes missing and `unidentified`,
  `unassigned`, `unknown`, or `unclassified` labels at their reported ranks.
  Repeated ancestor names do not imply a more precise assignment.
- Normalization selects the deepest resolved source assignment while preserving
  provider taxonomy, sequences, read counts, copies/mL, and source locators.
- Composition, diversity, method comparison, and control taxon overlap apply
  the same resolution policy, including to previously normalized records.
- Rebuilt retrieval documents correct older placeholder assignments using
  retained source taxonomy.
- Normalization defaults to version 3 with a pinned taxonomy-policy identity;
  descriptive analysis and retrieval documents advance to version 2. Historical
  analysis bundles and version-1 document provenance remain verifiable.
- The reference file remains an offline regression fixture and is excluded
  from runtime container images.

## Verification

The local backend gate passed 760 tests with 13 expected service-gated skips,
78.26% aggregate coverage, and 100% statement coverage of the shared taxonomy
helper. The focused integration subset passed 87 tests. Repository-wide Ruff
and diff checks passed. CI, release, cloud build, and deployment evidence is
recorded separately in the [operations record](RELEASE_0.4.4_OPERATIONS.md).

For the reference file, the tests retain 26 named species groups (29,166 reads)
or 36 named genera (38,064 reads), explicitly accounting for unresolved reads.
These are provider-label interpretation expectations under synthetic eligible
assay metadata, not independently confirmed biodiversity observations.

## Existing corpus

No schema migration or scientific reclassification is introduced. Existing
published canonical rows and retrieval artifacts require a controlled rebuild
from retained source snapshots; deploying the code alone does not rewrite
them. The bounded pilot remains unknown and excluded from environmental-only
analysis. See the [taxonomy reference and rebuild procedure](ANEMONE_TAXONOMY_REFERENCE.md).
