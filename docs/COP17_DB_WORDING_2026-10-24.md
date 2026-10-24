# COP17 DB wording correction

Deployed revision `ocean-cop17-demo-00012-llq`; API source `133d2210124ea0316bfd82dd73113af2b3524a0d`, build `51bfd8da-47ec-4b4e-9487-cc7a706b9adb`.

The exact visitor question “How many sampling locations are recorded in ANEMONE DB?” was previously rejected because `DB`
was absent from the location-count vocabulary. Both location and geographic
catalogue questions now accept `DB` and `database` consistently. This changes
accepted wording only. Scientific filters, provider/control scope, SQL,
algorithm versions and immutable aggregate evidence remain unchanged. Date,
place and mixed-source restrictions still require their existing verified scope.

The exact question now returns **216 distinct reported coordinate positions**
in the published matching ANEMONE catalogue, with its existing citation and
precision/classification caveats, without invoking a language model.
This does not establish 216 precise physical sites or the number of named bays.

Backend: 1,654 passed, 122 optional integration skips. Location/geography/sample
routing: 184 passed. Container runtime/authentication/schema and image-scan gates
passed. Independent restricted-demo SQL retained the 216-position reference and
historical evidence checks; the completed QA job is sealed. Actual signed-in
cases are recorded in `COP17_DEMO_DB_WORDING_RECEIPT_2026-10-24.json`. The current sidebar frontend, production service,
scientific data, identities and overhaul checkout remain unchanged.

To reproduce, open the demo Chat page, select Free-text search with ANEMONE eDNA
enabled and ask the exact question above. The lowercase `db` and full-word
`database` variants are also covered by regressions.
