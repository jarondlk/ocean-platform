# Catalogue collection browsing — 2026-11-04 JST

Revision `ocean-v1-beta-serving-00015-m2d` serves 100% of beta traffic. The
metagenome and MUR SST datasets were already deployed alongside CTD, but the
default CTD snapshot and snapshot selector made the other collections easy to
miss. The user selected easier browsing of the existing collections as the next
increment; this rollout does not add ANEMONE or merge scientific snapshots.

The Context Catalog now shows a “Browse collections” section with a direct
dataset button for each currently authorized discovery descriptor. CTD,
metagenome and MUR SST can be reached from the same page, with their full existing
qualification labels. Switching through either a collection button or the
snapshot selector opens the selected collection's datasets and clears the old
source/search/authority filters, parent, selected object, inspector section and
page cursor. Page size is retained. Search explicitly applies to the selected
collection. The switcher is omitted inside an investigation's pinned snapshot.
Discovery errors or invalidation remove its entries through the existing access
boundary; no hardcoded dataset membership or new data discovery endpoint exists.

Source `2dc37de2e6ab5be69a265fa88c4baf03c7b29b21` passed 349 focused frontend
tests and both frontend/hosting typechecks with verified Node 22.23.4. The new
navigation regression covers a filtered, paginated CTD inspector switching to
another collection, URL round-trip and isolation from the original state.
Cloud Build `ec75732e-45e2-49fa-8687-1304154172f1` passed the application build
and isolated nonroot, network-disabled image proof using the approved Tokyo
build identity, staging bucket and `CLOUD_LOGGING_ONLY`. The source-only package
contained 71 selected application files plus packaging/manifest files.

Frontend image:
`context-frontend@sha256:ea1bfd889dab29afd1d6f8dd3315bcad42aba0e58e33e3180cae3ddc43e1c649`.
The candidate was staged Ready without traffic. Fresh service-template and
resolved-revision comparisons verified that only the frontend image (and
generated template client nonce) changed before promotion. Live readback
confirmed 100% traffic and the same staged template. Revision `00014-xzr` is
the traffic rollback target. API image remains
`snapshot-api@sha256:f72ed2a8c95cf65496e9593cf790a6bef9143ab34f55710a17bd350d022c1e37`.
The activation, source data, context settings, identities, secrets, SQL proxy,
ingress, startup and min0/max1 scaling remain unchanged. Login returned 200;
unauthenticated runtime returned 401. No database, IAM, job or legacy changes
were made.

Signed-in browser verification showed all three collection buttons together.
Starting from a CTD source filter and CTD search, selecting MUR SST cleared the
previous search and source filter, selected dataset listing, and displayed
“MUR Miyagi 2020–2023 — provisional regional preview.”
The metagenome button displayed “Existing raw Kraken and MetaEuk genus matrices,”
and the CTD button displayed “Existing raw CTD collection.” Both selected the
correct snapshot and dataset listing directly. The metagenome collection URL
was then reloaded to verify that the selected collection and dataset view are
restorable.

ANEMONE/eDNA remains behind its separate latency/integrity acceptance. The
three-hour schedule remains paused, model/dispatch/worker execution remains
disabled, and the ¥50,000/month notice threshold is unchanged.
