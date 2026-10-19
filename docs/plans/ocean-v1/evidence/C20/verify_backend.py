"""One source-pinned C20 acceptance run, with unavailable external targets."""
from __future__ import annotations

import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
start = json.loads((HERE / "start-snapshot.json").read_text())
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output-subdir", help="Fresh evidence directory for an intentional verification rerun")
arguments = parser.parse_args()
if arguments.output_subdir:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", arguments.output_subdir):
        parser.error("Expected one lowercase evidence directory")
    HERE = HERE / arguments.output_subdir
    HERE.mkdir(exist_ok=False)
owned = [
    ".github/workflows/tests.yml", "config.py", "api/auth.py", "api/main.py",
    "api/rate_limit.py", "api/v1_runtime_routes.py", "api/research_run_routes.py",
    "db/app_models.py", "schema/research_runs.py",
    "migrations/versions/20261019_0018_research_runs.py",
    "orchestration/research_runs.py", "orchestration/research_dispatch.py",
    "orchestration/research_controller.py", "orchestration/research_controller_budget.py",
    "orchestration/research_controller_replay.py",
    "tests/research_run_support.py", "tests/research_run_postgres_support.py",
    "tests/integration/test_research_runs_postgres.py",
    "tests/integration/test_investigation_postgres.py",
    "tests/test_bootstrap_database.py",
    "tests/test_research_runs.py", "tests/test_research_run_api.py", "tests/test_research_run_http.py",
    "tests/test_research_run_postgres_guard.py", "tests/test_research_run_runtime.py",
    "tests/test_research_controller_replay.py",
    "docs/plans/ocean-v1/evidence/C20/verify_backend.py",
    "docs/plans/ocean-v1/evidence/C20/wire-fixtures.json",
]
paths = sorted(p for p in set(owned) | set(start["formal_current_source_files"]) | set(start["C19_tested_transitive_source_files"]) if not p.startswith("frontend"))

def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}


def save(name, value):
    with (HERE / name).open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


if any((HERE / name).exists() for name in ("backend-tests.txt", "backend-result.json", "backend-tested-source.json", "compatibility-tests.txt")):
    raise RuntimeError("Refusing to rewrite C20 acceptance evidence")
before = hashes()
environment = dict(os.environ, AUTH_MODE="disabled", DEPLOYMENT_ENV="test",
    ENABLE_MOCK_LOGIN="false", PERSIST_LOCAL_CHAT="false", ENABLE_V1_SHELL="false",
    ENABLE_V1_CATALOGUE="false", ENABLE_V1_CATALOGUE_BROWSER="false",
    ENABLE_V1_INVESTIGATIONS="false", ENABLE_V1_RESEARCH_CONTROLLER="false",
    ENABLE_V1_RESEARCH_RUNS="false", ENABLE_V1_RESEARCH_DISPATCH="false",
    RUN_POSTGRES_INTEGRATION="0", DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/ocean_c20_unused",
    MODEL_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:1")
commands = [
    ("compatibility-tests.txt", [sys.executable, "-m", "pytest", "tests/test_auth.py", "tests/test_rate_limit.py", "tests/test_migration_configuration.py", "-q", "--no-cov"]),
    ("backend-tests.txt", [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short", "--cov=api", "--cov=config", "--cov=db", "--cov=preprocessing", "--cov=ingestion", "--cov=orchestration", "--cov=schema", "--cov=evaluation", "--cov-report=term-missing", "--cov-fail-under=70"]),
]
results = []
for name, command in commands:
    started = time.monotonic()
    with (HERE / name).open("x") as log:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=1500)
    results.append({"command": command, "output": name, "seconds": round(time.monotonic()-started, 2), "exit_code": result.returncode})
    print(json.dumps(results[-1]), flush=True)
    if result.returncode:
        break
after = hashes()
changed = [name for name in before if before[name] != after[name]]
save("backend-tested-source.json", {"before_sha256": before, "after_sha256": after, "changed": changed, "owned_paths": owned})
receipt = {"results": results, "source_changed_during_run": changed, "source_paths": len(paths),
    "environment": {key: environment[key] for key in (
        "AUTH_MODE", "DEPLOYMENT_ENV", "ENABLE_MOCK_LOGIN", "PERSIST_LOCAL_CHAT",
        "ENABLE_V1_SHELL", "ENABLE_V1_CATALOGUE", "ENABLE_V1_CATALOGUE_BROWSER",
        "ENABLE_V1_INVESTIGATIONS", "ENABLE_V1_RESEARCH_CONTROLLER",
        "ENABLE_V1_RESEARCH_RUNS", "ENABLE_V1_RESEARCH_DISPATCH",
        "RUN_POSTGRES_INTEGRATION", "DATABASE_URL", "MODEL_PROVIDER", "OLLAMA_BASE_URL",
    )}}
save("backend-result.json", receipt)
print(json.dumps(receipt))
print("\n".join((HERE / results[-1]["output"]).read_text().splitlines()[-4:]))
raise SystemExit(next((item["exit_code"] for item in results if item["exit_code"]), 0) or bool(changed))
