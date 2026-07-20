# provenance-eco-rag

**Onagawa Source Chat** — a provenance-aware Retrieval-Augmented Generation (RAG) system for marine environmental monitoring in Miyagi Prefecture, Japan.

Transforms fragmented field data — CTD water profiles, metagenome sequencing, and satellite SST — into a citation-grounded question-answering system where every answer traces back to its original source.

---

## Study Sites

| Bay | Code | Coordinates | Data |
| --- | --- | --- | --- |
| Onagawa Bay | O | ~38.44°N, 141.45°E | CTD + Metagenome + SST |
| Ishinomaki Bay | I | ~38.41°N, 141.30°E | CTD + Metagenome |
| Mutsu Bay | M | source metadata | CTD + Metagenome |

---

## Architecture

```mermaid
flowchart TB
    subgraph Sources["Data Sources"]
        CTD["CTD\n1 TSV, 10,955 profiles"]
        META["Metagenome\n11 TSV files"]
        SST["Satellite SST\n1,848 NetCDF"]
    end

    PROV["Provenance Registry\nSHA-256, 1,849 records"]

    subgraph Preprocess["Preprocessing"]
        CTD_PP["CTD Pipeline\nstandardize, summaries"]
        META_PP["Metagenome Pipeline\nKraken, MetaEuk, groups"]
        SST_PP["SST Pipeline\npoint extraction, daily agg"]
    end

    NORM["Normalized Parquets\n16 files"]
    ANCHOR["Anchor Events\n286 anchors, 496 links"]

    subgraph Analysis["Ecological Analysis"]
        PREANA["Pre-Analysis\n5 ecological analyses\n5 RAG documents"]
        RELIAB["Reliability Ensurance\n4 validation outputs\n4 RAG documents"]
    end

    RETDOCS["Retrieval Documents\n323 narrative chunks\n162 CTD + 82 meta + 79 SST"]

    subgraph Storage["PostgreSQL + pgvector"]
        EMB["Vector Embeddings\n323 x 768-dim\nnomic-embed-text"]
        FTS["Full-Text Index\ntsvector + ts_rank_cd"]
        DB["9 Relational Tables\nprofiles, samples, links"]
    end

    RET["Hybrid Retrieval\nVector + FTS + RRF\n+ Analysis + Reliability injection"]
    LLM["LLM\nProvenance-aware prompting\nCitation-grounded answers"]

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
    PREANA -.->|inject| RET
    RELIAB -.->|inject| RET
    RET -->|top-K + context| LLM
```

---

## Technology Stack

| Component | Technology |
| --- | --- |
| Language | Python 3.12 + TypeScript/React |
| Database | PostgreSQL 16 + pgvector (cosine similarity) |
| Container | Podman / Docker |
| LLM | Ollama (local) — qwen2.5:14b-instruct |
| Embeddings | nomic-embed-text (768-dim) |
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
# Install dependencies
pip install -r requirements.txt

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

No `.env` file is required. `DATABASE_URL`, `OLLAMA_BASE_URL`,
`EMBEDDING_MODEL`, and `CHAT_MODEL` can be supplied as optional environment
overrides.

### Data Pipeline

Recommended manual batch entrypoint:

```bash
python scripts/run_pipeline.py --validate-only
python scripts/run_pipeline.py --preflight-only --stages full
python scripts/run_pipeline.py --execute --tag 2026-07-refresh --reset-db --embed
```

`scripts/run_pipeline.py` is dry-run by default. Real execution requires
`--execute`; destructive database reloads also require `--reset-db`. Each run
writes status, logs, and a manifest under `data/pipeline_runs/`.
The `/pipeline` page exposes manual controls, preflight checks, active job
status, per-stage logs, artifact freshness, run history, manifests, and
artifact diffs.

Individual stages remain runnable for focused debugging:

```bash
python scripts/ingest.py                # 1. Ingestion + preprocessing
python scripts/build_retrieval_docs.py  # 2. Anchor events + documents + links
python scripts/run_pre_analysis.py      # 3. Ecological analyses
python scripts/run_reliability.py       # 4. Cross-source reliability validation
python scripts/load_db.py --reset --embed  # 5. Populate DB + embed 323 docs
```

Traceability and incremental-load planning are also manual:

```bash
python scripts/build_provenance_manifest.py --write --run-id 2026-07-refresh
python scripts/load_db.py --upsert --dry-run --limit-keys 25 --json
```

