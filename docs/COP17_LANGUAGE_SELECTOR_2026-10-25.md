# COP17 chat language selector

Status: **deployed and verified**, revision `ocean-cop17-demo-00016-wvf` at
100% demo traffic. The user explicitly authorized immediate deployment after
cancelling the earlier October 26 schedule. No scheduled task was used.

Frontend source: `1ffa7d934e9a9ce2976867961eb28091be3e0e35`. Accepted candidate build:
`66a08847-f324-4c6b-8c4f-91a438f73efd`. Candidate image:
`asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/frontend@sha256:439a6c83a5ebd4291b231e4b94e562c9a8310507fe71c6fefd396697f1771123`.

The COP17 Chat sidebar no longer contains the English/Japanese button row. The
introductory text, free-text default, both advanced examples, fixed dataset/assay
and evidence-source controls remain. The question field remains the main focus.
Saved interface-language preferences are preserved; no locale is added to the
chat API request. Answer-language handling, question routing, source selection,
data, scientific limits, model prompts and all current API behavior are unchanged.
English/Japanese answer selection remains driven by the question. Mixed-language
requests and model wording retain their existing behavior; no new language
guarantee or translation layer is introduced.

Validation: all 86 existing frontend tests, TypeScript, production container
build, runtime/authentication and schema/backup/restore gates passed. The image
scan has zero CRITICAL and zero language-package findings; inherited OS findings
remain 43 HIGH, 58 MEDIUM, 60 LOW and 1 UNKNOWN. A loopback-only layout fixture
confirmed the selector is absent, the question remains prominent and the page
has no horizontal overflow. That fixture performs no model or scientific calls.
The accepted API digest remains pinned and no backend code was deployed.

Scheduling was stopped before any real deployment task was armed. The dedicated
paused queue, unused release identity and custom role were deleted. Temporary
Cloud Run, runtime-identity and repository-reader grants were removed, and the
new Cloud Tasks API was returned to its original disabled state. No repository
tag was created. The subsequent explicitly authorized rollout changed only the demo frontend
image and its source-commit metadata. The complete API container, remaining
service configuration and production specification/traffic are unchanged. Local preview services and tab were closed.

Live verification: the original Otsuchi Bay question returned the same August
17, 2020 source sample and five supported taxa/ranks with citation. The 216-count,
English/Japanese ten-example and named-area/map-context answers are identical to
the prior release. Professor E3-B and E4-B top-ten rows match the preceding release;
each displays six SVG plots. The selector is absent throughout these checks, and
the page has no horizontal overflow. Protected API endpoints still require login.
No new revision error logs were observed during rehearsal. Existing model wording
can vary independently of this UI-only change.

Deployment proof: `COP17_DEMO_LANGUAGE_SWITCH_DEPLOYMENT_2026-10-25.json`. The earlier
`COP17_DEMO_LANGUAGE_SELECTOR_RECEIPT_2026-10-25.json` records the prepared
candidate and cancelled scheduling history. The candidate was deployed without
rebuilding or changing its accepted digest. Roll back the demo to
`ocean-cop17-demo-00015-hh7` to restore the language controls with the same API.
Local preview tabs/services and the temporary live QA tab were closed.
