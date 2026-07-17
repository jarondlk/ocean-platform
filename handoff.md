# Handoff Document — Onagawa Source Chat (provenance-eco-rag)

> **Last updated**: 2026-07-17
> **Project path**: `/Users/jaronchai/Documents/GitHub/provenance-eco-rag/`
> **Status**: Next.js + FastAPI migration active; legacy Streamlit UI archived as reference

---

## 1. What This Project Is

A **provenance-aware Retrieval-Augmented Generation (RAG) system** for marine environmental monitoring in Miyagi Prefecture, Japan. It ingests three heterogeneous data sources — CTD water profiles, metagenome sequencing, and satellite SST — normalizes them, builds narrative retrieval documents, and serves citation-grounded answers through a local LLM.

**Key differentiators from a generic RAG:**
- **Provenance tracking**: every file is registered with SHA-256 hashing before processing
- **Anchor events**: spatiotemporal linking layer that connects observations from the same place/time across different modalities
- **Reliability ensurance**: cross-source validation (SST↔CTD agreement, diversity anomaly detection, corroboration tiers)
- **Context injection**: keyword-triggered injection of pre-computed analyses and reliability assessments into the LLM prompt
- **Ablation Studies**: full 7-variant infrastructure to quantify the impact of multi-modal evidence and reliability pipelines

---

## 2. Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 + TypeScript/React |
| Database | PostgreSQL 16 + pgvector (cosine similarity) |
| Container | Podman / Docker (`Containerfile.api`, `frontend/Containerfile`, layered compose files) |
| LLM | Ollama (local) — `qwen2.5:14b-instruct` |
| Embeddings | `nomic-embed-text` (768-dim) |
| UI | Next.js academic UI + FastAPI API; archived Streamlit reference |
| Search | pgvector cosine + tsvector FTS + Reciprocal Rank Fusion |
| Testing | pytest + Next.js typecheck/build |

---

## 3. Architecture Overview

```
Raw Data → Provenance → Preprocessing → Normalized Parquets
                                            ↓
                              Anchor Events + Cross-Source Links
                                            ↓
                              Retrieval Documents (323 narrative chunks)
                                            ↓
                              PostgreSQL (embeddings + FTS + relational)
                                            ↓
                              Hybrid Retrieval (Vector + FTS + RRF)
                                  + Analysis injection
                                  + Reliability injection
                                            ↓
                              LLM (provenance-aware prompting)
```

---

## 4. Directory Structure

