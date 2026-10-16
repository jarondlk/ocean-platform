# Final C13 legacy method alias review

A final primary-agent review reproduced an eligibility gap after the first
checkpoint: method_id cross_source_validation was reported unaffected/eligible,
although C02 registers that legacy type as sst_ctd_validation. Publication could
therefore omit the affected method receipt while retaining the old label.

The frozen input validator now resolves the existing positive C02 result-ID,
document-type and file-name aliases before applying the canonical eligibility
rule. It does not infer new aliases or grant approval. Seventeen legacy-label
cases require the unversioned gate, four cases preserve valid canonical reviewed
receipts under legacy labels, and one actual sealed-map case verifies that an
unversioned alias remains qualified Metadata history and cannot join global
published findings. These 22 cases augment the original 283 local cases to 305.

Final required acceptance: 1,991 passed. Full backend: 3,525 passed, 127 gated skips,
84.50% coverage; nine generated checks and active Ruff pass. No SQL, workflow,
frontend, shared catalogue contract, real scientific file or earlier receipt changed.
The original local receipt/source map/evidence are immutable; this amendment
records two source/test path supersessions. Final-source hosted CI is still
required; prior checkpoint CI is retained only as historical evidence.
