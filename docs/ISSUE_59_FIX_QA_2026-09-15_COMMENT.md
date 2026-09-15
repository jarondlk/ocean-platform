Implemented the eight reported defects in the local v0.4.5 candidate:

- Expand and validate citation ranges.
- Enforce explicit filters across supplementary and linked evidence.
- Keep supplied evidence, citation audits, returned sources, and saved history consistent.
- Present citation checks separately from scientific claim verification.
- Include eDNA internal standards with provenance, separate from biological detection totals; preserve unknown calibration status where appropriate.
- Match citation auditing to the rendered Markdown.
- Preserve readable validation errors and failure references.
- Reject blank questions before retrieval.

Verification: 805 backend tests passed, 13 PostgreSQL integration tests passed in a fresh disposable database, and 37 frontend tests passed. A later boundary regression passed within 56 focused tests. TypeScript, frontend build, lint, and diff checks passed; all 29 adversarial probes passed.

The final live candidate batch produced 25 answers, two expected empty-scope abstentions, and one deliberately triggered output-limit error. There were no invalid-citation failures. All 25 answers had matching audited and clickable citation sequences. Five repeated controls questions retained unknown calibration status. These checks do not establish universal scientific correctness.

The candidate has not been committed or deployed. Keep this issue open until rollout, the eDNA retrieval/embedding/provenance refresh, and deployed acceptance checks are complete.
