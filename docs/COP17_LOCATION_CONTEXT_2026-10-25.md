# COP17 location examples and generalized map context

This demo-only change preserves the existing count-only v2 and geographic-coverage
v3 evidence. It adds an immutable v4 receipt for count-plus-examples requests and
for generalized named-area context. Ordinary sample retrieval and fixed published
fish/SST analyses retain their routing and scientific scope.

## Questions

- How many sampling locations are recorded in ANEMONE DB?
- How many sampling locations are recorded in ANEMONE DB? Please show me 10 example locations.
- How many named areas are available in ANEMONE DB?
- ANEMONE DBの採水地点はいくつありますか？10か所の例を示してください。
- 名前のある採水エリアはいくつありますか？

Use Free-text search with ANEMONE eDNA enabled. Exact project, run, taxon, date,
coordinate, assay and control filters are retained. Unsupported place/date text
continues to request explicit source filters rather than silently widening scope.
Examples accept 1–20 positions (default 10), ordered by exact stored latitude and
longitude with the smallest matching sample ID as the representative source row.
They are deterministic examples, not a random or geographically representative set.
The requested example limit never changes the full-cohort total.

## Scientific meaning and map attribution

The current default published scope has **216 distinct recorded coordinate pairs**.
Repeated dates, assays and assignment methods do not multiply this count.
Coordinates include provider grid positions; precise physical sampling sites and
official named-area membership remain unverified.

A separately versioned offline map layer provides approximate proximity context
for **96 positions**, with **120 unassigned**, using **87 reference-name groups**.
This is a partial map-reference grouping, not the official total of named bays or
ANEMONE sampling regions. Reference names include bays, coves, inlets, straits,
marine channels and selected major islands. Names can overlap and vary in scale.
The UI explicitly says **Near [name]**, approximate and map-derived; original
ANEMONE labels, dates, coordinates and source hashes remain separate.

Source: [GeoNames Japan gazetteer](https://download.geonames.org/export/dump/JP.zip),
retrieved 2026-10-25, [format and CC BY 4.0 attribution](https://download.geonames.org/export/dump/readme.txt).
Source archive SHA256: `c9a170e56a214eb4aadd64bca130ce996ed65da5c1f0f05d7d24648e007155bf`.
This product adapts the geographic context from that source; GeoNames does not
endorse the associations. The application retains selected source coordinates,
feature IDs, dates, aliases and source links in the cited immutable evidence.

Matching uses marine reference points within 10 km, or selected major island
points within 20 km when no marine candidate qualifies. A competing candidate
within 1 km of the closest distance is ambiguous. Obvious inland source labels
remain unassigned. These thresholds are context-selection rules, **not estimates
of sampling-coordinate accuracy** or assertions of containment in mapped bays.
A same-type shared source alias within 20 km merges Hakata/Fukuoka references once.
All associations and distance/alias/exclusion rules were reviewed; no manual bay
boundary validation is claimed. The Otsuchi coordinate remains unassigned because
the Otsuchi and Funakoshi reference points are almost tied; the original ANEMONE
Otsuchi sample label and original sample-search answer are preserved.

## Evidence and release checks

V4 evidence retains the unchanged v3 full-cohort publication/fingerprint receipt,
all exact matching coordinate representatives, applied filters, example options,
map version/hash, selected source features, assignment method and limitations.
Cache identities include publication, filters, map version/hash and presentation
options. Historical v1/v2/v3 citations remain readable. No scientific-table schema
migration or scientific source metadata update is required.

Local checks: 1,689 backend tests passed, 133 optional PostgreSQL checks skipped;
219 focused context/geography/location/original-sample routing checks passed;
86 frontend tests passed. Dedicated PostgreSQL, deployed-snapshot and signed-in
browser results are recorded in the release receipt after acceptance.