```
source_chat_agt/
├── archive/
│   └── legacy-streamlit/           # Archived Streamlit UI and container overlay
├── config.py                       # All paths, DB URL, model settings, thresholds
├── Containerfile.api               # FastAPI backend image
├── docker-compose.yml              # PostgreSQL + pgvector service
├── docker-compose.next.yml         # Optional FastAPI + Next.js services
├── docker-compose.ollama.yml       # Optional Ollama runtime service overlay
├── .env.example                    # Local container env defaults
├── requirements.txt                # Python deps with minimum version pins
│
├── api/                            # FastAPI API layer
├── frontend/                       # Next.js academic UI
│
├── preprocessing/
│   ├── common.py                   # Sample ID parsing, column canonicalization
│   ├── ctd.py                      # CTD load → standardize → summaries
│   ├── metagenome.py               # Kraken/MetaEuk abundance, QC, groups
│   ├── remote_sensing.py           # NetCDF SST extraction
│   ├── pre_analysis.py             # 5 ecological analyses → JSONL docs
│   └── reliability_ensurance.py    # 4 cross-source validation engines → JSONL docs
│
├── ingestion/
│   ├── provenance.py               # SHA-256 file registration (JSONL)
│   └── file_inventory.py           # Directory scanner
│
├── schema/
│   └── anchor_event.py             # Spatiotemporal linking (sample_id → lat/lon/time)
│
├── retrieval/
│   ├── document_builder.py         # Raw data → narrative text chunks
│   ├── cross_source_linker.py      # same_sample + time_match links
│   ├── hybrid_retriever.py         # pgvector + FTS + RRF (primary backend)
│   └── local_retriever.py          # BM25 + numpy fallback (no DB needed)
│
├── db/
│   ├── models.py                   # 9 SQLAlchemy ORM tables
│   ├── connection.py               # Engine, sessions, init_db
│   └── vector_store.py             # Ollama embedding + cosine search
│
├── orchestration/
│   ├── query_orchestrator.py       # Cross-source evidence expansion
│   └── unified.py                  # Prompt builder + context injection
│
├── evaluation/
│   ├── benchmark.py                # Core benchmark runner & 7 variants
│   ├── questions.py                # 15 questions across 5 categories
│   ├── reference_answers.py        # Expert answers for scoring
│   ├── quality_metrics.py          # Answer scoring metrics
│   ├── statistical_analysis.py     # Significance tests (Friedman/Wilcoxon)
│   ├── visualization.py            # Radar/bar/heatmap generators
│   └── report.py                   # Multi-run evaluation comparison
│
├── scripts/                        # CLI pipeline scripts (run in order)
│   ├── ingest.py                   # 1. Ingestion pipeline
│   ├── build_retrieval_docs.py     # 2. Documents + links
│   ├── load_db.py                  # 3. Populate PostgreSQL + embeddings
│   ├── run_pre_analysis.py         # 4. Pre-analysis pipeline
│   ├── run_reliability.py          # 5. Reliability pipeline
│   ├── run_evaluation.py           # 6. Automated evaluation benchmark (CLI)
│   ├── run_ablation.py             # 7. 7-variant ablation study CLI
│   └── compare_evaluations.py      # Multi-run evaluation comparison
│
├── tests/                          # 208 tests, all synthetic data
│   ├── conftest.py                 # Shared fixtures
│   ├── test_common.py              # 12 tests
│   ├── test_provenance.py          # 7 tests
│   ├── test_anchor_events.py       # 7 tests
│   ├── test_reliability.py         # 16 tests
│   ├── test_prompt_builder.py      # 13 tests
│   ├── test_questions.py           # 20 tests
│   ├── test_quality_metrics.py     # 15 tests
│   ├── test_statistical_analysis.py# 29 tests
│   ├── test_evaluation.py          # 26 tests
│   └── test_report.py              # 18 tests
│
├── data/                           # All gitignored (large files)
│   ├── raw/ctd/                    # CTD_Onagawa.tsv
│   ├── raw/meta/                   # 11 metagenome files
│   ├── normalized/                 # 16 parquet files
│   ├── canonical/                  # anchor_events, cross_source_links
│   ├── serving/                    # retrieval docs, registry
│   ├── analysis/                   # 6 pre-analysis outputs + analysis_documents.jsonl
│   ├── reliability/                # 5 reliability outputs + reliability_documents.jsonl
│   ├── provenance/                 # provenance.jsonl
│   └── evaluation/                 # Timestamped evaluation results (CSV + JSON + report)
│
├── onagawa_sst_subset/             # Satellite NetCDF files (~51MB, gitignored)
└── docs/screenshots/               # 5 UI screenshots for README
```

---

## 5. Key Files to Understand First

| Priority | File | Why |
|---|---|---|
| 1 | `config.py` | All paths, DB URL, model settings, thresholds — everything starts here |
| 2 | `orchestration/unified.py` | The prompt builder — how retrieved docs, analysis, and reliability are assembled into an LLM prompt |
| 3 | `api/main.py` | FastAPI surface for chat, exploration, pipeline, database, and evaluation |
| 4 | `preprocessing/reliability_ensurance.py` | The novel contribution — SST↔CTD agreement, diversity prediction, corroboration |
| 5 | `evaluation/benchmark.py` | The evaluation framework — handles `SystemVariant` execution for ablation |
| 6 | `retrieval/local_retriever.py` | Fallback retriever that works without PostgreSQL |

---

## 6. How to Run

### Prerequisites
- Python 3.12+, Podman/Docker, Ollama

### Setup
```bash
pip install -r requirements.txt
podman compose up -d                      # PostgreSQL + pgvector on port 5433
ollama pull qwen2.5:14b-instruct          # LLM
ollama pull nomic-embed-text              # Embeddings
```

