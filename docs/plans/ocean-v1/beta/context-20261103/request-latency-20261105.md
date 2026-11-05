# Request latency update — 2026-11-05 JST

The user requested a fix for slow data loads and repeated checks on clicks and
reloads. Source `7b01ea57173f1ead542bbec46f0505845e049ff9` removes redundant
frontend requests and repeats of the same remote authority checks within one
backend read. Follow-up `baecffb46e1728380ca76e71c448b89beba1a1c3` normalizes
conflicts detected by the closing verification into the existing safe 503.

Catalogue root listings reuse the overview response. Inspector selection and
section changes no longer reload the dataset list. A verified navigation path
arrives with the inspector instead of triggering separate ancestor opens.
Research loads saved investigations independently of slow snapshot discovery;
its ten-second list polling no longer repeats discovery. Explicit reload still
refreshes discovery, and context/list polling remains enabled.

Backend read scopes check current activation and lifecycle bytes/generations at
both ends of each operation. They recheck all observed manifests before return,
reject changed control state, and expire on errors and completion. Thread and
copied-context isolation, bounded membership, and a prohibition on retention
writes within read scopes prevent reuse across requests or mutations. Immutable
payloads remain read and hash-verified on every operation; this is not a
cross-request payload cache. Access and scientific qualifications are unchanged.

## Validation and measurements

The focused backend suite passed 321 checks; additional boundary and final
closing-conflict suites passed 172 and 73 checks respectively, with overlap.
Frontend passed 361 checks, both frontend/hosting typechecks passed, and
packaging passed 34 probes. Both accepted images passed their isolated nonroot,
network-disabled source proofs. Broad CI was not rerun for this increment.

An operator-Mac probe used actual beta GCS with a local test principal, not
browser authentication. These single-run measurements vary with network load:

| Operation | Before | After |
| --- | ---: | ---: |
| Discover collections | 11.2456 s | 6.4064 s |
| CTD inspector | 2.7017 s | 1.4542 s |
| Metagenome inspector | 5.1957 s | 4.4520 s |
| SST inspector | 4.1319 s | 2.2559 s |

Discovery activation/control reads fell from 32/24 to 2/2; its 32 immutable
reads remained. Inspector activation/control reads also fell to 2/2, with
immutable reads unchanged. All response hashes matched after excluding only
the added verified navigation path. The final API follow-up changes error
normalization only, after this successful-path probe.

## Deployment

- Frontend source: `7b01ea57173f1ead542bbec46f0505845e049ff9`.
  Build: `fdcd1fa9-c9a1-43d5-8d09-38538a72055f`.
  Image: `context-frontend@sha256:f2354f38c4412cb7c58efbbd3f47be77e2bba707e3d8c43499c9eef008b2c4a1`.
- API source: `baecffb46e1728380ca76e71c448b89beba1a1c3`.
  Build: `65d23d29-0bba-4a63-aa3b-d6f2935df9e6`.
  Image: `snapshot-api@sha256:c4c15379db125dfe506d728a6f17fbcb60fd88613d7cffdcf771e48b2111bc77`.
- Revision: `ocean-v1-beta-serving-00017-kvz`, staged Ready with no traffic,
  then promoted. Fresh Nov 5 readback confirms Ready and 100% traffic.
  Rollback revision: `ocean-v1-beta-serving-00016-sfb`.

The full before/after service template differs only in the API/frontend images
and generated client nonce. Identity, secrets, SQL proxy, ingress, startup,
activation and min0/max1 are preserved. No IAM, database, jobs, legacy,
scientific-data publication, scheduling or capacity changes were made.
ANEMONE/eDNA remains gated, execution remains disabled, and the three-hour
schedule remains paused. The ¥50,000/month notification boundary remains.

Live HTTPS login returned 200 and unauthenticated runtime returned 401.
Authenticated discovery showed all three qualified collections. Sampled live
discovery requests returned 200 in 5.142–5.727 seconds; initial CTD overview
returned 200 in 0.914 seconds. Metagenome switching returned successful overview
and listing in 6.707 and 6.523 seconds. Metagenome inspection showed its complete
ancestry, and the Kraken table displayed 100 of 58,712 retained rows. SST
inspection and its table displayed 100 of 1,455 retained rows. These are bounded
acceptance observations, not a latency guarantee. Several-second initial loads
remain, and scale-to-zero can add cold-start delay.

Final live sampling recorded three successful inspector requests (1.064–4.014
seconds), three list requests (0.860–6.523 seconds), and four table queries
(1.140–8.786 seconds), all HTTP 200. Exactly one inspector open was observed
per selected dataset, including the metagenome section changes; no additional
list request was triggered by those section changes. CTD inspection retained
162 casts and 10,955 depth observations; its casts page displayed 100 rows.
The saved CTD conversation reopened with one attachment and zero pinned
restrictions. During subsequent Research navigation, 13 investigation requests
returned 200 while snapshot discovery ran once (5.429 seconds), rather than
on each ten-second list poll. No saved application records were changed.
