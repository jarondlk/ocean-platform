# COP17 introductory card removed

Deployed and verified on `cop17-demo`, revision `ocean-cop17-demo-00017-lbr` at 100% demo traffic.
Frontend source `6d177e9aff1954e04d31101293e8c932d48921d7`, build `efe65db9-b654-4386-bf7c-c4a89c94d9be`.

The Settings sidebar no longer includes “Explore ocean data with your own
questions” or “Free-text search is the default. Advanced examples use predefined
datasets.” The card and its spacing are removed. The question remains prominent,
free-text stays the default, both advanced modes and their fixed setup remain,
and the language selector stays hidden. This changes only frontend presentation.
The entire API container is identical to the previous revision. Model prompts,
chat requests, retrieval, routing, data, scientific constraints, workflows,
authentication, production service and overhaul working files are unchanged.

All 86 existing frontend tests and TypeScript passed. The container production
build, runtime/import, authentication and schema/backup/restore checks passed;
the complete vulnerability scan was reviewed. See `COP17_DEMO_INTRO_REMOVAL_RECEIPT_2026-10-26.json` for findings and
immutable image/proof hashes. No backend SQL or dependency change was needed.

Live regression checks pass for the original Otsuchi Bay sample question,
216-position count, ten example positions, generalized map context, Japanese
location examples and published fish-frequency/SST workflows. Deterministic
answers/citations and advanced top-ten rows match the preceding release, and
each advanced workflow retains six SVG plots. The original sample answer has
the correct August 17, 2020 sample, five supported taxa/ranks and source citation.
The introductory card and language selector are absent throughout; there is no
horizontal overflow. Existing model wording may vary between requests. No new
revision error logs were observed during rehearsal. Temporary QA tabs were closed.

Rollback to `ocean-cop17-demo-00016-wvf` restores the introductory card with
the same API and still-hidden language selector. No deployment schedule, IAM
grant, schema change or scientific-data modification was introduced.
