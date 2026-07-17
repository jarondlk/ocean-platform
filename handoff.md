# Handoff Document - Onagawa Source Chat (provenance-eco-rag)

> **Last updated**: 2026-07-17
> **Project path**: `/Users/jaronchai/Documents/GitHub/provenance-eco-rag/`
> **Current status**: Active Next.js + FastAPI application, local-first RAG stack, manual batch ingestion only. Legacy Streamlit UI is archived for reference.

---

## 1. Executive Summary

This repository contains a provenance-aware Retrieval-Augmented Generation
system for marine environmental monitoring in Miyagi Prefecture, Japan. It
combines CTD water profiles, metagenome sequencing outputs, and satellite SST
observations into a citation-grounded question-answering system.

The project has moved from a Streamlit-first research UI to a more cloud-ready
application shape:

- **Frontend**: Next.js academic UI in `frontend/`
- **Backend**: FastAPI service in `api/`
- **Database**: PostgreSQL 16 + pgvector through `docker-compose.yml`
- **LLM runtime**: Ollama, usually host-run locally; optional compose overlay
- **Ingestion**: manual batch-run pipeline scripts, not automatic ingestion
- **Archive**: old Streamlit app and Streamlit container overlay preserved in
  `archive/legacy-streamlit/`

The active development direction is now Next.js + FastAPI. Streamlit should be
used only as historical reference and parity material.

---

## 2. What Changed Recently

### Repository Structure Cleanup

The old root-level Streamlit files were moved into an in-repo archive:

| Old root path | New archive path | Reason |
| --- | --- | --- |
| `app.py` | `archive/legacy-streamlit/app.py` | Previous monolithic Streamlit UI; no longer active root entrypoint |
| `Containerfile` | `archive/legacy-streamlit/Containerfile` | Streamlit-specific container image |
| `docker-compose.app.yml` | `archive/legacy-streamlit/docker-compose.app.yml` | Streamlit-specific compose overlay |

The archived Streamlit app was adjusted so it can still import project modules
from the repository root when intentionally run from the archive path.

### Documentation Updated

- `README.md` now presents Next.js + FastAPI as the normal application path.
- `README.md` keeps Streamlit documentation as an archived parity reference.
- `README.md` testing notes now reflect the current 235-test suite.
- `docs/ROADMAP.md` records the manual batch-ingestion direction and cloud UI
  migration direction.
- `archive/README.md` and `archive/legacy-streamlit/README.md` explain what is
  archived and how to intentionally run it.

### Active Stack Clarified

The active root stack is:

- `Containerfile.api` for FastAPI
- `frontend/Containerfile` for Next.js
- `docker-compose.yml` for PostgreSQL/pgvector
- `docker-compose.next.yml` for FastAPI + Next.js
- `docker-compose.ollama.yml` for optional containerized Ollama

The root no longer contains a Streamlit entrypoint.

### Local Artifacts Cleaned

Ignored local clutter was removed during the final repo health check:

- `.DS_Store`
- `.pytest_cache/`
- `__pycache__/`
- `frontend/tsconfig.tsbuildinfo`

The ignored `onagawa_sst_subset/` directory was intentionally left alone
because it is the local SST raw-data source needed for full regeneration.

---

## 3. Current Technology Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js, React, TypeScript |
| API | FastAPI, Pydantic schemas |
| RAG orchestration | Python modules in `orchestration/` and `retrieval/` |
| Database | PostgreSQL 16 + pgvector |
| Search | pgvector cosine similarity + PostgreSQL full-text search + RRF |
| LLM | Ollama, default `qwen2.5:14b-instruct` |
| Embeddings | Ollama `nomic-embed-text`, 768 dimensions |
| Data processing | pandas, Parquet, xarray, netCDF4, SciPy |
| Containers | Podman/Docker compose overlays |
| Tests | pytest backend/API/unit tests; Next.js typecheck/build |

---

## 4. Directory Map

