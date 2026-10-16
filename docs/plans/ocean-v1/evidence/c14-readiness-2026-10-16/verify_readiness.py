"""Read-only C14 preparation; C13 final hosted delivery remains a separate gate."""
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
    DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/ocean_c14_readiness_unused",
    MODEL_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:1",
)
checks = [
    ("baseline", [sys.executable, "-m", "pytest", "tests/test_catalogue_cache.py",
                  "tests/test_api_security.py", "tests/test_api_schemas.py", "tests/test_auth.py",
                  "-q", "--tb=short"]),
    ("C08-scale-oracle", [sys.executable, "-m", "pytest", "tests/test_context_catalogue_fixtures.py",
                           "-q", "--tb=short"]),
]
for name, script in (
    ("scope", "export_chat_scope.py"), ("schema", "export_context_catalogue.py"),
    ("browser-types", "export_catalogue_types.py"), ("examples", "export_catalogue_examples.py"),
    ("snapshots", "export_catalogue_snapshot.py"),
    ("adapters", "export_catalogue_adapter.py"), ("sst", "export_sst_catalogue.py"),
    ("edna", "export_edna_catalogue.py"), ("scientific", "export_scientific_catalogue.py"),
):
    checks.append((name, [sys.executable, "scripts/" + script, "--check"]))
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
receipt = {
    "checks": results, "safe_environment": {key: environment[key] for key in (
        "AUTH_MODE", "DEPLOYMENT_ENV", "ENABLE_MOCK_LOGIN", "PERSIST_LOCAL_CHAT",
        "RUN_POSTGRES_INTEGRATION", "DATABASE_URL", "MODEL_PROVIDER", "OLLAMA_BASE_URL")},
    "persistent_service_startups": 0, "C14_implementation_started_by_preparation": False,
    "C13_final_hosted_CI_and_delivery_gate": "Pending parent confirmation; not inferred from local readiness checks",
    "scale_scope": "C08 in-memory oracle of 100,000 canonical dataset objects; not C13 registry capacity or authenticated service acceptance",
}
(output / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
sys.exit(results[-1]["exit_code"])
