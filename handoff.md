# Handoff Document - Onagawa Source Chat (provenance-eco-rag)

> **Last updated**: 2026-07-23
> **Project path**: `/Users/jaronchai/Documents/GitHub/provenance-eco-rag/`
> **Current status**: Active invite-only Next.js + FastAPI application with OIDC, role-based authorization, persistent feedback, and a local-first RAG stack. Manual batch ingestion remains the only update path. Legacy Streamlit UI is archived for reference.

---

## 1. Executive Summary

This repository contains a provenance-aware Retrieval-Augmented Generation
system for marine environmental monitoring in Miyagi Prefecture, Japan. It
combines CTD water profiles, metagenome sequencing outputs, and satellite SST
observations into a citation-grounded question-answering system with
cross-source evidence expansion and deterministic answer citation auditing.

The project has moved from a Streamlit-first research UI to a more cloud-ready
application shape:

- **Frontend**: Next.js academic UI in `frontend/`
- **Backend**: FastAPI service in `api/`
- **Database**: PostgreSQL 16 + pgvector through `docker-compose.yml`
- **LLM runtime**: Ollama, usually host-run locally; optional compose overlay
- **Ingestion**: manual batch-run pipeline scripts, not automatic ingestion
- **Provenance**: manifest-backed lineage inspection plus read-only upsert
  dry-run planning
- **Identity**: invite-only OpenID Connect through Auth.js; viewer, researcher,
  and admin permissions are re-resolved from PostgreSQL on every API request
- **Feedback**: persisted chat interactions, thumbs-up/down reasons/comments,
  and an audited admin review/export workbench
- **Production boundary**: fail-closed configuration, private API/database
  topology, rate limits, security headers, and CI security checks
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
- `README.md` documents linked cross-source evidence, answer trust reports,
  invite-only authorization, feedback review, production safeguards, and the
  current 330+ test suite.
- `README.md` now includes a 2026-07-23 current prototype status section and
  fresh screenshots captured from the live Next.js/FastAPI prototype.
- `docs/ROADMAP.md` records the manual batch-ingestion direction and cloud UI
  migration direction, including completed citation rendering, linked evidence,
  trust report, and screenshot refresh work.
- `docs/SECURITY.md`, `docs/DEPLOYMENT.md`, and `docs/TESTING.md` define the
  authorization model, supported production topology, residual risks, and
  release verification.
- `archive/README.md` and `archive/legacy-streamlit/README.md` explain what is
  archived, how to intentionally run it, and where the active prototype docs
  live.

### Manual Pipeline Improvement

- Added `scripts/run_pipeline.py` as the safe manual batch orchestrator.
- Added pipeline preflight API support.
- Added durable pipeline manifests at `data/pipeline_runs/{run_id}/manifest.json`.
- Added run history/detail APIs for pipeline runs.
- Expanded the `/pipeline` page with preflight checks, active/background job
  status, artifact freshness, per-stage logs, run history, selected manifest
  JSON, artifact diffs, and log-tail inspection.
- Added tests for preflight command planning, reset blockers, dry-run manifest
  creation, active job discovery, artifact freshness, stage-log parsing, run
  history, and run detail retrieval.

### Repository Audit and Mutsu Correction

- Corrected bay code `M` to **Mutsu Bay** across active UI labels, retrieval
  naming, prompt context, preprocessing text documents, evaluation fixtures,
  README study-site documentation, and tests.
- Removed the old hardcoded `M` coordinate fallback from active retrieval and
  anchor-event generation. `M` coordinates should come from source metadata
  until a trusted Mutsu coordinate policy is added.
- Regenerated `data/serving/retrieval_documents.jsonl`,
  `data/serving/retrieval_documents.parquet`, and
  `data/canonical/anchor_events.parquet` from the corrected code.
- Reloaded the local PostgreSQL database with `python scripts/load_db.py --reset --embed`
  so the live `/database`, `/chat`, and retrieval surfaces no longer show stale
  generated bay-label text.
