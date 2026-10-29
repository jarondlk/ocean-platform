"""Hosted backend CI verifies generated C22/C25 browser registries without Node."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_review_and_execution_browser_contracts_match_current_python_models():
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts/export_experiment_contract.py'), '--check'],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