`--upsert --dry-run` is read-only. It compares current artifacts with database
keys through the provenance manifest and reports planned inserts, candidate
updates, stale rows, and embedding refresh candidates. Mutating upserts remain
blocked until row-level lineage and backup/rollback policy are hardened.

### Launch

Terminal 1:

```bash
uvicorn api.main:app --reload --port 8000
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:3000`.

### Containerized with Podman

The compose files are layered so you can choose how much to containerize.

| Command | Starts | LLM behavior |
| --- | --- | --- |
| `podman compose up -d` | PostgreSQL/pgvector only | Uses whatever app you run on your host |
| `podman compose -f docker-compose.yml -f docker-compose.next.yml up -d --build` | PostgreSQL/pgvector + FastAPI + Next.js app | API connects to Ollama running on your host |
| `OLLAMA_BASE_URL=http://ollama:11434 podman compose -f docker-compose.yml -f docker-compose.next.yml -f docker-compose.ollama.yml up -d --build` | PostgreSQL/pgvector + FastAPI + Next.js app + Ollama runtime | API connects to the `ollama` service inside the compose network |
| `podman compose -f docker-compose.yml -f archive/legacy-streamlit/docker-compose.app.yml up -d --build` | PostgreSQL/pgvector + archived Streamlit reference UI | Reference-only parity check against the old UI |

Recommended local macOS setup: containerize the app and database, but keep
Ollama running on the host. That lets Ollama use the normal local runtime path;
Ollama inside a Podman VM on macOS may be CPU-only and slower.

```bash
podman compose -f docker-compose.yml -f docker-compose.next.yml up -d --build
```

Then open:

```text
http://localhost:3000
```

For an intentional archived Streamlit parity check:

```bash
podman compose -f docker-compose.yml -f archive/legacy-streamlit/docker-compose.app.yml up -d --build
```

Then open:

```text
http://localhost:8501
```

Useful commands:

```bash
podman compose -f docker-compose.yml -f docker-compose.next.yml logs -f api
podman compose -f docker-compose.yml -f docker-compose.next.yml logs -f frontend
podman compose -f docker-compose.yml -f docker-compose.next.yml down
podman compose -f docker-compose.yml up -d postgres
```

If you want the LLM runtime containerized too:

```bash
OLLAMA_BASE_URL=http://ollama:11434 podman compose -f docker-compose.yml -f docker-compose.next.yml -f docker-compose.ollama.yml up -d --build
podman exec -it onagawa_ollama ollama pull nomic-embed-text
podman exec -it onagawa_ollama ollama pull qwen2.5:14b-instruct
```

The containers use these defaults:

| Setting | Container Default | Why |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://onagawa:onagawa@postgres:5432/onagawa_rag` | Uses the compose service name and internal PostgreSQL port |
| `OLLAMA_BASE_URL` | `http://host.containers.internal:11434` | Reaches Ollama running on your host from inside Podman |
| `OLLAMA_BASE_URL` with `docker-compose.ollama.yml` | `http://ollama:11434` | Set this in the command or `.env` when using containerized Ollama |
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
| `/data` | Source observations, CTD, taxa, SST, derived analysis, and reliability workbench |
| `/analysis` | Compatibility redirect to `/data?view=analysis` |
| `/database` | Expert database explorer, schema view, and read-only query tools |
| `/pipeline` | Manual batch ingestion and corpus rebuild controls |
| `/provenance` | Traceability manifest, document lineage, embedding treatment, and upsert dry-run |
| `/evaluation` | First-class evaluation suite with background runs and controls |
| `/chat` | Citation-grounded RAG query interface with expert retrieval/model knobs |
| `/evidence` | Compatibility redirect to `/explore?view=evidence` |
| `/system` | API, database, Ollama, artifact, and runtime status |
| `/debug` | Debug payloads and low-level diagnostic properties |

Local development:

```bash
uvicorn api.main:app --reload --port 8000
cd frontend
npm install
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
| **Database** | Table browser, SQL console (read-only), schema inspector, embedding statistics |
| **Stats** | Corpus metrics, sample coverage, provenance tracking |
| **Evaluation** | Benchmark 15 questions × 4 modes, measuring retrieval precision, source coverage, citation accuracy, context utilization, and latency. Exportable CSV results. |

### Sidebar

- **Model**: chat model, temperature, top_p, repeat_penalty, context_window
- **Retrieval**: vector/FTS weights, RRF-k, top-K, pre-analysis toggle, reliability toggle
- **Filters**: source type, bay, date range
- **Status**: backend connection indicator

### Screenshots

![Overview Tab](docs/screenshots/overview_tab.png)
*System Overview with pipeline architecture and live metrics.*

![Data (CTD) Tab](docs/screenshots/data_ctd_tab.png)
*Interactive depth profiles for CTD measurements.*

![Pre-Analysis Tab](docs/screenshots/pre_analysis_tab.png)
*Ecological correlations and diversity indices.*

![Database Explorer Tab](docs/screenshots/database_tab.png)
*Read-only SQL console and table inspector.*

![Stats Tab](docs/screenshots/stats_tab.png)
*Corpus statistics and data coverage.*

---

## Project Structure

```text
provenance-eco-rag/
├── archive/
│   └── legacy-streamlit/               # Archived Streamlit UI and container overlay
├── config.py                           # Paths, DB, models, thresholds
├── Containerfile.api                   # FastAPI backend container image
├── docker-compose.yml                  # PostgreSQL + pgvector service
├── docker-compose.next.yml             # Optional FastAPI + Next.js services
├── docker-compose.ollama.yml           # Optional Ollama service overlay
├── .env.example                        # Local container env defaults
│
├── api/                                # FastAPI API layer for Next.js
├── frontend/                           # Next.js academic UI
│
├── preprocessing/
│   ├── common.py                       # Sample ID parsing, TSV I/O
│   ├── ctd.py                          # CTD load → standardize → summaries
│   ├── metagenome.py                   # Kraken/MetaEuk abundance, QC, groups
│   ├── remote_sensing.py               # NetCDF SST extraction
│   ├── pre_analysis.py                 # Ecological pre-analysis (5 analyses)
│   └── reliability_ensurance.py        # Cross-source validation (4 engines)
│
├── ingestion/
│   ├── provenance.py                   # SHA-256 file registration (JSONL)
│   ├── lineage.py                      # Traceability manifests + upsert dry-run planner
│   └── file_inventory.py              # Directory scanner
│
├── schema/
│   └── anchor_event.py                 # Spatiotemporal linking
│
├── retrieval/
│   ├── document_builder.py             # Raw data → narrative text chunks
│   ├── cross_source_linker.py          # same_sample + time_match links
│   ├── hybrid_retriever.py             # pgvector + FTS + RRF (primary)
│   └── local_retriever.py              # BM25 + numpy fallback
│
├── db/
│   ├── models.py                       # 9 SQLAlchemy ORM tables
│   ├── connection.py                   # Engine, sessions, init_db
│   └── vector_store.py                 # Ollama embedding + cosine search
│
├── orchestration/
│   ├── query_orchestrator.py           # Cross-source evidence expansion
│   └── unified.py                      # Prompt builder + context injection
│
├── evaluation/
│   └── benchmark.py                    # 15 questions, 4 modes, 6 metrics
│
├── scripts/
│   ├── run_pipeline.py                 # Manual batch orchestrator + manifests
│   ├── build_provenance_manifest.py    # Manual traceability manifest writer
│   ├── ingest.py                       # Ingestion pipeline
│   ├── build_retrieval_docs.py         # Documents + links
│   ├── load_db.py                      # Reset load, embeddings, upsert dry-run
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
| Satellite SST | 1,848 NetCDF | ~3.7 GB | Dec 2025 – Feb 2026 |

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
| Retrieval documents | 323 (162 CTD + 82 meta + 79 SST) |
| Cross-source links | 496 temporal matches |
| Embeddings | 323 × 768-dim |

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

### PostgreSQL Database (9 tables)

| Table | Rows | Purpose |
| --- | --- | --- |
| `anchor_event` | 286 | Spatiotemporal linking |
| `ctd_profile` | 10,955 | Depth-resolved measurements |
| `ctd_summary` | 162 | Per-cast statistics |
| `metagenome_sample` | 82 | Sequencing + top taxa |
| `sst_point_observation` | 1,848 | Hourly satellite SST |
| `sst_daily_summary` | 79 | Daily regional SST |
| `retrieval_document` | 323 | Text + embeddings + tsvector |
| `cross_source_link` | 496 | CTD/meta ↔ SST links |
| `provenance_record` | 0 | (tracked via JSONL) |