- Audited all active routes in the browser at `http://127.0.0.1:3002`: `/`,
  `/explore`, `/data`, `/database`, `/pipeline`, `/provenance`, `/evaluation`,
  `/chat`, `/system`, `/debug`, plus `/analysis` and `/evidence` compatibility
  redirects. No fatal render text or top-level layout overflow was found.
- Audited major internal expert views: Data observations/CTD/taxa/SST/derived
  analysis/reliability; Pipeline status/run/logs/history; Provenance
  manifest/document trace/upsert dry-run; Evaluation
  runs/analytics/questions/standard/ablation/compare.
- Active-path sweeps are clean for old or misspelled M-bay labels; remaining old
  labels are only in historical generated evaluation CSVs and archived
  Streamlit reference files.

### Provenance Manifest and Upsert Dry-Run

- Added `ingestion/lineage.py` as the traceability-first manifest layer.
- Added `scripts/build_provenance_manifest.py` for manual manifest inspection
  and optional manifest writing under `data/provenance/`.
- Added read-only `scripts/load_db.py --upsert --dry-run --limit-keys N --json` support.
- Added FastAPI endpoints:
  - `GET /provenance/manifest`
  - `GET /provenance/trace/{doc_id}`
  - `GET /provenance/upsert-dry-run`
- Added a Next.js `/provenance` page with manifest tables, document trace
  lookup, embedding treatment, raw trace payload inspection, and manual dry-run
  controls.
- Added synthetic tests for lineage construction, content-hash comparison,
  embedding-refresh planning, and provenance API contracts.

Important boundary: mutating upserts are still intentionally blocked. The
current implementation plans and explains what would change; it does not write
incremental updates into PostgreSQL.

### Data and Analysis UI Consolidation

- Removed `Analysis` from the top-level sidebar.
- Combined source observations, CTD, taxa, SST, derived analysis, and
  reliability review under `/data`.
- Replaced `/analysis` with a compatibility redirect to `/data?view=analysis`.
- Extracted the former analysis page into `frontend/components/AnalysisWorkbench.tsx`
  so derived-analysis and reliability views can be embedded without duplicating
  chart/table logic.

### Explore and Evidence UI Consolidation

- Removed `Evidence` from the top-level sidebar.
- Combined normalized table exploration, time-series review, sample detail, and
  evidence retrieval under `/explore`.
- Replaced `/evidence` with a compatibility redirect to `/explore?view=evidence`.
- Extracted the former evidence page into `frontend/components/EvidenceWorkbench.tsx`
  so the retrieval diagnostics can live inside the corpus workbench without a
  second page implementation.

### Trustworthy Multi-Source Answering and Citation Audit

- Added linked evidence expansion for retrieval/chat requests through
  `expand_evidence` and `max_linked_sources`.
- Retrieval now returns primary `sources`, separate `linked_sources`, and
  diagnostics for expected, retrieved, and missing source families.
- Chat prompts include a linked cross-source evidence section when corroborating
  anchor-event neighbors are available.
- Added deterministic answer auditing in `orchestration/answer_audit.py`.
- Chat responses can include `answer_audit` with trust level, trust score,
  citation resolution records, invalid citation warnings, source-family
  requirements, linked-source use, and analysis/reliability context use.
- Citation requirements are context-aware: cited `[analysis_*]` documents can
  satisfy trend/correlation/diversity requirements, cited `[reliability_*]`
  documents can satisfy validation/trust requirements, and raw measurement
  questions still require raw source citations.
- Added Chat settings for linked evidence expansion and the trust-report toggle.
- Added a clean expert-facing Trust Report panel with summary metrics, warning
  table, requirement table, and citation-resolution table.
- Added `frontend/components/MarkdownAnswer.tsx` so answer text renders
  headings, lists, code blocks, tables, links, emphasis, and citation chips
  without using unsafe HTML injection.

### Invite-Only Authorization and Feedback

- Added Auth.js OpenID Connect login with verified-email invitation acceptance;
  there is no public registration or local password store.
- Added viewer, researcher, and admin roles. Research, commercial, and internal
  are account-type metadata, not permission-bearing roles.
