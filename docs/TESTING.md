# Testing and CI

## Local Verification

Install development dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

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
  --cov-fail-under=60
```

Run the security-sensitive lint boundary:

```bash
python -m ruff check \
  api/auth.py api/auth_routes.py api/admin_feedback_routes.py \
  api/chat_records.py api/feedback_routes.py api/rate_limit.py \
  config.py tests/test_auth.py tests/test_security_config.py \
  tests/test_rate_limit.py tests/test_admin_feedback.py \
  tests/test_chat_feedback.py tests/integration/test_app_metadata_postgres.py \
  --select E4,E7,E9,F
```

The lint boundary is intentionally incremental because the older scientific
pipeline has existing lint debt. New security-sensitive modules must remain
clean; broaden the boundary as legacy modules are repaired.

Verify the frontend:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
```

## PostgreSQL Integration

The normal suite skips the integration test. Against a disposable migrated
PostgreSQL/pgvector database:

```bash
DATABASE_URL=postgresql://onagawa:password@127.0.0.1:5432/onagawa_rag \
RUN_POSTGRES_INTEGRATION=1 \
AUTH_MODE=disabled \
DEPLOYMENT_ENV=test \
python -m pytest tests/integration/test_app_metadata_postgres.py -q
```

The test verifies migrated tables, invite acceptance, user persistence, and the
acceptance audit event. Its records are wrapped in an outer transaction and
rolled back.

## CI Checks

`.github/workflows/tests.yml` defines:

- backend tests, 60% aggregate coverage, and security-boundary linting;
- frontend lockfile installation, typechecking, and production build;
- a real pgvector service, Alembic migration, and metadata integration test;
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
