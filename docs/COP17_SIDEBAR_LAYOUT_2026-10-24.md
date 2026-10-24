# COP17 question-first layout

Deployed and verified on `cop17-demo`, revision `ocean-cop17-demo-00011-vgs`.
Frontend source `32db2374b562187bc183882e87cc3a6f9925d490`, build `81a172f4-ceca-4ca3-8089-5bf691ba56d9`.

The question field now leads the main column and has a larger responsive minimum
height. The introductory text, English/Japanese controls, all three search modes,
fixed 3NN + MiSeq explanation and active-example return control are grouped in
the Settings sidebar above the existing source choices. Free text remains the
default, and example selection preserves its existing fixed setup and draft-restoration behavior.

Verification: 86 existing frontend tests passed, TypeScript passed, the production
build and container/authentication/schema gates passed, and the complete image
scan was reviewed. Local fixture layouts were checked in English and Japanese
at desktop, tablet and phone widths with no horizontal overflow; this preview
performed no scientific or model execution. The viewport override was reset and
both temporary loopback services were stopped.

Actual signed-in demo checks are recorded separately in `COP17_DEMO_SIDEBAR_RECEIPT_2026-10-24.json`. They verify
sidebar placement, language and mode controls, original sample search and the
216-position count using the unchanged API. The frontend-only rollout preserves
the sample-search correction, geographic evidence, scientific data, authentication,
production service and overhaul checkout.

The first live model request encountered Vertex 429 RESOURCE_EXHAUSTED. A spaced
retry succeeded with the correct five source-supported taxa and ranks; the
unchanged API/provider behavior and both observations are retained in the receipt.

To reproduce: open the demo Chat page, type a question in the main field and Ask.
Use Settings for language, Free-text search or either advanced example. On narrow
screens, Settings follows the main content in the existing stacked layout.
Rollback to `ocean-cop17-demo-00010-dq6` restores the previous frontend with the
same accepted API image.
