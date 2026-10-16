"""Read-only C15 baselines; C14 delivery remains an explicit later pipeline gate."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[4]
node = shutil.which("node")
npm = shutil.which("npm")
assert node and npm, "Existing local Node and npm are required"
environment = dict(os.environ, NEXT_TELEMETRY_DISABLED="1", CI="1", DEPLOYMENT_ENV="test")
environment["PATH"] = str(Path(node).parent) + os.pathsep + environment.get("PATH", "")
env_files = sorted(path.name for path in (ROOT / "frontend-v1").glob(".env*"))
assert not env_files, "Review v1 environment files before a baseline build"
checks = [
    ("v1-tests", [npm, "--prefix", "frontend-v1", "test"]),
    ("v1-typecheck", [npm, "--prefix", "frontend-v1", "run", "typecheck"]),
    ("v1-build", [npm, "--prefix", "frontend-v1", "run", "build"]),
]
for name, script in (
    ("scope", "export_chat_scope.py"), ("schema", "export_context_catalogue.py"),
    ("browser-types", "export_catalogue_types.py"), ("examples", "export_catalogue_examples.py"),
    ("snapshots", "export_catalogue_snapshot.py"), ("adapters", "export_catalogue_adapter.py"),
    ("sst", "export_sst_catalogue.py"), ("edna", "export_edna_catalogue.py"),
    ("scientific", "export_scientific_catalogue.py"),
):
    checks.append((name, [sys.executable, "scripts/" + script, "--check"]))

results = []
for name, command in checks:
    started = time.monotonic()
    with (OUTPUT / f"{name}.txt").open("w") as log:
        process = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
    lines = (OUTPUT / f"{name}.txt").read_text().splitlines()
    results.append({
        "name": name,
        "command": command,
        "exit_code": process.returncode,
        "duration_seconds": round(time.monotonic() - started, 2),
        "summary": lines[-1] if lines else "No output; exit recorded above",
    })
    if process.returncode:
        break

receipt = {
    "component": "C15 read-only readiness preparation",
    "checks": results,
    "runtime": {
        "node_path": node,
        "node_version": subprocess.check_output([node, "--version"]).decode().strip(),
        "npm_path": npm,
        "npm_version": subprocess.check_output([npm, "--version"]).decode().strip(),
        "v1_environment_files": env_files,
        "dependency_installations": 0,
        "persistent_services_started": 0,
        "application_source_changes": 0,
        "build_outputs": "Only ignored frontend-v1/.next and frontend-v1/out outputs",
        "network_dependency": "Existing local modules only; no provider, model, database or production calls",
    },
    "C14_final_source_CI_and_delivery_gate": "Pending parent confirmation",
    "C15_implementation_started": False,
}
(OUTPUT / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
sys.exit(results[-1]["exit_code"])