```text
provenance-eco-rag/
├── api/                              # FastAPI service and endpoint logic
├── archive/
│   └── legacy-streamlit/             # Archived Streamlit app and overlay
├── data/                             # Tracked clean-clone artifacts + ignored generated outputs
├── db/                               # SQLAlchemy models, connection helpers, vector store
├── docs/                             # Roadmap and screenshots
├── evaluation/                       # Benchmark, questions, metrics, reports, statistics
├── frontend/                         # Next.js academic UI
├── ingestion/                        # File inventory and provenance registry
├── orchestration/                    # Prompt construction and RAG context injection
├── preprocessing/                    # CTD, metagenome, SST, pre-analysis, reliability
├── retrieval/                        # Document builder, hybrid retriever, local fallback
├── schema/                           # Anchor-event construction
├── scripts/                          # Manual batch pipeline and evaluation CLIs
├── tests/                            # 235 tests collected locally
├── config.py                         # Paths, model defaults, thresholds
├── Containerfile.api                 # FastAPI container
├── docker-compose.yml                # PostgreSQL/pgvector
├── docker-compose.next.yml           # FastAPI + Next.js overlay
├── docker-compose.ollama.yml         # Optional Ollama overlay
├── README.md                         # Public project guide
└── requirements.txt                  # Python dependency set
```

### Archive Policy

Keep active files in the root/module directories. Move only retired material
that is still useful as reference into `archive/`.

Current archive contents:

- `archive/legacy-streamlit/app.py`
- `archive/legacy-streamlit/Containerfile`
- `archive/legacy-streamlit/docker-compose.app.yml`
- `archive/legacy-streamlit/README.md`

Do not archive generated caches. Delete them locally instead.

---

## 5. Current Application Surface

The current UI is a practical academic interface. Avoid marketing-style pages,
large copy blocks, decorative cards, or flashy layouts. The user persona is an
expert researcher/operator who benefits from dense controls, transparent state,
and reproducible run information.

| Route | Purpose |
| --- | --- |
| `/` | Overview, corpus summary, tab feature map, backend signals |
| `/explore` | Competent data exploration workspace with filters, summaries, charts, and sample detail |
| `/data` | Source-specific CTD, metagenome, and SST browsing |
| `/analysis` | Pre-analysis and reliability output review |
| `/database` | Expert database explorer, schema inspection, read-only SQL/table tools |
| `/pipeline` | Manual batch ingestion and corpus rebuild controls |
| `/evaluation` | First-class evaluation suite with background jobs and detailed controls |
| `/chat` | Citation-grounded RAG chat with expert model/retrieval knobs |
| `/evidence` | Evidence catalog and source browsing |
| `/system` | API, database, Ollama, artifacts, and runtime status |
| `/debug` | Debug payloads and low-level diagnostics |

Visual direction:

- Default white backgrounds
- Academic, practical, compact layouts
- Baby-blue accents:
  - `#56B4E9` for rules, focus, outgoing icons
  - `#dceff8` for quiet dividers
  - `#f3fbff` for code/debug backgrounds
  - `#247fae` for high-contrast blue text
- Expert controls are acceptable when clearly grouped and labeled
- Hover help is preferable to visible explanatory copy for specialized knobs

---

## 6. FastAPI Surface

The main backend file is `api/main.py`. Key endpoint groups:

| Group | Endpoints |
| --- | --- |
| Health/statistics | `GET /health`, `GET /stats`, `GET /models` |
| Pipeline | `GET /pipeline/status`, `POST /pipeline/jobs`, `GET /pipeline/jobs/{job_id}`, `GET /pipeline/jobs/{job_id}/log`, `POST /pipeline/jobs/{job_id}/cancel` |
| Debug | `GET /debug` |
| Data page | `GET /data/catalog`, `GET /data/ctd-profile/{sample_id}`, `GET /data/taxa/{sample_id}`, `GET /data/sst` |
| Evaluation | `GET /evaluation/catalog`, `GET /evaluation/preflight`, `POST /evaluation/runs/standard`, `POST /evaluation/runs/ablation`, `GET /evaluation/jobs/{job_id}`, `POST /evaluation/jobs/{job_id}/cancel`, `GET /evaluation/runs`, `GET /evaluation/runs/{run_id}`, `GET /evaluation/runs/{run_id}/report`, `POST /evaluation/compare` |
| Analysis | `GET /analysis` |
| Database | `GET /database/schema`, `GET /database/table`, `POST /database/query` |
| Explore | `GET /explore/catalog`, `GET /explore/table`, `GET /explore/summary`, `GET /explore/timeseries`, `GET /explore/sample/{sample_id}` |
| Evidence/chat | `GET /documents`, `POST /retrieve`, `POST /chat` |

