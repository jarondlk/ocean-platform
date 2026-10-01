# OCEAN Platform v0.6.0

Chat settings now select evidence independently for CTD, metagenome, satellite
SST and ANEMONE eDNA. Each source has its own filters, reset and enabled state.
Categorical filters show available choices, with search for long lists and
choices narrowed by the other filters for that source. Date and coordinate
ranges retain explicit range controls.

## Included

- Account-specific browser settings with validated restore and reset. Questions,
  responses and transient analysis links are not stored as settings.
- Source/filter enforcement before retrieval ranking and across linked evidence,
  derived context, exact summaries, prompt packing and retained chat history.
- A visible applied scope and supported generation controls for the selected
  model provider. Selecting no sources returns a deterministic abstention.
- Bounded fixes for tracked summary/count routing, canonical taxon evidence and
  freshness claims. Sampling dates do not establish provider arrival dates;
  read counts do not establish organism abundance.
- English/Japanese labels and searchable, authenticated source filter choices.
- Percent-encoded Cloud SQL URLs work with the standard Alembic invocation.

## Migration and compatibility

Apply application migration `20261001_0014` before sending traffic to v0.6.0.
It expands the chat-history abstention-reason constraint. No corpus reimport,
document identity change, embedding rebuild or new user-settings table is
required. Existing API clients retain the validated legacy filter contract.

Keep the expanded constraint during an application rollback. Downgrading it
is refused while history contains the new reasons. Preserve historical
citations, publications and later user activity.

## Verification and deployment status

Source release and GCP deployment are separate steps. The
[operations record](RELEASE_0.6.0_OPERATIONS.md) records committed source,
remote checks, immutable images, migration, rollout and live acceptance as
they complete. The [implementation record](RELEASE_0.6.0_IMPLEMENTATION.md)
contains local verification and scientific limits.

Until that record confirms rollout, production remains the recorded v0.5.0
deployment. Live issue #70 acceptance remains pending; these changes do not
claim that every scientific or Japanese-language answer is validated.

The accessible ANEMONE observation remains the 2026-09-17 catalogue. Physical
sample identity and unknown environmental classifications remain unresolved.
Settings are local to each browser/account; synchronization, presets and
scheduled ingestion are outside this release.

The initial release tag is retained. A dependency-only runtime amendment updates
PyJWT to 2.15.1 and urllib3 to 2.8.0 after newly reported security advisories;
use the tested amendment and image digests in the operations record for GCP
rollout. The initial candidate must not be promoted without this amendment.
