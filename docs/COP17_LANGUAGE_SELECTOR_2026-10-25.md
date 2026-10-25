# COP17 chat language selector

Status: tested and ready; **not deployed and not scheduled**. The user cancelled
scheduling while retaining the update for a later explicit rollout. Live demo
revision remains `ocean-cop17-demo-00015-hh7` at 100% traffic.

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
tag was created. Both live demo and production service specifications match the
pre-change snapshots. Local preview services and tab were closed.

See `COP17_DEMO_LANGUAGE_SELECTOR_RECEIPT_2026-10-25.json` for immutable source,
image and proof hashes. For any future deployment, request a new explicit rollout;
the old scheduling scripts carry a cancellation guard and must not be reused as
an armed task. No deployment is planned for October 26 at 07:00 JST.
