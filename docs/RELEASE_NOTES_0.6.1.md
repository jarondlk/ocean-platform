# v0.6.1 — Chat scope and settings patch

**Candidate; Git tag and production promotion pending acceptance.**

- Selected eDNA filters now support ordinary exact-count paraphrases, including
  the rare-taxon questions that previously requested filters already set.
- Count answers emphasize the requested metric. Unsupported qualifiers and
  conflicting methods explain the clarification needed without widening scope.
- Account transitions cannot reuse or save another account's source settings.
  Storage failures remain usable within the session; corrupt scope needs reset.
- Transient analysis reset and late asynchronous responses have regression
  coverage. All-disabled source settings remain all-disabled across reload.
- Environmental/non-control scopes explain their exclusion of unclassified
  records. Answer instructions preserve unknown classifications and separate
  empty concentration tables from missing values/columns. Source-selection
  settings are described without invented scientific citations.
- Generated citations with unknown or invented labels are rejected before an
  answer is returned or saved, including when citation auditing is disabled.
  Historical citation rendering remains readable.
- Scientific instructions distinguish sequencing counts, reported DNA
  concentration, verified calibration and unresolved physical sample linkage.
  Assignment labels do not define laboratory protocols or algorithms.
  Month-only metagenome dates remain month-only; missing analysis evidence is
  distinguished from explicitly disabled settings. Catalogue aggregate counts
  and assay-specific metadata require their respective supporting citations.
- The operator QA runner meters actual API generation calls and captures
  complete hash-checked evidence. Manual review exposed further defects after
  structural checks passed. The corrected English matrix has 31 reviewed
  successful responses; earlier failures/rejections remain in the QA record.

No schema migration, corpus import or embedding refresh is required. Japanese
work and acceptance are deferred by the user; existing support remains.

See [implementation and QA](RELEASE_0.6.1_IMPLEMENTATION.md) and
[operations](RELEASE_0.6.1_OPERATIONS.md) for actual validation/deployment status.