The database query endpoint is intentionally read-only. Keep mutation blocking
in place, and continue improving SQL identifier handling rather than broadening
permissions.

---

## 7. Data Lifecycle

The system currently supports manual batch ingestion and rebuilds. It does not
yet support automatic watching, scheduled ingestion, or incremental cloud data
sync.

### Current Manual Lifecycle

1. **New source files arrive**
   - CTD TSV files go under `data/raw/ctd/`
   - Metagenome TSV/TXT files go under `data/raw/meta/`
   - SST NetCDF source files are local/ignored under `onagawa_sst_subset/`

2. **Ingestion and normalization**
   - Run `python scripts/ingest.py`
   - Provenance is recorded with SHA-256 hashes
   - Normalized parquet artifacts are written under `data/normalized/`

3. **Anchor events and retrieval documents**
   - Run `python scripts/build_retrieval_docs.py`
   - Cross-source links and anchor events are generated under `data/canonical/`
   - Retrieval documents are emitted under `data/serving/`

4. **Pre-analysis**
   - Run `python scripts/run_pre_analysis.py`
   - Ecological analysis parquet outputs and `analysis_documents.jsonl` are
     generated under `data/analysis/`

5. **Reliability ensurance**
   - Run `python scripts/run_reliability.py`
   - Cross-source validation outputs and `reliability_documents.jsonl` are
     generated under `data/reliability/`

6. **Database load and embeddings**
   - Run `python scripts/load_db.py --reset --embed`
   - PostgreSQL tables are rebuilt
   - Embeddings are generated via Ollama

7. **Application use**
   - Next.js calls FastAPI
   - FastAPI uses PostgreSQL when available
   - Retrieval falls back to local JSONL/BM25/numpy when PostgreSQL is down

### Manual Batch Direction

The planned next data workflow is a single manual batch command, not automatic
ingestion. The intended future command shape is something like:

```bash
python scripts/run_pipeline.py --tag 2026-07-manual-refresh --reset-db --embed
```

That future command should orchestrate existing scripts, record manifests,
capture row-count diffs, persist logs, and surface status in the `/pipeline`
page.

---

## 8. Container and Runtime Modes

### Database Only

```bash
podman compose up -d
```

Starts PostgreSQL/pgvector on host port `5433`.

### Recommended Local App Stack

```bash
podman compose -f docker-compose.yml -f docker-compose.next.yml up -d --build
```

Starts PostgreSQL, FastAPI, and Next.js. FastAPI connects to Ollama on the host
through `http://host.containers.internal:11434`.

### Optional Containerized Ollama

```bash
OLLAMA_BASE_URL=http://ollama:11434 podman compose -f docker-compose.yml -f docker-compose.next.yml -f docker-compose.ollama.yml up -d --build
```

Use this only when the LLM runtime should live inside compose too. On macOS,
host Ollama is usually faster and simpler than Ollama inside the Podman VM.

### Archived Streamlit Parity Check

```bash
podman compose -f docker-compose.yml -f archive/legacy-streamlit/docker-compose.app.yml up -d --build
```

Use this only to compare historical Streamlit behavior with the Next.js UI.

---

## 9. Testing and Verification

Latest local verification before this handoff update:

| Check | Result |
| --- | --- |
| `pytest` | 235 passed, 1 expected SciPy RuntimeWarning |
| `npm run typecheck` | Passed |
| `npm run build` | Passed |
| `git diff --check` | Passed |
| `python -m py_compile archive/legacy-streamlit/app.py` | Passed |

The SciPy warning comes from a deliberately degenerate statistical test case in
`tests/test_statistical_analysis.py`.

Current test modules:

| Area | Files |
| --- | --- |
| API and UI backend contracts | `test_api_explore.py`, `test_api_pipeline.py`, `test_api_evaluation.py`, `test_api_schemas.py` |
| Core data/provenance | `test_common.py`, `test_provenance.py`, `test_anchor_events.py` |
| Retrieval/prompting | `test_local_retriever.py`, `test_prompt_builder.py` |
| Evaluation/reliability | `test_reliability.py`, `test_evaluation.py`, `test_questions.py`, `test_quality_metrics.py`, `test_report.py`, `test_statistical_analysis.py` |

Run before larger commits:

```bash
pytest
cd frontend
npm run typecheck
npm run build
```

For docs-only commits, at minimum run:

```bash
git diff --check
```

---

## 10. Key Files To Understand First

| Priority | File | Why |
| --- | --- | --- |
| 1 | `config.py` | Central paths, model names, thresholds, and DB defaults |
| 2 | `api/main.py` | Active backend surface and orchestration for UI features |
| 3 | `api/schemas.py` | Frontend/backend contracts and expert-control payloads |
| 4 | `frontend/app/*/page.tsx` | Active UI routes |
| 5 | `frontend/components/AppShell.tsx` | Navigation structure and page shell |
| 6 | `orchestration/unified.py` | Prompt builder, retrieval dispatch, context injection |
| 7 | `retrieval/hybrid_retriever.py` | PostgreSQL vector + FTS retrieval |
| 8 | `retrieval/local_retriever.py` | Local fallback retrieval without PostgreSQL |
| 9 | `preprocessing/reliability_ensurance.py` | Cross-source reliability layer |
| 10 | `evaluation/benchmark.py` | System variants and benchmark execution |

---

## 11. What Is Complete

| Area | Status |
| --- | --- |
| Core data pipeline | CTD, metagenome, SST normalization and retrieval-document build path exist |
| Provenance | SHA-256 file registry exists |
| Anchor/cross-source linking | Anchor events and cross-source links exist |
| Retrieval | PostgreSQL hybrid retrieval and local fallback exist |
| Prompting | Provenance-aware citations plus analysis/reliability injection exist |
| Evaluation | Standard/background runs, ablation controls, run browser, reports, comparison |
| Pipeline UI | Manual batch job controls and logs exist |
| Database UI | Schema, table browsing, and read-only query surface exist |
| Data exploration | Explore/data/analysis pages exist for expert browsing |
| System/debug | Status and debug surfaces exist |
| Containerization | Database-only, Next/FastAPI, optional Ollama, and archived Streamlit modes exist |
| Archive | Legacy Streamlit root files are preserved under `archive/legacy-streamlit/` |

---

## 12. Known Limitations

| Limitation | Notes |
| --- | --- |
| Ingestion is manual | No automatic file watcher, scheduler, queue, or cloud object-store sync yet |
| Batch orchestration is split | Existing scripts run separately; unified `run_pipeline.py` is planned |
| Database load is reset-oriented | `scripts/load_db.py --reset --embed` is the reliable path; upsert/migrations are future work |
| Cloud hardening not done | No reverse proxy/TLS guide, backup automation, auth, or production secret strategy yet |
| Ollama is local-first | Host Ollama is preferred on macOS; containerized Ollama is optional and may be slower |
| Streamlit is archived | Do not add new active features to `archive/legacy-streamlit/app.py` |
| Screenshots are historical | `docs/screenshots/` are useful reference images, not necessarily current Next.js UI captures |
| Integration tests are limited | Most tests are synthetic; a temporary PostgreSQL/pgvector integration suite is still needed |
| CI status should be checked | If `.github/workflows/` is absent in a branch, add CI before relying on GitHub checks |