### Pipeline (run in order)
```bash
python scripts/ingest.py                  # Register + normalize raw data
python scripts/build_retrieval_docs.py    # Build 323 narrative documents
python scripts/load_db.py                 # Load into PostgreSQL + embed
python scripts/run_pre_analysis.py        # 5 ecological analyses
python scripts/run_reliability.py         # 4 reliability validations
```

### Application

Terminal 1:

```bash
uvicorn api.main:app --reload --port 8000
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev                               # Opens at localhost:3000
```

### Containerized with Podman
The compose files are intentionally layered:

| Command | Starts | LLM behavior |
|---|---|---|
| `podman compose up -d` | PostgreSQL/pgvector only | Host-run app/CLI can connect to DB on `localhost:5433` |
| `podman compose -f docker-compose.yml -f docker-compose.next.yml up -d --build` | PostgreSQL/pgvector + FastAPI + Next.js app | API connects to host Ollama at `http://host.containers.internal:11434` |
| `OLLAMA_BASE_URL=http://ollama:11434 podman compose -f docker-compose.yml -f docker-compose.next.yml -f docker-compose.ollama.yml up -d --build` | PostgreSQL/pgvector + FastAPI + Next.js app + Ollama runtime | API connects to compose service `http://ollama:11434` |
| `podman compose -f docker-compose.yml -f archive/legacy-streamlit/docker-compose.app.yml up -d --build` | PostgreSQL/pgvector + archived Streamlit reference UI | Reference-only parity check |

For local macOS development, prefer host Ollama plus containerized app/database;
Ollama inside the Podman Linux VM may be CPU-only and slower. If using the
Ollama overlay, pull models into the Ollama container once:

```bash
podman exec -it onagawa_ollama ollama pull nomic-embed-text
podman exec -it onagawa_ollama ollama pull qwen2.5:14b-instruct
```

### Tests
```bash
python -m pytest tests/ -v                # 208 tests, ~2.5s, no DB needed
```

---

## 7. Configuration Reference

All settings in `config.py`, overridable via environment variables:

| Setting | Default | Env Var |
|---|---|---|
| Database URL | `postgresql://onagawa:onagawa@localhost:5433/onagawa_rag` | `DATABASE_URL` |
| Ollama URL | `http://localhost:11434` | `OLLAMA_BASE_URL` |
| Chat model | `qwen2.5:14b-instruct` | `CHAT_MODEL` |
| Embedding model | `nomic-embed-text` | `EMBEDDING_MODEL` |
| Embedding dim | 768 | `EMBEDDING_DIM` |
| SST-CTD threshold | 2.0°C | `SST_CTD_THRESHOLD` |
| Anomaly sigma | 2.0σ | `DIVERSITY_ANOMALY_SIGMA` |

---

## 8. Data Flow Details

### Retrieval Pipeline
1. User query → `orchestration/unified.py:retrieve()` auto-detects PostgreSQL vs local
2. PostgreSQL path: `hybrid_retriever.py` does vector search + FTS + RRF fusion
3. Local path: `local_retriever.py` does BM25 + numpy cosine similarity
4. Results → `unified.py:build_prompt()` assembles evidence block
5. If keywords match → analysis/reliability JSONL docs are injected into prompt
6. Prompt → Ollama streaming API → response with `[doc_id]` citations

### Context Injection Keywords
- **Analysis**: correlation, diversity, trend, seasonal, co-occurrence, community, taxa-environment
- **Reliability**: reliable, reliability, confidence, agreement, validation, cross-source, corroboration, anomaly

---

## 9. Testing Strategy

- All tests use **synthetic in-memory data** — no database, Ollama, or real files needed
- Fixtures in `conftest.py` create DataFrames and temp JSONL files on-the-fly
- External dependencies mocked via `unittest.mock.patch`
- `tmp_path` for file I/O, auto-cleaned

### Test Coverage Focus
| Module | Coverage | Notes |
|---|---|---|
| `ingestion/provenance.py` | High | Core provenance logic fully covered |
| `schema/anchor_event.py` | High | Anchor creation + edge cases |
| `evaluation/` | High | Scoring, variants, statistical models, questions decoupled |
| `orchestration/unified.py` | High | Prompt builder covered; `retrieve()` is integration-level |

---

