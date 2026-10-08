# Script and deployment entrypoint inventory

Reviewed 2026-10-08 against repository callers, CLI implementations, tests,
templates and operating guidance. No script executes automatically merely
because it is present. Cloud Run serving uses `JOB_EXECUTION_MODE=external`;
batch work remains manual. An operator CLI without an application caller is
not unused code. The tables below cover every tracked entrypoint in `scripts/`,
the GCP shell/build helpers and standalone QA modules.

Current acquisition direction: NASA context is complete; both superseded NOAA
jobs are stopped and preserved, and the follow-up is paused. Use retained bytes
for the published v0.7.4 Miyagi demo. Acquisition commands below are retained
operator tooling, not authorization to restart downloads. See
[accepted operations](../docs/RELEASE_0.7.4_OPERATIONS.md).

## Maintained application and development commands

| Entrypoint | Caller / supported purpose | Effects / default |
| --- | --- | --- |
| `bootstrap_dev.sh` | Root README and dependency guide | Creates local Python environment; installs hashed dev lock. |
| `bootstrap_database.py` | Compose startup and migration job template | Default upgrades migrations/initializes corpus; `--check-only` reads tables, required columns, vector extension and exact migration heads. |
| `ingest.py` | API stage registry and batch runner | Regenerates local normalized/source artifacts; `--validate-only` checks inputs. |
| `build_retrieval_docs.py` | API stage registry and batch runner | Rebuilds local anchors/docs/links; `--help` exits before work. |
| `run_pre_analysis.py` | API stage registry | Regenerates local ecological summaries; `--help` exits before work. |
| `run_reliability.py` | API stage registry | Regenerates local reliability artifacts; `--help` exits before work. |
| `run_pipeline.py` | API controls and pipeline job template | Plans batch stages by default; explicit execution inserts verified backup before database mutation. Raw-validation-only mode runs safe validation unless dry-run requested. |
| `load_db.py` | API stage registry, pipeline and ANEMONE runners/importer | Transactional corpus upsert or explicit reset; database writes require reviewed invocation. Never reset application metadata. |
| `database_backup.py` | API stage registry, pipeline, CI and candidate verification | Explicit create/verify/disposable restore-test; private backup artifacts may include users/history. |
| `build_provenance_manifest.py` | API registry, ANEMONE runner, lineage and QA | Preview by default; explicit local write or immutable publication advances guarded pointer. |
| `update_embeddings.py` | API controls and embedding job template | Normal invocation writes embeddings and may call paid models; use dry-run/probe/limit deliberately. |
| `sync_anemone.py` | ANEMONE runner | Bounded inventory/plan by default; explicit acquisition writes snapshots and contacts provider. |
| `normalize_anemone.py` | ANEMONE runner/catalogue preparation | Validate-only default; explicit execution publishes canonical artifacts. |
| `run_anemone_job.py` | Manual process/sync templates | Offline plan by default; explicit stages acquire/import/materialize/analyze/publish/apply approved classification. |
| `materialize_edna_retrieval.py` | API/batch stages and ANEMONE runner | Dry-run default; execute publishes eDNA retrieval generation. |
| `run_edna_analysis.py` | API stage registry | Recipe validation/preflight by default; execute publishes registered descriptive bundle. |
| `run_evaluation.py` | Evaluation job template | Calls configured retrieval/models and saves reports; bounded cases/modes needed. |
| `run_ablation.py` | API evaluation controls | Runs evaluation variants, calls models and writes reports. |
| `compare_evaluations.py` | README/operator evaluation workflow | Reads saved CSV runs; optional saved comparison report. |
| `export_chat_scope.py` | CI and generated frontend scope contract | Generates contract; `--check` verifies without rewriting. |
| `invite_user.py` | README/deployment bootstrap | Explicit invitation/account administration writes metadata. |
| `hash_mock_password.py` | Local guarded mock-login setup | Interactive scrypt hash generation; local test harness only. |
| `verify_candidate_containers.sh` | Candidate Cloud Build | Creates/removes synthetic Docker containers on `cloudbuild` network; migration, restore, imports, auth/HTTP and runtime-security verification. No production secrets. |
| `verify_runtime_security.sh` | Candidate verifier | Read-only Linux runtime inventory; checks UID, CLI absence, capabilities, privilege bits and mount configuration. |

## Maintained operator-only tools

These are not wired to automatic production jobs. Retain their implementations
and underlying module tests; lack of a UI caller is intentional.

