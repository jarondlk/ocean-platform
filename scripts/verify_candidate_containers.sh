#!/usr/bin/env bash
# Cloud Build/local Docker only: isolated containers, synthetic DB, no real secrets.
set -euo pipefail
report_dir=${CANDIDATE_REPORT_DIR:-/workspace/candidate-reports}
mkdir -p "$report_dir"
trap 'docker rm -f ocean-v070-qa-api ocean-v070-qa-frontend ocean-v070-qa-postgres >/dev/null 2>&1 || true' EXIT
docker inspect ocean-candidate-api ocean-candidate-frontend > "$report_dir/images.json"
docker run -d --name ocean-v070-qa-postgres --network cloudbuild \
  -e POSTGRES_USER=ocean -e POSTGRES_PASSWORD=candidate-only-password \
  -e POSTGRES_DB=ocean_platform pgvector/pgvector:pg16
for attempt in $(seq 1 60); do
  if docker exec ocean-v070-qa-postgres pg_isready -U ocean -d ocean_platform; then break; fi
  sleep 1
done
docker exec ocean-v070-qa-postgres pg_isready -U ocean -d ocean_platform
qa_database='postgresql://ocean:candidate-only-password@ocean-v070-qa-postgres:5432/ocean_platform'
docker run --rm --network cloudbuild -e DATABASE_URL="$qa_database" \
  ocean-candidate-api python -m alembic upgrade head
docker run --rm --network cloudbuild -e DATABASE_URL="$qa_database" \
  -e DATABASE_BACKUP_CONTAINER='' ocean-candidate-api \
  python scripts/database_backup.py create --output-dir /tmp/candidate-backups --label candidate-qa --restore-test
docker run --rm --network cloudbuild -e DEPLOYMENT_ENV=test -e AUTH_MODE=disabled \
  ocean-candidate-api python -c '
import importlib, importlib.util, json, os
assert os.getuid() != 0, "API must run as non-root"
for module in ("api.main", "scripts.run_pipeline", "scripts.run_research_analysis", "scripts.run_research_sst_panel", "preprocessing.research_sst"):
    importlib.import_module(module)
for module in ("pip", "setuptools", "wheel"):
    assert importlib.util.find_spec(module) is None, module
from tests.research_fixtures import research_fixture
from preprocessing.edna_detection_frequency import build_detection_frequency
recipe, source, areas, members, links, taxa = research_fixture()
tables = build_detection_frequency(recipe, source, areas, members, links)
sardine = next(row for row in tables["ranking"] if row["species"] == "Sardinops melanostictus")
assert (sardine["detected"], sardine["eligible"]) == (7, 15)
import tempfile, pathlib, numpy as np, xarray as xr
with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "synthetic.nc"
    xr.Dataset({"sst": (("lat", "lon"), np.ones((2, 2)))}).to_netcdf(path)
    with xr.open_dataset(path) as dataset:
        assert dataset.sst.shape == (2, 2)
print(json.dumps({"imports": "passed", "numeric_fixture": "7/15", "netcdf": "passed", "installation_tools": "absent"}))
' > "$report_dir/runtime-imports.json"
docker run -d --name ocean-v070-qa-api --network cloudbuild \
  -e DATABASE_URL="$qa_database" -e DEPLOYMENT_ENV=test -e AUTH_MODE=required \
  -e ENABLE_MOCK_LOGIN=false -e PERSIST_LOCAL_CHAT=false \
  -e INTERNAL_AUTH_SECRET=candidate-only-internal-key-long-enough-2026 ocean-candidate-api
docker run -d --name ocean-v070-qa-frontend --network cloudbuild \
  -e DEPLOYMENT_ENV=test -e AUTH_MODE=required -e ENABLE_MOCK_LOGIN=false \
  -e AUTH_SECRET=candidate-only-session-key-distinct-2026 \
  -e INTERNAL_AUTH_SECRET=candidate-only-internal-key-long-enough-2026 \
  -e AUTH_TRUST_HOST=true -e AUTH_URL=http://ocean-v070-qa-frontend:3000 \
  -e API_BASE_URL=http://ocean-v070-qa-api:8000 -e HOSTNAME=0.0.0.0 ocean-candidate-frontend
docker exec -i ocean-v070-qa-api python - <<'CHECK' > "$report_dir/http-smoke.json"
import json, time, urllib.request, urllib.error
checks = [
    ("http://127.0.0.1:8000/health/live", 200),
    ("http://127.0.0.1:8000/chat/analysis-options", 401),
    ("http://127.0.0.1:8000/research-registry-reviews", 401),
    ("http://ocean-v070-qa-frontend:3000/login", 200),
    ("http://ocean-v070-qa-frontend:3000/api/auth/providers", 200),
    ("http://ocean-v070-qa-frontend:3000/api/backend/chat/analysis-options", 401),
]
results = []
for url, expected in checks:
    for attempt in range(60):
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
            continue
        if status == expected:
            break
        time.sleep(1)
    else:
        raise SystemExit("Candidate smoke failed: " + url)
    results.append({"url": url, "status": status})
print(json.dumps(results))
CHECK
docker exec ocean-v070-qa-frontend node -e '
const fs = require("fs");
for (const path of ["/usr/local/lib/node_modules/npm", "/usr/local/lib/node_modules/corepack", "/usr/local/bin/npm", "/usr/local/bin/npx"]) {
  if (fs.existsSync(path)) throw new Error("Unexpected runtime tooling: " + path);
}
if (process.getuid() === 0) throw new Error("Frontend must run as non-root");
if (process.versions.node.split(".")[0] !== "22") throw new Error("Expected Node 22 runtime");
const osRelease = fs.readFileSync("/etc/os-release", "utf8");
if (!osRelease.includes("VERSION_ID=\"13\"")) throw new Error("Expected Debian 13 runtime");
console.log(JSON.stringify({uid:process.getuid(), node:process.versions.node, os_release:osRelease, installation_tools:"absent"}));
' > "$report_dir/frontend-runtime.json"
docker exec ocean-v070-qa-api id > "$report_dir/api-user.log"
docker logs ocean-v070-qa-api > "$report_dir/api-startup.log" 2>&1
docker logs ocean-v070-qa-frontend > "$report_dir/frontend-startup.log" 2>&1
