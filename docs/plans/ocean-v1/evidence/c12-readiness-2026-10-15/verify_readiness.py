"""C12 offline readiness; no adapter, source database or provider is started."""
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
    DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/ocean_c12_readiness_unused",
    MODEL_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:1",
)
checks = [
    ("baseline", [sys.executable, "-m", "pytest", "tests/test_edna_service.py",
                  "tests/test_edna_aggregation.py", "tests/test_edna_taxonomy.py",
                  "tests/test_api_edna.py", "-q", "--tb=short"]),
    ("prerequisites", [sys.executable, "-m", "pytest",
                       "tests/test_publication_scope_contract.py", "tests/test_auto_settings.py",
                       "tests/test_research_chat.py", "tests/test_chat_source_scope.py",
                       "tests/test_conference_demo.py", "tests/test_provisional_research_demo.py",
                       "tests/test_regional_publication.py", "tests/test_research_readiness.py",
                       "tests/test_conference_review.py", "tests/test_catalogue_snapshots.py",
                       "tests/test_catalogue_snapshot_capture.py", "tests/test_catalogue_snapshot_transfer.py",
                       "tests/test_catalogue_snapshot_fixtures.py", "tests/test_context_catalogue_contract.py",
                       "tests/test_context_catalogue_fixtures.py", "-q", "--tb=short"]),
    ("edna-semantics", [sys.executable, "-m", "pytest",
                        "tests/test_anemone_classification.py", "tests/test_classification_application.py",
                        "tests/test_edna_analysis.py", "tests/test_anemone_catalogue.py",
                        "tests/test_anemone_nontarget.py", "-q", "--tb=short"]),
]
for name, script in (
    ("scope", "export_chat_scope.py"), ("schema", "export_context_catalogue.py"),
    ("browser-types", "export_catalogue_types.py"), ("examples", "export_catalogue_examples.py"),
    ("snapshots", "export_catalogue_snapshot.py"),
    ("neighbor-adapters", "export_catalogue_adapter.py"), ("neighbor-sst", "export_sst_catalogue.py"),
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
           "temporary_loopback_fixture_servers": "Semantic fixtures start and close local HTTP servers",
           "C12_implementation_started": False}
(output / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
sys.exit(results[-1]["exit_code"])