| Entrypoint | Supported purpose / evidence | Effects / limitations |
| --- | --- | --- |
| `build_gcp_seed_manifest.py` | Called by raw-seed upload helper; manifest tests | Offline bounded raw-file inventory; writes manifest only. Initial seed workflow, not historical SST research acquisition. |
| `check_research_readiness.py` | v0.7.0 implementation/readiness contract | Reads retained candidate metadata; writes census; no registry approval. |
| `inventory_historical_sst.py` | #103 all-location/year acquisition census | Explicit production READ ONLY snapshot or verified candidate; writes local inventory only; no account/history reads. |
| `acquire_historical_sst.py` | #103 historical acquisition operator | Preflight and bounded metadata queries; only explicit child-ID `batch --execute` downloads; persistent resume/reconciliation; optional provider-scoped IPv4 with verified TLS; original metadata inspection preserves NRT/final distinction; no cloud publication. |
| `acquire_historical_sst_cloud.py` | #103 capped private raw archive | Dry-run default; explicit execution uses one writer, bounded staging, byte-verified immutable raw/checkpoint resume and terminal reconciliation; 64 GiB raw ceiling. No DB, registry approval, corpus/model calls or serving deployment. |
| `acquire_hybrid_sst.py` | Current #103 hybrid acquisition operator | Dry-run default; coarse daily context and small native multi-day patches have distinct plan/role identities; explicit acquisition keeps 8 MiB/file and 32 GiB raw limits, verified resume, private failure journals and terminal coverage counts. No DB, credentials, scientific approval or Chat publication. The former full-resolution bulk job is superseded and must not auto-resume. |
| `acquire_nasa_sst_context.py` | #103 selected context-first recovery | Dry-run default; bounded daily NASA regional context, 4 GiB cumulative raw cap, immutable generation/byte receipts, CAS lease and verified resume. Interim raw is explicitly separate and ineligible for final-series evidence. Uses a private local token; native patches and scientific publication remain pending. |
| `prepare_historical_sst_context.py` | #103 archive-to-review integration | Offline final-only monthly preflight; explicit execution reads one bounded batch from the existing private archive into an immutable local review package. Verifies durable reconciliation, raw bytes, generation and original provenance. No provider downloads, DB/cloud writes, scientific approval or Chat publication. |
| `preview_historical_sst_context.py` | #103 verified daily context diagnostics | Rechecks a bounded sealed review package against its exact source plan/reconciliation and original receipts; reports daily temperature, uncertainty, ice, mask counts and explicit final-series gaps. Optional rectangle is unreviewed; optional `--proposed-quality` evaluates explicit draft QC/weighting separately, preserving sparse values with warnings and the original diagnostics. Coarse grid-point summaries are not native sample-area SST. Local JSON only; no network, DB, approval, matching or publication. |
| `preview_historical_sst_matching.py` | #103 provisional historical matching | Uses explicit members and hash-bound daily SST rows, or verified context diagnostics with QC rules. Records Japan-midday assumptions, 24-hour coverage, a 48-hour retry only above 20% temporal misses, actual source dates and warnings. Computes region/season-relative thirds from supported SST days independently of fish samples. Local preview only; diagnostic rectangles and occurrence proxies do not establish reviewed coastal areas or physical collections. No provider download, DB or publication. |
| `qualify_nasa_hybrid_sst.py` | #103 authenticated fallback qualification | Dry-run default; selects hybrid child hashes and expands at most 16 NASA one-day subsets. Owned private local bearer file, fixed HTTPS origin, no redirects, sanitized resume journals and independent final-generation/grid/unit validation. No cloud credential storage, bulk acquisition, DB or scientific publication. |
| `compare_historical_sst.py` | #103 product/access comparison | Prepares fixed probes; optional small MUR downloads and private retained Himawari footprint inspection; preserves differing versions/statistics/time offsets; scientific selection stays pending. |
| `probe_himawari_sst.py` | #103 authenticated archive comparison | Dry-run default; explicit execution lists a directory or downloads 1–4 selected files over verified encrypted FTPS. Private credentials, bounded bytes, checksums/atomic generations; no scientific publication or bulk queue. |
| `prepare_anemone_catalogue.py` | v0.5.0 catalogue/import workflow | Reads observed archive; writes staged bounded candidates. |
| `import_anemone_catalogue.py` | Catalogue importer regression/integration tests | Explicit database destination; default merge is rolled back, execute commits. It can still take locks or stage local artifacts. |
| `qa_anemone_catalogue.py` | v0.5.0 full-candidate reconciliation | Isolated candidate/database/serving tree required; reads counts, provenance and hashes; writes QA report. |
| `refresh_anemone_catalogue.py` | v0.5.0 refresh design and `ingestion/anemone_refresh.py` tests | Contacts provider and writes observed archive immediately on invocation; bounded requests/bytes/interval. No deployed schedule. |
| `register_classification_workload.py` | ANEMONE pilot/review runbook and tests | Creates explicit auditable classification workload actor; not web identity impersonation. |
| `prepare_research_sst.py` | v0.7.0 acquisition plan; acquisition tests | Offline plan by default; execute downloads/stages granules. Product approval remains separate. |
| `run_research_sst_panel.py` | v0.7.0 implementation and container import gate | Preflight/build panel from applied sampling/product reviews; execute publishes immutable panel. |
| `run_research_sst_collection.py` | #103 bounded multi-panel research input | Explicit child/area selection; current applied review preflight; execute publishes immutable collection with verified child raw provenance. |
| `prepare_historical_sst_period.py` | Retained #103 context across a fixed period | Default preflight; explicit bounded GCS reads verify monthly sealed bytes, generation, QC and gaps. Local processing only; file lock and exact checkpoints, no provider downloads or scientific publication. |
| `run_research_context_panel.py` | Formal regional-context review bridge | Default preflight; execution requires actually applied sampling/product reviews before immutable panel publication. Does not bypass researcher/admin role gates. |
| `run_provisional_research_demo.py` | Explicitly user-approved provisional regional demo | Default preflight; execution requires current full-source verification and the hash-bound user decision. Publishes only to the separate provisional namespace; no canonical classifications, physical IDs, review/role changes or provider acquisition. |
| `run_research_analysis.py` | Research bundle implementation and image import gate | Preflight default; execute creates approved-registry-bound research bundle. |
| `evaluate_edna_pilot.py` | Saved-record evaluator and ANEMONE runbook | Reads evidence/human review; no model generation; not a substitute for six real research demos. |
| `render_gcp_templates.py` | GCP runbook; renderer tests | Offline YAML rendering; use a private temporary output directory. Bootstrap templates are not fresh production definitions. |
| `retention_cleanup.py` | Security retention guide and tests | Read-only dry-run default; deletion requires execute plus exact confirmation; never run as an audit convenience. |

