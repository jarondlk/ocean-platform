# ANEMONE taxonomy reference and interpretation

Status: released and deployed in v0.4.4 on 2026-09-11 and applied to the
retained production pilot. See the [operations record](RELEASE_0.4.4_OPERATIONS.md).
This changes taxonomy interpretation, not environmental/control classification.

## Reference scope

The user approved `community_qc3nn_target.tsv` as an offline reference for
existing and future eDNA integration. The unchanged file is retained at
[`tests/fixtures/anemone/community_qc3nn_target.tsv`](../tests/fixtures/anemone/community_qc3nn_target.tsv).

- Received from the user on 2026-09-11; provider attribution: ANEMONE DB.
- SHA-256: `e9923f5b0251ec30d61c6b22347c0b0040d6aec4f444e83f0e67975a61defb16`.
- Size: 49,101 bytes; 40 columns; 56 sequence records; 38,260 reads.
- Provider identifier:
  `2021EarthWatchRUN01__20210905T0705-MNC-IshinomakiKotakehama__MiFish`.
- Assignment method represented by the filename: QCauto+95%-3NN.

This is a format and interpretation regression reference, not a taxonomic
reference database, whitelist of permitted species, verified identification
benchmark, or complete acquisition snapshot. It supplies no approved sample
classification, coordinates, assay protocol, control results, or calibration
model. Its presence under tests does not ingest it into the scientific corpus.
Tests that require an assay use explicitly synthetic companion metadata.

## Shared interpretation

`preprocessing/edna_taxonomy.py` owns the shared rules:

1. Blank/non-text values and `NA`, `N/A`, `NULL`, and `NaN` are missing.
2. `unidentified`, `unassigned`, `unknown`, and `unclassified`, either alone or
   followed by whitespace and context, are unresolved at that rank. Matching
   ignores case and surrounding whitespace. For example, `unidentified
   Acanthopagrus` in `species` does not identify a species or independently
   supply a genus assignment; a usable `genus` source field is required.
3. Select the deepest resolved source assignment. If a name is repeated across
   intermediate ranks, prefer its indexed canonical rank. Repeating the same
   name in multiple canonical ranks does not add precision: keep the broadest
   occurrence. Distinct lower-rank assignments remain available.
4. Retain indexed provider labels and every source rank in `taxonomy_json`.
   Only the derived `assigned_taxon_name`/`assigned_taxon_rank` interpretation
   changes during normalization. Sequence, counts, copies/mL, source bytes and
   row locators are preserved; affected derived content hashes change.
5. Analysis excludes unresolved requested ranks with `unresolved_rank`, keeps
   excluded reads visible, and computes proportions using retained reads.
   The rule also applies to old canonical rows that still contain placeholders.
6. Method agreement and control taxon overlap use resolved lineages. Their raw
   evidence remains inspectable; sequence-based control overlap is preserved.
7. Rebuilt retrieval text derives assignment names/ranks from source taxonomy,
   including for older records whose stored assignment incorrectly says
   `isolate`. It does not rewrite canonical rows while rendering documents.

These rules do not rename species, infer missing taxonomy from name suffixes,
verify reference-database accuracy, change read thresholds, pool assignment
methods, or change sample/control eligibility.

## Reference expectations

| Interpretation | Expected result |
| --- | --- |
| Deepest resolved assignments | 37 sequence rows at species, 18 at genus, 1 at family |
| Species analysis, minimum 1 read | 26 named groups; 29,166 retained reads; 19 excluded rows / 9,094 reads |
| Genus analysis, minimum 1 read | 36 named groups; 38,064 retained reads; 1 excluded row / 196 reads |
| Unknown sample classification | All 56 rows excluded from environmental-only analysis |

These are parser/analysis expectations under a synthetic eligible assay, not
an approved environmental result for the actual reference sample. Named
groups are provider assignments, not independently confirmed species.

## Existing data and reproducibility

Normalization defaults to version 3 and records `taxonomy_policy_version` in
both bundle identity and manifest. This policy marker remains pinned even if
an environment overrides the normalization version. Analysis uses
`edna-descriptive-v2`, so old v1 analyses remain verifiable and become
historical instead of being served as current results. Retrieval documents
use version 2; provenance validation accepts versions 1 and 2 and applies the
same source-file and row-integrity checks to both.

New normalized bundles receive new identities while sequence-based detection
IDs remain stable. No schema migration is needed. Deployment alone does not
rewrite previously published rows or document text.

For an existing sample, use the bounded stages in the
[pilot runbook](../deploy/gcp/ANEMONE_PILOT.md):

1. Retain the previous deployment and verified backup, raw snapshot, normalized
   bundle, analyses, and provenance publication.
2. Re-normalize the exact retained raw snapshot with the new code. Preserve the
   same classification review where one exists; never omit a review and thereby
   revert an already-reviewed sample. The current unknown pilot stays unknown.
3. Inspect the normalized diff and run the eDNA-only import validation. Expect
   stable detection identities, counts, sequences, source locators and sample
   classification, with corrected assignment fields and derived hashes.
4. Perform the bounded import, materialize retrieval, refresh affected
   embeddings, regenerate registered analyses, and publish/verify provenance.
   Retain historical bundles for old citations; do not edit them or patch SQL
   assignment fields manually.
5. Verify Data, retrieval text, method comparisons, exclusions, and citation
   navigation against the same source rows. Environmental-only results may
   remain empty because taxonomy interpretation does not resolve classification.

Future files use the same general interpretation rules; their taxa and read
totals need not resemble this reference.

## Verification

Local verification on 2026-09-11 passed 760 backend tests with 13 expected
service-gated skips and 78.26% aggregate coverage. The shared taxonomy helper
had 100% statement coverage. Repository-wide Ruff and `git diff --check`
passed. The focused normalization, taxonomy, analysis, retrieval, classification
preview, and provenance subset passed 87 tests.

The normalization fixtures use a temporary localhost HTTP server; the complete
run used local fixture access after the sandbox-only attempt blocked socket
binding. These local tests did not acquire ANEMONE data or change scientific
classification. The later release passed PostgreSQL integration in GitHub CI
and rebuilt the retained production pilot; cloud verification is recorded in
the [release operations record](RELEASE_0.4.4_OPERATIONS.md).