- Added default-deny FastAPI route policies, current-role/status resolution on
  every request, immediate suspension, and self-demotion/self-suspension
  protection for administrators.
- Added persistent chat interactions and thumbs-up/down feedback with reason
  codes and optional comments.
- Added administrator user/invitation management plus a filtered feedback
  review and CSV export surface. Security-sensitive changes write audit events.
- Added fail-closed production configuration, bounded short-lived internal
  tokens, request/body limits, read-only SQL defense in depth, response security
  headers, and per-user production rate limits.
- Added Alembic-backed metadata integration testing, coverage enforcement,
  pinned CI actions, Dependabot configuration, a production Compose topology,
  and security/deployment/testing runbooks.

### Prototype Screenshot Refresh

- Replaced historical Streamlit-era README screenshots with live Next.js/FastAPI
  prototype captures from 2026-07-21.
- Current screenshot files under `docs/screenshots/`:
  `prototype_overview.png`, `prototype_explore_evidence.png`,
  `prototype_data_analysis.png`, `prototype_provenance.png`, and
  `prototype_chat_trust_report.png`.
- The Chat screenshot was captured after a real local-model query and shows the
  Answer Trust Report with context-aware citation requirements.

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
├── docs/                             # Security, deployment, testing, roadmap, screenshots
├── evaluation/                       # Benchmark, questions, metrics, reports, statistics
├── frontend/                         # Next.js academic UI
├── ingestion/                        # File inventory, provenance registry, lineage manifests
├── orchestration/                    # Prompt construction and RAG context injection
├── preprocessing/                    # CTD, metagenome, SST, pre-analysis, reliability
├── retrieval/                        # Document builder, hybrid retriever, local fallback
├── schema/                           # Anchor-event construction
├── scripts/                          # Manual batch pipeline and evaluation CLIs
├── tests/                            # 330+ unit, API, and integration tests
├── config.py                         # Paths, model defaults, thresholds
├── Containerfile.api                 # FastAPI container
├── docker-compose.yml                # PostgreSQL/pgvector
├── docker-compose.next.yml           # FastAPI + Next.js overlay
├── docker-compose.ollama.yml         # Optional Ollama overlay
├── docker-compose.production.yml     # Private-service production topology
├── .env.production.example           # Production environment template
├── README.md                         # Public project guide
├── requirements.txt                  # Python runtime dependency set
└── requirements-dev.txt              # CI/development verification tools
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
| `/explore` | Corpus workbench for tables, filters, summaries, charts, sample detail, and evidence retrieval |
| `/data` | Combined domain workbench for observations, CTD, taxa, SST, derived analysis, and reliability |
| `/analysis` | Compatibility redirect to `/data?view=analysis` |
| `/database` | Expert database explorer, schema inspection, read-only SQL/table tools |
| `/pipeline` | Manual batch ingestion and corpus rebuild controls |
| `/provenance` | Traceability manifest, document lineage, embedding treatment, upsert dry-run |
| `/evaluation` | First-class evaluation suite with background jobs and detailed controls |
| `/chat` | Citation-grounded RAG chat with expert retrieval/model knobs, linked evidence, Markdown answer rendering, and answer trust reports |
| `/evidence` | Compatibility redirect to `/explore?view=evidence` |
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
| Pipeline | `GET /pipeline/status`, `POST /pipeline/preflight`, `POST /pipeline/jobs`, `GET /pipeline/jobs/{job_id}`, `GET /pipeline/jobs/{job_id}/log`, `POST /pipeline/jobs/{job_id}/cancel`, `GET /pipeline/runs`, `GET /pipeline/runs/{run_id}` |
| Provenance | `GET /provenance/manifest`, `GET /provenance/trace/{doc_id}`, `GET /provenance/upsert-dry-run` |
| Debug | `GET /debug` |
| Data page | `GET /data/catalog`, `GET /data/ctd-profile/{sample_id}`, `GET /data/taxa/{sample_id}`, `GET /data/sst` |
| Evaluation | `GET /evaluation/catalog`, `GET /evaluation/preflight`, `POST /evaluation/runs/standard`, `POST /evaluation/runs/ablation`, `GET /evaluation/jobs/{job_id}`, `POST /evaluation/jobs/{job_id}/cancel`, `GET /evaluation/runs`, `GET /evaluation/runs/{run_id}`, `GET /evaluation/runs/{run_id}/report`, `POST /evaluation/compare` |
| Analysis | `GET /analysis` |
| Database | `GET /database/schema`, `GET /database/table` |
| Explore | `GET /explore/catalog`, `GET /explore/table`, `GET /explore/summary`, `GET /explore/timeseries`, `GET /explore/sample/{sample_id}` |
| Evidence/chat | `GET /documents`, `POST /retrieve`, `POST /chat` |

