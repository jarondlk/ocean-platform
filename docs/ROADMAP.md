# Improvement Roadmap

This roadmap tracks practical improvements for turning the current research
prototype into a cleaner local/server/cloud system. The near-term goal is not
fully automatic ingestion; it is a reliable **manual scheduled batch update**
workflow that can later become automated.

## Current Baseline

- Data ingestion is manual and batch-oriented.
- `scripts/ingest.py` regenerates normalized Parquet outputs from the expected
  raw CTD, metagenome, and SST inputs.
- Follow-on scripts rebuild retrieval docs, analysis outputs, reliability
  outputs, and the PostgreSQL/pgvector database.
- The app reads previously generated artifacts and/or PostgreSQL. It does not
  watch for new files or run ingestion during user sessions.
- Repeated database loads are safest with `scripts/load_db.py --reset --embed`.
  Read-only upsert planning exists through `scripts/load_db.py --upsert --dry-run`,
  but mutating upsert semantics are not production-ready yet.
- Retrieval/chat can expand primary top-K evidence through anchor-event
  cross-source links and report expected, retrieved, and missing source
  families.
- Chat can return a deterministic answer trust report that audits citations
  against primary evidence, linked evidence, pre-analysis context, and
  reliability context.
- The README screenshot set was refreshed from the live Next.js/FastAPI
  prototype on 2026-07-21.

## Near-Term Priority: Manual Scheduled Batch Updates

Goal: make updates repeatable enough to run manually on a schedule, such as
weekly or monthly, without making ingestion automatic yet.

- [x] Add a single orchestration command, `scripts/run_pipeline.py`,
      that runs the full batch in order:

  ```bash
  python scripts/ingest.py
  python scripts/build_retrieval_docs.py
  python scripts/run_pre_analysis.py
  python scripts/run_reliability.py
  python scripts/load_db.py --reset --embed
  ```

- [x] Add flags to the orchestration command:
  `--skip-sst`, `--no-embed`, `--validate-only`, `--preflight-only`,
  `--execute`, `--reset-db`, and `--tag RUN_NAME`.
- [x] Write timestamped run logs under `data/pipeline_runs/` with command
      status and elapsed time.
- [x] Write a manifest snapshot for each run, including raw file paths,
      row counts, generated artifact paths, database snapshots, and diffs.
- [x] Add a provenance manifest layer that traces raw files, derived artifacts,
      retrieval documents, and embedding treatment.
- [x] Add read-only `--upsert --dry-run` planning before any database mutation
      path exists.
- [x] Add a documented manual schedule, for example:

  ```bash
  # 1. Place updated raw files in data/raw/ and onagawa_sst_subset/
  # 2. Run validation
  python scripts/run_pipeline.py --validate-only

  # 3. Run full scheduled batch
  python scripts/run_pipeline.py --execute --tag 2026-03-update --reset-db --embed
  ```

- [ ] Add a rollback note: keep the previous `data/` artifact snapshot and
      PostgreSQL dump before each scheduled update.

## Data Ingestion Improvements

- [x] Add a manual provenance manifest command:

  ```bash
  python scripts/build_provenance_manifest.py --write --run-id 2026-03-update
  ```

- [ ] Add stricter validation for expected raw columns, date ranges, sample ID
      formats, and duplicate sample IDs before writing outputs.
- [ ] Make `onagawa_sst_subset/` expectations explicit with a generated manifest
      because the raw NetCDF tree is intentionally not tracked in git.
- [ ] Add source-specific input reports:
  CTD rows/casts, metagenome samples/runs/taxa, SST files/days.
- [ ] Add row-count and sample-count diffing between the previous run and the
      new run.
- [ ] Add row-level source hashes for CTD/metagenome TSV records; current
      provenance is file-level plus stable sample/source keys.

## Database Loading Improvements

- [ ] Keep `--reset --embed` as the default reliable scheduled update path.
- [x] Add read-only upsert dry-run planning for keyed tables and retrieval
      document embedding refresh candidates.
- [ ] Add a database backup command before reset, using `pg_dump` or an
      equivalent containerized backup command.
- [ ] Add mutating idempotent upsert support later for tables keyed by
      `sample_id`, `doc_id`, `event_id`, and SST timestamps, using the
      provenance manifest as the safety contract.
- [ ] Add migration tooling, such as Alembic, if schemas begin changing often.
- [ ] Add integration tests against a temporary PostgreSQL/pgvector container.

## Containerization and Deployment

- [x] Archive the legacy Streamlit `Containerfile` and compose overlay under
      `archive/legacy-streamlit/`.
