# v0.5.0 release and deployment record

Started 2026-09-27 JST. The user requested a one-time **GitHub-first release**, followed by manual GCP deployment when authentication permits. No GitHub deployment workflow or workload federation is being reinstated.

## GitHub preparation

Source branch: `gcp-dev`; target: protected `main`. API/frontend versions are 0.5.0. CI now explicitly runs the catalogue and exact-aggregate PostgreSQL suites, alongside the existing integration suites, on PostgreSQL 16/pgvector.

Commit, PR, CI and release identifiers will be added once confirmed. Release notes explicitly identify **GCP deployment pending**.

Local checks on 2026-09-27:

- Ruff and diff whitespace checks passed.
- All 40 frontend tests, typecheck and production build passed.
- Python dependency consistency passed; Alembic has one head, `20260925_0013`.
- Backend regression: **862 passed, 29 environment-gated skips**, with **79.13% coverage**, above the 70% gate. Dedicated CI exercises the PostgreSQL-gated suites.
- The first sandboxed backend attempt could not bind loopback HTTP fixture servers. It is not counted as a successful regression run; the suite was rerun with loopback access.

## GCP status

**Not deployed by this release operation yet.** The prior deployment record describes v0.4.5 as last verified on 2026-09-16; fresh authentication and live inspection are required before asserting today's production state.

Remaining gates: verify current state and budget, isolated PostgreSQL 16/cloud artifact rehearsal, backup/restore, migration and pilot-overlap reconciliation, catalogue import, complete matching embeddings, provenance publication, actual hybrid/model and browser QA, coordinated production cutover and recovery checks. See [the release plan](RELEASE_0.5.0_PLAN.md).

The frozen accessible catalogue is the 2026-09-17 observation. Its source/candidate identities and local reconciliation are recorded in [implementation QA](ANEMONE_V0.5.0_IMPLEMENTATION.md). Candidate embedding coverage at the last QA was 0/6,996; source publication does not satisfy that serving gate.

## Answer-quality follow-up

The [issue draft](ISSUE_ANEMONE_CHAT_QUALITY_DRAFT.md) records confirmed local routing and response-focus bugs. The issue will be filed before GCP deployment with `bug` and `logic` labels and explicit local-only reproduction status; production reproduction will be added after deployment.
