"""One source-bound C17 backend run against explicit unavailable external targets."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

output = Path(__file__).resolve().parent
root = output.parents[4]
names = (
    ".github/workflows/tests.yml", "api/auth.py", "api/main.py", "config.py", "db/app_models.py",
    "api/investigation_routes.py", "schema/investigations.py", "orchestration/investigations.py",
    "migrations/versions/20261018_0017_investigations.py",
    *(str(path.relative_to(root)) for path in sorted((root / "tests").glob("*investigation*.py"))),
    *(str(path.relative_to(root)) for path in sorted((root / "tests/integration").glob("*investigation*.py"))),
)


def hashes():
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


if any((output / name).exists() for name in ("backend-tests.txt", "backend-result.json", "backend-tested-source.json")):
    raise RuntimeError("Existing C17 full-run receipts cannot be rewritten")
before = hashes()
environment = dict(
    os.environ, AUTH_MODE="disabled", DEPLOYMENT_ENV="test", ENABLE_V1_SHELL="false",
    ENABLE_V1_CATALOGUE="false", ENABLE_V1_CATALOGUE_BROWSER="false", ENABLE_V1_INVESTIGATIONS="false",
    ENABLE_MOCK_LOGIN="false", PERSIST_LOCAL_CHAT="false", RUN_POSTGRES_INTEGRATION="0",
    DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/ocean_c17_regressions_unused",
    MODEL_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:1",
)
command = [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short",
           "--cov=api", "--cov=config", "--cov=db", "--cov=preprocessing", "--cov=ingestion",
           "--cov=orchestration", "--cov=schema", "--cov=evaluation", "--cov-report=term-missing",
           "--cov-fail-under=70"]
started = time.monotonic()
with (output / "backend-tests.txt").open("x") as log:
    result = subprocess.run(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
after = hashes()
changed = [name for name in before if before[name] != after[name]]
with (output / "backend-tested-source.json").open("x") as stream:
    stream.write(json.dumps({"before_sha256": before, "after_sha256": after, "changed": changed}, indent=2) + "\n")
receipt = {"command": command, "seconds": round(time.monotonic() - started, 2), "exit_code": result.returncode,
           "source_changed_during_run": changed,
           "safe_environment": {key: value for key, value in environment.items() if key in (
               "AUTH_MODE", "DEPLOYMENT_ENV", "ENABLE_V1_SHELL", "ENABLE_V1_CATALOGUE", "ENABLE_V1_CATALOGUE_BROWSER",
               "ENABLE_V1_INVESTIGATIONS", "ENABLE_MOCK_LOGIN", "PERSIST_LOCAL_CHAT", "RUN_POSTGRES_INTEGRATION",
               "DATABASE_URL", "MODEL_PROVIDER", "OLLAMA_BASE_URL")}}
with (output / "backend-result.json").open("x") as stream:
    stream.write(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
print("\n".join((output / "backend-tests.txt").read_text().splitlines()[-4:]))
raise SystemExit(result.returncode or bool(changed))