## 10. Current State & What's Complete

### Fully Working
- [x] 9-layer data pipeline (ingestion → provenance → normalize → anchor → retrieval docs → embeddings → analysis → reliability → RAG)
- [x] Archived 8-tab Streamlit UI for reference/parity checks
- [x] Next.js + FastAPI academic UI migration scaffold and feature expansion
- [x] Evaluation Tab with 4 sub-tabs: Standard, Ablation Study, Compare Runs, Questions Browser
- [x] Full 7-variant ablation study CLI (`scripts/run_ablation.py`) & UI plotting
- [x] 208 unit tests passing
- [x] README with full architecture, testing docs, and project structure
- [x] Automated evaluation CLI (`scripts/run_evaluation.py`) with multi-model support, result persistence, and markdown report generation
- [x] Evaluation comparison CLI (`scripts/compare_evaluations.py`) for cross-run analysis

### Known Limitations
- `archive/legacy-streamlit/app.py` is a retained monolith and should be used only as reference material
- Next.js + FastAPI is now the forward cloud-facing UI/backend split
- SQL table browser uses f-strings for table names (safe because values come from `inspector.get_table_names()`, not user input)
- CI/CD: GitHub Actions runs `pytest` on every push/PR to main (`.github/workflows/tests.yml`)

---

## 11. Potential Next Steps

Detailed planning lives in `docs/ROADMAP.md`. The current ingestion direction
is **manual scheduled batch updates first**, not automatic ingestion yet.

| Area | Task | Difficulty |
|---|---|---|
| **Data** | Add `scripts/run_pipeline.py` for a single manual scheduled batch command | Easy |
| **Data** | Add run manifests, row-count diffs, and timestamped run logs | Medium |
| **Cloud UI** | Expand the Next.js academic UI toward Streamlit feature parity | Medium |
| **Cloud UI** | Continue extracting RAG/backend logic behind FastAPI endpoints | Medium |
| **Evaluation** | Run the full 105-evaluation ablation study: `python scripts/run_ablation.py` | Easy |
| **Evaluation** | Run multi-model comparison: `python scripts/run_evaluation.py --models model1,model2` | Easy |
| **Evaluation** | Add LLM-as-judge scoring (use a second model to rate answer quality) | Medium |
| **UI** | Mine `archive/legacy-streamlit/app.py` for any remaining parity gaps | Medium |
| **Testing** | Add integration tests that run against a test database | Medium |
| **Testing** | Set up GitHub Actions CI to run `pytest` on every push | Easy |
| **Coverage** | Add tests for `preprocessing/pre_analysis.py` and `remote_sensing.py` | Medium |
| **Security** | Parameterize SQL table browser queries with SQLAlchemy `quoted_name` | Easy |
| **Data** | Add more study site data (additional bays, time periods) | Easy |
| **Deployment** | Add production-grade reverse proxy/TLS and backup automation for the containerized stack | Medium |

---

## 12. Gotchas & Things to Know

1. **Port 5433**: PostgreSQL runs on 5433 (not default 5432) to avoid conflicts
2. **Local fallback**: If PostgreSQL is down, the app silently falls back to `local_retriever.py` — no crash, but no vector search
3. **`canonicalize_colname`** in `common.py`: runs `.lower()` before `.replace()`, so case-sensitive replacements (like `"SigmaT"→"sigma_t"`) happen on the lowercased string
4. **Empty DataFrame guard**: `anchor_event.py` line 130 has a guard for empty DataFrames — removing it will cause `KeyError` on `event_id`
5. **Analysis/Reliability JSONL**: These files in `data/analysis/` and `data/reliability/` are the bridge between pre-analysis and the RAG prompt — if they're missing, context injection silently returns empty strings
6. **Evaluation temperature**: The benchmark uses `temperature=0.0` for determinism — changing this will make results non-reproducible
7. **`onagawa_sst_subset/`**: This 51MB directory contains the actual satellite NetCDF files — it's gitignored but must exist locally for the SST pipeline to work
8. **Container modes**: `docker-compose.next.yml` does not start Ollama by itself; it expects host Ollama. Add `docker-compose.ollama.yml` only when you want the LLM runtime containerized too