## Legacy and historical entrypoints

| Entrypoint | Disposition |
| --- | --- |
| `phase7_release_probe.py` | Retained historical v0.1.0 Phase 7 smoke/load tool and tests. Dry-run default; execution requires operator-provided private cookie file and host confirmation. Its query matrix and acceptance do not cover current source settings/research roles. Do not obtain browser session cookies through automation. |
| `evaluation/qa/run_anemone_questions.py` | Retained v0.5.0 local-candidate question matrix. Model phase can be billable; imported metric helper is still used by v0.6.1 acceptance runner. |
| `evaluation/qa/run_v061_acceptance.py` | Retained bounded v0.6.1 question/claim evidence capture. Non-persisting synthetic QA identity is not normal Google live-role acceptance; exact aggregate evidence may be retained. |
| `evaluation/qa/run_chat_system_qa.py` | Historical v0.4.5 read-only PostgreSQL/model probe with ephemeral SQLite history; candidate operator diagnostic, not current release gate. |
| `evaluation/qa/probe_chat_contract.py` | Historical adversarial observation harness with test fixtures. Reports findings for human review; not a security or scientific acceptance certification. |
| `archive/legacy-streamlit/app.py`, container and compose overlay | Explicitly retired application UI; parity/history only. Archive dependency set is separate from production. |

Do not remove migrations, historical QA scripts, old bundle readers or archived
release records merely because current production does not invoke them. They
may support restore, replay, parity or retained evidence.

## GCP entrypoints and reuse boundaries

| Entrypoint | Status / use |
| --- | --- |
| `deploy/gcp/prepare-foundation.sh` | Guarded initial provisioning of APIs/identities/secret containers/bucket/bindings. Not routine patch deployment. |
| `deploy/gcp/create-cloud-sql.sh` | Guarded initial billable provisioning. Default small tier is a bootstrap choice, not the upgraded live tier. Not a scaling/config reconciliation tool. |
| `deploy/gcp/upload-data.sh` | Initial bounded raw-seed helper; dry-run still contacts GCS. Rejects unexpected files. Never use to sync the entire current data bucket or acquire approved research SST. |
| `cloudbuild.yaml` | Maintained combined source tests/audit and two-image build. Does not deploy or perform the full candidate runtime/security gate. |
| `deploy/gcp/cloudbuild-candidate-qa.yaml` | Maintained two-image synthetic runtime/restore/security gate. Full scans collect findings; scan exit zero is not acceptance. Configurable `_QA_REPORT_PREFIX` prevents hard-coded old release paths. |
| `deploy/gcp/cloudbuild-frontend.yaml` | Manual single-image rebuild helper; not referenced by CI/current release gate. Retain for targeted operations, but require combined acceptance before deployment. Default `manual` tag is mutable; resolve exact digest. |
| `service.template.yaml` and five job families | Maintained bootstrap examples (migration, pipeline, embedding, evaluation, ANEMONE process/sync). Actual live jobs have operator-reviewed definitions. ANEMONE sync template exists without a deployed sync job. Patch from fresh live configuration. |
| `*.rendered.yaml` | Ignored generated local output, not authority. Five v0.4.2 renders found during audit were moved outside the deploy directory into private audit storage. Regenerate/review only when needed. |

No tracked script was proven safe to delete. The clearly unused deployment
artifacts were the five stale local renders; the historical probe/QA tools and
single-image build helper are retained with explicit limits. There is no new
automatic acquisition, research approval, retention or ingestion schedule.