`POST /retrieve` and `POST /chat` accept `expand_evidence` and
`max_linked_sources`. `POST /chat` also accepts `run_answer_audit` and returns
`linked_sources`, `retrieval_diagnostics`, and optional `answer_audit`.

Database access is intentionally GET-only through validated schema and table
inspection endpoints. Free-form SQL execution and its permission were removed;
add future analytical reports as server-defined, structured endpoints.

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

7. **Traceability and dry-run planning**
   - Run `python scripts/build_provenance_manifest.py --write --run-id <run_id>`
   - Optionally run `python scripts/load_db.py --upsert --dry-run --limit-keys 25 --json`
   - Inspect `/provenance` for source hashes, artifact versions, document
     trace paths, embedding treatment, and upsert planning

8. **Application use**
   - Next.js calls FastAPI
   - FastAPI uses PostgreSQL when available
   - Retrieval falls back to local JSONL/BM25/numpy when PostgreSQL is down

### Manual Batch Runner

The data workflow now has a single manual batch command. It is still not
automatic ingestion: no watcher, scheduler, queue, or cloud sync starts this
without an explicit operator action.

```bash
python scripts/run_pipeline.py --validate-only
python scripts/run_pipeline.py --preflight-only --stages full
python scripts/run_pipeline.py --execute --tag 2026-07-manual-refresh --reset-db --embed
```

`scripts/run_pipeline.py` is dry-run by default. Real execution requires
`--execute`; destructive database loads require `--reset-db`. Runs write
`progress.json`, `run.log`, `run_meta.json`, and `manifest.json` under
`data/pipeline_runs/{run_id}/`.

The `/pipeline` page can start background jobs, run preflight checks, inspect
active/background job status, show per-stage logs, list run history, inspect
manifests, report artifact freshness, and display artifact diffs.

### Provenance and Incremental-Load Planning

The provenance layer is intentionally inspectable before it becomes mutating:

```bash
python scripts/build_provenance_manifest.py --limit-documents 500
python scripts/build_provenance_manifest.py --write --run-id 2026-07-lineage-check
python scripts/load_db.py --upsert --dry-run --limit-keys 25 --json
```

The manifest currently records:

- Raw file existence, SHA-256, collection fingerprints, registry counts, and
  latest processing run where available
- Derived artifact paths, producer stage, table mapping, key columns, row
  counts, schema hashes, and file hashes
- Retrieval document IDs, source type, source keys, content hashes, metadata
  hashes, and inferred source artifacts/files
- Embedding treatment for the manifest document window, including model,
  dimension, database status, and refresh candidates

The upsert dry-run compares current artifacts against PostgreSQL keys and
reports planned inserts, candidate updates, stale existing keys, and
retrieval-document embedding refresh candidates. It is read-only and should
remain so until row-level lineage, backup/rollback, and integration testing are
implemented.

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

Latest local verification for this audit:

| Check | Result |
| --- | --- |
| `pytest` | 337 passed, 1 gated integration test skipped, 3 expected SciPy RuntimeWarnings |
| Coverage boundary | 65% aggregate; required floor is 60% |
| PostgreSQL metadata integration | Passed against migrated local PostgreSQL/pgvector |
| Security-boundary Ruff check | Passed |
| `npm run typecheck` | Passed |
| Production-configured `npm run build` | Passed |
| Production Compose expansion | Passed |
| `git diff --check` | Passed |

