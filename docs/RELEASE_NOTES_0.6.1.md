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
- The operator scientific QA runner meters the actual API generation client
  and emits bounded, hash-checked evidence records. Initial model acceptance
  failed and a fresh capped batch remains pending; corrected instructions
  alone do not establish answer quality.

No schema migration, corpus import or embedding refresh is required. Japanese
work and acceptance are deferred by the user; existing support remains.

See [implementation and QA](RELEASE_0.6.1_IMPLEMENTATION.md) and
[operations](RELEASE_0.6.1_OPERATIONS.md) for actual validation/deployment status.
