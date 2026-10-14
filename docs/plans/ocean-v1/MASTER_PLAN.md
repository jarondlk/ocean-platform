# OCEAN v1.0.0 — Context Catalog and Research Workspace

Planning baseline: 2026-10-12 JST. Accepted design; P00 implementation selected
on 2026-10-13 JST. C01–C27 have not started.
Revised 2026-10-13 JST for a separate v1 site and local UI/UX-first delivery.
This document preserves the scientific architecture and records that amendment.
Use [DECISIONS.md](DECISIONS.md) for locked choices, [STATUS.md](STATUS.md) for
actual progress, and [README.md](README.md) to select one component.

## 1. Product direction

Build a separate OCEAN v1 scientific research environment while the existing
production site retains its legacy architecture. Use fully isolated infrastructure
and explicit approved-data copies as defined in [SITE_SEPARATION.md](SITE_SEPARATION.md).
Start with the local P00 prototype and [UI/UX brief](UI_UX_BRIEF.md), then connect
backend capabilities component by component. The three connected capabilities are:

- **Context Catalog:** an authoritative, navigable inventory of accessible data,
  analyses, statistics, metadata and relationships.
- **Research:** conversations that investigate that catalogue through validated
  operations and retained evidence.
- **Workspace:** a persistent private investigation containing multiple chats,
  selected context, results and approved experiments.

Catalogue exploration becomes the default on the new v1 site after acceptance.
The legacy site retains its routing and traffic. Exact queries
operate over complete matching datasets. Top-k retrieval remains a tool for
targeted documentary evidence, not the gate for structured-data discovery.
A document at retrieval rank 26 must remain discoverable through catalogue
navigation. A system-wide count must not be calculated from the first 25
documents. Navigation itself is not a correctness guarantee: metadata,
deterministic scope validation and completion checks remain essential.

Preserve canonical data, scientific distinctions, provenance, authorization and
existing exact workflows. Repair or quarantine defective evidence before
exposing it through the new catalogue. Existing operational acceptance must
never be relabelled independent scientific approval.

The major UI redesign uses OCEAN Platform branding, restrained ocean-blue
accents, readable tables, light/dark themes and English/Japanese support.
See [the UI concept](mockups/ocean-v1-research-catalogue.png) and its
[interpretation notes](mockups/README.md). The image is illustrative, not live
data or a functioning prototype.

## 2. Context Catalog

### Information architecture

    Context Catalog
    ├── Data
    │   ├── CTD → collections / campaigns → datasets
    │   ├── SST → products → collections → datasets
    │   ├── Metagenome → collections → datasets
    │   └── eDNA → providers / projects → datasets
    ├── Analyses
    │   ├── Published results
    │   └── Available workflows
    ├── Statistics
    │   ├── Inventory counts
    │   ├── Spatial and temporal coverage
    │   └── Data quality and documented gaps
    ├── Metadata
    │   ├── Variables and units
    │   ├── Sampling, assays and assignment methods
    │   ├── Source documentation
    │   └── Provenance and publication manifests
    └── Relationships
        ├── Sample identities
        ├── Matching rules
        └── Qualified overlaps

Within v1, these are virtual views over its canonical objects, not duplicate
records for each directory. The explicitly transferred copy from the legacy
system is separate storage with retained origin provenance.
Identifiers survive display-name/path changes. Location, time, taxon and method
facets reach the same objects without double-counting them.

Data owns records and tables. Every dataset exposes Overview, Tables, Coverage,
Methods, Provenance and Related sections. Source-specific entities include
casts, depth measurements, grids, assays, controls and taxa.

Analyses contains existing published results, input definitions, methods,
qualifications and result tables. Available workflows describe capabilities,
not completed findings. Private experiments remain in their Workspace.

Statistics exposes defined descriptive operations and snapshot-bound results.
Every count names its entity and denominator: datasets, observations, source
occurrences, assays or detection rows. Filtered receipts are retained with an
investigation instead of creating unlimited global directories.

Metadata holds shared definitions and documentary evidence. Relationships
distinguishes physical identity, reviewed matching, proximity and unresolved
associations. Candidate links cannot satisfy verified-comparison requirements.

### Shared human and agent contract

Each node provides stable identity, kind, title, purpose, snapshot, breadcrumbs,
scientific scope, deterministic summary, children/tables, supported operations,
related links, availability/approval qualifications and provenance references.

Listings report applied filters, stable ordering, total matches, returned count,
cursor and completeness. Unknown totals remain unknown. Summaries cover all
qualifying descendants, not the displayed page. Preview truncation and
incomplete underlying data are different states.

Name, path, identity and facet searches are exhaustive and paginated. Optional
relevance ordering cannot exclude inventory members. Ranked evidence search
is a separately labelled operation. Every permitted directory and subdirectory
is reachable; a 100,000-object catalogue need not be loaded into the DOM at once.

