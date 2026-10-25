# COP17 response scope wording

Status: deployed and verified on `ocean-cop17-demo-00015-hh7` at 100% demo
traffic. API source `610131be719ffe715297d7bd0dd267d24b229952`, build
`dc19e3d5-799f-4aa8-8b2a-a132a1163ea4`. The frontend and production service
are unchanged. Rollback target: `ocean-cop17-demo-00014-mg6`.

The demo prompt omits routine prose such as “Applied evidence scope exclusions:
CTD measurements and shotgun metagenome taxonomy sources are excluded by request
settings.” Equivalent routine source-settings summaries are also discouraged.
Source selection is still explained if the visitor asks about it, or if a
needed source is disabled and prevents answering the question.

The evidence-scope metadata, selected evidence, filters, routing, scientific
limitations, citations and answer auditing are unchanged. Scope remains visible
in Settings and evidence details. The non-demo prompt is byte-for-byte identical
to baseline `bcbe5a5c7266d5c9c26d7b8d430cea7b1d6eeb40` for the same inputs.
No CSV aliases or other pending functionality are included.

Validation: 1,689 backend tests passed; 133 optional PostgreSQL tests skipped.
The existing prompt/source-scope/sample/location/geography/demo selection has
311 passing tests. Lint and diff checks passed. A direct prompt comparison
confirmed the identical non-demo prompt, retained demo evidence and applied scope,
and the exception for necessary source-selection explanations. No new database
SQL, schema, frontend or dependency changes are required.

Live verification: the original Otsuchi Bay question was answered twice without
routine CTD/metagenome exclusion prose. Both answers retained the August 17, 2020
sample, three supported species-level taxa, two genus-level taxa and source
citation. The count-only answer and citation are byte-for-byte identical to the
pre-release baseline. English and Japanese count-plus-ten examples still return
216 positions and ten rows. Generalized map context remains 87 reference-name
groups for 96 positions, with 120 unassigned; this is not a verified named-area
total. Professor E3-B and E4-B each retain exact top-ten table-row parity with the
previous release and six SVG plots. No page overflow or new revision error logs
were observed during these checks.

The API passed container/import, authenticated HTTP, schema/backup/restore and
scan review gates. The scan has zero CRITICAL and zero language-package findings;
inherited OS findings remain 44 HIGH, 70 MEDIUM, 82 LOW and 1 UNKNOWN. Protected
API endpoints still require authentication. No new database SQL required a new
restricted-database QA job. Prompt guidance does not guarantee identical wording
for every future model response.

Release evidence: `COP17_DEMO_RESPONSE_SCOPE_RECEIPT_2026-10-25.json`. Private raw
browser proof and screenshots are hashed in the receipt. No CSV aliases were
implemented or deployed.
