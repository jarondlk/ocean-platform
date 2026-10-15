"""C10 offline readiness checks; no adapters or live services are started."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

output = Path(__file__).resolve().parent
root = output.parents[4]
environment = dict(
    os.environ, AUTH_MODE="disabled", DEPLOYMENT_ENV="test",
    ENABLE_MOCK_LOGIN="false", PERSIST_LOCAL_CHAT="false", RUN_POSTGRES_INTEGRATION="0",
    DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/ocean_c10_readiness_unused",
    MODEL_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:1",
)
checks = [
    ("baseline", [sys.executable, "-m", "pytest", "tests/test_ctd.py",
                  "tests/test_metagenome_loaders.py", "tests/test_overview_coverage.py",
                  "-q", "--tb=short"]),
    ("prerequisites", [sys.executable, "-m", "pytest",
                       "tests/test_reliability.py", "tests/test_pre_analysis.py",
                       "tests/test_statistical_analysis.py", "tests/test_derived_artifact_eligibility.py",
                       "tests/test_remote_sensing.py", "tests/test_catalogue_snapshots.py",
                       "tests/test_catalogue_snapshot_capture.py", "tests/test_catalogue_snapshot_transfer.py",
                       "tests/test_catalogue_snapshot_fixtures.py", "tests/test_context_catalogue_contract.py",
                       "tests/test_context_catalogue_fixtures.py", "tests/test_metagenome_document_contract.py",
                       "-q", "--tb=short"]),
    ("schema", [sys.executable, "scripts/export_context_catalogue.py", "--check"]),
    ("browser-types", [sys.executable, "scripts/export_catalogue_types.py", "--check"]),
    ("examples", [sys.executable, "scripts/export_catalogue_examples.py", "--check"]),
    ("snapshots", [sys.executable, "scripts/export_catalogue_snapshot.py", "--check"]),
    ("scope", [sys.executable, "scripts/export_chat_scope.py", "--check"]),
]
results = []
for name, command in checks:
    with (output / f"{name}.txt").open("w") as log:
        process = subprocess.run(command, cwd=root, env=environment,
                                 stdout=log, stderr=subprocess.STDOUT)
    lines = (output / f"{name}.txt").read_text().splitlines()
    results.append({"name": name, "command": command, "exit_code": process.returncode,
                    "summary": lines[-1] if lines else "No output; exit recorded above"})
    if process.returncode:
        break
receipt = {"checks": results, "safe_environment": {key: environment[key] for key in (
    "AUTH_MODE", "DEPLOYMENT_ENV", "ENABLE_MOCK_LOGIN", "PERSIST_LOCAL_CHAT",
    "RUN_POSTGRES_INTEGRATION", "DATABASE_URL", "MODEL_PROVIDER", "OLLAMA_BASE_URL")},
           "service_startups": 0, "C10_implementation_started": False}
(output / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
sys.exit(results[-1]["exit_code"])