The SciPy warnings come from deliberately degenerate evaluation/statistical
fixtures and are expected by the test coverage.

Current test modules:

| Area | Files |
| --- | --- |
| Authorization, feedback, and security | `test_auth.py`, `test_security_config.py`, `test_rate_limit.py`, `test_chat_feedback.py`, `test_admin_feedback.py` |
| API and UI backend contracts | `test_api_explore.py`, `test_api_pipeline.py`, `test_api_provenance.py`, `test_api_evaluation.py`, `test_api_retrieve.py`, `test_api_schemas.py` |
| Core data/provenance | `test_common.py`, `test_provenance.py`, `test_lineage.py`, `test_anchor_events.py` |
| Retrieval/prompting/audit | `test_local_retriever.py`, `test_prompt_builder.py`, `test_answer_audit.py` |
| Evaluation/reliability | `test_reliability.py`, `test_evaluation.py`, `test_questions.py`, `test_quality_metrics.py`, `test_report.py`, `test_statistical_analysis.py` |
| PostgreSQL metadata integration | `integration/test_app_metadata_postgres.py` |

Use the CI-equivalent commands in `docs/TESTING.md` before larger commits.
At minimum:

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
| 1 | `config.py` | Central paths, model defaults, and fail-closed API configuration |
| 2 | `api/auth.py` | Identity resolution, permission matrix, default-deny authorization |
| 3 | `frontend/auth.ts` | OIDC provider, invite acceptance, session enrichment |
| 4 | `api/main.py` | Active backend surface and middleware registration |
| 5 | `api/schemas.py` | Frontend/backend contracts and bounded payloads |
| 6 | `frontend/app/*/page.tsx` | Active UI routes |
| 7 | `frontend/components/AppShell.tsx` | Permission-aware navigation and page shell |
| 8 | `orchestration/unified.py` | Prompt builder, retrieval dispatch, linked evidence, context injection |
| 9 | `orchestration/answer_audit.py` | Citation resolution, trust scoring, and context-aware requirements |
| 10 | `retrieval/hybrid_retriever.py` | PostgreSQL vector + FTS retrieval |
| 11 | `retrieval/local_retriever.py` | Local fallback retrieval without PostgreSQL |
| 12 | `docs/SECURITY.md` | Authorization matrix, trust boundaries, limitations, release checklist |

---

## 11. What Is Complete

| Area | Status |
| --- | --- |
| Core data pipeline | CTD, metagenome, SST normalization and retrieval-document build path exist |
| Provenance | SHA-256 file registry, traceability manifest, document trace API/UI, and read-only upsert dry-run exist |
| Anchor/cross-source linking | Anchor events and cross-source links exist |
| Retrieval | PostgreSQL hybrid retrieval and local fallback exist |
| Trustworthy multi-source answering | Primary retrieval, linked cross-source evidence expansion, source-family diagnostics, and chat/evidence controls exist |
| Prompting | Provenance-aware citations plus linked evidence and analysis/reliability injection exist |
| Answer trust report | Deterministic citation audit, context-aware citation requirements, warnings, exportable tables, and Chat UI toggle exist |
| Evaluation | Standard/background runs, ablation controls, run browser, reports, comparison |
| Pipeline UI | Manual batch job controls, preflight checks, active/background job status, artifact freshness, per-stage logs, run history, manifests, and artifact diffs exist |
| Database UI | Schema, table browsing, and read-only query surface exist |
| Data exploration | Combined Explore corpus workbench plus combined Data domain workbench exist for expert browsing |
| System/debug | Status and debug surfaces exist |
| Invite-only identity | OIDC, invitations, viewer/researcher/admin roles, suspension, and audit events exist |
| User feedback | Persisted chat interactions, feedback revisions, admin review/filter/export exist |
| Security boundary | Fail-closed production config, default-deny authorization, bounded tokens/input, rate limits, headers, and SQL defense in depth exist |
| CI and integration | Coverage enforcement, security lint, pinned actions, dependency monitoring config, and PostgreSQL metadata integration exist |
| Containerization | Database-only, Next/FastAPI, optional Ollama, production private-service, and archived Streamlit modes exist |
| Archive | Legacy Streamlit root files are preserved under `archive/legacy-streamlit/` |

