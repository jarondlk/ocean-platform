#!/usr/bin/env bash
set -euo pipefail
report_dir=${CANDIDATE_REPORT_DIR:-/workspace/candidate-reports}
trap 'docker rm -f ocean-context-qa-postgres >/dev/null 2>&1 || true' EXIT
docker run -d --name ocean-context-qa-postgres --network cloudbuild -e POSTGRES_USER=ocean -e POSTGRES_PASSWORD=context-fixture-only -e POSTGRES_DB=ocean_platform pgvector/pgvector:pg16
for attempt in $(seq 1 60); do
  if docker exec ocean-context-qa-postgres pg_isready -h 127.0.0.1 -U ocean; then break; fi
  sleep 1
done
docker exec ocean-context-qa-postgres pg_isready -h 127.0.0.1 -U ocean
docker exec ocean-context-qa-postgres psql -U ocean -d ocean_platform -c 'CREATE EXTENSION IF NOT EXISTS vector'
# Tooling is installed only in an ephemeral test venv, never in the release image.
docker run --rm --user 0 --network cloudbuild -e AUTH_MODE=disabled -e DEPLOYMENT_ENV=test -e RUN_POSTGRES_INTEGRATION=1 -e DATABASE_URL=postgresql://ocean:context-fixture-only@ocean-context-qa-postgres:5432/ocean_platform ocean-candidate-api sh -ceu '
python -m venv --system-site-packages /tmp/context-tests
/tmp/context-tests/bin/pip install pytest==9.1.1 httpx==0.28.1
/tmp/context-tests/bin/python -m pytest tests/integration/test_cop17_location_context_postgres.py tests/integration/test_cop17_geography_aggregate_postgres.py tests/integration/test_cop17_location_reuse_postgres.py tests/integration/test_cop17_location_aggregate_postgres.py tests/test_edna_location_counts.py tests/test_edna_geography.py -q --tb=short
' 2>&1 | tee "$report_dir/location-context-postgres.log"
