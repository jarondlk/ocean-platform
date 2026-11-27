# Start here — `overhaul` branch

This branch holds two related applications. Read this page first; the long
`README.md` describes the legacy site and is intentionally left unchanged.

| | Legacy site (v0.7.x) | OCEAN v1 beta |
|---|---|---|
| URL | oceaninfobio.com | beta.oceaninfobio.com |
| Branch of record | `main` | `overhaul` |
| Frontend | `frontend/` (Next.js) | `frontend-v1/` (Next.js, EN/JA) |
| API entry | `api/main.py` | `api/v1_host.py` (serving) and `api.v1_beta_question_entry controller` (research controller) |
| Cloud project | legacy project | `ocean-v1-beta-20261101` (Tokyo) |
| Status | live, maintenance only | invite-only beta, being completed |

Both apps share `db/`, `orchestration/`, `schema/`, `ingestion/` and
`config.py`. The legacy `api/main.py` also mounts the v1 routers behind
default-off `ENABLE_V1_*` flags; the beta itself runs `api/v1_host.py`.

## What OCEAN v1 is

A research workspace for Miyagi coastal monitoring data — CTD water profiles,
metagenome summaries, MUR sea-surface temperature and ANEMONE eDNA:

- **Context Catalog** — browse every dataset, analysis and statistic in full.
- **Research** — ask questions; answers cite the exact retained evidence.
- **Workspace** — saved investigations with chosen data, conversations,
  results and (later) approved experiments.

The model only selects verified evidence; the server writes every value. See
[the master plan](docs/plans/ocean-v1/MASTER_PLAN.md) for the design.

## Where things are

- **Current beta state:** [docs/plans/ocean-v1/STATUS.md](docs/plans/ocean-v1/STATUS.md)
- **Remaining work before the beta is usable:** [USABLE_BETA_PLAN.md](docs/plans/ocean-v1/beta/USABLE_BETA_PLAN.md)
- **Full beta completion plan (B0–B5 gates):** [BETA_COMPLETION_PLAN.md](docs/plans/ocean-v1/beta/BETA_COMPLETION_PLAN.md)
- **Planning hub and component contracts:** [docs/plans/ocean-v1/README.md](docs/plans/ocean-v1/README.md)
- **Beta deployment log:** [handoffs/BETA_DEPLOYMENT.md](docs/plans/ocean-v1/handoffs/BETA_DEPLOYMENT.md)
- **Archived component evidence (C01–C27):** [EVIDENCE_ARCHIVE.md](docs/plans/ocean-v1/EVIDENCE_ARCHIVE.md)
- **Legacy docs and release notes:** [docs/README.md](docs/README.md)
- **Cloud access from this Mac:** [AGENTS.md](AGENTS.md) and [deploy/gcp-v1/CLI_AUTOMATION.md](deploy/gcp-v1/CLI_AUTOMATION.md)

## Run and test locally

```bash
.venv/bin/python -m pytest   # full suite; takes 20+ minutes
```

```bash
npm --prefix frontend-v1 test
```

```bash
npm --prefix frontend-v1 run typecheck
```

For a browsable v1 UI backed by the real v1 API and synthetic data, run the
C26 harness: `docs/plans/ocean-v1/evidence/C26/serve_acceptance_qa.py` on port
3101 (with `DEPLOYMENT_ENV=test AUTH_MODE=disabled`, a `/private/tmp` state
file `{"actor":"owner","revision":"r1"}` and a new observations path), then
`npx --prefix frontend-v1 next dev frontend-v1/development/c26 --port 3102`.
`npm --prefix frontend-v1 run preview` shows the older synthetic prototype.

## Rules worth knowing

- Do not rewrite history: receipts cite commit IDs.
- Do not edit files pinned by receipts or the C26 start receipt (for example
  the root `README.md` and the October audit files); check
  [EVIDENCE_ARCHIVE.md](docs/plans/ocean-v1/EVIDENCE_ARCHIVE.md) first.
- The beta CLI identity may build images and update `ocean-v1-beta-serving`
  only. The research controller, queue, Scheduler, SQL, secrets and IAM need
  the operator's own access.
- Each serving deployment gets a receipt under `docs/plans/ocean-v1/beta/` and,
  for frontend-only changes, an entry in `scripts/beta_b1_dispatch.py`.
