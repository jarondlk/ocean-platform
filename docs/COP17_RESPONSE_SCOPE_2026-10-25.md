# COP17 response scope wording

Status: implemented and locally verified; deployment awaits Google Cloud CLI
reauthentication. The running demo remains at revision `ocean-cop17-demo-00014-mg6`
until a candidate passes the normal build/runtime/scan gates and is deployed.

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

After deployment, rehearse the original Otsuchi Bay question and confirm five
supported taxon names/ranks and source citation without routine excluded-source
prose. Recheck the 216-position count, location examples/geography, and fixed
published fish-frequency and SST scenarios. Scientific limitations and relevant
scope-related abstentions must remain visible when needed.