### Scientific meaning and snapshots

Keep access eligibility, ingestion, scientific approval, publication, query
readiness and embedding readiness independent. Preserve SST products and spatial
resolution, CTD sampling contracts, complete metagenome measurement semantics,
and eDNA protocol/method/control distinctions. Omitted top-ten taxa are not
zero. Source occurrences are not automatically physical samples.

Distinguish zero matches, missing expected observations, un-ingested or
unpublished data, unsupported operations and unknown coverage.

Build immutable snapshots binding content hashes, publication generations,
classification and relationship versions, and operation versions. Export
canonical eDNA rows and classifications alongside existing immutable artifacts.
Use shared scientific filters and PyArrow/Pandas frozen-data adapters, verified
against current exact services. Reuse current SQL semantics and preserve appropriate local regressions. The
legacy deployment and its endpoints stay independent; v1 reads only its own stores. Queryability must not require a ready embedding index.

Standalone browsing defaults to the latest eligible snapshot. Investigation
browsing uses its pinned snapshot. Explicit refresh creates an updated branch
and flags removed/replaced selections; the original remains reproducible.
Current revocations and permissions override historical access.

## 3. Research engine and evidence

Use a separate controller rather than embedding an agent loop in the existing
monolithic Chat handler. Provide typed tools for:

- Catalogue overview, list and open.
- Coverage and validated counts, summaries and record queries.
- Qualified relationships and published analysis results.
- Scoped evidence search and retained evidence opening.
- Experiment proposal preparation, without automatic execution.

Use the provider-independent structured model interface; native function
calling is optional. The model receives no unrestricted SQL, administrative
tools or publication capability.

Each run freezes its snapshot and effective context revision, resolves the
question's geography/dates/taxa/products/methods, inspects the permitted
inventory, explores iteratively, checks completion and synthesizes grounded
results. Explicit constraints are binding. Conflicting or unresolved qualifiers
require clarification. Exact and synthesis routes share one scope validator.

Maintain a checklist of relevant datasets, completed operations and unanswered
questions. A model finish action cannot establish completeness. Preserve
deterministic shortcuts for exact counts and eligible published workflows.

Keep broad inventory summaries and scope in context, loading bounded evidence
as necessary. Compact older observations into references while preserving
critical limitations. Receipts bind operations, parameters, snapshots, input
identities, result hashes and completeness. Large results remain server-side.
Final citations reference evidence actually supplied to synthesis. Citation
validity is traceability, not factual verification.

Chats have separate transcripts. Investigation attachments/pins are shared;
another chat's generated narrative is not automatically scientific evidence.
Explicitly attach retained results when reusing them.

Persist investigations, conversations, context revisions, runs, events and
receipts through additive migrations. Use a private Cloud Run controller,
Cloud Tasks, transactional outbox, leases and idempotent steps. Checkpoint
between operations. Model runtime results include termination, timing and
available usage.

Initial configurable bounds: 180 active seconds and 12 tool actions per
ordinary run; record pages default to 100 and cap at 500; one malformed-action
repair within the same budget. Clarification/approval waits do not consume
active exploration time. Interrupted or exhausted runs preserve completed
observations and report unresolved work. Continuation is a linked run on the
same snapshot.

## 4. Approved experimental Python

Experiments use only currently eligible frozen inputs. Present question,
cohort, exclusions, pairing, method, code, assumptions, expected outputs and
resource limits before approval. Bind approval to proposal/code/input hashes;
changes require renewed approval. Execution approval is not scientific approval.

Use a dedicated GCP Linux worker with gVisor. A trusted supervisor stages inputs
and collects outputs. The sandbox receives no production credentials, database
access, external network, host sockets or package installation capability.

Use a pinned Python scientific environment. Initial bounds: two CPUs, 4 GiB,
ten minutes, 256 MiB inputs and 50 MiB outputs; one active experiment per user
and two globally. Retain code, environment/image identity, seeds, input hashes,
logs and validated tables/plots. Treat output files as untrusted; preview only
approved formats. Never execute returned HTML/notebooks in the application.

Experimental labels survive Chat, Workspace, citations and exports. Results
cannot automatically update classifications, verified relationships or published
analyses. Existing scientific review/publication remains a separate process.

## 5. UI and public interfaces

Primary navigation on v1: Research, Context Catalog, Tools. Tools preserves
relevant Data, Explore, Provenance and Evaluation workflows in v1. Settings and
Administration remain permission-controlled. Legacy deep links keep working on
the existing site; no shared session or automatic redirect is assumed.