- [x] Add `docker-compose.ollama.yml` for optional containerized Ollama.
- [ ] Add a server deployment guide with reverse proxy/TLS, backups, and
      private-only Ollama networking.
- [ ] Add a production `.env.example` variant for server deployments.
- [ ] Decide where large raw and generated artifacts live on a server:
      local volume, NAS, S3-compatible object storage, or managed bucket.

## Future Cloud UI Replacement

Streamlit remains useful as historical reference material for thesis demos,
screenshots, and parity checks. The cloud-facing implementation direction is
now a conventional web architecture: Next.js frontend plus FastAPI backend.

- [x] Archive the Streamlit UI under `archive/legacy-streamlit/` rather than
      keeping it as the active root entrypoint.
- [x] Extract reusable application behavior behind FastAPI endpoints so the
      frontend calls APIs rather than importing Streamlit-specific functions.
- [x] Prototype a small API layer first: query, retrieve, ask, evidence search,
      dataset status, pipeline run status, and evaluation results.
- [x] Start a Next.js + FastAPI proof of concept.
- [x] Refresh the public README screenshots with current Next.js/FastAPI
      prototype captures.

Candidate directions:

| Option | Fit | Tradeoff |
| --- | --- | --- |
| [Next.js](https://nextjs.org/docs) frontend + [FastAPI](https://fastapi.tiangolo.com/) backend | Best likely cloud-facing architecture; strong for auth, routing, polished UI, streaming chat, and API separation | Requires a TypeScript/React frontend |
| FastAPI + server-rendered templates/HTMX | Simpler than React; keeps most code Python-side | Less rich for complex dashboards and interactive exploration |
| [Dash](https://dash.plotly.com/) | Good for scientific dashboards and Plotly-heavy analytics | Less flexible for polished app/product UX than a custom frontend |
| Keep archived Streamlit runnable | Useful for private parity checks and historical reference | Not the forward path for public cloud UX, auth, multi-user polish, or frontend maintainability |

Evaluation criteria:

- [ ] Authentication and authorization story.
- [ ] Streaming token-by-token chat UX.
- [x] Source-citation rendering, Markdown answer rendering, and answer trust
      report in the Chat interface.
- [ ] Explore evidence panel tables, filters, charts, and downloads.
- [ ] API contract between frontend and RAG backend.
- [ ] Deployment simplicity on one server and on managed cloud.
- [ ] Maintainability for a mostly Python codebase.
- [ ] Ability to show pipeline freshness, database health, model health, and
      evaluation reports clearly.

Current migration direction: **Next.js + FastAPI**, with Streamlit kept only as
an archived reference for remaining parity checks.

## App and RAG Improvements

- [ ] Use `archive/legacy-streamlit/app.py` only to identify remaining parity
      gaps; implement new UI behavior in Next.js and reusable behavior in
      FastAPI/service modules.
- [x] Surface manual pipeline freshness, active/background job state, logs,
      history, and artifact diffs in the UI.
- [x] Surface provenance manifest, document trace, embedding treatment, and
      upsert dry-run planning in the UI.
- [x] Add a health/status page for PostgreSQL, local JSONL fallback, Ollama,
      model availability, and artifact presence.
- [x] Add linked cross-source evidence expansion for retrieval/chat requests.
- [x] Add context-aware answer citation audit and trust report UI.
- [x] Replace historical README screenshots with current prototype screenshots.
- [ ] Add click-through citation chips from answers/trust reports into
      provenance traces and source detail panels.
- [ ] Add clearer warnings when the app is using local BM25 fallback instead of
      PostgreSQL/pgvector.

## Evaluation and Quality

- [ ] Run the full ablation study after each major data update.
- [ ] Add a short scheduled-update QA checklist:
  tests pass, pipeline completes, document counts look plausible, app starts,
  representative questions retrieve expected sources.
- [ ] Add LLM-as-judge scoring only after the baseline scheduled batch workflow
      is stable.

## Later: Incremental or Automatic Ingestion

These are intentionally **not** the immediate plan.

- [ ] Add incremental detection of new/changed raw files from manifests.
- [ ] Add per-source incremental jobs for CTD, metagenome, and SST.
- [ ] Add true database upserts and deletion handling.
- [ ] Add a scheduler, such as cron/systemd timer, GitHub Actions self-hosted
      runner, Airflow, Prefect, or cloud scheduled jobs.
- [ ] Add file-watcher or object-storage event ingestion only if data arrival
      becomes frequent enough to justify it.
