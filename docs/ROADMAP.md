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
- Repeated database loads use `scripts/load_db.py --upsert --embed`, with
  logical-key staging, source-row hashes, and one transaction. `--reset` is an
  explicit full-replacement operation.
- Retrieval/chat can expand primary top-K evidence through anchor-event
  cross-source links and report expected, retrieved, and missing source
  families.
- Chat can return a deterministic answer trust report that audits citations
  against primary evidence, linked evidence, pre-analysis context, and
  reliability context.
- The application is invite-only through OIDC, with viewer, researcher, and
  admin permissions enforced by a default-deny FastAPI policy.
- Cloud sign-in uses Google OIDC; the application does not own production
  password storage, recovery, MFA, or lockout.
- Chat interactions and thumbs-up/down feedback are persisted for the user and
  available to administrators through a filtered review/export surface.
- Production-like environments fail closed on unsafe authentication, secret,
  CORS, or local-persistence configuration.
- The bounded GCP prototype is live on Cloud Run with Cloud SQL, Cloud Storage,
  Secret Manager, Cloud Run Jobs, Vertex AI, immutable Provenance snapshots,
  and OCEAN Platform release `v0.2.1`. The active data plane now uses the
  `ocean-*` service, job, identity, database, secret, registry, and bucket
  naming contract; private legacy rollback resources are retained temporarily.
- Operational administration is consolidated under `/admin` with Users,
  Feedback, Pipeline, Database, System, and Debug sections.
- The README screenshot set was refreshed from the authenticated OCEAN
  Platform Cloud Run deployment on 2026-08-25.

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
  python scripts/database_backup.py create
  python scripts/load_db.py --upsert --embed
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
- [x] Move hosted Provenance manifest and trace reads to integrity-verified,
      immutable snapshots published by the manual pipeline.
- [x] Add read-only `--upsert --dry-run` planning.
- [x] Add a documented manual schedule, for example:

  ```bash
  # 1. Place updated raw files in data/raw/ and onagawa_sst_subset/
  # 2. Run validation
  python scripts/run_pipeline.py --validate-only

  # 3. Run full scheduled batch
  python scripts/run_pipeline.py --execute --tag 2026-03-update --embed
  ```

- [x] Add a verified PostgreSQL backup before each database mutation and
      document artifact snapshot/off-host retention responsibilities.

## Data Ingestion Improvements

- [x] Add a manual provenance manifest command:

  ```bash
  python scripts/build_provenance_manifest.py --write --run-id 2026-03-update
  ```

- [x] Add stricter validation for expected raw columns, date ranges, sample ID
      formats, and duplicate sample IDs before writing outputs.
- [x] Make `onagawa_sst_subset/` expectations explicit with a generated manifest
      because the raw NetCDF tree is intentionally not tracked in git.
- [x] Add source-specific input reports:
  CTD rows/casts, metagenome samples/runs/taxa, SST files/days.
- [x] Add row-count and sample-count diffing between the previous run and the
      new run.
- [x] Add row-level source hashes for keyed corpus records.

## Database Loading Improvements

- [x] Make transactional `--upsert --embed` the default scheduled update path
      while retaining stale keys for explicit operator review.
- [x] Add read-only upsert dry-run planning for keyed tables and retrieval
      document embedding refresh candidates.
- [x] Add a database backup command before mutation, using `pg_dump` or an
      equivalent containerized backup command.
- [x] Add mutating idempotent upsert support for tables keyed by `sample_id`,
      `doc_id`, `event_id`, and SST timestamps, using row hashes and a staging
      transaction as the safety contract.
- [x] Add Alembic migrations for application metadata tables.
- [x] Add PostgreSQL/pgvector CI integration tests for migrations, invitation
      acceptance, user persistence, audit events, shared rate limits, repeated
      upserts, and isolated restore checks.

## Containerization and Deployment

- [x] Archive the legacy Streamlit `Containerfile` and compose overlay under
      `archive/legacy-streamlit/`.
- [x] Add `deploy/compose/ollama.yml` for optional containerized Ollama.
- [x] Add a server deployment guide with reverse proxy/TLS, backups, and
      private-only Ollama networking.
- [x] Add a production environment template and private-service Compose
      topology for server deployments.
- [x] Deploy the bounded managed GCP prototype with workload identity, Google
      OIDC, Cloud Run/Jobs, Cloud SQL, Cloud Storage, Secret Manager, Vertex AI,
      budget controls, and tested rollback.
- [ ] Decide where large raw and generated artifacts live on a server:
      local volume, NAS, S3-compatible object storage, or managed bucket.

## Cloud UI Replacement

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

- [x] Invite-only OIDC authentication, verified-email invitation acceptance,
      viewer/researcher/admin authorization, suspension, and audit events.
- [x] Keep local mock credentials isolated while presenting a single neutral
      production sign-in action.
- [x] Select and configure Google OIDC with hosted email/password,
      recovery, MFA, lockout, and abuse protection.
- [ ] Streaming token-by-token chat UX.
- [x] Source-citation rendering, Markdown answer rendering, and answer trust
      report in the Chat interface.
- [x] Explore evidence panel tables, filters, charts, and CSV downloads.
- [x] API contract between frontend and RAG backend, including the authenticated
      Next.js proxy boundary.
- [x] Prove deployment on one managed-cloud prototype with immutable builds,
      bounded jobs, authentication, rollback, and cost ceilings.
- [ ] Automate a reviewed release workflow without weakening manual cost and
      production-approval gates.
- [ ] Maintainability for a mostly Python codebase.
- [x] Ability to show pipeline freshness, database health, model health, and
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

- [x] Provide saved runs, reports, analytics, questions, Standard/Ablation
      controls, comparison, and CSV exports in the Evaluation UI.
- [x] Validate a bounded Vertex Baseline/Full evaluation through the manual
      `ocean-evaluation` Cloud Run Job and reopen its artifacts in the UI.
- [ ] Connect the Evaluation start controls to the external Cloud Run Job with
      a least-privilege execution bridge and server-side workload ceilings.
- [ ] Run the full ablation study after each major data update.
- [ ] Add a short scheduled-update QA checklist:
  tests pass, pipeline completes, document counts look plausible, app starts,
  representative questions retrieve expected sources.
- [x] Add opt-in LLM-as-judge and quality scoring controls while keeping them
      disabled for bounded smoke runs by default.
- [ ] Calibrate judge scoring, define its retention/access policy, and approve
      its cost envelope before making it a routine release gate.

## Later: Incremental or Automatic Ingestion

These are intentionally **not** the immediate plan.

- [ ] Add incremental detection of new/changed raw files from manifests.
- [ ] Add per-source incremental jobs for CTD, metagenome, and SST.
- [ ] Add opt-in, policy-backed deletion handling for stale database keys.
- [ ] Add a scheduler, such as cron/systemd timer, GitHub Actions self-hosted
      runner, Airflow, Prefect, or cloud scheduled jobs.
- [ ] Add file-watcher or object-storage event ingestion only if data arrival
      becomes frequent enough to justify it.
