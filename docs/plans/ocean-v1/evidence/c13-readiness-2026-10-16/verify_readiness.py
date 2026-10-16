"""C13 offline readiness against the accepted C12 checkout; no live services."""
from __future__ import annotations

import argparse
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
    DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/ocean_c13_readiness_unused",
    MODEL_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:1",
)
groups = {
    "baseline": ["test_research_registry.py", "test_research_chat.py",
                 "test_edna_environment.py", "test_regional_publication.py"],
    "scientific-prerequisites": [
        "test_publication_scope_contract.py", "test_auto_settings.py", "test_chat_source_scope.py",
        "test_conference_demo.py", "test_provisional_research_demo.py",
        "test_research_readiness.py", "test_conference_review.py",
        "test_reliability.py", "test_pre_analysis.py", "test_statistical_analysis.py",
        "test_derived_artifact_eligibility.py", "test_remote_sensing.py",
        "test_immutable_bundle_security.py",
    ],
    "catalogue-prerequisites": [
        "test_context_catalogue_contract.py", "test_context_catalogue_fixtures.py",
        "test_catalogue_snapshots.py", "test_catalogue_snapshot_capture.py",
        "test_catalogue_snapshot_transfer.py", "test_catalogue_snapshot_fixtures.py",
        "test_catalogue_adapter_contract.py", "test_catalogue_adapter_inputs.py",
        "test_frozen_catalogue_adapters.py", "test_sst_catalogue_contract.py",
        "test_sst_catalogue_inputs.py", "test_frozen_sst_catalogue.py",
        "test_edna_catalogue_contract.py", "test_edna_catalogue_inputs.py",
        "test_edna_catalogue_query.py", "test_frozen_edna_catalogue.py",
        "test_edna_catalogue_adversarial.py",
    ],
}
checks = [(name, [sys.executable, "-m", "pytest", *["tests/" + p for p in paths],
                  "-q", "--tb=short"]) for name, paths in groups.items()]
for name, script in (
    ("scope", "export_chat_scope.py"), ("schema", "export_context_catalogue.py"),
    ("browser-types", "export_catalogue_types.py"), ("examples", "export_catalogue_examples.py"),
    ("snapshots", "export_catalogue_snapshot.py"),
    ("adapters", "export_catalogue_adapter.py"), ("sst", "export_sst_catalogue.py"),
    ("edna", "export_edna_catalogue.py"),
):
    checks.append((name, [sys.executable, "scripts/" + script, "--check"]))
parser = argparse.ArgumentParser()
parser.add_argument("--from-check", choices=[name for name, _ in checks])
arguments = parser.parse_args()
start = [name for name, _ in checks].index(arguments.from_check) if arguments.from_check else 0
results = []
if start:
    results = json.loads((output / "results.json").read_text())["checks"][:start]
    if len(results) != start or any(item["exit_code"] for item in results):
        raise ValueError("Resume requires successful preceding checks")
for name, command in checks[start:]:
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
           "persistent_service_startups": 0,
           "temporary_loopback_fixture_servers": "Any local HTTP fixtures are synthetic and closed by tests",
           "C13_implementation_started": False}
(output / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
sys.exit(results[-1]["exit_code"])
