# Interface copy cleanup — 2026-11-04 JST

The user requested removal of distracting copy and unnecessary taglines.
Source `f32d98c1b356db493d71105910bf8b951c863d29` removes repeated page
introductions, OCEAN/v1 eyebrows, the Platform wordmark subtitle, the sidebar
access explanation, settings/account helper paragraphs, About marketing cards,
placeholder tool categories, and generic catalogue and research instructions.
Empty and unavailable states are shorter. Login retains its heading and Google
sign-in control. Both English and Japanese presentation were updated.

Functional labels, accessible control names, retry/conflict/uncertain-write
messages, source-provided descriptions and qualifications, completeness counts,
availability and scientific-approval fields remain. No catalogue, permissions,
mutation, execution or scientific-source logic changed. The redundant research
execution warning is shown only alongside existing activity; disabled execution
controls and other state indicators remain.

All 141 existing focused runtime/navigation/mutation checks and both final
frontend/hosting typechecks passed with verified Node 22.23.4. No tests that
merely assert removed prose were added. Cloud Build
`8de7dc81-b550-446b-8bc2-8e8e96dca8c5` passed its build and isolated nonroot,
network-disabled image proof in Tokyo using the approved identity, staging
bucket and `CLOUD_LOGGING_ONLY`.

Frontend image:
`context-frontend@sha256:7dec51dbf0af4a4ec6c2d44630610d4c5aa9e186eea0e6ab03f1cff4c31ce629`.
Revision `ocean-v1-beta-serving-00016-sfb` was staged Ready without traffic.
Fresh service-template and old/new resolved-revision comparisons verified only
the frontend image and generated client nonce changed before promotion.
Live readback verified 100% traffic with the staged template. Previous revision
`00015-m2d` is the traffic rollback target. The existing API, activation, CTD/
metagenome/SST data, service identity, secrets, SQL proxy, ingress, startup and
min0/max1 settings are preserved. No IAM, SQL, job, legacy or schedule changes
were made. ANEMONE/eDNA and execution gates remain unchanged.

Public login returned 200, with one heading, the Google sign-in control and no
helper paragraphs. Unauthenticated runtime returned 401. Signed-in catalogue
verification showed the three collection controls and the metagenome dataset
with its unknown-denominator qualification, without the removed introductions
or sidebar explanations.

The existing saved CTD conversation opened with one attachment and disabled
execution. Settings retained its language/theme controls without helper prose;
Tools retained its unavailable state without the placeholder category cards;
About retained factual application identity without marketing cards. These
checks made no application data or presentation preference changes.

Research availability initially timed out while catalogue discovery took
8.0–11.7 seconds despite HTTP 200 replies, exceeding that screen's existing
8-second read bound. Its error/reload controls remained visible. The saved
conversation subsequently loaded through its existing direct URL. This is the
already-open discovery latency issue, not a performance acceptance pass; no
deadline or backend was changed by the copy cleanup.