---

## 13. Recommended Next Work Order

### 1. Manual Batch Pipeline Consolidation

Create `scripts/run_pipeline.py` to orchestrate the current manual stages:

1. `scripts/ingest.py`
2. `scripts/build_retrieval_docs.py`
3. `scripts/run_pre_analysis.py`
4. `scripts/run_reliability.py`
5. `scripts/load_db.py --reset --embed`

Add:

- Run tags
- Run manifest JSON
- Stage timing
- Row-count diffs
- Artifact freshness checks
- Failure boundaries and resumability notes
- UI status integration on `/pipeline`

Keep this manual batch-run only for now.

### 2. Pipeline Safety and Database Backups

Before destructive reset loads:

- Add optional `pg_dump` backup command
- Show backup path in `/pipeline`
- Make reset/embed consequences explicit in the UI
- Add a dry-run/preflight mode that checks required artifacts and models

### 3. Evaluation Suite Hardening

Continue treating evaluation as first-class:

- Add LLM-as-judge scoring with a separate judge model
- Store judge prompts, scores, and rationale
- Add report export/download affordances in the UI
- Add regression comparison against a selected baseline run
- Add charts for latency, citation accuracy, faithfulness, and source coverage

### 4. Cloud-Ready App Architecture

Next.js + FastAPI remains the preferred direction. Before server/cloud use:

- Add authentication and authorization
- Add production `.env.example`
- Add reverse proxy/TLS deployment guide
- Keep Ollama private to the app network
- Decide artifact storage: local volume, NAS, S3-compatible object store, or managed bucket
- Add backups for PostgreSQL and important generated artifacts
- Add deployment health checks and log-retention policy

### 5. Database and SQL Improvements

- Add integration tests with temporary PostgreSQL/pgvector
- Consider Alembic if schemas begin changing often
- Add idempotent upsert support keyed by `sample_id`, `doc_id`, `event_id`, and SST timestamps
- Continue tightening read-only SQL validation and identifier quoting

### 6. UI Parity and Expert UX

Use `archive/legacy-streamlit/app.py` only as parity reference. Implement all
new work in Next.js/FastAPI.

Potential parity checks:

- Confirm all old Streamlit data views have Next.js equivalents
- Replace historical screenshots with current Next.js screenshots when stable
- Improve source-citation rendering and evidence inspection from chat
- Add compact export/download controls for tables and evaluation reports
- Add richer pipeline freshness and data lineage indicators

---

## 14. Operational Gotchas

1. PostgreSQL uses host port `5433`, not default `5432`.
2. `DATABASE_URL` differs inside compose vs on the host.
3. `OLLAMA_BASE_URL` is usually `http://localhost:11434` on host and
   `http://host.containers.internal:11434` from app containers.
4. `docker-compose.next.yml` does not start Ollama unless combined with
   `docker-compose.ollama.yml`.
5. `onagawa_sst_subset/` is ignored but needed for full SST regeneration.
6. `data/` includes tracked clean-clone artifacts, while many regenerated
   outputs are ignored by `.gitignore`.
7. Analysis and reliability JSONL files are prompt-injection bridges. If they
   are missing, those contexts silently become empty.
8. Evaluation temperature defaults to deterministic behavior. Raising it can
   make run comparisons noisy.
9. The local retriever fallback keeps the app useful without PostgreSQL, but it
   is not equivalent to pgvector search.
10. Archived Streamlit files should not be edited for new product behavior.

---

## 15. Commit Readiness Checklist

Before committing larger code changes:

```bash
git status --short
git diff --check
pytest
cd frontend
npm run typecheck
npm run build
```

Before committing docs-only changes:

```bash
git status --short
git diff --check
```

Ignored local artifacts that can be deleted, not archived:

- `.DS_Store`
- `.pytest_cache/`
- `__pycache__/`
- `frontend/tsconfig.tsbuildinfo`

Ignored local artifacts that may be intentionally kept:

- `onagawa_sst_subset/`
- optional raw satellite staging directories
