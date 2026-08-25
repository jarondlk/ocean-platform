# Testing and CI

## Current release evidence

For stable release `v0.1.0` and source commit `2820f128`, the local backend
suite passed 454 tests with 3 skipped checks and 74.31% aggregate coverage.
Ruff, frontend typecheck, the production Next.js build, Cloud Build, Cloud Run
candidate checks, authenticated Admin navigation, and the bounded external
evaluation smoke test also passed. CI runs for pushes to `main` and `gcp-dev`
and for pull requests targeting `main`/`master`.

This is a point-in-time release record, not a substitute for rerunning the
commands below after changes.

## Local Verification

Install development dependencies:

```bash
./scripts/bootstrap_dev.sh
source .venv/bin/activate
```

The bootstrap script creates an isolated Python 3.12 environment and installs
the fully transitive development lock with `--require-hashes`. Runtime,
analysis, and archived Streamlit dependencies are separately locked in
`requirements/runtime.txt`, `requirements/analysis.txt`, and
`requirements/archive.txt`.

For browser testing of the permission-aware UI without organization OIDC
credentials, run both services with `AUTH_MODE=required`,
`DEPLOYMENT_ENV=test`, matching `INTERNAL_AUTH_SECRET` values, and
`ENABLE_MOCK_LOGIN=true`. Generate the three required scrypt password hashes
with `python scripts/hash_mock_password.py` and assign them to
`MOCK_VIEWER_PASSWORD_HASH`, `MOCK_RESEARCHER_PASSWORD_HASH`, and
`MOCK_ADMIN_PASSWORD_HASH`. The login page exposes three fixed accounts:
`viewer@mock.invalid`, `researcher@mock.invalid`, and `admin@mock.invalid`.
Each is created once in the isolated test database on first API use so foreign
keys, role changes, suspension, chat, feedback, and audit behavior use the same
application-metadata path as provider-backed users. This harness is rejected in
staging and production and does not replace the final real-provider callback
smoke test. Run it only against an isolated test environment because its
mutations are real within that environment.

Run the backend suite and the same coverage boundary used by CI:

```bash
AUTH_MODE=disabled DEPLOYMENT_ENV=test PERSIST_LOCAL_CHAT=false \
python -m pytest tests/ -q --tb=short \
  --cov=api \
  --cov=config \
  --cov=db \
  --cov=preprocessing \
  --cov=ingestion \
  --cov=orchestration \
  --cov=schema \
  --cov=evaluation \
  --cov-report=term-missing \
  --cov-fail-under=70
```

Run the active Python lint boundary:

```bash
python -m ruff check \
  api config.py db evaluation ingestion orchestration preprocessing \
  retrieval schema scripts tests
```

The lint configuration in `pyproject.toml` covers active Python code. Archived
reference code is intentionally outside this boundary.

Verify the frontend:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
```

## PostgreSQL Integration

The normal suite skips the gated PostgreSQL integration modules. Against a
disposable migrated PostgreSQL/pgvector database:

```bash
DATABASE_URL=postgresql://onagawa:password@127.0.0.1:5432/onagawa_rag \
RUN_POSTGRES_INTEGRATION=1 \
AUTH_MODE=disabled \
DEPLOYMENT_ENV=test \
python -m pytest \
  tests/integration/test_app_metadata_postgres.py \
  tests/integration/test_operational_postgres.py \
  -q
```

The tests verify migrated tables, invite acceptance, user persistence,
database-backed mock identity suspension, audited invitation mutations, and
shared rate-limit behavior. Their records are isolated and cleaned up.

Exercise the database mutation safety path:

```bash
python scripts/load_db.py --upsert --json
python scripts/load_db.py --upsert --json
python scripts/database_backup.py create --label local-check --restore-test
```

The repeated load must be idempotent. The backup command verifies archive
integrity and restores into a disposable database before removing it.

## CI Checks

`.github/workflows/tests.yml` defines:

- backend tests, a 70% aggregate coverage floor, and active Python linting;
- frontend lockfile installation, typechecking, and production build;
- a real pgvector service, Alembic migration, metadata/shared-rate-limit
  integration tests, repeated transactional upserts, and backup restore testing;
- dependency review for public repositories or private repositories with GitHub
  Code Security enabled.

Workflow token permissions are read-only. Official actions are pinned to full
commit SHAs and dependency updates are monitored by
`.github/dependabot.yml`.

For a private repository with GitHub Code Security, set the repository Actions
variable `GH_CODE_SECURITY_ENABLED=true`. Enable these repository settings:

- dependency graph;
- Dependabot alerts and security updates;
- secret scanning and push protection when available;
- CodeQL default setup for Python and JavaScript/TypeScript.

Protect the default branch with the backend, frontend, PostgreSQL integration,
and applicable dependency-review checks.

Package-advisory audits that send dependency metadata to third-party services
are not enabled by this repository configuration. Add them only after the
repository owner approves the service and data-sharing implications.