---

## 12. Known Limitations

| Limitation | Notes |
| --- | --- |
| Ingestion is manual | No automatic file watcher, scheduler, queue, or cloud object-store sync yet |
| Pipeline backup/rollback | Unified `run_pipeline.py` exists, but database backup and rollback automation are still future work |
| Database load is reset-oriented | `scripts/load_db.py --reset --embed` is the reliable corpus mutation path; `--upsert --dry-run` exists, but mutating corpus upserts remain future work |
| Production operations remain operator-managed | The topology, TLS, secret, backup, and rollback requirements are documented, but backup/restore and log-retention automation are not implemented |
| Ollama is local-first | Host Ollama is preferred on macOS; containerized Ollama is optional and may be slower |
| Streamlit is archived | Do not add new active features to `archive/legacy-streamlit/app.py` |
| Screenshots are point-in-time | `docs/screenshots/` contains current prototype captures from 2026-07-21; refresh them after major UI changes |
| Trust report is deterministic | The current audit checks supplied evidence and citations; it is not an LLM-as-judge semantic faithfulness scorer |
| Integration scope is focused | PostgreSQL migrations/invites/audits are integration-tested; most RAG and scientific tests remain synthetic |
| CSP is report-only | Review violations before changing it to enforcement mode |
| Rate limiting is single-process | Replace the in-memory limiter before adding API workers or hosts |
| Security operations require repository settings | Enable protected required checks, Dependabot alerts/security updates, CodeQL, and secret scanning where available |

---

## 13. Recommended Next Work Order

### 1. Pipeline Safety and Database Backups

Before destructive reset loads:

- Add optional `pg_dump` backup command
- Show backup path in `/pipeline`
- Make reset/embed consequences explicit in the UI
- Extend preflight with backup-path, free-space, and restore-readiness checks

### 2. Evaluation Suite Hardening

Continue treating evaluation as first-class:

- Add LLM-as-judge scoring with a separate judge model
- Store judge prompts, scores, and rationale
- Add report export/download affordances in the UI
- Add regression comparison against a selected baseline run
- Add charts for latency, citation accuracy, faithfulness, and source coverage

### 3. Production Operations and Security Follow-Through

The supported single-host topology and authorization boundary now exist.
Before real users or multiple workers:

- Enable protected CI, Dependabot security updates, CodeQL, and secret scanning
- Complete the manual release checklist in `docs/SECURITY.md`
- Deploy and test the TLS reverse proxy while keeping API, PostgreSQL, and
  Ollama private
- Automate and restore-test backups for PostgreSQL and important artifacts
- Decide artifact storage: local volume, NAS, S3-compatible object store, or
  managed bucket
- Add deployment health checks, log retention, and incident contacts
- Move rate limits to a shared store or gateway before horizontal scaling
- Review CSP reports and switch to enforcement after compatibility validation

### 4. Database and SQL Improvements

- Expand PostgreSQL integration coverage beyond metadata/invitation flows
- Keep Alembic migrations additive and rollback-reviewed
- Extend the provenance manifest with row-level hashes and embedding run IDs
- Add mutating idempotent upsert support keyed by `sample_id`, `doc_id`,
  `event_id`, and SST timestamps after backup/rollback policy is in place
- Continue tightening read-only SQL validation and identifier quoting

### 5. UI Parity and Expert UX

Use `archive/legacy-streamlit/app.py` only as parity reference. Implement all
new work in Next.js/FastAPI.

Potential parity checks:

- Confirm all old Streamlit data views have Next.js equivalents
- Add click-through citation chips from answers/trust reports into provenance
  traces and source detail panels
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