---

## Retrieval System

### Hybrid Search

1. **Query** → embedded via nomic-embed-text (768-dim)
2. **Vector search** — pgvector cosine similarity over 323 embeddings
3. **Full-text search** — PostgreSQL tsvector with ts_rank_cd
4. **SQL filters** — bay, source_type, time range
5. **RRF fusion** — merges vector + FTS rankings: `score = w_v/(k+r_v) + w_f/(k+r_f)` where k=60

### Context Injection

| Context | Trigger keywords | Citations |
| --- | --- | --- |
| **Pre-Analysis** | correlation, diversity, trend, seasonal, ecosystem, ... | `[analysis_*]` |
| **Reliability** | reliable, confidence, validate, anomaly, gap, temperature, SST, CTD, ... | `[reliability_*]` |

Both are toggleable via sidebar checkboxes.

### Provenance-Aware Prompting

Every prompt includes:
- System rules enforcing `[doc_id]`, `[analysis_*]`, and `[reliability_*]` citations
- Retrieved evidence with source type, time, and provenance metadata
- Pre-analysis context (when keyword-triggered)
- Reliability context (when keyword-triggered)

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
| `DATABASE_URL` | `postgresql://onagawa:onagawa@localhost:5433/onagawa_rag` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` |
| `EMBEDDING_MODEL` | `nomic-embed-text` (768-dim) |
| `CHAT_MODEL` | `qwen2.5:14b-instruct` |
| `SST_CTD_AGREEMENT_THRESHOLD` | 2.0°C (env: `SST_CTD_THRESHOLD`) |
| `DIVERSITY_ANOMALY_SIGMA` | 2.0 (env: `DIVERSITY_ANOMALY_SIGMA`) |

---

## Testing

For planned engineering work, including manual scheduled batch updates,
deployment hardening, and continued cloud UI/backend work, see
[docs/ROADMAP.md](docs/ROADMAP.md).

### Methodology

All tests use **pytest** with **synthetic in-memory data** — no PostgreSQL, Ollama, or real data files required. This ensures reproducibility: anyone can clone the repository and run the full test suite immediately.

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

# Run with coverage report
pytest tests/ -v --cov=preprocessing --cov=ingestion --cov=orchestration --cov=schema --cov=evaluation --cov-report=term-missing

# Check the Next.js frontend
cd frontend
npm run typecheck
npm run build
```

### Current Test Matrix

The current suite collects **254 tests** across 18 test modules:

| Test area | Files |
| --- | --- |
| API pages and controls | `test_api_explore.py`, `test_api_pipeline.py`, `test_api_provenance.py`, `test_api_evaluation.py`, `test_api_retrieve.py`, `test_api_schemas.py` |
| Data normalization and provenance | `test_common.py`, `test_provenance.py`, `test_lineage.py`, `test_anchor_events.py` |
| Retrieval and prompting | `test_local_retriever.py`, `test_prompt_builder.py` |
| Reliability and evaluation | `test_reliability.py`, `test_evaluation.py`, `test_questions.py`, `test_quality_metrics.py`, `test_report.py`, `test_statistical_analysis.py` |

Latest verified local result:

```text
254 passed, 3 scipy RuntimeWarnings
```

The warnings are emitted by SciPy for intentionally degenerate evaluation and
statistical fixtures, and are expected by the test coverage.

---

## Design Decisions

1. **Parquet as intermediate format** — columnar storage for fast analytical queries; PostgreSQL for production serving
2. **Anchor events** — spatiotemporal linking layer connecting CTD, metagenome, and SST from the same place/time
3. **Narrative text chunks** — each document is a self-contained paragraph with statistics, not raw CSV rows
4. **Dual retrieval backends** — auto-detects PostgreSQL; falls back to local BM25 + numpy without a database
5. **Pre-analysis injection** — keyword-triggered: only injects for complex ecosystem queries
6. **Reliability ensurance** — modular cross-source validation with SST↔CTD agreement, diversity prediction, and corroboration scoring
7. **Variable-prevalence co-occurrence** — selects genera in 10–90% of samples to avoid trivial co-occurrence
8. **Read-only SQL console** — blocks destructive queries while allowing analytical exploration
9. **Port 5433** — avoids conflict with default PostgreSQL on 5432
10. **Modular pipeline** — each stage is independently runnable via CLI scripts
