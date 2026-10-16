"""C12 required offline acceptance and reused C02/C08/C09/C10 regressions."""
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
    DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/ocean_c12_acceptance_unused",
    MODEL_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:1",
)
tests = [
    "tests/test_edna_catalogue_contract.py",
    "tests/test_edna_catalogue_inputs.py",
    "tests/test_edna_catalogue_query.py",
    "tests/test_frozen_edna_catalogue.py",
    "tests/test_edna_catalogue_adversarial.py",
    "tests/test_edna_service.py",
    "tests/test_edna_aggregation.py",
    "tests/test_edna_taxonomy.py",
    "tests/test_api_edna.py",
    "tests/test_anemone_classification.py",
    "tests/test_classification_application.py",
    "tests/test_classification_review_domain.py",
    "tests/test_edna_analysis.py",
    "tests/test_anemone_catalogue.py",
    "tests/test_anemone_nontarget.py",
    "tests/test_publication_scope_contract.py",
    "tests/test_auto_settings.py",
    "tests/test_research_chat.py",
    "tests/test_chat_source_scope.py",
    "tests/test_conference_demo.py",
    "tests/test_provisional_research_demo.py",
    "tests/test_regional_publication.py",
    "tests/test_research_readiness.py",
    "tests/test_conference_review.py",
    "tests/test_context_catalogue_contract.py",
    "tests/test_context_catalogue_fixtures.py",
    "tests/test_catalogue_snapshots.py",
    "tests/test_catalogue_snapshot_capture.py",
    "tests/test_catalogue_snapshot_transfer.py",
    "tests/test_catalogue_snapshot_fixtures.py",
    "tests/test_catalogue_adapter_contract.py",
    "tests/test_catalogue_adapter_inputs.py",
    "tests/test_frozen_catalogue_adapters.py",
    "tests/test_sst_catalogue_contract.py",
    "tests/test_sst_catalogue_inputs.py",
    "tests/test_frozen_sst_catalogue.py"
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