P00 first explores these journeys in frontend-v1 with typed synthetic fixtures.
Use plain-language actions, progressive disclosure, preserved drafts, undo for
reversible choices and clear recovery. Review working interactions with the user
and iterate before backend integration; the static mockup does not freeze layout.
C15/C16/C18/C25 reuse and integrate this frontend with real v1 contracts later.

Research opens private named investigations. Within one investigation show a
conversation list, Chat and a resizable Workspace. Workspace tabs are Context,
Results, Experiments and Evidence. Activity is an expandable action history in
Chat, with cancellation and elapsed time, not hidden model reasoning.

Attach adds available context without narrowing exploration. Pin constraint
explicitly restricts investigation scope. Browsing and display filters do
neither. Context changes affect future runs only.

Citations open retained receipts in Workspace. Tables and plots label their
source as descriptive query, published analysis or experiment, with scope,
authority and provenance.

The standalone Context Catalog has a directory tree, breadcrumbs, searchable
listing, precise totals/paging, snapshot selector and selected-node inspector.
The same browser powers Add context. Deep links and Back/Forward restore node,
snapshot and inspector state. Browse latest does not refresh an investigation.

At narrow widths Chat/Workspace become tabs and the tree becomes a drawer.
Scope, evidence, cancellation and approvals remain accessible. Support keyboard,
screen readers, light/dark themes, long labels and English/Japanese text.

Version contracts for nodes/listings, snapshots, context revisions, runs,
receipts and proposals. New route families:

- /catalogue/* — discovery, inspection and validated queries.
- /research/investigations/* — conversations, attachments, pins and branches.
- /research/runs/* — creation, status, cursor event polling, clarification,
  continuation and cancellation.
- /research/experiments/* — proposals, approval, execution and artifacts.

Revalidate ownership and current permissions on every operation. Viewer
catalogue/evidence access must remain within current Chat permissions;
row-level browsing/export and experiments retain researcher-level restrictions.
Do not leak hidden names, counts or structure.

The legacy site retains /chat, saved interactions, feedback and citation links.
V1 investigations are independent. Legacy-history continuation/import is deferred
until an explicitly approved transfer design exists; do not bridge to production.

## 6. Delivery and acceptance

Sequence: P00 local synthetic UI and user feedback; accepted UX direction; C01–C07
correctness foundations; four-source catalogue/snapshots; staged integration of
the existing prototype with research/controller services; approved experiments;
integrated evaluation and separate-site rollout preparation. P00 is a prerequisite
for implementation, not for planning the later components.

Develop with independent v1 catalogue, research and experiment flags. Rollback
affects v1 only and preserves its investigations/evidence. The legacy deployment,
main-domain traffic, database and storage remain untouched. C24 prepares isolated
site/worker configuration; actual provisioning and launch require later authorization.

P00 acceptance requires locally working journeys and recorded user review, not a
claim of backend capability. C26 separately verifies real-service integration,
full infrastructure separation and synthetic approved-data transfer contracts.
Required live isolation and real data-transfer gates remain explicit.

Catalogue/UI gates: every permitted directory and leaf reachable; 100,000-object
fixture with targets beyond legacy rank 25 and first pages; identical agent/UI
membership and scoped counts; exact totals independent of previews; no
cross-link double-counting; distinct empty/zero/unknown/unavailable/error states;
explicit context changes; functional deep links, reload/resume and responsive
accessible bilingual layouts; no cross-account leaks.

Scientific/execution gates: exact numerical reference parity; rejection of
incompatible model actions; preservation of sampling, protocol, physical-identity
and authority qualifications; no mixed snapshots or duplicate execution;
reopenable evidence; reproducible experiments; effective approval/isolation/
budget controls; existing exact workflows/history/citations remain compatible.

Evaluate the actual controller against legacy Chat using identical scopes,
permissions and snapshots. Deterministic acceptance requires full inventory
accounting and numerical parity, with zero critical scope/authority violations.
Report live-model factual errors, completion, latency, tool use, tokens and
cost separately from citation validity. Paid/provider/live acceptance requires
separate authorization and cannot be claimed from synthetic tests.

All four current source families are in scope. Contig ingestion, unpublished
experimental inputs, external downloads, R, GPUs, collaborative workspaces and
automatic scientific publication are outside v1. Existing providers and roles
remain. Infrastructure provisioning, production data changes and deployment
are not authorized by creating this planning package.

## 7. Scalability assessment

The 2026-10-13 [scalability review](SCALABILITY_REVIEW.md) evaluates growth in
data, analysis methods and concurrent users against this architecture and the
current checkout. It identifies proposed refinements for bounded data access,
incremental snapshots, extension contracts, agent completeness, admission and
capacity evidence. The architecture is extensible; achieved capacity is not yet
established. Proposed workload targets do not supersede accepted decisions.

The review does not change component states, dependencies or implementation
authorization.
