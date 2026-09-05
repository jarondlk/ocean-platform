# OCEAN Platform

**Ocean Coastal Ecosystem Archive Nexus (OCEAN)** — a provenance-aware
research platform for marine environmental monitoring, centered on Miyagi
Prefecture, Japan, with separately qualified external evidence.

Transforms fragmented field data — CTD water profiles, shotgun metagenome
summaries, satellite SST, and ANEMONE MiFish eDNA — into a citation-grounded
question-answering system where every answer traces back to its original source
and can be audited against the evidence that was actually supplied.

---

## Study Sites

| Bay | Code | Coordinates | Data |
| --- | --- | --- | --- |
| Onagawa Bay | O | ~38.44°N, 141.45°E | CTD + Metagenome + SST |
| Ishinomaki Bay | I | ~38.41°N, 141.30°E | CTD + Metagenome |
| Mutsu Bay | M | source metadata | CTD + Metagenome |

The bounded ANEMONE pilot retains its provider-supplied location and collection
metadata. It is not assigned to one of these monitoring bays by inference, and
its sample classification remains unknown in `v0.4.0`.

---

## Current Prototype Status

Status as of **2026-09-05**: this is an active invite-only **Next.js +
FastAPI** prototype deployed on GCP, with PostgreSQL/pgvector retrieval,
Vertex AI generation and embeddings, Google OIDC, and Cloud Run Jobs for
operator-approved batch work. The same application remains runnable locally
with PostgreSQL and Ollama. The old Streamlit interface is archived for
historical reference; new product work happens in the Next.js UI and FastAPI
service.

Current managed milestone:

