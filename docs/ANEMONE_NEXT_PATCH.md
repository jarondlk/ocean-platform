# ANEMONE classification — next patch

Decision: on 2026-09-03 the user prioritized `v0.4.0` and explicitly deferred
classification workflow completion. Keep the pilot `sample_kind=unknown` and
`is_control=null`. Its proposed environmental classification is not approved.

## v0.4.0 boundary

- Preserve source metadata, detections, method labels, hashes and citations.
- Keep unknown samples excluded from environmental-only composition/diversity
  and environmental linking; retain explicit exclusion reasons in exports.
- Do not apply the draft, infer a reviewer or relabel the sample to pass a gate.
- Release the existing integration without claiming completed classification,
  contamination clearance, environmental biodiversity validation or validated
  CTD/SST overlap. Classification approval is not a release gate for this scope.
- Operational gates still apply: CI, backup/restore, compatible migrations,
  authorization, source/provenance integrity, bounded costs and deployment checks.

## Next-patch work

1. Review the implemented operator/CLI flow and identify the remaining gaps
   between its tested primitives and a complete researcher workflow.
2. Provide a clear draft/review/approve-or-reject path with exact sample and
   source-row evidence, a real reviewer identity, timestamp and rationale.
   Review permissions and audit attribution must be explicit; current operator
   attestations are not authenticated reviewer signatures.
3. Preview the effect on inclusion/exclusion and derived results before applying
   a decision. Unknown must remain a valid unresolved outcome.
4. Validate and apply approved reviews through the controlled job workflow,
   regenerate retrieval/analysis/provenance, retain prior identities/citations,
   and test replay, failure recovery and explicit rollback.
5. Validate the retained pilot with a qualified researcher. Verify control
   context, scientific outputs and model-answer limitations independently.
6. Complete authenticated end-to-end tests, then document acceptance and ship
   the patch. Do not choose a final classification or approval in advance.

Inputs: [operator implementation](ANEMONE_CLASSIFICATION_REVIEW.md),
[unapproved pilot proposal](ANEMONE_PILOT_CLASSIFICATION_PROPOSAL.md), and
[retained canary evidence](ANEMONE_PILOT_2026-09-03.md).
