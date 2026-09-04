# OCEAN Platform v0.4.0

ANEMONE MiFish eDNA integration for source inspection, reproducible analyses
and citation-grounded research.

## Included

- Bounded sample/run inventory and resumable interpreted-TSV acquisition with
  immutable hashes, source contracts and replay-safe canonical import.
- Separate QCauto and QCauto+3-NN assignments, detection read counts, reported
  copies/mL, internal standards and sample/experiment metadata.
- eDNA data inspection, retrieval documents, exact citations, source provenance
  and reproducible analysis exports. Sample/method filters apply before ranking.
- Method-separated composition/diversity tooling with explicit exclusions,
  descriptive assignment comparison, and guarded environmental matching.
- Verified local/GCS artifact publication, manual bounded job stages and
  publication consistency checks; no automatic archive-wide ingestion.
- Operator classification-review primitives, retained contract history and
  metadata-only recognition of non-target files. FASTQ, images and non-target
  community payloads are not downloaded or analyzed by this MVP.

## Known limitations and next patch

The pilot classification remains **unknown**, by the user's explicit release
decision. The environmental-water proposal is unapproved and must not be
applied. Unknown samples remain citable source evidence but are excluded from
environmental-only composition/diversity and environmental linking. Empty
results with exclusion reasons are expected, not missing data to fill in.

Classification workflow completion and researcher acceptance move to the
[next patch](ANEMONE_NEXT_PATCH.md). This release does not claim validated
environmental biodiversity results for the pilot, contamination clearance,
independent taxonomic accuracy or live CTD/SST overlap. Read counts and reported
copies/mL are not organism abundance; method agreement does not prove accuracy.

FASTQ processing, unrestricted mirroring, scheduled synchronization and
automatic classification are outside this release.

## Operations

Apply additive migrations through `20260903_0008` before serving this version.
Preserve the previous application revision and a verified database backup; do
not automatically downgrade the schema or overwrite user/chat records.

The release record must identify the verified source commit, immutable build,
deployed revision, backup and production checks. Local and CI evidence alone
does not establish live deployment or scientific acceptance. Existing identity,
scale and budget controls remain unchanged, including the user's JPY 20,000
total monthly project ceiling.
