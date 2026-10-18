"""One source-pinned C19 acceptance run, with unavailable external targets."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
start = json.loads((HERE / "start-snapshot.json").read_text())
owned = ["config.py", "schema/research_controller.py", *[
    "orchestration/" + name + ".py" for name in (
        "research_controller", "research_controller_budget",
        "research_controller_observations", "research_controller_scope",
    )
], *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "tests").glob("test_research_controller*.py"))]]
paths = sorted(set(owned) | set(start["formal_current_source_files"]) | set(start["C18_accepted_source"]))


def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}


def save(name, value):
    with (HERE / name).open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


if any((HERE / name).exists() for name in ("backend-tests.txt", "backend-result.json", "backend-tested-source.json", "compatibility-tests.txt")):
    raise RuntimeError("Refusing to rewrite C19 acceptance evidence")
before = hashes()
environment = dict(os.environ, AUTH_MODE="disabled", DEPLOYMENT_ENV="test",
    ENABLE_MOCK_LOGIN="false", PERSIST_LOCAL_CHAT="false", ENABLE_V1_SHELL="false",
    ENABLE_V1_CATALOGUE="false", ENABLE_V1_CATALOGUE_BROWSER="false",
    ENABLE_V1_INVESTIGATIONS="false", ENABLE_V1_RESEARCH_CONTROLLER="false",
    RUN_POSTGRES_INTEGRATION="0", DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/ocean_c19_unused",
    MODEL_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:1")
commands = [
    ("compatibility-tests.txt", [sys.executable, "-m", "pytest", "tests/test_research_chat.py", "tests/test_model_runtime.py", "tests/test_chat_source_scope.py", "-q", "--no-cov"]),
    ("backend-tests.txt", [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short", "--cov=api", "--cov=config", "--cov=db", "--cov=preprocessing", "--cov=ingestion", "--cov=orchestration", "--cov=schema", "--cov=evaluation", "--cov-report=term-missing", "--cov-fail-under=70"]),
]
results = []
for name, command in commands:
    started = time.monotonic()
    with (HERE / name).open("x") as log:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
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
        "RUN_POSTGRES_INTEGRATION", "DATABASE_URL", "MODEL_PROVIDER", "OLLAMA_BASE_URL",
    )}}
save("backend-result.json", receipt)
print(json.dumps(receipt))
print("\n".join((HERE / results[-1]["output"]).read_text().splitlines()[-4:]))
raise SystemExit(next((item["exit_code"] for item in results if item["exit_code"]), 0) or bool(changed))
