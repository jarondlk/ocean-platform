# Pilot classification proposal

Status: **draft — not approved or imported**. Prepared from the retained source
on 2026-09-03. The canonical sample remains `unknown`.

The user explicitly deferred this review to the [next patch](ANEMONE_NEXT_PATCH.md).
Do not apply it during the `v0.4.0` release.

## Proposed decision

Classify `20171218T0103-KUM-Otomi-Surface` as an **environmental water sample**,
subject to confirmation that it is field-collected water rather than a blank
or other control. This is an inference from the combined source record, not an
explicit provider category.

The field-collection metadata, water-processing description and filter record
support this proposal together. No single name, coordinate or collection device
is treated as proof. A classification of environmental/non-control describes
the sample's role; it does not mean contamination was excluded experimentally.

## Exact source evidence

Source file: `sample.tsv.xz`, within the [original pilot sample](https://db.anemone.bio/dist/MiFish/ANEMONE/2019KibanS/2019KibanSRUN01/2019KibanSRUN01__20171218T0103-KUM-Otomi-Surface__MiFish/).

| TSV row | Metadata key | Recorded value |
| --- | --- | --- |
| 6 | `lat_lon` | `35.54166667 135.56250000` |
| 8 | `samp_collec_device` | `bucket` |
| 9 | `samp_mat_process` | `filtering water, adding RNAlater to the filter, storing in freezer` |
| 12 | `collection_date_utc` | `2017-12-18T01:03:00Z` |
| 18 | `filter_prod_name` | `Sterivex-HV` |

Rows include header row 1. Values were checked against the decompressed source;
the file hash below refers to the original compressed bytes.

- Provider sample ID: `2019KibanSRUN01__20171218T0103-KUM-Otomi-Surface__MiFish`
- Raw snapshot: `c57c669f0e87953cbbac70a0053f895bc8f6d391bc89ef9f14aa4b34c5ea5432`
- Source file SHA-256: `95e8693c06694a82e922ef07f11e2569bf1116b78819848413b9f73c50abb4b9`
- Acquisition contract SHA-256: `958c8df592571219dd4dbc2c5b454c03501ffc86b855f84fe8ae2c8d100356da`

## What is not established

- No explicit `sample_type`, `sample_category` or `control_type` is present.
- Negative-control pairing, contamination clearance and independent taxonomic
  accuracy have not been established by this proposal.
- Internal-standard sequences are distinct from classification of this sample
  as a positive/negative control. Source `ncopiesperml` estimates are distinct
  from sequencing read counts; neither establishes organism abundance.
- Source `temp`, `salinity` and other numeric fields without reviewed units
  are not used to manufacture environmental measurements or SST overlap.
- General file-format documentation describes the tables, not the category of
  this particular sample.

## Reviewer action

Confirm or reject the proposed environmental classification using the provider
sample record and relevant collection/laboratory protocol. If the evidence is
insufficient, keep the sample unknown. Record the researcher's name, actual
review timestamp, supporting evidence and final rationale before approval.
Permission to prepare this proposal is not scientific approval.

The machine-readable draft is retained locally at
`/private/tmp/ocean-anemone-pilot.DxUnef/classification-proposal.json`.
It has `status=draft`, an environmental proposal, and blank `reviewer` and
`reviewed_at`; normalization and review publication must reject it. It is not
committed to the repository. Preserve it with the other pilot artifacts before
temporary-directory cleanup.

After approval, use the [classification workflow](ANEMONE_CLASSIFICATION_REVIEW.md)
for validation, isolated import, revised analyses, materialization and provenance.
This proposal does not apply a database change, activate a bundle, call a model,
change GCP billing, merge branches or publish a release.
