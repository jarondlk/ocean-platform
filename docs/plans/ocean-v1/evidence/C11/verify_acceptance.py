"""C11 required offline acceptance and reused C02/C08/C09/C10 regressions."""
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
    DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/ocean_c11_acceptance_unused",
    MODEL_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:1",
)
tests = [
    "tests/test_sst_catalogue_contract.py", "tests/test_sst_catalogue_inputs.py",
    "tests/test_frozen_sst_catalogue.py",
    "tests/test_sst_nasa_context.py", "tests/test_research_sst.py",
    "tests/test_regional_publication.py", "tests/test_overview_coverage.py",
    "tests/test_reliability.py", "tests/test_pre_analysis.py",
    "tests/test_statistical_analysis.py", "tests/test_derived_artifact_eligibility.py",
    "tests/test_remote_sensing.py", "tests/test_catalogue_snapshots.py",
    "tests/test_catalogue_snapshot_capture.py", "tests/test_catalogue_snapshot_transfer.py",
    "tests/test_catalogue_snapshot_fixtures.py", "tests/test_context_catalogue_contract.py",
    "tests/test_context_catalogue_fixtures.py", "tests/test_historical_sst_acquisition.py",
    "tests/test_sst_context_review.py", "tests/test_regional_context_normalization.py",
    "tests/test_research_sst_panel.py", "tests/test_research_sst_collection.py",
    "tests/test_catalogue_adapter_contract.py", "tests/test_catalogue_adapter_inputs.py",
    "tests/test_frozen_catalogue_adapters.py",
]
command = [sys.executable, "-m", "pytest", *tests, "-q", "--tb=short"]
with (output / "required-tests.txt").open("w") as log:
    result = subprocess.run(command, cwd=root, env=environment,
                            stdout=log, stderr=subprocess.STDOUT)
receipt = {"command": command, "exit_code": result.returncode,
           "summary": (output / "required-tests.txt").read_text().splitlines()[-1],
           "safe_environment": {key: environment[key] for key in (
               "AUTH_MODE", "DEPLOYMENT_ENV", "ENABLE_MOCK_LOGIN", "PERSIST_LOCAL_CHAT",
               "RUN_POSTGRES_INTEGRATION", "DATABASE_URL", "MODEL_PROVIDER", "OLLAMA_BASE_URL")}}
(output / "required-result.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
sys.exit(result.returncode)
