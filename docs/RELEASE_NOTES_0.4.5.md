# OCEAN Platform v0.4.5

Release scope and pre-deployment verification are documented below. See the
[fix verification report](ISSUE_59_FIX_QA_2026-09-15.md) for candidate QA evidence.
Production deployment and the eDNA refresh completed on 2026-09-16. See the
[release operations record](RELEASE_0.4.5_OPERATIONS.md) for deployment QA and limits.

This release fixes the chat failures and evidence-handling defects tracked in
[issue #59](https://github.com/jarondlk/ocean-platform/issues/59).

- Generation uses short request-local citation labels, expanded back to canonical
  source IDs before saving and rendering. Bounded ranges, lists, and mixed groups
  are supported; unknown labels, range gaps, reversed ranges, and excessive ranges
  are rejected. The output-limit error remains explicit, with no successful
  partial answers or automatic retry.
- Supplementary analysis, reliability, and linked evidence must match explicit
  filters. Context without sufficient scope metadata is excluded. Aggregate time
  ranges must fit wholly within the selected interval. Source-family filters also
  constrain supplementary evidence; unfiltered cross-source comparisons remain
  available. Empty eligible evidence abstains without a model call.
- Prompt construction packs complete source blocks and records the exact supplied
  excerpts, omitted documents, and text truncation. Citation maps, API ledgers,
  auditing, and saved history use this supplied set. New interactions use prompt
  version `ocean-chat-v4`; historical interactions remain unchanged.
- Citation checks respect the Markdown subset rendered by the UI, including code,
  external links, paragraphs, lists, and table-cell boundaries. Shared fixtures
  test the backend against the actual frontend renderer.
- The UI presents citation checks and coverage, with claim verification explicitly
  marked as not performed. New audits expose `citation_check_status`, `audit_kind`,
  and `claim_verification`. Legacy `trust_level` is `not_assessed`; the retained
  `trust_score` is a compatibility coverage heuristic, not scientific confidence.
- eDNA retrieval document version 3 includes assay-level internal-standard records
  and their source provenance. Standard reads do not enter biological detection
  totals. Missing copies/mL establishes neither absent standards nor absence of
  calibration. The provenance publisher validates the new standard metadata and
  continues to accept historical document versions 1 and 2.
- Blank API questions are rejected. Frontend errors retain codes and interaction
  IDs; date-validation errors show concise messages without echoed request JSON.

## Deployment requirements

This expanded fix requires an eDNA retrieval refresh, unlike the earlier
citation-only candidate. Deploy the updated document builder and provenance
validator together, rematerialize active eDNA documents, recompute invalidated
embeddings, and publish the updated provenance snapshot. Verify the four pilot
standards, method-specific detection totals, and citation navigation against the
refreshed corpus before promoting the candidate. Keep the previous immutable
publication and service revision available for rollback.

No database schema migration or scientific taxonomy renormalization is required.
The 1,600-token deployment cap is unchanged. Cloud QA previews new eDNA summaries
in memory against read-only production data; it does not replace the production
refresh or deployed-service acceptance check.