- GitHub release [`v0.4.0`](https://github.com/jarondlk/ocean-platform/releases/tag/v0.4.0)
  adds bounded ANEMONE MiFish eDNA acquisition, canonical storage, retrieval,
  citation navigation, descriptive analysis, and registered artifact
  publication. The deployed source is `a63885a573b18eb92c184fb88fdb85b5aae3cb09`
  and the active revision is `ocean-platform-v040-a63885a`.
- The preceding `v0.3.0` revision `ocean-platform-v030-1bb38b8` and verified
  pre-release backup remain the immediate rollback references. Review corpus
  and schema compatibility before rollback; do not overwrite later user or
  chat records.
- Dependency refreshes and the NLTK-free evaluator have since merged to both
  remote `main` and `gcp-dev` at `4a4bd38`. They are post-release maintenance
  and are not part of the deployed `v0.4.0` image.
- The live data plane uses Artifact Registry `ocean-platform`, Cloud SQL
  `ocean-postgres` / database `ocean_platform`, jobs under the `ocean-*`
  prefix, OCEAN Secret Manager entries, and bucket
  `data-infra-infobio-ocean-data`. The former service is private and the
  deletion-protected legacy SQL instance is stopped for bounded rollback; its
  two runtime identities are disabled and its orphan job definitions have
  been removed.
- The post-cutover [GCP resource audit](docs/GCP_RESOURCE_AUDIT.md) records the
  active housekeeping controls and the legacy resources that still require
  explicit approval before deletion.
- The live application is
  [`https://ocean-platform-469489188516.asia-northeast1.run.app`](https://ocean-platform-469489188516.asia-northeast1.run.app).
- GitHub records the successful deployment against the `production`
  environment while `gcp-dev` remains the development branch and `main` the
  stable integration branch.

Implemented in the current prototype:

- Manual batch ingestion and corpus rebuild controls, including preflight,
  background job status, run logs, artifact freshness, manifests, and diffs.
- Traceability surfaces for provenance manifests, document lineage, embedding
  treatment, strict raw-source validation, and upsert planning.
- Expert data workbenches for source observations, CTD profiles, taxa, SST,
  ANEMONE eDNA, derived ecological analysis, and reliability review.
- A bounded ANEMONE MiFish evidence path with separate QCauto and QCauto+3-NN
  assignments, exact source-row citations, method-separated retrieval, and
  explicit exclusion of unknown/control samples from environmental-only work.
- Hybrid retrieval over pgvector + PostgreSQL full-text search with local
  fallback retrieval when PostgreSQL is unavailable.
- Trustworthy multi-source answering with linked cross-source evidence,
  analysis/reliability context injection, Markdown answer rendering, and a
  deterministic Answer Trust Report / Citation Audit.
- Validated citation deep links from chat evidence into exact provenance,
  sample, CTD, taxa, SST, derived-analysis, and reliability views.
- Evaluation run management for standard and ablation runs, saved run browsing,
  analytics, reports, and comparison.
- Invite-only OpenID Connect authentication with verified-email invitation
  acceptance, viewer/researcher/admin roles, research/commercial/internal
  account metadata, immediate suspension enforcement, and audited
  administration.
- Persistent chat interactions with thumbs-up/down feedback, reason codes,
  comments, and an administrator feedback-review/export workbench.
- A consolidated administrator workspace under `/admin` for users, feedback,
  pipeline state, database inspection, system health, and diagnostics.
- Fail-closed production configuration, bounded internal identity tokens,
  default-deny API authorization, request limits, security headers, production
  rate limits, a private-service Compose topology, and hardened CI checks.

Still intentionally future work:

- Complete the researcher-facing ANEMONE classification review and acceptance
  workflow. The deployed pilot remains `sample_kind=unknown` and
  `is_control=null`.
- Deterministically abstain before model generation when filters leave no
  evidence, and expose the active recipe-derived filters and empty cohort in
  the research UI.
- Automatic ingestion, file watching, or scheduled cloud sync.
- Automatic deletion of database rows whose source keys disappear from a batch;
  idempotent upserts retain stale rows and report them for operator review.
- Periodic restore drills and a reviewed retirement date for the stopped
  legacy rollback resources. The live Cloud SQL instance already has seven
  retained backups, seven days of PITR, deletion protection, and a 20 GB
  storage ceiling.
- Calibration and routine release-gate use of the existing opt-in
  LLM-as-judge/quality metrics.
- A least-privilege bridge from the Evaluation UI's start controls to the
  external Cloud Run evaluation job. Production evaluations currently remain
  explicit operator-run jobs.

Documentation map:

- `README.md` is the current public project guide and screenshot source.
- `handoff.md` is the operator/developer handoff for resuming work.
- `docs/ROADMAP.md` tracks completed and planned engineering work.
- `docs/SECURITY.md` defines the authorization and application-security model.
- `docs/DEPLOYMENT.md` covers the supported production topology and operations.
- `deploy/gcp/README.md` tracks the managed GCP prototype topology and
  pre-provisioning templates.
- `docs/TESTING.md` documents local verification and required CI checks.
- `archive/` docs describe historical Streamlit reference material only.

---

## Architecture

```mermaid
flowchart TB
    subgraph Sources["Data Sources"]
        CTD["CTD\n1 TSV, 10,955 profiles"]
        META["Metagenome\n11 TSV files"]
        SST["Satellite SST\n1,848 NetCDF"]
        EDNA["ANEMONE MiFish\n1 pilot sample, 70 detections"]
    end

    PROV["Provenance Registry\nSHA-256 files, rows, and publications"]

    subgraph Preprocess["Preprocessing"]
        CTD_PP["CTD Pipeline\nstandardize, summaries"]
        META_PP["Metagenome Pipeline\nKraken, MetaEuk, groups"]
        SST_PP["SST Pipeline\npoint extraction, daily agg"]
        EDNA_PP["eDNA Pipeline\nbounded acquire, normalize, review"]
    end

    NORM["Normalized artifacts\nlegacy Parquets + immutable eDNA bundle"]
    ANCHOR["Anchor Events\n286 anchors, 496 links"]

    subgraph Analysis["Ecological Analysis"]
        PREANA["Pre-Analysis\n5 ecological analyses\n5 RAG documents"]
        RELIAB["Reliability Ensurance\n4 validation outputs\n4 RAG documents"]
    end

    RETDOCS["Retrieval Documents\n325 total\n323 legacy + 2 eDNA"]

    subgraph Storage["PostgreSQL + pgvector"]
        EMB["Vector Embeddings\n325 x 768-dim\nlocal: nomic / GCP: Gemini"]
        FTS["Full-Text Index\ntsvector + ts_rank_cd"]
        DB["23 PostgreSQL Tables\nscientific + application metadata"]
    end

    RET["Hybrid Retrieval\nVector + FTS + RRF\n+ Linked cross-source evidence"]
    CTX["Context Injection\nAnalysis + Reliability docs"]
    LLM["LLM\nProvenance-aware prompting\nCitation-grounded answers"]
    AUDIT["Answer Trust Report\nCitation resolution + requirements"]

    Sources --> PROV --> Preprocess --> NORM
    NORM --> ANCHOR
    NORM --> Analysis
    PREANA -.->|correlations| RELIAB
    ANCHOR --> RETDOCS
    NORM --> RETDOCS
    RETDOCS --> EMB & FTS & DB
    PREANA --> DB
    EMB -->|cosine| RET
    FTS -->|rank| RET
    PREANA -.-> CTX
    RELIAB -.-> CTX
    RET -->|primary + linked evidence| LLM
    CTX -->|analysis + reliability context| LLM
    LLM --> AUDIT
```

---

## Technology Stack

| Component | Technology |
| --- | --- |
| Language | Python 3.12 + TypeScript/React |
| Database | PostgreSQL 16 + pgvector (cosine similarity) |
| Container | Podman / Docker |
| LLM | Vertex AI `gemini-3.6-flash` on GCP; Ollama `qwen2.5:14b-instruct` locally |
| Embeddings | Vertex AI `gemini-embedding-001` on GCP; `nomic-embed-text` locally (both 768-dim) |
| Data | Pandas, Parquet, xarray, netCDF4, SciPy |
| ORM | SQLAlchemy 2.x |
| UI | Next.js academic UI + FastAPI API; Streamlit archived as reference |
| Search | pgvector cosine + tsvector FTS + Reciprocal Rank Fusion |

---

## Quick Start

### Prerequisites

- Python 3.12
- Podman or Docker
- Ollama

### Setup

```bash
# Create .venv and install the hash-verified development lock
./scripts/bootstrap_dev.sh
source .venv/bin/activate

# Start database
podman machine start
podman compose up -d              # PostgreSQL + pgvector on port 5433

# Pull models
ollama pull nomic-embed-text
ollama pull qwen2.5:14b-instruct
```

### Clean Clone Data Notes

This repository snapshot includes the tracked `data/` artifacts needed for tests,
local evidence retrieval, and app data browsing. Newly generated data remains
ignored by `.gitignore`.

Ignored files/directories needed only for full regeneration:

| Path | Needed for | Notes |
| --- | --- | --- |
| `onagawa_sst_subset/` | `python scripts/ingest.py` SST preprocessing | Local working copy has 1,848 NetCDF files, about 51 MB |
| `himawari_raw/` | Optional raw Himawari `.DAT` parsing | Not required by the default pipeline |
| `data/raw/anemone/` and `EDNA_CACHE_DIR` | ANEMONE acquisition, normalization, and replay | Generated by bounded operator-approved runs; credentials and downloaded source data are not committed |

The invite-only application requires OIDC and signing secrets. Copy
`.env.example` to `.env`, register the callback URL
`http://localhost:3000/api/auth/callback/<OIDC_PROVIDER_ID>` with your OpenID
Connect provider, and fill in `AUTH_SECRET`, `INTERNAL_AUTH_SECRET`, the
`OIDC_*` settings, and the matching `AUTH_ALLOWED_PROVIDERS` value. The two
signing secrets must be different and at least 32 random bytes each.
`AUTH_MODE=disabled` is only for an isolated local preview; staging and
production reject it at startup.

For realistic role-aware UI development without organization OIDC credentials,
keep `AUTH_MODE=required` and set `ENABLE_MOCK_LOGIN=true` in an isolated local
environment. Configure the three `MOCK_*_PASSWORD_HASH` settings using
`python scripts/hash_mock_password.py`. The login page then accepts the fixed
Viewer, Researcher, and Admin mock emails through a normal email/password form.
It creates signed Auth.js sessions and exercises the normal FastAPI permission
matrix. On first API use, each fixed identity is created once in the local test
database; subsequent requests resolve its current role, account type, and
suspension status from PostgreSQL. Plaintext passwords are never committed.
The flag is disabled by default and rejected in staging and production. Use it
only against an isolated development environment: chat, feedback, audit, and
Admin actions retain their real local effects.

Cloud authentication will remain OIDC-backed through a managed identity
provider that can present a conventional email/password experience. The
application will not store production password hashes or implement password
reset, recovery, MFA, or breached-password checks itself. Local mock mode shows
only the mock email/password form; production shows one neutral **Sign in**
action that hands authentication to the configured provider.

Apply application-metadata migrations and bootstrap the first admin invite:

```bash
python -m alembic upgrade head
python scripts/invite_user.py admin@example.org --role admin --account-type internal
```

Invitations are matched to the verified OIDC email. There is no local password
database or public sign-up path. Corpus reloads preserve the application
metadata tables that hold users and invitations.

### Data Pipeline

Recommended manual batch entrypoint:

```bash
python scripts/run_pipeline.py --validate-only
python scripts/run_pipeline.py --preflight-only --stages full
python scripts/run_pipeline.py --execute --tag 2026-07-refresh --embed
```

`scripts/run_pipeline.py` is dry-run by default. Real execution requires
`--execute`. A verified PostgreSQL backup is created before the default
transactional, idempotent upsert. Full replacement is available only through
the explicit `--reset-db` flag. Each run writes status, logs, and a manifest
under `data/pipeline_runs/`.
The `/pipeline` page exposes manual controls, preflight checks, active job
status, per-stage logs, artifact freshness, run history, manifests, and
artifact diffs.

Individual stages remain runnable for focused debugging:

```bash
python scripts/ingest.py                # 1. Ingestion + preprocessing
python scripts/build_retrieval_docs.py  # 2. Anchor events + documents + links
python scripts/run_pre_analysis.py      # 3. Ecological analyses
python scripts/run_reliability.py       # 4. Cross-source reliability validation
python scripts/database_backup.py create --restore-test  # 5. Verified DB backup
python scripts/load_db.py --upsert --embed                # 6. Transactional load
```

Traceability, dry-run planning, and explicit full replacement remain available:

```bash
python scripts/build_provenance_manifest.py --write --run-id 2026-07-refresh
python scripts/load_db.py --upsert --dry-run --limit-keys 25 --json
python scripts/load_db.py --reset --embed
```

The upsert path compares current artifacts with logical database keys and
source-row hashes. It inserts and updates inside one transaction, preserves
unchanged retrieval embeddings, and reports stale rows without deleting them.
`--upsert --dry-run` exposes the same plan without writing.

ANEMONE/eDNA uses a separate bounded operator workflow. Commands are offline or
validation-only unless `--execute` is supplied; acquisition credentials belong
in mounted files and are never passed to processing or serving:

```bash
python scripts/run_anemone_job.py --stage inventory --scope-url <sample-or-run-url>
python scripts/normalize_anemone.py --snapshot-id <snapshot-id>
python scripts/materialize_edna_retrieval.py
python scripts/run_edna_analysis.py --recipe <reviewed-recipe.json> --dry-run
```

See [the ANEMONE pilot runbook](deploy/gcp/ANEMONE_PILOT.md) for the approved
execution, publication, backup, and rollback sequence.

### Launch

Terminal 1:

```bash
uvicorn api.main:app --reload --port 8000
```

Terminal 2:

```bash
cd frontend
npm ci
npm run dev
```

Then open `http://localhost:3000`.

FastAPI requires a short-lived internal identity token on every route except
`/health/live`. Use the Next.js application as the browser entrypoint; do not
expose the FastAPI port publicly in production.

### Containerized with Podman

The compose files are layered so you can choose how much to containerize.

| Command | Starts | LLM behavior |
| --- | --- | --- |
| `podman compose up -d` | PostgreSQL/pgvector only | Uses whatever app you run on your host |
| `podman compose -f compose.yml -f deploy/compose/app.yml up -d --build` | PostgreSQL/pgvector + FastAPI + Next.js app | API connects to Ollama running on your host |
| `OLLAMA_BASE_URL=http://ollama:11434 podman compose -f compose.yml -f deploy/compose/app.yml -f deploy/compose/ollama.yml up -d --build` | PostgreSQL/pgvector + FastAPI + Next.js app + Ollama runtime | API connects to the `ollama` service inside the compose network |
| `podman compose -f compose.yml -f archive/legacy-streamlit/docker-compose.app.yml up -d --build` | PostgreSQL/pgvector + archived Streamlit reference UI | Reference-only parity check against the old UI |

Recommended local macOS setup: containerize the app and database, but keep
Ollama running on the host. That lets Ollama use the normal local runtime path;
Ollama inside a Podman VM on macOS may be CPU-only and slower.

```bash
podman compose -f compose.yml -f deploy/compose/app.yml up -d --build
```

Then open:

```text
http://localhost:3000
```

For an intentional archived Streamlit parity check:

```bash
podman compose -f compose.yml -f archive/legacy-streamlit/docker-compose.app.yml up -d --build
```

Then open:

```text
http://localhost:8501
```

Useful commands:

```bash
podman compose -f compose.yml -f deploy/compose/app.yml logs -f api
podman compose -f compose.yml -f deploy/compose/app.yml logs -f frontend
podman compose -f compose.yml -f deploy/compose/app.yml down
podman compose -f compose.yml up -d postgres
```

If you want the LLM runtime containerized too:

```bash
OLLAMA_BASE_URL=http://ollama:11434 podman compose -f compose.yml -f deploy/compose/app.yml -f deploy/compose/ollama.yml up -d --build
podman exec -it ocean_ollama ollama pull nomic-embed-text
podman exec -it ocean_ollama ollama pull qwen2.5:14b-instruct
```

The containers use these defaults:

| Setting | Container Default | Why |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://ocean:ocean@postgres:5432/ocean_platform` | Uses the compose service name and internal PostgreSQL port |
| `OLLAMA_BASE_URL` | `http://host.containers.internal:11434` | Reaches Ollama running on your host from inside Podman |
| `OLLAMA_BASE_URL` with `deploy/compose/ollama.yml` | `http://ollama:11434` | Set this in the command or `.env` when using containerized Ollama |
| `NEXT_PORT` | `3000` | Host port mapped to the Next.js frontend |
| `API_PORT` | `8000` | Host port mapped to FastAPI |
| `API_BASE_URL` | `http://api:8000` | Internal compose URL used by the Next.js proxy |

Copy `.env.example` to `.env` if you want to override these values locally.
Do not expose Ollama's `11434` port publicly when moving this to a server.

---

## Application

The forward UI migration path is a **Next.js academic interface** backed by a
FastAPI service:

| Route | Description |
| --- | --- |
| `/` | Overview page with per-tab feature map, corpus summary, and health signals |
| `/explore` | Corpus workbench for source coverage, filters, charts, sample detail, and evidence retrieval |
| `/data` | Source observations, CTD, taxa, SST, eDNA, derived analysis, and reliability workbench |
| `/analysis` | Compatibility redirect to `/data?view=analysis` |
| `/provenance` | Traceability manifest, document lineage, embedding treatment, and upsert dry-run |
| `/evaluation` | First-class evaluation suite with background runs and controls |
| `/chat` | Citation-grounded RAG query interface with expert retrieval/model knobs, linked cross-source evidence, Markdown rendering, and an answer trust report |
| `/settings` | Per-user language, formatting, and interface preferences |
| `/login` | Neutral Google OIDC entry point for invited accounts |
| `/evidence` | Compatibility redirect to `/explore?view=evidence` |
| `/admin` | Admin-only workspace overview and navigation |
| `/admin/users` | Admin-only invitations, roles, account types, and suspension controls |
| `/admin/feedback` | Admin-only feedback review, evidence inspection, and CSV export |
| `/admin/pipeline` | Manual batch ingestion state, logs, history, and artifacts |
| `/admin/database` | Expert database explorer, schema view, and read-only query tools |
| `/admin/system` | API, database, model, artifact, and runtime status |
| `/admin/debug` | Debug payloads and low-level diagnostic properties |
| `/pipeline`, `/database`, `/system`, `/debug` | Compatibility redirects into the corresponding Admin section |

Local development:

```bash
uvicorn api.main:app --reload --port 8000
cd frontend
npm ci
npm run dev
```

Then open:

```text
http://localhost:3000
```

The previous Streamlit UI is archived as readable reference material at
`archive/legacy-streamlit/`.

The archived Streamlit interface had **8 tabs**:

| Tab | Description |
| --- | --- |
| **Overview** | Pipeline architecture diagram (Graphviz) with live metrics across all stages |
| **Chat** | Streaming LLM chat with provenance-aware RAG, source citations, and automatic context injection. Shows all sources (retrieved + analysis + reliability) feeding the LLM. |
| **Evidence Explorer** | Search 323 documents by keyword, source type, and bay |
| **Data** | CTD depth profiles, metagenome composition (Kraken/MetaEuk), SST time series |
| **Pre-Analysis** | 5 sub-tabs: CTD Trends, Correlations, Diversity, Co-occurrence, Reliability |
| **Database** | Validated table browser, schema inspector, embedding statistics |
| **Stats** | Corpus metrics, sample coverage, provenance tracking |
| **Evaluation** | Benchmark 15 questions × 4 modes, measuring retrieval precision, source coverage, citation accuracy, context utilization, and latency. Exportable CSV results. |

### Current Expert Controls

The active Next.js interface exposes compact controls where they affect the
workflow:

- **Model**: chat model, temperature, top_p, repeat_penalty, context_window
- **Retrieval**: vector/FTS weights, RRF-k, top-K, linked evidence expansion, pre-analysis toggle, reliability toggle, trust-report toggle
- **Filters**: source type, bay, date range, plus eDNA sample, assay, assignment method, taxonomy, and classification fields
- **Status**: backend connection indicator

### Prototype Screenshots — v0.3.0 UI Baseline

Captured from the authenticated OCEAN Platform Cloud Run deployment on
**2026-08-25** after the parallel-service cutover and full route validation.
These are retained as the v0.3.0 interface baseline and do not show the eDNA
views added in v0.4.0.

![Current overview](docs/screenshots/prototype_overview.png)
*Overview page with corpus counts, source balance, runtime signals, and active
route registry.*

![Current explore evidence workbench](docs/screenshots/prototype_explore_evidence.png)
*Explore evidence workbench with retrieval filters, linked-evidence controls,
diagnostics, and source rows.*

![Current data analysis workbench](docs/screenshots/prototype_data_analysis.png)
*Data workbench showing derived CTD trend analysis inside the active Next.js
interface.*

![Current provenance workbench](docs/screenshots/prototype_provenance.png)
*Provenance workbench with manifest counts, lineage flow, artifact classes, and
source registration diagnostics.*

![Current chat trust report](docs/screenshots/prototype_chat_trust_report.png)
*Chat Trust Report after a real Vertex AI query, showing trust level,
context-aware citation requirements, and citation resolution.*

---

## Project Structure

```text
ocean-platform/
├── archive/
│   └── legacy-streamlit/               # Archived Streamlit UI and container overlay
├── config.py                           # Paths, DB, models, thresholds
├── Containerfile.api                   # FastAPI backend container image
├── compose.yml                         # Default local PostgreSQL + pgvector service
├── .env.example                        # Local container env defaults
├── requirements/                       # Python inputs and hash-verified locks
├── data_contracts/                     # Versioned external-source contracts
├── analysis_contracts/                 # Reviewed analysis recipe schemas
├── deploy/
│   ├── compose/                        # App, Ollama, and production definitions
│   ├── env/                            # Production environment template
│   └── gcp/                            # Managed GCP prototype templates
│
├── api/                                # FastAPI API layer for Next.js
├── frontend/                           # Next.js academic UI
├── docs/                               # Security, deployment, testing, roadmap
│
├── preprocessing/
│   ├── common.py                       # Sample ID parsing, TSV I/O
│   ├── ctd.py                          # CTD load → standardize → summaries
│   ├── metagenome.py                   # Kraken/MetaEuk abundance, QC, groups
│   ├── remote_sensing.py               # NetCDF SST extraction
│   ├── anemone.py                      # ANEMONE normalization
│   ├── anemone_classification.py       # Explicit classification review
│   ├── edna_analysis.py                # Descriptive eDNA analysis
│   ├── pre_analysis.py                 # Ecological pre-analysis (5 analyses)
│   └── reliability_ensurance.py        # Cross-source validation (4 engines)
│
├── ingestion/
│   ├── provenance.py                   # SHA-256 file registration (JSONL)
│   ├── lineage.py                      # Traceability manifests + upsert planner
│   ├── raw_validation.py               # Strict raw-source validation contracts
│   ├── anemone.py                      # Bounded inventory/acquisition
│   ├── edna_analysis_bundle.py         # Registered immutable analysis outputs
│   └── file_inventory.py              # Directory scanner
│
├── schema/
│   └── anchor_event.py                 # Spatiotemporal linking
│
├── retrieval/
│   ├── document_builder.py             # Raw data → narrative text chunks
│   ├── cross_source_linker.py          # same_sample + time_match links
│   ├── edna_document_builder.py        # Method-separated eDNA evidence
│   ├── edna_environment_linker.py      # Qualified observation matching
│   ├── edna_materializer.py            # Transactional retrieval publication
│   ├── hybrid_retriever.py             # pgvector + FTS + RRF (primary)
│   └── local_retriever.py              # BM25 + numpy fallback
│
├── db/
│   ├── backup.py                       # Verified backup and isolated restore checks
│   ├── models.py                       # Scientific corpus SQLAlchemy models
│   ├── connection.py                   # Engine, sessions, init_db
│   └── vector_store.py                 # Ollama embedding + cosine search
│
├── orchestration/
│   ├── answer_audit.py                 # Citation resolution and answer trust report
│   ├── query_orchestrator.py           # Cross-source evidence expansion
│   └── unified.py                      # Prompt builder, linked evidence, context injection
│
├── evaluation/
│   └── benchmark.py                    # 15 questions, 4 modes, 6 metrics
│
├── scripts/
│   ├── run_pipeline.py                 # Manual batch orchestrator + manifests
│   ├── run_anemone_job.py              # Explicit bounded eDNA job stages
│   ├── normalize_anemone.py            # Validate/publish normalized bundles
│   ├── materialize_edna_retrieval.py   # Publish eDNA retrieval documents
│   ├── run_edna_analysis.py            # Reproducible descriptive analyses
│   ├── database_backup.py              # Backup, verification, and restore-test CLI
│   ├── build_provenance_manifest.py    # Manual traceability manifest writer
│   ├── ingest.py                       # Ingestion pipeline
│   ├── build_retrieval_docs.py         # Documents + links
│   ├── load_db.py                      # Transactional upsert/reset + embeddings
│   ├── run_pre_analysis.py             # Pre-analysis pipeline
│   ├── run_reliability.py              # Reliability pipeline
│   ├── update_embeddings.py            # Partial embedding refresh
│   ├── run_evaluation.py               # Evaluation CLI
│   ├── run_ablation.py                 # Ablation CLI
│   └── compare_evaluations.py          # Evaluation comparison CLI
│
├── tests/
│   ├── conftest.py                     # Shared fixtures (synthetic data)
│   ├── test_api_*.py                   # FastAPI contracts for UI pages and jobs
│   ├── test_common.py                  # Sample ID parsing, canonicalization
│   ├── test_provenance.py              # SHA-256, JSONL, dedup
│   ├── test_anchor_events.py           # Anchor creation, coordinates
│   ├── test_local_retriever.py         # Local fallback retriever
│   ├── test_prompt_builder.py          # Prompt structure, context injection
│   ├── test_reliability.py             # Agreement, tiers, anomaly, docs
│   └── test_evaluation/report/...      # Benchmark, metrics, reporting, stats
│
└── data/
    ├── raw/ctd/                        # 1 file (CTD_Onagawa.tsv)
    ├── raw/meta/                       # 11 files (Kraken, MetaEuk, QC)
    ├── raw/anemone/                    # Ignored external-source snapshots
    ├── normalized/                     # 16 parquet files
    ├── canonical/                      # anchor_events, cross_source_links
    ├── serving/                        # retrieval docs, embeddings, registry
    ├── analysis/                       # 6 pre-analysis outputs
    ├── reliability/                    # 5 reliability outputs
    └── provenance/                     # provenance.jsonl
```

---

## Data

### Raw Input

| Source | Files | Size | Period |
| --- | --- | --- | --- |
| CTD (Onagawa) | 1 TSV | 1.2 MB | Jan 2024 – Mar 2026 |
| Metagenome | 11 TSV/TXT | 34 MB | Apr 2024 – Feb 2026 |
| Satellite SST subset | 1,848 NetCDF | ~51 MB locally | Dec 2025 – Feb 2026 |
| ANEMONE MiFish pilot | 1 bounded source snapshot | Operator-managed | Provider metadata |

### Processed Output

| Dataset | Records |
| --- | --- |
| CTD profiles (standardized) | 10,955 depth points |
| CTD cast summaries | 162 casts |
| Kraken genus abundance | 58,712 (716 genera × 82 samples) |
| MetaEuk genus abundance | 67,240 (820 genera × 82 samples) |
| SST hourly observations | 1,848 points |
| SST daily summaries | 79 days |
| Anchor events | 286 (207 sample + 79 SST) |
| Cross-source links | 496 temporal matches |
| ANEMONE eDNA | 1 unknown sample, 1 assay, 70 detections, 4 internal standards |
| Retrieval documents | 325 (323 legacy + 2 method-separated eDNA) |
| Embeddings | 325 × 768-dim |

### Pre-Analysis

| Output | Content |
| --- | --- |
| CTD monthly trends | 27 monthly aggregates per bay |
| Taxa-env correlations | 100 Spearman pairs, **21 significant** (p<0.05) |
| Diversity indices | 164 samples: Shannon, Simpson, Richness, Evenness |
| Bay comparison | Per-bay CTD aggregates |
| Co-occurrence | 30×30 Jaccard similarity matrix |
| Analysis documents | 5 text summaries for RAG injection |

### Reliability Ensurance

| Output | Result |
| --- | --- |
| SST ↔ CTD validation | 24 paired obs, **100% agreement**, mean ΔT = 0.92°C |
| Gap interpolation | 79 SST days, interpolated surface T, confidence 0.916 |
| Diversity prediction | 37 samples, **1 anomaly** (2024-07-O-s1, −2.3σ) |
| Corroboration scoring | **37 verified**, 20 supported, 150 standalone |
| Reliability documents | 4 text summaries for RAG injection |

### PostgreSQL Scientific Corpus

| Table | Rows | Purpose |
| --- | --- | --- |
| `anchor_event` | 286 | Spatiotemporal linking |
| `ctd_profile` | 10,955 | Depth-resolved measurements |
| `ctd_summary` | 162 | Per-cast statistics |
| `metagenome_sample` | 82 | Sequencing + top taxa |
| `sst_point_observation` | 1,848 | Hourly satellite SST |
| `sst_daily_summary` | 79 | Daily regional SST |
| `retrieval_document` | 325 | Text + embeddings + tsvector |
| `cross_source_link` | 496 | CTD/meta ↔ SST links |
| `provenance_record` | 0 | (tracked via JSONL) |

The eDNA extension adds `external_source_snapshot`, `external_source_file`,
`edna_sample`, `edna_assay`, `edna_detection`, and `edna_internal_standard`.
The deployed pilot contains 1 snapshot, 13 registered source-file records,
1 sample, 1 assay, 70 detections, and 4 standards.

Six external-source/eDNA tables, the corpus-publication table, and the
Alembic-managed identity, invitation, chat, feedback, audit, and rate-limit
tables bring the deployed database to 23 tables at migration head
`20260903_0008`.

---

## Retrieval System

### Hybrid Search

1. **Query** → embedded at 768 dimensions using `gemini-embedding-001` on GCP
   or `nomic-embed-text` locally
2. **Vector search** — pgvector cosine similarity over 325 embeddings
3. **Full-text search** — PostgreSQL tsvector with ts_rank_cd
4. **SQL filters** — bay, source type, time range, and structured eDNA scope
5. **RRF fusion** — merges vector + FTS rankings: `score = w_v/(k+r_v) + w_f/(k+r_f)` where k=60

### Trustworthy Multi-Source Answering

Retrieval can expand the primary top-K result set through anchor-event links so
nearby CTD, metagenome, and satellite SST records are available as corroborating
evidence. The `/retrieve` and `/chat` endpoints return primary `sources`,
separate `linked_sources`, and diagnostics that report expected, retrieved, and
missing source families. The same controls are exposed in the Explore evidence
workbench and Chat settings through `expand_evidence` and
`max_linked_sources`.

### Context Injection

| Context | Trigger keywords | Citations |
| --- | --- | --- |
| **Pre-Analysis** | correlation, diversity, trend, seasonal, ecosystem, ... | `[analysis_*]` |
| **Reliability** | reliable, confidence, validate, anomaly, gap, temperature, SST, CTD, ... | `[reliability_*]` |

Both are toggleable via Chat settings.

### Provenance-Aware Prompting

Every prompt includes:
- System rules enforcing `[doc_id]`, `[analysis_*]`, and `[reliability_*]` citations
- Retrieved evidence with source type, time, and provenance metadata
- Linked cross-source evidence with link type and source anchor
- Pre-analysis context (when keyword-triggered)
- Reliability context (when keyword-triggered)

### Answer Trust Report / Citation Audit

Chat responses can include a deterministic `answer_audit` payload. The audit
resolves every bracket citation against primary sources, linked sources,
analysis context, and reliability context; reports valid and invalid citations;
counts primary, linked, analysis, and reliability citations; and assigns a
`strong`, `caution`, or `weak` trust level.

The audit is context-aware:

- Synthesis questions about trends, correlations, diversity, or ecosystem
  patterns can satisfy source requirements with cited `[analysis_*]` context
  when that context covers the expected source family.
- Reliability and validation questions can satisfy source requirements with
  cited `[reliability_*]` context when the reliability document covers the
  relevant CTD/SST evidence.
- Raw measurement questions still require raw source citations, even if an
  analysis summary mentions the same topic.
- Retrieval gaps are surfaced as warnings unless the answer explicitly
  acknowledges the missing evidence.

---

## Reliability Ensurance

Cross-source validation layer that uses overlapping data to reinforce system confidence.

| Engine | Method | Result |
| --- | --- | --- |
| **SST ↔ CTD** | Compare satellite SST with CTD surface T on matching dates | 24/24 agree, mean ΔT = 0.92°C |
| **Gap Interpolation** | Continuous SST fills temporal gaps between CTD dates | 79 days, confidence 0.916 |
| **Diversity Prediction** | Predict Shannon H' from CTD conditions via known correlations | 1 anomaly: 2024-07-O-s1 (−2.3σ) |
| **Corroboration** | Multi-source agreement scoring per observation | 37 verified / 207 total |

**Reliability tiers**: verified (multi-source) → supported (partial) → standalone (single source)

---

## Key Ecological Findings

### Taxa–Environment Correlations (21/100 significant, p<0.05)

| Genus | Variable | ρ | Direction |
| --- | --- | --- | --- |
| Gyrodinium | temperature | −0.60 | Dinoflagellate declines with warming |
| Oncaea | temperature | +0.59 | Copepod increases with warming |
| Levanderina | salinity | −0.50 | Declines with salinity |
| Seminavis | temperature | −0.52 | Diatom declines with warming |

### Community Diversity (Kraken, 82 samples)

- **Shannon H'**: mean = 3.884, range [0.77, 5.10]
- **Simpson 1-D**: mean = 0.908
- **Richness**: mean = 394 genera, range [52, 671]

### Detected Anomaly

Sample **2024-07-O-s1** (Onagawa Bay, July 2024): Shannon H' = 1.601 vs predicted 3.453 (−2.3σ). Indicates possible bloom event or dominance shift.

---

## Configuration

Key settings in [config.py](config.py):

| Setting | Default |
| --- | --- |
| `DATABASE_URL` | `postgresql://ocean:ocean@localhost:5433/ocean_platform` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` |
| `MODEL_PROVIDER` | `ollama` locally; `vertex` in the GCP service and jobs |
| `EMBEDDING_MODEL` | `nomic-embed-text` (768-dim) |
| `CHAT_MODEL` | `qwen2.5:14b-instruct` |
| `DEPLOYMENT_ENV` | `development`; `staging` and `production` enable fail-closed checks |
| `AUTH_MODE` | `required`; `disabled` is allowed only for isolated local development/tests |
| `AUTH_ALLOWED_PROVIDERS` | `oidc`; comma-separated stable provider IDs accepted by the API |
| `AUTH_URL` | `http://localhost:3000` locally; must be the public HTTPS URL in production |
| `OIDC_PROVIDER_ID` | `oidc`; determines the callback path and durable provider identity |
| `PROVENANCE_READ_MODE` | `build` locally; GCP uses the fail-closed `snapshot` fast path |
| `PROVENANCE_SNAPSHOT_URI` | Local `data/provenance`; GCP uses the private bucket `provenance/` prefix |
| `PROVENANCE_CACHE_TTL_SECONDS` | `60` |
| `ANEMONE_BASE_URL` | `https://db.anemone.bio/dist/MiFish/ANEMONE/` |
| `ANEMONE_MAX_FILES` / `ANEMONE_MAX_BYTES` | `2000` / `536870912`; override downward for bounded pilots |
| `EDNA_ARTIFACT_URI` | Blank locally; approved registered-object prefix in managed storage |
| `EDNA_CACHE_DIR` | Local POSIX staging/cache, never a bucket FUSE mount |
| `SST_CTD_AGREEMENT_THRESHOLD` | 2.0°C (env: `SST_CTD_THRESHOLD`) |
| `DIVERSITY_ANOMALY_SIGMA` | 2.0 (env: `DIVERSITY_ANOMALY_SIGMA`) |

---

## Testing

For the complete local and CI verification commands, see
[docs/TESTING.md](docs/TESTING.md). Planned engineering work remains in
[docs/ROADMAP.md](docs/ROADMAP.md).

### Methodology

The normal pytest run uses **synthetic in-memory data** and does not require
PostgreSQL, Ollama, or real data files. A separately gated PostgreSQL/pgvector
integration test verifies migrations, invite acceptance, metadata persistence,
and audit-event creation against a real database.

**Key design principles:**

- **Fixtures over files** — shared test data is defined in `conftest.py` as pytest fixtures that generate DataFrames and temporary JSONL files on-the-fly
- **Unit isolation** — each test validates a single function or logic path, with external dependencies mocked via `unittest.mock.patch`
- **Edge case coverage** — empty inputs, boundary values, and invalid data are tested alongside normal cases
- **No side effects** — tests use `tmp_path` (pytest built-in) for any file I/O, cleaned up automatically

### Running the Tests

```bash
# Run all backend/unit/API tests
pytest tests/ -v

# Collect without running, useful for quick inventory checks
python -m pytest --collect-only -q

# Run the CI-equivalent coverage boundary
AUTH_MODE=disabled DEPLOYMENT_ENV=test PERSIST_LOCAL_CHAT=false \
pytest tests/ -q --tb=short \
  --cov=api --cov=config --cov=db --cov=preprocessing --cov=ingestion \
  --cov=orchestration --cov=schema --cov=evaluation \
  --cov-report=term-missing --cov-fail-under=70

# Check the Next.js frontend
cd frontend
npm run typecheck
npm run build
```

### Current Test Matrix

The current suite contains more than **640 tests** across unit, API, and
integration modules. The deployed v0.4.0 release gate passed 638 backend tests
with 9 PostgreSQL-gated skips and 77.11% coverage. Post-release validation of
the merged dependency and NLTK-removal maintenance passed 642 tests with 9
skips and 77.15% coverage; those later changes are not yet deployed.

| Test area | Files |
| --- | --- |
| Authentication, authorization, feedback, and security | `test_auth.py`, `test_security_config.py`, `test_rate_limit.py`, `test_chat_feedback.py`, `test_admin_feedback.py` |
| API pages and controls | `test_api_explore.py`, `test_api_pipeline.py`, `test_api_provenance.py`, `test_api_evaluation.py`, `test_api_retrieve.py`, `test_api_schemas.py` |
| Data normalization and provenance | `test_common.py`, `test_provenance.py`, `test_lineage.py`, `test_raw_validation.py`, `test_metagenome_loaders.py`, `test_anchor_events.py` |
| Retrieval, prompting, and answer audit | `test_local_retriever.py`, `test_query_orchestrator.py`, `test_prompt_builder.py`, `test_answer_audit.py` |
| Reliability and evaluation | `test_reliability.py`, `test_evaluation.py`, `test_questions.py`, `test_quality_metrics.py`, `test_report.py`, `test_statistical_analysis.py` |
| Database safety and loading | `test_database_backup.py`, `test_load_db_upsert.py` |
| PostgreSQL integration | `integration/test_app_metadata_postgres.py`, `integration/test_operational_postgres.py` |

Latest verified local result:

```text
642 passed, 9 skipped; 77.15% coverage
```

---

## Design Decisions

1. **Parquet as intermediate format** — columnar storage for fast analytical queries; PostgreSQL for production serving
2. **Anchor events** — spatiotemporal linking layer connecting CTD, metagenome, and SST from the same place/time
3. **Narrative text chunks** — each document is a self-contained paragraph with statistics, not raw CSV rows
4. **Dual retrieval backends** — auto-detects PostgreSQL; falls back to local BM25 + numpy without a database
5. **Pre-analysis injection** — keyword-triggered: only injects for complex ecosystem queries
6. **Reliability ensurance** — modular cross-source validation with SST↔CTD agreement, diversity prediction, and corroboration scoring
7. **Variable-prevalence co-occurrence** — selects genera in 10–90% of samples to avoid trivial co-occurrence
8. **Structured database inspection** — table and column allowlists plus parameterized pagination replace free-form SQL
9. **Port 5433** — avoids conflict with default PostgreSQL on 5432
10. **Modular pipeline** — each stage is independently runnable via CLI scripts
